"""
Tests for the Bambu cloud API client (bambu_cloud.py).

All HTTP calls are mocked — no real network requests are made.
"""

import pytest
from unittest.mock import patch, MagicMock
import httpx

import bambu_cloud as bc


def _make_response(status_code: int, json_body: dict) -> MagicMock:
    """Helper to build a mock httpx.Response."""
    r = MagicMock(spec=httpx.Response)
    r.status_code = status_code
    r.json.return_value = json_body
    r.raise_for_status = MagicMock()
    if status_code >= 400:
        r.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=r
        )
    return r


class TestLogin:
    def test_successful_login_no_2fa(self):
        mock_resp = _make_response(200, {
            "accessToken": "eyJtesttoken",
            "refreshToken": "eyJrefresh",
        })
        with patch("httpx.post", return_value=mock_resp):
            result = bc.login("user@example.com", "password")
        assert not result.needs_2fa
        assert result.token == "eyJtesttoken"
        assert result.error is None

    def test_login_requires_2fa(self):
        mock_resp = _make_response(200, {
            "loginType": "verifyCode",
            "tfaKey": "tfa-key-abc123",
            "accessToken": None,
        })
        with patch("httpx.post", return_value=mock_resp):
            result = bc.login("user@example.com", "password")
        assert result.needs_2fa
        assert result.tfa_key == "tfa-key-abc123"
        assert result.token is None

    def test_login_bad_credentials(self):
        mock_resp = _make_response(400, {"error": "Invalid credentials"})
        with patch("httpx.post", return_value=mock_resp):
            result = bc.login("bad@example.com", "wrong")
        assert not result.needs_2fa
        assert result.error is not None
        assert "400" in result.error

    def test_login_network_error(self):
        with patch("httpx.post", side_effect=Exception("timeout")):
            result = bc.login("user@example.com", "password")
        assert result.error == "timeout"

    def test_login_unexpected_response(self):
        mock_resp = _make_response(200, {"someUnknownField": "value"})
        with patch("httpx.post", return_value=mock_resp):
            result = bc.login("user@example.com", "password")
        assert result.error is not None


class TestVerify2FA:
    def test_successful_verification(self):
        mock_resp = _make_response(200, {"accessToken": "eyJverified"})
        with patch("httpx.post", return_value=mock_resp):
            result = bc.verify_2fa("tfa-key", "123456")
        assert result.token == "eyJverified"
        assert result.error is None

    def test_invalid_code(self):
        mock_resp = _make_response(400, {"error": "Invalid code"})
        with patch("httpx.post", return_value=mock_resp):
            result = bc.verify_2fa("tfa-key", "000000")
        assert result.error is not None

    def test_network_error(self):
        with patch("httpx.post", side_effect=Exception("network down")):
            result = bc.verify_2fa("key", "123456")
        assert "network down" in result.error


class TestGetDevices:
    def test_returns_device_list(self):
        mock_resp = _make_response(200, {
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
        with patch("httpx.get", return_value=mock_resp):
            devices = bc.get_devices("some-token")
        assert len(devices) == 2
        assert devices[0].dev_id == "01P00C123456"
        assert devices[0].model_label == "P1S"
        assert devices[1].model_label == "H2D"
        assert devices[1].lan_mode_default is True

    def test_unknown_model_falls_back_to_product_name(self):
        mock_resp = _make_response(200, {
            "devices": [{
                "dev_id": "UNKN0001",
                "name": "New Printer",
                "dev_model_name": "BL-X999",
                "dev_product_name": "Bambu Lab X999",
                "dev_access_code": "00000000",
                "online": False,
            }]
        })
        with patch("httpx.get", return_value=mock_resp):
            devices = bc.get_devices("token")
        assert devices[0].model_label == "X999"

    def test_skips_malformed_devices(self):
        mock_resp = _make_response(200, {
            "devices": [
                {"bad": "data"},  # should be skipped
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
        with patch("httpx.get", return_value=mock_resp):
            devices = bc.get_devices("token")
        assert len(devices) == 1

    def test_model_map_coverage(self):
        """Smoke-test all known model codes map to our labels."""
        cases = {
            "BL-A002": "A1",
            "BL-P002": "P1S",
            "BL-P003": "P2S",
            "BL-H001": "H2D",
        }
        for code, expected in cases.items():
            d = bc.BambuDevice(
                dev_id="X",
                name="Test",
                dev_model_name=code,
                dev_product_name="Bambu Lab " + expected,
                dev_access_code="00000000",
            )
            assert d.model_label == expected, f"{code} should map to {expected}"

    def test_lan_mode_defaults(self):
        """LAN mode should be False for A1/P1S, True for P2S/H2D."""
        off_models = ["BL-A001", "BL-A002", "BL-P001", "BL-P002"]
        on_models  = ["BL-P003", "BL-H001"]

        for code in off_models:
            d = bc.BambuDevice(dev_id="X", name="T", dev_model_name=code,
                               dev_product_name="T", dev_access_code="00000000")
            assert d.lan_mode_default is False, f"{code} should default lan_mode=False"

        for code in on_models:
            d = bc.BambuDevice(dev_id="X", name="T", dev_model_name=code,
                               dev_product_name="T", dev_access_code="00000000")
            assert d.lan_mode_default is True, f"{code} should default lan_mode=True"
