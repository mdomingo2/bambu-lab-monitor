"""
Tests for the authentication system.

These tests use a separate TestClient that does NOT override require_auth,
so they exercise the real cookie-based auth flow.
"""

import os
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from sqlmodel import SQLModel

import database as _db


@pytest.fixture(scope="module")
def auth_client():
    """A TestClient with real auth (no require_auth override).

    The session-scoped `client` fixture in conftest.py installs a fake
    require_auth override for the whole pytest session. We temporarily
    remove it here so that real cookie-based auth is exercised.
    """
    with (
        patch("mqtt_manager.PrinterConnection.start"),
        patch("main._go2rtc_put",    new=AsyncMock()),
        patch("main._go2rtc_delete", new=AsyncMock()),
    ):
        from main import app
        import auth as _auth_module

        # Remove the fake-auth override (restore after module tests finish)
        saved_override = app.dependency_overrides.pop(_auth_module.require_auth, None)
        try:
            SQLModel.metadata.create_all(_db.engine)
            with TestClient(app, raise_server_exceptions=True) as c:
                yield c
        finally:
            if saved_override is not None:
                app.dependency_overrides[_auth_module.require_auth] = saved_override


@pytest.fixture(autouse=True)
def ensure_test_user():
    """Re-create the test user before every test (clean_tables deletes it)."""
    import auth as _auth
    SQLModel.metadata.create_all(_db.engine)
    if not _db.get_user("testuser"):
        _db.create_user("testuser", _auth.hash_password("testpass123"))
    yield


class TestLoginLogout:
    def test_login_success(self, auth_client):
        r = auth_client.post("/api/auth/login",
                             json={"username": "testuser", "password": "testpass123"})
        assert r.status_code == 200
        body = r.json()
        assert body["username"] == "testuser"
        assert body["role"] == "admin"
        # Session cookie must be set
        assert "bambu_session" in r.cookies

    def test_login_wrong_password(self, auth_client):
        r = auth_client.post("/api/auth/login",
                             json={"username": "testuser", "password": "wrongpass"})
        assert r.status_code == 401

    def test_login_unknown_user(self, auth_client):
        r = auth_client.post("/api/auth/login",
                             json={"username": "nobody", "password": "irrelevant"})
        assert r.status_code == 401

    def test_logout_clears_cookie(self, auth_client):
        # Log in first
        auth_client.post("/api/auth/login",
                         json={"username": "testuser", "password": "testpass123"})
        r = auth_client.post("/api/auth/logout")
        assert r.status_code == 200
        # Cookie should be deleted (empty value or absent)
        assert r.cookies.get("bambu_session", "") == ""


class TestProtectedEndpoints:
    def test_unauthenticated_returns_401(self, auth_client):
        """Without a session cookie, protected endpoints return 401."""
        # Ensure no active session by logging out first
        auth_client.post("/api/auth/logout")
        r = auth_client.get("/api/printers")
        assert r.status_code == 401

    def test_authenticated_can_access(self, auth_client):
        """After login, protected endpoints are accessible."""
        r = auth_client.post("/api/auth/login",
                             json={"username": "testuser", "password": "testpass123"})
        assert r.status_code == 200, f"Login failed: {r.text}"
        r = auth_client.get("/api/printers")
        assert r.status_code == 200

    def test_me_returns_current_user(self, auth_client):
        auth_client.post("/api/auth/login",
                         json={"username": "testuser", "password": "testpass123"})
        r = auth_client.get("/api/auth/me")
        assert r.status_code == 200
        assert r.json()["username"] == "testuser"

    def test_me_without_auth_returns_401(self, auth_client):
        """Without a session, /api/auth/me returns 401."""
        auth_client.post("/api/auth/logout")
        r = auth_client.get("/api/auth/me")
        assert r.status_code == 401


class TestPasswordChange:
    def test_change_password_success(self, auth_client):
        import auth as _auth
        # Ensure user exists with known password
        _db.update_user_password("testuser", _auth.hash_password("testpass123"))
        auth_client.post("/api/auth/login",
                         json={"username": "testuser", "password": "testpass123"})
        r = auth_client.post("/api/auth/change-password", json={
            "current_password": "testpass123",
            "new_password": "newpass456",
        })
        assert r.status_code == 200
        # Reset for other tests
        _db.update_user_password("testuser", _auth.hash_password("testpass123"))

    def test_change_password_wrong_current(self, auth_client):
        auth_client.post("/api/auth/login",
                         json={"username": "testuser", "password": "testpass123"})
        r = auth_client.post("/api/auth/change-password", json={
            "current_password": "wrongcurrent",
            "new_password": "newpass456",
        })
        assert r.status_code == 400

    def test_change_password_too_short(self, auth_client):
        auth_client.post("/api/auth/login",
                         json={"username": "testuser", "password": "testpass123"})
        r = auth_client.post("/api/auth/change-password", json={
            "current_password": "testpass123",
            "new_password": "short",
        })
        assert r.status_code == 400


class TestTokenUtils:
    def test_create_and_decode_token(self):
        import auth as _auth
        token = _auth.create_access_token("alice")
        assert _auth.decode_token(token) == "alice"

    def test_decode_invalid_token_returns_none(self):
        import auth as _auth
        assert _auth.decode_token("not.a.token") is None

    def test_hash_and_verify_password(self):
        import auth as _auth
        h = _auth.hash_password("mysecret")
        assert _auth.verify_password("mysecret", h)
        assert not _auth.verify_password("wrong", h)
