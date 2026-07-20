"""Unit tests for src/dashboard/main.py — FastAPI dashboard with 14 endpoints.

Uses FastAPI TestClient with mocked GameDatabase + ScreenshotManager.
No ROM, no emulator, no real filesystem.
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# ── Fake dependencies to avoid real filesystem/SQLite ───────────────────

class FakeScreenshotManager:
    """Fake ScreenshotManager that doesn't touch filesystem."""
    def __init__(self, *args, **kwargs):
        pass
    def get_latest_screenshot(self):
        return None


class FakeGameDatabase:
    """Fake GameDatabase that doesn't touch SQLite."""
    def __init__(self, *args, **kwargs):
        pass


@pytest.fixture(scope="module")
def client():
    """TestClient with patched deps — imported once per module."""
    with patch("src.dashboard.main.ScreenshotManager", FakeScreenshotManager):
        with patch("src.dashboard.main.GameDatabase", FakeGameDatabase):
            from src.dashboard.main import app
    return TestClient(app)


@pytest.fixture
def auth():
    """Default auth headers."""
    return {"x-api-key": "ptp-secret-key-12345"}


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
        resp = client.post("/control/command", json={"command": "A"}, headers=auth,
                           params={"session_id": "fresh-cmd-test"})
        assert resp.status_code == 400

    def test_command_when_started(self, client, auth):
        client.post("/control/start", headers=auth)
        resp = client.post("/control/command", json={
            "command": "A", "reasoning": "test", "confidence": 0.8
        }, headers=auth)
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
        assert client.get("/status?session_id=s1", headers=auth).json()["running"] is False
        assert client.get("/status?session_id=s2", headers=auth).json()["running"] is True

    def test_list_sessions(self, client, auth):
        client.post("/control/start?session_id=s1", headers=auth)
        client.post("/control/start?session_id=s2", headers=auth)
        sessions = client.get("/sessions", headers=auth).json()["sessions"]
        assert len(sessions) >= 2
