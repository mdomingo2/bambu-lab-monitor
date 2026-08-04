"""
MQTT connection manager for Bambu Lab printers.

Each printer gets its own PrinterConnection that runs a Paho MQTT client on a
background daemon thread. The client connects to the printer's local broker
(port 8883, TLS, username bblp / access_code), subscribes to the report topic,
and calls the on_status callback whenever a new status snapshot is parsed.

MQTTManager owns all connections and provides a thread-safe publish() method
for sending commands (print control, LED control, etc.) back to the printer.
"""

import json
import ssl
import time
import threading
import logging
from datetime import datetime, timezone
from typing import Callable

import paho.mqtt.client as mqtt

from models import Printer, PrinterStatus, AMSTray, AMSUnit, HMSAlert

logger = logging.getLogger(__name__)

MQTT_PORT = 8883
MQTT_USERNAME = "bblp"
RECONNECT_DELAY = 30        # seconds between outer reconnect attempts
OFFLINE_GRACE_SECS = 20    # don't mark OFFLINE until disconnected this long
RECONNECT_MIN_DELAY = 5    # Paho exponential-backoff floor (seconds)
RECONNECT_MAX_DELAY = 60   # Paho exponential-backoff ceiling (seconds)

# Maps stg_cur integers to human-readable stage labels shown in the UI.
STAGE_LABELS: dict[int, str] = {
    0:   "",
    1:   "Leveling",
    2:   "Preheating bed",
    3:   "Sweeping XY",
    4:   "Changing filament",
    5:   "Paused",
    6:   "Filament runout",
    7:   "Cooling bed",
    8:   "Heating nozzle",
    9:   "Heating bed",
    10:  "Scanning extruder",
    11:  "Scanning bed",
    12:  "First layer scan",
    14:  "Waiting for user",
    17:  "Calibrating",
    20:  "First layer check",
    255: "",
}


class PrinterConnection:
    """Manages a single Bambu printer's MQTT connection and status parsing."""

    def __init__(self, printer: Printer, on_status: Callable[[PrinterStatus], None]):
        self.printer = printer
        self.on_status = on_status
        self.status = PrinterStatus(printer_id=printer.id)
        self._client: mqtt.Client | None = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._offline_timer: threading.Timer | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._offline_timer is not None:
            self._offline_timer.cancel()
            self._offline_timer = None
        if self._client:
            try:
                self._client.disconnect()
                self._client.loop_stop()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Internal MQTT loop
    # ------------------------------------------------------------------

    def _build_client(self) -> mqtt.Client:
        """Create and configure a Paho MQTT client for this printer."""
        client = mqtt.Client(
            client_id=f"bambu_farm_{self.printer.id[:8]}",
            protocol=mqtt.MQTTv311,
        )
        client.username_pw_set(MQTT_USERNAME, self.printer.access_code)

        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        client.tls_set_context(ctx)

        # Exponential backoff so we don't hammer the printer when it only
        # allows one MQTT client at a time (common with LAN-mode printers).
        client.reconnect_delay_set(
            min_delay=RECONNECT_MIN_DELAY,
            max_delay=RECONNECT_MAX_DELAY,
        )

        client.on_connect    = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message    = self._on_message
        return client

    def _run(self) -> None:
        """Background thread: connect, loop, reconnect on failure."""
        while self._running:
            try:
                self._client = self._build_client()
                self._client.connect(self.printer.ip, MQTT_PORT, keepalive=60)
                self._client.loop_forever(retry_first_connection=False)
            except Exception as exc:
                logger.warning(f"[{self.printer.name}] MQTT error: {exc}")
                self.status.connected = False
                self.status.gcode_state = "OFFLINE"
                self.on_status(self.status)
            if self._running:
                time.sleep(RECONNECT_DELAY)

    # ------------------------------------------------------------------
    # Paho callbacks
    # ------------------------------------------------------------------

    def _on_connect(self, client, userdata, flags, rc) -> None:
        if rc != 0:
            logger.warning(f"[{self.printer.name}] MQTT connect failed rc={rc}")
            return
        # Cancel any pending "mark offline" timer — we're back online.
        if self._offline_timer is not None:
            self._offline_timer.cancel()
            self._offline_timer = None
        logger.info(f"[{self.printer.name}] MQTT connected")
        # Subscribe to the printer's report topic, then request a full push.
        client.subscribe(f"device/{self.printer.serial}/report", qos=0)
        client.publish(
            f"device/{self.printer.serial}/request",
            json.dumps({"pushing": {"sequence_id": "0", "command": "pushall"}}),
            qos=0,
        )

    def _on_disconnect(self, client, userdata, rc) -> None:
        logger.info(f"[{self.printer.name}] MQTT disconnected rc={rc}")
        self.status.connected = False
        # Don't mark OFFLINE immediately — LAN-mode printers often reconnect
        # within seconds (single-client broker limit). Wait OFFLINE_GRACE_SECS
        # before declaring the printer truly offline to avoid UI flicker.
        if self._offline_timer is not None:
            self._offline_timer.cancel()
        self._offline_timer = threading.Timer(
            OFFLINE_GRACE_SECS, self._mark_offline
        )
        self._offline_timer.daemon = True
        self._offline_timer.start()

    def _mark_offline(self) -> None:
        """Called by the grace-period timer if we haven't reconnected in time."""
        self._offline_timer = None
        if not self.status.connected:
            logger.info(f"[{self.printer.name}] marking OFFLINE after grace period")
            self.status.gcode_state = "OFFLINE"
            self.on_status(self.status)

    def _on_message(self, client, userdata, msg) -> None:
        try:
            data = json.loads(msg.payload)
            self._parse_report(data)
        except Exception as exc:
            logger.debug(f"[{self.printer.name}] parse error: {exc}")

    # ------------------------------------------------------------------
    # Status parsing
    # ------------------------------------------------------------------

    def _parse_report(self, data: dict) -> None:
        """Extract status fields from a Bambu MQTT report payload.

        All state lives under the 'print' key in the report. We only update
        fields that are present in the message so stale values from a prior
        full-push aren't overwritten by sparse heartbeat messages.
        """
        print_data = data.get("print", {})
        if not print_data:
            return

        s = self.status
        s.connected = True

        # Core print state
        s.gcode_state    = print_data.get("gcode_state", s.gcode_state)
        s.progress       = int(print_data.get("mc_percent", s.progress))
        s.remaining_time = int(print_data.get("mc_remaining_time", s.remaining_time))
        s.layer_num      = int(print_data.get("layer_num", s.layer_num))
        s.total_layers   = int(print_data.get("total_layer_num", s.total_layers))

        # Temperatures
        s.nozzle_temp   = float(print_data.get("nozzle_temper",        s.nozzle_temp))
        s.nozzle_target = float(print_data.get("nozzle_target_temper", s.nozzle_target))
        s.bed_temp      = float(print_data.get("bed_temper",           s.bed_temp))
        s.bed_target    = float(print_data.get("bed_target_temper",    s.bed_target))
        s.chamber_temp  = float(print_data.get("chamber_temper",       s.chamber_temp))

        # File identifiers
        s.current_file = print_data.get("subtask_name", s.current_file)
        s.cover_file   = print_data.get("cover_file",   s.cover_file)
        s.gcode_file   = print_data.get("gcode_file",   s.gcode_file)

        # Speed
        s.speed_level = int(print_data.get("spd_lvl", s.speed_level))
        try:
            s.speed_pct = int(print_data.get("spd_mag", s.speed_pct))
        except Exception:
            pass

        # Misc
        s.wifi_signal     = print_data.get("wifi_signal", s.wifi_signal)
        s.nozzle_diameter = str(print_data.get("nozzle_diameter", s.nozzle_diameter))
        s.nozzle_type     = print_data.get("nozzle_type", s.nozzle_type)
        s.print_error     = int(print_data.get("print_error", s.print_error))
        if "print_type" in print_data:
            s.print_type = print_data["print_type"]

        # Stage label
        try:
            s.stage = STAGE_LABELS.get(int(print_data.get("stg_cur", -1)), "")
        except Exception:
            s.stage = ""

        # Fan speeds — Bambu reports 0–15, convert to 0–100 %.
        # Use a sentinel so 0 (fan genuinely off) is preserved and not
        # treated as "missing" by the `or` fallback.
        _MISSING = object()

        def _fan(key: str):
            raw = print_data.get(key, _MISSING)
            if raw is _MISSING:
                return _MISSING
            try:
                return round(int(raw) / 15 * 100)
            except Exception:
                return _MISSING

        for attr, key in (
            ("fan_speed",          "cooling_fan_speed"),
            ("heatbreak_fan_speed","heatbreak_fan_speed"),
            ("aux_fan_speed",      "big_fan1_speed"),
            ("chamber_fan_speed",  "big_fan2_speed"),
        ):
            val = _fan(key)
            if val is not _MISSING:
                setattr(s, attr, val)

        # Chamber light state
        for light in print_data.get("lights_report", []):
            if light.get("node") == "chamber_light":
                s.chamber_light = light.get("mode", "")

        # HMS (Health Management System) alerts.
        # Each entry has 'attr' and 'code' as 32-bit integers. We split each
        # into two 16-bit words to produce the HMS_AAAA-BBBB-CCCC-DDDD string
        # used in Bambu wiki troubleshooting URLs.
        hms_raw = print_data.get("hms", [])
        if isinstance(hms_raw, list):
            alerts = []
            for entry in hms_raw:
                try:
                    attr = int(entry.get("attr", 0))
                    code = int(entry.get("code", 0))
                    hms_code = "HMS_{:04X}-{:04X}-{:04X}-{:04X}".format(
                        (attr >> 16) & 0xFFFF,
                        attr         & 0xFFFF,
                        (code >> 16) & 0xFFFF,
                        code         & 0xFFFF,
                    )
                    # Wiki URL format: no "HMS_" prefix, hyphens → underscores
                    # e.g. HMS_0300-0100-0001-0003 → /hmscode/0300_0100_0001_0003
                    wiki_slug = hms_code.removeprefix("HMS_").replace("-", "_")
                    alerts.append(HMSAlert(
                        attr=attr,
                        code=code,
                        hms_code=hms_code,
                        wiki_url=(
                            "https://wiki.bambulab.com/en/x1/troubleshooting"
                            f"/hmscode/{wiki_slug}"
                        ),
                    ))
                except Exception:
                    pass
            s.hms_alerts = alerts

        # XCam AI feature toggles (not detection events)
        xcam = print_data.get("xcam", {})
        if xcam:
            s.xcam_spaghetti_enabled    = bool(xcam.get("spaghetti_detect",    False))
            s.xcam_halt_enabled         = bool(xcam.get("print_halt",          False))
            s.xcam_first_layer_enabled  = bool(xcam.get("first_layer_inspect", False))

        # Virtual/external tray (filament loaded without AMS, slot id 254)
        vt = print_data.get("vt_tray", {})
        if vt and vt.get("tray_type"):
            raw_color = vt.get("tray_color", "FFFFFFFF")
            s.vt_tray = AMSTray(
                slot=254,
                tray_type=vt.get("tray_type", ""),
                color="#" + raw_color[:6] if len(raw_color) >= 6 else "#FFFFFF",
                remain=int(vt.get("remain", 0)),
                sub_brand=vt.get("tray_sub_brands", ""),
            )

        # AMS units and trays
        ams_data = print_data.get("ams", {})
        if ams_data and "ams" in ams_data:
            trays: list[AMSTray] = []
            units: list[AMSUnit] = []
            for unit_idx, ams_unit in enumerate(ams_data.get("ams", [])):
                try:
                    raw_trays = ams_unit.get("tray", [])
                    # Count raw tray entries (incl. empty slots) reported by
                    # the firmware — this gives the physical slot capacity.
                    # A single-slot AMS HT sends 1 entry; standard AMS sends 4.
                    slot_count = len(raw_trays) if raw_trays else 4
                    units.append(AMSUnit(
                        unit_id=unit_idx,
                        humidity=int(ams_unit.get("humidity", 0)),
                        temp=float(ams_unit.get("temp", 0.0)),
                        slot_count=slot_count,
                    ))
                except Exception:
                    pass
                for tray in ams_unit.get("tray", []):
                    tray_type = tray.get("tray_type", "")
                    if not tray_type:
                        continue
                    raw_color = tray.get("tray_color", "FFFFFFFF")
                    trays.append(AMSTray(
                        slot=unit_idx * 4 + int(tray.get("id", 0)),
                        tray_type=tray_type,
                        color="#" + raw_color[:6] if len(raw_color) >= 6 else "#FFFFFF",
                        remain=int(tray.get("remain", 0)),
                        sub_brand=tray.get("tray_sub_brands", ""),
                    ))
            if trays:
                s.ams_trays = trays
            if units:
                s.ams_units = units
            try:
                s.ams_current_tray = int(ams_data.get("tray_now", -1))
            except Exception:
                pass

        s.last_update = datetime.now(timezone.utc).isoformat()
        self.on_status(s)


class MQTTManager:
    """Owns all printer MQTT connections and provides a unified publish API."""

    def __init__(self, on_status: Callable[[PrinterStatus], None]):
        self.on_status = on_status
        self._connections: dict[str, PrinterConnection] = {}

    def add_printer(self, printer: Printer) -> None:
        """Start (or restart) a connection for the given printer."""
        if printer.id in self._connections:
            self._connections[printer.id].stop()
        conn = PrinterConnection(printer, self.on_status)
        self._connections[printer.id] = conn
        conn.start()

    def remove_printer(self, printer_id: str) -> None:
        conn = self._connections.pop(printer_id, None)
        if conn:
            conn.stop()

    def update_printer(self, printer: Printer) -> None:
        """Reconnect with updated credentials/IP."""
        self.remove_printer(printer.id)
        self.add_printer(printer)

    def get_status(self, printer_id: str) -> PrinterStatus | None:
        conn = self._connections.get(printer_id)
        return conn.status if conn else None

    def get_all_statuses(self) -> dict[str, PrinterStatus]:
        return {pid: conn.status for pid, conn in self._connections.items()}

    def publish(self, printer_id: str, payload: dict) -> bool:
        """Send a JSON command to a printer via its existing MQTT connection.

        Thread-safe: Paho's publish() queues the message for the loop_forever
        thread. Returns False if no connection exists for this printer.
        """
        conn = self._connections.get(printer_id)
        if not conn or not conn._client:
            logger.warning(f"[{printer_id}] publish: no active client")
            return False
        topic = f"device/{conn.printer.serial}/request"
        try:
            conn._client.publish(topic, json.dumps(payload), qos=0)
            return True
        except Exception as exc:
            logger.warning(f"[{printer_id}] publish failed: {exc}")
            return False

    def stop_all(self) -> None:
        for conn in self._connections.values():
            conn.stop()
        self._connections.clear()
