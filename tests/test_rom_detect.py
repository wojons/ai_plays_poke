"""
Unit tests for rom_detect.py — ROM platform detection and title extraction.

Tests cover:
- GB ROM detection (0xCE at 0x0104, file size ≤ 2 MiB)
- GBA ROM detection (non-0xCE at 0x0104, or oversized)
- Game title extraction (GB and GBA header locations)
- Edge cases: missing files, null bytes, oversized GB ROMs
"""

import pytest
from pathlib import Path

from src.core.rom_detect import detect_platform, get_game_name


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_rom(path: Path, byte_104: bytes, size: int = 0, title_bytes: tuple[int, bytes] | None = None) -> None:
    """Create a minimal ROM file with the specified header byte and optional title."""
    data = bytearray(size)
    # Pad to at least 0x105 bytes so we can set byte at 0x0104
    if len(data) < 0x105:
        data = bytearray(max(size, 0x105))
    data[0x0104] = byte_104[0]
    if title_bytes is not None:
        offset, title_data = title_bytes
        for i, b in enumerate(title_data):
            data[offset + i] = b
    path.write_bytes(bytes(data))


# ── detect_platform ──────────────────────────────────────────────────────────

class TestDetectPlatform:
    """Tests for detect_platform()."""

    # ── GB detection ─────────────────────────────────────────────────────

    def test_gb_with_ce_byte_and_small_size(self, tmp_path):
        """ROM with 0xCE at 0x0104 and size ≤ 2 MiB → 'gb'."""
        rom = tmp_path / "pokemon_blue.gb"
        _make_rom(rom, b"\xCE", size=1_048_576)  # 1 MiB
        assert detect_platform(rom) == "gb"

    def test_gb_with_ce_byte_at_exact_max_size(self, tmp_path):
        """ROM with 0xCE exactly at 2 MiB → 'gb'."""
        rom = tmp_path / "pokemon_gold.gb"
        _make_rom(rom, b"\xCE", size=2_097_152)  # exactly 2 MiB
        assert detect_platform(rom) == "gb"

    def test_gb_with_ce_byte_edge(self, tmp_path):
        """ROM with 0xCE and size=1 → 'gb' (smallest valid)."""
        rom = tmp_path / "tiny.gb"
        _make_rom(rom, b"\xCE", size=1)
        assert detect_platform(rom) == "gb"

    # ── GBA detection ────────────────────────────────────────────────────

    def test_gba_non_ce_byte(self, tmp_path):
        """ROM without 0xCE at 0x0104 → 'gba'."""
        rom = tmp_path / "pokemon_leafgreen.gba"
        _make_rom(rom, b"\x00", size=16_777_216)  # 16 MiB
        assert detect_platform(rom) == "gba"

    def test_gba_with_ff_byte(self, tmp_path):
        """ROM with 0xFF at 0x0104 → 'gba'."""
        rom = tmp_path / "unknown.gba"
        _make_rom(rom, b"\xFF", size=8_388_608)
        assert detect_platform(rom) == "gba"

    def test_gba_oversized_even_with_ce(self, tmp_path):
        """ROM with 0xCE but size > 2 MiB → 'gba' (size disqualifies)."""
        rom = tmp_path / "oversized.gba"
        _make_rom(rom, b"\xCE", size=2_097_153)  # 2 MiB + 1
        assert detect_platform(rom) == "gba"

    def test_gba_ce_byte_but_large_size(self, tmp_path):
        """ROM with 0xCE and 32 MiB → 'gba'."""
        rom = tmp_path / "big.gba"
        _make_rom(rom, b"\xCE", size=33_554_432)
        assert detect_platform(rom) == "gba"

    # ── Path-as-string ───────────────────────────────────────────────────

    def test_accepts_string_path(self, tmp_path):
        """detect_platform accepts a string path."""
        rom = tmp_path / "test.gb"
        _make_rom(rom, b"\xCE", size=32768)
        assert detect_platform(str(rom)) == "gb"

    # ── Error cases ──────────────────────────────────────────────────────

    def test_missing_file_raises(self, tmp_path):
        """Missing file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="ROM not found"):
            detect_platform(tmp_path / "nonexistent.gb")

    def test_directory_raises(self, tmp_path):
        """Path to a directory raises FileNotFoundError (is_file check)."""
        with pytest.raises(FileNotFoundError, match="ROM not found"):
            detect_platform(tmp_path)


# ── get_game_name ────────────────────────────────────────────────────────────

class TestGetGameName:
    """Tests for get_game_name()."""

    # ── GB titles ────────────────────────────────────────────────────────

    def test_gb_title_basic(self, tmp_path):
        """GB ROM: title at 0x134, up to 16 chars."""
        rom = tmp_path / "pokemon_red.gb"
        title = b"POKEMON RED\x00\x00\x00\x00\x00"
        _make_rom(rom, b"\xCE", size=1_048_576, title_bytes=(0x0134, title))
        assert get_game_name(rom) == "POKEMON RED"

    def test_gb_title_16_chars(self, tmp_path):
        """GB ROM: title exactly 16 chars, no null byte."""
        rom = tmp_path / "full.gb"
        title = b"POKEMON BLUEVER1"
        _make_rom(rom, b"\xCE", size=1_048_576, title_bytes=(0x0134, title))
        assert get_game_name(rom) == "POKEMON BLUEVER1"

    def test_gb_title_null_terminated(self, tmp_path):
        """GB ROM: null byte mid-title → stop at null."""
        rom = tmp_path / "nullterm.gb"
        title = b"PM RED\x00PADDING123"
        _make_rom(rom, b"\xCE", size=1_048_576, title_bytes=(0x0134, title))
        assert get_game_name(rom) == "PM RED"

    def test_gb_title_all_nulls(self, tmp_path):
        """GB ROM: all nulls → 'UNKNOWN'."""
        rom = tmp_path / "nulls.gb"
        title = b"\x00" * 16
        _make_rom(rom, b"\xCE", size=1_048_576, title_bytes=(0x0134, title))
        assert get_game_name(rom) == "UNKNOWN"

    def test_gb_title_with_spaces(self, tmp_path):
        """GB ROM: title with trailing spaces → stripped."""
        rom = tmp_path / "spaces.gb"
        title = b"POKE BLUE   \x00\x00\x00"
        _make_rom(rom, b"\xCE", size=1_048_576, title_bytes=(0x0134, title))
        assert get_game_name(rom) == "POKE BLUE"

    # ── GBA titles ───────────────────────────────────────────────────────

    def test_gba_title_basic(self, tmp_path):
        """GBA ROM: title at 0xA0, up to 12 chars."""
        rom = tmp_path / "leafgreen.gba"
        title = b"LEAF GREEN\x00"
        _make_rom(rom, b"\x00", size=16_777_216, title_bytes=(0x00A0, title))
        assert get_game_name(rom) == "LEAF GREEN"

    def test_gba_title_12_chars(self, tmp_path):
        """GBA ROM: title exactly 12 chars."""
        rom = tmp_path / "twelve.gba"
        title = b"POKEMONFIRE1"
        _make_rom(rom, b"\xFF", size=16_777_216, title_bytes=(0x00A0, title))
        assert get_game_name(rom) == "POKEMONFIRE1"

    def test_gba_title_null_terminated(self, tmp_path):
        """GBA ROM: null byte mid-title → stop at null."""
        rom = tmp_path / "nullterm_gba.gba"
        title = b"EMERALD\x00JUNK"
        _make_rom(rom, b"\x00", size=16_777_216, title_bytes=(0x00A0, title))
        assert get_game_name(rom) == "EMERALD"

    def test_gba_title_all_nulls(self, tmp_path):
        """GBA ROM: all nulls → 'UNKNOWN'."""
        rom = tmp_path / "nulls_gba.gba"
        title = b"\x00" * 12
        _make_rom(rom, b"\xFF", size=16_777_216, title_bytes=(0x00A0, title))
        assert get_game_name(rom) == "UNKNOWN"

    # ── Error cases ──────────────────────────────────────────────────────

    def test_missing_file_raises(self, tmp_path):
        """Missing file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="ROM not found"):
            get_game_name(tmp_path / "nonexistent.gba")

    # ── Non-ASCII handling ───────────────────────────────────────────────

    def test_non_ascii_bytes_replaced(self, tmp_path):
        """Non-ASCII bytes in title → replaced with replacement char."""
        rom = tmp_path / "nonascii.gb"
        # 0xFF is not valid ASCII
        title = b"POKE\xFFMON RED\x00\x00\x00"
        _make_rom(rom, b"\xCE", size=1_048_576, title_bytes=(0x0134, title))
        result = get_game_name(rom)
        assert "POKE" in result
        assert "MON RED" in result
        # Should contain replacement char (U+FFFD)
        assert "\ufffd" in result or "?" in result


# ── Integration ──────────────────────────────────────────────────────────────

class TestIntegration:
    """End-to-end: detect → extract."""

    def test_gb_workflow(self, tmp_path):
        """detect_platform + get_game_name on a GB ROM."""
        rom = tmp_path / "complete.gb"
        title = b"POKEMON RED\x00\x00\x00\x00\x00"
        _make_rom(rom, b"\xCE", size=1_048_576, title_bytes=(0x0134, title))
        assert detect_platform(rom) == "gb"
        assert get_game_name(rom) == "POKEMON RED"

    def test_gba_workflow(self, tmp_path):
        """detect_platform + get_game_name on a GBA ROM."""
        rom = tmp_path / "complete.gba"
        title = b"FIRE RED\x00\x00\x00\x00"
        _make_rom(rom, b"\x00", size=16_777_216, title_bytes=(0x00A0, title))
        assert detect_platform(rom) == "gba"
        assert get_game_name(rom) == "FIRE RED"

    def test_gb_unknown_title(self, tmp_path):
        """detect_platform works even when title is UNKNOWN."""
        rom = tmp_path / "unknown.gb"
        _make_rom(rom, b"\xCE", size=32_768, title_bytes=(0x0134, b"\x00" * 16))
        assert detect_platform(rom) == "gb"
        assert get_game_name(rom) == "UNKNOWN"
