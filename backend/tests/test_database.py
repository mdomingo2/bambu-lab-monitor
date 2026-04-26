"""
Unit tests for database.py functions.

Uses the in-memory engine configured in conftest.py — no file I/O.
"""

import time
import pytest
import database as db


# ── Printer CRUD ─────────────────────────────────────────────────────────────

class TestPrinterDB:

    def _make_printer(self, **kwargs):
        from models import Printer
        defaults = dict(
            name="Test", model="P1S", ip="10.0.0.1",
            serial="SN001", access_code="12345678",
        )
        return db.create_printer(Printer(**{**defaults, **kwargs}))

    def test_create_and_retrieve(self):
        p = self._make_printer(name="Alpha")
        found = db.get_printer(p.id)
        assert found is not None
        assert found.name == "Alpha"

    def test_get_unknown_id_returns_none(self):
        assert db.get_printer("no-such-id") is None

    def test_get_all_empty(self):
        assert db.get_all_printers() == []

    def test_get_all_returns_all(self):
        self._make_printer(name="A", serial="S1")
        self._make_printer(name="B", serial="S2")
        assert len(db.get_all_printers()) == 2

    def test_update_name(self):
        p = self._make_printer()
        updated = db.update_printer(p.id, {"name": "Updated"})
        assert updated.name == "Updated"

    def test_update_unknown_id_returns_none(self):
        assert db.update_printer("bad-id", {"name": "X"}) is None

    def test_delete(self):
        p = self._make_printer()
        assert db.delete_printer(p.id) is True
        assert db.get_printer(p.id) is None

    def test_delete_unknown_returns_false(self):
        assert db.delete_printer("no-such-id") is False


# ── Settings ──────────────────────────────────────────────────────────────────

class TestSettings:

    def test_defaults_returned_for_missing_keys(self):
        settings = db.get_settings()
        assert settings["farm_name"] == "Print Farm"

    def test_set_and_get_setting(self):
        db.set_setting("farm_name", "Test Lab")
        assert db.get_settings()["farm_name"] == "Test Lab"

    def test_set_setting_upserts(self):
        db.set_setting("farm_name", "First")
        db.set_setting("farm_name", "Second")
        assert db.get_settings()["farm_name"] == "Second"


# ── Print history ─────────────────────────────────────────────────────────────

class TestPrintHistory:

    def test_start_job_creates_running_record(self):
        job = db.start_print_job("p1", "Printer One", "model.gcode")
        assert job.status == "running"
        assert job.id is not None
        assert job.started_at != ""

    def test_finish_job_sets_status(self):
        job = db.start_print_job("p1", "Printer One", "model.gcode")
        db.finish_print_job(job.id, "completed")
        history = db.get_print_history()
        assert history[0].status == "completed"

    def test_finish_job_sets_duration(self):
        job = db.start_print_job("p1", "P1", "model.gcode")
        time.sleep(0.05)
        db.finish_print_job(job.id, "completed")
        history = db.get_print_history()
        assert history[0].duration_seconds is not None
        assert history[0].duration_seconds >= 0

    def test_finish_job_sets_finished_at(self):
        job = db.start_print_job("p1", "P1", "model.gcode")
        db.finish_print_job(job.id, "failed")
        history = db.get_print_history()
        assert history[0].finished_at is not None

    def test_history_newest_first(self):
        db.start_print_job("p1", "P1", "first.gcode")
        time.sleep(0.01)
        db.start_print_job("p1", "P1", "second.gcode")
        history = db.get_print_history()
        assert history[0].file_name == "second.gcode"

    def test_history_empty_when_no_jobs(self):
        assert db.get_print_history() == []

    def test_abandon_running_marks_cancelled(self):
        job = db.start_print_job("p1", "P1", "stuck.gcode")
        assert job.status == "running"
        db.abandon_running_jobs()
        history = db.get_print_history()
        assert history[0].status == "cancelled"

    def test_abandon_completed_jobs_unaffected(self):
        job = db.start_print_job("p1", "P1", "done.gcode")
        db.finish_print_job(job.id, "completed")
        db.abandon_running_jobs()
        history = db.get_print_history()
        assert history[0].status == "completed"


# ── Dismissed alerts ──────────────────────────────────────────────────────────

class TestDismissedAlerts:

    def test_dismiss_alert(self):
        db.dismiss_alert("p1", "HMS_0001-0001-0001-0001")
        codes = db.get_dismissed_alerts("p1")
        assert "HMS_0001-0001-0001-0001" in codes

    def test_dismiss_is_idempotent(self):
        code = "HMS_0001-0001-0001-0001"
        db.dismiss_alert("p1", code)
        db.dismiss_alert("p1", code)   # second call must not raise
        assert db.get_dismissed_alerts("p1").count(code) == 1

    def test_undismiss_alert(self):
        code = "HMS_0001-0001-0001-0001"
        db.dismiss_alert("p1", code)
        db.undismiss_alert("p1", code)
        assert code not in db.get_dismissed_alerts("p1")

    def test_undismiss_nonexistent_is_noop(self):
        db.undismiss_alert("p1", "HMS_FFFF-FFFF-FFFF-FFFF")  # should not raise

    def test_get_all_dismissed_alerts(self):
        db.dismiss_alert("p1", "HMS_0001-0001-0001-0001")
        db.dismiss_alert("p2", "HMS_0002-0002-0002-0002")
        all_dismissed = db.get_all_dismissed_alerts()
        assert "p1" in all_dismissed
        assert "p2" in all_dismissed

    def test_dismissed_alerts_scoped_to_printer(self):
        code = "HMS_0001-0001-0001-0001"
        db.dismiss_alert("p1", code)
        assert code not in db.get_dismissed_alerts("p2")
