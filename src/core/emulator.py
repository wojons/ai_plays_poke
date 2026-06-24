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
