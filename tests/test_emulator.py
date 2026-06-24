"""
Unit tests for Emulator class — mock pygba to test without ROM files.
"""
from __future__ import annotations

import numpy as np
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock


# ── helpers ────────────────────────────────────────────────────────────────

def _make_emu() -> "Emulator":
    """Construct an Emulator with fully mocked pygba internals.

    Avoids the eager ROM-file existence check by patching
    ``Path.is_file`` and ``PyGBA.load``.
    """
    with (
        patch("pathlib.Path.is_file", return_value=True),
        patch("pathlib.Path.resolve", return_value=Path("/fake/rom.gba")),
        patch("src.core.emulator.PyGBA") as mock_pygba_cls,
        patch("src.core.emulator.mgba") as mock_mgba,
    ):
        mock_pygba = MagicMock()
        mock_pygba.core.desired_video_dimensions.return_value = (240, 160)
        mock_pygba_cls.load.return_value = mock_pygba

        mock_fb = MagicMock()
        mock_fb.to_pil.return_value.convert.return_value = MagicMock()
        mock_mgba.image.Image.return_value = mock_fb

        from src.core.emulator import Emulator
        emu = Emulator("/fake/rom.gba")
        return emu


# ── tests ──────────────────────────────────────────────────────────────────

class TestEmulatorProperties:
    """Property accessors: is_gb, platform, rom_path."""

    def test_is_gb_false_for_gba(self) -> None:
        emu = _make_emu()
        assert emu.is_gb is False

    def test_platform_returns_gba(self) -> None:
        emu = _make_emu()
        assert emu.platform == "gba"

    def test_rom_path_absolute(self) -> None:
        emu = _make_emu()
        assert emu.rom_path == Path("/fake/rom.gba")

    def test_is_gb_true_when_dimensions_match(self) -> None:
        """When pygba reports 256×224, platform is gb."""
        with (
            patch("pathlib.Path.is_file", return_value=True),
            patch("pathlib.Path.resolve", return_value=Path("/fake/rom.gb")),
            patch("src.core.emulator.PyGBA") as mock_pygba_cls,
            patch("src.core.emulator.mgba") as mock_mgba,
        ):
            mock_pygba = MagicMock()
            mock_pygba.core.desired_video_dimensions.return_value = (256, 224)
            mock_pygba_cls.load.return_value = mock_pygba

            mock_fb = MagicMock()
            mock_mgba.image.Image.return_value = mock_fb

            from src.core.emulator import Emulator
            emu = Emulator("/fake/rom.gb")
            assert emu.is_gb is True
            assert emu.platform == "gb"


class TestFastForward:
    """fast_forward(n) runs core.run_frame() n times."""

    def test_fast_forward_positive(self) -> None:
        emu = _make_emu()
        emu.fast_forward(10)
        assert emu._pygba.core.run_frame.call_count == 10

    def test_fast_forward_zero(self) -> None:
        emu = _make_emu()
        emu.fast_forward(0)
        assert emu._pygba.core.run_frame.call_count == 0

    def test_fast_forward_negative(self) -> None:
        emu = _make_emu()
        emu.fast_forward(-5)
        assert emu._pygba.core.run_frame.call_count == 0


class TestPressButton:
    """press_button delegates to pygba.press_<name>."""

    def test_press_a(self) -> None:
        emu = _make_emu()
        emu.press_button("a", frames=3)
        emu._pygba.press_a.assert_called_once_with(3)

    def test_press_start(self) -> None:
        emu = _make_emu()
        emu.press_button("start", frames=7)
        emu._pygba.press_start.assert_called_once_with(7)

    def test_press_up(self) -> None:
        emu = _make_emu()
        emu.press_button("up", frames=2)
        emu._pygba.press_up.assert_called_once_with(2)

    def test_press_case_insensitive(self) -> None:
        emu = _make_emu()
        emu.press_button("A", frames=5)
        emu._pygba.press_a.assert_called_once_with(5)

    def test_press_unknown_button_raises(self) -> None:
        emu = _make_emu()
        with pytest.raises(ValueError, match="Unknown button"):
            emu.press_button("triangle")

    def test_press_frames_clamped_to_one(self) -> None:
        emu = _make_emu()
        emu.press_button("a", frames=0)
        emu._pygba.press_a.assert_called_once_with(1)

    def test_press_l_and_r(self) -> None:
        emu = _make_emu()
        emu.press_button("l", frames=4)
        emu._pygba.press_l.assert_called_once_with(4)
        emu.press_button("r", frames=4)
        emu._pygba.press_r.assert_called_once_with(4)

    def test_press_select(self) -> None:
        emu = _make_emu()
        emu.press_button("select", frames=3)
        emu._pygba.press_select.assert_called_once_with(3)

    def test_press_all_directions(self) -> None:
        emu = _make_emu()
        for btn in ("up", "down", "left", "right"):
            emu.press_button(btn)
        emu._pygba.press_up.assert_called_once()
        emu._pygba.press_down.assert_called_once()
        emu._pygba.press_left.assert_called_once()
        emu._pygba.press_right.assert_called_once()


class TestWait:
    """wait(frames) delegates to pygba.wait()."""

    def test_wait_positive(self) -> None:
        emu = _make_emu()
        emu.wait(20)
        emu._pygba.wait.assert_called_once_with(20)

    def test_wait_zero(self) -> None:
        emu = _make_emu()
        emu.wait(0)
        emu._pygba.wait.assert_called_once_with(0)

    def test_wait_negative_clamped(self) -> None:
        emu = _make_emu()
        emu.wait(-10)
        emu._pygba.wait.assert_called_once_with(0)


class TestCapture:
    """capture() returns a numpy array from the framebuffer."""

    def test_capture_returns_array(self) -> None:
        emu = _make_emu()
        img = emu.capture()
        assert isinstance(img, np.ndarray)

    def test_capture_calls_framebuffer(self) -> None:
        emu = _make_emu()
        emu.capture()
        emu._framebuffer.to_pil.assert_called()


class TestStop:
    """stop() resets the core and sets _running=False."""

    def test_stop_resets_core(self) -> None:
        emu = _make_emu()
        emu.stop()
        emu._pygba.core.reset.assert_called()

    def test_stop_sets_running_false(self) -> None:
        emu = _make_emu()
        assert emu._running is True
        emu.stop()
        assert emu._running is False

    def test_stop_idempotent(self) -> None:
        """Second stop() is a no-op (already stopped)."""
        emu = _make_emu()
        emu.stop()
        emu._pygba.core.reset.reset_mock()
        emu.stop()
        emu._pygba.core.reset.assert_not_called()


class TestReset:
    """reset() restarts the core."""

    def test_reset_calls_core(self) -> None:
        emu = _make_emu()
        emu.reset()
        emu._pygba.core.reset.assert_called()

    def test_reset_sets_running_true(self) -> None:
        emu = _make_emu()
        emu.stop()
        assert emu._running is False
        emu.reset()
        assert emu._running is True


class TestSkipIntro:
    """skip_intro() runs press A + wait in a loop."""

    def test_skip_intro_defaults(self) -> None:
        emu = _make_emu()
        emu.skip_intro()
        # 16 repetitions: press_a + wait each
        assert emu._pygba.press_a.call_count == 16
        assert emu._pygba.wait.call_count == 16
        # First press uses 30 frames, first wait uses 60
        emu._pygba.press_a.assert_called_with(30)
        emu._pygba.wait.assert_called_with(60)

    def test_skip_intro_custom_params(self) -> None:
        emu = _make_emu()
        emu.skip_intro(press_frames=10, wait_frames=20, repetitions=3)
        assert emu._pygba.press_a.call_count == 3
        assert emu._pygba.wait.call_count == 3
        emu._pygba.press_a.assert_called_with(10)
        emu._pygba.wait.assert_called_with(20)

    def test_skip_intro_single_repetition(self) -> None:
        emu = _make_emu()
        emu.skip_intro(repetitions=1)
        assert emu._pygba.press_a.call_count == 1
        assert emu._pygba.wait.call_count == 1


class TestBypassTitle:
    """bypass_title() presses START to get past the title screen."""

    def test_bypass_title_presses_start(self) -> None:
        emu = _make_emu()
        emu.bypass_title()
        # Two START presses
        assert emu._pygba.press_start.call_count == 2
        assert emu._pygba.wait.call_count == 2

    def test_bypass_title_press_frames(self) -> None:
        emu = _make_emu()
        emu.bypass_title()
        # First press: 30 frames, second: 15 frames
        calls = emu._pygba.press_start.call_args_list
        assert calls[0] == ((30,),) or calls[0].args == (30,)
        assert calls[1] == ((15,),) or calls[1].args == (15,)


class TestEnterName:
    """enter_name() mechanically navigates the name-entry keyboard grid."""

    def test_enter_name_default_ash(self) -> None:
        """Entering 'ASH' should navigate grid and press A for each char + END."""
        emu = _make_emu()
        emu.enter_name()  # default "ASH"

        # Should press A 4 times: A, S, H, END
        assert emu._pygba.press_a.call_count == 4

        # Navigation: 8 right + 1 down to reach S, then 1 left + 1 up to reach H,
        # then 6 down + 1 right to reach END
        assert emu._pygba.press_right.call_count > 0, "Need right presses"
        assert emu._pygba.press_left.call_count > 0, "Need left presses"
        assert emu._pygba.press_down.call_count > 0, "Need down presses"

    def test_enter_name_single_a(self) -> None:
        """Entering 'A' (already at cursor) just presses A then END."""
        emu = _make_emu()
        emu.enter_name("A")

        # A press for the letter + A press for END = 2
        assert emu._pygba.press_a.call_count == 2
        # Navigation: just down×6 + right×1 to reach END from (0,0)
        assert emu._pygba.press_down.call_count == 6

    def test_enter_name_case_insensitive(self) -> None:
        """Lowercase input is uppercased, same navigation as uppercase."""
        emu = _make_emu()
        emu.enter_name("ash")
        # Same as "ASH" — 4 A presses
        assert emu._pygba.press_a.call_count == 4


class TestCombo:
    """combo() presses multiple buttons simultaneously.

    GBA key constants are imported inside the method body
    (``from mgba.gba import GBA``), so we patch ``mgba.gba.GBA``.
    """

    def test_combo_empty_list_noop(self) -> None:
        emu = _make_emu()
        emu.combo([])
        emu._pygba.wait.assert_not_called()

    @patch("mgba.gba.GBA")
    def test_combo_single_button(self, mock_gba: MagicMock) -> None:
        mock_gba.KEY_A = 1
        emu = _make_emu()
        emu.combo(["a"], frames=5)
        emu._pygba.core.add_keys.assert_called_once()
        emu._pygba.core.clear_keys.assert_called_once()

    @patch("mgba.gba.GBA")
    def test_combo_unknown_button_raises(self, mock_gba: MagicMock) -> None:
        mock_gba.KEY_A = 1
        emu = _make_emu()
        with pytest.raises(ValueError, match="Unknown button"):
            emu.combo(["a", "triangle"])


class TestCompatAliases:
    """Compatibility aliases delegate to primary methods."""

    def test_start_calls_reset(self) -> None:
        emu = _make_emu()
        with patch.object(emu, "reset") as mock_reset:
            emu.start()
            mock_reset.assert_called_once()

    def test_capture_screen_calls_capture(self) -> None:
        emu = _make_emu()
        with patch.object(emu, "capture", return_value=np.zeros((160, 240, 3))) as mock_cap:
            result = emu.capture_screen()
            mock_cap.assert_called_once()
            assert isinstance(result, np.ndarray)

    def test_tick_calls_fast_forward(self) -> None:
        emu = _make_emu()
        emu.tick(5)
        assert emu._pygba.core.run_frame.call_count == 5

    def test_tick_defaults_to_one_frame(self) -> None:
        emu = _make_emu()
        emu.tick()
        assert emu._pygba.core.run_frame.call_count == 1
