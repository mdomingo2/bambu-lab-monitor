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
2. If needs_2fa, client calls verify(tfa_key, code, email)
   → {token: "eyJ..."}
3. client calls get_devices(token)
   → list[BambuDevice]

Session persistence
-------------------
When 2FA is required the httpx.Client from the login call is kept alive in
_tfa_sessions[email] so that verify_2fa() can reuse the SAME client (and
therefore the same cookie jar / TCP connection).  This avoids the issue of
trying to serialize and re-inject Cloudflare cookies into a brand-new client.
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
# Headers required by Bambu's API
# Mirrors what OrcaSlicer / bambu_network_agent sends so Bambu doesn't block
# the request as an unknown client.
# ---------------------------------------------------------------------------

_AUTH_HEADERS = {
    "User-Agent":           "bambu_network_agent/01.09.05.04",
    "X-BBL-Client-Name":    "OrcaSlicer",
    "X-BBL-Client-Version": "01.09.05.04",
    "X-BBL-Client-OS-Type": "linux",
    "X-BBL-Language":       "en",
    "X-BBL-App-Version":    "01.09.05.04",
    "X-BBL-Timezone":       "UTC",
    "Accept":               "application/json",
    "Accept-Language":      "en",
    "Content-Type":         "application/json",
    "Referer":              "https://bambulab.com/",
}

_API_HEADERS = {
    "User-Agent":           "bambu_network_agent/01.09.05.04",
    "X-BBL-Client-Name":    "OrcaSlicer",
    "X-BBL-Client-Version": "01.09.05.04",
    "Accept":               "application/json",
}

# ---------------------------------------------------------------------------
# In-memory 2FA session store
# Maps email → live httpx.Client that still holds the login cookie jar.
# Cleaned up after verify_2fa() completes (success or failure).
# ---------------------------------------------------------------------------

_tfa_sessions: dict[str, httpx.Client] = {}

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
    session_cookies: dict = {}       # kept for API compat; not used internally anymore


# ---------------------------------------------------------------------------
# API functions
# ---------------------------------------------------------------------------

def login(email: str, password: str) -> BambuLoginResult:
    """Authenticate with Bambu cloud using email + password.

    If 2FA is required the live httpx.Client is stored in _tfa_sessions[email]
    so that verify_2fa() can reuse it with the same cookie jar.
    """
    # Close any leftover session for this email before starting fresh.
    _close_tfa_session(email)

    client = httpx.Client(
        headers=_AUTH_HEADERS,
        timeout=_TIMEOUT,
        follow_redirects=True,
    )
    try:
        r = client.post(
            _AUTH_URL,
            json={"account": email, "password": password, "apiError": ""},
        )
        logger.info("Bambu login HTTP %s", r.status_code)
        logger.info("Bambu login response body: %s", r.text[:500])
        logger.info("Bambu login cookies: %s", list(dict(client.cookies).keys()))
        logger.info(
            "Bambu login Set-Cookie headers: %s",
            r.headers.get_list("set-cookie") if hasattr(r.headers, "get_list") else r.headers.get("set-cookie"),
        )
        r.raise_for_status()
        body = r.json()
    except httpx.HTTPStatusError as exc:
        client.close()
        logger.warning("Bambu login error %s: %s", exc.response.status_code, exc.response.text[:300])
        return BambuLoginResult(
            needs_2fa=False,
            error=f"Bambu cloud returned {exc.response.status_code}",
        )
    except Exception as exc:
        client.close()
        return BambuLoginResult(needs_2fa=False, error=str(exc))

    # 2FA required — keep the client alive so verify_2fa() reuses the session
    if body.get("loginType") == "verifyCode":
        tfa_key = body.get("tfaKey") or ""
        logger.info(
            "Bambu 2FA required. tfaKey=%r, cookies=%s",
            tfa_key, list(dict(client.cookies).keys()),
        )
        _tfa_sessions[email] = client   # hand off ownership; NOT closed here
        return BambuLoginResult(needs_2fa=True, tfa_key=tfa_key)

    # No 2FA — close the client, we have the token
    token = body.get("accessToken") or body.get("access_token")
    client.close()
    if token:
        return BambuLoginResult(needs_2fa=False, token=token)

    logger.warning("Bambu login unexpected body keys: %s", list(body.keys()))
    return BambuLoginResult(
        needs_2fa=False,
        error=body.get("error") or body.get("message") or "Unexpected response from Bambu cloud",
    )


def verify_2fa(
    tfa_key: str,
    code: str,
    session_cookies: dict | None = None,   # kept for API compat; ignored
    email: str = "",
) -> BambuLoginResult:
    """Submit the 2FA verification code and get an access token.

    Reuses the live httpx.Client stored by login() so the cookie jar is intact.
    Falls back to a fresh client if no stored session exists (e.g. after a
    server restart).
    """
    client = _tfa_sessions.pop(email, None) if email else None
    owns_client = client is None
    if client is None:
        logger.warning("Bambu verify_2fa: no stored session for %r, creating fresh client", email)
        client = httpx.Client(
            headers=_AUTH_HEADERS,
            timeout=_TIMEOUT,
            cookies=session_cookies or {},
        )

    body: dict = {"tfaKey": tfa_key, "tfaCode": code, "apiError": ""}
    if email:
        body["account"] = email

    logger.info(
        "Bambu verify_2fa: email=%r, code=%r, cookie_keys=%s, reused_session=%s",
        email, code, list(dict(client.cookies).keys()), not owns_client,
    )

    try:
        r = client.post(_TFA_URL, json=body)
        logger.info("Bambu verify HTTP %s body: %s", r.status_code, r.text[:500])
        r.raise_for_status()
        resp_body = r.json()
    except httpx.HTTPStatusError as exc:
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
            needs_2fa=True,
            tfa_key=tfa_key,
            error=f"Verification failed: {detail}",
        )
    except Exception as exc:
        return BambuLoginResult(needs_2fa=True, tfa_key=tfa_key, error=str(exc))
    finally:
        client.close()

    token = resp_body.get("accessToken") or resp_body.get("access_token")
    if token:
        return BambuLoginResult(needs_2fa=False, token=token)

    return BambuLoginResult(
        needs_2fa=True,
        tfa_key=tfa_key,
        error=resp_body.get("error") or resp_body.get("message") or "2FA verification failed",
    )


def _close_tfa_session(email: str) -> None:
    """Close and discard any stored 2FA session for this email."""
    client = _tfa_sessions.pop(email, None)
    if client is not None:
        try:
            client.close()
        except Exception:
            pass


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
