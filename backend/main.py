"""
Bambu Farm Monitor — FastAPI backend.

Responsibilities:
  - Persist printer configs via SQLite (database.py)
  - Bridge printer MQTT streams to WebSocket clients (mqtt_manager.py)
  - Serve print thumbnails fetched over implicit FTPS from the printer SD card
  - Proxy light/print-control commands back to printers via MQTT
  - Register printer RTSP streams with go2rtc for WebRTC camera viewing
  - Track print history and broadcast lifecycle events over WebSocket
"""

import asyncio
import ftplib
import io
import logging
import os
import ssl
import subprocess
import tempfile
import zipfile
from contextlib import asynccontextmanager
from typing import Set

import httpx
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

import database as db
from models import (
    Printer, PrinterCreate, PrinterUpdate,
    PrinterStatus, PrintControl, LightControl, SettingsUpdate, AlertDismiss,
)
from mqtt_manager import MQTTManager

# ---------------------------------------------------------------------------
# Logging — configure before any module-level logger calls
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
GO2RTC_URL = os.getenv("GO2RTC_URL", "http://go2rtc:1984")

# Minimum chamber temperature (°C) to display. Printers without an enclosure
# or in cloud mode report 0–5 °C; suppress those readings.
CHAMBER_TEMP_MIN_DISPLAY = 15

# Thumbnail paths inside Bambu .gcode.3mf ZIP archives, tried in preference
# order. These are plate renders written by Bambu Studio / Orca Slicer.
_3MF_THUMBNAIL_PATHS = [
    "Metadata/plate_1.png",         # full-size plate render (most common)
    "Metadata/plate_1_small.png",
    "Metadata/top_1.png",           # top-down view
    "Metadata/pick_1.png",          # isometric pick view
    "Metadata/plate_2.png",         # multi-plate jobs
    "Metadata/thumbnail_v2.png",    # older Bambu Studio format
    "Metadata/thumbnail.png",
    "Metadata/thumbnail_small.png",
    "thumbnail/thumbnail.png",
]

# ---------------------------------------------------------------------------
# In-memory state
# ---------------------------------------------------------------------------
ws_clients: Set[WebSocket] = set()
mqtt_manager: MQTTManager | None = None
status_cache: dict[str, dict] = {}
thumbnail_cache: dict[str, bytes] = {}
timelapse_thumb_cache: dict[str, bytes] = {}

# Maps printer_id → active PrintJob.id while a print is running.
_print_sessions: dict[str, str] = {}


# ---------------------------------------------------------------------------
# Implicit FTPS (port 990) with SSL session reuse
# ---------------------------------------------------------------------------

class _ImplicitFTP_TLS(ftplib.FTP_TLS):
    """Implicit FTPS with SSL session reuse — required by Bambu printers.

    Two problems solved:
    1. Implicit FTPS: SSL wraps the control socket immediately on connect
       (no STARTTLS handshake, unlike explicit FTPS on port 21).
    2. SSL session reuse: Bambu returns 522 on data connections unless the
       data channel reuses the control channel's TLS session. We override
       ntransfercmd to pass session=self.sock.session when wrapping.
    """

    def __init__(self):
        super().__init__()
        self._sock = None

    @property
    def sock(self):
        return self._sock

    @sock.setter
    def sock(self, value):
        # Wrap plain sockets in TLS immediately (implicit mode).
        if value is not None and not isinstance(value, ssl.SSLSocket):
            value = self.context.wrap_socket(value)
        self._sock = value

    def ntransfercmd(self, cmd, rest=None):
        """Open data connection reusing the control channel's SSL session."""
        conn, size = ftplib.FTP.ntransfercmd(self, cmd, rest)
        if self._prot_p:
            conn = self.context.wrap_socket(
                conn,
                server_hostname=self.host,
                session=self.sock.session,  # key: reuse existing session
            )
        return conn, size


def _make_ftps_context() -> ssl.SSLContext:
    """Create a permissive SSL context suitable for Bambu's self-signed cert."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _ftps_connect(ip: str, access_code: str, timeout: int = 10) -> _ImplicitFTP_TLS:
    """Open an authenticated implicit-FTPS connection to a printer."""
    ftp = _ImplicitFTP_TLS()
    ftp.context = _make_ftps_context()
    ftp.connect(host=ip, port=990, timeout=timeout)
    ftp.login("bblp", access_code)
    ftp.prot_p()
    return ftp


def _ftps_download(ip: str, access_code: str, remote_path: str, timeout: int = 10) -> bytes | None:
    """Download a single file from the printer SD card via implicit FTPS.

    Returns the raw bytes on success, None if the file is missing or any
    network/auth error occurs.
    """
    try:
        ftp = _ftps_connect(ip, access_code, timeout)
        buf = io.BytesIO()
        ftp.retrbinary(f"RETR /{remote_path.lstrip('/')}", buf.write)
        ftp.quit()
        return buf.getvalue()
    except Exception as exc:
        logger.debug(f"FTPS download {ip}/{remote_path}: {exc}")
        return None


def _ftps_list_dir(ip: str, access_code: str, path: str = "/") -> list[str] | None:
    """List a directory on the printer SD card. Returns None on failure."""
    try:
        ftp = _ftps_connect(ip, access_code, timeout=5)
        entries = ftp.nlst(path)
        ftp.quit()
        return entries
    except Exception as exc:
        logger.debug(f"FTPS list {path} on {ip}: {exc}")
        return None


def _ftps_download_partial(
    ip: str, access_code: str, remote_path: str, max_bytes: int = 8 * 1024 * 1024
) -> bytes | None:
    """Download the first *max_bytes* of a file via implicit FTPS.

    Bambu timelapse MP4s are encoded with the moov atom at the front
    (fast-start / web-optimised), so the first ~4–8 MB contains everything
    ffmpeg needs to decode a poster frame without fetching the full file.
    """
    try:
        ftp = _ftps_connect(ip, access_code, timeout=20)
        buf = io.BytesIO()

        def _writer(chunk: bytes) -> None:
            remaining = max_bytes - buf.tell()
            if remaining <= 0:
                raise ftplib.error_reply("partial done")  # abort the transfer
            buf.write(chunk[:remaining])

        try:
            ftp.retrbinary(f"RETR /{remote_path.lstrip('/')}", _writer)
        except ftplib.error_reply:
            pass  # expected abort after max_bytes
        try:
            ftp.quit()
        except Exception:
            pass
        data = buf.getvalue()
        return data if data else None
    except Exception as exc:
        logger.debug(f"FTPS partial download {ip}/{remote_path}: {exc}")
        return None


def _extract_video_frame(video_bytes: bytes) -> bytes | None:
    """Use ffmpeg to extract the first decodable frame as a JPEG.

    Writes *video_bytes* to a temp file so ffmpeg can seek even when only
    the initial chunk of the file is available (requires fast-start MP4).
    Returns raw JPEG bytes or None if extraction fails.
    """
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            tmp.write(video_bytes)
            tmp_path = tmp.name

        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", tmp_path,
                "-ss", "0",
                "-frames:v", "1",
                "-vf", "scale=480:-1",   # thumbnail width 480px, preserve AR
                "-f", "image2",
                "-vcodec", "mjpeg",
                "pipe:1",
            ],
            capture_output=True,
            timeout=15,
        )
        os.unlink(tmp_path)

        if result.returncode == 0 and result.stdout:
            return result.stdout
        logger.debug(f"[timelapse thumb] ffmpeg exit {result.returncode}: {result.stderr[-200:]!r}")
        return None
    except Exception as exc:
        logger.debug(f"[timelapse thumb] ffmpeg error: {exc}")
        return None


# ---------------------------------------------------------------------------
# Thumbnail helpers
# ---------------------------------------------------------------------------

def _extract_thumbnail_from_3mf(data: bytes) -> bytes | None:
    """Extract the first matching plate thumbnail from a .gcode.3mf ZIP.

    Bambu/Orca slicers embed PNG renders inside the ZIP. We try paths in
    _3MF_THUMBNAIL_PATHS order and return the first hit.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = zf.namelist()
            logger.info(f"[3mf] zip entries ({len(names)}): {names[:20]}")
            for path in _3MF_THUMBNAIL_PATHS:
                if path in names:
                    return zf.read(path)
            logger.info(f"[3mf] no thumbnail path matched; candidates: {_3MF_THUMBNAIL_PATHS}")
    except Exception as exc:
        logger.info(f"[3mf] extraction failed ({len(data)} bytes, magic={data[:4]!r}): {exc}")
    return None


def _ftps_list_3mf(ip: str, access_code: str) -> list[str]:
    """Return .3mf paths from the printer SD card, newest-first when MDTM works.

    Model differences:
      P2S / H2D: .gcode.3mf files at FTP root, returned as /name.gcode.3mf
      A1  / P1S: .3mf files inside /cache/, returned as bare names by nlst

    The /cache/ listing is capped at 20 to avoid iterating 400+ files on
    busy P1S printers.
    """
    try:
        ftp = _ftps_connect(ip, access_code, timeout=10)
        candidates: list[str] = []

        # P2S / H2D: .gcode.3mf at root
        root_entries = ftp.nlst("/")
        candidates.extend(e for e in root_entries if e.lower().endswith(".gcode.3mf"))

        # A1 / P1S: .3mf files under /cache/
        if not candidates:
            try:
                for entry in ftp.nlst("/cache"):
                    name = entry.lstrip("/")
                    if name.lower().endswith(".3mf") and not name.lower().endswith(".bbl"):
                        candidates.append(f"/cache/{name}")
                        if len(candidates) >= 20:
                            break
            except Exception as cache_exc:
                logger.info(f"[thumbnail] /cache listing failed on {ip}: {cache_exc}")

        logger.info(f"[thumbnail] {ip} SD candidates ({len(candidates)}): {candidates[:8]}")

        if not candidates:
            ftp.quit()
            return []

        # Sort newest-first via MDTM timestamps when firmware supports it.
        timed: list[tuple[str, str]] = []
        mdtm_supported = False
        for path in candidates:
            try:
                resp = ftp.sendcmd(f"MDTM {path}")
                timed.append((resp.split()[-1], path))
                mdtm_supported = True
            except Exception:
                timed.append(("", path))

        ftp.quit()

        if mdtm_supported:
            timed.sort(reverse=True)
            logger.info(f"[thumbnail] {ip} newest by MDTM: {[p for _, p in timed[:3]]}")

        return [p for _, p in timed]

    except Exception as exc:
        logger.info(f"[thumbnail] _ftps_list_3mf {ip} failed: {exc}")
        return []


def _fetch_thumbnail_sync(
    printer_id: str,
    ip: str,
    access_code: str,
    cover_file: str,
    gcode_file: str,
    subtask_name: str = "",
) -> bytes | None:
    """Fetch a print thumbnail from the printer SD card (runs in thread pool).

    Tries four strategies in sequence, stopping at the first hit:

    1a. subtask_name / gcode_file ends in .3mf → direct download from
        /cache/<name> then /<name>  (A1 / P1S firmware pattern)

    1b. subtask_name looks like a job title (not a filename) → try
        /<subtask_name>.gcode.3mf  (P2S / H2D firmware pattern)

    2.  List all .3mf files on SD card sorted newest-first, try each
        until we find one with an embedded thumbnail.

    3.  gcode_file path itself is a .3mf (some firmware variants).

    4.  Explicit cover_file path from MQTT (pre-rendered JPEG/PNG).

    Cache key is printer_id (one slot per printer).  The cache is cleared
    by on_printer_status() whenever current_file changes, so every new job
    always triggers a fresh fetch regardless of filename reuse.
    """
    if printer_id in thumbnail_cache:
        return thumbnail_cache[printer_id]

    def _cache(data: bytes) -> bytes:
        thumbnail_cache[printer_id] = data
        return data

    logger.info(
        f"[thumbnail] {ip} subtask={subtask_name!r} "
        f"cover={cover_file!r} gcode={gcode_file!r}"
    )

    # Strategy 1a: direct .3mf download (A1 / P1S)
    for name in filter(None, [subtask_name, gcode_file]):
        if name.lower().endswith(".3mf"):
            clean = name.lstrip("/")
            for path in [f"/cache/{clean}", f"/{clean}"]:
                raw = _ftps_download(ip, access_code, path, timeout=20)
                if raw:
                    img = _extract_thumbnail_from_3mf(raw)
                    if img:
                        logger.info(f"[thumbnail] hit via strategy 1a: {path}")
                        return _cache(img)

    # Strategy 1b: job-title .gcode.3mf at SD root (P2S / H2D)
    if subtask_name and not subtask_name.lower().endswith(".3mf"):
        for ext in (".gcode.3mf", ".3mf"):
            raw = _ftps_download(ip, access_code, f"/{subtask_name}{ext}", timeout=20)
            if raw:
                img = _extract_thumbnail_from_3mf(raw)
                if img:
                    logger.info(f"[thumbnail] hit via strategy 1b: /{subtask_name}{ext}")
                    return _cache(img)

    # Strategy 2: scan SD card newest-first
    for candidate in _ftps_list_3mf(ip, access_code):
        raw = _ftps_download(ip, access_code, candidate, timeout=20)
        if raw:
            img = _extract_thumbnail_from_3mf(raw)
            if img:
                logger.info(f"[thumbnail] hit via strategy 2: {candidate}")
                return _cache(img)
            logger.info(f"[thumbnail] no image in {candidate}")

    # Strategy 3: gcode_file is itself a .3mf
    if gcode_file and ".3mf" in gcode_file.lower():
        raw = _ftps_download(ip, access_code, gcode_file, timeout=20)
        if raw:
            img = _extract_thumbnail_from_3mf(raw)
            if img:
                logger.info(f"[thumbnail] hit via strategy 3: {gcode_file}")
                return _cache(img)

    # Strategy 4: explicit cover_file from MQTT
    if cover_file:
        img = _ftps_download(ip, access_code, cover_file, timeout=5)
        if img:
            logger.info(f"[thumbnail] hit via strategy 4 (cover_file): {cover_file}")
            return _cache(img)

    logger.debug(
        f"[thumbnail] no thumbnail for {ip}: "
        f"subtask={subtask_name!r} gcode={gcode_file!r} cover={cover_file!r}"
    )
    return None


# ---------------------------------------------------------------------------
# go2rtc integration
# ---------------------------------------------------------------------------

async def _go2rtc_put(printer: Printer) -> None:
    """Register or update a printer's RTSPS stream in go2rtc."""
    name = f"bambu_{printer.id}"
    url = f"rtsps://bblp:{printer.access_code}@{printer.ip}:322/streaming/live/1"
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            await client.put(f"{GO2RTC_URL}/api/streams?name={name}", content=url)
        logger.info(f"go2rtc: registered {printer.name!r} as {name}")
    except Exception as exc:
        logger.warning(f"go2rtc: could not register {printer.name!r}: {exc}")


async def _go2rtc_delete(printer_id: str) -> None:
    """Remove a printer's stream from go2rtc."""
    name = f"bambu_{printer_id}"
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            await client.delete(f"{GO2RTC_URL}/api/streams?name={name}")
        logger.info(f"go2rtc: removed {name}")
    except Exception as exc:
        logger.warning(f"go2rtc: could not remove {name}: {exc}")


# ---------------------------------------------------------------------------
# WebSocket broadcast
# ---------------------------------------------------------------------------

async def broadcast(msg: dict) -> None:
    """Send a JSON message to all connected WebSocket clients.

    Silently drops dead connections without raising.
    """
    dead: Set[WebSocket] = set()
    for ws in ws_clients:
        try:
            await ws.send_json(msg)
        except Exception:
            dead.add(ws)
    ws_clients.difference_update(dead)


# ---------------------------------------------------------------------------
# MQTT status callback & print lifecycle tracking
# ---------------------------------------------------------------------------

def on_printer_status(status: PrinterStatus) -> None:
    """Handle a status update from the MQTT manager.

    Detects print start / end transitions, writes history records, and
    broadcasts both lifecycle events and raw status updates to WS clients.
    Called from a background thread — uses run_coroutine_threadsafe.
    """
    prev = status_cache.get(status.printer_id, {})
    prev_state = prev.get("gcode_state", "OFFLINE")
    curr_state = status.gcode_state

    loop = app.state.loop

    # Clear thumbnail cache whenever the active file changes so the next
    # request always fetches a fresh image for the new job.
    if prev.get("current_file") != status.current_file:
        thumbnail_cache.pop(status.printer_id, None)

    # Print started
    if prev_state != "RUNNING" and curr_state == "RUNNING":
        printer = db.get_printer(status.printer_id)
        name = printer.name if printer else status.printer_id
        job = db.start_print_job(status.printer_id, name, status.current_file)
        _print_sessions[status.printer_id] = job.id
        asyncio.run_coroutine_threadsafe(
            broadcast({"type": "print_event", "data": {
                "event": "started",
                "printer_id": status.printer_id,
                "printer_name": name,
                "file_name": status.current_file,
            }}),
            loop,
        )

    # Print ended (any terminal state after RUNNING)
    elif prev_state == "RUNNING" and curr_state in ("FINISH", "FAILED", "IDLE"):
        job_id = _print_sessions.pop(status.printer_id, None)
        final = (
            "completed" if curr_state == "FINISH"
            else "failed" if curr_state == "FAILED"
            else "cancelled"
        )
        if job_id:
            db.finish_print_job(job_id, final)
        printer = db.get_printer(status.printer_id)
        name = printer.name if printer else status.printer_id
        asyncio.run_coroutine_threadsafe(
            broadcast({"type": "print_event", "data": {
                "event": final,
                "printer_id": status.printer_id,
                "printer_name": name,
                "file_name": prev.get("current_file", ""),
            }}),
            loop,
        )

    status_cache[status.printer_id] = status.model_dump()
    asyncio.run_coroutine_threadsafe(
        broadcast({"type": "status_update", "data": status.model_dump()}),
        loop,
    )


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.loop = asyncio.get_running_loop()
    db.init_db()
    db.abandon_running_jobs()  # clean up stale jobs from a prior server session

    global mqtt_manager
    mqtt_manager = MQTTManager(on_printer_status)

    for printer in db.get_all_printers():
        mqtt_manager.add_printer(printer)
        await _go2rtc_put(printer)

    yield

    if mqtt_manager:
        mqtt_manager.stop_all()


app = FastAPI(title="Bambu Farm Monitor", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Printer CRUD
# ---------------------------------------------------------------------------

@app.get("/api/printers")
def list_printers():
    return [p.model_dump() for p in db.get_all_printers()]


@app.post("/api/printers", status_code=201)
async def add_printer(data: PrinterCreate):
    printer = Printer(**data.model_dump())
    saved = db.create_printer(printer)
    mqtt_manager.add_printer(saved)
    await _go2rtc_put(saved)
    await broadcast({"type": "printers_update", "data": {"action": "add", "printer": saved.model_dump()}})
    return saved.model_dump()


@app.get("/api/printers/{printer_id}")
def get_printer(printer_id: str):
    p = db.get_printer(printer_id)
    if not p:
        raise HTTPException(status_code=404, detail="Printer not found")
    return p.model_dump()


@app.patch("/api/printers/{printer_id}")
async def update_printer(printer_id: str, data: PrinterUpdate):
    updates = {k: v for k, v in data.model_dump().items() if v is not None}
    p = db.update_printer(printer_id, updates)
    if not p:
        raise HTTPException(status_code=404, detail="Printer not found")
    mqtt_manager.update_printer(p)
    await _go2rtc_put(p)
    await broadcast({"type": "printers_update", "data": {"action": "update", "printer": p.model_dump()}})
    return p.model_dump()


@app.delete("/api/printers/{printer_id}", status_code=204)
async def delete_printer(printer_id: str):
    success = db.delete_printer(printer_id)
    if not success:
        raise HTTPException(status_code=404, detail="Printer not found")
    mqtt_manager.remove_printer(printer_id)
    await _go2rtc_delete(printer_id)
    status_cache.pop(printer_id, None)
    await broadcast({"type": "printers_update", "data": {"action": "delete", "printer_id": printer_id}})


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

@app.get("/api/settings")
def get_settings_endpoint():
    return db.get_settings()


@app.patch("/api/settings")
async def update_settings(data: SettingsUpdate):
    if data.farm_name is not None:
        db.set_setting("farm_name", data.farm_name)
    settings = db.get_settings()
    await broadcast({"type": "settings_update", "data": settings})
    return settings


# ---------------------------------------------------------------------------
# Thumbnails
# ---------------------------------------------------------------------------

@app.get("/api/printers/{printer_id}/thumbnail")
async def get_thumbnail(printer_id: str):
    p = db.get_printer(printer_id)
    if not p:
        raise HTTPException(status_code=404, detail="Printer not found")

    st = status_cache.get(printer_id, {})
    cover   = st.get("cover_file", "")
    gcode   = st.get("gcode_file", "")
    subtask = st.get("current_file", "")

    if not (cover or gcode or subtask):
        raise HTTPException(status_code=404, detail="No print file available")

    data = await asyncio.get_running_loop().run_in_executor(
        None, _fetch_thumbnail_sync, printer_id, p.ip, p.access_code, cover, gcode, subtask
    )
    if not data:
        raise HTTPException(status_code=404, detail="Thumbnail unavailable")

    content_type = "image/png" if data[:4] == b"\x89PNG" else "image/jpeg"
    return Response(content=data, media_type=content_type)


@app.get("/api/printers/{printer_id}/thumbnail/debug")
async def debug_thumbnail(printer_id: str):
    """Diagnostic endpoint: returns MQTT state and FTPS directory listings.

    Useful for diagnosing thumbnail fetch failures without touching production
    paths. Safe to call while a print is in progress.
    """
    p = db.get_printer(printer_id)
    if not p:
        raise HTTPException(status_code=404, detail="Printer not found")

    st = status_cache.get(printer_id, {})
    return {
        "printer_ip": p.ip,
        "current_file_subtask": st.get("current_file") or None,
        "cover_file_from_mqtt": st.get("cover_file") or None,
        "gcode_file_from_mqtt": st.get("gcode_file") or None,
        "gcode_state": st.get("gcode_state") or None,
        "sd_3mf_files": await asyncio.get_running_loop().run_in_executor(
            None, _ftps_list_3mf, p.ip, p.access_code
        ),
    }


# ---------------------------------------------------------------------------
# Print controls
# ---------------------------------------------------------------------------

@app.post("/api/printers/{printer_id}/control")
async def control_print(printer_id: str, data: PrintControl):
    p = db.get_printer(printer_id)
    if not p:
        raise HTTPException(status_code=404, detail="Printer not found")

    action = data.action.lower()
    if action not in ("pause", "resume", "stop"):
        raise HTTPException(status_code=400, detail="action must be pause | resume | stop")

    # Bambu firmware requires "param" to be present (empty string) or the
    # command is rejected and the printer logs HMS 0007 "MQTT command failed".
    payload = {"print": {"sequence_id": "2005", "command": action, "param": ""}}
    if not mqtt_manager.publish(printer_id, payload):
        raise HTTPException(status_code=503, detail="MQTT not connected")
    return {"ok": True, "action": action}


@app.post("/api/printers/{printer_id}/light")
async def control_light(printer_id: str, data: LightControl):
    p = db.get_printer(printer_id)
    if not p:
        raise HTTPException(status_code=404, detail="Printer not found")

    mode = data.mode.lower()
    if mode not in ("on", "off"):
        raise HTTPException(status_code=400, detail="mode must be on | off")

    # Bambu MQTT requires all timing fields or the command is silently ignored.
    payload = {
        "system": {
            "sequence_id": "2005",
            "command": "ledctrl",
            "led_node": "chamber_light",
            "led_mode": mode,
            "led_on_time": 500,
            "led_off_time": 500,
            "loop_times": 1,
            "interval_time": 1000,
        }
    }
    if not mqtt_manager.publish(printer_id, payload):
        raise HTTPException(status_code=503, detail="MQTT not connected")
    return {"ok": True, "mode": mode}


# ---------------------------------------------------------------------------
# Dismissed HMS alerts
# ---------------------------------------------------------------------------

@app.get("/api/printers/{printer_id}/dismissed-alerts")
def list_dismissed_alerts(printer_id: str):
    """Return the list of HMS codes the user has dismissed for this printer."""
    return {"dismissed": db.get_dismissed_alerts(printer_id)}


@app.post("/api/printers/{printer_id}/dismissed-alerts", status_code=201)
async def dismiss_alert(printer_id: str, data: AlertDismiss):
    """Dismiss an HMS alert so it is hidden in the UI. Idempotent."""
    p = db.get_printer(printer_id)
    if not p:
        raise HTTPException(status_code=404, detail="Printer not found")
    db.dismiss_alert(printer_id, data.hms_code)
    dismissed = db.get_dismissed_alerts(printer_id)
    await broadcast({
        "type": "dismissed_alerts_update",
        "data": {"printer_id": printer_id, "dismissed": dismissed},
    })
    return {"dismissed": dismissed}


@app.delete("/api/printers/{printer_id}/dismissed-alerts/{hms_code}", status_code=200)
async def undismiss_alert(printer_id: str, hms_code: str):
    """Restore a dismissed HMS alert so it appears in the UI again."""
    p = db.get_printer(printer_id)
    if not p:
        raise HTTPException(status_code=404, detail="Printer not found")
    db.undismiss_alert(printer_id, hms_code)
    dismissed = db.get_dismissed_alerts(printer_id)
    await broadcast({
        "type": "dismissed_alerts_update",
        "data": {"printer_id": printer_id, "dismissed": dismissed},
    })
    return {"dismissed": dismissed}


# ---------------------------------------------------------------------------
# Timelapses
# ---------------------------------------------------------------------------

@app.get("/api/printers/{printer_id}/timelapses")
async def list_timelapses(printer_id: str):
    p = db.get_printer(printer_id)
    if not p:
        raise HTTPException(status_code=404, detail="Printer not found")

    def _list() -> list[str]:
        entries = _ftps_list_dir(p.ip, p.access_code, "/timelapse") or []
        files = [
            e.split("/")[-1] if "/" in e else e
            for e in entries
            if e.lower().endswith((".mp4", ".avi", ".mov"))
        ]
        # Return only the 3 most recent so the UI doesn't get cluttered.
        return sorted(files, reverse=True)[:3]

    files = await asyncio.get_running_loop().run_in_executor(None, _list)
    return {"files": files}


@app.get("/api/printers/{printer_id}/timelapses/{filename}/thumb")
async def timelapse_thumb(printer_id: str, filename: str):
    """Return a JPEG poster frame extracted from the first 8 MB of the video.

    Results are cached in memory for the lifetime of the server process.
    Returns 404 when ffmpeg cannot decode a frame (non-fast-start file or
    very short partial data).
    """
    if "/" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    cache_key = f"{printer_id}:{filename}"
    if cache_key in timelapse_thumb_cache:
        return Response(content=timelapse_thumb_cache[cache_key], media_type="image/jpeg")

    p = db.get_printer(printer_id)
    if not p:
        raise HTTPException(status_code=404, detail="Printer not found")

    def _make_thumb() -> bytes | None:
        partial = _ftps_download_partial(p.ip, p.access_code, f"/timelapse/{filename}")
        if not partial:
            return None
        return _extract_video_frame(partial)

    jpeg = await asyncio.get_running_loop().run_in_executor(None, _make_thumb)
    if not jpeg:
        raise HTTPException(status_code=404, detail="Thumbnail unavailable")

    timelapse_thumb_cache[cache_key] = jpeg
    return Response(content=jpeg, media_type="image/jpeg")


@app.get("/api/printers/{printer_id}/timelapses/{filename}")
async def download_timelapse(printer_id: str, filename: str):
    p = db.get_printer(printer_id)
    if not p:
        raise HTTPException(status_code=404, detail="Printer not found")
    if "/" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    data = await asyncio.get_running_loop().run_in_executor(
        None, _ftps_download, p.ip, p.access_code, f"/timelapse/{filename}", 120
    )
    if not data:
        raise HTTPException(status_code=404, detail="File not found")

    return Response(
        content=data,
        media_type="video/mp4",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# History & status
# ---------------------------------------------------------------------------

@app.get("/api/history")
def get_history():
    return [j.model_dump() for j in db.get_print_history()]


@app.get("/api/status")
def get_all_statuses():
    return status_cache


@app.get("/api/status/{printer_id}")
def get_status(printer_id: str):
    if printer_id in status_cache:
        return status_cache[printer_id]
    s = mqtt_manager.get_status(printer_id)
    if s:
        return s.model_dump()
    raise HTTPException(status_code=404, detail="Status not found")


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Persistent WebSocket for real-time status and event updates.

    On connect, sends an 'init' payload with all printer configs, current
    statuses, and settings. Subsequent messages are broadcast by
    on_printer_status and the CRUD endpoints.
    """
    await websocket.accept()
    ws_clients.add(websocket)
    try:
        await websocket.send_json({
            "type": "init",
            "data": {
                "printers":          [p.model_dump() for p in db.get_all_printers()],
                "statuses":          status_cache,
                "settings":          db.get_settings(),
                "dismissed_alerts":  db.get_all_dismissed_alerts(),
            },
        })
        while True:
            await websocket.receive_text()   # keep connection alive
    except WebSocketDisconnect:
        pass
    finally:
        ws_clients.discard(websocket)
