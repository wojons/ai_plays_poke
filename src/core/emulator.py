"""
Unified Emulator wrapper using PyBoy.

Replaces pygba/mGBA with PyBoy for reliable memory reads (VRAM, WRAM).
Same API surface for drop-in compatibility.
"""

from __future__ import annotations

from pathlib import Path
import io
import numpy as np
from pyboy import PyBoy as _PyBoy
from pyboy.utils import WindowEvent

# ── Button name → WindowEvent mapping ────────────────────────────────────

_BUTTON_EVENTS: dict[str, WindowEvent] = {
    "a": WindowEvent.PRESS_BUTTON_A,
    "b": WindowEvent.PRESS_BUTTON_B,
    "up": WindowEvent.PRESS_ARROW_UP,
    "down": WindowEvent.PRESS_ARROW_DOWN,
    "left": WindowEvent.PRESS_ARROW_LEFT,
    "right": WindowEvent.PRESS_ARROW_RIGHT,
    "start": WindowEvent.PRESS_BUTTON_START,
    "select": WindowEvent.PRESS_BUTTON_SELECT,
}

_RELEASE_EVENTS: dict[str, WindowEvent] = {
    "a": WindowEvent.RELEASE_BUTTON_A,
    "b": WindowEvent.RELEASE_BUTTON_B,
    "up": WindowEvent.RELEASE_ARROW_UP,
    "down": WindowEvent.RELEASE_ARROW_DOWN,
    "left": WindowEvent.RELEASE_ARROW_LEFT,
    "right": WindowEvent.RELEASE_ARROW_RIGHT,
    "start": WindowEvent.RELEASE_BUTTON_START,
    "select": WindowEvent.RELEASE_BUTTON_SELECT,
}


# ── Legacy Button compat ──────────────────────────────────────────────────

class _ButtonCompat:
    A = "a"
    B = "b"
    START = "start"
    SELECT = "select"
    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"

Button = _ButtonCompat()


# ── Emulator class ────────────────────────────────────────────────────────

class Emulator:
    """Unified PyBoy emulator wrapper.

    Usage::

        emu = Emulator("path/to/rom.gb")
        screen = emu.capture()            # RGB numpy array
        emu.press_button("a", frames=5)
        emu.wait(30)
        emu.stop()
    """

    def __init__(self, rom_path: str | Path) -> None:
        rom_path = Path(rom_path).resolve()
        if not rom_path.is_file():
            raise FileNotFoundError(f"ROM not found: {rom_path}")

        self._rom_path = rom_path
        self._pyboy: _PyBoy = _PyBoy(str(rom_path), window="null")
        self._running: bool = True
        self._is_gb: bool = True  # PyBoy only supports GB/GBC

    # ── properties ───────────────────────────────────────────────────

    @property
    def is_gb(self) -> bool:
        return self._is_gb

    @property
    def platform(self) -> str:
        return "gb"

    @property
    def rom_path(self) -> Path:
        return self._rom_path

    # ── screen capture ───────────────────────────────────────────────

    def capture(self) -> np.ndarray:
        """Capture the current screen as an RGB numpy array (144×160)."""
        # PyBoy screen is (144, 160, 4) RGBA, no SGB border
        screen = self._pyboy.screen.ndarray
        # Convert RGBA → RGB
        return screen[:, :, :3].copy()

    # ── timing ───────────────────────────────────────────────────────

    def fast_forward(self, frames: int) -> None:
        """Run *frames* at maximum emulator speed."""
        for _ in range(max(frames, 0)):
            self._pyboy.tick()

    def wait(self, frames: int) -> None:
        """Advance by *frames* without pressing any button."""
        self.fast_forward(frames)

    def tick(self, frames: int = 1) -> None:
        """Compatibility: advance by N frames."""
        self.fast_forward(frames)

    # ── input ────────────────────────────────────────────────────────

    def press_button(self, button: str, frames: int = 5) -> None:
        """Press and hold a single button for *frames*."""
        button = button.lower()
        if button not in _BUTTON_EVENTS:
            raise ValueError(
                f"Unknown button: {button!r}. Valid: {sorted(_BUTTON_EVENTS)}"
            )
        frames = max(frames, 1)
        self._pyboy.send_input(_BUTTON_EVENTS[button])
        for _ in range(frames - 1):
            self._pyboy.tick()
        self._pyboy.send_input(_RELEASE_EVENTS[button])
        self._pyboy.tick()

    def combo(self, buttons: list[str], frames: int = 5) -> None:
        """Press multiple buttons simultaneously for *frames*."""
        if not buttons:
            return
        frames = max(frames, 1)
        for btn in buttons:
            btn = btn.lower()
            if btn not in _BUTTON_EVENTS:
                raise ValueError(f"Unknown button: {btn!r}")
            self._pyboy.send_input(_BUTTON_EVENTS[btn])
        for _ in range(frames - 1):
            self._pyboy.tick()
        for btn in buttons:
            self._pyboy.send_input(_RELEASE_EVENTS[btn.lower()])
        self._pyboy.tick()

    # ── intro skip ───────────────────────────────────────────────────

    def skip_intro(
        self,
        *,
        press_frames: int = 30,
        wait_frames: int = 60,
        repetitions: int = 16,
    ) -> None:
        """Advance past the game intro by A-mashing."""
        for _ in range(repetitions):
            self.press_button("a", frames=press_frames)
            self.wait(wait_frames)

    def bypass_title(self) -> None:
        """Press START to get past the Gen 1 title screen."""
        self.press_button("start", frames=30)
        self.wait(90)
        self.press_button("start", frames=15)
        self.wait(60)

    def enter_name(self, name: str = "ASH") -> None:
        """Mechanically enter a name on the Gen 1 keyboard screen."""
        name = name.upper()[:7]

        _grid: dict[str, tuple[int, int]] = {
            "A": (0, 0), "B": (0, 1), "C": (0, 2), "D": (0, 3),
            "E": (0, 4), "F": (0, 5), "G": (0, 6), "H": (0, 7),
            "I": (0, 8), "J": (0, 9),
            "K": (1, 0), "L": (1, 1), "M": (1, 2), "N": (1, 3),
            "O": (1, 4), "P": (1, 5), "Q": (1, 6), "R": (1, 7),
            "S": (1, 8), "T": (1, 9),
            "U": (2, 0), "V": (2, 1), "W": (2, 2), "X": (2, 3),
            "Y": (2, 4), "Z": (2, 5),
            "a": (3, 2), "b": (3, 3), "c": (3, 4), "d": (3, 5),
            "e": (3, 6), "f": (3, 7), "g": (3, 8), "h": (3, 9),
            "i": (4, 0), "j": (4, 1), "k": (4, 2), "l": (4, 3),
            "m": (4, 4), "n": (4, 5), "o": (4, 6), "p": (4, 7),
            "q": (4, 8), "r": (4, 9),
            "s": (5, 0), "t": (5, 1), "u": (5, 2), "v": (5, 3),
            "w": (5, 4), "x": (5, 5), "y": (5, 6), "z": (5, 7),
        }
        _END_POS = (6, 9)

        cur_r, cur_c = 0, 0

        for ch in name:
            target = _grid.get(ch)
            if target is None:
                continue
            tr, tc = target
            dr = tr - cur_r
            dc = tc - cur_c
            if dc > 0:
                for _ in range(dc):
                    self.press_button("right", frames=4)
            elif dc < 0:
                for _ in range(-dc):
                    self.press_button("left", frames=4)
            if dr > 0:
                for _ in range(dr):
                    self.press_button("down", frames=4)
            elif dr < 0:
                for _ in range(-dr):
                    self.press_button("up", frames=4)
            self.wait(6)
            self.press_button("a", frames=8)
            self.wait(12)
            cur_r, cur_c = tr, tc

        # Navigate to END and confirm
        dr = _END_POS[0] - cur_r
        dc = _END_POS[1] - cur_c
        if dc > 0:
            for _ in range(dc):
                self.press_button("right", frames=4)
        elif dc < 0:
            for _ in range(-dc):
                self.press_button("left", frames=4)
        if dr > 0:
            for _ in range(dr):
                self.press_button("down", frames=4)
        elif dr < 0:
            for _ in range(-dr):
                self.press_button("up", frames=4)
        self.wait(6)
        self.press_button("a", frames=8)
        self.wait(30)

    # ── lifecycle ────────────────────────────────────────────────────

    def reset(self) -> None:
        """Reset the emulator to its initial state."""
        self._pyboy.stop()
        self._pyboy = _PyBoy(str(self._rom_path), window="null")
        self._running = True

    def stop(self) -> None:
        """Stop the emulator and release resources."""
        if self._running:
            self._pyboy.stop()
            self._running = False

    def start(self) -> None:
        """Compatibility: start the emulator."""
        self.reset()

    def capture_screen(self) -> np.ndarray:
        """Compatibility alias for :meth:`capture`."""
        return self.capture()

    # ── save / load state ────────────────────────────────────────────

    def save_state(self, slot: int) -> None:
        """Save full emulator checkpoint to a numbered slot."""
        _cp_dir = Path("checkpoints")
        _cp_dir.mkdir(parents=True, exist_ok=True)
        path = _cp_dir / f"{slot}.state"
        with open(path, "wb") as fh:
            self._pyboy.save_state(fh)

    def load_state(self, slot: int) -> None:
        """Restore a full emulator checkpoint from a numbered slot."""
        path = Path("checkpoints") / f"{slot}.state"
        if not path.is_file():
            raise FileNotFoundError(f"Checkpoint slot {slot} not found: {path}")
        with open(path, "rb") as fh:
            self._pyboy.load_state(fh)

    # ── RAM reading ──────────────────────────────────────────────────

    def read_u8(self, addr: int) -> int:
        """Read a single byte from emulated Game Boy memory."""
        return self._pyboy.memory[addr]

    def read_u16(self, addr: int) -> int:
        """Read a 16-bit little-endian word from memory."""
        lo = self.read_u8(addr)
        hi = self.read_u8(addr + 1)
        return (hi << 8) | lo
