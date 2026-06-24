"""
Unified Emulator wrapper using pygba/mGBA.

Supports both GB (Game Boy / Game Boy Color via SGB) and GBA ROMs
through a single interface. For GB ROMs, the SGB border is cropped
to produce a clean 144×160 game screen.
"""

from __future__ import annotations

from pathlib import Path
import mgba.image
import numpy as np
from pygba import PyGBA

# ── button name → pygba method mapping ──────────────────────────────────────
_BUTTON_METHODS: dict[str, str] = {
    "a": "press_a",
    "b": "press_b",
    "up": "press_up",
    "down": "press_down",
    "left": "press_left",
    "right": "press_right",
    "start": "press_start",
    "select": "press_select",
    "l": "press_l",
    "r": "press_r",
}

# SGB border crop region: [y_start:y_end, x_start:x_end]
_SGB_CROP = (slice(40, 184), slice(48, 208))

# ── helpers ──────────────────────────────────────────────────────────────────


def _is_gb_dimensions(dims: tuple[int, int]) -> bool:
    """Return True if video dimensions indicate SGB / GB mode (256×224)."""
    return dims == (256, 224)


# ── Emulator class ───────────────────────────────────────────────────────────

# Legacy Button compat — buttons are just lowercase strings internally
class _ButtonCompat:
    A = "A"
    B = "B"
    START = "START"
    SELECT = "SELECT"
    UP = "UP"
    DOWN = "DOWN"
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    L = "L"
    R = "R"

Button = _ButtonCompat()


class Emulator:
    """
    Unified pygba emulator wrapper.

    Usage::

        emu = Emulator("path/to/rom.gb")   # auto-detects GB vs GBA
        screen = emu.capture()            # RGB numpy array
        emu.press_button("a", frames=5)
        emu.wait(30)
        emu.stop()
    """

    def __init__(self, rom_path: str | Path) -> None:
        """
        Load a ROM and initialise the emulator.

        Args:
            rom_path: Path to a .gb, .gbc, or .gba ROM file.

        Raises:
            FileNotFoundError: If *rom_path* does not exist.
            ValueError: If the ROM cannot be loaded by pygba.
        """
        rom_path = Path(rom_path).resolve()
        if not rom_path.is_file():
            raise FileNotFoundError(f"ROM not found: {rom_path}")

        self._rom_path = rom_path
        self._pygba: PyGBA = PyGBA.load(str(rom_path))

        # Determine platform from the video dimensions pygba reports.
        dims = self._pygba.core.desired_video_dimensions()
        self._is_gb: bool = _is_gb_dimensions(dims)

        # Create the framebuffer and attach it.
        self._framebuffer = mgba.image.Image(*dims)
        self._pygba.core.set_video_buffer(self._framebuffer)
        self._pygba.core.reset()  # **required** after set_video_buffer

        self._running: bool = True

    # ── properties ───────────────────────────────────────────────────────

    @property
    def is_gb(self) -> bool:
        """True if the loaded ROM is a Game Boy / Game Boy Color title."""
        return self._is_gb

    @property
    def platform(self) -> str:
        """Return ``"gb"`` or ``"gba"``."""
        return "gb" if self._is_gb else "gba"

    @property
    def rom_path(self) -> Path:
        """Absolute path to the ROM file."""
        return self._rom_path

    # ── screen capture ───────────────────────────────────────────────────

    def capture(self) -> np.ndarray:
        """
        Capture the current screen as an RGB numpy array.

        For GB ROMs the SGB border is cropped, yielding **144×160** pixels.
        For GBA ROMs the full **160×240** frame is returned.

        Returns:
            uint8 array of shape ``(height, width, 3)``.
        """
        img = np.array(self._framebuffer.to_pil().convert("RGB"))
        if self._is_gb:
            img = img[_SGB_CROP]
        return img

    # ── fast-forward ──────────────────────────────────────────────────────

    def fast_forward(self, frames: int) -> None:
        """Run *frames* at maximum emulator speed (no throttling, ~12k FPS).

        Use this instead of :meth:`wait` when you want to skip through
        animations, dialogue, or transitions as quickly as possible.
        """
        for _ in range(max(frames, 0)):
            self._pygba.core.run_frame()

    # ── input ────────────────────────────────────────────────────────────

    def press_button(self, button: str, frames: int = 5) -> None:
        """
        Press and hold a single button for *frames*.

        Args:
            button: Button name (``"a"``, ``"start"``, ``"up"``, …).
            frames: Number of frames to hold (≥ 1).
        """
        button = button.lower()
        if button not in _BUTTON_METHODS:
            raise ValueError(
                f"Unknown button: {button!r}. Valid: {sorted(_BUTTON_METHODS)}"
            )
        method = getattr(self._pygba, _BUTTON_METHODS[button])
        method(max(frames, 1))

    def wait(self, frames: int) -> None:
        """Advance the emulator by *frames* without pressing any button."""
        self._pygba.wait(max(frames, 0))

    def combo(self, buttons: list[str], frames: int = 5) -> None:
        """
        Press multiple buttons simultaneously for *frames*.

        Args:
            buttons: List of button names.
            frames: Number of frames to hold.
        """
        if not buttons:
            return
        frames = max(frames, 1)
        core = self._pygba.core

        from mgba.gba import GBA

        _KEY_MAP: dict[str, int] = {
            "up": GBA.KEY_UP,
            "down": GBA.KEY_DOWN,
            "left": GBA.KEY_LEFT,
            "right": GBA.KEY_RIGHT,
            "a": GBA.KEY_A,
            "b": GBA.KEY_B,
            "l": GBA.KEY_L,
            "r": GBA.KEY_R,
            "start": GBA.KEY_START,
            "select": GBA.KEY_SELECT,
        }

        key_mask = 0
        for btn in buttons:
            btn = btn.lower()
            if btn not in _KEY_MAP:
                raise ValueError(f"Unknown button: {btn!r}")
            key_mask |= _KEY_MAP[btn]

        core.add_keys(key_mask)
        self._pygba.wait(frames - 1)
        core.clear_keys(key_mask)
        self._pygba.wait(1)

    # ── intro skip ───────────────────────────────────────────────────────

    def skip_intro(
        self,
        *,
        press_frames: int = 30,
        wait_frames: int = 60,
        repetitions: int = 16,
    ) -> None:
        """Advance past the game intro sequence.

        Presses the A button repeatedly, separated by waits, to
        advance through copyright screens, title screen, Professor
        Oak's introduction, and naming screens until the player
        reaches the overworld.

        This is a **best-effort** method — the exact frame counts
        needed vary by ROM and generation.  The defaults work for
        Pokémon LeafGreen / FireRed (GBA, gen3).

        Args:
            press_frames:  How long to hold A each press (≥ 1).
            wait_frames:   How long to idle between presses.
            repetitions:   How many press+wait cycles to perform.
        """
        for _ in range(repetitions):
            self.press_button("a", frames=press_frames)
            self.wait(wait_frames)

    def bypass_title(self) -> None:
        """Press START to get past the Gen 1 title screen.

        On Pokémon Red/Blue, the title screen shows the Pokémon logo and
        waits for a START press.  After START is pressed, a brief animation
        plays (the logo flashes), then the game transitions to Professor
        Oak's introduction.

        This is deterministic — no AI deliberation needed.
        """
        self.press_button("start", frames=30)
        self.wait(90)  # title animation plays
        # Some ROMs need a second press if timing is off
        self.press_button("start", frames=15)
        self.wait(60)

    def enter_name(self, name: str = "ASH") -> None:
        """Mechanically enter a name on the Gen 1 keyboard screen.

        Pokémon Red/Blue/Yellow use a fixed keyboard grid for name entry.
        The cursor starts at the top-left cell (letter "A").  This method
        navigates to each character and presses A, then selects END.

        Keyboard layout (Gen 1 English):

            Row 0:  A  B  C  D  E  F  G  H  I  J
            Row 1:  K  L  M  N  O  P  Q  R  S  T
            Row 2:  U  V  W  X  Y  Z  (  )  :  ;
            Row 3:  [  ]  a  b  c  d  e  f  g  h
            Row 4:  i  j  k  l  m  n  o  p  q  r
            Row 5:  s  t  u  v  w  x  y  z     É
            Row 6: 'd 'l 'm 'r 's 't 'v  s  PK MN END

        Args:
            name: The name to enter (1-7 characters, uppercase).
                  Defaults to "ASH".
        """
        name = name.upper()[:7]  # max 7 chars in Gen 1

        # Keyboard grid — (row, col) → character
        _grid: dict[str, tuple[int, int]] = {
            # Row 0
            "A": (0, 0), "B": (0, 1), "C": (0, 2), "D": (0, 3),
            "E": (0, 4), "F": (0, 5), "G": (0, 6), "H": (0, 7),
            "I": (0, 8), "J": (0, 9),
            # Row 1
            "K": (1, 0), "L": (1, 1), "M": (1, 2), "N": (1, 3),
            "O": (1, 4), "P": (1, 5), "Q": (1, 6), "R": (1, 7),
            "S": (1, 8), "T": (1, 9),
            # Row 2
            "U": (2, 0), "V": (2, 1), "W": (2, 2), "X": (2, 3),
            "Y": (2, 4), "Z": (2, 5),
            # Row 3
            "a": (3, 2), "b": (3, 3), "c": (3, 4), "d": (3, 5),
            "e": (3, 6), "f": (3, 7), "g": (3, 8), "h": (3, 9),
            # Row 4
            "i": (4, 0), "j": (4, 1), "k": (4, 2), "l": (4, 3),
            "m": (4, 4), "n": (4, 5), "o": (4, 6), "p": (4, 7),
            "q": (4, 8), "r": (4, 9),
            # Row 5
            "s": (5, 0), "t": (5, 1), "u": (5, 2), "v": (5, 3),
            "w": (5, 4), "x": (5, 5), "y": (5, 6), "z": (5, 7),
        }
        _END_POS = (6, 9)  # END button

        cur_r, cur_c = 0, 0  # cursor starts at (0,0) = "A"

        for ch in name:
            target = _grid.get(ch)
            if target is None:
                continue  # skip unmapped characters
            tr, tc = target

            # Navigate to target
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

    # ── lifecycle ────────────────────────────────────────────────────────

    def reset(self) -> None:
        """Reset the emulator to its initial state."""
        self._pygba.core.reset()
        self._running = True

    def stop(self) -> None:
        """Stop the emulator and release resources."""
        if self._running:
            self._pygba.core.reset()
            self._running = False

    # ── compatibility aliases ──────────────────────────────────────────

    def start(self) -> None:
        """Compatibility: start the emulator."""
        self.reset()

    def capture_screen(self) -> np.ndarray:
        """Compatibility alias for :meth:`capture`."""
        return self.capture()

    def tick(self, frames: int = 1) -> None:
        """Compatibility: advance by N frames."""
        self.fast_forward(frames)

    # ── save / load state (full emulator checkpoint) ─────────────────────

    def save_state(self, slot: int) -> None:
        """Save full emulator checkpoint to a numbered slot.

        Uses pygba's :meth:`~mgba.core.Core.save_raw_state`, which captures
        the complete emulator state (RAM, CPU registers, I/O, video) — not
        just the game's SRAM.  The state is written to ``checkpoints/<slot>.raw``.

        Args:
            slot: An integer slot number (typically 0–4).

        Raises:
            OSError: If the checkpoint directory cannot be created or the
                file cannot be written.
        """
        _cp_dir = Path("checkpoints")
        _cp_dir.mkdir(parents=True, exist_ok=True)
        raw = self._pygba.core.save_raw_state()
        path = _cp_dir / f"{slot}.raw"
        with open(path, "wb") as fh:
            fh.write(bytes(raw))

    def load_state(self, slot: int) -> None:
        """Restore a full emulator checkpoint from a numbered slot.

        Reads the raw state bytes from ``checkpoints/<slot>.raw`` and feeds
        them to :meth:`~mgba.core.Core.load_raw_state`.

        Args:
            slot: The checkpoint slot to restore.

        Raises:
            FileNotFoundError: If no checkpoint exists for *slot*.
        """
        path = Path("checkpoints") / f"{slot}.raw"
        if not path.is_file():
            raise FileNotFoundError(f"Checkpoint slot {slot} not found: {path}")
        with open(path, "rb") as fh:
            raw = fh.read()
        self._pygba.core.load_raw_state(raw)

    # ── compatibility aliases ──────────────────────────────────────────

    def _save_state_legacy(self, path: str | Path) -> None:
        """Compatibility: save emulator state (SRAM only, not full checkpoint)."""
        import pickle
        data = self._pygba.core.savedata_copy()
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'wb') as fh:
            pickle.dump(data, fh)

    def _load_state_legacy(self, path: str | Path) -> None:
        """Compatibility: load emulator state (SRAM only)."""
        import pickle
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"State file not found: {path}")
        with open(path, 'rb') as fh:
            data = pickle.load(fh)
        self._pygba.core.savedata_restore(data)

