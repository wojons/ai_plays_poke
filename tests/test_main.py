"""Unit tests for src/main.py — PokemonAIAgent + main() entry point."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import numpy as np
import pytest


# Import the module under test
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from main import PokemonAIAgent, main


# Fixtures
@pytest.fixture
def mock_pyboy():
    """Mock PyBoy with screen ndarray + memory + tick + stop.

    Uses instance attributes (not PropertyMock on the class) to avoid
    polluting the shared MagicMock class across tests.
    """
    pyboy = MagicMock()

    # Screen — return a small valid RGB image
    screen = MagicMock()
    screen.ndarray = np.zeros((144, 160, 3), dtype=np.uint8)
    pyboy.screen = screen

    # Memory — return byte values for Gen 1 addresses
    memory = MagicMock()
    memory.__getitem__ = MagicMock(return_value=42)
    pyboy.memory = memory

    pyboy.tick = MagicMock()
    pyboy.stop = MagicMock()
    return pyboy


@pytest.fixture
def agent(tmp_path, mock_pyboy):
    """Create a PokemonAIAgent with a tmp_path ROM and mocked PyBoy, then start()."""
    rom = tmp_path / "test.gb"
    rom.write_bytes(b"\x00" * 32)
    with patch("main.PyBoy", return_value=mock_pyboy):
        a = PokemonAIAgent(str(rom))
        a.start()
        a._tmp = tmp_path  # keep tmp alive
    return a


# ——— PokemonAIAgent.__init__ ———
class TestPokemonAIAgentInit:
    def test_init_stores_rom_path(self, tmp_path):
        rom = tmp_path / "test.gb"
        rom.write_bytes(b"\x00" * 32)
        a = PokemonAIAgent(str(rom))
        assert a.rom_path == str(rom)
        assert a.pyboy is None

    def test_init_creates_screenshot_dir(self, tmp_path):
        rom = tmp_path / "test.gb"
        rom.write_bytes(b"\x00" * 32)
        a = PokemonAIAgent(str(rom))
        expected = Path(__file__).parent.parent / "screenshots"
        assert expected.exists()
        assert a.screenshot_dir == expected


# ——— PokemonAIAgent.start ———
class TestStart:
    def test_start_rom_missing(self, tmp_path):
        a = PokemonAIAgent("/nonexistent/rom.gb")
        assert a.start() is False

    def test_start_rom_exists(self, tmp_path, mock_pyboy):
        rom = tmp_path / "test.gb"
        rom.write_bytes(b"\x00" * 32)
        with patch("main.PyBoy", return_value=mock_pyboy):
            a = PokemonAIAgent(str(rom))
            assert a.start() is True
            assert a.pyboy is not None

    def test_start_calls_pyboy_constructor(self, tmp_path, mock_pyboy):
        rom = tmp_path / "test.gb"
        rom.write_bytes(b"\x00" * 32)
        with patch("main.PyBoy") as mock_cls:
            mock_cls.return_value = mock_pyboy
            a = PokemonAIAgent(str(rom))
            a.start()
            mock_cls.assert_called_once_with(str(rom))


# ——— PokemonAIAgent.run_ticks ———
class TestRunTicks:
    def test_run_default_ticks(self, agent):
        agent.pyboy = agent.pyboy  # already set
        agent.run_ticks()
        assert agent.pyboy.tick.call_count == 100

    def test_run_custom_ticks(self, agent):
        agent.run_ticks(10)
        assert agent.pyboy.tick.call_count == 10

    def test_run_zero_ticks(self, agent):
        agent.run_ticks(0)
        agent.pyboy.tick.assert_not_called()


# ——— PokemonAIAgent.capture_screenshot ———
class TestCaptureScreenshot:
    def test_capture_success(self, agent, tmp_path):
        agent.screenshot_dir = tmp_path
        assert agent.capture_screenshot(1) is True
        expected = tmp_path / "screenshot_0001.png"
        assert expected.exists()

    def test_capture_zero_tick(self, agent, tmp_path):
        agent.screenshot_dir = tmp_path
        assert agent.capture_screenshot(0) is True
        expected = tmp_path / "screenshot_0000.png"
        assert expected.exists()

    def test_capture_large_tick(self, agent, tmp_path):
        agent.screenshot_dir = tmp_path
        assert agent.capture_screenshot(9999) is True
        expected = tmp_path / "screenshot_9999.png"
        assert expected.exists()

    def test_capture_screen_none_returns_none(self, tmp_path):
        """When screen.ndarray returns None, capture returns None."""
        rom = tmp_path / "test.gb"
        rom.write_bytes(b"\x00" * 32)
        # Fresh mock — no class-level PropertyMock interference
        pyboy = MagicMock()
        screen = MagicMock()
        screen.ndarray = None
        pyboy.screen = screen
        with patch("main.PyBoy", return_value=pyboy):
            a = PokemonAIAgent(str(rom))
            a.start()
            a.screenshot_dir = tmp_path
            result = a.capture_screenshot(5)
        # if screen_nparr is not None → False → falls through → returns None
        assert result is None

    def test_capture_empty_array(self, tmp_path):
        rom = tmp_path / "test.gb"
        rom.write_bytes(b"\x00" * 32)
        pyboy = MagicMock()
        screen = MagicMock()
        screen.ndarray = np.array([], dtype=np.uint8)  # .size = 0
        pyboy.screen = screen
        with patch("main.PyBoy", return_value=pyboy):
            a = PokemonAIAgent(str(rom))
            a.start()
            a.screenshot_dir = tmp_path
            result = a.capture_screenshot(5)
        # screen_nparr.size > 0 is False → falls through → returns None
        assert result is None

    def test_capture_exception_returns_false(self, tmp_path):
        rom = tmp_path / "test.gb"
        rom.write_bytes(b"\x00" * 32)
        pyboy = MagicMock()
        screen = MagicMock()
        # ndarray access raises RuntimeError
        type(screen).ndarray = PropertyMock(side_effect=RuntimeError("boom"))
        pyboy.screen = screen
        with patch("main.PyBoy", return_value=pyboy):
            a = PokemonAIAgent(str(rom))
            a.start()
            a.screenshot_dir = tmp_path
            result = a.capture_screenshot(1)
        assert result is False


# ——— PokemonAIAgent.read_memory_data ———
class TestReadMemoryData:
    def test_read_memory_pyboy_none(self, agent):
        agent.pyboy = None
        assert agent.read_memory_data() is None

    def test_read_memory_returns_dict(self, agent):
        result = agent.read_memory_data()
        assert isinstance(result, dict)
        assert "player_hp" in result
        assert "enemy_hp" in result
        assert result["player_hp"] == 42  # default mock return

    def test_read_memory_exception_returns_none(self, agent):
        agent.pyboy.memory.__getitem__ = MagicMock(side_effect=Exception("bad addr"))
        assert agent.read_memory_data() is None


# ——— PokemonAIAgent.get_game_state ———
class TestGetGameState:
    def test_get_game_state_returns_dict(self, agent, tmp_path):
        agent.screenshot_dir = tmp_path
        state = agent.get_game_state(5)
        assert state["tick"] == 5
        assert state["screenshot"] == "screenshots/screenshot_0005.png"
        assert isinstance(state["memory_data"], dict)

    def test_get_game_state_tick_zero(self, agent, tmp_path):
        agent.screenshot_dir = tmp_path
        state = agent.get_game_state(0)
        assert state["tick"] == 0


# ——— PokemonAIAgent.stop ———
class TestStop:
    def test_stop_calls_pyboy_stop(self, agent):
        pyboy_ref = agent.pyboy  # capture before stop() sets it to None
        agent.stop()
        pyboy_ref.stop.assert_called_once()
        assert agent.pyboy is None

    def test_stop_pyboy_already_none(self, agent):
        agent.pyboy = None
        agent.stop()  # no crash
        assert agent.pyboy is None

    def test_stop_idempotent(self, agent):
        agent.stop()
        agent.stop()  # second call — pyboy is already None, no crash


# ——— main() ———
class TestMainFunction:
    def test_main_rom_not_found(self, tmp_path):
        """main() with nonexistent ROM should return early without crash."""
        with patch("main.PokemonAIAgent") as MockAgent:
            inst = MockAgent.return_value
            inst.start.return_value = False
            main()
            inst.start.assert_called_once()
            inst.run_ticks.assert_not_called()

    def test_main_happy_path(self, tmp_path, mock_pyboy):
        """main() full happy path — no crash."""
        rom = tmp_path / "test.gb"
        rom.write_bytes(b"\x00" * 32)
        with patch("main.PyBoy", return_value=mock_pyboy):
            with patch("main.PokemonAIAgent") as MockAgent:
                inst = MockAgent.return_value
                inst.start.return_value = True
                inst.get_game_state.return_value = {
                    "tick": 0,
                    "screenshot": "screenshots/screenshot_0000.png",
                    "memory_data": {"player_hp": 42},
                }
                main()
                inst.start.assert_called_once()
                assert inst.run_ticks.call_count >= 2  # 500 init + ticks
                assert inst.get_game_state.call_count == 6  # 0, 100-500
                inst.stop.assert_called_once()

    def test_main_exception_in_loop(self, tmp_path, mock_pyboy):
        """main() handles exception gracefully — stop is still called."""
        rom = tmp_path / "test.gb"
        rom.write_bytes(b"\x00" * 32)
        with patch("main.PyBoy", return_value=mock_pyboy):
            with patch("main.PokemonAIAgent") as MockAgent:
                inst = MockAgent.return_value
                inst.start.return_value = True
                inst.run_ticks.side_effect = RuntimeError("crash")
                main()
                inst.stop.assert_called_once()  # finally block runs
