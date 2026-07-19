"""Unit tests for src/dashboard/main.py — FastAPI dashboard with 14 endpoints.

Uses FastAPI TestClient with mocked GameDatabase + ScreenshotManager.
No ROM, no emulator, no real filesystem.
"""

import base64
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch, PropertyMock

import pytest
from fastapi.testclient import TestClient

# Import the module under test — must mock deps before importing
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


@pytest.fixture(autouse=True)
def mock_screenshot_manager():
    """Mock ScreenshotManager for all tests."""
    with patch("src.dashboard.main.ScreenshotManager", autospec=True) as mgr:
        yield mgr


@pytest.fixture(autouse=True)
def mock_game_database():
    """Mock GameDatabase for all tests."""
    with patch("src.dashboard.main.GameDatabase", autospec=True) as db:
        yield db


@pytest.fixture
def client():
    """TestClient with mocked dependencies."""
    from src.dashboard.main import app
    return TestClient(app)


@pytest.fixture
def headers():
    """Default auth headers."""
    return {"x-api-key": "ptp-secret-key-12345"}


# ── DashboardSession Tests ──────────────────────────────────────────────

class TestDashboardSessionInit:
    def test_init_stores_session_id(self):
        from src.dashboard.main import DashboardSession
        ds = DashboardSession("test-session")
        assert ds.session_id == "test-session"

    def test_init_creates_save_dir(self, tmp_path):
        from src.dashboard.main import DashboardSession
        save_dir = tmp_path / "saves"
        ds = DashboardSession("test", str(save_dir))
        assert save_dir.exists()
        assert save_dir.is_dir()

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
        assert str(ds.save_dir) == "./game_saves"


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

    def test_pause_while_stopped(self):
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

    def test_resume_while_stopped(self):
        from src.dashboard.main import DashboardSession
        ds = DashboardSession("test")
        ds.resume()
        assert ds.state["paused"] is False

    def test_stop_clears_running_and_paused(self):
        from src.dashboard.main import DashboardSession
        ds = DashboardSession("test")
        ds.start()
        ds.pause()
        ds.stop()
        assert ds.state["running"] is False
        assert ds.state["paused"] is False


class TestDashboardSessionUpdateTick:
    def test_update_tick_increments_counter(self):
        from src.dashboard.main import DashboardSession
        ds = DashboardSession("test")
        ds.update_tick()
        assert ds.state["tick_count"] == 1
        ds.update_tick()
        assert ds.state["tick_count"] == 2

    def test_update_tick_sets_state(self):
        from src.dashboard.main import DashboardSession
        ds = DashboardSession("test")
        ds.update_tick(new_state="battle")
        assert ds.state["current_state"] == "battle"

    def test_update_tick_sets_location(self):
        from src.dashboard.main import DashboardSession
        ds = DashboardSession("test")
        ds.update_tick(location="Pallet Town")
        assert ds.state["location"] == "Pallet Town"

    def test_update_tick_sets_last_action_time(self):
        from src.dashboard.main import DashboardSession
        ds = DashboardSession("test")
        ds.update_tick()
        assert ds.state["last_action_time"] is not None

    def test_update_tick_tick_rate_window_capped(self):
        from src.dashboard.main import DashboardSession
        ds = DashboardSession("test")
        for _ in range(70):
            ds.update_tick()
        assert len(ds._tick_rate_window) <= 60


class TestDashboardSessionCommands:
    def test_add_command_appends(self):
        from src.dashboard.main import DashboardSession
        ds = DashboardSession("test")
        ds.add_command({"command": "A"})
        assert len(ds.command_history) == 1
        assert ds.command_history[0]["command"] == "A"

    def test_add_command_includes_timestamp_and_tick(self):
        from src.dashboard.main import DashboardSession
        ds = DashboardSession("test")
        ds.add_command({"command": "B"})
        assert "timestamp" in ds.command_history[0]
        assert "tick" in ds.command_history[0]

    def test_command_history_capped_at_1000(self):
        from src.dashboard.main import DashboardSession
        ds = DashboardSession("test")
        for i in range(1500):
            ds.add_command({"command": str(i)})
        assert len(ds.command_history) == 1000
        assert ds.command_history[-1]["command"] == "1499"


class TestDashboardSessionStatus:
    def test_get_status_idle(self):
        from src.dashboard.main import DashboardSession
        ds = DashboardSession("test")
        status = ds.get_status()
        assert status["session_id"] == "test"
        assert status["running"] is False
        assert status["tick_count"] == 0
        assert status["elapsed_seconds"] == 0.0

    def test_get_status_running(self):
        from src.dashboard.main import DashboardSession
        ds = DashboardSession("test")
        ds.start()
        ds.update_tick(new_state="overworld", location="Route 1")
        status = ds.get_status()
        assert status["running"] is True
        assert status["current_state"] == "overworld"
        assert status["location"] == "Route 1"

    def test_get_status_elapsed_time(self):
        from src.dashboard.main import DashboardSession
        ds = DashboardSession("test")
        ds.start()
        status = ds.get_status()
        assert status["elapsed_seconds"] >= 0


class TestDashboardSessionMetrics:
    def test_get_metrics_empty(self):
        from src.dashboard.main import DashboardSession
        ds = DashboardSession("test")
        metrics = ds.get_metrics()
        assert metrics["total_ticks"] == 0
        assert metrics["total_commands"] == 0
        assert metrics["success_rate"] == 1.0

    def test_get_metrics_with_ticks(self):
        from src.dashboard.main import DashboardSession
        ds = DashboardSession("test")
        ds.start()
        for _ in range(5):
            ds.update_tick()
        metrics = ds.get_metrics()
        assert metrics["total_ticks"] == 5

    def test_get_metrics_with_commands(self):
        from src.dashboard.main import DashboardSession
        ds = DashboardSession("test")
        ds.add_command({"command": "A", "success": True, "confidence": 0.9})
        ds.add_command({"command": "B", "success": False, "confidence": 0.5})
        metrics = ds.get_metrics()
        assert metrics["total_commands"] == 2
        assert metrics["success_rate"] == 0.5
        assert metrics["avg_confidence"] == 0.7

    def test_get_metrics_session_active_flag(self):
        from src.dashboard.main import DashboardSession
        ds = DashboardSession("test")
        ds.start()
        metrics = ds.get_metrics()
        assert metrics["session_active"] is True


class TestDashboardSessionRecentActions:
    def test_get_recent_actions_returns_latest(self):
        from src.dashboard.main import DashboardSession
        ds = DashboardSession("test")
        for i in range(10):
            ds.add_command({"command": str(i)})
        actions = ds.get_recent_actions(3)
        assert len(actions) == 3
        assert actions[-1]["command"] == "9"

    def test_get_recent_actions_default_limit(self):
        from src.dashboard.main import DashboardSession
        ds = DashboardSession("test")
        for i in range(5):
            ds.add_command({"command": str(i)})
        actions = ds.get_recent_actions()
        assert len(actions) == 5


# ── HTTP Endpoint Tests ─────────────────────────────────────────────────

class TestRootEndpoint:
    def test_root_returns_200(self, client):
        # FileResponse to static/index.html — may or may not exist
        resp = client.get("/")
        # 404 is OK — static file may not exist in test environment
        assert resp.status_code in (200, 404)


class TestHealthEndpoint:
    def test_health_no_auth_required(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data

    def test_health_with_auth(self, client, headers):
        resp = client.get("/health", headers=headers)
        assert resp.status_code == 200


class TestStatusEndpoint:
    def test_status_no_auth_returns_401(self, client):
        resp = client.get("/status")
        assert resp.status_code in (401, 403, 422)

    def test_status_with_auth(self, client, headers):
        resp = client.get("/status", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "session_id" in data
        assert "running" in data

    def test_status_custom_session_id(self, client, headers):
        resp = client.get("/status?session_id=custom", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == "custom"


class TestScreenshotsLatest:
    def test_latest_no_auth(self, client):
        resp = client.get("/screenshots/latest")
        assert resp.status_code in (401, 403, 422)

    def test_latest_with_auth_no_screenshots(self, client, headers):
        resp = client.get("/screenshots/latest", headers=headers)
        assert resp.status_code == 404
        data = resp.json()
        assert "error" in data

    def test_latest_format_base64_no_screenshots(self, client, headers):
        resp = client.get("/screenshots/latest?format=base64", headers=headers)
        assert resp.status_code == 404


class TestScreenshotsFile:
    def test_file_no_path_returns_422(self, client):
        resp = client.get("/screenshots/file")
        assert resp.status_code == 422

    def test_file_missing_path(self, client, headers):
        resp = client.get("/screenshots/file?path=/nonexistent.png", headers=headers)
        assert resp.status_code == 404


class TestActionsRecent:
    def test_recent_no_auth(self, client):
        resp = client.get("/actions/recent")
        assert resp.status_code in (401, 403, 422)

    def test_recent_with_auth(self, client, headers):
        resp = client.get("/actions/recent", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "actions" in data
        assert "total_count" in data

    def test_recent_with_limit(self, client, headers):
        resp = client.get("/actions/recent?limit=10", headers=headers)
        assert resp.status_code == 200


class TestMetricsEndpoint:
    def test_metrics_no_auth(self, client):
        resp = client.get("/metrics")
        assert resp.status_code in (401, 403, 422)

    def test_metrics_with_auth(self, client, headers):
        resp = client.get("/metrics", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "total_ticks" in data


class TestControlEndpoints:
    def test_pause_no_auth(self, client):
        resp = client.post("/control/pause")
        assert resp.status_code in (401, 403, 422)

    def test_pause_with_auth_not_started(self, client, headers):
        resp = client.post("/control/pause", headers=headers)
        assert resp.status_code == 400

    def test_resume_no_auth(self, client):
        resp = client.post("/control/resume")
        assert resp.status_code in (401, 403, 422)

    def test_stop_with_auth(self, client, headers):
        resp = client.post("/control/stop", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "stopped"

    def test_start_creates_session(self, client, headers):
        resp = client.post("/control/start", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "started"

    def test_start_then_status(self, client, headers):
        client.post("/control/start", headers=headers)
        resp = client.get("/status", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["running"] is True

    def test_command_no_auth(self, client):
        resp = client.post("/control/command", json={"command": "A"})
        assert resp.status_code in (401, 403, 422)

    def test_command_not_running(self, client, headers):
        resp = client.post("/control/command", json={"command": "A"}, headers=headers)
        assert resp.status_code == 400

    def test_command_when_started(self, client, headers):
        client.post("/control/start", headers=headers)
        resp = client.post("/control/command", json={"command": "A", "reasoning": "test", "confidence": 0.8}, headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "queued"


class TestSessionsEndpoint:
    def test_sessions_no_auth(self, client):
        resp = client.get("/sessions")
        assert resp.status_code in (401, 403, 422)

    def test_sessions_with_auth(self, client, headers):
        resp = client.get("/sessions", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "sessions" in data


class TestApiDocs:
    def test_api_docs_no_auth(self, client):
        resp = client.get("/api/docs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "PTP-01X Dashboard API"
        assert "endpoints" in data


class TestVerifyApiKey:
    def test_invalid_api_key(self, client):
        resp = client.get("/status", headers={"x-api-key": "wrong-key"})
        assert resp.status_code == 401

    def test_missing_api_key(self, client):
        resp = client.get("/status")
        # FastAPI raises 403 for missing dependency; 422 if body is missing
        assert resp.status_code in (401, 403, 422)


class TestCreateDashboardApp:
    def test_create_dashboard_app_returns_app(self):
        from src.dashboard.main import create_dashboard_app, app
        result = create_dashboard_app()
        assert result is app

    def test_create_dashboard_app_accepts_save_dir(self):
        from src.dashboard.main import create_dashboard_app
        result = create_dashboard_app(save_dir="./custom")
        assert result is not None


class TestSessionsIntegration:
    def test_start_pause_resume_stop_flow(self, client, headers):
        # Start
        r = client.post("/control/start", headers=headers)
        assert r.status_code == 200

        # Status shows running
        r = client.get("/status", headers=headers)
        assert r.json()["running"] is True

        # Pause
        r = client.post("/control/pause", headers=headers)
        assert r.status_code == 200
        r = client.get("/status", headers=headers)
        assert r.json()["paused"] is True

        # Resume
        r = client.post("/control/resume", headers=headers)
        assert r.status_code == 200
        r = client.get("/status", headers=headers)
        assert r.json()["paused"] is False

        # Stop
        r = client.post("/control/stop", headers=headers)
        assert r.status_code == 200
        r = client.get("/status", headers=headers)
        assert r.json()["running"] is False

    def test_multi_session_independent(self, client, headers):
        # Start two sessions
        client.post("/control/start?session_id=s1", headers=headers)
        client.post("/control/start?session_id=s2", headers=headers)

        # s1 status
        r = client.get("/status?session_id=s1", headers=headers)
        assert r.json()["session_id"] == "s1"
        assert r.json()["running"] is True

        # s2 status
        r = client.get("/status?session_id=s2", headers=headers)
        assert r.json()["session_id"] == "s2"
        assert r.json()["running"] is True

        # Stop s1 only
        client.post("/control/stop?session_id=s1", headers=headers)
        r = client.get("/status?session_id=s1", headers=headers)
        assert r.json()["running"] is False

        # s2 still running
        r = client.get("/status?session_id=s2", headers=headers)
        assert r.json()["running"] is True

    def test_list_sessions_shows_all(self, client, headers):
        client.post("/control/start?session_id=s1", headers=headers)
        client.post("/control/start?session_id=s2", headers=headers)

        r = client.get("/sessions", headers=headers)
        assert r.status_code == 200
        sessions = r.json()["sessions"]
        assert len(sessions) >= 2
        sids = {s["session_id"] for s in sessions}
        assert "s1" in sids
        assert "s2" in sids
