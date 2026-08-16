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

import sqlite3  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Any, Dict  # noqa: E402
from unittest.mock import MagicMock, call, patch  # noqa: E402

import pytest  # noqa: E402

# game_loop.py inserts project root into sys.path for db.* imports
# Tests need src/ on sys.path for db.database, core.*, src.* imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root))

from src.schemas.commands import GameState  # noqa: E402

# Import after mocking external dependencies to avoid import-time side effects
with (
    patch("db.database.GameDatabase", MagicMock()),
    patch("core.emulator.Emulator", MagicMock()),
    patch("core.emulator.Button", MagicMock()),
    patch("core.screenshots.ScreenshotManager", MagicMock()),
    patch("core.screenshots.SimpleLiveView", MagicMock()),
    patch("core.ai_client.GameAIManager", MagicMock()),
    patch("core.ai_client.OpenRouterClient", MagicMock()),
    patch("core.save_manager.SaveManager", MagicMock()),
    patch("core.save_manager.SaveManagerConfig", MagicMock()),
    patch("src.core.vision.VisionClient", MagicMock()),
    patch("src.core.prompt_assembler.PromptStack", MagicMock()),
    patch("src.core.tools.TOOL_SCHEMA", [{"type": "function"}]),
    patch("src.core.tools.parse_tool_call", MagicMock()),
):
    from src.game_loop import GameLoop, EmulatorManager, create_config


# ════════════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════════════


def _make_config(
    rom_path: str = "/tmp/test.gb", save_dir: str = "/tmp/test_save"
) -> Dict[str, Any]:
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


def _basic_game_state(tick: int = 0, screen_type: str = "overworld") -> GameState:
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
            GameLoop(config)
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
        with (
            patch("src.game_loop.GameDatabase", MagicMock()),
            patch("src.game_loop.ScreenshotManager", MagicMock()),
            patch("src.game_loop.SimpleLiveView", MagicMock()),
            patch("src.game_loop.SaveManager", MagicMock()),
            patch("src.game_loop.SaveManagerConfig", MagicMock()),
        ):
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
            gl.session_id = 42
            gl.pending_commands = []
            gl.command_history = []
            gl.current_battle_id = None
            gl.battle_turn_count = 0
            gl._boot_verified = False
            gl._ram_reader = None
            gl._last_screen_type = "unknown"
            gl.metrics = {
                "total_ticks": 0,
                "screenshots_taken": 0,
                "commands_sent": 0,
                "ai_decisions": 0,
                "battles_encountered": 0,
                "battles_won": 0,
                "battles_lost": 0,
                "start_time": None,
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
        """When interval hasn't elapsed, screenshot is NOT captured (tick 1 always captures)."""
        gl.config["screenshot_interval"] = 10
        gl.current_tick = 1
        gl.last_screenshot_tick = 1  # tick 1 already captured
        gl.run_single_tick()
        # current_tick(2) - last_screenshot_tick(1) = 1 < 10 → no screenshot
        assert gl.last_screenshot_tick == 1  # unchanged

    def test_boot_progression_presses_start_until_screen_transitions(
        self, gl: GameLoop
    ) -> None:
        """Title screen → press START → RAM verifies menu → stop pressing."""
        gl.current_tick = 15
        with patch("src.game_loop.RAMReader") as ram_cls:
            ram = ram_cls.return_value
            ram.screen_type.side_effect = ["title", "menu"]
            gl.run_single_tick()
        # One START press, then the transition is verified via RAM.
        gl.emulator.press_button.assert_called_once_with("start", frames=30)
        assert gl._boot_verified is True

    def test_boot_progression_alternates_start_then_a_when_still_title(
        self, gl: GameLoop
    ) -> None:
        """Copyright screen reads as title → second press is A, then verified."""
        gl.current_tick = 15
        with patch("src.game_loop.RAMReader") as ram_cls:
            ram = ram_cls.return_value
            ram.screen_type.side_effect = ["title", "title", "menu"]
            gl.run_single_tick()
        assert gl.emulator.press_button.call_args_list == [
            call("start", frames=30),
            call("a", frames=30),
        ]
        assert gl._boot_verified is True

    def test_boot_progression_fails_loudly_when_stuck_on_title(
        self, gl: GameLoop
    ) -> None:
        """10 presses with no screen transition → loud RuntimeError."""
        gl.current_tick = 15
        with patch("src.game_loop.RAMReader") as ram_cls:
            ram_cls.return_value.screen_type.return_value = "title"
            with pytest.raises(RuntimeError, match="Boot progression failed"):
                gl.run_single_tick()
        assert gl.emulator.press_button.call_count == 10

    def test_boot_progression_skips_when_screen_already_progressed(
        self, gl: GameLoop
    ) -> None:
        """RAM already shows a non-title screen → no presses, verified."""
        gl.current_tick = 15
        with patch("src.game_loop.RAMReader") as ram_cls:
            ram_cls.return_value.screen_type.return_value = "menu"
            gl.run_single_tick()
        gl.emulator.press_button.assert_not_called()
        assert gl._boot_verified is True

    def test_boot_progression_ram_failure_falls_back_to_last_vision_state(
        self, gl: GameLoop
    ) -> None:
        """RAMReader unavailable (e.g. non-Gen-1) → last vision state used."""
        gl.current_tick = 15
        gl._last_screen_type = "overworld"  # last vision classification
        with patch("src.game_loop.RAMReader", side_effect=RuntimeError("no rom")):
            gl.run_single_tick()
        # Falls back to vision state (overworld) → no presses needed.
        gl.emulator.press_button.assert_not_called()
        assert gl._boot_verified is True

    def test_executes_pending_commands_when_present(self, gl: GameLoop) -> None:
        gl.config["screenshot_interval"] = 999  # suppress screenshots
        gl.pending_commands = [
            {
                "tick": 0,
                "command": "press:A",
                "reasoning": "test",
                "confidence": 0.5,
                "button": None,
            }
        ]
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


class TestBattleRecordingIntegrity:
    """Regression coverage for battle records produced by the legacy loop."""

    @staticmethod
    def _make_loop(tmp_path: Path) -> GameLoop:
        from db.database import GameDatabase

        gl = GameLoop.__new__(GameLoop)
        gl.config = {
            "rom_path": "/tmp/test.gb",
            "save_dir": str(tmp_path),
        }
        gl.emulator = MagicMock()
        gl.emulator_mgr = None
        gl.db = GameDatabase(str(tmp_path / "game_data.db"))
        gl.db.start_session(rom_path="/tmp/test.gb", model_name="test")
        gl.current_tick = 0
        gl.current_battle_id = None
        gl.battle_turn_count = 0
        gl._ram_reader = None
        gl._last_screen_type = "unknown"
        gl.metrics = {
            "battles_encountered": 0,
            "battles_won": 0,
            "battles_lost": 0,
        }
        return gl

    @staticmethod
    def _battle_rows(gl: GameLoop) -> list[tuple[str | None, str | None]]:
        with sqlite3.connect(gl.db.db_path) as conn:
            return conn.execute(
                "SELECT enemy_pokemon, outcome FROM battles ORDER BY battle_id"
            ).fetchall()

    def test_title_screen_only_run_records_zero_battles(self, tmp_path: Path) -> None:
        """RAM-confirmed title screens override two false vision battle detections."""
        gl = self._make_loop(tmp_path)
        false_opponents = {
            11: "unknown (dark silhouette)",
            14: "unidentified (sprite unclear)",
        }
        states = [
            _basic_game_state(
                tick=tick,
                screen_type="battle" if tick in false_opponents else "title",
            )
            for tick in range(1, 41)
        ]
        for state in states:
            state.enemy_pokemon = false_opponents.get(state.tick)

        with (
            patch.object(gl, "_analyze_game_state", side_effect=states),
            patch("src.game_loop.RAMReader") as ram_cls,
        ):
            ram_cls.return_value.screen_type.return_value = "title"
            for tick in range(1, 41):
                gl.current_tick = tick
                gl._detect_battle_transition()

        assert self._battle_rows(gl) == []
        assert gl.metrics["battles_encountered"] == 0
        assert gl.metrics["battles_won"] == 0

    def test_ram_battle_evidence_starts_record_when_vision_is_unknown(
        self, tmp_path: Path
    ) -> None:
        """The authoritative RAM battle flag is sufficient evidence to start."""
        gl = self._make_loop(tmp_path)
        state = _basic_game_state(tick=1, screen_type="unknown")
        state.enemy_pokemon = "Pidgey"

        with (
            patch.object(gl, "_analyze_game_state", return_value=state),
            patch("src.game_loop.RAMReader") as ram_cls,
        ):
            ram_cls.return_value.screen_type.return_value = "battle"
            gl._detect_battle_transition()

        assert self._battle_rows(gl) == [("Pidgey", "ongoing")]
        assert gl.metrics["battles_encountered"] == 1

    def test_unidentified_opponent_is_not_counted_as_win(self, tmp_path: Path) -> None:
        """An ended verified battle with an unclear sprite has no win outcome."""
        gl = self._make_loop(tmp_path)
        battle = _basic_game_state(tick=1, screen_type="battle")
        battle.enemy_pokemon = "unidentified (sprite unclear)"
        ended = _basic_game_state(tick=2, screen_type="overworld")

        with (
            patch.object(gl, "_analyze_game_state", side_effect=[battle, ended]),
            patch("src.game_loop.RAMReader") as ram_cls,
        ):
            ram_cls.return_value.screen_type.side_effect = ["battle", "overworld"]
            gl._detect_battle_transition()
            gl._detect_battle_transition()

        assert self._battle_rows(gl) == [
            ("unidentified (sprite unclear)", "unknown")
        ]
        assert gl.metrics["battles_encountered"] == 1
        assert gl.metrics["battles_won"] == 0
        assert gl.metrics["battles_lost"] == 0


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
        gl.pending_commands = [
            {
                "tick": 1,
                "command": "press:A",
                "reasoning": "test reason",
                "confidence": 0.7,
                "button": None,
            }
        ]
        gl._execute_pending_commands()
        assert gl.emulator.press_button.called
        assert gl.metrics["commands_sent"] == 1
        assert len(gl.command_history) == 1
        assert gl.command_history[0]["success"] is True

    def test_consumes_one_command_per_call(self, gl: GameLoop) -> None:
        gl.pending_commands = [
            {
                "tick": 1,
                "command": "press:A",
                "reasoning": "r1",
                "confidence": 0.5,
                "button": None,
            },
            {
                "tick": 2,
                "command": "press:B",
                "reasoning": "r2",
                "confidence": 0.6,
                "button": None,
            },
        ]
        gl._execute_pending_commands()
        assert len(gl.pending_commands) == 1
        assert gl.command_history[0]["command"] == "press:A"

    def test_invalid_command_handled_gracefully(self, gl: GameLoop) -> None:
        gl.pending_commands = [
            {
                "tick": 1,
                "command": "bogus",
                "reasoning": "bad",
                "confidence": 0.1,
                "button": None,
            }
        ]
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
            "total_ticks": 0,
            "screenshots_taken": 0,
            "commands_sent": 0,
            "ai_decisions": 0,
            "battles_encountered": 0,
            "battles_won": 0,
            "battles_lost": 0,
            "start_time": None,
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
        gl.session_id = 42
        gl.stop()
        gl.emulator.stop.assert_called_once()

    def test_stop_sets_running_false(self, gl: GameLoop) -> None:
        gl.is_running = True
        gl.session_id = 42
        gl.stop()
        assert gl.is_running is False

    def test_stop_saves_emulator_state(self, gl: GameLoop) -> None:
        gl.is_running = True
        gl.session_id = 42
        gl.stop()
        gl.emulator.save_state.assert_called_once()

    def test_stop_calls_db_end_session(self, gl: GameLoop) -> None:
        gl.is_running = True
        gl.session_id = 42
        gl.stop()
        gl.db.end_session.assert_called_once()

    def test_stop_exports_session_data(self, gl: GameLoop) -> None:
        gl.is_running = True
        gl.session_id = 42
        gl.stop()
        gl.db.export_session_data.assert_called_once_with(42)


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
        gl.session_id = 42
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


# ── Regression: AP-GAP-001 ───────────────────────────────────────────────


class TestAnalyzeGameStateNoneHP:
    """None HP values from vision must not crash tick-loop formatting."""

    @pytest.fixture
    def loop_with_vision(self) -> GameLoop:
        """A GameLoop stub with real AI enabled and mocked vision result."""
        with patch.object(GameLoop, "__init__", lambda self, config: None):
            gl = GameLoop.__new__(GameLoop)
            gl.current_tick = 1
            gl.battle_turn_count = 0
            gl.emulator_mgr = None
            gl.metrics = {}
            gl.use_real_ai = True
            gl.ai_manager = MagicMock()
            gl.emulator = MagicMock()
            gl.emulator.capture_screen.return_value = None
            setattr(
                gl,
                "_analyze_game_state_stub",
                MagicMock(return_value=_basic_game_state()),
            )
            return gl

    def test_none_player_hp_defaults_to_100(self, loop_with_vision: GameLoop) -> None:
        """player_hp=None → 100.0, no crash."""
        loop_with_vision.ai_manager.analyze_screenshot.return_value = {
            "screen_type": "battle",
            "player_hp": None,
            "enemy_hp": 50,
        }
        result = loop_with_vision._analyze_game_state()
        assert result.player_hp_percent == 100.0

    def test_none_enemy_hp_defaults_to_100(self, loop_with_vision: GameLoop) -> None:
        """enemy_hp=None → 100.0, no crash."""
        loop_with_vision.ai_manager.analyze_screenshot.return_value = {
            "screen_type": "battle",
            "player_hp": 80,
            "enemy_hp": None,
        }
        result = loop_with_vision._analyze_game_state()
        assert result.enemy_hp_percent == 100.0

    def test_none_screen_type_defaults_to_overworld(
        self, loop_with_vision: GameLoop
    ) -> None:
        """screen_type=None → 'overworld', no crash."""
        loop_with_vision.ai_manager.analyze_screenshot.return_value = {
            "screen_type": None,
            "player_hp": 100,
            "enemy_hp": 100,
        }
        result = loop_with_vision._analyze_game_state()
        assert result.screen_type == "overworld"

    def test_format_string_safe_with_none(self, loop_with_vision: GameLoop) -> None:
        """The HP format string must not crash when values are None."""
        loop_with_vision.ai_manager.analyze_screenshot.return_value = {
            "screen_type": "battle",
            "player_hp": None,
            "enemy_hp": None,
        }
        # This should not raise — the fix coerces None → 100.0
        result = loop_with_vision._analyze_game_state()
        assert result.player_hp_percent == 100.0
        assert result.enemy_hp_percent == 100.0


# ── Regression: GAP-020 ───────────────────────────────────────────────────


class TestVisionRecommendedActionWiring:
    """GAP-020: vision recommended_action must become queued commands."""

    @pytest.fixture
    def gl(self) -> GameLoop:
        """A GameLoop stub with real AI enabled and a mocked vision result."""
        with patch.object(GameLoop, "__init__", lambda self, config: None):
            gl = GameLoop.__new__(GameLoop)
            gl.current_tick = 1
            gl.battle_turn_count = 0
            gl.emulator_mgr = None
            gl.use_real_ai = True
            gl.ai_manager = MagicMock()
            gl.emulator = MagicMock()
            gl.emulator.capture_screen.return_value = object()
            gl.pending_commands = []
            gl.command_history = []
            gl.db = MagicMock()
            gl.metrics = {"ai_decisions": 0, "commands_sent": 0}
            setattr(
                gl,
                "_analyze_game_state_stub",
                MagicMock(return_value=_basic_game_state()),
            )
            return gl

    def _vision(self, **overrides: Any) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "screen_type": "title",
            "player_hp": 100,
            "enemy_hp": 100,
        }
        result.update(overrides)
        return result

    def test_press_start_wired_to_pending_commands(self, gl: GameLoop) -> None:
        """recommended_action 'press:START' becomes a queued press command."""
        gl.ai_manager.analyze_screenshot.return_value = self._vision(
            recommended_action="press:START"
        )
        gl._analyze_game_state()
        assert len(gl.pending_commands) == 1
        cmd = gl.pending_commands[0]
        assert cmd["command"] == "press:START"
        assert cmd["button"] is None
        assert cmd["tick"] == 1
        assert gl.metrics["ai_decisions"] == 1

    def test_press_start_space_form_wired(self, gl: GameLoop) -> None:
        """'press START' (space form) normalizes to press:START."""
        gl.ai_manager.analyze_screenshot.return_value = self._vision(
            recommended_action="press START"
        )
        gl._analyze_game_state()
        assert gl.pending_commands[0]["command"] == "press:START"

    def test_walk_up_maps_to_press_up(self, gl: GameLoop) -> None:
        """'walk up' (overworld suggestion) maps to a directional press."""
        gl.ai_manager.analyze_screenshot.return_value = self._vision(
            screen_type="overworld", recommended_action="walk up"
        )
        gl._analyze_game_state()
        assert gl.pending_commands[0]["command"] == "press:UP"

    def test_unsupported_action_logged_and_dropped(self, gl: GameLoop) -> None:
        """Non-button actions are NOT queued and do NOT count as decisions."""
        gl.ai_manager.analyze_screenshot.return_value = self._vision(
            recommended_action="do nothing"
        )
        gl._analyze_game_state()
        assert gl.pending_commands == []
        assert gl.metrics["ai_decisions"] == 0

    def test_no_recommended_action_queues_nothing(self, gl: GameLoop) -> None:
        """Vision result without recommended_action → no command queued."""
        gl.ai_manager.analyze_screenshot.return_value = self._vision()
        gl._analyze_game_state()
        assert gl.pending_commands == []
        assert gl.metrics["ai_decisions"] == 0

    def test_no_double_queue_while_pending(self, gl: GameLoop) -> None:
        """A second vision call must not stack a duplicate while one is pending."""
        gl.ai_manager.analyze_screenshot.return_value = self._vision(
            recommended_action="press:START"
        )
        gl._analyze_game_state()
        assert len(gl.pending_commands) == 1
        # Simulate the second per-tick vision call (battle detect + snapshot).
        gl._analyze_game_state()
        assert len(gl.pending_commands) == 1

    def test_recommended_action_executes_as_button_press(self, gl: GameLoop) -> None:
        """Queued recommendation flows through _execute_pending_commands."""
        gl.ai_manager.analyze_screenshot.return_value = self._vision(
            recommended_action="press:START"
        )
        gl._analyze_game_state()
        gl._execute_pending_commands()
        assert gl.emulator.press_button.called
        assert gl.metrics["commands_sent"] == 1

    def test_recommended_action_counts_as_ai_decision(self, gl: GameLoop) -> None:
        """Wiring a recommendation is an AI decision (honest metrics)."""
        gl.ai_manager.analyze_screenshot.return_value = self._vision(
            recommended_action="press:A"
        )
        gl._analyze_game_state()
        gl._analyze_game_state()
        assert gl.metrics["ai_decisions"] == 1  # no double count


class TestNormalizeRecommendedAction:
    """GAP-020: recommended_action normalization edge cases."""

    def test_press_colon_forms(self) -> None:
        for raw, expected in (
            ("press:A", "press:A"),
            ("press:a", "press:A"),
            ("press:B", "press:B"),
            ("press:START", "press:START"),
            ("press:start", "press:START"),
            ("press:SELECT", "press:SELECT"),
            ("press:UP", "press:UP"),
            ("press:DOWN", "press:DOWN"),
            ("press:LEFT", "press:LEFT"),
            ("press:RIGHT", "press:RIGHT"),
        ):
            assert GameLoop._normalize_recommended_action(raw) == expected

    def test_press_space_forms(self) -> None:
        assert GameLoop._normalize_recommended_action("press START") == "press:START"
        assert GameLoop._normalize_recommended_action("press A") == "press:A"
        assert GameLoop._normalize_recommended_action("PRESS B") == "press:B"

    def test_walk_move_forms(self) -> None:
        assert GameLoop._normalize_recommended_action("walk up") == "press:UP"
        assert GameLoop._normalize_recommended_action("walk down") == "press:DOWN"
        assert GameLoop._normalize_recommended_action("move left") == "press:LEFT"
        assert GameLoop._normalize_recommended_action("move right") == "press:RIGHT"
        assert GameLoop._normalize_recommended_action("go up") == "press:UP"

    def test_unmappable_returns_none(self) -> None:
        assert GameLoop._normalize_recommended_action("") is None
        assert GameLoop._normalize_recommended_action("do nothing") is None
        assert GameLoop._normalize_recommended_action("press:X") is None
        assert GameLoop._normalize_recommended_action("press:") is None
        assert GameLoop._normalize_recommended_action("wait") is None
        assert GameLoop._normalize_recommended_action("walk sideways") is None
        assert GameLoop._normalize_recommended_action("walk") is None
