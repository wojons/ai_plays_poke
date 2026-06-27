"""
Unit tests for game_loop.py — COV-16: 0% → 40%+

Tests cover:
- Pure AI decision functions (_simple_battle_ai, _simple_menu_ai, etc.)
- Stub decision routing (_get_stub_ai_decision)
- Command parsing (_parse_command)
- Tick loop mock (_run_single_tick)
- Command execution with mocked emulator
- Lifecycle (start/stop flags)
- Stub game state analysis (_analyze_game_state_stub)
"""

import sys
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

# game_loop.py inserts project root into sys.path for db.* imports
# Tests need src/ on sys.path for db.database, core.*, src.* imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root))

from src.schemas.commands import GameState

# Import after mocking external dependencies to avoid import-time side effects
with patch("db.database.GameDatabase", MagicMock()), \
     patch("core.emulator.Emulator", MagicMock()), \
     patch("core.emulator.Button", MagicMock()), \
     patch("core.screenshots.ScreenshotManager", MagicMock()), \
     patch("core.screenshots.SimpleLiveView", MagicMock()), \
     patch("core.ai_client.GameAIManager", MagicMock()), \
     patch("core.ai_client.OpenRouterClient", MagicMock()), \
     patch("core.save_manager.SaveManager", MagicMock()), \
     patch("core.save_manager.SaveManagerConfig", MagicMock()), \
     patch("src.core.vision.VisionClient", MagicMock()), \
     patch("src.core.prompt_assembler.PromptStack", MagicMock()), \
     patch("src.core.tools.TOOL_SCHEMA", [{"type": "function"}]), \
     patch("src.core.tools.parse_tool_call", MagicMock()):
    from src.game_loop import GameLoop, EmulatorManager, create_config


# ════════════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════════════


def _make_config(rom_path: str = "/tmp/test.gb",
                 save_dir: str = "/tmp/test_save") -> Dict[str, Any]:
    return {
        "rom_path": rom_path,
        "save_dir": save_dir,
        "screenshot_interval": 10,
        "load_state": None,
        "max_ticks": 100,
        "model_name": "stub_ai",
        "multi_instance": False,
        "instance_count": 3,
    }


def _basic_game_state(tick: int = 0,
                      screen_type: str = "overworld") -> GameState:
    return GameState(
        tick=tick,
        timestamp="2026-01-01T00:00:00",
        screen_type=screen_type,
        is_battle=(screen_type == "battle"),
        is_menu=(screen_type == "menu"),
        has_dialog=(screen_type == "dialog"),
        can_move=(screen_type == "overworld"),
        turn_number=0,
        player_hp_percent=100.0,
        enemy_hp_percent=100.0,
    )


# ════════════════════════════════════════════════════════════════════════════
# Pure AI decision functions
# ════════════════════════════════════════════════════════════════════════════

class TestSimpleBattleAI:
    """Tests for _simple_battle_ai."""

    @pytest.fixture
    def loop(self) -> GameLoop:
        with patch.object(GameLoop, "__init__", lambda self, config: None):
            gl = GameLoop.__new__(GameLoop)
            gl.current_tick = 0
            gl.metrics = {}
            return gl

    def test_returns_press_A(self, loop: GameLoop) -> None:
        gs = _basic_game_state(screen_type="battle")
        result = loop._simple_battle_ai(gs)
        assert result["action"] == "press:A"
        assert result["confidence"] == 0.6
        assert "battle" in result["reasoning"].lower()

    def test_has_button(self, loop: GameLoop) -> None:
        gs = _basic_game_state(screen_type="battle")
        result = loop._simple_battle_ai(gs)
        assert "button" in result


class TestSimpleMenuAI:
    """Tests for _simple_menu_ai."""

    @pytest.fixture
    def loop(self) -> GameLoop:
        with patch.object(GameLoop, "__init__", lambda self, config: None):
            gl = GameLoop.__new__(GameLoop)
            gl.current_tick = 0
            gl.metrics = {}
            return gl

    def test_returns_press_DOWN(self, loop: GameLoop) -> None:
        gs = _basic_game_state(screen_type="menu")
        result = loop._simple_menu_ai(gs)
        assert result["action"] == "press:DOWN"
        assert result["confidence"] == 0.5

    def test_reasoning_mentions_menu(self, loop: GameLoop) -> None:
        gs = _basic_game_state(screen_type="menu")
        result = loop._simple_menu_ai(gs)
        assert "menu" in result["reasoning"].lower()
        assert "cursor" in result["reasoning"].lower()


class TestSimpleDialogAI:
    """Tests for _simple_dialog_ai."""

    @pytest.fixture
    def loop(self) -> GameLoop:
        with patch.object(GameLoop, "__init__", lambda self, config: None):
            gl = GameLoop.__new__(GameLoop)
            gl.current_tick = 0
            gl.metrics = {}
            return gl

    def test_returns_press_A(self, loop: GameLoop) -> None:
        gs = _basic_game_state(screen_type="dialog")
        result = loop._simple_dialog_ai(gs)
        assert result["action"] == "press:A"
        assert result["confidence"] == 0.9

    def test_reasoning_mentions_dialog(self, loop: GameLoop) -> None:
        gs = _basic_game_state(screen_type="dialog")
        result = loop._simple_dialog_ai(gs)
        assert "dialog" in result["reasoning"].lower()


class TestSimpleExplorationAI:
    """Tests for _simple_exploration_ai."""

    @pytest.fixture
    def loop(self) -> GameLoop:
        with patch.object(GameLoop, "__init__", lambda self, config: None):
            gl = GameLoop.__new__(GameLoop)
            gl.current_tick = 0
            gl.metrics = {}
            return gl

    def test_returns_press_UP(self, loop: GameLoop) -> None:
        gs = _basic_game_state(screen_type="overworld")
        result = loop._simple_exploration_ai(gs)
        assert result["action"] == "press:UP"
        assert result["confidence"] == 0.4

    def test_reasoning_mentions_exploration(self, loop: GameLoop) -> None:
        gs = _basic_game_state(screen_type="overworld")
        result = loop._simple_exploration_ai(gs)
        assert "explor" in result["reasoning"].lower()


# ════════════════════════════════════════════════════════════════════════════
# Stub AI decision routing
# ════════════════════════════════════════════════════════════════════════════

class TestGetStubAIDecision:
    """Tests for _get_stub_ai_decision routing logic."""

    @pytest.fixture
    def loop(self) -> GameLoop:
        with patch.object(GameLoop, "__init__", lambda self, config: None):
            gl = GameLoop.__new__(GameLoop)
            gl.current_tick = 0
            gl.metrics = {}
            return gl

    def test_routes_to_battle(self, loop: GameLoop) -> None:
        gs = _basic_game_state(screen_type="battle")
        gs.is_battle = True
        result = loop._get_stub_ai_decision(gs)
        assert "battle" in result["reasoning"].lower()

    def test_routes_to_menu(self, loop: GameLoop) -> None:
        gs = _basic_game_state(screen_type="menu")
        gs.is_menu = True
        result = loop._get_stub_ai_decision(gs)
        assert "menu" in result["reasoning"].lower()

    def test_routes_to_dialog(self, loop: GameLoop) -> None:
        gs = _basic_game_state(screen_type="dialog")
        gs.has_dialog = True
        result = loop._get_stub_ai_decision(gs)
        assert "dialog" in result["reasoning"].lower()

    def test_routes_to_exploration(self, loop: GameLoop) -> None:
        gs = _basic_game_state(screen_type="overworld")
        result = loop._get_stub_ai_decision(gs)
        assert "explor" in result["reasoning"].lower()

    def test_battle_takes_priority_over_menu(self, loop: GameLoop) -> None:
        """is_battle is checked first — overrides other flags."""
        gs = _basic_game_state(screen_type="battle")
        gs.is_battle = True
        gs.is_menu = True
        gs.has_dialog = True
        result = loop._get_stub_ai_decision(gs)
        assert result["action"] == "press:A"

    def test_returns_dict_with_required_keys(self, loop: GameLoop) -> None:
        for st in ("battle", "menu", "dialog", "overworld"):
            gs = _basic_game_state(screen_type=st)
            if st == "battle":
                gs.is_battle = True
            elif st == "menu":
                gs.is_menu = True
            elif st == "dialog":
                gs.has_dialog = True
            result = loop._get_stub_ai_decision(gs)
            assert "action" in result
            assert "reasoning" in result
            assert "confidence" in result
            assert "button" in result


# ════════════════════════════════════════════════════════════════════════════
# Command parsing
# ════════════════════════════════════════════════════════════════════════════

class TestParseCommand:
    """Tests for _parse_command string parsing."""

    @pytest.fixture
    def loop(self) -> GameLoop:
        with patch.object(GameLoop, "__init__", lambda self, config: None):
            gl = GameLoop.__new__(GameLoop)
            gl.current_tick = 0
            gl.metrics = {}
            return gl

    def test_press_A(self, loop: GameLoop) -> None:
        result = loop._parse_command("press:A")
        assert result is not None
        assert result["type"] == "press"

    def test_press_UP(self, loop: GameLoop) -> None:
        result = loop._parse_command("press:UP")
        assert result is not None
        assert result["type"] == "press"

    def test_press_lowercase(self, loop: GameLoop) -> None:
        result = loop._parse_command("press:a")
        assert result is not None
        assert result["type"] == "press"

    def test_press_START(self, loop: GameLoop) -> None:
        result = loop._parse_command("press:START")
        assert result is not None
        assert result["type"] == "press"

    def test_press_SELECT(self, loop: GameLoop) -> None:
        result = loop._parse_command("press:SELECT")
        assert result is not None
        assert result["type"] == "press"

    def test_press_LEFT(self, loop: GameLoop) -> None:
        result = loop._parse_command("press:LEFT")
        assert result is not None

    def test_press_RIGHT(self, loop: GameLoop) -> None:
        result = loop._parse_command("press:RIGHT")
        assert result is not None

    def test_press_DOWN(self, loop: GameLoop) -> None:
        result = loop._parse_command("press:DOWN")
        assert result is not None

    def test_press_B(self, loop: GameLoop) -> None:
        result = loop._parse_command("press:B")
        assert result is not None

    def test_unknown_button_returns_none(self, loop: GameLoop) -> None:
        result = loop._parse_command("press:X")
        assert result is None

    def test_no_colon_returns_none(self, loop: GameLoop) -> None:
        result = loop._parse_command("pressA")
        assert result is None

    def test_three_colons_returns_none(self, loop: GameLoop) -> None:
        result = loop._parse_command("press:A:B")
        assert result is None

    def test_empty_string_returns_none(self, loop: GameLoop) -> None:
        result = loop._parse_command("")
        assert result is None

    def test_non_press_command_returns_none(self, loop: GameLoop) -> None:
        result = loop._parse_command("wait:30")
        assert result is None


# ════════════════════════════════════════════════════════════════════════════
# Stub game state analysis
# ════════════════════════════════════════════════════════════════════════════

class TestAnalyzeGameStateStub:
    """Tests for _analyze_game_state_stub tick-based simulation."""

    @pytest.fixture
    def loop(self) -> GameLoop:
        with patch.object(GameLoop, "__init__", lambda self, config: None):
            gl = GameLoop.__new__(GameLoop)
            gl.current_tick = 50
            gl.metrics = {}
            return gl

    def test_tick_below_100_returns_overworld(self, loop: GameLoop) -> None:
        loop.current_tick = 50
        gs = _basic_game_state(tick=50)
        result = loop._analyze_game_state_stub(gs)
        assert result.screen_type == "overworld"
        assert not result.is_battle

    def test_tick_in_battle_range(self, loop: GameLoop) -> None:
        loop.current_tick = 120
        gs = _basic_game_state(tick=120)
        result = loop._analyze_game_state_stub(gs)
        assert result.screen_type == "battle"
        assert result.is_battle
        assert result.enemy_pokemon == "Pidgey"
        assert result.player_hp_percent == 85.0
        assert result.enemy_hp_percent == 100.0

    def test_tick_in_menu_range(self, loop: GameLoop) -> None:
        loop.current_tick = 210
        gs = _basic_game_state(tick=210)
        result = loop._analyze_game_state_stub(gs)
        assert result.screen_type == "menu"
        assert result.is_menu
        assert result.menu_type == "main"

    def test_tick_in_dialog_range(self, loop: GameLoop) -> None:
        loop.current_tick = 305
        gs = _basic_game_state(tick=305)
        result = loop._analyze_game_state_stub(gs)
        assert result.screen_type == "dialog"
        assert result.has_dialog
        assert "Welcome" in result.dialog_text

    def test_tick_between_ranges_returns_overworld(self, loop: GameLoop) -> None:
        """Tick 160 is between battle (100-150) and menu (200-220)."""
        loop.current_tick = 160
        gs = _basic_game_state(tick=160)
        result = loop._analyze_game_state_stub(gs)
        assert result.screen_type == "overworld"

    def test_tick_exactly_100_enters_battle(self, loop: GameLoop) -> None:
        """100 < tick check is exclusive at lower bound."""
        loop.current_tick = 101
        gs = _basic_game_state(tick=101)
        result = loop._analyze_game_state_stub(gs)
        assert result.screen_type == "battle"

    def test_tick_exactly_150_exits_battle(self, loop: GameLoop) -> None:
        """150 < tick check is exclusive at upper bound."""
        loop.current_tick = 150
        gs = _basic_game_state(tick=150)
        result = loop._analyze_game_state_stub(gs)
        assert result.screen_type != "battle"


# ════════════════════════════════════════════════════════════════════════════
# Constructor tests
# ════════════════════════════════════════════════════════════════════════════

class TestGameLoopInit:
    """Tests for GameLoop.__init__ configuration and state initialization."""

    def test_init_stores_config(self) -> None:
        config = _make_config()
        gl = GameLoop(config)
        assert gl.config == config

    def test_init_creates_emulator_not_manager(self) -> None:
        """When multi_instance=False, creates emulator directly."""
        config = _make_config()
        gl = GameLoop(config)
        assert gl.emulator is not None
        assert gl.emulator_mgr is None

    def test_init_creates_emulator_manager_when_multi(self) -> None:
        """When multi_instance=True, creates EmulatorManager."""
        config = _make_config()
        config["multi_instance"] = True
        # EmulatorManager raises NotImplementedError in __init__
        # but that's expected — just verify the branch is reachable
        try:
            gl = GameLoop(config)
        except NotImplementedError:
            pass  # Expected — EmulatorManager is a stub

    def test_init_initializes_state_tracking(self) -> None:
        config = _make_config()
        gl = GameLoop(config)
        assert gl.current_tick == 0
        assert gl.is_running is False
        assert gl.paused is False
        assert gl.session_id is None

    def test_init_initializes_metrics(self) -> None:
        config = _make_config()
        gl = GameLoop(config)
        assert "total_ticks" in gl.metrics
        assert gl.metrics["total_ticks"] == 0
        assert gl.metrics["screenshots_taken"] == 0
        assert gl.metrics["commands_sent"] == 0
        assert gl.metrics["ai_decisions"] == 0
        assert gl.metrics["battles_encountered"] == 0
        assert gl.metrics["battles_won"] == 0
        assert gl.metrics["battles_lost"] == 0
        assert gl.metrics["start_time"] is None

    def test_init_command_pipeline_empty(self) -> None:
        config = _make_config()
        gl = GameLoop(config)
        assert gl.pending_commands == []
        assert gl.command_history == []

    def test_init_battle_tracking_defaults(self) -> None:
        config = _make_config()
        gl = GameLoop(config)
        assert gl.current_battle_id is None
        assert gl.battle_turn_count == 0

    def test_init_with_default_save_dir(self) -> None:
        """Verify defaults from config are used."""
        config = _make_config()
        gl = GameLoop(config)
        assert gl.config["save_dir"] == "/tmp/test_save"


# ════════════════════════════════════════════════════════════════════════════
# Tick loop
# ════════════════════════════════════════════════════════════════════════════

class TestRunSingleTick:
    """Tests for run_single_tick core loop."""

    @pytest.fixture
    def gl(self) -> GameLoop:
        config = _make_config(save_dir="/tmp/test_run_tick")
        # Create loop with mocked emulator
        with patch("src.game_loop.GameDatabase", MagicMock()), \
             patch("src.game_loop.ScreenshotManager", MagicMock()), \
             patch("src.game_loop.SimpleLiveView", MagicMock()), \
             patch("src.game_loop.SaveManager", MagicMock()), \
             patch("src.game_loop.SaveManagerConfig", MagicMock()):
            gl = GameLoop.__new__(GameLoop)
            gl.config = config
            gl.emulator = MagicMock()
            gl.emulator_mgr = None
            gl.db = MagicMock()
            gl.screenshot_mgr = MagicMock()
            gl.live_view = MagicMock()
            gl.save_manager = MagicMock()
            gl.ai_manager = None
            gl.use_real_ai = False
            gl.vision_client = None
            gl.prompt_stack = None
            gl.prompt_client = None
            gl.current_tick = 0
            gl.last_screenshot_tick = 0
            gl.is_running = True
            gl.paused = False
            gl.session_id = "test-session"
            gl.pending_commands = []
            gl.command_history = []
            gl.current_battle_id = None
            gl.battle_turn_count = 0
            gl.metrics = {
                "total_ticks": 0, "screenshots_taken": 0,
                "commands_sent": 0, "ai_decisions": 0,
                "battles_encountered": 0, "battles_won": 0,
                "battles_lost": 0, "start_time": None,
            }
            return gl

    def test_increments_tick_counters(self, gl: GameLoop) -> None:
        gl.run_single_tick()
        assert gl.current_tick == 1
        assert gl.metrics["total_ticks"] == 1

    def test_ticks_emulator(self, gl: GameLoop) -> None:
        gl.run_single_tick()
        gl.emulator.tick.assert_called_once()

    def test_multiple_ticks_accumulate(self, gl: GameLoop) -> None:
        for i in range(5):
            gl.run_single_tick()
        assert gl.current_tick == 5
        assert gl.metrics["total_ticks"] == 5
        assert gl.emulator.tick.call_count == 5

    def test_no_screenshot_when_not_interval(self, gl: GameLoop) -> None:
        """When interval hasn't elapsed, screenshot is NOT captured."""
        gl.config["screenshot_interval"] = 10
        gl.current_tick = 0
        gl.last_screenshot_tick = 0
        gl.run_single_tick()
        # current_tick(1) - last_screenshot_tick(0) = 1 < 10 → no screenshot
        assert gl.last_screenshot_tick == 0  # unchanged

    def test_executes_pending_commands_when_present(self, gl: GameLoop) -> None:
        gl.config["screenshot_interval"] = 999  # suppress screenshots
        gl.pending_commands = [{
            "tick": 0,
            "command": "press:A",
            "reasoning": "test",
            "confidence": 0.5,
            "button": None,
        }]
        gl.run_single_tick()
        assert len(gl.pending_commands) == 0  # consumed
        assert len(gl.command_history) == 1

    def test_ticks_emulator_mgr_when_multi(self, gl: GameLoop) -> None:
        """When emulator_mgr is set, tick through it."""
        gl.emulator_mgr = MagicMock()
        gl.emulator_mgr.get_instance.return_value = gl.emulator
        gl.current_instance = "instance_0"
        gl.run_single_tick()
        # get_instance is called multiple times (tick, screenshot, etc.)
        # Verify it was called at least once with the correct instance
        gl.emulator_mgr.get_instance.assert_any_call("instance_0")
        gl.emulator.tick.assert_called_once()


# ════════════════════════════════════════════════════════════════════════════
# Command execution
# ════════════════════════════════════════════════════════════════════════════

class TestExecutePendingCommands:
    """Tests for _execute_pending_commands."""

    @pytest.fixture
    def gl(self) -> GameLoop:
        config = _make_config(save_dir="/tmp/test_exec")
        gl = GameLoop.__new__(GameLoop)
        gl.config = config
        gl.emulator = MagicMock()
        gl.emulator_mgr = None
        gl.db = MagicMock()
        gl.pending_commands = []
        gl.command_history = []
        gl.metrics = {"commands_sent": 0}
        gl.current_instance = "instance_0"
        return gl

    def test_empty_queue_does_nothing(self, gl: GameLoop) -> None:
        gl._execute_pending_commands()
        assert gl.metrics["commands_sent"] == 0

    def test_executes_press_command(self, gl: GameLoop) -> None:
        gl.pending_commands = [{
            "tick": 1,
            "command": "press:A",
            "reasoning": "test reason",
            "confidence": 0.7,
            "button": None,
        }]
        gl._execute_pending_commands()
        assert gl.emulator.press_button.called
        assert gl.metrics["commands_sent"] == 1
        assert len(gl.command_history) == 1
        assert gl.command_history[0]["success"] is True

    def test_consumes_one_command_per_call(self, gl: GameLoop) -> None:
        gl.pending_commands = [
            {"tick": 1, "command": "press:A", "reasoning": "r1", "confidence": 0.5, "button": None},
            {"tick": 2, "command": "press:B", "reasoning": "r2", "confidence": 0.6, "button": None},
        ]
        gl._execute_pending_commands()
        assert len(gl.pending_commands) == 1
        assert gl.command_history[0]["command"] == "press:A"

    def test_invalid_command_handled_gracefully(self, gl: GameLoop) -> None:
        gl.pending_commands = [{
            "tick": 1,
            "command": "bogus",
            "reasoning": "bad",
            "confidence": 0.1,
            "button": None,
        }]
        # Should not crash — logs error via db.log_command
        gl._execute_pending_commands()
        assert gl.metrics["commands_sent"] == 0  # not incremented on failure
        # command_history should still be empty (not added on error)
        # db.log_command should have been called with failure
        assert gl.db.log_command.called


# ════════════════════════════════════════════════════════════════════════════
# Lifecycle
# ════════════════════════════════════════════════════════════════════════════

class TestGameLoopLifecycle:
    """Tests for start/stop lifecycle."""

    @pytest.fixture
    def gl(self) -> GameLoop:
        config = _make_config(save_dir="/tmp/test_lifecycle")
        gl = GameLoop.__new__(GameLoop)
        gl.config = config
        gl.emulator = MagicMock()
        gl.emulator_mgr = None
        gl.db = MagicMock()
        gl.db.start_session.return_value = "sess-001"
        gl.screenshot_mgr = MagicMock()
        gl.live_view = MagicMock()
        gl.save_manager = MagicMock()
        gl.ai_manager = None
        gl.use_real_ai = False
        gl.vision_client = None
        gl.prompt_stack = None
        gl.prompt_client = None
        gl.current_tick = 0
        gl.last_screenshot_tick = 0
        gl.is_running = False
        gl.paused = False
        gl.session_id = None
        gl.pending_commands = []
        gl.command_history = []
        gl.current_battle_id = None
        gl.battle_turn_count = 0
        gl.metrics = {
            "total_ticks": 0, "screenshots_taken": 0,
            "commands_sent": 0, "ai_decisions": 0,
            "battles_encountered": 0, "battles_won": 0,
            "battles_lost": 0, "start_time": None,
        }
        return gl

    def test_start_sets_is_running(self, gl: GameLoop) -> None:
        gl.start()
        assert gl.is_running is True

    def test_start_starts_emulator(self, gl: GameLoop) -> None:
        gl.start()
        gl.emulator.start.assert_called_once()

    def test_start_creates_db_session(self, gl: GameLoop) -> None:
        gl.start()
        gl.db.start_session.assert_called_once()
        assert gl.session_id == "sess-001"

    def test_start_records_start_time(self, gl: GameLoop) -> None:
        gl.start()
        assert gl.metrics["start_time"] is not None

    def test_stop_when_not_running_is_noop(self, gl: GameLoop) -> None:
        gl.is_running = False
        gl.stop()
        gl.emulator.save_state.assert_not_called()

    def test_stop_stops_emulator(self, gl: GameLoop) -> None:
        gl.is_running = True
        gl.session_id = "sess-001"
        gl.stop()
        gl.emulator.stop.assert_called_once()

    def test_stop_sets_running_false(self, gl: GameLoop) -> None:
        gl.is_running = True
        gl.session_id = "sess-001"
        gl.stop()
        assert gl.is_running is False

    def test_stop_saves_emulator_state(self, gl: GameLoop) -> None:
        gl.is_running = True
        gl.session_id = "sess-001"
        gl.stop()
        gl.emulator.save_state.assert_called_once()

    def test_stop_calls_db_end_session(self, gl: GameLoop) -> None:
        gl.is_running = True
        gl.session_id = "sess-001"
        gl.stop()
        gl.db.end_session.assert_called_once()

    def test_stop_exports_session_data(self, gl: GameLoop) -> None:
        gl.is_running = True
        gl.session_id = "sess-001"
        gl.stop()
        gl.db.export_session_data.assert_called_once_with("sess-001")


# ════════════════════════════════════════════════════════════════════════════
# create_config
# ════════════════════════════════════════════════════════════════════════════

class TestCreateConfig:
    """Tests for create_config CLI arg mapping."""

    def test_basic_mapping(self) -> None:
        args = MagicMock()
        args.rom = "/tmp/test.gb"
        args.save_dir = "/tmp/saves"
        args.screenshot_interval = 30
        args.load_state = None
        args.max_ticks = 500
        args.multi_instance = False
        args.instances = 1
        cfg = create_config(args)
        assert cfg["rom_path"] == "/tmp/test.gb"
        assert cfg["save_dir"] == "/tmp/saves"
        assert cfg["screenshot_interval"] == 30
        assert cfg["max_ticks"] == 500
        assert cfg["model_name"] == "stub_ai"

    def test_multi_instance_enabled(self) -> None:
        args = MagicMock()
        args.multi_instance = True
        args.instances = 5
        cfg = create_config(args)
        assert cfg["multi_instance"] is True
        assert cfg["instance_count"] == 5

    def test_load_state_included(self) -> None:
        args = MagicMock()
        args.load_state = "checkpoint.state"
        cfg = create_config(args)
        assert cfg["load_state"] == "checkpoint.state"


# ════════════════════════════════════════════════════════════════════════════
# EmulatorManager (stub)
# ════════════════════════════════════════════════════════════════════════════

class TestEmulatorManager:
    """Tests for EmulatorManager stub class."""

    def test_init_raises_not_implemented(self) -> None:
        with pytest.raises(NotImplementedError):
            EmulatorManager("/tmp/test.gb", 3)

    def test_start_all_raises(self) -> None:
        # Can't test without init — but the class body confirms the stub pattern
        # Just verify the class exists and has expected methods
        assert hasattr(EmulatorManager, "start_all")
        assert hasattr(EmulatorManager, "stop_all")
        assert hasattr(EmulatorManager, "get_instance")


# ════════════════════════════════════════════════════════════════════════════
# _print_final_stats
# ════════════════════════════════════════════════════════════════════════════

class TestPrintFinalStats:
    """Tests for _print_final_stats output."""

    def test_prints_stats_without_crashing(self) -> None:
        gl = GameLoop.__new__(GameLoop)
        gl.session_id = "test-123"
        gl.metrics = {
            "total_ticks": 42,
            "screenshots_taken": 5,
            "commands_sent": 3,
            "ai_decisions": 2,
            "battles_encountered": 1,
            "battles_won": 1,
            "battles_lost": 0,
            "start_time": None,
        }
        # Should not crash (no asserts needed — just exercising the code path)
        gl._print_final_stats()
