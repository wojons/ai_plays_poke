"""Unit tests for diagnostic/utility scripts.

Tests pure functions from:
- src/memory_reader.py (scan_memory_for_pokemon_data, read_pokemon_stats)
- src/debug_screen.py (debug_screen)
- src/generate_yellow_screenshots.py (generate_pokemon_yellow_screenshots)

All use mocked PyBoy — no ROM, no emulator, no filesystem.
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# ── memory_reader.py ────────────────────────────────────────────────────

class TestScanMemory:
    def _make_memory(self, addr_map):
        """Create a mock memory that returns addr_map[addr] on [addr] access."""
        mem = MagicMock()

        def side_effect(addr, *args, **kwargs):
            if addr in addr_map:
                return addr_map[addr]
            raise IndexError(f"no value at {hex(addr)}")
        mem.__getitem__.side_effect = side_effect
        return mem

    def test_scans_range_and_collects_nonzero_pairs(self):
        from memory_reader import scan_memory_for_pokemon_data
        mock_pyboy = MagicMock()
        mock_pyboy.memory = self._make_memory({
            0xD000: 5, 0xD001: 10, 0xD002: 0, 0xD003: 3,
            0xD004: 7, 0xD005: 0,
        })
        result = scan_memory_for_pokemon_data(mock_pyboy, (0xD000, 0xD006))
        assert len(result) == 1  # Only (5, 10) has both > 0
        assert "addr_0xd000" in result

    def test_empty_result_when_no_nonzero_pairs(self):
        from memory_reader import scan_memory_for_pokemon_data
        mock_pyboy = MagicMock()
        mock_pyboy.memory = self._make_memory({addr: 0 for addr in range(0xD000, 0xD010)})
        result = scan_memory_for_pokemon_data(mock_pyboy, (0xD000, 0xD010))
        assert result == {}

    def test_stops_on_indexerror(self):
        from memory_reader import scan_memory_for_pokemon_data
        mock_pyboy = MagicMock()
        mem = MagicMock()

        def raising(addr, *args, **kwargs):
            if addr > 0xD010:
                raise IndexError()
            return 1
        mem.__getitem__.side_effect = raising
        mock_pyboy.memory = mem

        result = scan_memory_for_pokemon_data(mock_pyboy, (0xD000, 0xD020))
        assert isinstance(result, dict)

    def test_custom_scan_range(self):
        from memory_reader import scan_memory_for_pokemon_data
        mock_pyboy = MagicMock()
        mock_pyboy.memory = self._make_memory({addr: 1 for addr in range(0xC000, 0xC012)})
        result = scan_memory_for_pokemon_data(mock_pyboy, (0xC000, 0xC010))
        assert len(result) == 8  # 8 pairs from range(0xC000, 0xC010, step=2)


class TestReadPokemonStats:
    def test_reads_known_addresses(self):
        from memory_reader import read_pokemon_stats
        mock_pyboy = MagicMock()
        mem = MagicMock()
        addr_vals = {
            0xD158: 100, 0xD159: 150, 0xD16A: 25, 0xD15E: 0,
            0xCFD8: 80, 0xCFD9: 120, 0xCFE2: 22,
        }
        mem.__getitem__.side_effect = lambda addr, *a, **kw: addr_vals.get(addr, 0)
        mock_pyboy.memory = mem

        stats = read_pokemon_stats(mock_pyboy)
        assert stats["player_hp"] == 100
        assert stats["player_max_hp"] == 150
        assert stats["player_level"] == 25
        assert stats["enemy_hp"] == 80
        assert stats["enemy_max_hp"] == 120
        assert stats["enemy_level"] == 22

    def test_returns_none_on_error(self):
        from memory_reader import read_pokemon_stats
        mock_pyboy = MagicMock()
        mock_pyboy.memory = MagicMock()
        mock_pyboy.memory.__getitem__.side_effect = ValueError("bad addr")

        stats = read_pokemon_stats(mock_pyboy)
        assert stats is None

    def test_all_stats_present(self):
        from memory_reader import read_pokemon_stats
        mock_pyboy = MagicMock()
        mock_pyboy.memory = MagicMock()
        mock_pyboy.memory.__getitem__.side_effect = lambda addr, *a, **kw: 1

        stats = read_pokemon_stats(mock_pyboy)
        expected_keys = {"player_hp", "player_max_hp", "player_level",
                         "player_status", "enemy_hp", "enemy_max_hp", "enemy_level"}
        assert set(stats.keys()) == expected_keys


# ── debug_screen.py ─────────────────────────────────────────────────────

class TestDebugScreen:
    def test_rom_not_found_returns_false(self):
        from debug_screen import debug_screen
        result = debug_screen("/nonexistent/rom.gb")
        assert result is False

    def test_happy_path_returns_true(self):
        from debug_screen import debug_screen
        import numpy as np
        mock_pyboy = MagicMock()
        mock_screen = MagicMock()
        mock_screen.ndarray = np.zeros((144, 160), dtype=np.uint8) + 255
        mock_pyboy.screen = mock_screen

        with patch("debug_screen.os.path.exists", return_value=True):
            with patch("debug_screen.PyBoy", return_value=mock_pyboy):
                result = debug_screen("fake_rom.gb", num_ticks=100)
                assert result is True
                assert mock_pyboy.tick.call_count == 100
                mock_pyboy.stop.assert_called_once()

    def test_file_missing_returns_false(self):
        from debug_screen import debug_screen
        with patch("debug_screen.os.path.exists", return_value=False):
            result = debug_screen("missing.gb")
            assert result is False


# ── generate_yellow_screenshots.py ──────────────────────────────────────

class TestGenerateYellowScreenshots:
    def test_rom_not_found_returns_false(self):
        from generate_yellow_screenshots import generate_pokemon_yellow_screenshots
        result = generate_pokemon_yellow_screenshots(num_ticks=100, screenshot_interval=10)
        assert result is False

    def test_saves_screenshots_at_interval(self):
        from generate_yellow_screenshots import generate_pokemon_yellow_screenshots
        mock_pyboy = MagicMock()
        mock_image = MagicMock()
        mock_pyboy.screen = MagicMock()
        mock_pyboy.screen.image = mock_image

        with patch("generate_yellow_screenshots.os.path.exists", return_value=True):
            with patch("generate_yellow_screenshots.PyBoy", return_value=mock_pyboy):
                with patch.object(Path, "mkdir"):
                    result = generate_pokemon_yellow_screenshots(
                        num_ticks=100, screenshot_interval=10
                    )
                    assert result is True
                    assert mock_pyboy.stop.called
                    assert mock_image.save.call_count == 10

    def test_no_screenshots_when_none_at_interval(self):
        from generate_yellow_screenshots import generate_pokemon_yellow_screenshots
        mock_pyboy = MagicMock()
        mock_pyboy.screen = MagicMock()
        mock_pyboy.screen.image = MagicMock()

        with patch("generate_yellow_screenshots.os.path.exists", return_value=True):
            with patch("generate_yellow_screenshots.PyBoy", return_value=mock_pyboy):
                result = generate_pokemon_yellow_screenshots(
                    num_ticks=5, screenshot_interval=100
                )
                assert result is True
                assert mock_pyboy.screen.image.save.call_count == 1

    def test_continues_on_screenshot_error(self):
        from generate_yellow_screenshots import generate_pokemon_yellow_screenshots
        mock_pyboy = MagicMock()
        mock_image = MagicMock()
        mock_image.save.side_effect = OSError("disk full")
        mock_pyboy.screen = MagicMock()
        mock_pyboy.screen.image = mock_image

        with patch("generate_yellow_screenshots.os.path.exists", return_value=True):
            with patch("generate_yellow_screenshots.PyBoy", return_value=mock_pyboy):
                result = generate_pokemon_yellow_screenshots(
                    num_ticks=50, screenshot_interval=10
                )
                assert result is True
                assert mock_pyboy.tick.call_count == 50
