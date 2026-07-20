"""Unit tests for src/memory_reader.py — memory scanning and stats reading.

All tests are mock-based: no emulator, no ROM. PyBoy is replaced with a
MagicMock exposing a .memory mapping.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch


sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from memory_reader import read_pokemon_stats, scan_memory_for_pokemon_data, test_memory_scanning


def make_pyboy(memory_values: dict[int, int] | None = None, default: int = 0) -> MagicMock:
    """Build a mock PyBoy whose .memory[addr] returns values from the dict."""
    values = memory_values or {}
    memory = MagicMock()
    memory.__getitem__ = MagicMock(side_effect=lambda addr: values.get(addr, default))
    pyboy = MagicMock()
    pyboy.memory = memory
    return pyboy


class TestScanMemoryForPokemonData:
    def test_returns_dict(self):
        pyboy = make_pyboy()
        result = scan_memory_for_pokemon_data(pyboy, scan_range=(0xD000, 0xD010))
        assert isinstance(result, dict)

    def test_finds_nonzero_pairs(self):
        # Both addr and addr+1 non-zero → recorded
        values = {0xD000: 10, 0xD001: 20, 0xD004: 5, 0xD005: 6}
        pyboy = make_pyboy(values)
        result = scan_memory_for_pokemon_data(pyboy, scan_range=(0xD000, 0xD008))
        assert result["addr_0xd000"] == "10, 20"
        assert result["addr_0xd004"] == "5, 6"
        # Zero pair at 0xD002 not recorded
        assert "addr_0xd002" not in result

    def test_skips_when_either_byte_zero(self):
        values = {0xD000: 10, 0xD001: 0, 0xD002: 0, 0xD003: 7}
        pyboy = make_pyboy(values)
        result = scan_memory_for_pokemon_data(pyboy, scan_range=(0xD000, 0xD004))
        assert result == {}

    def test_scans_every_two_bytes(self):
        pyboy = make_pyboy(default=1)
        scan_memory_for_pokemon_data(pyboy, scan_range=(0xD000, 0xD010))
        addrs = [call.args[0] for call in pyboy.memory.__getitem__.call_args_list]
        # Reads addr and addr+1 for each even addr in range
        expected = []
        for a in range(0xD000, 0xD010, 2):
            expected += [a, a + 1]
        assert addrs == expected

    def test_default_scan_range(self):
        pyboy = make_pyboy(default=1)
        result = scan_memory_for_pokemon_data(pyboy)
        # Range (0xD000, 0xE000) step 2 = 2048 iterations, all nonzero
        assert len(result) == 2048
        assert "addr_0xd000" in result
        assert "addr_0xdffe" in result

    def test_index_error_breaks_loop(self):
        memory = MagicMock()
        memory.__getitem__ = MagicMock(side_effect=IndexError("oob"))
        pyboy = MagicMock()
        pyboy.memory = memory
        result = scan_memory_for_pokemon_data(pyboy, scan_range=(0xD000, 0xD010))
        assert result == {}

    def test_index_error_mid_scan_keeps_prior_results(self):
        calls = {"n": 0}

        def side_effect(addr):
            calls["n"] += 1
            if calls["n"] > 4:
                raise IndexError("oob")
            return 5

        memory = MagicMock()
        memory.__getitem__ = MagicMock(side_effect=side_effect)
        pyboy = MagicMock()
        pyboy.memory = memory
        result = scan_memory_for_pokemon_data(pyboy, scan_range=(0xD000, 0xD010))
        # Two full pairs read before failure (4 reads), then break on 5th
        assert len(result) == 2


class TestReadPokemonStats:
    def test_returns_all_stat_keys(self):
        pyboy = make_pyboy(default=42)
        stats = read_pokemon_stats(pyboy)
        assert stats is not None
        for key in (
            "player_hp",
            "player_max_hp",
            "player_level",
            "player_status",
            "enemy_hp",
            "enemy_max_hp",
            "enemy_level",
        ):
            assert key in stats

    def test_reads_correct_addresses(self):
        pyboy = make_pyboy(default=1)
        read_pokemon_stats(pyboy)
        addrs = [call.args[0] for call in pyboy.memory.__getitem__.call_args_list]
        assert addrs == [0xD158, 0xD159, 0xD16A, 0xD15E, 0xCFD8, 0xCFD9, 0xCFE2]

    def test_values_from_memory(self):
        values = {0xD158: 35, 0xD159: 40, 0xD16A: 12, 0xD15E: 0,
                  0xCFD8: 20, 0xCFD9: 22, 0xCFE2: 10}
        pyboy = make_pyboy(values)
        stats = read_pokemon_stats(pyboy)
        assert stats == {
            "player_hp": 35,
            "player_max_hp": 40,
            "player_level": 12,
            "player_status": 0,
            "enemy_hp": 20,
            "enemy_max_hp": 22,
            "enemy_level": 10,
        }

    def test_exception_returns_none(self):
        memory = MagicMock()
        memory.__getitem__ = MagicMock(side_effect=Exception("bad read"))
        pyboy = MagicMock()
        pyboy.memory = memory
        assert read_pokemon_stats(pyboy) is None


class TestMemoryScanningFunction:
    """test_memory_scanning() is a diagnostic driver — mock PyBoy and ROM existence."""

    def test_rom_missing_returns_false(self):
        with patch("memory_reader.os.path.exists", return_value=False):
            assert test_memory_scanning() is False

    def test_happy_path_returns_true(self):
        pyboy = make_pyboy(default=1)
        with (
            patch("memory_reader.os.path.exists", return_value=True),
            patch("memory_reader.PyBoy", return_value=pyboy) as mock_cls,
        ):
            assert test_memory_scanning() is True
            mock_cls.assert_called_once_with("data/rom/pokemon_blue.gb")
            # 500 init ticks
            assert pyboy.tick.call_count == 500
            pyboy.stop.assert_called_once()

    def test_no_data_found_still_completes(self):
        pyboy = make_pyboy(default=0)  # scan finds nothing; stats all 0
        with (
            patch("memory_reader.os.path.exists", return_value=True),
            patch("memory_reader.PyBoy", return_value=pyboy),
        ):
            assert test_memory_scanning() is True
            pyboy.stop.assert_called_once()
