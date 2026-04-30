"""
Bambu Lab cloud API client.

Handles account login (with optional 2FA) and device discovery.
All communication goes to the unofficial but community-documented Bambu
endpoints; this module isolates every cloud call so it's easy to stub
in tests.

Typical flow
------------
1. client calls login(email, password)
   → {needs_2fa: True, tfa_key: "..."} if 2FA enabled, or
   → {needs_2fa: False, token: "eyJ..."} if no 2FA
2. If needs_2fa, client calls verify(tfa_key, code)
   → {token: "eyJ..."}
3. client calls get_devices(token)
   → list[BambuDevice]
"""

import logging
import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cloud API base URLs
# ---------------------------------------------------------------------------

_AUTH_URL    = "https://bambulab.com/api/sign-in/form"
_TFA_URL     = "https://bambulab.com/api/sign-in/tfa"
_DEVICES_URL = "https://api.bambulab.com/v1/iot-service/api/user/device"

# Timeout for all cloud calls (seconds)
_TIMEOUT = 15

# ---------------------------------------------------------------------------
# Headers required by Bambu's API (mimics the official network agent)
# ---------------------------------------------------------------------------

_AUTH_HEADERS = {
    "User-Agent": "bambu_network_agent/01.09.05.04",
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Referer": "https://bambulab.com/",
}

_API_HEADERS = {
    "User-Agent": "bambu_network_agent/01.09.05.04",
    "Accept": "application/json",
}

# ---------------------------------------------------------------------------
# Known model codes → our internal model labels
# ---------------------------------------------------------------------------
# Source: community reverse-engineering of Bambu's device API.
# "dev_model_name" from the API maps to these device codes.

_MODEL_MAP: dict[str, str] = {
    # A-series
    "BL-A001": "A1 Mini",
    "BL-A002": "A1",
    # P-series
    "BL-P001": "P1P",
    "BL-P002": "P1S",
    "BL-P003": "P2S",   # unconfirmed dev code — may vary by region
    # X-series
    "BL-B001": "X1C",
    "BL-B002": "X1E",
    # H-series
    "BL-H001": "H2D",
}

# Models we actually support in the farm monitor (shown in Setup dropdown)
_SUPPORTED_MODELS = {"A1", "P1S", "P2S", "H2D"}

# Models that default lan_mode=False (camera RTSP not supported)
_LAN_MODE_OFF = {"A1", "A1 Mini", "P1P", "P1S"}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

class BambuDevice(BaseModel):
    """One printer from the Bambu cloud device list."""
    dev_id: str              # serial number
    name: str                # user-assigned name
    dev_model_name: str      # e.g. "BL-P002"
    dev_product_name: str    # human name e.g. "Bambu Lab P1S"
    dev_access_code: str     # MQTT password (shown on printer screen too)
    online: bool = False

    @property
    def model_label(self) -> str:
        """Map dev_model_name to our internal model label.

        Falls back to the first word of dev_product_name if the code is
        unknown (e.g. a brand-new printer type not yet in _MODEL_MAP).
        """
        if self.dev_model_name in _MODEL_MAP:
            return _MODEL_MAP[self.dev_model_name]
        # Try to extract "P1S", "A1", etc. from "Bambu Lab P1S"
        parts = self.dev_product_name.split()
        if parts:
            return parts[-1]
        return self.dev_model_name

    @property
    def lan_mode_default(self) -> bool:
        return self.model_label not in _LAN_MODE_OFF


class BambuLoginResult(BaseModel):
    needs_2fa: bool
    tfa_key: str | None = None       # present when needs_2fa=True
    token: str | None = None         # present when needs_2fa=False
    error: str | None = None         # human-readable error message


# ---------------------------------------------------------------------------
# API functions
# ---------------------------------------------------------------------------

def login(email: str, password: str) -> BambuLoginResult:
    """Authenticate with Bambu cloud using email + password."""
    try:
        r = httpx.post(
            _AUTH_URL,
            json={"account": email, "password": password, "apiError": ""},
            headers=_AUTH_HEADERS,
            timeout=_TIMEOUT,
        )
        logger.info("Bambu login HTTP %s", r.status_code)
        logger.info("Bambu login response body: %s", r.text[:500])
        r.raise_for_status()
        body = r.json()
    except httpx.HTTPStatusError as exc:
        logger.warning("Bambu login error %s: %s", exc.response.status_code, exc.response.text[:300])
        return BambuLoginResult(
            needs_2fa=False,
            error=f"Bambu cloud returned {exc.response.status_code}",
        )
    except Exception as exc:
        return BambuLoginResult(needs_2fa=False, error=str(exc))

    # 2FA required
    if body.get("loginType") == "verifyCode":
        tfa_key = body.get("tfaKey") or body.get("tfa_key") or body.get("tfakey") or ""
        logger.info("Bambu 2FA required. tfaKey field value: %r (all keys: %s)", tfa_key, list(body.keys()))
        return BambuLoginResult(needs_2fa=True, tfa_key=tfa_key)

    token = body.get("accessToken") or body.get("access_token")
    if token:
        return BambuLoginResult(needs_2fa=False, token=token)

    # Unknown response format
    logger.warning("Bambu login unexpected body keys: %s", list(body.keys()))
    return BambuLoginResult(
        needs_2fa=False,
        error=body.get("error") or body.get("message") or "Unexpected response from Bambu cloud",
    )


def verify_2fa(tfa_key: str, code: str) -> BambuLoginResult:
    """Submit the 2FA verification code and get an access token."""
    logger.info("Bambu verify_2fa: tfaKey=%r (len=%d) code=%r", tfa_key[:8] + "..." if len(tfa_key) > 8 else tfa_key, len(tfa_key), code)
    try:
        r = httpx.post(
            _TFA_URL,
            json={"tfaKey": tfa_key, "tfaCode": code, "apiError": ""},
            headers=_AUTH_HEADERS,
            timeout=_TIMEOUT,
        )
        logger.info("Bambu verify HTTP %s body: %s", r.status_code, r.text[:500])
        r.raise_for_status()
        body = r.json()
    except httpx.HTTPStatusError as exc:
        # Try to surface Bambu's actual error message from the response body.
        try:
            err_body = exc.response.json()
            detail = (
                err_body.get("error")
                or err_body.get("message")
                or err_body.get("detail")
                or str(err_body)
            )
        except Exception:
            detail = exc.response.text or str(exc.response.status_code)
        return BambuLoginResult(
            needs_2fa=True,  # keep needs_2fa=True so frontend stays on 2FA step
            tfa_key=tfa_key,
            error=f"Verification failed: {detail}",
        )
    except Exception as exc:
        return BambuLoginResult(needs_2fa=True, tfa_key=tfa_key, error=str(exc))

    token = body.get("accessToken") or body.get("access_token")
    if token:
        return BambuLoginResult(needs_2fa=False, token=token)

    return BambuLoginResult(
        needs_2fa=True,
        tfa_key=tfa_key,
        error=body.get("error") or body.get("message") or "2FA verification failed",
    )


def get_devices(token: str) -> list[BambuDevice]:
    """Fetch all devices registered to the authenticated account."""
    r = httpx.get(
        _DEVICES_URL,
        headers={**_API_HEADERS, "Authorization": f"Bearer {token}"},
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    body = r.json()

    devices = body.get("devices") or body.get("data") or []
    result: list[BambuDevice] = []
    for d in devices:
        try:
            dev_id = d.get("dev_id", "")
            access_code = d.get("dev_access_code", "")
            if not dev_id or not isinstance(d, dict):
                continue   # skip malformed entries
            result.append(BambuDevice(
                dev_id=dev_id,
                name=d.get("name", "Unknown"),
                dev_model_name=d.get("dev_model_name", ""),
                dev_product_name=d.get("dev_product_name", d.get("dev_model_name", "")),
                dev_access_code=access_code,
                online=bool(d.get("online", False)),
            ))
        except Exception:
            pass
    return result
