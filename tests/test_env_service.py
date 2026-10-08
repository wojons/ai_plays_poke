"""Tests for the CH-SPLIT env service (increment 1).

All emulator behavior is mocked — no ROM or PyBoy needed in CI.
"""

from __future__ import annotations

import base64
from typing import Any
from unittest.mock import MagicMock, patch

import numpy
import pytest
from fastapi.testclient import TestClient

import src.env_service as env_service
from src.env_service import app


@pytest.fixture
def client() -> Any:
    env_service._emulator = None
    env_service._ram_reader = None
    env_service._rom_path = ""
    env_service._boot_state = None
    with TestClient(app) as test_client:
        yield test_client
    env_service._emulator = None
    env_service._ram_reader = None


def _make_emulator() -> MagicMock:
    emu = MagicMock()
    emu.capture.return_value = numpy.zeros((144, 160, 3), dtype=numpy.uint8)
    emu.wait.return_value = None
    emu.press_button.return_value = None
    return emu


def _make_ram_reader() -> MagicMock:
    reader = MagicMock()
    reader.current_map_name.return_value = "Pallet Town"
    reader.current_map_id.return_value = 40
    reader.player_x.return_value = 37
    reader.player_y.return_value = 5
    reader.player_tile_x.return_value = 9
    reader.player_tile_y.return_value = 7
    reader.player_facing.return_value = "down"
    reader.screen_type.return_value = "overworld"
    reader.party_count.return_value = 1
    reader.is_moving.return_value = False
    return reader


def _boot(client: Any) -> Any:
    with patch.object(env_service, "Emulator", return_value=_make_emulator()):
        with patch.object(env_service, "RAMReader", return_value=_make_ram_reader()):
            return client.post(
                "/env/boot",
                json={
                    "rom_path": "/tmp/fake.gb",
                    "boot_state": "/tmp/fake.state",
                },
            )


def test_health_idle_then_booted(client: Any) -> None:
    response = client.get("/env/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "idle",
        "booted": False,
        "rom_path": None,
        "boot_state": None,
    }
    assert _boot(client).status_code == 200
    health = client.get("/env/health").json()
    assert health["booted"] is True
    assert health["rom_path"] == "/tmp/fake.gb"


def test_boot_guard_returns_409(client: Any) -> None:
    assert _boot(client).status_code == 200
    second = _boot(client)
    assert second.status_code == 409
    assert "already booted" in second.json()["detail"]


def test_boot_missing_rom_returns_400(client: Any) -> None:
    with patch.object(
        env_service, "Emulator", side_effect=FileNotFoundError("no such rom")
    ):
        response = client.post("/env/boot", json={})
    assert response.status_code == 400
    assert "no such rom" in response.json()["detail"]


def test_observe_shape_before_boot_409(client: Any) -> None:
    response = client.get("/env/observe")
    assert response.status_code == 409


def test_observe_shape(client: Any) -> None:
    assert _boot(client).status_code == 200
    response = client.get("/env/observe")
    assert response.status_code == 200
    body = response.json()
    assert body["location"] == "Pallet Town"
    assert body["map_id"] == 40
    assert body["player_tile_x"] == 9
    assert body["player_tile_y"] == 7
    assert body["screen_type"] == "overworld"
    assert body["party_count"] == 1
    assert body["is_moving"] is False
    assert body["screenshot_format"] == "png"
    assert base64.b64decode(body["screenshot_base64"])[:8] == (b"\x89PNG\r\n\x1a\n")


def test_observe_ram_failure_fields_null(client: Any) -> None:
    assert _boot(client).status_code == 200
    reader = env_service._ram_reader
    reader.current_map_name.side_effect = RuntimeError("ram glitch")
    response = client.get("/env/observe")
    assert response.status_code == 200
    assert response.json()["location"] is None


def test_act_presses_buttons_and_returns_observation(client: Any) -> None:
    assert _boot(client).status_code == 200
    response = client.post("/env/act", json={"buttons": ["a", "up"], "frames": 5})
    assert response.status_code == 200
    body = response.json()
    assert body["pressed"] == ["a", "up"]
    assert body["frames"] == 5
    assert body["observation"]["location"] == "Pallet Town"
    emu = env_service._emulator
    emu.press_button.assert_any_call("a", frames=5)
    emu.press_button.assert_any_call("up", frames=5)


def test_act_without_buttons_still_advances(client: Any) -> None:
    assert _boot(client).status_code == 200
    waits_before = env_service._emulator.wait.call_count
    response = client.post("/env/act", json={"buttons": [], "frames": 30})
    assert response.status_code == 200
    env_service._emulator.wait.assert_called_with(30)
    assert env_service._emulator.wait.call_count == waits_before + 1


def test_act_before_boot_409(client: Any) -> None:
    response = client.post("/env/act", json={"buttons": ["a"], "frames": 5})
    assert response.status_code == 409


def test_act_frames_out_of_range_422(client: Any) -> None:
    response = client.post("/env/act", json={"buttons": ["a"], "frames": 0})
    assert response.status_code == 422
    response = client.post("/env/act", json={"buttons": ["a"], "frames": 100000})
    assert response.status_code == 422


def test_reset_reloads_boot_state(client: Any) -> None:
    assert _boot(client).status_code == 200
    response = client.post("/env/reset")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "reset"
    assert body["booted"] is True
    emu = env_service._emulator
    emu.load_state.assert_called_with("/tmp/fake.state")
    assert emu.wait.call_count >= 1  # boot settle + reset settle


def test_reset_before_boot_409(client: Any) -> None:
    response = client.post("/env/reset")
    assert response.status_code == 409
