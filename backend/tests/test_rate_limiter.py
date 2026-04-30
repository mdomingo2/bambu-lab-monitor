"""
Tests for the IP-based brute-force rate limiter (rate_limiter.py).

All tests manipulate the limiter directly and use monkeypatching of
time.monotonic to avoid real sleeps.
"""

import time
import pytest
import rate_limiter as rl


@pytest.fixture(autouse=True)
def fresh_limiter():
    """Reset the module-level singleton before every test."""
    rl.limiter.reset()
    yield
    rl.limiter.reset()


# ---------------------------------------------------------------------------
# Basic counting
# ---------------------------------------------------------------------------

class TestFailureCounting:

    def test_no_block_before_limit(self):
        for _ in range(rl.LOGIN_ATTEMPT_LIMIT - 1):
            rl.limiter.record_failure("1.2.3.4")
        blocked, _ = rl.limiter.is_blocked("1.2.3.4")
        assert not blocked

    def test_block_triggers_at_limit(self):
        for _ in range(rl.LOGIN_ATTEMPT_LIMIT):
            rl.limiter.record_failure("1.2.3.4")
        blocked, _ = rl.limiter.is_blocked("1.2.3.4")
        assert blocked

    def test_failure_count_increments(self):
        rl.limiter.record_failure("1.2.3.4")
        rl.limiter.record_failure("1.2.3.4")
        assert rl.limiter.failure_count("1.2.3.4") == 2

    def test_unknown_ip_not_blocked(self):
        blocked, remaining = rl.limiter.is_blocked("9.9.9.9")
        assert not blocked
        assert remaining == 0

    def test_ips_tracked_independently(self):
        for _ in range(rl.LOGIN_ATTEMPT_LIMIT):
            rl.limiter.record_failure("1.1.1.1")
        blocked_a, _ = rl.limiter.is_blocked("1.1.1.1")
        blocked_b, _ = rl.limiter.is_blocked("2.2.2.2")
        assert blocked_a
        assert not blocked_b


# ---------------------------------------------------------------------------
# Lockout duration & exponential backoff
# ---------------------------------------------------------------------------

class TestLockoutDuration:

    def test_first_lockout_duration(self, monkeypatch):
        base_time = 1000.0
        monkeypatch.setattr(time, "monotonic", lambda: base_time)

        for _ in range(rl.LOGIN_ATTEMPT_LIMIT):
            rl.limiter.record_failure("1.2.3.4")

        blocked, remaining = rl.limiter.is_blocked("1.2.3.4")
        assert blocked
        # remaining should be ≈ BASE_LOCKOUT_SECONDS (we round up by 1)
        assert rl.BASE_LOCKOUT_SECONDS <= remaining <= rl.BASE_LOCKOUT_SECONDS + 1

    def test_second_lockout_doubles(self, monkeypatch):
        base_time = 1000.0
        monkeypatch.setattr(time, "monotonic", lambda: base_time)

        for _ in range(rl.LOGIN_ATTEMPT_LIMIT + 1):   # one past the limit
            rl.limiter.record_failure("1.2.3.4")

        _, remaining = rl.limiter.is_blocked("1.2.3.4")
        assert rl.BASE_LOCKOUT_SECONDS * 2 <= remaining <= rl.BASE_LOCKOUT_SECONDS * 2 + 1

    def test_third_lockout_quadruples(self, monkeypatch):
        base_time = 1000.0
        monkeypatch.setattr(time, "monotonic", lambda: base_time)

        for _ in range(rl.LOGIN_ATTEMPT_LIMIT + 2):   # two past the limit
            rl.limiter.record_failure("1.2.3.4")

        _, remaining = rl.limiter.is_blocked("1.2.3.4")
        assert rl.BASE_LOCKOUT_SECONDS * 4 <= remaining <= rl.BASE_LOCKOUT_SECONDS * 4 + 1

    def test_lockout_expires(self, monkeypatch):
        now = [1000.0]
        monkeypatch.setattr(time, "monotonic", lambda: now[0])

        for _ in range(rl.LOGIN_ATTEMPT_LIMIT):
            rl.limiter.record_failure("1.2.3.4")

        # Fast-forward past the lockout window
        now[0] += rl.BASE_LOCKOUT_SECONDS + 1
        blocked, _ = rl.limiter.is_blocked("1.2.3.4")
        assert not blocked


# ---------------------------------------------------------------------------
# Success resets the counter
# ---------------------------------------------------------------------------

class TestSuccessReset:

    def test_success_clears_failures(self):
        rl.limiter.record_failure("1.2.3.4")
        rl.limiter.record_failure("1.2.3.4")
        rl.limiter.record_success("1.2.3.4")
        assert rl.limiter.failure_count("1.2.3.4") == 0

    def test_success_unblocks_ip(self):
        for _ in range(rl.LOGIN_ATTEMPT_LIMIT):
            rl.limiter.record_failure("1.2.3.4")
        rl.limiter.record_success("1.2.3.4")
        blocked, _ = rl.limiter.is_blocked("1.2.3.4")
        assert not blocked

    def test_success_on_unknown_ip_is_safe(self):
        rl.limiter.record_success("9.9.9.9")   # should not raise
        assert rl.limiter.failure_count("9.9.9.9") == 0


# ---------------------------------------------------------------------------
# reset() helper
# ---------------------------------------------------------------------------

class TestReset:

    def test_reset_single_ip(self):
        rl.limiter.record_failure("1.2.3.4")
        rl.limiter.record_failure("5.6.7.8")
        rl.limiter.reset("1.2.3.4")
        assert rl.limiter.failure_count("1.2.3.4") == 0
        assert rl.limiter.failure_count("5.6.7.8") == 1

    def test_reset_all(self):
        rl.limiter.record_failure("1.2.3.4")
        rl.limiter.record_failure("5.6.7.8")
        rl.limiter.reset()
        assert rl.limiter.failure_count("1.2.3.4") == 0
        assert rl.limiter.failure_count("5.6.7.8") == 0


# ---------------------------------------------------------------------------
# Login endpoint integration (via TestClient)
# ---------------------------------------------------------------------------

class TestLoginEndpointRateLimit:
    """Test that the /api/auth/login endpoint enforces the rate limit."""

    @pytest.fixture(autouse=True)
    def _real_user(self):
        """Create a real DB user so we can test successful logins."""
        import database as _db
        import auth as _auth
        _db.create_user("localuser", _auth.hash_password("goodpass123"), "admin")

    def test_too_many_failures_returns_429(self, client):
        for _ in range(rl.LOGIN_ATTEMPT_LIMIT):
            client.post("/api/auth/login", json={"username": "x", "password": "wrong"})
        r = client.post("/api/auth/login", json={"username": "x", "password": "wrong"})
        assert r.status_code == 429

    def test_429_includes_retry_after_header(self, client):
        for _ in range(rl.LOGIN_ATTEMPT_LIMIT):
            client.post("/api/auth/login", json={"username": "x", "password": "wrong"})
        r = client.post("/api/auth/login", json={"username": "x", "password": "wrong"})
        assert "Retry-After" in r.headers

    def test_successful_login_resets_counter(self, client):
        # Two failures — still under the limit
        for _ in range(rl.LOGIN_ATTEMPT_LIMIT - 1):
            client.post("/api/auth/login", json={"username": "x", "password": "wrong"})

        # Successful login clears the counter
        client.post("/api/auth/login", json={"username": "localuser", "password": "goodpass123"})

        # One more bad attempt should be 401 (not 429) because counter was reset
        r = client.post("/api/auth/login", json={"username": "x", "password": "wrong"})
        assert r.status_code == 401   # blocked would be 429

    def test_correct_credentials_not_blocked_initially(self, client):
        r = client.post("/api/auth/login", json={"username": "localuser", "password": "goodpass123"})
        assert r.status_code == 200
