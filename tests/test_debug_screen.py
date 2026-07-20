"""Unit tests for src/debug_screen.py — PyBoy screen debugging utilities.

All tests are mock-based: no emulator, no ROM. PyBoy is replaced with a
MagicMock exposing .tick/.stop/.screen.ndarray.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock, patch

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from debug_screen import debug_screen


def make_pyboy(ndarray_value=None, ndarray_side_effect=None) -> MagicMock:
    """Build a mock PyBoy with a configurable screen.ndarray."""
    pyboy = MagicMock()
    pyboy.tick = MagicMock()
    pyboy.stop = MagicMock()
    screen = MagicMock()
    if ndarray_side_effect is not None:
        type(screen).ndarray = PropertyMock(side_effect=ndarray_side_effect)
    else:
        screen.ndarray = ndarray_value
    pyboy.screen = screen
    return pyboy


class TestDebugScreenRomCheck:
    def test_rom_missing_returns_false(self, capsys):
        with patch("debug_screen.os.path.exists", return_value=False):
            result = debug_screen("data/rom/missing.gb", num_ticks=10)
        assert result is False
        assert "ROM not found" in capsys.readouterr().out

    def test_rom_missing_does_not_construct_pyboy(self):
        with (
            patch("debug_screen.os.path.exists", return_value=False),
            patch("debug_screen.PyBoy") as mock_cls,
        ):
            debug_screen("data/rom/missing.gb", num_ticks=10)
        mock_cls.assert_not_called()


class TestDebugScreenLoop:
    def test_happy_path_returns_true(self):
        arr = np.random.randint(0, 200, size=(144, 160, 3), dtype=np.uint8)
        pyboy = make_pyboy(ndarray_value=arr)
        with (
            patch("debug_screen.os.path.exists", return_value=True),
            patch("debug_screen.PyBoy", return_value=pyboy) as mock_cls,
        ):
            result = debug_screen("data/rom/pokemon_blue.gb", num_ticks=50)
        assert result is True
        mock_cls.assert_called_once_with("data/rom/pokemon_blue.gb")
        assert pyboy.tick.call_count == 50
        pyboy.stop.assert_called_once()

    def test_screen_checked_every_100_ticks(self, capsys):
        arr = np.zeros((144, 160, 3), dtype=np.uint8)
        pyboy = make_pyboy(ndarray_value=arr)
        with (
            patch("debug_screen.os.path.exists", return_value=True),
            patch("debug_screen.PyBoy", return_value=pyboy),
        ):
            debug_screen("rom.gb", num_ticks=250)
        out = capsys.readouterr().out
        # Ticks 0, 100, 200 → three screen checks
        assert "Tick 0:" in out
        assert "Tick 100:" in out
        assert "Tick 200:" in out
        assert "Tick 50:" not in out

    def test_screen_stats_printed(self, capsys):
        arr = np.full((144, 160, 3), 100, dtype=np.uint8)
        pyboy = make_pyboy(ndarray_value=arr)
        with (
            patch("debug_screen.os.path.exists", return_value=True),
            patch("debug_screen.PyBoy", return_value=pyboy),
        ):
            debug_screen("rom.gb", num_ticks=1)
        out = capsys.readouterr().out
        assert "min: 100" in out
        assert "max: 100" in out
        assert "mean: 100.00" in out

    def test_non_white_pixels_detected(self, capsys):
        arr = np.full((144, 160, 3), 255, dtype=np.uint8)
        arr[0, 0] = [10, 20, 30]  # non-white pixel
        pyboy = make_pyboy(ndarray_value=arr)
        with (
            patch("debug_screen.os.path.exists", return_value=True),
            patch("debug_screen.PyBoy", return_value=pyboy),
        ):
            debug_screen("rom.gb", num_ticks=1)
        out = capsys.readouterr().out
        assert "non-white pixels" in out
        assert "all white" not in out

    def test_all_white_screen_detected(self, capsys):
        arr = np.full((144, 160, 3), 255, dtype=np.uint8)
        pyboy = make_pyboy(ndarray_value=arr)
        with (
            patch("debug_screen.os.path.exists", return_value=True),
            patch("debug_screen.PyBoy", return_value=pyboy),
        ):
            debug_screen("rom.gb", num_ticks=1)
        out = capsys.readouterr().out
        assert "all white" in out

    def test_none_screen_skipped(self, capsys):
        pyboy = make_pyboy(ndarray_value=None)
        with (
            patch("debug_screen.os.path.exists", return_value=True),
            patch("debug_screen.PyBoy", return_value=pyboy),
        ):
            result = debug_screen("rom.gb", num_ticks=100)
        assert result is True
        out = capsys.readouterr().out
        assert "Screen data" not in out
        assert pyboy.tick.call_count == 100

    def test_empty_screen_skipped(self, capsys):
        pyboy = make_pyboy(ndarray_value=np.array([], dtype=np.uint8))
        with (
            patch("debug_screen.os.path.exists", return_value=True),
            patch("debug_screen.PyBoy", return_value=pyboy),
        ):
            result = debug_screen("rom.gb", num_ticks=100)
        assert result is True
        assert "Screen data" not in capsys.readouterr().out

    def test_screen_exception_caught_loop_continues(self, capsys):
        pyboy = make_pyboy(ndarray_side_effect=RuntimeError("screen fail"))
        try:
            with (
                patch("debug_screen.os.path.exists", return_value=True),
                patch("debug_screen.PyBoy", return_value=pyboy),
            ):
                result = debug_screen("rom.gb", num_ticks=200)
        finally:
            # Clean up class-level PropertyMock so other tests are unaffected
            del type(pyboy.screen).ndarray
        assert result is True
        out = capsys.readouterr().out
        assert "Error at tick 0" in out
        assert "Error at tick 100" in out
        assert pyboy.tick.call_count == 200
        pyboy.stop.assert_called_once()

    def test_debug_dir_created(self, tmp_path):
        """debug/ directory is created next to the project root."""
        import debug_screen as ds

        arr = np.zeros((4, 4, 3), dtype=np.uint8)
        pyboy = make_pyboy(ndarray_value=arr)
        with (
            patch("debug_screen.os.path.exists", return_value=True),
            patch("debug_screen.PyBoy", return_value=pyboy),
        ):
            debug_screen("rom.gb", num_ticks=1)
        expected = Path(ds.__file__).parent.parent / "debug"
        assert expected.exists()

    def test_default_num_ticks(self):
        arr = np.zeros((4, 4, 3), dtype=np.uint8)
        pyboy = make_pyboy(ndarray_value=arr)
        with (
            patch("debug_screen.os.path.exists", return_value=True),
            patch("debug_screen.PyBoy", return_value=pyboy),
        ):
            debug_screen("rom.gb")
        assert pyboy.tick.call_count == 1000
