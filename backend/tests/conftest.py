"""
Shared test fixtures for the Bambu Farm Monitor backend.

Strategy:
  - DATABASE_URL is forced to an in-memory SQLite engine *before* any app
    modules are imported, so database.py's module-level engine uses it.
  - MQTT connections are patched so no real threads are spawned and no real
    printers are dialled.
  - go2rtc HTTP calls are patched with AsyncMock so the lifespan completes.
  - Every test gets a clean slate via the `clean_tables` autouse fixture.
"""

import os
# Must be set before any app module import (database.py reads it at load time)
os.environ["DATABASE_URL"] = "sqlite://"

import pytest
from unittest.mock import patch, AsyncMock
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine, select, text
from sqlmodel.pool import StaticPool

# ── In-memory test database ───────────────────────────────────────────────────

import database as _db
from models import PrinterType

_TEST_ENGINE = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
# Replace the production engine before main.py is imported
_db.engine = _TEST_ENGINE


# Snapshot the seed rows as plain dicts at import time.  database.py's
# _SEED_PRINTER_TYPES are model instances that get attached to a Session when
# _migrate() seeds them during app startup; once that Session closes they are
# detached, and reading pt.name later raises DetachedInstanceError.  Copying
# the values now — before anything persists them — sidesteps that entirely.
_SEED_TYPE_ROWS = [
    {
        "name": pt.name,
        "lan_mode_default": pt.lan_mode_default,
        "timelapse_support": pt.timelapse_support,
        "camera_capable": pt.camera_capable,
    }
    for pt in _db._SEED_PRINTER_TYPES
]


def _seed_printer_types() -> None:
    """Re-seed the default printer types.

    Printer types are reference data, not per-test state: in production
    database._migrate() seeds them once and they are always present.  The
    clean_tables fixture truncates every table, so without this the table
    would be empty from the second test onward and anything driven off it
    — the timelapse gate, LAN Mode defaults — would silently misbehave.
    """
    with Session(_TEST_ENGINE) as session:
        if session.exec(select(PrinterType)).first():
            return
        for row in _SEED_TYPE_ROWS:
            session.add(PrinterType(**row))
        session.commit()

# ── Shared test payload ───────────────────────────────────────────────────────

PRINTER_PAYLOAD = {
    "name": "Test P1S",
    "model": "P1S",
    "ip": "192.168.1.100",
    "serial": "TESTSERIAL01",
    "access_code": "12345678",
    "lan_mode": True,
}


# ── Session-scoped test client ────────────────────────────────────────────────

@pytest.fixture(scope="session")
def client():
    """
    Create a FastAPI TestClient once per test session.

    MQTT PrinterConnection.start is patched so no background threads are
    spawned, and go2rtc helpers are patched with AsyncMock so the lifespan
    does not attempt real HTTP calls.

    auth.require_auth is overridden to return a dummy admin user so API
    tests don't need to set up real session cookies.
    """
    with (
        patch("mqtt_manager.PrinterConnection.start"),
        patch("main._go2rtc_put",    new=AsyncMock()),
        patch("main._go2rtc_delete", new=AsyncMock()),
    ):
        from main import app
        import auth
        from models import User

        # Bypass auth for all tests — return a synthetic admin user.
        def _fake_auth():
            return User(
                id="test-user-id",
                username="testadmin",
                hashed_password="",
                role="admin",
                created_at="",
            )

        app.dependency_overrides[auth.require_auth] = _fake_auth

        SQLModel.metadata.create_all(_TEST_ENGINE)
        with TestClient(app) as c:
            yield c

        app.dependency_overrides.clear()


# ── Per-test DB isolation ─────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clean_tables():
    """Truncate all tables before every test so tests are fully independent."""
    SQLModel.metadata.create_all(_TEST_ENGINE)
    _seed_printer_types()
    yield
    with Session(_TEST_ENGINE) as session:
        for table in reversed(SQLModel.metadata.sorted_tables):
            session.exec(text(f"DELETE FROM {table.name}"))  # type: ignore[call-overload]
        session.commit()
