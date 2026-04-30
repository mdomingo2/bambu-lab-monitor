"""
IP-based brute-force protection for authentication endpoints.

Policy
------
- After LOGIN_ATTEMPT_LIMIT consecutive failures from the same IP the IP is
  locked out for BASE_LOCKOUT_SECONDS * 2^(excess_failures) seconds.
- A successful login resets the counter for that IP.
- State is in-memory and intentionally not persisted — on restart counters
  reset, which is fine.  The goal is to throttle live attacks, not to
  maintain permanent bans.

Lockout schedule (BASE = 300 s, LIMIT = 3):
  attempt 3  →  300 s  ( 5 min)
  attempt 4  →  600 s  (10 min)
  attempt 5  → 1200 s  (20 min)
  attempt 6  → 2400 s  (40 min)
  …
"""

import threading
import time
from dataclasses import dataclass, field

LOGIN_ATTEMPT_LIMIT  = 3     # failures before the first lockout
BASE_LOCKOUT_SECONDS = 300   # duration of the first lockout (seconds)


@dataclass
class _Entry:
    failures: int  = 0
    locked_until: float = 0.0   # monotonic timestamp; 0 = not locked


class RateLimiter:
    """Thread-safe per-IP failure tracker."""

    def __init__(self) -> None:
        self._lock    = threading.Lock()
        self._entries: dict[str, _Entry] = {}

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def is_blocked(self, ip: str) -> tuple[bool, int]:
        """Return (blocked, seconds_remaining).

        seconds_remaining is 0 when not blocked.
        """
        with self._lock:
            entry = self._entries.get(ip)
            if entry is None:
                return False, 0
            remaining = entry.locked_until - time.monotonic()
            if remaining > 0:
                return True, int(remaining) + 1   # round up so UI never shows 0
            return False, 0

    def record_failure(self, ip: str) -> None:
        """Increment the failure counter and update the lockout window."""
        with self._lock:
            entry = self._entries.setdefault(ip, _Entry())
            entry.failures += 1
            if entry.failures >= LOGIN_ATTEMPT_LIMIT:
                excess   = entry.failures - LOGIN_ATTEMPT_LIMIT
                duration = BASE_LOCKOUT_SECONDS * (2 ** excess)
                entry.locked_until = time.monotonic() + duration

    def record_success(self, ip: str) -> None:
        """Clear all failure state for this IP after a successful login."""
        with self._lock:
            self._entries.pop(ip, None)

    # ------------------------------------------------------------------
    # Helpers (testing / admin)
    # ------------------------------------------------------------------

    def reset(self, ip: str | None = None) -> None:
        """Reset one IP (or all IPs when ip is None). Used in tests."""
        with self._lock:
            if ip is None:
                self._entries.clear()
            else:
                self._entries.pop(ip, None)

    def failure_count(self, ip: str) -> int:
        """Return the current failure count for an IP. Used in tests."""
        with self._lock:
            entry = self._entries.get(ip)
            return entry.failures if entry else 0


# Module-level singleton — imported by main.py
limiter = RateLimiter()
