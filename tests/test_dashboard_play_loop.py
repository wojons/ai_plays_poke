"""Live proof for the dashboard play loop (QA-CONSOLE-4).

The HTTP suite (``tests/test_dashboard.py``) stubs the loop so it stays
hermetic, and a stub can only prove the wiring. This module boots the REAL
thing — ``src/dashboard/play_loop.py`` with PyBoy and the provisioned ROM — so
``POST /control/start`` is proven against the emulator, not only against a fake:

* a started session publishes ``tick_count >= 1`` and a RAM-derived location
* ``GET /screenshots/latest`` answers 200 with real PNG bytes instead of 404
* a start whose loop cannot boot refuses with 503 and ``last_error`` — the
  session never claims ``running: true`` with zero ticks

Marked ``rom``/``integration``: skipped when the ROM is not provisioned.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

REPO_ROOT = Path(__file__).resolve().parent.parent
ROM = REPO_ROOT / "data/rom/Pokemon - Blue Version (USA, Europe) (SGB Enhanced).gb"

TEST_API_KEY = "live-play-loop-key"
AUTH = {"x-api-key": TEST_API_KEY}

pytestmark = [
    pytest.mark.integration,
    pytest.mark.rom,
    pytest.mark.skipif(not ROM.is_file(), reason=f"ROM not provisioned at {ROM}"),
]


@pytest.fixture(scope="module", autouse=True)
def _api_key_env():
    import src.dashboard.main as dashboard_main

    with patch.object(dashboard_main, "API_KEY", TEST_API_KEY):
        yield


@pytest.fixture
def dashboard_client():
    """A client over the real app with a clean in-memory session registry."""
    import src.dashboard.main as dashboard_main

    dashboard_main.dashboard_sessions.clear()
    yield TestClient(dashboard_main.app)
    for session in list(dashboard_main.dashboard_sessions.values()):
        session.stop()
    dashboard_main.dashboard_sessions.clear()


def test_http_start_produces_ticks_location_and_a_screenshot(
    tmp_path, dashboard_client
) -> None:
    """AC-2/AC-4: the real start path ticks, resolves a location, saves a PNG."""
    save_dir = tmp_path / "saves"
    resp = dashboard_client.post(f"/control/start?save_dir={save_dir}", headers=AUTH)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "started"
    assert body["session_id"] == "default"
    assert body["tick_count"] >= 1, body

    status = dashboard_client.get("/status", headers=AUTH).json()
    assert status["running"] is True
    assert status["tick_count"] >= 1
    assert status["location"] != "Unknown"
    assert status["current_state"] not in ("idle", "error")
    assert status["last_action_time"] is not None
    assert status["last_error"] is None

    metrics = dashboard_client.get("/metrics", headers=AUTH).json()
    assert metrics["total_ticks"] >= 1
    assert metrics["session_active"] is True

    # First screenshot lands at tick 5 (DEFAULT_SCREENSHOT_EVERY); give the loop
    # a bounded window rather than assuming it already happened.
    deadline = time.monotonic() + 30.0
    latest = dashboard_client.get("/screenshots/latest", headers=AUTH)
    while latest.status_code == 404 and time.monotonic() < deadline:
        time.sleep(0.2)
        latest = dashboard_client.get("/screenshots/latest", headers=AUTH)

    assert latest.status_code == 200, latest.text
    payload = latest.json()
    assert payload["path"].endswith(".png")
    raw = dashboard_client.get(payload["url"])
    assert raw.status_code == 200
    assert len(raw.content) > 100  # real PNG bytes, not an empty placeholder
    assert raw.content[:8] == b"\x89PNG\r\n\x1a\n"

    assert dashboard_client.post("/control/stop", headers=AUTH).status_code == 200
    stopped = dashboard_client.get("/status", headers=AUTH).json()
    assert stopped["running"] is False
    tick_after_stop = stopped["tick_count"]
    time.sleep(0.3)
    assert (
        dashboard_client.get("/status", headers=AUTH).json()["tick_count"]
        == tick_after_stop
    )


def test_start_refuses_honestly_when_the_loop_cannot_boot(
    tmp_path, monkeypatch, dashboard_client
) -> None:
    """The real loop, pointed at a missing ROM, must refuse — never fake a start."""
    import src.dashboard.main as dashboard_main
    from src.dashboard.play_loop import DashboardPlayLoop

    missing = tmp_path / "not-a-rom.gb"
    monkeypatch.setattr(
        dashboard_main,
        "PLAY_LOOP_FACTORY",
        lambda session: DashboardPlayLoop(session, rom_path=missing, boot_state=None),
    )

    resp = dashboard_client.post(
        f"/control/start?save_dir={tmp_path / 'saves'}", headers=AUTH
    )
    assert resp.status_code == 503, resp.text
    assert "ROM not found" in resp.json()["error"]

    status = dashboard_client.get("/status", headers=AUTH).json()
    assert status["running"] is False
    assert status["tick_count"] == 0
    assert "ROM not found" in status["last_error"]
    assert status["current_state"] == "error"


def test_play_loop_defaults_resolve_inside_the_repo(monkeypatch) -> None:
    """The loop's ROM/checkpoint defaults do not depend on the process cwd."""
    from src.dashboard.play_loop import (
        DEFAULT_BOOT_STATE,
        DEFAULT_ROM,
        REPO_ROOT,
        resolve_boot_state,
        resolve_rom_path,
    )

    monkeypatch.delenv("PTP_DASHBOARD_ROM", raising=False)
    monkeypatch.delenv("PTP_DASHBOARD_BOOT_STATE", raising=False)

    assert DEFAULT_ROM.parent == REPO_ROOT / "data" / "rom"
    assert DEFAULT_ROM.is_file()
    assert resolve_rom_path() == DEFAULT_ROM
    assert DEFAULT_BOOT_STATE.is_file()
    assert resolve_boot_state() == DEFAULT_BOOT_STATE
