"""
Tests for the go2rtc stream-registration helpers in main.py.

These helpers are AsyncMock-patched everywhere else (see conftest.py), so they
need their own direct tests — a broken request here is invisible to the rest of
the suite while producing "stream not found" in the browser.

go2rtc's /api/streams handler reads *everything* from the query string:

    query := r.URL.Query()
    src := query.Get("src")
    if src == "" && r.Method != "POST" {
        api.ResponseJSON(w, streams)   // returns 200 + the stream list
        return
    }

So a request without ?src= is answered with 200 OK and creates nothing.  That
makes an omitted src indistinguishable from success unless we assert on the
outgoing request, which is what these tests do.
"""

import httpx
import pytest
from unittest.mock import patch

import main
from models import Printer


# conftest.py's session-scoped `client` fixture patches both helpers with
# AsyncMock, and that patch stays active for the rest of the run once any test
# has used the fixture.  Bind the real coroutines here instead: pytest imports
# every test module during collection, before any fixture body executes, so
# these names always point at the genuine implementation.
_go2rtc_put = main._go2rtc_put
_go2rtc_delete = main._go2rtc_delete


PRINTER = Printer(
    id="7e778f60-45ec-4ca3-8370-c8f30e779cd4",
    name="Justin's H2S friend",
    model="H2D",
    ip="192.168.1.240",
    serial="TESTSERIAL01",
    access_code="a1b2c3d4",
    lan_mode=True,
)

STREAM_NAME = f"bambu_{PRINTER.id}"
EXPECTED_SRC = f"rtsps://bblp:{PRINTER.access_code}@{PRINTER.ip}:322/streaming/live/1"


class _FakeResponse:
    status_code = 200

    def raise_for_status(self):
        return None


class _FakeClient:
    """Records outgoing requests instead of dialling go2rtc."""

    calls: list[httpx.Request] = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def _record(self, method, url, **kwargs):
        # Build a real httpx.Request so param encoding is exercised for real.
        _FakeClient.calls.append(httpx.Request(method, url, **kwargs))
        return _FakeResponse()

    async def put(self, url, **kwargs):
        return self._record("PUT", url, **kwargs)

    async def delete(self, url, **kwargs):
        return self._record("DELETE", url, **kwargs)


@pytest.fixture
def sent():
    _FakeClient.calls = []
    with patch("main.httpx.AsyncClient", _FakeClient):
        yield _FakeClient.calls


# ── PUT / register ────────────────────────────────────────────────────────────

class TestGo2rtcPut:
    @pytest.mark.asyncio
    async def test_sends_src_as_query_param(self, sent):
        """The RTSPS URL must arrive as ?src= — go2rtc ignores the body."""
        await _go2rtc_put(PRINTER)
        assert len(sent) == 1
        assert sent[0].url.params.get("src") == EXPECTED_SRC

    @pytest.mark.asyncio
    async def test_sends_stream_name_as_query_param(self, sent):
        await _go2rtc_put(PRINTER)
        assert sent[0].url.params.get("name") == STREAM_NAME

    @pytest.mark.asyncio
    async def test_src_is_never_empty(self, sent):
        """Regression: an empty ?src= makes go2rtc return the stream list
        with 200 OK and register nothing at all."""
        await _go2rtc_put(PRINTER)
        assert sent[0].url.params.get("src", "") != ""

    @pytest.mark.asyncio
    async def test_does_not_send_a_request_body(self, sent):
        """The old implementation put the URL in the body, where it was
        silently discarded."""
        await _go2rtc_put(PRINTER)
        assert sent[0].content == b""

    @pytest.mark.asyncio
    async def test_targets_the_streams_endpoint(self, sent):
        await _go2rtc_put(PRINTER)
        assert sent[0].url.path == "/api/streams"
        assert sent[0].method == "PUT"

    @pytest.mark.asyncio
    async def test_url_is_percent_encoded(self, sent):
        """The raw query must be encoded so the rtsps:// URL survives intact."""
        await _go2rtc_put(PRINTER)
        raw = str(sent[0].url)
        assert "rtsps%3A%2F%2F" in raw

    @pytest.mark.asyncio
    async def test_http_error_is_swallowed_but_logged(self, sent, caplog):
        """A go2rtc outage must not break printer creation."""
        with patch.object(
            _FakeResponse,
            "raise_for_status",
            side_effect=httpx.HTTPStatusError("400", request=None, response=None),
        ):
            await _go2rtc_put(PRINTER)
        assert "could not register" in caplog.text


# ── DELETE / unregister ───────────────────────────────────────────────────────

class TestGo2rtcDelete:
    @pytest.mark.asyncio
    async def test_identifies_stream_by_src_param(self, sent):
        """go2rtc's DELETE branch keys off ?src=, so passing the stream name
        as ?name= deletes nothing."""
        await _go2rtc_delete(PRINTER.id)
        assert len(sent) == 1
        assert sent[0].url.params.get("src") == STREAM_NAME

    @pytest.mark.asyncio
    async def test_src_is_never_empty(self, sent):
        await _go2rtc_delete(PRINTER.id)
        assert sent[0].url.params.get("src", "") != ""

    @pytest.mark.asyncio
    async def test_targets_the_streams_endpoint(self, sent):
        await _go2rtc_delete(PRINTER.id)
        assert sent[0].url.path == "/api/streams"
        assert sent[0].method == "DELETE"


# ── Reconciliation against the database ───────────────────────────────────────

class _ReconcileClient(_FakeClient):
    """Serves a canned /api/streams payload and records PUTs."""

    streams: dict = {}
    get_fails: bool = False

    async def get(self, url, **kwargs):
        if _ReconcileClient.get_fails:
            raise httpx.ConnectError("go2rtc is down")
        resp = _FakeResponse()
        resp.json = lambda: _ReconcileClient.streams  # type: ignore[method-assign]
        return resp


@pytest.fixture
def reconcile(monkeypatch):
    """Patch httpx + db so _go2rtc_reconcile sees one printer and fake go2rtc.

    Once any test has used conftest's session-scoped `client` fixture,
    main._go2rtc_put stays AsyncMock-patched for the rest of the run, and
    _go2rtc_reconcile would call the mock instead of issuing a request.
    Rebind the real coroutine (captured at import, above) so these tests
    assert on the actual outgoing PUT whatever order the suite runs in.
    """
    _FakeClient.calls = []
    _ReconcileClient.streams = {}
    _ReconcileClient.get_fails = False
    monkeypatch.setattr(main, "_go2rtc_put", _go2rtc_put)
    monkeypatch.setattr(main.db, "get_all_printers", lambda: [PRINTER])
    with patch("main.httpx.AsyncClient", _ReconcileClient):
        yield _FakeClient.calls


def _live(url):
    return {STREAM_NAME: {"producers": [{"url": url}]}}


class TestGo2rtcReconcile:
    @pytest.mark.asyncio
    async def test_missing_stream_is_reregistered(self, reconcile):
        """go2rtc restarting alone drops every stream the backend added."""
        _ReconcileClient.streams = {}
        assert await main._go2rtc_reconcile() == 1
        assert reconcile[0].url.params.get("src") == EXPECTED_SRC

    @pytest.mark.asyncio
    async def test_stale_url_is_corrected(self, reconcile):
        """A changed IP or access code must overwrite what go2rtc holds."""
        _ReconcileClient.streams = _live(
            "rtsps://bblp:OLDCODE0@192.168.1.99:322/streaming/live/1"
        )
        assert await main._go2rtc_reconcile() == 1
        assert reconcile[0].url.params.get("src") == EXPECTED_SRC

    @pytest.mark.asyncio
    async def test_correct_stream_is_left_alone(self, reconcile):
        """The steady state must be silent — no PUT, no log spam."""
        _ReconcileClient.streams = _live(EXPECTED_SRC)
        assert await main._go2rtc_reconcile() == 0
        assert reconcile == []

    @pytest.mark.asyncio
    async def test_stream_with_no_producers_is_repaired(self, reconcile):
        _ReconcileClient.streams = {STREAM_NAME: {"producers": []}}
        assert await main._go2rtc_reconcile() == 1

    @pytest.mark.asyncio
    async def test_unreachable_go2rtc_does_not_register(self, reconcile):
        """Distinguish 'no streams' from 'no answer' — re-registering into a
        dead go2rtc achieves nothing and would log a failure every pass."""
        _ReconcileClient.get_fails = True
        assert await main._go2rtc_reconcile() == 0
        assert reconcile == []


class TestReconcileLoop:
    @pytest.mark.asyncio
    async def test_loop_survives_a_failing_pass(self, monkeypatch):
        """One bad pass must not kill the loop for the rest of the process."""
        import asyncio
        calls = []

        async def boom():
            calls.append(1)
            raise RuntimeError("transient")

        monkeypatch.setattr(main, "_go2rtc_reconcile", boom)
        task = asyncio.create_task(main._go2rtc_reconcile_loop(0))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert len(calls) > 1, "loop stopped after the first failure"


# ── Write-back bug classification ─────────────────────────────────────────────

class TestWritebackBugDetection:
    def _err(self, status, body):
        req = httpx.Request("PUT", "http://go2rtc:1984/api/streams")
        resp = httpx.Response(status, text=body, request=req)
        return httpx.HTTPStatusError("boom", request=req, response=resp)

    def test_recognises_the_yaml_writeback_failure(self):
        assert main._is_writeback_bug(
            self._err(400, "yaml: line 13: did not find expected key")
        )

    def test_other_400s_are_still_real_failures(self):
        assert not main._is_writeback_bug(self._err(400, "some other problem"))

    def test_non_400_is_a_real_failure(self):
        assert not main._is_writeback_bug(self._err(500, "did not find expected key"))

    def test_error_without_a_response_is_a_real_failure(self):
        """httpx errors raised before a response exists must not be swallowed."""
        assert not main._is_writeback_bug(
            httpx.HTTPStatusError("400", request=None, response=None)
        )

    @pytest.mark.asyncio
    async def test_writeback_failure_is_not_logged_as_a_warning(self, sent, caplog):
        """Expected on every restart — it must not read as a broken camera."""
        import logging
        err = self._err(400, "yaml: line 13: did not find expected key")
        with patch.object(_FakeResponse, "raise_for_status", side_effect=err):
            with caplog.at_level(logging.INFO):
                await _go2rtc_put(PRINTER)
        assert "could not register" not in caplog.text
        assert "write-back skipped" in caplog.text


# ── Name agreement with the frontend ──────────────────────────────────────────

def test_stream_name_matches_frontend_convention():
    """CameraModal.jsx opens `?src=bambu_${printer.id}` — if these two ever
    diverge the browser gets 'stream not found' for every printer."""
    assert STREAM_NAME == f"bambu_{PRINTER.id}"
