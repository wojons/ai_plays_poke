"""
Unit tests for src/core/game_loop.py — COV-20: 0% → 45%+

Tests cover:
- Pure screen-analysis functions (_detect_hp_bars, _detect_text, _detect_menu_pattern, _analyze_screenshot)
- Simple AI heuristics (_simple_battle_ai, _simple_menu_ai, _simple_exploration_ai)
- Constructor with mocked dependencies
- Lifecycle (start/stop) with mocked emulator + DB
- Tick loop with mocked components
- Command execution pipeline
- AI decision routing (async via asyncio.run)
- Battle transition detection
"""

import asyncio
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import pytest

# Import the module under test at top level so coverage tracking works
from src.core.game_loop import GameLoop


# ---------------------------------------------------------------------------
# Pure functions — no mocking needed
# ---------------------------------------------------------------------------

class TestDetectHPBars:
    """Tests for _detect_hp_bars — color-based HP bar detection."""

    @pytest.fixture
    def gl(self):
        from src.core.game_loop import GameLoop
        with patch("src.core.game_loop.Emulator"), \
             patch("src.core.game_loop.GameDatabase"), \
             patch("src.core.game_loop.ScreenshotManager"):
            gl = GameLoop(rom_path=Path("/fake/rom.gb"), save_dir=Path("/tmp"))
            return gl

    def test_detects_red_bar(self, gl):
        region = np.zeros((20, 50, 3), dtype=np.uint8)
        region[5:15, 5:45] = [255, 0, 0]
        assert gl._detect_hp_bars(region) is True

    def test_detects_green_bar(self, gl):
        region = np.zeros((20, 50, 3), dtype=np.uint8)
        region[5:15, 5:45] = [0, 255, 0]
        assert gl._detect_hp_bars(region) is True

    def test_detects_mixed_red_green(self, gl):
        region = np.zeros((20, 50, 3), dtype=np.uint8)
        region[5:10, 5:25] = [255, 0, 0]
        region[10:15, 25:45] = [0, 255, 0]
        assert gl._detect_hp_bars(region) is True

    def test_black_region_no_bar(self, gl):
        region = np.zeros((20, 50, 3), dtype=np.uint8)
        assert gl._detect_hp_bars(region) is False

    def test_blue_region_no_bar(self, gl):
        region = np.zeros((20, 50, 3), dtype=np.uint8)
        region[:, :] = [0, 0, 255]
        assert gl._detect_hp_bars(region) is False

    def test_white_region_no_bar(self, gl):
        region = np.zeros((20, 50, 3), dtype=np.uint8)
        region[:, :] = [255, 255, 255]
        assert gl._detect_hp_bars(region) is False

    def test_below_threshold(self, gl):
        region = np.zeros((20, 50, 3), dtype=np.uint8)
        region[0, 0] = [255, 0, 0]
        assert gl._detect_hp_bars(region) is False

    def test_above_threshold(self, gl):
        region = np.zeros((10, 10, 3), dtype=np.uint8)
        region[0:8, 0:7] = [255, 0, 0]  # 56 red pixels
        assert gl._detect_hp_bars(region) is True

    def test_tiny_region(self, gl):
        region = np.zeros((1, 1, 3), dtype=np.uint8)
        assert gl._detect_hp_bars(region) is False


class TestDetectText:
    """Tests for _detect_text — contrast-based text detection."""

    @pytest.fixture
    def gl(self):
        from src.core.game_loop import GameLoop
        with patch("src.core.game_loop.Emulator"), \
             patch("src.core.game_loop.GameDatabase"), \
             patch("src.core.game_loop.ScreenshotManager"):
            gl = GameLoop(rom_path=Path("/fake/rom.gb"), save_dir=Path("/tmp"))
            return gl

    def test_high_contrast_is_text(self, gl):
        region = np.zeros((40, 100, 3), dtype=np.uint8)
        region[10:30, 20:80] = [255, 255, 255]
        assert gl._detect_text(region) is True

    def test_low_contrast_no_text(self, gl):
        region = np.ones((40, 100, 3), dtype=np.uint8) * 128
        assert gl._detect_text(region) is False

    def test_solid_black_no_text(self, gl):
        region = np.zeros((40, 100, 3), dtype=np.uint8)
        assert gl._detect_text(region) is False

    def test_solid_white_no_text(self, gl):
        region = np.ones((40, 100, 3), dtype=np.uint8) * 255
        assert gl._detect_text(region) is False

    def test_alternating_pattern_is_text(self, gl):
        row = np.tile([0, 255], 50)
        gray_tile = np.tile(row, (20, 1))
        region = np.stack([gray_tile] * 3, axis=-1).astype(np.uint8)
        assert gl._detect_text(region) is True

    def test_just_below_threshold(self, gl):
        region = np.ones((40, 100, 3), dtype=np.uint8) * 128
        region[20, 50] = [150, 150, 150]
        assert gl._detect_text(region) is False


class TestDetectMenuPattern:
    """Tests for _detect_menu_pattern — edge-detection-based menu grid."""

    @pytest.fixture
    def gl(self):
        from src.core.game_loop import GameLoop
        with patch("src.core.game_loop.Emulator"), \
             patch("src.core.game_loop.GameDatabase"), \
             patch("src.core.game_loop.ScreenshotManager"):
            gl = GameLoop(rom_path=Path("/fake/rom.gb"), save_dir=Path("/tmp"))
            return gl

    def test_grid_pattern_is_menu(self, gl):
        region = np.zeros((100, 100, 3), dtype=np.uint8)
        region[20, :] = [255, 255, 255]
        region[40, :] = [255, 255, 255]
        region[60, :] = [255, 255, 255]
        region[80, :] = [255, 255, 255]
        region[:, 25] = [255, 255, 255]
        region[:, 50] = [255, 255, 255]
        region[:, 75] = [255, 255, 255]
        result = gl._detect_menu_pattern(region)
        assert isinstance(result, bool)

    def test_blank_region_no_menu(self, gl):
        region = np.zeros((100, 100, 3), dtype=np.uint8)
        assert gl._detect_menu_pattern(region) is False

    def test_noise_region_no_menu(self, gl):
        rng = np.random.RandomState(42)
        region = rng.randint(0, 256, (100, 100, 3), dtype=np.uint8)
        result = gl._detect_menu_pattern(region)
        assert isinstance(result, bool)

    def test_1x1_region(self, gl):
        region = np.zeros((1, 1, 3), dtype=np.uint8)
        assert gl._detect_menu_pattern(region) is False


class TestAnalyzeScreenshot:
    """Tests for _analyze_screenshot — composite game state detection."""

    @pytest.fixture
    def gl(self):
        from src.core.game_loop import GameLoop
        with patch("src.core.game_loop.Emulator"), \
             patch("src.core.game_loop.GameDatabase"), \
             patch("src.core.game_loop.ScreenshotManager"):
            gl = GameLoop(rom_path=Path("/fake/rom.gb"), save_dir=Path("/tmp"))
            return gl

    def test_empty_screen_no_state(self, gl):
        screen = np.zeros((240, 160, 3), dtype=np.uint8)
        result = gl._analyze_screenshot(screen)
        assert result["is_battle"] is False
        assert result["has_dialog"] is False
        assert result["is_menu"] is False
        assert result["requires_ai_decision"] is False

    def test_battle_detected(self, gl):
        screen = np.zeros((240, 160, 3), dtype=np.uint8)
        screen[5:15, 5:45] = [255, 0, 0]
        result = gl._analyze_screenshot(screen)
        assert result["is_battle"] is True
        assert result["requires_ai_decision"] is True

    def test_dialog_detected(self, gl):
        screen = np.zeros((240, 160, 3), dtype=np.uint8)
        screen[200:240, :] = [255, 255, 255]
        screen[215:225, 20:140] = [0, 0, 0]
        result = gl._analyze_screenshot(screen)
        assert result["has_dialog"] is True
        assert result["requires_ai_decision"] is True

    def test_all_states(self, gl):
        screen = np.zeros((240, 160, 3), dtype=np.uint8)
        screen[5:15, 5:45] = [255, 0, 0]
        screen[200:240, :] = [255, 255, 255]
        screen[215:225, 20:140] = [0, 0, 0]
        result = gl._analyze_screenshot(screen)
        assert result["is_battle"] is True
        assert result["has_dialog"] is True

    def test_tiny_screen(self, gl):
        screen = np.zeros((10, 10, 3), dtype=np.uint8)
        result = gl._analyze_screenshot(screen)
        assert "is_battle" in result
        assert "requires_ai_decision" in result

    def test_wide_screen(self, gl):
        screen = np.zeros((240, 320, 3), dtype=np.uint8)
        result = gl._analyze_screenshot(screen)
        assert isinstance(result["is_battle"], bool)


class TestSimpleAIHeuristics:
    """Tests for _simple_battle_ai, _simple_menu_ai, _simple_exploration_ai."""

    @pytest.fixture
    def gl(self):
        from src.core.game_loop import GameLoop
        with patch("src.core.game_loop.Emulator"), \
             patch("src.core.game_loop.GameDatabase"), \
             patch("src.core.game_loop.ScreenshotManager"):
            gl = GameLoop(rom_path=Path("/fake/rom.gb"), save_dir=Path("/tmp"))
            return gl

    def test_battle_ai_returns_dict(self, gl):
        result = gl._simple_battle_ai()
        assert isinstance(result, dict)
        assert result["action"] == "press:A"
        assert "reasoning" in result
        assert 0 <= result["confidence"] <= 1

    def test_menu_ai_returns_dict(self, gl):
        result = gl._simple_menu_ai()
        assert result["action"] == "press:DOWN"
        assert result["confidence"] == 0.5

    def test_exploration_ai_returns_dict(self, gl):
        result = gl._simple_exploration_ai()
        assert result["action"] == "press:UP"
        assert result["confidence"] == 0.4

    def test_all_three_return_different_actions(self, gl):
        actions = {
            gl._simple_battle_ai()["action"],
            gl._simple_menu_ai()["action"],
            gl._simple_exploration_ai()["action"],
        }
        assert len(actions) == 3


# ---------------------------------------------------------------------------
# Constructor and lifecycle — with mocked dependencies
# ---------------------------------------------------------------------------

class TestGameLoopInit:
    """Tests for GameLoop.__init__ with mocked dependencies."""

    def test_constructor_stores_rom_path(self):
        from src.core.game_loop import GameLoop
        with patch("src.core.game_loop.Emulator"), \
             patch("src.core.game_loop.GameDatabase"), \
             patch("src.core.game_loop.ScreenshotManager"):
            gl = GameLoop(rom_path=Path("/fake/rom.gb"), save_dir=Path("/tmp/saves"))
            assert gl.rom_path == Path("/fake/rom.gb")

    def test_constructor_creates_emulator(self):
        from src.core.game_loop import GameLoop
        with patch("src.core.game_loop.Emulator") as mock_emu, \
             patch("src.core.game_loop.GameDatabase"), \
             patch("src.core.game_loop.ScreenshotManager"):
            gl = GameLoop(rom_path=Path("/fake/rom.gb"), save_dir=Path("/tmp"))
            mock_emu.assert_called_once_with(str(Path("/fake/rom.gb")))

    def test_constructor_creates_database(self):
        from src.core.game_loop import GameLoop
        with patch("src.core.game_loop.Emulator"), \
             patch("src.core.game_loop.GameDatabase") as mock_db, \
             patch("src.core.game_loop.ScreenshotManager"):
            gl = GameLoop(rom_path=Path("/fake/rom.gb"), save_dir=Path("/tmp/saves"))
            mock_db.assert_called_once()

    def test_default_interval_values(self):
        from src.core.game_loop import GameLoop
        with patch("src.core.game_loop.Emulator"), \
             patch("src.core.game_loop.GameDatabase"), \
             patch("src.core.game_loop.ScreenshotManager"):
            gl = GameLoop(rom_path=Path("/fake/rom.gb"), save_dir=Path("/tmp"))
            assert gl.screenshot_interval == 1.0
            assert gl.ai_response_delay == 0.5

    def test_custom_interval_values(self):
        from src.core.game_loop import GameLoop
        with patch("src.core.game_loop.Emulator"), \
             patch("src.core.game_loop.GameDatabase"), \
             patch("src.core.game_loop.ScreenshotManager"):
            gl = GameLoop(rom_path=Path("/fake/rom.gb"), save_dir=Path("/tmp"),
                          screenshot_interval=2.5, ai_response_delay=0.1)
            assert gl.screenshot_interval == 2.5
            assert gl.ai_response_delay == 0.1

    def test_initial_state_values(self):
        from src.core.game_loop import GameLoop
        with patch("src.core.game_loop.Emulator"), \
             patch("src.core.game_loop.GameDatabase"), \
             patch("src.core.game_loop.ScreenshotManager"):
            gl = GameLoop(rom_path=Path("/fake/rom.gb"), save_dir=Path("/tmp"))
            assert gl.current_tick == 0
            assert gl.last_screenshot_time == 0
            assert gl.is_running is False
            assert gl.paused is False
            assert gl.pending_commands == []
            assert gl.command_history == []

    def test_metrics_initialized(self):
        from src.core.game_loop import GameLoop
        with patch("src.core.game_loop.Emulator"), \
             patch("src.core.game_loop.GameDatabase"), \
             patch("src.core.game_loop.ScreenshotManager"):
            gl = GameLoop(rom_path=Path("/fake/rom.gb"), save_dir=Path("/tmp"))
            assert gl.metrics["total_ticks"] == 0
            assert gl.metrics["screenshots_taken"] == 0
            assert gl.metrics["commands_sent"] == 0
            assert gl.metrics["battles_encountered"] == 0
            assert gl.metrics["start_time"] is None


class TestGameLoopLifecycle:
    """Tests for start() and stop() with mocked dependencies."""

    def _make_gl(self):
        from src.core.game_loop import GameLoop
        with patch("src.core.game_loop.Emulator"), \
             patch("src.core.game_loop.GameDatabase"), \
             patch("src.core.game_loop.ScreenshotManager"):
            gl = GameLoop(rom_path=Path("/fake/rom.gb"), save_dir=Path("/tmp"))
            gl.emulator = MagicMock()
            gl.db = MagicMock()
            gl.screenshot_manager = MagicMock()
            return gl

    def test_start_sets_running(self):
        gl = self._make_gl()
        gl.start()
        assert gl.is_running is True

    def test_start_calls_emulator_start(self):
        gl = self._make_gl()
        gl.start()
        gl.emulator.start.assert_called_once()

    def test_start_sets_start_time(self):
        gl = self._make_gl()
        gl.start()
        assert gl.metrics["start_time"] is not None

    def test_stop_when_not_running_returns(self):
        gl = self._make_gl()
        gl.is_running = False
        gl.metrics["start_time"] = None
        gl.stop()
        gl.emulator.save_state.assert_not_called()

    def test_stop_saves_emulator_state(self):
        gl = self._make_gl()
        gl.is_running = True
        gl.metrics["start_time"] = None
        gl.stop()
        gl.emulator.save_state.assert_called_once()

    def test_stop_stops_emulator(self):
        gl = self._make_gl()
        gl.is_running = True
        gl.metrics["start_time"] = None
        gl.stop()
        gl.emulator.stop.assert_called_once()

    def test_stop_sets_running_false(self):
        gl = self._make_gl()
        gl.is_running = True
        gl.metrics["start_time"] = None
        gl.stop()
        assert gl.is_running is False

    def test_stop_logs_metrics(self):
        gl = self._make_gl()
        gl.is_running = True
        gl.metrics["start_time"] = None
        gl.stop()
        gl.db.log_session_metrics.assert_called_once()


class TestRunSingleTick:
    """Tests for run_single_tick() with mocked dependencies."""

    def _make_gl(self):
        from src.core.game_loop import GameLoop
        with patch("src.core.game_loop.Emulator"), \
             patch("src.core.game_loop.GameDatabase"), \
             patch("src.core.game_loop.ScreenshotManager"):
            gl = GameLoop(rom_path=Path("/fake/rom.gb"), save_dir=Path("/tmp"))
            gl.emulator = MagicMock()
            gl.db = MagicMock()
            gl.screenshot_manager = MagicMock()
            gl._capture_and_process_screenshot = MagicMock()
            gl._detect_battle_transition = MagicMock()
            return gl

    def test_tick_increments_counter(self):
        gl = self._make_gl()
        gl.run_single_tick()
        assert gl.current_tick == 1

    def test_tick_calls_emulator_tick(self):
        gl = self._make_gl()
        gl.run_single_tick()
        gl.emulator.tick.assert_called_once()

    def test_tick_updates_total_ticks_metric(self):
        gl = self._make_gl()
        gl.run_single_tick()
        assert gl.metrics["total_ticks"] == 1

    def test_multiple_ticks_increment(self):
        gl = self._make_gl()
        for _ in range(5):
            gl.run_single_tick()
        assert gl.current_tick == 5

    def test_tick_captures_screenshot_on_interval(self):
        gl = self._make_gl()
        gl.last_screenshot_time = 0
        gl.screenshot_interval = 0.0
        gl.run_single_tick()
        gl._capture_and_process_screenshot.assert_called_once()

    def test_tick_skips_screenshot_if_not_interval(self):
        gl = self._make_gl()
        gl.last_screenshot_time = time.time() + 999
        gl.run_single_tick()
        gl._capture_and_process_screenshot.assert_not_called()

    def test_tick_executes_pending_commands(self):
        gl = self._make_gl()
        gl.pending_commands = [{"command": "press:A"}]
        gl.run_single_tick()
        assert len(gl.pending_commands) == 0

    def test_tick_detects_battle_transition(self):
        gl = self._make_gl()
        gl.run_single_tick()
        gl._detect_battle_transition.assert_called_once()


class TestExecutePendingCommands:
    """Tests for _execute_pending_commands() with mocked emulator + DB."""

    def _make_gl(self):
        from src.core.game_loop import GameLoop
        with patch("src.core.game_loop.Emulator"), \
             patch("src.core.game_loop.GameDatabase"), \
             patch("src.core.game_loop.ScreenshotManager"):
            gl = GameLoop(rom_path=Path("/fake/rom.gb"), save_dir=Path("/tmp"))
            gl.emulator = MagicMock()
            gl.db = MagicMock()
            gl.screenshot_manager = MagicMock()
            return gl

    def test_empty_queue_noop(self):
        gl = self._make_gl()
        gl._execute_pending_commands()
        gl.emulator.press_button.assert_not_called()

    def test_press_a_executes(self):
        gl = self._make_gl()
        gl.pending_commands = [{"command": "press:A", "reasoning": "test", "confidence": 0.9}]
        gl._execute_pending_commands()
        gl.emulator.press_button.assert_called_once()

    def test_press_down_executes(self):
        gl = self._make_gl()
        gl.pending_commands = [{"command": "press:DOWN", "reasoning": "menu", "confidence": 0.5}]
        gl._execute_pending_commands()
        gl.emulator.press_button.assert_called_once()

    def test_unknown_button_logs_error(self):
        gl = self._make_gl()
        gl.pending_commands = [{"command": "press:NOTABUTTON", "reasoning": "test", "confidence": 0.5}]
        gl._execute_pending_commands()
        gl.emulator.press_button.assert_not_called()

    def test_press_start_executes(self):
        gl = self._make_gl()
        gl.pending_commands = [{"command": "press:START", "reasoning": "menu", "confidence": 0.5}]
        gl._execute_pending_commands()
        gl.emulator.press_button.assert_called_once()

    def test_press_select_executes(self):
        gl = self._make_gl()
        gl.pending_commands = [{"command": "press:SELECT", "reasoning": "test", "confidence": 0.5}]
        gl._execute_pending_commands()
        gl.emulator.press_button.assert_called_once()

    def test_command_without_colon_handled(self):
        gl = self._make_gl()
        gl.pending_commands = [{"command": "pressA", "reasoning": "bad format", "confidence": 0.5}]
        gl._execute_pending_commands()  # should not crash

    def test_sequence_command_does_not_execute_button(self):
        gl = self._make_gl()
        gl.pending_commands = [{"command": "sequence:UP,DOWN", "reasoning": "seq", "confidence": 0.5}]
        gl._execute_pending_commands()
        gl.emulator.press_button.assert_not_called()

    def test_batch_command_does_not_execute_button(self):
        gl = self._make_gl()
        gl.pending_commands = [{"command": "batch:something", "reasoning": "batch", "confidence": 0.5}]
        gl._execute_pending_commands()
        gl.emulator.press_button.assert_not_called()

    def test_command_appended_to_history(self):
        gl = self._make_gl()
        gl.pending_commands = [{"command": "press:A", "reasoning": "hist", "confidence": 0.8}]
        gl._execute_pending_commands()
        assert len(gl.command_history) == 1
        assert gl.command_history[0]["success"] is True

    def test_metrics_commands_sent_incremented(self):
        gl = self._make_gl()
        gl.pending_commands = [{"command": "press:A", "reasoning": "m", "confidence": 0.8}]
        gl._execute_pending_commands()
        assert gl.metrics["commands_sent"] == 1


class TestGetAIDecision:
    """Tests for _get_ai_decision() async routing — using asyncio.run()."""

    def _make_gl(self):
        from src.core.game_loop import GameLoop
        with patch("src.core.game_loop.Emulator"), \
             patch("src.core.game_loop.GameDatabase"), \
             patch("src.core.game_loop.ScreenshotManager"):
            gl = GameLoop(rom_path=Path("/fake/rom.gb"), save_dir=Path("/tmp"))
            gl.db = MagicMock()
            gl.current_tick = 42
            return gl

    def test_battle_state_routes_to_battle_ai(self):
        gl = self._make_gl()
        result = asyncio.run(gl._get_ai_decision(
            {"is_battle": True, "is_menu": False, "requires_ai_decision": True}))
        assert result["action"] == "press:A"
        assert gl.pending_commands[0]["command"] == "press:A"

    def test_menu_state_routes_to_menu_ai(self):
        gl = self._make_gl()
        result = asyncio.run(gl._get_ai_decision(
            {"is_battle": False, "is_menu": True, "requires_ai_decision": True}))
        assert result["action"] == "press:DOWN"

    def test_default_routes_to_exploration_ai(self):
        gl = self._make_gl()
        result = asyncio.run(gl._get_ai_decision(
            {"is_battle": False, "is_menu": False, "requires_ai_decision": True}))
        assert result["action"] == "press:UP"

    def test_battle_takes_priority_over_menu(self):
        gl = self._make_gl()
        result = asyncio.run(gl._get_ai_decision(
            {"is_battle": True, "is_menu": True, "requires_ai_decision": True}))
        assert result["action"] == "press:A"

    def test_pending_commands_populated(self):
        gl = self._make_gl()
        asyncio.run(gl._get_ai_decision(
            {"is_battle": False, "is_menu": False, "requires_ai_decision": True}))
        assert len(gl.pending_commands) == 1
        assert gl.pending_commands[0]["tick"] == 42


class TestDetectBattleTransition:
    """Tests for _detect_battle_transition() with mocked deps."""

    def _make_gl(self):
        from src.core.game_loop import GameLoop
        with patch("src.core.game_loop.Emulator"), \
             patch("src.core.game_loop.GameDatabase"), \
             patch("src.core.game_loop.ScreenshotManager"):
            gl = GameLoop(rom_path=Path("/fake/rom.gb"), save_dir=Path("/tmp"))
            gl.emulator = MagicMock()
            gl.db = MagicMock()
            return gl

    def test_skips_when_not_divisible_by_60(self):
        gl = self._make_gl()
        gl.current_tick = 42
        gl._detect_battle_transition()
        gl.emulator.capture_screen.assert_not_called()

    def test_checks_at_tick_60(self):
        gl = self._make_gl()
        gl.current_tick = 60
        gl.emulator.capture_screen.return_value = np.zeros((240, 160, 3), dtype=np.uint8)
        gl._detect_battle_transition()
        gl.emulator.capture_screen.assert_called_once()

    def test_battle_start_detected(self):
        gl = self._make_gl()
        gl.current_tick = 120
        screen = np.zeros((240, 160, 3), dtype=np.uint8)
        screen[5:15, 5:45] = [255, 0, 0]
        gl.emulator.capture_screen.return_value = screen
        gl._detect_battle_transition()
        assert hasattr(gl, '_was_battling')
        assert gl._was_battling is True
        gl.db.log_battle_start.assert_called_once()

    def test_battle_end_detected(self):
        gl = self._make_gl()
        gl.current_tick = 180
        gl._was_battling = True
        gl.emulator.capture_screen.return_value = np.zeros((240, 160, 3), dtype=np.uint8)
        gl._detect_battle_transition()
        assert not hasattr(gl, '_was_battling')


# ---------------------------------------------------------------------------
# Integration
# ---------------------------------------------------------------------------

class TestGameLoopIntegration:
    """End-to-end tests with all deps mocked."""

    def test_full_lifecycle(self):
        from src.core.game_loop import GameLoop
        with patch("src.core.game_loop.Emulator") as mock_emu_cls, \
             patch("src.core.game_loop.GameDatabase") as mock_db_cls, \
             patch("src.core.game_loop.ScreenshotManager") as mock_ss_cls:
            mock_emu = MagicMock()
            mock_db = MagicMock()
            mock_ss = MagicMock()
            mock_emu_cls.return_value = mock_emu
            mock_db_cls.return_value = mock_db
            mock_ss_cls.return_value = mock_ss

            gl = GameLoop(rom_path=Path("/fake/rom.gb"), save_dir=Path("/tmp"))
            assert gl.is_running is False

            gl.start()
            assert gl.is_running is True
            mock_emu.start.assert_called_once()

            gl.metrics["start_time"] = None
            gl.stop()
            assert gl.is_running is False
            mock_emu.stop.assert_called_once()
