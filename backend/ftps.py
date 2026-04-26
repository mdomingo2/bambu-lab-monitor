"""
ftps.py — Implicit FTPS helpers for Bambu printer SD card access.

Bambu printers expose their SD card over implicit FTPS (port 990) with two
quirks that require custom handling:
  1. SSL is applied immediately on the control socket (no STARTTLS).
  2. Data channels must reuse the control channel's TLS session or the printer
     returns error 522.

All functions in this module are synchronous and intended to be called from a
thread-pool executor (run_in_executor) so they don't block the event loop.
"""

import ftplib
import io
import logging
import os
import ssl
import subprocess
import tempfile

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Core FTPS client
# ---------------------------------------------------------------------------

class ImplicitFTP_TLS(ftplib.FTP_TLS):
    """Implicit FTPS with SSL session reuse — required by Bambu printers.

    Two problems solved:
    1. Implicit FTPS: SSL wraps the control socket immediately on connect
       (no STARTTLS handshake, unlike explicit FTPS on port 21).
    2. SSL session reuse: Bambu returns 522 on data connections unless the
       data channel reuses the control channel's TLS session.  We override
       ntransfercmd to pass session=self.sock.session when wrapping.
    """

    def __init__(self):
        super().__init__()
        self._sock = None

    @property
    def sock(self):
        return self._sock

    @sock.setter
    def sock(self, value):
        if value is not None and not isinstance(value, ssl.SSLSocket):
            value = self.context.wrap_socket(value)
        self._sock = value

    def ntransfercmd(self, cmd, rest=None):
        """Open a data connection reusing the control channel's SSL session."""
        conn, size = ftplib.FTP.ntransfercmd(self, cmd, rest)
        if self._prot_p:
            conn = self.context.wrap_socket(
                conn,
                server_hostname=self.host,
                session=self.sock.session,
            )
        return conn, size


def _make_ssl_context() -> ssl.SSLContext:
    """Create a permissive SSL context for Bambu's self-signed certificate."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def connect(ip: str, access_code: str, timeout: int = 10) -> ImplicitFTP_TLS:
    """Open an authenticated implicit-FTPS connection to a Bambu printer."""
    ftp = ImplicitFTP_TLS()
    ftp.context = _make_ssl_context()
    ftp.connect(host=ip, port=990, timeout=timeout)
    ftp.login("bblp", access_code)
    ftp.prot_p()
    return ftp


# ---------------------------------------------------------------------------
# File operations
# ---------------------------------------------------------------------------

def download(ip: str, access_code: str, remote_path: str, timeout: int = 10) -> bytes | None:
    """Download a single file from the printer SD card.

    Returns raw bytes on success, None if the file is missing or any
    network / auth error occurs.
    """
    try:
        ftp = connect(ip, access_code, timeout)
        buf = io.BytesIO()
        ftp.retrbinary(f"RETR /{remote_path.lstrip('/')}", buf.write)
        ftp.quit()
        return buf.getvalue()
    except Exception as exc:
        logger.debug(f"FTPS download {ip}/{remote_path}: {exc}")
        return None


def list_dir(ip: str, access_code: str, path: str = "/") -> list[str] | None:
    """List a directory on the printer SD card. Returns None on failure."""
    try:
        ftp = connect(ip, access_code, timeout=5)
        entries = ftp.nlst(path)
        ftp.quit()
        return entries
    except Exception as exc:
        logger.debug(f"FTPS list {path} on {ip}: {exc}")
        return None


def download_partial(
    ip: str,
    access_code: str,
    remote_path: str,
    max_bytes: int = 8 * 1024 * 1024,
) -> bytes | None:
    """Download the first *max_bytes* of a file via implicit FTPS.

    Bambu timelapse MP4s are encoded with the moov atom at the front
    (fast-start / web-optimised), so the first ~4–8 MB contains everything
    ffmpeg needs to decode a poster frame without fetching the whole file.
    """
    try:
        ftp = connect(ip, access_code, timeout=20)
        buf = io.BytesIO()

        def _writer(chunk: bytes) -> None:
            remaining = max_bytes - buf.tell()
            if remaining <= 0:
                raise ftplib.error_reply("partial done")
            buf.write(chunk[:remaining])

        try:
            ftp.retrbinary(f"RETR /{remote_path.lstrip('/')}", _writer)
        except ftplib.error_reply:
            pass  # expected abort after max_bytes

        try:
            ftp.quit()
        except Exception:
            pass

        data = buf.getvalue()
        return data if data else None
    except Exception as exc:
        logger.debug(f"FTPS partial download {ip}/{remote_path}: {exc}")
        return None


# ---------------------------------------------------------------------------
# Video frame extraction
# ---------------------------------------------------------------------------

def extract_video_frame(video_bytes: bytes) -> bytes | None:
    """Use ffmpeg to extract the first decodable frame as a JPEG.

    Writes *video_bytes* to a temp file so ffmpeg can seek even when only
    the initial chunk of the video is available (requires fast-start MP4).
    Returns raw JPEG bytes or None if extraction fails.
    """
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            tmp.write(video_bytes)
            tmp_path = tmp.name

        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", tmp_path,
                "-ss", "0",
                "-frames:v", "1",
                "-vf", "scale=480:-1",
                "-f", "image2",
                "-vcodec", "mjpeg",
                "pipe:1",
            ],
            capture_output=True,
            timeout=15,
        )
        os.unlink(tmp_path)

        if result.returncode == 0 and result.stdout:
            return result.stdout
        logger.debug(f"[timelapse thumb] ffmpeg exit {result.returncode}: {result.stderr[-200:]!r}")
        return None
    except Exception as exc:
        logger.debug(f"[timelapse thumb] ffmpeg error: {exc}")
        return None
