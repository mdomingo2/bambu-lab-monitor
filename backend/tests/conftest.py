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
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine, select, text
from sqlmodel.pool import StaticPool

# ── In-memory test database ───────────────────────────────────────────────────

import database as _db

_TEST_ENGINE = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
# Replace the production engine before main.py is imported
_db.engine = _TEST_ENGINE

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
    """
    with (
        patch("mqtt_manager.PrinterConnection.start"),
        patch("main._go2rtc_put",    new=AsyncMock()),
        patch("main._go2rtc_delete", new=AsyncMock()),
    ):
        from main import app
        SQLModel.metadata.create_all(_TEST_ENGINE)
        with TestClient(app) as c:
            yield c


# ── Per-test DB isolation ─────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clean_tables():
    """Truncate all tables before every test so tests are fully independent."""
    SQLModel.metadata.create_all(_TEST_ENGINE)
    yield
    with Session(_TEST_ENGINE) as session:
        for table in reversed(SQLModel.metadata.sorted_tables):
            session.exec(text(f"DELETE FROM {table.name}"))  # type: ignore[call-overload]
        session.commit()
