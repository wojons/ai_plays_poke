"""Unit tests for src/dashboard/main.py — FastAPI dashboard with 14 endpoints.

Uses FastAPI TestClient. Every dashboard session is rooted at a per-test
tmp_path save dir (see the ``client`` fixture) — no ROM, no emulator, and no
dependence on the repo-local ``game_saves`` tree that real runs populate.
"""

import json
import re
import socket
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# ── Test seams: real ScreenshotManager + faked SQLite ────────────────────

# Base class for the hermetic scanner below: the REAL ScreenshotManager
# (imported through src.core so it is not intercepted by the dashboard
# module's patched attribute), so directory scans stay genuine.
from src.core.screenshot_manager import ScreenshotManager


class HermeticScreenshotManager(ScreenshotManager):
    """Real scanner rooted at a per-test ``tmp_path`` screenshots dir.

    ``DashboardSession`` constructs ``ScreenshotManager`` positionally
    (``ScreenshotManager(str(save_dir / "screenshots"))``), so this keeps the
    real ``get_latest_screenshot`` glob-over-directory behaviour while every
    test's scans land in tmp_path — the /screenshots/latest 404 below is then
    decided by an empty HERMETIC dir, never by the repo-local ``game_saves``
    tree that a real run populates.
    """

    def __init__(self, screenshot_dir):
        super().__init__(str(screenshot_dir))


class FakeGameDatabase:
    """Fake GameDatabase that doesn't touch SQLite."""

    def __init__(self, *args, **kwargs):
        pass


TEST_API_KEY = "unit-test-dashboard-key"


@pytest.fixture(scope="module", autouse=True)
def _api_key_env():
    """All dashboard tests run with an explicitly configured PTP_API_KEY."""
    import src.dashboard.main as dashboard_main

    with patch.object(dashboard_main, "API_KEY", TEST_API_KEY):
        yield


@pytest.fixture
def client(tmp_path, monkeypatch):
    """TestClient whose sessions never see the repo-local game_saves tree.

    The patches are held open (monkeypatch) for the life of the client — the
    previous version's ``with patch(...)`` blocks exited BEFORE any request
    ran, so the dashboard module's ``ScreenshotManager`` was the REAL class at
    request time. Combined with the module-global ``dashboard_sessions`` cache
    (lazily seeded by unrelated tests in this module), GET /screenshots/latest
    answered from the real ``./game_saves`` directory: a real run's
    ``tick_*.png`` flipped the expected-404 test to 200 (TEST-HERM-1).
    """
    import src.dashboard.main as dashboard_main

    monkeypatch.setattr(dashboard_main, "ScreenshotManager", HermeticScreenshotManager)
    monkeypatch.setattr(dashboard_main, "GameDatabase", FakeGameDatabase)
    # Fresh cache per test: without this, a DashboardSession rooted at
    # ./game_saves created by an earlier test in this module (or left over
    # from a previous test session in the same process) is reused and reads
    # the real tree.
    monkeypatch.setattr(dashboard_main, "dashboard_sessions", {})
    # get_session() builds DashboardSession(session_id) with the relative
    # default save_dir="./game_saves"; chdir pins that default to the test's
    # own tmp dir so the lazy "default" session can never read the repo-local
    # game_saves tree a real run populates.
    monkeypatch.chdir(tmp_path)
    from src.dashboard.main import app

    return TestClient(app)


@pytest.fixture
def auth():
    """Default auth headers."""
    return {"x-api-key": TEST_API_KEY}


class TestFailClosedAuth:
    """PTP_API_KEY unset => every request fails closed with 401."""

    def test_unset_key_rejects_old_default_key(self, monkeypatch):
        import src.dashboard.main as dashboard_main

        monkeypatch.delenv("PTP_API_KEY", raising=False)
        with patch.object(dashboard_main, "API_KEY", None):
            client = TestClient(dashboard_main.app)
            # The old committed default key must NOT authenticate anymore.
            resp = client.get(
                "/status", headers={"x-api-key": "ptp" + "-secret-key-12345"}
            )
            assert resp.status_code == 401

    def test_unset_key_rejects_missing_header(self, monkeypatch):
        import src.dashboard.main as dashboard_main

        monkeypatch.delenv("PTP_API_KEY", raising=False)
        with patch.object(dashboard_main, "API_KEY", None):
            client = TestClient(dashboard_main.app)
            assert client.get("/status").status_code == 401
            assert client.get("/metrics").status_code == 401

    def test_unset_key_rejects_empty_header(self, monkeypatch):
        import src.dashboard.main as dashboard_main

        monkeypatch.delenv("PTP_API_KEY", raising=False)
        with patch.object(dashboard_main, "API_KEY", None):
            client = TestClient(dashboard_main.app)
            assert client.get("/status", headers={"x-api-key": ""}).status_code == 401

    def test_configured_key_authenticates(self):
        client = TestClient(__import__("src.dashboard.main", fromlist=["app"]).app)
        assert (
            client.get("/status", headers={"x-api-key": TEST_API_KEY}).status_code
            == 200
        )

    def test_startup_does_not_print_the_api_key(self, capsys, monkeypatch):
        """The ``__main__`` block must not echo the key to stdout."""
        runpy = __import__("runpy")
        import src.dashboard as dashboard_pkg

        # Port 8000 may be occupied by a local dashboard or another test.
        # Port 0 keeps this fake-uvicorn startup test independent of that state.
        monkeypatch.setenv("PTP_DASHBOARD_PORT", "0")

        with patch.dict(
            "sys.modules",
            {"uvicorn": type(sys)("fake_uvicorn")},
        ):
            fake_uvicorn = sys.modules["uvicorn"]

            class FakeConfig:
                def __init__(self, *args, **kwargs):
                    pass

            class FakeServer:
                def __init__(self, config):
                    pass

                def run(self):
                    return None

            fake_uvicorn.Config = FakeConfig
            fake_uvicorn.Server = FakeServer
            runpy.run_path(
                str(Path(dashboard_pkg.__file__).parent / "main.py"),
                run_name="__main__",
            )
        out = capsys.readouterr().out
        assert "API Key" not in out
        assert TEST_API_KEY not in out

    def test_dashboard_bind_failure(self, monkeypatch, capsys):
        """An occupied dashboard port fails before the success banner."""
        import runpy

        import src.dashboard as dashboard_pkg

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            port = listener.getsockname()[1]
            monkeypatch.setenv("PTP_DASHBOARD_HOST", "127.0.0.1")
            monkeypatch.setenv("PTP_DASHBOARD_PORT", str(port))

            with pytest.raises(SystemExit) as exc_info:
                runpy.run_path(
                    str(Path(dashboard_pkg.__file__).parent / "main.py"),
                    run_name="__main__",
                )

        assert exc_info.value.code != 0
        output = capsys.readouterr()
        combined = output.out + output.err
        assert "PTP_DASHBOARD_PORT" in combined
        assert "Starting PTP-01X Dashboard" not in combined


# ── DashboardSession Unit Tests ─────────────────────────────────────────


class TestDashboardSessionInit:
    def test_init_stores_session_id(self):
        from src.dashboard.main import DashboardSession

        ds = DashboardSession("test-session")
        assert ds.session_id == "test-session"

    def test_init_creates_save_dir(self, tmp_path):
        from src.dashboard.main import DashboardSession

        save_dir = tmp_path / "saves"
        _ = DashboardSession("test", str(save_dir))
        assert save_dir.exists()

    def test_init_default_state(self):
        from src.dashboard.main import DashboardSession

        ds = DashboardSession("test")
        assert ds.state["running"] is False
        assert ds.state["paused"] is False
        assert ds.state["tick_count"] == 0
        assert ds.state["current_state"] == "idle"
        assert ds.state["location"] == "Unknown"
        assert ds.state["start_time"] is None

    def test_init_command_history_empty(self):
        from src.dashboard.main import DashboardSession

        ds = DashboardSession("test")
        assert ds.command_history == []

    def test_init_default_save_dir(self):
        from src.dashboard.main import DashboardSession

        ds = DashboardSession("test")
        assert str(ds.save_dir) == "game_saves"  # Path("./game_saves") strips "./"


class TestDashboardSessionLifecycle:
    def test_start_sets_running(self):
        from src.dashboard.main import DashboardSession

        ds = DashboardSession("test")
        ds.start()
        assert ds.state["running"] is True
        assert ds.state["paused"] is False
        assert ds.state["start_time"] is not None

    def test_pause_while_running(self):
        from src.dashboard.main import DashboardSession

        ds = DashboardSession("test")
        ds.start()
        ds.pause()
        assert ds.state["paused"] is True

    def test_pause_while_stopped_noop(self):
        from src.dashboard.main import DashboardSession

        ds = DashboardSession("test")
        ds.pause()
        assert ds.state["paused"] is False

    def test_resume_while_paused(self):
        from src.dashboard.main import DashboardSession

        ds = DashboardSession("test")
        ds.start()
        ds.pause()
        ds.resume()
        assert ds.state["paused"] is False

    def test_stop_clears_running_and_paused(self):
        from src.dashboard.main import DashboardSession

        ds = DashboardSession("test")
        ds.start()
        ds.stop()
        assert ds.state["running"] is False
        assert ds.state["paused"] is False


class TestDashboardSessionUpdateTick:
    def test_increments_counter(self):
        from src.dashboard.main import DashboardSession

        ds = DashboardSession("test")
        ds.update_tick()
        assert ds.state["tick_count"] == 1
        ds.update_tick()
        assert ds.state["tick_count"] == 2

    def test_sets_state(self):
        from src.dashboard.main import DashboardSession

        ds = DashboardSession("test")
        ds.update_tick(new_state="battle")
        assert ds.state["current_state"] == "battle"

    def test_sets_location(self):
        from src.dashboard.main import DashboardSession

        ds = DashboardSession("test")
        ds.update_tick(location="Pallet Town")
        assert ds.state["location"] == "Pallet Town"

    def test_tick_rate_window_capped(self):
        from src.dashboard.main import DashboardSession

        ds = DashboardSession("test")
        for _ in range(70):
            ds.update_tick()
        assert len(ds._tick_rate_window) <= 60


class TestDashboardSessionCommands:
    def test_add_command_stores_fields(self):
        from src.dashboard.main import DashboardSession

        ds = DashboardSession("test")
        ds.add_command({"command": "A"})
        assert ds.command_history[0]["command"] == "A"
        assert "timestamp" in ds.command_history[0]
        assert "tick" in ds.command_history[0]

    def test_history_capped_at_1000(self):
        from src.dashboard.main import DashboardSession

        ds = DashboardSession("test")
        for i in range(1500):
            ds.add_command({"command": str(i)})
        assert len(ds.command_history) == 1000


class TestDashboardSessionStatus:
    def test_get_status_idle(self):
        from src.dashboard.main import DashboardSession

        ds = DashboardSession("test")
        status = ds.get_status()
        assert status["session_id"] == "test"
        assert status["running"] is False
        assert status["tick_count"] == 0

    def test_get_status_running_with_location(self):
        from src.dashboard.main import DashboardSession

        ds = DashboardSession("test")
        ds.start()
        ds.update_tick(new_state="overworld", location="Route 1")
        status = ds.get_status()
        assert status["running"] is True
        assert status["current_state"] == "overworld"
        assert status["location"] == "Route 1"


class TestDashboardSessionMetrics:
    def test_empty_session(self):
        from src.dashboard.main import DashboardSession

        ds = DashboardSession("test")
        metrics = ds.get_metrics()
        assert metrics["total_ticks"] == 0
        assert metrics["total_commands"] == 0
        assert metrics["success_rate"] == 1.0

    def test_with_ticks(self):
        from src.dashboard.main import DashboardSession

        ds = DashboardSession("test")
        ds.start()
        for _ in range(5):
            ds.update_tick()
        assert ds.get_metrics()["total_ticks"] == 5

    def test_with_mixed_commands(self):
        from src.dashboard.main import DashboardSession

        ds = DashboardSession("test")
        ds.add_command({"command": "A", "success": True, "confidence": 0.9})
        ds.add_command({"command": "B", "success": False, "confidence": 0.5})
        metrics = ds.get_metrics()
        assert metrics["total_commands"] == 2
        assert metrics["success_rate"] == 0.5
        assert metrics["avg_confidence"] == 0.7


class TestDashboardSessionRecentActions:
    def test_returns_latest(self):
        from src.dashboard.main import DashboardSession

        ds = DashboardSession("test")
        for i in range(10):
            ds.add_command({"command": str(i)})
        actions = ds.get_recent_actions(3)
        assert len(actions) == 3

    def test_default_limit_50(self):
        from src.dashboard.main import DashboardSession

        ds = DashboardSession("test")
        for i in range(5):
            ds.add_command({"command": str(i)})
        actions = ds.get_recent_actions()
        assert len(actions) == 5


# ── HTTP Endpoint Tests ─────────────────────────────────────────────────


class TestHealthEndpoint:
    def test_no_auth_required(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"


class TestStatusEndpoint:
    def test_no_auth_blocked(self, client):
        assert client.get("/status").status_code in (401, 403)

    def test_with_auth_returns_session(self, client, auth):
        resp = client.get("/status", headers=auth)
        assert resp.status_code == 200
        data = resp.json()
        assert "session_id" in data
        assert "running" in data

    def test_custom_session_id(self, client, auth):
        resp = client.get("/status?session_id=custom", headers=auth)
        assert resp.json()["session_id"] == "custom"


class TestScreenshotsLatest:
    def test_no_auth_blocked(self, client):
        assert client.get("/screenshots/latest").status_code in (401, 403)

    def test_with_auth_no_screenshots_returns_404(self, client, auth):
        assert client.get("/screenshots/latest", headers=auth).status_code == 404

    def test_screenshot_in_hermetic_dir_returns_200(self, client, auth, tmp_path):
        """Positive control: the fixture's isolation does not fake the 404.

        A file placed in the TEST's own tmp screenshots dir (never the
        repo-local tree) must be found by the real scanner — proving the
        expected-404 test above asserts on a genuinely scanned empty dir.
        """
        import src.dashboard.main as dashboard_main

        # The default session is created lazily on first request.
        assert client.get("/status", headers=auth).status_code == 200
        session = dashboard_main.dashboard_sessions["default"]
        hermetic_dir = session.screenshot_manager.screenshot_dir
        assert Path(hermetic_dir).resolve().is_relative_to(tmp_path)
        screenshot = hermetic_dir / "tick_000001_screenshot_test.png"
        screenshot.write_bytes(b"fake png bytes")

        resp = client.get("/screenshots/latest", headers=auth)
        assert resp.status_code == 200
        assert resp.json()["path"] == str(screenshot)


class TestScreenshotsFile:
    def test_no_path_returns_422(self, client):
        assert client.get("/screenshots/file").status_code == 422

    def test_missing_path_returns_404(self, client, auth):
        resp = client.get("/screenshots/file?path=/nonexistent.png", headers=auth)
        assert resp.status_code == 404


class TestActionsRecent:
    def test_no_auth_blocked(self, client):
        assert client.get("/actions/recent").status_code in (401, 403)

    def test_with_auth_returns_structure(self, client, auth):
        resp = client.get("/actions/recent", headers=auth)
        assert resp.status_code == 200
        data = resp.json()
        assert "actions" in data
        assert "total_count" in data


class TestMetricsEndpoint:
    def test_no_auth_blocked(self, client):
        assert client.get("/metrics").status_code in (401, 403)

    def test_with_auth_returns_structure(self, client, auth):
        resp = client.get("/metrics", headers=auth)
        assert resp.status_code == 200
        assert "total_ticks" in resp.json()


class TestControlEndpoints:
    def test_pause_no_auth_blocked(self, client):
        assert client.post("/control/pause").status_code in (401, 403)

    def test_pause_not_started_returns_400(self, client, auth):
        assert client.post("/control/pause", headers=auth).status_code == 400

    def test_stop_always_ok(self, client, auth):
        resp = client.post("/control/stop", headers=auth)
        assert resp.status_code == 200
        assert resp.json()["status"] == "stopped"

    def test_start_creates_session(self, client, auth):
        resp = client.post("/control/start", headers=auth)
        assert resp.status_code == 200
        assert resp.json()["status"] == "started"

    def test_start_then_status_running(self, client, auth):
        client.post("/control/start", headers=auth)
        resp = client.get("/status", headers=auth)
        assert resp.json()["running"] is True

    def test_command_not_running_returns_400(self, client, auth):
        # Use unique session ID to avoid cross-test state leak from test_start
        resp = client.post(
            "/control/command",
            json={"command": "A"},
            headers=auth,
            params={"session_id": "fresh-cmd-test"},
        )
        assert resp.status_code == 400

    def test_command_when_started(self, client, auth):
        client.post("/control/start", headers=auth)
        resp = client.post(
            "/control/command",
            json={"command": "A", "reasoning": "test", "confidence": 0.8},
            headers=auth,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "queued"


class TestSessionsEndpoint:
    def test_no_auth_blocked(self, client):
        assert client.get("/sessions").status_code in (401, 403)

    def test_with_auth_returns_list(self, client, auth):
        resp = client.get("/sessions", headers=auth)
        assert resp.status_code == 200
        assert "sessions" in resp.json()


class TestApiDocs:
    def test_no_auth_ok(self, client):
        resp = client.get("/api/docs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "PTP-01X Dashboard API"
        assert "endpoints" in data


class TestVerifyApiKey:
    def test_invalid_key_returns_401(self, client):
        resp = client.get("/status", headers={"x-api-key": "wrong-key"})
        assert resp.status_code == 401

    def test_missing_key_blocked(self, client):
        assert client.get("/status").status_code in (401, 403)


class TestCreateDashboardApp:
    def test_returns_app(self):
        from src.dashboard.main import create_dashboard_app, app

        assert create_dashboard_app() is app

    def test_accepts_save_dir(self):
        from src.dashboard.main import create_dashboard_app

        assert create_dashboard_app(save_dir="./custom") is not None


class TestSessionsIntegration:
    def test_full_lifecycle(self, client, auth):
        # Start → status running
        assert client.post("/control/start", headers=auth).status_code == 200
        assert client.get("/status", headers=auth).json()["running"] is True

        # Pause → status paused
        assert client.post("/control/pause", headers=auth).status_code == 200
        assert client.get("/status", headers=auth).json()["paused"] is True

        # Resume → status not paused
        assert client.post("/control/resume", headers=auth).status_code == 200
        assert client.get("/status", headers=auth).json()["paused"] is False

        # Stop → status not running
        assert client.post("/control/stop", headers=auth).status_code == 200
        assert client.get("/status", headers=auth).json()["running"] is False

    def test_multi_session_independent(self, client, auth):
        client.post("/control/start?session_id=s1", headers=auth)
        client.post("/control/start?session_id=s2", headers=auth)
        client.post("/control/stop?session_id=s1", headers=auth)
        assert (
            client.get("/status?session_id=s1", headers=auth).json()["running"] is False
        )
        assert (
            client.get("/status?session_id=s2", headers=auth).json()["running"] is True
        )

    def test_list_sessions(self, client, auth):
        client.post("/control/start?session_id=s1", headers=auth)
        client.post("/control/start?session_id=s2", headers=auth)
        sessions = client.get("/sessions", headers=auth).json()["sessions"]
        assert len(sessions) >= 2


# ── Static asset + API key bootstrap (INT-GL-1) ─────────────────────────


class TestStaticAssetHasNoApiKeyLiteral:
    """The tracked dashboard asset must carry no credential literal.

    ``src/dashboard/static/index.html`` shipped a default API key: a credential
    in source control, and the exact shape the gitreins full-tree secrets scan
    flags ("hardcoded API key"). The key is now injected at serve time as
    ``window.ENV`` by ``render_index_html``.
    """

    # Mirrors the built-in scanner's "hardcoded API key" danger pattern.
    LITERAL_KEY_PATTERN = (
        r"""(?i)(api[_-]?key|apikey)\s*[:=]\s*["'][A-Za-z0-9_\-]{20,}["']"""
    )

    def test_pattern_still_matches_a_literal_key(self):
        # Non-vacuity guard: the assertion below only means something while the
        # pattern still matches the shape it exists to catch. The sample is
        # assembled at runtime so no key-shaped literal lands in this file.
        sample = "const API_KEY = '" + ("a1b2c3d4e5f6" * 2) + "';"
        assert re.search(self.LITERAL_KEY_PATTERN, sample) is not None

    def test_index_html_has_no_api_key_literal(self):
        from src.dashboard.main import INDEX_HTML_PATH

        html = INDEX_HTML_PATH.read_text(encoding="utf-8")
        assert re.search(self.LITERAL_KEY_PATTERN, html) is None


class TestApiKeyBootstrap:
    """``GET /`` serves index.html with the runtime key injected."""

    def test_render_injects_the_key_it_is_given(self):
        from src.dashboard.main import render_index_html

        body = render_index_html("unit-test-key")
        assert json.dumps({"PTP_API_KEY": "unit-test-key"}) in body

    def test_render_injects_into_head_before_the_app_script(self):
        from src.dashboard.main import render_index_html

        body = render_index_html("unit-test-key")
        bootstrap_at = body.index("window.ENV = ")
        assert bootstrap_at < body.index("</head>")
        assert bootstrap_at < body.index("const API_KEY")

    def test_render_preserves_the_page(self):
        from src.dashboard.main import render_index_html

        body = render_index_html("unit-test-key")
        assert body.startswith("<!DOCTYPE html>")
        assert body.rstrip().endswith("</html>")
        assert body.count("</head>") == 1

    def test_root_serves_the_injected_page(self, client):
        from src.dashboard.main import API_KEY

        resp = client.get("/")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/html")
        assert json.dumps({"PTP_API_KEY": API_KEY}) in resp.text
        assert resp.text.rstrip().endswith("</html>")


# ── Control transport: session_id travels as a query param (DF-AIPP-11) ──


class TestControlTransportQueryParam:
    """Controls must select their session through the query string.

    The control handlers (``main.py`` pause/resume/stop/start) declare
    ``session_id`` as a query parameter, but the dashboard UI posted
    ``{"session_id": ...}`` in the JSON body of every control call. FastAPI
    ignored the body field, so Start/Pause/Resume/Stop always acted on
    ``"default"``: selecting a non-default session in the dropdown changed the
    read routes only, and Pause/Stop answered 200 while a *different* session
    was actually paused/stopped. These tests pin both halves of the fix — the
    asset's URL shape, and end-to-end behaviour over that transport. Handlers
    are intentionally unchanged.
    """

    CONTROL_FUNCTIONS = {
        "startSession": "/control/start",
        "pauseSession": "/control/pause",
        "resumeSession": "/control/resume",
        "stopSession": "/control/stop",
    }

    @staticmethod
    def _function_body(html: str, name: str) -> str:
        """Source of ``async function <name>()`` up to its closing brace."""
        match = re.search(
            rf"async function {name}\(\) \{{(.*?)\n        \}}", html, re.DOTALL
        )
        assert match is not None, f"{name}() not found in index.html"
        return match.group(1)

    def test_every_control_button_sends_session_id_as_a_query_param(self):
        from src.dashboard.main import INDEX_HTML_PATH

        html = INDEX_HTML_PATH.read_text(encoding="utf-8")
        for name, route in self.CONTROL_FUNCTIONS.items():
            body = self._function_body(html, name)
            assert f"{route}?session_id=${{currentSessionId}}" in body, (
                f"{name}() must POST to {route} with session_id on the query "
                "string — the handlers read it as a query parameter"
            )

    def test_no_control_button_sends_a_request_body(self):
        from src.dashboard.main import INDEX_HTML_PATH

        html = INDEX_HTML_PATH.read_text(encoding="utf-8")
        for name in self.CONTROL_FUNCTIONS:
            body = self._function_body(html, name)
            assert "body:" not in body, (
                f"{name}() must not send a request body — a session_id in the "
                "JSON body is ignored by the query-parameter handlers"
            )

    def test_read_routes_still_use_query_params(self):
        from src.dashboard.main import INDEX_HTML_PATH

        html = INDEX_HTML_PATH.read_text(encoding="utf-8")
        for route in ("/status", "/metrics", "/actions/recent"):
            assert f"{route}?session_id=${{currentSessionId}}" in html

    def test_non_default_session_lifecycle_over_query_transport(self, client, auth):
        """start → command → pause → resume → stop on a non-default session."""
        sid = "dfui"

        # start — the response echoes the requested session, and "default"
        # stays idle (the regression was everything landing on "default").
        started = client.post(f"/control/start?session_id={sid}", headers=auth)
        assert started.status_code == 200
        assert started.json() == {"status": "started", "session_id": sid}
        assert (
            client.get(f"/status?session_id={sid}", headers=auth).json()["running"]
            is True
        )
        assert (
            client.get("/status?session_id=default", headers=auth).json()["running"]
            is False
        )

        # command — queued into the non-default session only.
        queued = client.post(
            f"/control/command?session_id={sid}", json={"command": "A"}, headers=auth
        )
        assert queued.status_code == 200
        assert queued.json()["status"] == "queued"
        assert (
            client.get(f"/actions/recent?session_id={sid}", headers=auth).json()[
                "total_count"
            ]
            == 1
        )
        assert (
            client.get("/actions/recent?session_id=default", headers=auth).json()[
                "total_count"
            ]
            == 0
        )

        # pause — echoes the non-default id and pauses it, not "default".
        paused = client.post(f"/control/pause?session_id={sid}", headers=auth)
        assert paused.status_code == 200
        assert paused.json() == {"status": "paused", "session_id": sid}
        assert (
            client.get(f"/status?session_id={sid}", headers=auth).json()["paused"]
            is True
        )
        assert (
            client.get("/status?session_id=default", headers=auth).json()["paused"]
            is False
        )

        # resume
        resumed = client.post(f"/control/resume?session_id={sid}", headers=auth)
        assert resumed.status_code == 200
        assert resumed.json() == {"status": "resumed", "session_id": sid}
        assert (
            client.get(f"/status?session_id={sid}", headers=auth).json()["paused"]
            is False
        )

        # stop
        stopped = client.post(f"/control/stop?session_id={sid}", headers=auth)
        assert stopped.status_code == 200
        assert stopped.json() == {"status": "stopped", "session_id": sid}
        assert (
            client.get(f"/status?session_id={sid}", headers=auth).json()["running"]
            is False
        )

    def test_body_only_session_id_selects_nothing(self, client, auth):
        """The pre-fix UI transport, pinned as a red-line.

        With the session in the JSON body the handlers answer for "default",
        so this pause report fails (400: default is not running) and the
        selected session keeps running. Asserts the defect is real in the
        handler contract and therefore cannot be reintroduced in the UI.
        """
        client.post("/control/start?session_id=dfui", headers=auth)
        resp = client.post("/control/pause", json={"session_id": "dfui"}, headers=auth)
        assert resp.status_code == 400
        assert resp.json() == {"error": "Session not running"}
        assert (
            client.get("/status?session_id=dfui", headers=auth).json()["running"]
            is True
        )
