"""
Bambu Farm Monitor — FastAPI backend.

Responsibilities:
  - Persist printer configs via SQLite (database.py)
  - Bridge printer MQTT streams to WebSocket clients (mqtt_manager.py)
  - Serve print thumbnails fetched over implicit FTPS from the printer SD card
  - Proxy light/print-control commands back to printers via MQTT
  - Register printer RTSP streams with go2rtc for WebRTC camera viewing
  - Track print history and broadcast lifecycle events over WebSocket
  - Session auth via httpOnly JWT cookies (auth.py)
  - Bambu cloud account integration (bambu_cloud.py)
"""

import asyncio
import logging
import os
import secrets
from contextlib import asynccontextmanager, suppress
from typing import Annotated, Set

import httpx
from fastapi import (
    APIRouter, Depends, FastAPI, HTTPException,
    Request, Response, WebSocket, WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response as FastAPIResponse

import auth
import bambu_cloud
import database as db
import ftps
import rate_limiter
import thumbnail
from models import (
    AdminPasswordReset, AlertDismiss, BambuCloudDevicesRequest,
    BambuCloudLoginRequest, BambuCloudVerifyRequest,
    LightControl, PasswordChange, Printer, PrinterType, PrinterTypeCreate,
    PrintControl, PrinterCreate, PrinterUpdate,
    PrinterStatus, SettingsUpdate, UserCreate, UserLogin,
)
from mqtt_manager import MQTTManager

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
GO2RTC_URL = os.getenv("GO2RTC_URL", "http://go2rtc:1984")

# How often to re-check go2rtc's streams against the database.  0 disables the
# background loop (the test suite sets this, and drives _go2rtc_reconcile
# directly instead of waiting on a timer).
GO2RTC_RECONCILE_SECONDS = int(os.getenv("GO2RTC_RECONCILE_SECONDS", "60"))

# ---------------------------------------------------------------------------
# In-memory state
# ---------------------------------------------------------------------------
ws_clients: Set[WebSocket] = set()
mqtt_manager: MQTTManager | None = None
status_cache: dict[str, dict] = {}

# Maps printer_id → active PrintJob.id while a print is running.
_print_sessions: dict[str, str] = {}


# ---------------------------------------------------------------------------
# go2rtc integration
# ---------------------------------------------------------------------------

# go2rtc (1.9.14) cannot patch a stream key it loaded from its own config file:
# the stream *is* applied in memory, but writing the config back fails with
# 400 "yaml: line N: did not find expected key".  Every restart therefore logs
# one of these per pre-existing printer.  Recognising it keeps that expected
# noise out of the warning stream — see DEPLOY.md for the full write-up.
_GO2RTC_WRITEBACK_BUG = "did not find expected key"


def _go2rtc_stream_name(printer_id: str) -> str:
    """go2rtc stream key for a printer.  CameraModal.jsx opens the same name."""
    return f"bambu_{printer_id}"


def _go2rtc_src(printer: Printer) -> str:
    """RTSPS source URL for a printer's camera."""
    return f"rtsps://bblp:{printer.access_code}@{printer.ip}:322/streaming/live/1"


def _is_writeback_bug(exc: Exception) -> bool:
    """True for the known go2rtc config write-back failure (stream still applied)."""
    resp = getattr(exc, "response", None)
    if resp is None or getattr(resp, "status_code", None) != 400:
        return False
    try:
        return _GO2RTC_WRITEBACK_BUG in resp.text
    except Exception:
        return False


async def _go2rtc_put(printer: Printer) -> None:
    """Register or update a printer's RTSPS stream in go2rtc.

    go2rtc takes the stream source from the *query string* (?src=), never from
    the request body.  Its handler short-circuits on an empty ?src= and returns
    the full stream list with 200 OK, so a body-only request silently creates
    nothing while still looking like a success.  Both params are required:
        PUT /api/streams?name=<stream name>&src=<rtsps url>
    """
    name = _go2rtc_stream_name(printer.id)
    url = _go2rtc_src(printer)
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.put(
                f"{GO2RTC_URL}/api/streams",
                params={"name": name, "src": url},
            )
            resp.raise_for_status()
        logger.info(f"go2rtc: registered {printer.name!r} as {name}")
    except Exception as exc:
        if _is_writeback_bug(exc):
            logger.info(
                f"go2rtc: applied {printer.name!r} as {name}; config write-back "
                f"skipped (known go2rtc limitation, stream is live)"
            )
        else:
            logger.warning(f"go2rtc: could not register {printer.name!r}: {exc}")


async def _go2rtc_delete(printer_id: str) -> None:
    """Remove a printer's stream from go2rtc.

    DELETE identifies the stream by ?src= — go2rtc uses that param as the key
    into its stream map here, so ?name= is ignored and deletes nothing.
    """
    name = _go2rtc_stream_name(printer_id)
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.delete(
                f"{GO2RTC_URL}/api/streams",
                params={"src": name},
            )
            resp.raise_for_status()
        logger.info(f"go2rtc: removed {name}")
    except Exception as exc:
        logger.warning(f"go2rtc: could not remove {name}: {exc}")


async def _go2rtc_live_streams() -> dict[str, str] | None:
    """Map of stream name → first producer URL, as go2rtc currently holds it.

    Returns None when go2rtc could not be reached, so callers can tell "go2rtc
    has no streams" (which needs repair) apart from "go2rtc did not answer"
    (which does not — re-registering into the void achieves nothing).
    """
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get(f"{GO2RTC_URL}/api/streams")
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.debug(f"go2rtc: could not list streams: {exc}")
        return None

    live: dict[str, str] = {}
    for name, info in (data or {}).items():
        producers = (info or {}).get("producers") or []
        live[name] = (producers[0] or {}).get("url", "") if producers else ""
    return live


async def _go2rtc_reconcile() -> int:
    """Re-register any printer whose stream is missing or wrong in go2rtc.

    The database is the source of truth.  Two things put go2rtc out of step
    with it, and registering only at startup fixes neither:

      - go2rtc restarting on its own reloads whatever is in its config file,
        losing every stream the backend added since.
      - go2rtc cannot write an updated URL back to that file for a stream it
        loaded from disk, so a printer whose IP or access code changed keeps
        the stale URL there and picks it up on the next go2rtc restart.

    Re-registering repairs both, because the PUT is applied in memory even
    when the config write-back fails.  Returns the number of streams repaired.
    """
    live = await _go2rtc_live_streams()
    if live is None:
        return 0

    repaired = 0
    for printer in db.get_all_printers():
        if live.get(_go2rtc_stream_name(printer.id)) != _go2rtc_src(printer):
            await _go2rtc_put(printer)
            repaired += 1

    if repaired:
        logger.info(f"go2rtc: reconciled {repaired} stream(s) against the database")
    return repaired


async def _go2rtc_reconcile_loop(interval: int) -> None:
    """Run _go2rtc_reconcile forever, surviving individual failures."""
    while True:
        await asyncio.sleep(interval)
        try:
            await _go2rtc_reconcile()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(f"go2rtc: reconcile pass failed: {exc}")


# ---------------------------------------------------------------------------
# WebSocket broadcast
# ---------------------------------------------------------------------------

async def broadcast(msg: dict) -> None:
    """Send a JSON message to all connected WebSocket clients."""
    dead: Set[WebSocket] = set()
    for ws in ws_clients:
        try:
            await ws.send_json(msg)
        except Exception:
            dead.add(ws)
    ws_clients.difference_update(dead)


# ---------------------------------------------------------------------------
# MQTT status callback & print lifecycle tracking
# ---------------------------------------------------------------------------

def on_printer_status(status: PrinterStatus) -> None:
    """Handle a status update from the MQTT manager."""
    prev = status_cache.get(status.printer_id, {})
    prev_state = prev.get("gcode_state", "OFFLINE")
    curr_state = status.gcode_state
    loop = app.state.loop

    if prev.get("current_file") != status.current_file:
        thumbnail.cache.pop(status.printer_id, None)

    if prev_state != "RUNNING" and curr_state == "RUNNING":
        printer = db.get_printer(status.printer_id)
        name = printer.name if printer else status.printer_id
        job = db.start_print_job(status.printer_id, name, status.current_file)
        _print_sessions[status.printer_id] = job.id
        asyncio.run_coroutine_threadsafe(
            broadcast({"type": "print_event", "data": {
                "event": "started",
                "printer_id": status.printer_id,
                "printer_name": name,
                "file_name": status.current_file,
            }}),
            loop,
        )

    elif prev_state == "RUNNING" and curr_state in ("FINISH", "FAILED", "IDLE"):
        job_id = _print_sessions.pop(status.printer_id, None)
        final = (
            "completed" if curr_state == "FINISH"
            else "failed" if curr_state == "FAILED"
            else "cancelled"
        )
        if job_id:
            db.finish_print_job(job_id, final)
        printer = db.get_printer(status.printer_id)
        name = printer.name if printer else status.printer_id
        asyncio.run_coroutine_threadsafe(
            broadcast({"type": "print_event", "data": {
                "event": final,
                "printer_id": status.printer_id,
                "printer_name": name,
                "file_name": prev.get("current_file", ""),
            }}),
            loop,
        )

    status_cache[status.printer_id] = status.model_dump()
    asyncio.run_coroutine_threadsafe(
        broadcast({"type": "status_update", "data": status.model_dump()}),
        loop,
    )


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.loop = asyncio.get_running_loop()
    db.init_db()
    db.abandon_running_jobs()

    # Ensure at least one admin user exists on first boot.
    if db.count_users() == 0:
        username = os.getenv("APP_USERNAME", "admin")
        password = os.getenv("APP_PASSWORD", "")
        if not password:
            password = secrets.token_urlsafe(14)
            logger.warning("=" * 60)
            logger.warning("  FIRST-RUN ADMIN CREDENTIALS")
            logger.warning(f"  Username : {username}")
            logger.warning(f"  Password : {password}")
            logger.warning("  Set APP_PASSWORD in your .env to use a fixed password.")
            logger.warning("=" * 60)
        db.create_user(username, auth.hash_password(password))

    global mqtt_manager
    mqtt_manager = MQTTManager(on_printer_status)

    for printer in db.get_all_printers():
        mqtt_manager.add_printer(printer)
        await _go2rtc_put(printer)

    # Keep go2rtc in step with the database for as long as we are running;
    # registering once at startup leaves it stale if go2rtc restarts alone.
    reconcile_task: asyncio.Task | None = None
    if GO2RTC_RECONCILE_SECONDS > 0:
        reconcile_task = asyncio.create_task(
            _go2rtc_reconcile_loop(GO2RTC_RECONCILE_SECONDS)
        )

    yield

    if reconcile_task:
        reconcile_task.cancel()
        with suppress(asyncio.CancelledError):
            await reconcile_task

    if mqtt_manager:
        mqtt_manager.stop_all()


app = FastAPI(title="Bambu Farm Monitor", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Health check  (public — no auth required for Docker/load-balancer probes)
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Auth endpoints  (public — no require_auth)
# ---------------------------------------------------------------------------

def _client_ip(request: Request) -> str:
    """Extract the real client IP, preferring the header nginx sets."""
    return (
        request.headers.get("X-Real-IP")
        or request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or (request.client.host if request.client else "unknown")
    )


@app.post("/api/auth/login")
def login(data: UserLogin, request: Request, response: Response):
    ip = _client_ip(request)

    blocked, retry_after = rate_limiter.limiter.is_blocked(ip)
    if blocked:
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed login attempts. Try again in {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
        )

    user = db.get_user(data.username)
    if not user or not auth.verify_password(data.password, user.hashed_password):
        rate_limiter.limiter.record_failure(ip)
        blocked, retry_after = rate_limiter.limiter.is_blocked(ip)
        if blocked:
            logger.warning(f"Login rate limit triggered for IP {ip} after {rate_limiter.limiter.failure_count(ip)} failures")
        raise HTTPException(status_code=401, detail="Invalid username or password")

    rate_limiter.limiter.record_success(ip)
    auth.set_auth_cookie(response, user.username)
    return {"username": user.username, "role": user.role}


@app.post("/api/auth/logout")
def logout(response: Response):
    auth.clear_auth_cookie(response)
    return {"ok": True}


@app.get("/api/auth/me")
def me(current_user=Depends(auth.require_auth)):
    return {"username": current_user.username, "role": current_user.role}


# ---------------------------------------------------------------------------
# Protected API router
# All routes below require a valid session cookie.
# ---------------------------------------------------------------------------

router = APIRouter(dependencies=[Depends(auth.require_auth)])


# ── MAC address lookup ────────────────────────────────────────────────────────

def _lookup_mac(ip: str) -> str | None:
    """Return the MAC address for a LAN IP by reading the host ARP table.

    /host_arp is the Pi host's /proc/net/arp bind-mounted read-only into the
    container.  Format per line:
        IP address  HW type  Flags  HW address           Mask  Device
        192.168.1.100  0x1    0x2    aa:bb:cc:dd:ee:ff    *     wlan0
    """
    try:
        with open("/host_arp") as f:
            for line in f:
                parts = line.split()
                if (
                    len(parts) >= 4
                    and parts[0] == ip
                    and parts[3] != "00:00:00:00:00:00"
                ):
                    return parts[3].upper()
    except Exception:
        pass
    return None


def _enrich(p) -> dict:
    """Return a printer dict with mac_address appended."""
    data = p.model_dump()
    data["mac_address"] = _lookup_mac(p.ip)
    return data


def get_printer_or_404(printer_id: str) -> Printer:
    """Resolve a {printer_id} path param, 404ing if there is no such printer.

    Used as a dependency so the lookup-and-404 does not have to be repeated —
    and cannot be forgotten — in every per-printer route.
    """
    p = db.get_printer(printer_id)
    if not p:
        raise HTTPException(status_code=404, detail="Printer not found")
    return p


# Annotated alias so routes read `printer: PrinterDep` instead of carrying a
# Depends(...) default, which keeps them free of B008 noqa comments.
PrinterDep = Annotated[Printer, Depends(get_printer_or_404)]


# ── Printer CRUD ─────────────────────────────────────────────────────────────

@router.get("/api/printers")
def list_printers():
    return [_enrich(p) for p in db.get_all_printers()]


@router.post("/api/printers", status_code=201)
async def add_printer(data: PrinterCreate):
    printer = Printer(**data.model_dump())
    saved = db.create_printer(printer)
    mqtt_manager.add_printer(saved)
    await _go2rtc_put(saved)
    enriched = _enrich(saved)
    await broadcast({"type": "printers_update", "data": {"action": "add", "printer": enriched}})
    return enriched


@router.get("/api/printers/{printer_id}")
def get_printer(p: PrinterDep):
    return _enrich(p)


@router.patch("/api/printers/{printer_id}")
async def update_printer(printer_id: str, data: PrinterUpdate):
    updates = {k: v for k, v in data.model_dump().items() if v is not None}
    p = db.update_printer(printer_id, updates)
    if not p:
        raise HTTPException(status_code=404, detail="Printer not found")
    mqtt_manager.update_printer(p)
    await _go2rtc_put(p)
    enriched = _enrich(p)
    await broadcast({"type": "printers_update", "data": {"action": "update", "printer": enriched}})
    return enriched


@router.delete("/api/printers/{printer_id}", status_code=204)
async def delete_printer(printer_id: str):
    success = db.delete_printer(printer_id)
    if not success:
        raise HTTPException(status_code=404, detail="Printer not found")
    mqtt_manager.remove_printer(printer_id)
    await _go2rtc_delete(printer_id)
    status_cache.pop(printer_id, None)
    await broadcast({"type": "printers_update", "data": {"action": "delete", "printer_id": printer_id}})


# ── Printer types ────────────────────────────────────────────────────────────

@router.get("/api/printer-types")
def list_printer_types():
    return db.get_all_printer_types()


@router.post("/api/printer-types", status_code=201)
def create_printer_type(data: PrinterTypeCreate):
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Printer type name cannot be empty.")
    if len(name) > 20:
        raise HTTPException(status_code=422, detail="Printer type name must be 20 characters or fewer.")
    existing = db.get_printer_type(name)
    if existing:
        raise HTTPException(status_code=409, detail=f"Printer type '{name}' already exists.")
    pt = PrinterType(
        name=name,
        lan_mode_default=data.lan_mode_default,
        timelapse_support=data.timelapse_support,
        camera_capable=data.camera_capable,
    )
    return db.create_printer_type(pt)


@router.delete("/api/printer-types/{name}", status_code=204)
def delete_printer_type(name: str):
    try:
        found = db.delete_printer_type(name)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if not found:
        raise HTTPException(status_code=404, detail="Printer type not found.")


# ── Settings ─────────────────────────────────────────────────────────────────

@router.get("/api/settings")
def get_settings_endpoint():
    return db.get_settings()


@router.patch("/api/settings")
async def update_settings(data: SettingsUpdate):
    if data.farm_name is not None:
        db.set_setting("farm_name", data.farm_name)
    settings = db.get_settings()
    await broadcast({"type": "settings_update", "data": settings})
    return settings


# ── Account management ───────────────────────────────────────────────────────

@router.post("/api/auth/change-password")
def change_password(data: PasswordChange, current_user=Depends(auth.require_auth)):  # noqa: B008
    if not auth.verify_password(data.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if len(data.new_password) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters")
    db.update_user_password(current_user.username, auth.hash_password(data.new_password))
    return {"ok": True}


# ── User management (admin) ───────────────────────────────────────────────────

def _require_admin(current_user=Depends(auth.require_auth)):  # noqa: B008
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return current_user


@router.get("/api/users")
def list_users(current_user=Depends(_require_admin)):  # noqa: B008
    return [{"username": u.username, "role": u.role} for u in db.list_users()]


@router.post("/api/users", status_code=201)
def create_user(data: UserCreate, current_user=Depends(_require_admin)):  # noqa: B008
    if db.get_user(data.username):
        raise HTTPException(status_code=400, detail="Username already taken")
    if len(data.username.strip()) < 1:
        raise HTTPException(status_code=400, detail="Username cannot be empty")
    if len(data.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    if data.role not in ("admin", "viewer"):
        raise HTTPException(status_code=400, detail="Role must be 'admin' or 'viewer'")
    user = db.create_user(data.username.strip(), auth.hash_password(data.password), data.role)
    return {"username": user.username, "role": user.role}


@router.delete("/api/users/{username}", status_code=204)
def delete_user(username: str, current_user=Depends(_require_admin)):  # noqa: B008
    if username == current_user.username:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")
    target = db.get_user(username)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    # Protect the last admin
    if target.role == "admin":
        admin_count = sum(1 for u in db.list_users() if u.role == "admin")
        if admin_count <= 1:
            raise HTTPException(status_code=400, detail="Cannot delete the last admin account")
    db.delete_user(username)


@router.patch("/api/users/{username}/password")
def admin_reset_password(username: str, data: AdminPasswordReset, current_user=Depends(_require_admin)):  # noqa: B008
    if not db.get_user(username):
        raise HTTPException(status_code=404, detail="User not found")
    if len(data.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    db.update_user_password(username, auth.hash_password(data.new_password))
    return {"ok": True}


# ── Thumbnails ───────────────────────────────────────────────────────────────

@router.get("/api/printers/{printer_id}/thumbnail")
async def get_thumbnail(printer_id: str, p: PrinterDep):

    st = status_cache.get(printer_id, {})
    cover   = st.get("cover_file", "")
    gcode   = st.get("gcode_file", "")
    subtask = st.get("current_file", "")

    if not (cover or gcode or subtask):
        raise HTTPException(status_code=404, detail="No print file available")

    data = await asyncio.get_running_loop().run_in_executor(
        None, thumbnail.fetch_sync, printer_id, p.ip, p.access_code, cover, gcode, subtask
    )

    if not data and p.lan_mode:
        data = await thumbnail.snapshot_from_camera(printer_id)
        if data:
            thumbnail.cache[printer_id] = data

    if not data:
        raise HTTPException(status_code=404, detail="Thumbnail unavailable")

    content_type = "image/png" if data[:4] == b"\x89PNG" else "image/jpeg"
    return FastAPIResponse(content=data, media_type=content_type)


@router.get("/api/printers/{printer_id}/thumbnail/debug")
async def debug_thumbnail(printer_id: str, p: PrinterDep):

    st = status_cache.get(printer_id, {})
    return {
        "printer_ip": p.ip,
        "current_file_subtask": st.get("current_file") or None,
        "cover_file_from_mqtt":  st.get("cover_file") or None,
        "gcode_file_from_mqtt":  st.get("gcode_file") or None,
        "gcode_state":           st.get("gcode_state") or None,
        "sd_3mf_files": await asyncio.get_running_loop().run_in_executor(
            None, thumbnail._list_3mf, p.ip, p.access_code
        ),
    }


# ── Print controls ───────────────────────────────────────────────────────────

@router.post("/api/printers/{printer_id}/control")
async def control_print(printer_id: str, p: PrinterDep, data: PrintControl):

    action = data.action.lower()
    if action not in ("pause", "resume", "stop"):
        raise HTTPException(status_code=400, detail="action must be pause | resume | stop")

    payload = {"print": {"sequence_id": "2005", "command": action, "param": ""}}
    if not mqtt_manager.publish(printer_id, payload):
        raise HTTPException(status_code=503, detail="MQTT not connected")
    return {"ok": True, "action": action}


@router.post("/api/printers/{printer_id}/light")
async def control_light(printer_id: str, p: PrinterDep, data: LightControl):

    mode = data.mode.lower()
    if mode not in ("on", "off"):
        raise HTTPException(status_code=400, detail="mode must be on | off")

    payload = {
        "system": {
            "sequence_id": "2005",
            "command": "ledctrl",
            "led_node": "chamber_light",
            "led_mode": mode,
            "led_on_time": 500,
            "led_off_time": 500,
            "loop_times": 1,
            "interval_time": 1000,
        }
    }
    if not mqtt_manager.publish(printer_id, payload):
        raise HTTPException(status_code=503, detail="MQTT not connected")
    return {"ok": True, "mode": mode}


# ── Dismissed HMS alerts ─────────────────────────────────────────────────────

@router.get("/api/printers/{printer_id}/dismissed-alerts")
def list_dismissed_alerts(printer_id: str):
    return {"dismissed": db.get_dismissed_alerts(printer_id)}


@router.post("/api/printers/{printer_id}/dismissed-alerts", status_code=201)
async def dismiss_alert(printer_id: str, p: PrinterDep, data: AlertDismiss):
    db.dismiss_alert(printer_id, data.hms_code)
    dismissed = db.get_dismissed_alerts(printer_id)
    await broadcast({
        "type": "dismissed_alerts_update",
        "data": {"printer_id": printer_id, "dismissed": dismissed},
    })
    return {"dismissed": dismissed}


@router.delete("/api/printers/{printer_id}/dismissed-alerts/{hms_code}", status_code=200)
async def undismiss_alert(printer_id: str, p: PrinterDep, hms_code: str):
    db.undismiss_alert(printer_id, hms_code)
    dismissed = db.get_dismissed_alerts(printer_id)
    await broadcast({
        "type": "dismissed_alerts_update",
        "data": {"printer_id": printer_id, "dismissed": dismissed},
    })
    return {"dismissed": dismissed}


# ── Timelapses ───────────────────────────────────────────────────────────────

def _require_timelapse_support(p) -> None:
    """Raise 404 if the printer model doesn't support timelapse retrieval."""
    if not db.printer_type_timelapse_supported(p.model):
        raise HTTPException(
            status_code=404,
            detail=f"Timelapse retrieval is not supported for {p.model}",
        )


@router.get("/api/printers/{printer_id}/timelapses")
async def list_timelapses(p: PrinterDep):
    _require_timelapse_support(p)

    def _list() -> list[str]:
        entries = ftps.list_dir(p.ip, p.access_code, "/timelapse") or []
        files = [
            e.split("/")[-1] if "/" in e else e
            for e in entries
            if e.lower().endswith((".mp4", ".avi", ".mov"))
        ]
        return sorted(files, reverse=True)[:3]

    files = await asyncio.get_running_loop().run_in_executor(None, _list)
    return {"files": files}


@router.get("/api/printers/{printer_id}/timelapses/{filename}/thumb")
async def timelapse_thumb(printer_id: str, filename: str):
    if "/" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    cache_key = f"{printer_id}:{filename}"
    if cache_key in thumbnail.cache:
        return FastAPIResponse(content=thumbnail.cache[cache_key], media_type="image/jpeg")

    # Looked up here rather than via the PrinterDep dependency on purpose: a
    # dependency runs before the handler, so it would turn the cache hit above
    # into a database read on every request.
    p = db.get_printer(printer_id)
    if not p:
        raise HTTPException(status_code=404, detail="Printer not found")
    _require_timelapse_support(p)

    def _make_thumb() -> bytes | None:
        partial = ftps.download_partial(p.ip, p.access_code, f"/timelapse/{filename}")
        return ftps.extract_video_frame(partial) if partial else None

    jpeg = await asyncio.get_running_loop().run_in_executor(None, _make_thumb)
    if not jpeg:
        raise HTTPException(status_code=404, detail="Thumbnail unavailable")

    thumbnail.cache[cache_key] = jpeg
    return FastAPIResponse(content=jpeg, media_type="image/jpeg")


@router.get("/api/printers/{printer_id}/timelapses/{filename}")
async def download_timelapse(p: PrinterDep, filename: str):
    _require_timelapse_support(p)
    if "/" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    data = await asyncio.get_running_loop().run_in_executor(
        None, ftps.download, p.ip, p.access_code, f"/timelapse/{filename}", 120
    )
    if not data:
        raise HTTPException(status_code=404, detail="File not found")

    return FastAPIResponse(
        content=data,
        media_type="video/mp4",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


# ── History & status ─────────────────────────────────────────────────────────

@router.get("/api/history")
def get_history():
    return [j.model_dump() for j in db.get_print_history()]


@router.get("/api/status")
def get_all_statuses():
    return status_cache


@router.get("/api/status/{printer_id}")
def get_printer_status(printer_id: str):
    if printer_id in status_cache:
        return status_cache[printer_id]
    raise HTTPException(status_code=404, detail="Status not found")


# ── Bambu cloud integration ───────────────────────────────────────────────────

@router.post("/api/bambu-cloud/login")
def bambu_cloud_login(data: BambuCloudLoginRequest):
    """Authenticate with Bambu cloud. Returns a token or a 2FA challenge."""
    result = bambu_cloud.login(data.email, data.password)
    if result.error:
        raise HTTPException(status_code=400, detail=result.error)
    return {
        "needs_2fa": result.needs_2fa,
        "tfa_key": result.tfa_key,
        "token": result.token,
    }


@router.post("/api/bambu-cloud/verify")
def bambu_cloud_verify(data: BambuCloudVerifyRequest):
    """Submit 2FA verification code and get an access token."""
    result = bambu_cloud.verify_2fa(data.tfa_key, data.code, email=data.email)
    if result.error:
        raise HTTPException(status_code=422, detail=result.error)
    return {"token": result.token}


@router.post("/api/bambu-cloud/devices")
def bambu_cloud_devices(data: BambuCloudDevicesRequest):
    """Fetch devices for an authenticated Bambu cloud account."""
    try:
        devices = bambu_cloud.get_devices(data.token)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "devices": [
            {
                "serial":       d.dev_id,
                "name":         d.name,
                "model":        d.model_label,
                "access_code":  d.dev_access_code,
                "product_name": d.dev_product_name,
                "online":       d.online,
                "lan_mode":     d.lan_mode_default,
            }
            for d in devices
        ]
    }


# ---------------------------------------------------------------------------
# WebSocket  (auth via cookie; no APIRouter dependency injection for WS)
# ---------------------------------------------------------------------------

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    # Validate session cookie before accepting the connection.
    token = websocket.cookies.get(auth.COOKIE_NAME)
    if not token or not auth.decode_token(token):
        await websocket.close(code=4001)
        return

    await websocket.accept()
    ws_clients.add(websocket)
    try:
        await websocket.send_json({
            "type": "init",
            "data": {
                "printers":         [_enrich(p) for p in db.get_all_printers()],
                "statuses":         status_cache,
                "settings":         db.get_settings(),
                "dismissed_alerts": db.get_all_dismissed_alerts(),
            },
        })
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        ws_clients.discard(websocket)


# ---------------------------------------------------------------------------
# Register protected router
# ---------------------------------------------------------------------------

app.include_router(router)
