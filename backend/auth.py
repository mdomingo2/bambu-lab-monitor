"""
Authentication utilities for Bambu Farm Monitor.

Provides:
  - Password hashing via bcrypt (passlib)
  - JWT creation and validation via python-jose
  - FastAPI dependency `require_auth` that reads the httpOnly session cookie
  - `set_auth_cookie` / `clear_auth_cookie` helpers for login/logout responses

JWT secret is auto-generated on first use and persisted in the FarmSettings
table so it survives container restarts without requiring an env var.
Pass JWT_SECRET in your environment to pin a specific secret (useful for
multi-instance deployments or key rotation).
"""

import os
import secrets
import logging
from datetime import datetime, timedelta, timezone

from fastapi import Cookie, Depends, HTTPException, Response, status
from jose import JWTError, jwt
from passlib.context import CryptContext

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ALGORITHM = "HS256"
TOKEN_EXPIRE_DAYS = 30          # long-lived; users are on a private LAN
COOKIE_NAME = "bambu_session"

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ---------------------------------------------------------------------------
# Password helpers
# ---------------------------------------------------------------------------


def hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


# ---------------------------------------------------------------------------
# JWT secret — generated once and stored in FarmSettings
# ---------------------------------------------------------------------------

_cached_secret: str | None = None


def get_jwt_secret() -> str:
    """Return the JWT signing secret, creating one if it doesn't exist yet."""
    global _cached_secret
    if _cached_secret:
        return _cached_secret

    # env var always wins (allows key rotation without DB access)
    env_secret = os.getenv("JWT_SECRET", "")
    if env_secret:
        _cached_secret = env_secret
        return _cached_secret

    # Lazy import to avoid circular dependency (auth ← database ← models)
    import database as db  # noqa: PLC0415
    settings = db.get_settings()
    if "jwt_secret" in settings:
        _cached_secret = settings["jwt_secret"]
        return _cached_secret

    new_secret = secrets.token_hex(32)
    db.set_setting("jwt_secret", new_secret)
    logger.info("Generated new JWT signing secret")
    _cached_secret = new_secret
    return _cached_secret


# ---------------------------------------------------------------------------
# Token creation / validation
# ---------------------------------------------------------------------------


def create_access_token(username: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=TOKEN_EXPIRE_DAYS)
    return jwt.encode(
        {"sub": username, "exp": expire},
        get_jwt_secret(),
        algorithm=ALGORITHM,
    )


def decode_token(token: str) -> str | None:
    """Decode a JWT and return the username ('sub'), or None if invalid."""
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[ALGORITHM])
        return payload.get("sub")
    except JWTError:
        return None


# ---------------------------------------------------------------------------
# Cookie helpers (called by login/logout endpoints)
# ---------------------------------------------------------------------------


def set_auth_cookie(response: Response, username: str) -> None:
    token = create_access_token(username)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,          # JS cannot read this cookie
        samesite="lax",         # CSRF protection for normal browsing
        secure=False,           # nginx handles HTTPS; backend is on HTTP internally
        max_age=60 * 60 * 24 * TOKEN_EXPIRE_DAYS,
        path="/",
    )


def clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(key=COOKIE_NAME, path="/")


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------


def require_auth(bambu_session: str | None = Cookie(default=None)):
    """FastAPI dependency — raises 401 if the session cookie is missing/invalid.

    Returns the User ORM object for the authenticated user.
    Usage:
        @router.get("/api/printers")
        def list_printers(user = Depends(require_auth)):
            ...
    Or via APIRouter:
        router = APIRouter(dependencies=[Depends(require_auth)])
    """
    if not bambu_session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    username = decode_token(bambu_session)
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or invalid",
        )

    import database as db  # noqa: PLC0415
    user = db.get_user(username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    return user
