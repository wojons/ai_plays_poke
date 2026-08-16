"""
Unit tests for ram_map_server: deterministic boot progression + POST /input.

All tests stub the emulator — no real PyBoy boot, no ROM required.
"""

from __future__ import annotations

import json
import sys
from io import BytesIO
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import ram_map_server as rms  # noqa: E402


# ── Fakes ────────────────────────────────────────────────────────────────


class FakeEmu:
    """Records every input call; exposes the two WRAM bytes the boot helper reads."""

    def __init__(self, name_length: int = 0, sprite_state: int = 1) -> None:
        self.name_length = name_length
        self.sprite_state = sprite_state
        self.presses: list[tuple[str, int]] = []
        self.combos: list[tuple[list[str], int]] = []
        self.entered: list[str] = []
        self.submits = 0
        self.bypasses = 0
        self.intro_reps: int | None = None
        self.ticks: list[int] = []
        self.waits: list[int] = []
        self.ff: list[int] = []

    def tick(self, frames: int = 1) -> None:
        self.ticks.append(frames)

    def wait(self, frames: int) -> None:
        self.waits.append(frames)

    def fast_forward(self, frames: int) -> None:
        self.ff.append(frames)

    def press_button(self, button: str, frames: int = 5) -> None:
        self.presses.append((button, frames))

    def combo(self, buttons: list[str], frames: int = 5) -> None:
        self.combos.append((list(buttons), frames))

    def bypass_title(self) -> None:
        self.bypasses += 1

    def skip_intro(self, *, repetitions: int = 16) -> None:
        self.intro_reps = repetitions

    def enter_name(self, name: str = "ASH") -> None:
        self.entered.append(name)

    def submit_name(self) -> None:
        self.submits += 1

    def read_u8(self, addr: int) -> int:
        if addr == rms.ADDR_NAMING_NAME_LENGTH:
            return self.name_length
        if addr == rms.ADDR_SPRITE_STATE_DATA:
            return self.sprite_state
        return 0


class FakeReader:
    """Returns a scripted screen_type sequence, then 'overworld' forever."""

    def __init__(self, screens: list[str]) -> None:
        self.screens = list(screens)

    def screen_type(self) -> str:
        if self.screens:
            return self.screens.pop(0)
        return "overworld"

    def current_map_name(self) -> str:
        return "Red's House 2F"


# ── Boot-progression helper ─────────────────────────────────────────────


class TestAdvanceToOverworld:
    def test_lands_directly_when_already_overworld(self) -> None:
        emu = FakeEmu()
        reader = FakeReader(["overworld"])
        rms._advance_to_overworld(emu, reader)
        assert emu.presses == []
        assert emu.entered == []
        assert emu.submits == 0

    def test_types_name_on_empty_buffer(self) -> None:
        emu = FakeEmu(name_length=0)
        reader = FakeReader(["name_entry", "dialog", "overworld"])
        rms._advance_to_overworld(emu, reader)
        assert emu.entered == ["ASH"]
        assert emu.submits == 0
        assert ("a", 20) in emu.presses  # A-mash through the dialog

    def test_accepts_existing_name_when_buffer_non_empty(self) -> None:
        emu = FakeEmu(name_length=7)  # skip_intro's A-mashing typed into it
        reader = FakeReader(["name_entry", "overworld"])
        rms._advance_to_overworld(emu, reader)
        assert emu.entered == []
        assert emu.submits == 1

    def test_handles_two_name_entries(self) -> None:
        emu = FakeEmu(name_length=0)
        reader = FakeReader(["name_entry", "name_entry", "overworld"])
        rms._advance_to_overworld(emu, reader)
        assert emu.entered == ["ASH"]
        assert emu.submits == 1  # rival name screen accepts the default

    def test_raises_when_stuck(self) -> None:
        emu = FakeEmu()
        reader = FakeReader(["dialog"] * 5)
        with pytest.raises(RuntimeError, match="Failed to reach overworld"):
            rms._advance_to_overworld(emu, reader, max_cycles=5)

    def test_boot_emulator_wires_advance(self, monkeypatch) -> None:
        emu = FakeEmu()
        monkeypatch.setattr(rms, "Emulator", lambda path: emu)
        monkeypatch.setattr(
            rms,
            "RAMReader",
            lambda emu_, path: FakeReader(["name_entry", "overworld"]),
        )
        saved = (rms.emu, rms.reader)
        rms.emu = None
        rms.reader = None
        try:
            e, _r = rms.boot_emulator()
        finally:
            rms.emu, rms.reader = saved
        assert e is emu
        assert emu.bypasses == 1
        assert emu.intro_reps == 30
        assert emu.entered == ["ASH"]


# ── POST /input handler (no real socket — direct handler invocation) ─────


class _FakeSocket:
    """Socket stand-in: request bytes in, response bytes out.

    BaseHTTPRequestHandler uses ``wbufsize = 0``, so the response is written
    through a ``_SocketWriter`` that calls ``sendall()`` directly on the
    connection; ``makefile`` is only used for the read side.
    """

    def __init__(self, request: bytes) -> None:
        self._request = BytesIO(request)
        self.response = BytesIO()

    def makefile(self, mode: str, *args: Any) -> BytesIO:
        return self._request

    def sendall(self, data: bytes) -> None:
        self.response.write(data)


class _FakeServer:
    server_address = ("127.0.0.1", 8099)


def _post(body: bytes, path: str = "/input") -> tuple[int, dict]:
    request = (
        f"POST {path} HTTP/1.0\r\n".encode()
        + b"Host: localhost:8099\r\n"
        + b"Content-Type: application/json\r\n"
        + f"Content-Length: {len(body)}\r\n".encode()
        + b"\r\n"
        + body
    )
    sock = _FakeSocket(request)
    rms.Handler(sock, ("127.0.0.1", 4321), _FakeServer())
    raw = sock.response.getvalue()
    status = int(raw.split(b"\r\n", 1)[0].split()[1])
    _, _, body_bytes = raw.partition(b"\r\n\r\n")
    return status, json.loads(body_bytes) if body_bytes.strip() else {}


@pytest.fixture
def fake_emu() -> FakeEmu:
    return FakeEmu()


@pytest.fixture
def fake_reader() -> FakeReader:
    return FakeReader(["overworld"])


class TestPostInput:
    def test_single_button(self, fake_emu, fake_reader) -> None:
        with patch.object(rms, "boot_emulator", return_value=(fake_emu, fake_reader)):
            status, body = _post(json.dumps({"button": "a"}).encode())
        assert status == 200
        assert body["ok"] is True
        assert body["buttons"] == ["a"]
        assert body["frames"] == 5
        assert body["screen_type"] == "overworld"
        assert fake_emu.presses == [("a", 5)]

    def test_buttons_list_is_a_combo(self, fake_emu, fake_reader) -> None:
        with patch.object(rms, "boot_emulator", return_value=(fake_emu, fake_reader)):
            status, body = _post(json.dumps({"buttons": ["a", "start"]}).encode())
        assert status == 200
        assert body["buttons"] == ["a", "start"]
        assert fake_emu.combos == [(["a", "start"], 5)]
        assert fake_emu.presses == []

    def test_combo_alias(self, fake_emu, fake_reader) -> None:
        with patch.object(rms, "boot_emulator", return_value=(fake_emu, fake_reader)):
            status, body = _post(json.dumps({"combo": ["up", "a"]}).encode())
        assert status == 200
        assert body["buttons"] == ["up", "a"]
        assert fake_emu.combos == [(["up", "a"], 5)]

    def test_frames_are_passed_through(self, fake_emu, fake_reader) -> None:
        with patch.object(rms, "boot_emulator", return_value=(fake_emu, fake_reader)):
            status, _ = _post(
                json.dumps({"button": "down", "frames": 30}).encode()
            )
        assert status == 200
        assert fake_emu.presses == [("down", 30)]

    def test_uppercase_button_normalized(self, fake_emu, fake_reader) -> None:
        with patch.object(rms, "boot_emulator", return_value=(fake_emu, fake_reader)):
            status, body = _post(json.dumps({"button": "START"}).encode())
        assert status == 200
        assert body["buttons"] == ["start"]
        assert fake_emu.presses == [("start", 5)]

    def test_unknown_button_rejected(self, fake_emu, fake_reader) -> None:
        with patch.object(rms, "boot_emulator", return_value=(fake_emu, fake_reader)):
            status, body = _post(json.dumps({"button": "bogus"}).encode())
        assert status == 400
        assert body["ok"] is False
        assert "bogus" in body["error"]
        assert fake_emu.presses == []
        assert fake_emu.combos == []

    def test_unknown_button_inside_list_rejected(self, fake_emu, fake_reader) -> None:
        with patch.object(rms, "boot_emulator", return_value=(fake_emu, fake_reader)):
            status, _ = _post(json.dumps({"buttons": ["a", "x"]}).encode())
        assert status == 400
        assert fake_emu.combos == []

    def test_missing_button_rejected(self, fake_emu, fake_reader) -> None:
        with patch.object(rms, "boot_emulator", return_value=(fake_emu, fake_reader)):
            status, body = _post(json.dumps({}).encode())
        assert status == 400
        assert body["ok"] is False

    def test_non_string_button_rejected(self, fake_emu, fake_reader) -> None:
        with patch.object(rms, "boot_emulator", return_value=(fake_emu, fake_reader)):
            status, _ = _post(json.dumps({"button": 5}).encode())
        assert status == 400

    def test_invalid_frames_rejected(self, fake_emu, fake_reader) -> None:
        with patch.object(rms, "boot_emulator", return_value=(fake_emu, fake_reader)):
            status, _ = _post(json.dumps({"button": "a", "frames": 0}).encode())
        assert status == 400
        assert fake_emu.presses == []

    def test_malformed_json_returns_400(self, fake_emu, fake_reader) -> None:
        with patch.object(rms, "boot_emulator", return_value=(fake_emu, fake_reader)):
            status, body = _post(b"not json at all")
        assert status == 400
        assert body["ok"] is False

    def test_emulator_exception_folded_into_400(self, fake_reader) -> None:
        class BoomEmu(FakeEmu):
            def press_button(self, button: str, frames: int = 5) -> None:
                raise RuntimeError("pyboy exploded")

        with patch.object(
            rms, "boot_emulator", return_value=(BoomEmu(), fake_reader)
        ):
            status, body = _post(json.dumps({"button": "a"}).encode())
        assert status == 400
        assert "pyboy exploded" in body["error"]

    def test_non_input_path_returns_404(self, fake_emu, fake_reader) -> None:
        with patch.object(rms, "boot_emulator", return_value=(fake_emu, fake_reader)):
            status, _ = _post(json.dumps({"button": "a"}).encode(), path="/other")
        assert status == 404
        assert fake_emu.presses == []
