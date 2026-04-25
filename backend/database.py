"""
Database layer for Bambu Farm Monitor.

Thin wrapper around SQLModel / SQLite. All functions open their own session
so callers don't need to manage transactions. The engine is module-level and
thread-safe for read-heavy workloads (SQLite WAL mode is not explicitly set,
but SQLModel/SQLAlchemy handles concurrent reads safely).
"""

import os
from datetime import datetime, timezone

from sqlalchemy import text
from sqlmodel import SQLModel, Session, create_engine, select

from models import Printer, FarmSettings, PrintJob, DismissedAlert

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:////app/data/bambu.db")

# echo=False suppresses per-query SQL logging in production.
engine = create_engine(DATABASE_URL, echo=False)

# Settings applied when no row exists in FarmSettings.
DEFAULT_SETTINGS: dict[str, str] = {"farm_name": "Print Farm"}


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def init_db() -> None:
    """Create all tables if they don't already exist, then run migrations."""
    SQLModel.metadata.create_all(engine)
    _migrate()


def _migrate() -> None:
    """Forward-only column migrations for existing databases.

    SQLModel/create_all only creates missing *tables*, not missing *columns*.
    Add any new Printer/etc. columns here so existing installs upgrade cleanly.
    """
    with engine.connect() as conn:
        # lan_mode — added to support per-printer camera visibility toggle.
        # Default 1 (True) so existing printers keep showing the camera button.
        cols = [row[1] for row in conn.execute(text("PRAGMA table_info(printer)"))]
        if "lan_mode" not in cols:
            conn.execute(text("ALTER TABLE printer ADD COLUMN lan_mode INTEGER NOT NULL DEFAULT 1"))
            conn.commit()


# ---------------------------------------------------------------------------
# Printers
# ---------------------------------------------------------------------------

def get_all_printers() -> list[Printer]:
    with Session(engine) as session:
        return session.exec(select(Printer)).all()


def get_printer(printer_id: str) -> Printer | None:
    with Session(engine) as session:
        return session.get(Printer, printer_id)


def create_printer(printer: Printer) -> Printer:
    with Session(engine) as session:
        session.add(printer)
        session.commit()
        session.refresh(printer)
        return printer


def update_printer(printer_id: str, updates: dict) -> Printer | None:
    """Apply a partial update (PATCH semantics). Returns None if not found."""
    with Session(engine) as session:
        p = session.get(Printer, printer_id)
        if not p:
            return None
        for key, value in updates.items():
            if value is not None:
                setattr(p, key, value)
        session.add(p)
        session.commit()
        session.refresh(p)
        return p


def delete_printer(printer_id: str) -> bool:
    """Delete a printer. Returns False if not found."""
    with Session(engine) as session:
        p = session.get(Printer, printer_id)
        if not p:
            return False
        session.delete(p)
        session.commit()
        return True


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

def get_settings() -> dict[str, str]:
    """Return all farm settings, falling back to DEFAULT_SETTINGS for missing keys."""
    with Session(engine) as session:
        rows = session.exec(select(FarmSettings)).all()
        return {**DEFAULT_SETTINGS, **{row.key: row.value for row in rows}}


def set_setting(key: str, value: str) -> None:
    """Upsert a single setting key."""
    with Session(engine) as session:
        existing = session.get(FarmSettings, key)
        if existing:
            existing.value = value
            session.add(existing)
        else:
            session.add(FarmSettings(key=key, value=value))
        session.commit()


# ---------------------------------------------------------------------------
# Print history
# ---------------------------------------------------------------------------

def start_print_job(printer_id: str, printer_name: str, file_name: str) -> PrintJob:
    """Create a new running job record when a print starts."""
    job = PrintJob(
        printer_id=printer_id,
        printer_name=printer_name,
        file_name=file_name,
        started_at=datetime.now(timezone.utc).isoformat(),
        status="running",
    )
    with Session(engine) as session:
        session.add(job)
        session.commit()
        session.refresh(job)
    return job


def finish_print_job(job_id: str, status: str) -> None:
    """Close a job with the given terminal status and compute its duration."""
    with Session(engine) as session:
        job = session.get(PrintJob, job_id)
        if not job:
            return
        now = datetime.now(timezone.utc)
        job.finished_at = now.isoformat()
        job.status = status
        try:
            started = datetime.fromisoformat(job.started_at)
            job.duration_seconds = int((now - started).total_seconds())
        except Exception:
            pass
        session.add(job)
        session.commit()


def abandon_running_jobs() -> None:
    """Mark any jobs still 'running' from a previous server session as cancelled.

    Called once at startup to avoid jobs being permanently stuck in 'running'
    state after an unclean shutdown.
    """
    with Session(engine) as session:
        stale = session.exec(select(PrintJob).where(PrintJob.status == "running")).all()
        for job in stale:
            job.status = "cancelled"
            session.add(job)
        session.commit()


def get_all_dismissed_alerts() -> dict[str, list[str]]:
    """Return {printer_id: [hms_code, …]} for every printer that has dismissals."""
    with Session(engine) as session:
        rows = session.exec(select(DismissedAlert)).all()
    result: dict[str, list[str]] = {}
    for row in rows:
        result.setdefault(row.printer_id, []).append(row.hms_code)
    return result


def get_dismissed_alerts(printer_id: str) -> list[str]:
    """Return the list of dismissed HMS codes for a single printer."""
    with Session(engine) as session:
        rows = session.exec(
            select(DismissedAlert).where(DismissedAlert.printer_id == printer_id)
        ).all()
        return [r.hms_code for r in rows]


def dismiss_alert(printer_id: str, hms_code: str) -> None:
    """Persistently dismiss an HMS alert for a printer (idempotent)."""
    with Session(engine) as session:
        session.merge(DismissedAlert(printer_id=printer_id, hms_code=hms_code))
        session.commit()


def undismiss_alert(printer_id: str, hms_code: str) -> None:
    """Restore a previously dismissed HMS alert so it appears in the UI again."""
    with Session(engine) as session:
        row = session.exec(
            select(DismissedAlert).where(
                DismissedAlert.printer_id == printer_id,
                DismissedAlert.hms_code == hms_code,
            )
        ).first()
        if row:
            session.delete(row)
            session.commit()


def get_print_history(limit: int = 200) -> list[PrintJob]:
    """Return the most recent print jobs, newest first."""
    with Session(engine) as session:
        return list(
            session.exec(
                select(PrintJob).order_by(PrintJob.started_at.desc()).limit(limit)
            ).all()
        )
