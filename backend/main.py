"""
Bambu Farm Monitor — FastAPI backend.

Responsibilities:
  - Persist printer configs via SQLite (database.py)
  - Bridge printer MQTT streams to WebSocket clients (mqtt_manager.py)
  - Serve print thumbnails fetched over implicit FTPS from the printer SD card
  - Proxy light/print-control commands back to printers via MQTT
  - Register printer RTSP streams with go2rtc for WebRTC camera viewing
  - Track print history and broadcast lifecycle events over WebSocket
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Set

import httpx
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

import database as db
import ftps
import thumbnail
from models import (
    Printer, PrinterCreate, PrinterUpdate,
    PrinterStatus, PrintControl, LightControl, SettingsUpdate, AlertDismiss,
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

async def _go2rtc_put(printer: Printer) -> None:
    """Register or update a printer's RTSPS stream in go2rtc."""
    name = f"bambu_{printer.id}"
    url = f"rtsps://bblp:{printer.access_code}@{printer.ip}:322/streaming/live/1"
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            await client.put(f"{GO2RTC_URL}/api/streams?name={name}", content=url)
        logger.info(f"go2rtc: registered {printer.name!r} as {name}")
    except Exception as exc:
        logger.warning(f"go2rtc: could not register {printer.name!r}: {exc}")


async def _go2rtc_delete(printer_id: str) -> None:
    """Remove a printer's stream from go2rtc."""
    name = f"bambu_{printer_id}"
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            await client.delete(f"{GO2RTC_URL}/api/streams?name={name}")
        logger.info(f"go2rtc: removed {name}")
    except Exception as exc:
        logger.warning(f"go2rtc: could not remove {name}: {exc}")


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
    """Handle a status update from the MQTT manager.

    Detects print start / end transitions, writes history records, and
    broadcasts both lifecycle events and raw status updates to WS clients.
    Called from a background thread — uses run_coroutine_threadsafe.
    """
    prev = status_cache.get(status.printer_id, {})
    prev_state = prev.get("gcode_state", "OFFLINE")
    curr_state = status.gcode_state
    loop = app.state.loop

    # Clear thumbnail cache whenever the active file changes so the next
    # request always fetches a fresh image for the new job.
    if prev.get("current_file") != status.current_file:
        thumbnail.cache.pop(status.printer_id, None)

    # Print started
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

    # Print ended (any terminal state after RUNNING)
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

    global mqtt_manager
    mqtt_manager = MQTTManager(on_printer_status)

    for printer in db.get_all_printers():
        mqtt_manager.add_printer(printer)
        await _go2rtc_put(printer)

    yield

    if mqtt_manager:
        mqtt_manager.stop_all()


app = FastAPI(title="Bambu Farm Monitor", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Printer CRUD
# ---------------------------------------------------------------------------

@app.get("/api/printers")
def list_printers():
    return [p.model_dump() for p in db.get_all_printers()]


@app.post("/api/printers", status_code=201)
async def add_printer(data: PrinterCreate):
    printer = Printer(**data.model_dump())
    saved = db.create_printer(printer)
    mqtt_manager.add_printer(saved)
    await _go2rtc_put(saved)
    await broadcast({"type": "printers_update", "data": {"action": "add", "printer": saved.model_dump()}})
    return saved.model_dump()


@app.get("/api/printers/{printer_id}")
def get_printer(printer_id: str):
    p = db.get_printer(printer_id)
    if not p:
        raise HTTPException(status_code=404, detail="Printer not found")
    return p.model_dump()


@app.patch("/api/printers/{printer_id}")
async def update_printer(printer_id: str, data: PrinterUpdate):
    updates = {k: v for k, v in data.model_dump().items() if v is not None}
    p = db.update_printer(printer_id, updates)
    if not p:
        raise HTTPException(status_code=404, detail="Printer not found")
    mqtt_manager.update_printer(p)
    await _go2rtc_put(p)
    await broadcast({"type": "printers_update", "data": {"action": "update", "printer": p.model_dump()}})
    return p.model_dump()


@app.delete("/api/printers/{printer_id}", status_code=204)
async def delete_printer(printer_id: str):
    success = db.delete_printer(printer_id)
    if not success:
        raise HTTPException(status_code=404, detail="Printer not found")
    mqtt_manager.remove_printer(printer_id)
    await _go2rtc_delete(printer_id)
    status_cache.pop(printer_id, None)
    await broadcast({"type": "printers_update", "data": {"action": "delete", "printer_id": printer_id}})


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

@app.get("/api/settings")
def get_settings_endpoint():
    return db.get_settings()


@app.patch("/api/settings")
async def update_settings(data: SettingsUpdate):
    if data.farm_name is not None:
        db.set_setting("farm_name", data.farm_name)
    settings = db.get_settings()
    await broadcast({"type": "settings_update", "data": settings})
    return settings


# ---------------------------------------------------------------------------
# Thumbnails
# ---------------------------------------------------------------------------

@app.get("/api/printers/{printer_id}/thumbnail")
async def get_thumbnail(printer_id: str):
    p = db.get_printer(printer_id)
    if not p:
        raise HTTPException(status_code=404, detail="Printer not found")

    st = status_cache.get(printer_id, {})
    cover   = st.get("cover_file", "")
    gcode   = st.get("gcode_file", "")
    subtask = st.get("current_file", "")

    if not (cover or gcode or subtask):
        raise HTTPException(status_code=404, detail="No print file available")

    data = await asyncio.get_running_loop().run_in_executor(
        None, thumbnail.fetch_sync, printer_id, p.ip, p.access_code, cover, gcode, subtask
    )

    # FTPS thumbnail unavailable — fall back to a live camera snapshot for
    # printers that have LAN Mode enabled (go2rtc stream is reachable).
    if not data and p.lan_mode:
        data = await thumbnail.snapshot_from_camera(printer_id)
        if data:
            thumbnail.cache[printer_id] = data

    if not data:
        raise HTTPException(status_code=404, detail="Thumbnail unavailable")

    content_type = "image/png" if data[:4] == b"\x89PNG" else "image/jpeg"
    return Response(content=data, media_type=content_type)


@app.get("/api/printers/{printer_id}/thumbnail/debug")
async def debug_thumbnail(printer_id: str):
    """Diagnostic endpoint: returns MQTT state and FTPS directory listings."""
    p = db.get_printer(printer_id)
    if not p:
        raise HTTPException(status_code=404, detail="Printer not found")

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


# ---------------------------------------------------------------------------
# Print controls
# ---------------------------------------------------------------------------

@app.post("/api/printers/{printer_id}/control")
async def control_print(printer_id: str, data: PrintControl):
    p = db.get_printer(printer_id)
    if not p:
        raise HTTPException(status_code=404, detail="Printer not found")

    action = data.action.lower()
    if action not in ("pause", "resume", "stop"):
        raise HTTPException(status_code=400, detail="action must be pause | resume | stop")

    payload = {"print": {"sequence_id": "2005", "command": action, "param": ""}}
    if not mqtt_manager.publish(printer_id, payload):
        raise HTTPException(status_code=503, detail="MQTT not connected")
    return {"ok": True, "action": action}


@app.post("/api/printers/{printer_id}/light")
async def control_light(printer_id: str, data: LightControl):
    p = db.get_printer(printer_id)
    if not p:
        raise HTTPException(status_code=404, detail="Printer not found")

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


# ---------------------------------------------------------------------------
# Dismissed HMS alerts
# ---------------------------------------------------------------------------

@app.get("/api/printers/{printer_id}/dismissed-alerts")
def list_dismissed_alerts(printer_id: str):
    return {"dismissed": db.get_dismissed_alerts(printer_id)}


@app.post("/api/printers/{printer_id}/dismissed-alerts", status_code=201)
async def dismiss_alert(printer_id: str, data: AlertDismiss):
    p = db.get_printer(printer_id)
    if not p:
        raise HTTPException(status_code=404, detail="Printer not found")
    db.dismiss_alert(printer_id, data.hms_code)
    dismissed = db.get_dismissed_alerts(printer_id)
    await broadcast({
        "type": "dismissed_alerts_update",
        "data": {"printer_id": printer_id, "dismissed": dismissed},
    })
    return {"dismissed": dismissed}


@app.delete("/api/printers/{printer_id}/dismissed-alerts/{hms_code}", status_code=200)
async def undismiss_alert(printer_id: str, hms_code: str):
    p = db.get_printer(printer_id)
    if not p:
        raise HTTPException(status_code=404, detail="Printer not found")
    db.undismiss_alert(printer_id, hms_code)
    dismissed = db.get_dismissed_alerts(printer_id)
    await broadcast({
        "type": "dismissed_alerts_update",
        "data": {"printer_id": printer_id, "dismissed": dismissed},
    })
    return {"dismissed": dismissed}


# ---------------------------------------------------------------------------
# Timelapses
# ---------------------------------------------------------------------------

@app.get("/api/printers/{printer_id}/timelapses")
async def list_timelapses(printer_id: str):
    p = db.get_printer(printer_id)
    if not p:
        raise HTTPException(status_code=404, detail="Printer not found")

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


@app.get("/api/printers/{printer_id}/timelapses/{filename}/thumb")
async def timelapse_thumb(printer_id: str, filename: str):
    """Return a JPEG poster frame from the first 8 MB of the timelapse video."""
    if "/" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    cache_key = f"{printer_id}:{filename}"
    if cache_key in thumbnail.cache:
        return Response(content=thumbnail.cache[cache_key], media_type="image/jpeg")

    p = db.get_printer(printer_id)
    if not p:
        raise HTTPException(status_code=404, detail="Printer not found")

    def _make_thumb() -> bytes | None:
        partial = ftps.download_partial(p.ip, p.access_code, f"/timelapse/{filename}")
        return ftps.extract_video_frame(partial) if partial else None

    jpeg = await asyncio.get_running_loop().run_in_executor(None, _make_thumb)
    if not jpeg:
        raise HTTPException(status_code=404, detail="Thumbnail unavailable")

    thumbnail.cache[cache_key] = jpeg
    return Response(content=jpeg, media_type="image/jpeg")


@app.get("/api/printers/{printer_id}/timelapses/{filename}")
async def download_timelapse(printer_id: str, filename: str):
    p = db.get_printer(printer_id)
    if not p:
        raise HTTPException(status_code=404, detail="Printer not found")
    if "/" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    data = await asyncio.get_running_loop().run_in_executor(
        None, ftps.download, p.ip, p.access_code, f"/timelapse/{filename}", 120
    )
    if not data:
        raise HTTPException(status_code=404, detail="File not found")

    return Response(
        content=data,
        media_type="video/mp4",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# History & status
# ---------------------------------------------------------------------------

@app.get("/api/history")
def get_history():
    return [j.model_dump() for j in db.get_print_history()]


@app.get("/api/status")
def get_all_statuses():
    return status_cache


@app.get("/api/status/{printer_id}")
def get_printer_status(printer_id: str):
    if printer_id in status_cache:
        return status_cache[printer_id]
    raise HTTPException(status_code=404, detail="Status not found")


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Persistent WebSocket for real-time status and event updates.

    On connect, sends an 'init' payload with all printer configs, current
    statuses, and settings. Subsequent messages are broadcast by
    on_printer_status and the CRUD endpoints.
    """
    await websocket.accept()
    ws_clients.add(websocket)
    try:
        await websocket.send_json({
            "type": "init",
            "data": {
                "printers":         [p.model_dump() for p in db.get_all_printers()],
                "statuses":         status_cache,
                "settings":         db.get_settings(),
                "dismissed_alerts": db.get_all_dismissed_alerts(),
            },
        })
        while True:
            await websocket.receive_text()   # keep connection alive
    except WebSocketDisconnect:
        pass
    finally:
        ws_clients.discard(websocket)
