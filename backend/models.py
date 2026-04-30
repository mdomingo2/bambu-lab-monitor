"""
Data models shared across the backend.

SQLModel tables (persisted to SQLite):
  Printer       — printer configuration
  FarmSettings  — key/value farm-level settings
  PrintJob      — historical print job records
  DismissedAlert— user-dismissed HMS alert codes
  User          — local user account (scaffold for future auth)

Pydantic-only models (in-memory / API schema):
  PrinterStatus — live state from MQTT
  HMSAlert      — decoded Health Management System alert
  AMSTray       — single AMS filament slot
  AMSUnit       — AMS unit metadata (humidity, temp)
  PrinterCreate / PrinterUpdate / SettingsUpdate / PrintControl / LightControl
                — request body schemas
"""

from typing import Optional
from sqlmodel import Field, SQLModel
from pydantic import BaseModel
import uuid


# ---------------------------------------------------------------------------
# Persisted tables
# ---------------------------------------------------------------------------

class Printer(SQLModel, table=True):
    """A Bambu Lab printer registered with the farm."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    name: str
    model: str          # A1 | P1S | P2S | H2D
    ip: str
    serial: str
    access_code: str    # shown on printer screen under Settings → Network
    lan_mode: bool = Field(default=True)
    # lan_mode=True  → camera button is shown; go2rtc connects via RTSP on port 322
    # lan_mode=False → camera button is hidden; A1/A1 mini or LAN Mode off on printer


class FarmSettings(SQLModel, table=True):
    """Generic key/value store for farm-wide configuration."""
    key: str = Field(primary_key=True)
    value: str


class PrintJob(SQLModel, table=True):
    """Record of a single print job, written when a print starts/ends."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    printer_id: str = Field(index=True)
    printer_name: str = ""
    file_name: str = ""
    started_at: str = ""                # ISO-8601 UTC
    finished_at: Optional[str] = None  # ISO-8601 UTC; None while running
    status: str = "running"            # running | completed | failed | cancelled
    duration_seconds: Optional[int] = None


class DismissedAlert(SQLModel, table=True):
    """Persistent record of a user-dismissed HMS alert for one printer.

    Composite primary key (printer_id + hms_code) means the same HMS code
    can be dismissed independently on different printers.
    """
    printer_id: str = Field(primary_key=True)
    hms_code: str   = Field(primary_key=True)  # HMS_AAAA-BBBB-CCCC-DDDD


class User(SQLModel, table=True):
    """Local user account — scaffold for future authentication support.

    Passwords are stored as bcrypt hashes (never plaintext).
    The 'role' field is reserved for future RBAC (e.g. admin / viewer).

    NOTE: Auth endpoints are not yet implemented. This table is created by
    init_db() so the schema is ready when auth is added.
    """
    id: str              = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    username: str        = Field(unique=True, index=True)
    hashed_password: str = ""       # bcrypt hash; empty until auth is wired up
    role: str            = "admin"  # admin | viewer
    created_at: str      = ""       # ISO-8601 UTC


# ---------------------------------------------------------------------------
# Request body schemas
# ---------------------------------------------------------------------------

class PrinterCreate(BaseModel):
    name: str
    model: str
    ip: str
    serial: str
    access_code: str
    lan_mode: bool = True


class PrinterUpdate(BaseModel):
    """All fields optional — only provided fields are updated (PATCH semantics)."""
    name: Optional[str] = None
    model: Optional[str] = None
    ip: Optional[str] = None
    serial: Optional[str] = None
    access_code: Optional[str] = None
    lan_mode: Optional[bool] = None


class SettingsUpdate(BaseModel):
    farm_name: Optional[str] = None


class PrintControl(BaseModel):
    action: str   # pause | resume | stop


class LightControl(BaseModel):
    mode: str     # on | off


class AlertDismiss(BaseModel):
    hms_code: str   # e.g. HMS_0500-0500-0001-0007


class UserLogin(BaseModel):
    username: str
    password: str


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "admin"


class AdminPasswordReset(BaseModel):
    new_password: str


class BambuCloudLoginRequest(BaseModel):
    email: str
    password: str


class BambuCloudVerifyRequest(BaseModel):
    tfa_key: str
    code: str
    session_cookies: dict = {}


class BambuCloudDevicesRequest(BaseModel):
    token: str


# ---------------------------------------------------------------------------
# Live status models (in-memory only, not persisted)
# ---------------------------------------------------------------------------

class HMSAlert(BaseModel):
    """A single Health Management System alert decoded from MQTT.

    attr and code are the raw integers from the printer. hms_code is the
    human-readable form (e.g. HMS_0300-0100-0001-0003) used in Bambu wiki
    URLs for step-by-step troubleshooting instructions.
    """
    attr: int
    code: int
    hms_code: str   # HMS_AAAA-BBBB-CCCC-DDDD
    wiki_url: str   # https://wiki.bambulab.com/…/hmscode/<hms_code>


class AMSTray(BaseModel):
    """One filament slot inside an AMS unit."""
    slot: int
    tray_type: str = ""         # e.g. "PLA", "PETG"
    color: str = "#FFFFFF"      # CSS hex derived from tray_color MQTT field
    remain: int = 0             # estimated % remaining
    sub_brand: str = ""         # e.g. "Bambu", "Generic"


class AMSUnit(BaseModel):
    """AMS enclosure metadata — up to 4 trays per unit."""
    unit_id: int
    humidity: int = 0    # 0–5 scale; 5 = driest / ideal
    temp: float = 0.0    # °C inside the AMS
    slot_count: int = 4  # physical slot capacity (H2D AMS = 1, standard AMS = 4)


class PrinterStatus(BaseModel):
    """Complete live state for one printer, built from MQTT report messages."""
    printer_id: str
    connected: bool = False
    gcode_state: str = "OFFLINE"    # IDLE | RUNNING | PAUSE | FINISH | FAILED | OFFLINE
    stage: str = ""                 # human-readable sub-stage (e.g. "Leveling")
    progress: int = 0               # 0–100 %
    remaining_time: int = 0         # minutes
    nozzle_temp: float = 0.0        # °C actual
    nozzle_target: float = 0.0      # °C setpoint
    bed_temp: float = 0.0
    bed_target: float = 0.0
    chamber_temp: float = 0.0       # 0 when no enclosure or cloud mode
    current_file: str = ""          # subtask_name from MQTT (job title or filename)
    cover_file: str = ""            # pre-rendered thumbnail path on SD card
    gcode_file: str = ""            # raw gcode_file path from MQTT
    layer_num: int = 0
    total_layers: int = 0
    speed_level: int = 2            # 1 Silent … 4 Ludicrous
    speed_pct: int = 100            # speed override %
    wifi_signal: str = ""           # e.g. "-55dBm"
    fan_speed: int = 0              # part-cooling fan, 0–100 %
    heatbreak_fan_speed: int = 0
    aux_fan_speed: int = 0
    chamber_fan_speed: int = 0
    nozzle_diameter: str = ""       # e.g. "0.4"
    nozzle_type: str = ""           # brass | hardened_steel | stainless_steel
    print_error: int = 0            # non-zero = error; display as 0x… hex
    print_type: str = ""            # cloud | local
    chamber_light: str = ""         # on | off | flashing
    xcam_spaghetti_enabled: bool = False  # AI spaghetti detection toggle
    xcam_halt_enabled: bool = False       # halt-on-detect toggle
    xcam_first_layer_enabled: bool = False
    hms_alerts: list[HMSAlert] = []      # active Health Management System alerts
    ams_trays: list[AMSTray] = []
    ams_units: list[AMSUnit] = []
    ams_current_tray: int = -1      # slot index of active tray; -1 = none
    vt_tray: Optional[AMSTray] = None   # external spool (no AMS)
    last_update: Optional[str] = None   # ISO-8601 UTC of last MQTT message
