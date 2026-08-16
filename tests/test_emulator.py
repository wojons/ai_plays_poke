"""
Unit tests for Emulator class — mock PyBoy to test without ROM files.
"""

from __future__ import annotations

import contextlib
import numpy as np
import pytest
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

from pyboy.utils import WindowEvent

# ── Fixture: mock PyBoy for all emulator tests ──────────────────────────


@contextlib.contextmanager
def _mock_pyboy():
    """Context manager that patches PyBoy imports in the emulator module.

    Yields (mock_pyboy_cls, mock_pyboy_instance) for test setup.
    """
    with (
        patch("pathlib.Path.is_file", return_value=True),
        patch("pathlib.Path.resolve", return_value=Path("/fake/rom.gb")),
        patch("src.core.emulator._PyBoy") as mock_pyboy_cls,
    ):
        mock_pyboy = MagicMock()
        mock_pyboy.screen.ndarray = np.zeros((144, 160, 4), dtype=np.uint8)
        mock_pyboy_cls.return_value = mock_pyboy

        # Ensure fresh from_cache for each test
        if "Emulator" in dir():
            pass
        yield mock_pyboy


@pytest.fixture
def emu():
    """Create an Emulator with fully mocked PyBoy internals."""
    with _mock_pyboy() as mock_pyboy:
        from src.core.emulator import Emulator

        e = Emulator("/fake/rom.gb")
        e._pyboy = mock_pyboy
        yield e


@pytest.fixture
def emu_with_state():
    """Create Emulator with save_state/load_state mocked."""
    with (
        patch("pathlib.Path.is_file", return_value=True),
        patch("pathlib.Path.resolve", return_value=Path("/fake/rom.gb")),
        patch("pathlib.Path.mkdir"),
        patch("src.core.emulator._PyBoy") as mock_pyboy_cls,
    ):
        mock_pyboy = MagicMock()
        mock_pyboy.screen.ndarray = np.zeros((144, 160, 4), dtype=np.uint8)
        mock_pyboy_cls.return_value = mock_pyboy
        from src.core.emulator import Emulator

        e = Emulator("/fake/rom.gb")
        e._pyboy = mock_pyboy
        yield e


# ── tests ──────────────────────────────────────────────────────────────────


class TestEmulatorProperties:
    """Property accessors: is_gb, platform, rom_path."""

    def test_is_gb_true(self, emu) -> None:
        """PyBoy only supports GB — always True."""
        assert emu.is_gb is True

    def test_platform_returns_gb(self, emu) -> None:
        assert emu.platform == "gb"

    def test_rom_path_absolute(self, emu) -> None:
        assert emu.rom_path == Path("/fake/rom.gb")

    def test_button_compat(self) -> None:
        """Button constants have correct lowercase values."""
        from src.core.emulator import Button

        assert Button.A == "a"
        assert Button.B == "b"
        assert Button.START == "start"
        assert Button.SELECT == "select"
        assert Button.UP == "up"
        assert Button.DOWN == "down"
        assert Button.LEFT == "left"
        assert Button.RIGHT == "right"


class TestFastForward:
    """fast_forward(n) advances n frames without per-frame rendering."""

    def test_fast_forward_positive(self, emu) -> None:
        emu.fast_forward(10)
        emu._pyboy.tick.assert_called_once_with(10, render=False)
        assert emu._render_debt == 10

    def test_fast_forward_zero(self, emu) -> None:
        emu.fast_forward(0)
        assert emu._pyboy.tick.call_count == 0
        assert emu._render_debt == 0

    def test_fast_forward_negative(self, emu) -> None:
        emu.fast_forward(-5)
        assert emu._pyboy.tick.call_count == 0
        assert emu._render_debt == 0


class TestPressButton:
    """press_button sends WindowEvent press, ticks, then release."""

    def test_press_a(self, emu) -> None:
        emu.press_button("a", frames=3)
        emu._pyboy.send_input.assert_any_call(WindowEvent.PRESS_BUTTON_A)
        emu._pyboy.send_input.assert_any_call(WindowEvent.RELEASE_BUTTON_A)
        # hold frames tick without rendering, final tick renders
        emu._pyboy.tick.assert_any_call(2, render=False)
        emu._pyboy.tick.assert_any_call(1, render=True)

    def test_press_start(self, emu) -> None:
        emu.press_button("start", frames=3)
        emu._pyboy.send_input.assert_any_call(WindowEvent.PRESS_BUTTON_START)
        emu._pyboy.send_input.assert_any_call(WindowEvent.RELEASE_BUTTON_START)

    def test_press_up(self, emu) -> None:
        emu.press_button("up", frames=3)
        emu._pyboy.send_input.assert_any_call(WindowEvent.PRESS_ARROW_UP)
        emu._pyboy.send_input.assert_any_call(WindowEvent.RELEASE_ARROW_UP)

    def test_press_case_insensitive(self, emu) -> None:
        emu.press_button("A", frames=3)
        emu._pyboy.send_input.assert_any_call(WindowEvent.PRESS_BUTTON_A)
        emu._pyboy.send_input.assert_any_call(WindowEvent.RELEASE_BUTTON_A)

    def test_press_unknown_button_raises(self, emu) -> None:
        with pytest.raises(ValueError, match="Unknown button"):
            emu.press_button("triangle")

    def test_press_frames_clamped_to_one(self, emu) -> None:
        emu.press_button("a", frames=0)
        assert emu._pyboy.tick.call_count == 1

    def test_press_select(self, emu) -> None:
        emu.press_button("select", frames=3)
        emu._pyboy.send_input.assert_any_call(WindowEvent.PRESS_BUTTON_SELECT)
        emu._pyboy.send_input.assert_any_call(WindowEvent.RELEASE_BUTTON_SELECT)

    def test_press_all_directions(self, emu) -> None:
        for btn in ("up", "down", "left", "right"):
            emu.press_button(btn)
        assert emu._pyboy.send_input.call_count == 8


class TestWait:
    """wait(frames) delegates to fast_forward -> tick."""

    def test_wait_positive(self, emu) -> None:
        emu.wait(20)
        emu._pyboy.tick.assert_called_once_with(20, render=False)

    def test_wait_zero(self, emu) -> None:
        emu.wait(0)
        assert emu._pyboy.tick.call_count == 0

    def test_wait_negative_clamped(self, emu) -> None:
        emu.wait(-10)
        assert emu._pyboy.tick.call_count == 0


class TestCapture:
    """capture() returns an RGB numpy array from PyBoy screen."""

    def test_capture_returns_array(self, emu) -> None:
        img = emu.capture()
        assert isinstance(img, np.ndarray)

    def test_capture_rgba_to_rgb(self, emu) -> None:
        """RGBA (144, 160, 4) → RGB (144, 160, 3)."""
        img = emu.capture()
        assert img.shape == (144, 160, 3)

    def test_capture_values_preserved(self, emu) -> None:
        """RGB channels from RGBA are preserved, alpha channel dropped."""
        rgba = np.full((144, 160, 4), 128, dtype=np.uint8)
        rgba[:, :, 0] = 10
        rgba[:, :, 1] = 20
        rgba[:, :, 2] = 30
        emu._pyboy.screen.ndarray = rgba
        img = emu.capture()
        assert img[0, 0, 0] == 10
        assert img[0, 0, 1] == 20
        assert img[0, 0, 2] == 30


class TestStop:
    """stop() calls _pyboy.stop() and sets _running=False."""

    def test_stop_calls_pyboy_stop(self, emu) -> None:
        emu.stop()
        emu._pyboy.stop.assert_called_once()

    def test_stop_sets_running_false(self, emu) -> None:
        assert emu._running is True
        emu.stop()
        assert emu._running is False

    def test_stop_idempotent(self, emu) -> None:
        """Second stop() is a no-op (already stopped)."""
        emu.stop()
        emu._pyboy.stop.reset_mock()
        emu.stop()
        emu._pyboy.stop.assert_not_called()


class TestReset:
    """reset() stops the old emulator and creates a new PyBoy instance."""

    def test_reset_stops_old_pyboy(self, emu) -> None:
        emu.reset()
        emu._pyboy.stop.assert_called_once()

    def test_reset_sets_running_true(self, emu) -> None:
        emu.stop()
        assert emu._running is False
        emu.reset()
        assert emu._running is True


class TestSkipIntro:
    """skip_intro() runs press A + wait in a loop."""

    def test_skip_intro_defaults(self, emu) -> None:
        emu.skip_intro()
        assert emu._pyboy.send_input.call_count >= 32
        assert emu._pyboy.tick.call_count > 0

    def test_skip_intro_custom_params(self, emu) -> None:
        emu.skip_intro(press_frames=10, wait_frames=20, repetitions=3)
        assert emu._pyboy.send_input.call_count >= 6

    def test_skip_intro_single_repetition(self, emu) -> None:
        emu.skip_intro(repetitions=1)
        assert emu._pyboy.send_input.call_count == 2


class TestBypassTitle:
    """bypass_title() presses START to get past the title screen."""

    def test_bypass_title_presses_start(self, emu) -> None:
        emu.bypass_title()
        assert emu._pyboy.send_input.call_count == 4


class TestEnterName:
    """enter_name() mechanically navigates the name-entry keyboard grid."""

    def test_enter_name_default_ash(self, emu) -> None:
        """Entering 'ASH' should navigate grid and press A for each char + END."""
        emu.enter_name()
        press_a_calls = [
            c
            for c in emu._pyboy.send_input.call_args_list
            if c[0][0] == WindowEvent.PRESS_BUTTON_A
        ]
        assert len(press_a_calls) == 4

    def test_enter_name_single_a(self, emu) -> None:
        """Entering 'A' (already at cursor) just presses A then END."""
        emu.enter_name("A")
        press_a_calls = [
            c
            for c in emu._pyboy.send_input.call_args_list
            if c[0][0] == WindowEvent.PRESS_BUTTON_A
        ]
        assert len(press_a_calls) == 2

    def test_enter_name_case_insensitive(self, emu) -> None:
        """Lowercase input is uppercased, same result as uppercase."""
        emu.enter_name("ash")
        press_a_calls = [
            c
            for c in emu._pyboy.send_input.call_args_list
            if c[0][0] == WindowEvent.PRESS_BUTTON_A
        ]
        assert len(press_a_calls) == 4

    def test_enter_name_navigates_grid(self, emu) -> None:
        """Navigation keys are used to move the cursor."""
        emu.enter_name("ASH")
        all_press = [c[0][0] for c in emu._pyboy.send_input.call_args_list]
        direction_events = [
            WindowEvent.PRESS_ARROW_RIGHT,
            WindowEvent.PRESS_ARROW_LEFT,
            WindowEvent.PRESS_ARROW_UP,
            WindowEvent.PRESS_ARROW_DOWN,
        ]
        direction_used = [e for e in direction_events if e in all_press]
        assert len(direction_used) > 0

    def test_submit_name_navigates_to_real_end_key(self, emu) -> None:
        emu.submit_name()
        presses = [call[0][0] for call in emu._pyboy.send_input.call_args_list]

        assert presses.count(WindowEvent.PRESS_ARROW_DOWN) == 4
        assert presses.count(WindowEvent.PRESS_ARROW_RIGHT) == 8
        assert presses.count(WindowEvent.PRESS_BUTTON_A) == 2


class TestCombo:
    """combo() presses multiple buttons simultaneously via send_input."""

    def test_combo_empty_list_noop(self, emu) -> None:
        emu.combo([])
        emu._pyboy.send_input.assert_not_called()
        assert emu._pyboy.tick.call_count == 0

    def test_combo_single_button(self, emu) -> None:
        emu.combo(["a"], frames=5)
        assert emu._pyboy.send_input.call_count == 2
        emu._pyboy.tick.assert_any_call(4, render=False)
        emu._pyboy.tick.assert_any_call(1, render=True)

    def test_combo_multiple_buttons(self, emu) -> None:
        emu.combo(["a", "start"], frames=3)
        assert emu._pyboy.send_input.call_count == 4
        emu._pyboy.tick.assert_any_call(2, render=False)
        emu._pyboy.tick.assert_any_call(1, render=True)

    def test_combo_unknown_button_raises(self, emu) -> None:
        with pytest.raises(ValueError, match="Unknown button"):
            emu.combo(["a", "triangle"])


class TestCompatAliases:
    """Compatibility aliases delegate to primary methods."""

    def test_start_calls_reset(self, emu) -> None:
        with patch.object(emu, "reset") as mock_reset:
            emu.start()
            mock_reset.assert_called_once()

    def test_capture_screen_calls_capture(self, emu) -> None:
        with patch.object(
            emu, "capture", return_value=np.zeros((144, 160, 3))
        ) as mock_cap:
            result = emu.capture_screen()
            mock_cap.assert_called_once()
            assert isinstance(result, np.ndarray)

    def test_tick_calls_fast_forward(self, emu) -> None:
        emu.tick(5)
        emu._pyboy.tick.assert_called_once_with(5, render=False)

    def test_tick_defaults_to_one_frame(self, emu) -> None:
        emu.tick()
        assert emu._pyboy.tick.call_count == 1


class TestCheckpointing:
    """save_state / load_state using PyBoy serialization."""

    def test_save_state_calls_pyboy_and_writes_to_disk(self, emu_with_state) -> None:
        m_open = mock_open()
        with patch("builtins.open", m_open):
            emu_with_state.save_state(2)
            emu_with_state._pyboy.save_state.assert_called_once()
            m_open.assert_called_once()

    def test_save_state_creates_checkpoint_directory(self, emu_with_state) -> None:
        m_open = mock_open()
        with (
            patch("builtins.open", m_open),
            patch("pathlib.Path.mkdir") as mock_mkdir,
        ):
            emu_with_state.save_state(0)
            mock_mkdir.assert_called()

    def test_load_state_reads_from_disk_and_calls_pyboy(self, emu_with_state) -> None:
        with patch("builtins.open", mock_open()):
            emu_with_state.load_state(0)
            emu_with_state._pyboy.load_state.assert_called_once()

    def test_load_state_missing_slot_raises(self, emu_with_state) -> None:
        with patch("pathlib.Path.is_file", return_value=False):
            with pytest.raises(FileNotFoundError, match="Checkpoint slot 7 not found"):
                emu_with_state.load_state(7)

    def test_load_state_path_reads_exact_path(self, emu_with_state) -> None:
        """Path-based load reads the EXACT path given — no .state appended."""
        with patch("builtins.open", mock_open()) as m_open:
            emu_with_state.load_state("data/boot.state")
            args, _kwargs = m_open.call_args
            assert args[0] == Path("data/boot.state")
            emu_with_state._pyboy.load_state.assert_called_once()

    def test_load_state_path_missing_raises(self, emu_with_state) -> None:
        with patch("pathlib.Path.is_file", return_value=False):
            with pytest.raises(FileNotFoundError, match="data/boot.state"):
                emu_with_state.load_state("data/boot.state")

    def test_load_state_int_slot_still_works(self, emu_with_state) -> None:
        """Integer slot still reads checkpoints/<slot>.state."""
        with patch("builtins.open", mock_open()) as m_open:
            emu_with_state.load_state(7)
            args, _kwargs = m_open.call_args
            assert args[0] == Path("checkpoints/7.state")

    def test_save_then_load_roundtrip(self, emu_with_state) -> None:
        handle = MagicMock()
        m_save = mock_open()
        m_save.return_value = handle

        with patch("builtins.open", m_save):
            emu_with_state.save_state(1)
            emu_with_state._pyboy.save_state.assert_called_once()

        m_load = mock_open()
        with patch("builtins.open", m_load):
            emu_with_state.load_state(1)
            emu_with_state._pyboy.load_state.assert_called_once()

    def test_multiple_slots_independent(self, emu_with_state) -> None:
        open_calls: list[str] = []
        m_open = mock_open()
        with patch("builtins.open", m_open):
            emu_with_state.save_state(0)
            emu_with_state.save_state(3)
            for call_args in m_open.call_args_list:
                if len(call_args.args) >= 1:
                    open_calls.append(str(call_args.args[0]))
        assert any("0.state" in c for c in open_calls)
        assert any("3.state" in c for c in open_calls)

    # ── AP-GAP-001 regression ────────────────────────────────────────

    def test_save_state_path_creates_parent_dirs(self, emu_with_state) -> None:
        """Path-based save creates intermediate directories (no FileNotFoundError)."""
        m_open = mock_open()
        with (
            patch("builtins.open", m_open),
            patch("pathlib.Path.mkdir") as mock_mkdir,
        ):
            emu_with_state.save_state("game_saves/emulator_state.state")
            mock_mkdir.assert_called()
            m_open.assert_called_once()

    def test_save_state_path_no_double_suffix(self, emu_with_state) -> None:
        """Path-based save writes to the EXACT path given — no extra .state."""
        with patch("builtins.open", mock_open()) as m_open:
            emu_with_state.save_state("game_saves/emulator_state.state")
            args, _kwargs = m_open.call_args
            assert args[0] == Path("game_saves/emulator_state.state")

    def test_save_state_int_slot_still_works(self, emu_with_state) -> None:
        """Integer slot still writes to checkpoints/<slot>.state."""
        with patch("builtins.open", mock_open()) as m_open:
            emu_with_state.save_state(7)
            args, _kwargs = m_open.call_args
            assert args[0] == Path("checkpoints/7.state")


class TestRAMReading:
    """Memory read methods: read_u8, read_u16."""

    def test_read_u8_single_byte(self, emu) -> None:
        emu._pyboy.memory = {0xC000: 0xAB}
        assert emu.read_u8(0xC000) == 0xAB

    def test_read_u16_little_endian(self, emu) -> None:
        emu._pyboy.memory = {0xC000: 0x34, 0xC001: 0x12}
        assert emu.read_u16(0xC000) == 0x1234


_LEAK_ROM_PATH = Path("data/rom/pokemon_red.gb")


def _leak_has_rom() -> bool:
    return _LEAK_ROM_PATH.is_file()


class TestLeakRegression:
    """GAMEPLAY-LEAK-001: battle-loop native memory leak regression guards."""

    def test_pyboy_constructed_with_sound_disabled(self) -> None:
        """SDL2 audio must be disabled at construction (leak suspect b)."""
        with (
            patch("src.core.emulator._PyBoy") as mock_pyboy_cls,
            patch("pathlib.Path.is_file", return_value=True),
            patch("pathlib.Path.resolve", return_value=Path("/fake/rom.gb")),
        ):
            mock_pyboy = MagicMock()
            mock_pyboy.screen.ndarray = np.zeros((144, 160, 4), dtype=np.uint8)
            mock_pyboy_cls.return_value = mock_pyboy

            from src.core.emulator import Emulator

            Emulator("/fake/rom.gb")
            kwargs = mock_pyboy_cls.call_args.kwargs
            assert kwargs.get("sound") is False, (
                "sound=False required — SDL2 audio queue is a prime leak suspect"
            )

    def test_capture_rerenders_after_fast_forward_debt(self, emu) -> None:
        """Fast-forward skips rendering; capture re-renders exactly one frame."""
        emu.fast_forward(30)
        assert emu._render_debt == 30
        emu.capture()
        emu._pyboy.tick.assert_any_call(1, render=True)
        assert emu._render_debt == 0

    @pytest.mark.rom
    @pytest.mark.skipif(not _leak_has_rom(), reason="ROM not found at data/rom/pokemon_red.gb")
    def test_battle_loop_churn_rss_bounded(self) -> None:
        """Battle StateWindow churn (FF spans + wait + press + capture) must not grow RSS.

        Pre-fix runs leaked 70-100 MB/s during battle cycles and died at ~50 GB.
        This mirrors the animation-span pattern (fast_forward(180)+wait(60)+
        capture per cycle) without LLM calls; the bound catches render-path
        regressions deterministically.
        """
        import resource

        from src.core.emulator import Emulator

        emu = Emulator(str(_LEAK_ROM_PATH))
        try:
            emu.wait(60)
            for _ in range(12):
                emu.fast_forward(180)  # battle animation span
                emu.wait(60)
                emu.press_button("a", frames=15)
                _ = emu.capture()
            rss_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
            assert rss_mb < 1024, (
                f"RSS {rss_mb:.0f}MB after battle-churn loop — leak regression"
            )
        finally:
            emu.stop()
