"""
Unit tests for PrinterConnection._parse_report — the most critical parsing
logic in the backend.

No real MQTT connections are made; we call _parse_report directly with
hand-crafted payloads that mirror real Bambu MQTT messages.
"""

import pytest
from unittest.mock import MagicMock
from models import Printer, PrinterStatus

# Import the class we're unit-testing
from mqtt_manager import PrinterConnection


def make_connection() -> PrinterConnection:
    """Return a PrinterConnection with a dummy printer and a no-op callback."""
    printer = Printer(
        id="test-printer-1",
        name="Test",
        model="P1S",
        ip="192.168.1.1",
        serial="SN0001",
        access_code="12345678",
    )
    return PrinterConnection(printer, on_status=lambda _: None)


def parse(conn: PrinterConnection, print_data: dict) -> PrinterStatus:
    """Wrap a print_data dict in the expected MQTT envelope and parse it."""
    conn._parse_report({"print": print_data})
    return conn.status


# ── Core state ────────────────────────────────────────────────────────────────

class TestCoreState:

    def test_gcode_state_parsed(self):
        conn = make_connection()
        s = parse(conn, {"gcode_state": "RUNNING"})
        assert s.gcode_state == "RUNNING"

    def test_progress_parsed(self):
        conn = make_connection()
        s = parse(conn, {"mc_percent": 42})
        assert s.progress == 42

    def test_remaining_time_parsed(self):
        conn = make_connection()
        s = parse(conn, {"mc_remaining_time": 90})
        assert s.remaining_time == 90

    def test_layer_numbers_parsed(self):
        conn = make_connection()
        s = parse(conn, {"layer_num": 15, "total_layer_num": 200})
        assert s.layer_num   == 15
        assert s.total_layers == 200

    def test_connected_set_true_on_any_message(self):
        conn = make_connection()
        assert conn.status.connected is False
        parse(conn, {"gcode_state": "IDLE"})
        assert conn.status.connected is True

    def test_empty_print_key_is_noop(self):
        conn = make_connection()
        conn.status.gcode_state = "RUNNING"
        conn._parse_report({})          # no 'print' key at all
        assert conn.status.gcode_state == "RUNNING"   # unchanged

    def test_empty_print_dict_is_noop(self):
        conn = make_connection()
        conn.status.gcode_state = "RUNNING"
        conn._parse_report({"print": {}})
        assert conn.status.gcode_state == "RUNNING"

    def test_last_update_set(self):
        conn = make_connection()
        parse(conn, {"gcode_state": "IDLE"})
        assert conn.status.last_update is not None


# ── Temperatures ──────────────────────────────────────────────────────────────

class TestTemperatures:

    def test_nozzle_temp_parsed(self):
        s = parse(make_connection(), {"nozzle_temper": 210.5})
        assert s.nozzle_temp == pytest.approx(210.5)

    def test_nozzle_target_parsed(self):
        s = parse(make_connection(), {"nozzle_target_temper": 220.0})
        assert s.nozzle_target == pytest.approx(220.0)

    def test_bed_temp_parsed(self):
        s = parse(make_connection(), {"bed_temper": 60.0, "bed_target_temper": 65.0})
        assert s.bed_temp   == pytest.approx(60.0)
        assert s.bed_target == pytest.approx(65.0)

    def test_chamber_temp_parsed(self):
        s = parse(make_connection(), {"chamber_temper": 38.2})
        assert s.chamber_temp == pytest.approx(38.2)

    def test_missing_temperature_keeps_previous(self):
        conn = make_connection()
        parse(conn, {"nozzle_temper": 200.0})
        parse(conn, {"gcode_state": "RUNNING"})   # no temp key
        assert conn.status.nozzle_temp == pytest.approx(200.0)


# ── Fan speeds ────────────────────────────────────────────────────────────────

class TestFanSpeeds:

    def test_fan_off_zero_is_preserved(self):
        """
        Regression: fan speed of 0 (fan genuinely off) must not be treated as
        falsy and replaced by the previous non-zero value.
        """
        conn = make_connection()
        parse(conn, {"cooling_fan_speed": 15})   # set to 100%
        parse(conn, {"cooling_fan_speed": 0})    # turn off
        assert conn.status.fan_speed == 0

    def test_fan_full_speed(self):
        s = parse(make_connection(), {"cooling_fan_speed": 15})
        assert s.fan_speed == 100

    def test_fan_half_speed(self):
        s = parse(make_connection(), {"cooling_fan_speed": 7})
        # round(7/15*100) = 47
        assert s.fan_speed == round(7 / 15 * 100)

    def test_heatbreak_fan_parsed(self):
        s = parse(make_connection(), {"heatbreak_fan_speed": 15})
        assert s.heatbreak_fan_speed == 100

    def test_aux_fan_parsed(self):
        s = parse(make_connection(), {"big_fan1_speed": 15})
        assert s.aux_fan_speed == 100

    def test_chamber_fan_parsed(self):
        s = parse(make_connection(), {"big_fan2_speed": 8})
        assert s.chamber_fan_speed == round(8 / 15 * 100)

    def test_missing_fan_key_leaves_value_unchanged(self):
        conn = make_connection()
        parse(conn, {"cooling_fan_speed": 15})
        # Send a message that has no fan key at all
        parse(conn, {"gcode_state": "RUNNING"})
        assert conn.status.fan_speed == 100   # unchanged


# ── Chamber light ─────────────────────────────────────────────────────────────

class TestLight:

    def test_chamber_light_on(self):
        s = parse(make_connection(), {
            "lights_report": [{"node": "chamber_light", "mode": "on"}]
        })
        assert s.chamber_light == "on"

    def test_chamber_light_off(self):
        s = parse(make_connection(), {
            "lights_report": [{"node": "chamber_light", "mode": "off"}]
        })
        assert s.chamber_light == "off"

    def test_non_chamber_light_ignored(self):
        conn = make_connection()
        conn.status.chamber_light = "on"
        parse(conn, {"lights_report": [{"node": "work_light", "mode": "off"}]})
        assert conn.status.chamber_light == "on"   # unchanged


# ── HMS alerts ────────────────────────────────────────────────────────────────

class TestHMSAlerts:

    def test_hms_code_formatted_correctly(self):
        """attr and code integers → HMS_AAAA-BBBB-CCCC-DDDD hex string."""
        # attr = 0x03000001, code = 0x00030001 → HMS_0300-0001-0003-0001
        s = parse(make_connection(), {"hms": [
            {"attr": 0x03000001, "code": 0x00030001}
        ]})
        assert len(s.hms_alerts) == 1
        assert s.hms_alerts[0].hms_code == "HMS_0300-0001-0003-0001"

    def test_hms_wiki_url_uses_underscores(self):
        s = parse(make_connection(), {"hms": [
            {"attr": 0x03000001, "code": 0x00030001}
        ]})
        assert "_" in s.hms_alerts[0].wiki_url
        assert "-" not in s.hms_alerts[0].wiki_url.split("/hmscode/")[-1]

    def test_multiple_hms_alerts(self):
        s = parse(make_connection(), {"hms": [
            {"attr": 0x03000001, "code": 0x00030001},
            {"attr": 0x05000001, "code": 0x00050002},
        ]})
        assert len(s.hms_alerts) == 2

    def test_empty_hms_list_clears_alerts(self):
        conn = make_connection()
        parse(conn, {"hms": [{"attr": 0x03000001, "code": 0x00030001}]})
        parse(conn, {"hms": []})
        assert conn.status.hms_alerts == []


# ── AMS ───────────────────────────────────────────────────────────────────────

class TestAMSParsing:

    def _make_ams_payload(self, units):
        """Build an MQTT print payload containing the given AMS unit dicts."""
        return {
            "ams": {
                "ams": units,
                "tray_now": 0,
            }
        }

    def test_standard_ams_slot_count_is_4(self):
        payload = self._make_ams_payload([{
            "humidity": 3,
            "temp": 22.5,
            "tray": [
                {"id": 0, "tray_type": "PLA", "tray_color": "FF0000FF", "remain": 80, "tray_sub_brands": "Bambu"},
                {"id": 1, "tray_type": "", "tray_color": "FFFFFFFF", "remain": 0, "tray_sub_brands": ""},
                {"id": 2, "tray_type": "", "tray_color": "FFFFFFFF", "remain": 0, "tray_sub_brands": ""},
                {"id": 3, "tray_type": "", "tray_color": "FFFFFFFF", "remain": 0, "tray_sub_brands": ""},
            ],
        }])
        s = parse(make_connection(), payload)
        assert s.ams_units[0].slot_count == 4

    def test_h2d_ams_slot_count_is_1(self):
        """H2D reports only 1 tray entry per AMS unit — slot_count must reflect that."""
        payload = self._make_ams_payload([{
            "humidity": 4,
            "temp": 20.0,
            "tray": [
                {"id": 0, "tray_type": "PETG", "tray_color": "0000FFFF", "remain": 50, "tray_sub_brands": "Generic"},
            ],
        }])
        s = parse(make_connection(), payload)
        assert s.ams_units[0].slot_count == 1

    def test_ams_tray_color_is_css_hex(self):
        payload = self._make_ams_payload([{
            "humidity": 3, "temp": 22.0,
            "tray": [{"id": 0, "tray_type": "PLA", "tray_color": "FF0000FF", "remain": 80, "tray_sub_brands": ""}],
        }])
        s = parse(make_connection(), payload)
        assert s.ams_trays[0].color == "#FF0000"

    def test_ams_tray_color_short_string_falls_back(self):
        payload = self._make_ams_payload([{
            "humidity": 3, "temp": 22.0,
            "tray": [{"id": 0, "tray_type": "PLA", "tray_color": "FFF", "remain": 80, "tray_sub_brands": ""}],
        }])
        s = parse(make_connection(), payload)
        assert s.ams_trays[0].color == "#FFFFFF"

    def test_ams_empty_trays_excluded(self):
        """Trays with no tray_type are filtered out of ams_trays."""
        payload = self._make_ams_payload([{
            "humidity": 3, "temp": 22.0,
            "tray": [
                {"id": 0, "tray_type": "PLA", "tray_color": "FF0000FF", "remain": 80, "tray_sub_brands": ""},
                {"id": 1, "tray_type": "",    "tray_color": "FFFFFFFF", "remain": 0,  "tray_sub_brands": ""},
            ],
        }])
        s = parse(make_connection(), payload)
        assert len(s.ams_trays) == 1
        assert s.ams_trays[0].tray_type == "PLA"

    def test_ams_global_slot_id_stride_is_4(self):
        """
        Even on H2D (1 physical slot), global slot IDs are computed as
        unit_idx * 4 + tray.id.  Two units should give slot IDs 0 and 4.
        """
        payload = self._make_ams_payload([
            {"humidity": 3, "temp": 22.0,
             "tray": [{"id": 0, "tray_type": "PLA", "tray_color": "FF0000FF", "remain": 80, "tray_sub_brands": ""}]},
            {"humidity": 4, "temp": 20.0,
             "tray": [{"id": 0, "tray_type": "PETG", "tray_color": "0000FFFF", "remain": 50, "tray_sub_brands": ""}]},
        ])
        s = parse(make_connection(), payload)
        slots = [t.slot for t in s.ams_trays]
        assert 0 in slots
        assert 4 in slots

    def test_ams_humidity_and_temp_parsed(self):
        payload = self._make_ams_payload([{
            "humidity": 5, "temp": 18.7,
            "tray": [{"id": 0, "tray_type": "PLA", "tray_color": "FF0000FF", "remain": 90, "tray_sub_brands": ""}],
        }])
        s = parse(make_connection(), payload)
        assert s.ams_units[0].humidity == 5
        assert s.ams_units[0].temp     == pytest.approx(18.7)

    def test_ams_current_tray_parsed(self):
        payload = self._make_ams_payload([{
            "humidity": 3, "temp": 22.0,
            "tray": [{"id": 0, "tray_type": "PLA", "tray_color": "FF0000FF", "remain": 80, "tray_sub_brands": ""}],
        }])
        payload["ams"]["tray_now"] = 2
        s = parse(make_connection(), payload)
        assert s.ams_current_tray == 2


# ── Stage labels ──────────────────────────────────────────────────────────────

class TestStageLabel:

    def test_leveling_stage(self):
        s = parse(make_connection(), {"stg_cur": 1})
        assert s.stage == "Leveling"

    def test_unknown_stage_returns_empty(self):
        s = parse(make_connection(), {"stg_cur": 999})
        assert s.stage == ""

    def test_stage_255_returns_empty(self):
        s = parse(make_connection(), {"stg_cur": 255})
        assert s.stage == ""


# ── Virtual tray (external spool) ─────────────────────────────────────────────

class TestVirtualTray:

    def test_vt_tray_parsed(self):
        s = parse(make_connection(), {
            "vt_tray": {
                "tray_type": "TPU",
                "tray_color": "00FF00FF",
                "remain": 60,
                "tray_sub_brands": "Generic",
            }
        })
        assert s.vt_tray is not None
        assert s.vt_tray.tray_type == "TPU"
        assert s.vt_tray.color    == "#00FF00"
        assert s.vt_tray.remain   == 60

    def test_vt_tray_missing_type_is_ignored(self):
        s = parse(make_connection(), {"vt_tray": {"remain": 50}})
        assert s.vt_tray is None


# ── XCam AI settings ──────────────────────────────────────────────────────────

class TestXCam:

    def test_xcam_flags_parsed(self):
        s = parse(make_connection(), {
            "xcam": {
                "spaghetti_detect":    True,
                "print_halt":          False,
                "first_layer_inspect": True,
            }
        })
        assert s.xcam_spaghetti_enabled    is True
        assert s.xcam_halt_enabled         is False
        assert s.xcam_first_layer_enabled  is True
