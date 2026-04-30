"""
Tests for the Bambu cloud API client (bambu_cloud.py).

All HTTP calls are mocked — no real network requests are made.

login() and verify_2fa() both use httpx.Client internally, so we patch
bambu_cloud.httpx.Client to return a mock with a preset .post() response.
get_devices() uses httpx.get directly, so we patch bambu_cloud.httpx.get.
"""

import pytest
from unittest.mock import MagicMock, patch
import httpx

import bambu_cloud as bc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_response(status_code: int, json_body: dict) -> MagicMock:
    """Build a mock httpx.Response with the given status code and JSON body."""
    r = MagicMock(spec=httpx.Response)
    r.status_code = status_code
    r.text = str(json_body)
    r.json.return_value = json_body
    # raise_for_status raises on 4xx/5xx
    if status_code >= 400:
        r.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=r
        )
    else:
        r.raise_for_status.return_value = None
    return r


def _mock_client(resp: MagicMock) -> MagicMock:
    """Build a mock httpx.Client whose .post() returns *resp*."""
    client = MagicMock()
    client.post.return_value = resp
    client.cookies = {}          # dict(client.cookies) → {}
    client.close = MagicMock()
    return client


# ---------------------------------------------------------------------------
# TestLogin
# ---------------------------------------------------------------------------

class TestLogin:

    def teardown_method(self, _method):
        """Clean up any 2FA sessions left by a test."""
        bc._tfa_sessions.clear()

    def test_successful_login_no_2fa(self):
        resp = _make_response(200, {"accessToken": "eyJtesttoken"})
        mock_client = _mock_client(resp)
        with patch("bambu_cloud.httpx.Client", return_value=mock_client):
            result = bc.login("user@example.com", "password")
        assert not result.needs_2fa
        assert result.token == "eyJtesttoken"
        assert result.error is None

    def test_login_requires_2fa(self):
        resp = _make_response(200, {"loginType": "verifyCode", "tfaKey": ""})
        mock_client = _mock_client(resp)
        with patch("bambu_cloud.httpx.Client", return_value=mock_client):
            result = bc.login("user@example.com", "password")
        assert result.needs_2fa
        assert result.tfa_key == ""
        assert result.token is None
        # Session should have been stored
        assert "user@example.com" in bc._tfa_sessions

    def test_login_bad_credentials(self):
        resp = _make_response(400, {"error": "Invalid credentials"})
        mock_client = _mock_client(resp)
        with patch("bambu_cloud.httpx.Client", return_value=mock_client):
            result = bc.login("bad@example.com", "wrong")
        assert not result.needs_2fa
        assert result.error is not None
        assert "400" in result.error

    def test_login_network_error(self):
        mock_client = MagicMock()
        mock_client.post.side_effect = Exception("timeout")
        mock_client.close = MagicMock()
        with patch("bambu_cloud.httpx.Client", return_value=mock_client):
            result = bc.login("user@example.com", "password")
        assert result.error == "timeout"

    def test_login_unexpected_response(self):
        resp = _make_response(200, {"someUnknownField": "value"})
        mock_client = _mock_client(resp)
        with patch("bambu_cloud.httpx.Client", return_value=mock_client):
            result = bc.login("user@example.com", "password")
        assert result.error is not None

    def test_login_clears_previous_session_for_same_email(self):
        """A second login for the same email closes the previous client."""
        old_client = MagicMock()
        old_client.close = MagicMock()
        bc._tfa_sessions["user@example.com"] = old_client

        resp = _make_response(200, {"accessToken": "fresh-token"})
        mock_client = _mock_client(resp)
        with patch("bambu_cloud.httpx.Client", return_value=mock_client):
            bc.login("user@example.com", "password")

        old_client.close.assert_called_once()


# ---------------------------------------------------------------------------
# TestVerify2FA
# ---------------------------------------------------------------------------

class TestVerify2FA:

    def teardown_method(self, _method):
        bc._tfa_sessions.clear()

    def _store_session(self, email: str, resp: MagicMock) -> MagicMock:
        """Pre-load a mock client into _tfa_sessions (mimics a prior login)."""
        client = _mock_client(resp)
        bc._tfa_sessions[email] = client
        return client

    def test_successful_verification_reuses_stored_session(self):
        resp = _make_response(200, {"accessToken": "eyJverified"})
        self._store_session("user@example.com", resp)
        result = bc.verify_2fa("", "123456", email="user@example.com")
        assert result.token == "eyJverified"
        assert result.error is None
        # Session should have been consumed
        assert "user@example.com" not in bc._tfa_sessions

    def test_invalid_code_returns_error(self):
        resp = _make_response(400, {"error": "Invalid code"})
        self._store_session("user@example.com", resp)
        result = bc.verify_2fa("", "000000", email="user@example.com")
        assert result.error is not None
        assert result.needs_2fa is True

    def test_network_error_returns_error(self):
        client = MagicMock()
        client.post.side_effect = Exception("network down")
        client.cookies = {}
        client.close = MagicMock()
        bc._tfa_sessions["user@example.com"] = client
        result = bc.verify_2fa("", "123456", email="user@example.com")
        assert result.error is not None
        assert "network down" in result.error

    def test_no_stored_session_falls_back_to_fresh_client(self):
        """If no session stored (e.g. server restart), creates a new client."""
        resp = _make_response(200, {"accessToken": "eyJfresh"})
        mock_client = _mock_client(resp)
        # No entry in _tfa_sessions
        with patch("bambu_cloud.httpx.Client", return_value=mock_client):
            result = bc.verify_2fa("", "123456", email="user@example.com")
        assert result.token == "eyJfresh"

    def test_account_email_included_in_post_body(self):
        """The email should be sent as 'account' in the TFA POST body."""
        resp = _make_response(200, {"accessToken": "tok"})
        client = self._store_session("alice@example.com", resp)
        bc.verify_2fa("", "654321", email="alice@example.com")
        call_kwargs = client.post.call_args
        body = call_kwargs.kwargs.get("json") or call_kwargs.args[1] if len(call_kwargs.args) > 1 else {}
        if not body:
            body = client.post.call_args[1].get("json", {})
        assert body.get("account") == "alice@example.com"
        assert body.get("tfaCode") == "654321"


# ---------------------------------------------------------------------------
# TestGetDevices
# ---------------------------------------------------------------------------

class TestGetDevices:

    def test_returns_device_list(self):
        resp = _make_response(200, {
            "devices": [
                {
                    "dev_id": "01P00C123456",
                    "name": "My P1S",
                    "dev_model_name": "BL-P002",
                    "dev_product_name": "Bambu Lab P1S",
                    "dev_access_code": "12345678",
                    "online": True,
                },
                {
                    "dev_id": "01H00A654321",
                    "name": "Big Friend",
                    "dev_model_name": "BL-H001",
                    "dev_product_name": "Bambu Lab H2D",
                    "dev_access_code": "87654321",
                    "online": False,
                },
            ]
        })
        with patch("bambu_cloud.httpx.get", return_value=resp):
            devices = bc.get_devices("some-token")
        assert len(devices) == 2
        assert devices[0].dev_id == "01P00C123456"
        assert devices[0].model_label == "P1S"
        assert devices[1].model_label == "H2D"
        assert devices[1].lan_mode_default is True

    def test_unknown_model_falls_back_to_product_name(self):
        resp = _make_response(200, {
            "devices": [{
                "dev_id": "UNKN0001",
                "name": "New Printer",
                "dev_model_name": "BL-X999",
                "dev_product_name": "Bambu Lab X999",
                "dev_access_code": "00000000",
                "online": False,
            }]
        })
        with patch("bambu_cloud.httpx.get", return_value=resp):
            devices = bc.get_devices("token")
        assert devices[0].model_label == "X999"

    def test_skips_malformed_devices(self):
        resp = _make_response(200, {
            "devices": [
                {"bad": "data"},   # should be skipped (no dev_id)
                {
                    "dev_id": "GOOD0001",
                    "name": "Good Printer",
                    "dev_model_name": "BL-P002",
                    "dev_product_name": "Bambu Lab P1S",
                    "dev_access_code": "12345678",
                    "online": True,
                },
            ]
        })
        with patch("bambu_cloud.httpx.get", return_value=resp):
            devices = bc.get_devices("token")
        assert len(devices) == 1

    def test_model_map_coverage(self):
        """All known model codes should map to correct labels."""
        cases = {
            "BL-A001": "A1 Mini",
            "BL-A002": "A1",
            "BL-P001": "P1P",
            "BL-P002": "P1S",
            "BL-P003": "P2S",
            "BL-B001": "X1C",
            "BL-B002": "X1E",
            "BL-H001": "H2D",
        }
        for code, expected in cases.items():
            d = bc.BambuDevice(
                dev_id="X", name="Test",
                dev_model_name=code,
                dev_product_name="Bambu Lab " + expected,
                dev_access_code="00000000",
            )
            assert d.model_label == expected, f"{code} should map to {expected}"

    def test_lan_mode_defaults(self):
        """LAN mode off for A1/A1 Mini/P1P/P1S; on for P2S/H2D/X1C/X1E."""
        off_models = ["BL-A001", "BL-A002", "BL-P001", "BL-P002"]
        on_models  = ["BL-P003", "BL-H001", "BL-B001", "BL-B002"]

        for code in off_models:
            d = bc.BambuDevice(dev_id="X", name="T", dev_model_name=code,
                               dev_product_name="T", dev_access_code="00000000")
            assert d.lan_mode_default is False, f"{code} should default lan_mode=False"

        for code in on_models:
            d = bc.BambuDevice(dev_id="X", name="T", dev_model_name=code,
                               dev_product_name="T", dev_access_code="00000000")
            assert d.lan_mode_default is True, f"{code} should default lan_mode=True"
