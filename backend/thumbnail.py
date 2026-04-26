"""
thumbnail.py — Print thumbnail fetching for Bambu printers.

Thumbnails are fetched synchronously over FTPS and should always be called
via asyncio.get_running_loop().run_in_executor() to avoid blocking the event
loop.

Strategy waterfall (stops at first hit):
  0.  Cloud print with plate_N.gcode path → fetch plate_N.png from SD card.
  0b. Named cloud print → look for <subtask_name>.gcode.3mf at SD root.
  1a. Subtask/gcode name ends in .3mf → direct download from /cache/ or /.
  1b. Job-title .gcode.3mf at SD root (P2S / H2D LAN prints).
  2.  List all .3mf files on SD card newest-first, try each for an embedded PNG.
  3.  gcode_file path is itself a .3mf.
  4.  Explicit cover_file path from MQTT (pre-rendered JPEG/PNG).

Cache semantics:
  One cache slot per printer_id.  Cleared by on_printer_status() in main.py
  whenever the active file changes, so every new job triggers a fresh fetch.
"""

import io
import logging
import os
import re
import zipfile

import httpx

import ftps

logger = logging.getLogger(__name__)

GO2RTC_URL = os.getenv("GO2RTC_URL", "http://go2rtc:1984")

# Thumbnail paths inside Bambu .gcode.3mf ZIP archives, tried in preference
# order. These are plate renders written by Bambu Studio / Orca Slicer.
_3MF_THUMBNAIL_PATHS = [
    "Metadata/plate_1.png",
    "Metadata/plate_1_small.png",
    "Metadata/top_1.png",
    "Metadata/pick_1.png",
    "Metadata/plate_2.png",
    "Metadata/thumbnail_v2.png",
    "Metadata/thumbnail.png",
    "Metadata/thumbnail_small.png",
    "thumbnail/thumbnail.png",
]

# Module-level cache — one slot per printer_id.
# Managed externally: cleared by on_printer_status when current_file changes.
cache: dict[str, bytes] = {}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_from_3mf(data: bytes) -> bytes | None:
    """Extract the first matching plate thumbnail from a .gcode.3mf ZIP."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = zf.namelist()
            logger.info(f"[3mf] zip entries ({len(names)}): {names[:20]}")
            for path in _3MF_THUMBNAIL_PATHS:
                if path in names:
                    return zf.read(path)
            logger.info(f"[3mf] no thumbnail path matched; candidates: {_3MF_THUMBNAIL_PATHS}")
    except Exception as exc:
        logger.info(f"[3mf] extraction failed ({len(data)} bytes, magic={data[:4]!r}): {exc}")
    return None


def _list_3mf(ip: str, access_code: str) -> list[str]:
    """Return .3mf paths from the printer SD card, newest-first when MDTM works.

    Model differences:
      P2S / H2D: .gcode.3mf files at FTP root, returned as /name.gcode.3mf
      A1  / P1S: .3mf files inside /cache/, returned as bare names by nlst

    The /cache/ listing is capped at 20 to avoid iterating 400+ files on
    busy P1S printers.
    """
    try:
        ftp = ftps.connect(ip, access_code, timeout=10)
        candidates: list[str] = []

        root_entries = ftp.nlst("/")
        candidates.extend(e for e in root_entries if e.lower().endswith(".gcode.3mf"))

        if not candidates:
            try:
                for entry in ftp.nlst("/cache"):
                    name = entry.lstrip("/")
                    if name.lower().endswith(".3mf") and not name.lower().endswith(".bbl"):
                        candidates.append(f"/cache/{name}")
                        if len(candidates) >= 20:
                            break
            except Exception as exc:
                logger.info(f"[thumbnail] /cache listing failed on {ip}: {exc}")

        logger.info(f"[thumbnail] {ip} SD candidates ({len(candidates)}): {candidates[:8]}")

        if not candidates:
            ftp.quit()
            return []

        timed: list[tuple[str, str]] = []
        mdtm_supported = False
        for path in candidates:
            try:
                resp = ftp.sendcmd(f"MDTM {path}")
                timed.append((resp.split()[-1], path))
                mdtm_supported = True
            except Exception:
                timed.append(("", path))

        ftp.quit()

        if mdtm_supported:
            timed.sort(reverse=True)
            logger.info(f"[thumbnail] {ip} newest by MDTM: {[p for _, p in timed[:3]]}")

        return [p for _, p in timed]

    except Exception as exc:
        logger.info(f"[thumbnail] _list_3mf {ip} failed: {exc}")
        return []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_sync(
    printer_id: str,
    ip: str,
    access_code: str,
    cover_file: str,
    gcode_file: str,
    subtask_name: str = "",
) -> bytes | None:
    """Fetch a print thumbnail from the printer SD card (blocking / thread-safe).

    Returns cached bytes immediately if available. Otherwise runs the strategy
    waterfall described in the module docstring. Results are stored in cache[].
    """
    if printer_id in cache:
        return cache[printer_id]

    def _store(data: bytes) -> bytes:
        cache[printer_id] = data
        return data

    logger.info(
        f"[thumbnail] {ip} subtask={subtask_name!r} "
        f"cover={cover_file!r} gcode={gcode_file!r}"
    )

    # ── Strategy 0: cloud print with /data/Metadata/plate_N.gcode path ──────
    # H2D and P1S report this path for cloud-mode prints. The plate thumbnails
    # live in internal memory not accessible over FTPS, so we try a few
    # root-relative variants then return None rather than falling through to the
    # SD card scan (which would return the wrong file for a different job).
    plate_match = re.match(r".*/plate_(\d+)\.gcode$", gcode_file or "", re.IGNORECASE)
    if plate_match:
        plate = plate_match.group(1)
        for thumb_path in [
            f"/data/Metadata/plate_{plate}.png",
            f"/data/Metadata/plate_{plate}_small.png",
            f"/Metadata/plate_{plate}.png",
            f"/Metadata/plate_{plate}_small.png",
            f"/cache/Metadata/plate_{plate}.png",
        ]:
            img = ftps.download(ip, access_code, thumb_path, timeout=10)
            if img and img[:4] in (b"\x89PNG", b"\xff\xd8\xff"):
                logger.info(f"[thumbnail] hit via strategy 0 (plate png): {thumb_path}")
                return _store(img)

        # Strategy 0b: named cloud print. When the user names the job before
        # sending from Bambu Studio the .3mf is stored at the SD card root.
        # Slicer-profile descriptions always contain commas; real filenames don't.
        if subtask_name and "," not in subtask_name and not subtask_name.lower().endswith(".gcode"):
            for ext in (".gcode.3mf", ".3mf"):
                raw = ftps.download(ip, access_code, f"/{subtask_name}{ext}", timeout=20)
                if raw:
                    img = _extract_from_3mf(raw)
                    if img:
                        logger.info(f"[thumbnail] hit via strategy 0b (named cloud): /{subtask_name}{ext}")
                        return _store(img)

        logger.info(f"[thumbnail] strategy 0: unnamed cloud print on {ip}, no thumbnail via FTPS")
        return None

    # ── Strategy 1a: direct .3mf download (A1 / P1S) ───────────────────────
    for name in filter(None, [subtask_name, gcode_file]):
        if name.lower().endswith(".3mf"):
            clean = name.lstrip("/")
            for path in [f"/cache/{clean}", f"/{clean}"]:
                raw = ftps.download(ip, access_code, path, timeout=20)
                if raw:
                    img = _extract_from_3mf(raw)
                    if img:
                        logger.info(f"[thumbnail] hit via strategy 1a: {path}")
                        return _store(img)

    # ── Strategy 1b: job-title .gcode.3mf at SD root (P2S / H2D) ───────────
    if subtask_name and not subtask_name.lower().endswith(".3mf"):
        for ext in (".gcode.3mf", ".3mf"):
            raw = ftps.download(ip, access_code, f"/{subtask_name}{ext}", timeout=20)
            if raw:
                img = _extract_from_3mf(raw)
                if img:
                    logger.info(f"[thumbnail] hit via strategy 1b: /{subtask_name}{ext}")
                    return _store(img)

    # ── Strategy 2: scan SD card newest-first ───────────────────────────────
    for candidate in _list_3mf(ip, access_code):
        raw = ftps.download(ip, access_code, candidate, timeout=20)
        if raw:
            img = _extract_from_3mf(raw)
            if img:
                logger.info(f"[thumbnail] hit via strategy 2: {candidate}")
                return _store(img)
            logger.info(f"[thumbnail] no image in {candidate}")

    # ── Strategy 3: gcode_file is itself a .3mf ─────────────────────────────
    if gcode_file and ".3mf" in gcode_file.lower():
        raw = ftps.download(ip, access_code, gcode_file, timeout=20)
        if raw:
            img = _extract_from_3mf(raw)
            if img:
                logger.info(f"[thumbnail] hit via strategy 3: {gcode_file}")
                return _store(img)

    # ── Strategy 4: explicit cover_file from MQTT ────────────────────────────
    if cover_file:
        img = ftps.download(ip, access_code, cover_file, timeout=5)
        if img:
            logger.info(f"[thumbnail] hit via strategy 4 (cover_file): {cover_file}")
            return _store(img)

    logger.debug(
        f"[thumbnail] no thumbnail for {ip}: "
        f"subtask={subtask_name!r} gcode={gcode_file!r} cover={cover_file!r}"
    )
    return None


async def snapshot_from_camera(printer_id: str) -> bytes | None:
    """Grab a single JPEG frame from go2rtc for a printer's camera stream.

    Used as a thumbnail fallback for cloud-mode prints where the .3mf is not
    accessible via FTPS. Only called when lan_mode is True (RTSP reachable).
    """
    stream_name = f"bambu_{printer_id}"
    url = f"{GO2RTC_URL}/api/frame.jpeg?src={stream_name}"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            if resp.status_code == 200 and len(resp.content) > 1000:
                logger.info(f"[thumbnail] camera snapshot for {stream_name}: {len(resp.content)}B")
                return resp.content
            logger.debug(
                f"[thumbnail] go2rtc snapshot {stream_name}: "
                f"status={resp.status_code} size={len(resp.content)}B"
            )
    except Exception as exc:
        logger.debug(f"[thumbnail] go2rtc snapshot failed for {stream_name}: {exc}")
    return None
