"""
API endpoint tests — exercises every route in main.py via the TestClient.

All MQTT and go2rtc calls are stubbed by conftest.py.
Database is in-memory and reset between tests.
"""

import pytest
from unittest.mock import patch

PRINTER_PAYLOAD = {
    "name": "Test P1S",
    "model": "P1S",
    "ip": "192.168.1.100",
    "serial": "TESTSERIAL01",
    "access_code": "12345678",
    "lan_mode": True,
}


# ── Printer CRUD ─────────────────────────────────────────────────────────────

class TestPrinterCRUD:

    def test_list_printers_empty(self, client):
        r = client.get("/api/printers")
        assert r.status_code == 200
        assert r.json() == []

    def test_add_printer_returns_201(self, client):
        r = client.post("/api/printers", json=PRINTER_PAYLOAD)
        assert r.status_code == 201

    def test_add_printer_fields_persisted(self, client):
        r = client.post("/api/printers", json=PRINTER_PAYLOAD)
        body = r.json()
        assert body["name"]        == PRINTER_PAYLOAD["name"]
        assert body["model"]       == PRINTER_PAYLOAD["model"]
        assert body["ip"]          == PRINTER_PAYLOAD["ip"]
        assert body["serial"]      == PRINTER_PAYLOAD["serial"]
        assert body["access_code"] == PRINTER_PAYLOAD["access_code"]
        assert body["lan_mode"]    is True
        assert "id" in body

    def test_add_printer_appears_in_list(self, client):
        client.post("/api/printers", json=PRINTER_PAYLOAD)
        r = client.get("/api/printers")
        assert len(r.json()) == 1

    def test_add_multiple_printers(self, client):
        client.post("/api/printers", json=PRINTER_PAYLOAD)
        client.post("/api/printers", json={**PRINTER_PAYLOAD, "name": "Second", "serial": "SN2"})
        r = client.get("/api/printers")
        assert len(r.json()) == 2

    def test_get_printer_by_id(self, client):
        pid = client.post("/api/printers", json=PRINTER_PAYLOAD).json()["id"]
        r = client.get(f"/api/printers/{pid}")
        assert r.status_code == 200
        assert r.json()["id"] == pid

    def test_get_printer_unknown_id_returns_404(self, client):
        r = client.get("/api/printers/does-not-exist")
        assert r.status_code == 404

    def test_patch_printer_name(self, client):
        pid = client.post("/api/printers", json=PRINTER_PAYLOAD).json()["id"]
        r = client.patch(f"/api/printers/{pid}", json={"name": "Renamed"})
        assert r.status_code == 200
        assert r.json()["name"] == "Renamed"

    def test_patch_printer_unknown_id_returns_404(self, client):
        r = client.patch("/api/printers/bad-id", json={"name": "X"})
        assert r.status_code == 404

    def test_patch_preserves_unchanged_fields(self, client):
        pid = client.post("/api/printers", json=PRINTER_PAYLOAD).json()["id"]
        client.patch(f"/api/printers/{pid}", json={"name": "Renamed"})
        body = client.get(f"/api/printers/{pid}").json()
        assert body["model"]  == PRINTER_PAYLOAD["model"]
        assert body["serial"] == PRINTER_PAYLOAD["serial"]

    def test_delete_printer(self, client):
        pid = client.post("/api/printers", json=PRINTER_PAYLOAD).json()["id"]
        r = client.delete(f"/api/printers/{pid}")
        assert r.status_code == 204

    def test_delete_printer_removes_from_list(self, client):
        pid = client.post("/api/printers", json=PRINTER_PAYLOAD).json()["id"]
        client.delete(f"/api/printers/{pid}")
        assert client.get("/api/printers").json() == []

    def test_delete_printer_unknown_id_returns_404(self, client):
        r = client.delete("/api/printers/bad-id")
        assert r.status_code == 404

    def test_lan_mode_defaults_to_true(self, client):
        payload = {**PRINTER_PAYLOAD}
        del payload["lan_mode"]
        r = client.post("/api/printers", json=payload)
        assert r.json()["lan_mode"] is True


# ── Status endpoint ───────────────────────────────────────────────────────────

class TestStatus:

    def test_status_unknown_printer_returns_404(self, client):
        r = client.get("/api/status/does-not-exist")
        assert r.status_code == 404

    def test_status_known_printer_not_yet_connected_returns_404(self, client):
        """Printer added but MQTT hasn't pushed any status yet — still 404."""
        pid = client.post("/api/printers", json=PRINTER_PAYLOAD).json()["id"]
        r = client.get(f"/api/status/{pid}")
        # No MQTT data has been injected, so the status_cache has no entry
        assert r.status_code == 404


# ── Settings ──────────────────────────────────────────────────────────────────

class TestSettings:

    def test_get_settings_returns_defaults(self, client):
        r = client.get("/api/settings")
        assert r.status_code == 200
        assert "farm_name" in r.json()
        assert r.json()["farm_name"] == "Print Farm"

    def test_patch_farm_name(self, client):
        r = client.patch("/api/settings", json={"farm_name": "My Lab"})
        assert r.status_code == 200
        assert client.get("/api/settings").json()["farm_name"] == "My Lab"


# ── Print history ─────────────────────────────────────────────────────────────

class TestHistory:

    def test_history_empty(self, client):
        r = client.get("/api/history")
        assert r.status_code == 200
        assert r.json() == []

    def test_history_returns_jobs_after_write(self, client):
        import database as db
        db.start_print_job("printer-1", "Printer One", "model.gcode")
        r = client.get("/api/history")
        assert len(r.json()) == 1
        assert r.json()[0]["file_name"] == "model.gcode"
        assert r.json()[0]["status"] == "running"

    def test_history_newest_first(self, client):
        import database as db
        import time
        db.start_print_job("p1", "P1", "first.gcode")
        time.sleep(0.01)
        db.start_print_job("p1", "P1", "second.gcode")
        jobs = client.get("/api/history").json()
        assert jobs[0]["file_name"] == "second.gcode"

    def test_history_finished_job_shows_duration(self, client):
        import database as db
        import time
        job = db.start_print_job("p1", "P1", "test.gcode")
        time.sleep(0.1)
        db.finish_print_job(job.id, "completed")
        jobs = client.get("/api/history").json()
        assert jobs[0]["status"] == "completed"
        assert jobs[0]["duration_seconds"] is not None
        assert jobs[0]["duration_seconds"] >= 0


# ── HMS alert dismiss / restore ───────────────────────────────────────────────

class TestDismissedAlerts:

    def _make_printer(self, client):
        return client.post("/api/printers", json=PRINTER_PAYLOAD).json()["id"]

    def test_dismiss_alert(self, client):
        pid = self._make_printer(client)
        r = client.post(
            f"/api/printers/{pid}/dismissed-alerts",
            json={"hms_code": "HMS_0500-0500-0001-0007"},
        )
        assert r.status_code in (200, 201)
        assert "HMS_0500-0500-0001-0007" in r.json()["dismissed"]

    def test_dismiss_alert_is_idempotent(self, client):
        pid = self._make_printer(client)
        for _ in range(3):
            client.post(
                f"/api/printers/{pid}/dismissed-alerts",
                json={"hms_code": "HMS_0500-0500-0001-0007"},
            )
        r = client.get(f"/api/printers/{pid}/dismissed-alerts")
        assert r.json()["dismissed"].count("HMS_0500-0500-0001-0007") == 1

    def test_restore_alert(self, client):
        pid = self._make_printer(client)
        code = "HMS_0500-0500-0001-0007"
        client.post(f"/api/printers/{pid}/dismissed-alerts", json={"hms_code": code})
        r = client.delete(f"/api/printers/{pid}/dismissed-alerts/{code}")
        assert r.status_code == 200
        assert code not in r.json()["dismissed"]

    def test_get_dismissed_alerts_empty(self, client):
        pid = self._make_printer(client)
        r = client.get(f"/api/printers/{pid}/dismissed-alerts")
        assert r.status_code == 200
        assert r.json()["dismissed"] == []

    def test_multiple_alerts_dismissed(self, client):
        pid = self._make_printer(client)
        codes = ["HMS_0001-0001-0001-0001", "HMS_0002-0002-0002-0002"]
        for code in codes:
            client.post(f"/api/printers/{pid}/dismissed-alerts", json={"hms_code": code})
        dismissed = client.get(f"/api/printers/{pid}/dismissed-alerts").json()["dismissed"]
        assert set(dismissed) == set(codes)


# ── User management ───────────────────────────────────────────────────────────

class TestUserManagement:
    """
    These tests use the session-scoped `client` fixture which bypasses auth
    and injects a fake admin user, so all admin-only endpoints are reachable.
    """

    NEW_USER = {"username": "newuser", "password": "password123", "role": "viewer"}

    def test_list_users_returns_list(self, client):
        r = client.get("/api/users")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_create_user_returns_201(self, client):
        r = client.post("/api/users", json=self.NEW_USER)
        assert r.status_code == 201

    def test_create_user_fields_correct(self, client):
        r = client.post("/api/users", json=self.NEW_USER)
        body = r.json()
        assert body["username"] == "newuser"
        assert body["role"] == "viewer"

    def test_create_user_appears_in_list(self, client):
        client.post("/api/users", json=self.NEW_USER)
        users = client.get("/api/users").json()
        assert any(u["username"] == "newuser" for u in users)

    def test_create_duplicate_username_returns_400(self, client):
        client.post("/api/users", json=self.NEW_USER)
        r = client.post("/api/users", json=self.NEW_USER)
        assert r.status_code == 400

    def test_create_user_short_password_returns_400(self, client):
        r = client.post("/api/users", json={**self.NEW_USER, "password": "short"})
        assert r.status_code == 400

    def test_create_user_invalid_role_returns_400(self, client):
        r = client.post("/api/users", json={**self.NEW_USER, "role": "superuser"})
        assert r.status_code == 400

    def test_create_user_empty_username_returns_400(self, client):
        r = client.post("/api/users", json={**self.NEW_USER, "username": "   "})
        assert r.status_code == 400

    def test_delete_user(self, client):
        client.post("/api/users", json=self.NEW_USER)
        r = client.delete(f"/api/users/{self.NEW_USER['username']}")
        assert r.status_code == 204

    def test_delete_user_removes_from_list(self, client):
        client.post("/api/users", json=self.NEW_USER)
        client.delete(f"/api/users/{self.NEW_USER['username']}")
        users = client.get("/api/users").json()
        assert not any(u["username"] == "newuser" for u in users)

    def test_delete_unknown_user_returns_404(self, client):
        r = client.delete("/api/users/doesnotexist")
        assert r.status_code == 404

    def test_delete_self_returns_400(self, client):
        # The fake auth user is "testadmin" (see conftest.py)
        r = client.delete("/api/users/testadmin")
        assert r.status_code == 400

    def test_admin_reset_password_success(self, client):
        client.post("/api/users", json=self.NEW_USER)
        r = client.patch(
            f"/api/users/{self.NEW_USER['username']}/password",
            json={"new_password": "brandnewpass"},
        )
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_admin_reset_password_too_short_returns_400(self, client):
        client.post("/api/users", json=self.NEW_USER)
        r = client.patch(
            f"/api/users/{self.NEW_USER['username']}/password",
            json={"new_password": "tiny"},
        )
        assert r.status_code == 400

    def test_admin_reset_password_unknown_user_returns_404(self, client):
        r = client.patch("/api/users/nobody/password", json={"new_password": "validpassword"})
        assert r.status_code == 404


# ── Timelapse model gating ────────────────────────────────────────────────────

class TestTimelapseModelGate:
    """Timelapse retrieval over FTPS is only offered on models that store
    timelapses on the SD card — see printer_type_timelapse_supported in
    database.py, which drives the gate off the user-managed printer types."""

    def _printer(self, client, model):
        payload = {**PRINTER_PAYLOAD, "model": model, "serial": f"SN{model}"}
        return client.post("/api/printers", json=payload).json()["id"]

    @pytest.mark.parametrize("model", ["H2D", "H2S", "P2S"])
    def test_supported_models_reach_the_ftps_layer(self, client, model):
        """The gate must let these through to the SD-card listing. ftps is
        mocked so the test never dials a real printer."""
        pid = self._printer(client, model)
        listing = ["/timelapse/video_2.mp4", "/timelapse/video_1.mp4", "/timelapse/notes.txt"]
        with patch("main.ftps.list_dir", return_value=listing) as list_dir:
            r = client.get(f"/api/printers/{pid}/timelapses")
        assert r.status_code == 200
        # Non-video entries dropped, newest first
        assert r.json()["files"] == ["video_2.mp4", "video_1.mp4"]
        assert list_dir.called

    @pytest.mark.parametrize("model", ["H2D", "H2S", "P2S"])
    def test_supported_models_are_never_gated_out(self, client, model):
        pid = self._printer(client, model)
        with patch("main.ftps.list_dir", return_value=[]):
            r = client.get(f"/api/printers/{pid}/timelapses")
        assert "not supported" not in r.text

    @pytest.mark.parametrize("model", ["A1", "P1S"])
    def test_unsupported_models_return_404(self, client, model):
        """Rejected before any FTPS connection is attempted."""
        pid = self._printer(client, model)
        with patch("main.ftps.list_dir") as list_dir:
            r = client.get(f"/api/printers/{pid}/timelapses")
        assert r.status_code == 404
        assert "not supported" in r.text
        assert not list_dir.called
