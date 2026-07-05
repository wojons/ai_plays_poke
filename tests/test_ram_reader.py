"""
Unit tests for src/core/ram_reader.py — RAM-based game state reader.

Mocks both the emulator (via read_u8/read_u16) and the ROM bytes so no
real .gb file is needed.
"""
from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch


# ── helpers ────────────────────────────────────────────────────────────────


def _make_rom_bytes(
    map_count: int = 248,
    bank_table_offset: int = 0xC23D,
    ptr_table_offset: int = 0x01AE,
) -> bytes:
    """Build a minimal fake ROM binary with dummy map headers for testing."""
    # A 512KB ROM with everything zeroed except the map tables
    rom = bytearray(512 * 1024)

    # Set up a single map header at map_id=0:
    # Pointer table entry at 0x01AE: 16-bit little-endian = 0x4100
    # Bank table entry at 0xC23D: bank = 1
    # At ROM offset 1 * 0x4000 + (0x4100 - 0x4000) = 0x4100:
    #   tileset=4, height=4, width=4, block_ptr=0x4110
    # At block_ptr offset: 4×4 = 16 bytes of block data [0x0F, 0x10, ...]
    import struct

    # Map header pointer at ptr_table_offset (map 0)
    struct.pack_into("<H", rom, ptr_table_offset, 0x4100)

    # Bank byte at bank_table_offset (map 0)
    rom[bank_table_offset] = 1

    # Map header at ROM offset 0x4100
    # bank=1 => rom_offset = 1 * 0x4000 + (0x4100 - 0x4000) = 0x4100
    offset = 0x4100
    rom[offset] = 4          # tileset
    rom[offset + 1] = 4      # height
    rom[offset + 2] = 4      # width
    struct.pack_into("<H", rom, offset + 3, 0x4110)  # block_ptr

    # Block data at 0x4110: 4×4 = 16 bytes
    block_offset = 0x4110
    # Row 0: floor, wall, floor, wall
    rom[block_offset]     = 0x0F  # floor (tileset 4)
    rom[block_offset + 1] = 0x10  # wall
    rom[block_offset + 2] = 0x0F  # floor
    rom[block_offset + 3] = 0x10  # wall
    # Row 1: wall, stairs, wall, floor
    rom[block_offset + 4] = 0x10  # wall
    rom[block_offset + 5] = 0x0D  # stairs
    rom[block_offset + 6] = 0x10  # wall
    rom[block_offset + 7] = 0x0F  # floor
    # Row 2: floor, wall, object, floor
    rom[block_offset + 8]  = 0x0F  # floor
    rom[block_offset + 9]  = 0x10  # wall
    rom[block_offset + 10] = 0x12  # object
    rom[block_offset + 11] = 0x0F  # floor
    # Row 3: wall, floor, floor, wall
    rom[block_offset + 12] = 0x10  # wall
    rom[block_offset + 13] = 0x0F  # floor
    rom[block_offset + 14] = 0x0F  # floor
    rom[block_offset + 15] = 0x10  # wall

    return bytes(rom)


# ── RAMReader fixture ─────────────────────────────────────────────────────


@pytest.fixture
def mock_emu() -> MagicMock:
    """Emulator mock with read_u8/read_u16 returning known values."""
    emu = MagicMock()
    emu.read_u8.side_effect = _emu_read_u8
    emu.read_u16.side_effect = _emu_read_u16
    return emu


# A dict of address → value for the mock emulator's memory
_MEMORY: dict[int, int] = {}


def _emu_read_u8(addr: int) -> int:
    return _MEMORY.get(addr, 0)


def _emu_read_u16(addr: int) -> int:
    return _MEMORY.get(addr, 0) | (_MEMORY.get(addr + 1, 0) << 8)


def _set_default_memory() -> None:
    """Set default emulator memory values — player in Pallet Town (map 0x00)."""
    _MEMORY.clear()
    _MEMORY[0xD361] = 7   # wYCoord = 7 (player_y = 3 after -4)
    _MEMORY[0xD362] = 9   # wXCoord = 9 (player_x = 5 after -4)
    _MEMORY[0xD35E] = 0x00  # wCurMap = Pallet Town
    _MEMORY[0xCFC5] = 0      # wWalkCounter = 0 (not moving)
    _MEMORY[0xD057] = 0      # wIsInBattle = 0 (overworld)
    _MEMORY[0xCF2B] = 0      # wTextBoxFrame = 0
    _MEMORY[0xCC47] = 0      # wNamingScreenType = 0
    # Sprite state data — facing direction (offset 9, bits 2-3 = 0x00 = down)
    _MEMORY[0xC109] = 0x00


@pytest.fixture(autouse=True)
def _reset_memory() -> None:
    """Reset memory before each test."""
    _set_default_memory()


# ── _MapDB tests ──────────────────────────────────────────────────────────


class TestMapDBReadU8:
    def test_reads_single_byte(self) -> None:
        from src.core.ram_reader import _MapDB

        data = bytes([0x42, 0x00])
        assert _MapDB._read_u8(data, 0) == 0x42

    def test_reads_from_offset(self) -> None:
        from src.core.ram_reader import _MapDB

        data = bytes([0x00, 0xFF, 0x00])
        assert _MapDB._read_u8(data, 1) == 0xFF


class TestMapDBReadU16:
    def test_little_endian(self) -> None:
        from src.core.ram_reader import _MapDB

        data = bytes([0x34, 0x12])
        assert _MapDB._read_u16(data, 0) == 0x1234

    def test_with_offset(self) -> None:
        from src.core.ram_reader import _MapDB

        data = bytes([0x00, 0x00, 0xCD, 0xAB])
        assert _MapDB._read_u16(data, 2) == 0xABCD


class TestMapDBRomOffset:
    def test_bank_zero_returns_ptr_directly(self) -> None:
        from src.core.ram_reader import _MapDB

        assert _MapDB._rom_offset(None, 0x1234, 0) == 0x1234

    def test_bank_nonzero(self) -> None:
        from src.core.ram_reader import _MapDB

        # bank=2: offset = 2 * 0x4000 + (ptr - 0x4000) = ptr + 0x4000
        assert _MapDB._rom_offset(None, 0x5000, 2) == 0x9000

    def test_bank_one(self) -> None:
        from src.core.ram_reader import _MapDB

        # bank=1: offset = 1 * 0x4000 + (ptr - 0x4000) = ptr
        assert _MapDB._rom_offset(None, 0x4200, 1) == 0x4200


class TestMapDBParseHeader:
    """_parse_header with fake ROM bytes."""

    @pytest.fixture
    def db(self) -> object:
        rom = _make_rom_bytes()
        return _MapDB.__new__(_MapDB)  # skip __init__, inject _rom

    def _patch_rom(self, db: object, rom: bytes) -> None:
        db._rom = rom
        db._cache = {}

    def test_parse_map_zero(self) -> None:
        from src.core.ram_reader import _MapDB

        db = _MapDB.__new__(_MapDB)
        self._patch_rom(db, _make_rom_bytes())

        result = db._parse_header(0)
        assert result is not None
        assert result["tileset"] == 4
        assert result["width"] == 4
        assert result["height"] == 4
        assert len(result["block_data"]) == 16
        assert result["block_data"][0] == 0x0F  # floor
        assert result["block_data"][5] == 0x0D  # stairs

    def test_parse_invalid_map_id_returns_none(self) -> None:
        from src.core.ram_reader import _MapDB

        db = _MapDB.__new__(_MapDB)
        self._patch_rom(db, _make_rom_bytes())

        assert db._parse_header(999) is None

    def test_parse_out_of_bounds_returns_none(self) -> None:
        from src.core.ram_reader import _MapDB, _PTR_TABLE, _BANK_TABLE

        # Make a large enough ROM for tables but set roff+12 past end by
        # using a pointer that resolves beyond ROM size.
        rom_size = _BANK_TABLE + 16  # just barely covers the bank table
        rom = bytearray(rom_size)
        import struct

        # Pointer at _PTR_TABLE points to offset 0x4100
        struct.pack_into("<H", rom, _PTR_TABLE, 0x4100)
        # Bank = 1 => rom_offset = 1*0x4000 + (0x4100-0x4000) = 0x4100 = 16640
        rom[_BANK_TABLE] = 1
        # But ROM is only _BANK_TABLE + 16 = 49741 bytes
        # 16640 + 12 = 16652 which IS < 49741 -> header is reachable
        # So this test needs a larger offset. Let's use a pointer that
        # maps to an offset > ROM size.
        # Pointer 0xC000 with bank=3: offset = 3*0x4000 + (0xC000-0x4000) = 0x14000 = 81920
        struct.pack_into("<H", rom, _PTR_TABLE, 0xC000)
        rom[_BANK_TABLE] = 3
        # 81920 + 12 = 81932 > 49741 -> None expected

        db = _MapDB.__new__(_MapDB)
        self._patch_rom(db, bytes(rom))

        result = db._parse_header(0)
        assert result is None

    def test_caching_returns_same_object(self) -> None:
        from src.core.ram_reader import _MapDB

        db = _MapDB.__new__(_MapDB)
        self._patch_rom(db, _make_rom_bytes())

        r1 = db._parse_header(0)
        r2 = db._parse_header(0)
        assert r1 is r2


class TestMapDBGetMap:
    def test_valid_map(self) -> None:
        from src.core.ram_reader import _MapDB

        db = _MapDB.__new__(_MapDB)
        db._rom = _make_rom_bytes()
        db._cache = {}

        info = db.get_map(0)
        assert info is not None
        assert info["width"] == 4

    def test_invalid_map(self) -> None:
        from src.core.ram_reader import _MapDB

        db = _MapDB.__new__(_MapDB)
        db._rom = _make_rom_bytes()
        db._cache = {}

        assert db.get_map(999) is None


class TestMapDBBlockAt:
    def test_returns_block_value(self) -> None:
        from src.core.ram_reader import _MapDB

        db = _MapDB.__new__(_MapDB)
        db._rom = _make_rom_bytes()
        db._cache = {}

        assert db.block_at(0, 0, 0) == 0x0F  # floor
        assert db.block_at(0, 1, 1) == 0x0D  # stairs at (1,1)
        assert db.block_at(0, 3, 3) == 0x10  # wall at (3,3)

    def test_out_of_bounds(self) -> None:
        from src.core.ram_reader import _MapDB

        db = _MapDB.__new__(_MapDB)
        db._rom = _make_rom_bytes()
        db._cache = {}

        assert db.block_at(0, 10, 10) is None
        assert db.block_at(0, -1, 0) is None

    def test_nonexistent_map(self) -> None:
        from src.core.ram_reader import _MapDB

        db = _MapDB.__new__(_MapDB)
        db._rom = _make_rom_bytes()
        db._cache = {}

        assert db.block_at(999, 0, 0) is None


class TestMapDBClassifyBlock:
    def test_tileset4_known(self) -> None:
        from src.core.ram_reader import _MapDB

        db = _MapDB.__new__(_MapDB)
        assert db.classify_block(0x0F, 4) == "floor"
        assert db.classify_block(0x10, 4) == "wall"
        assert db.classify_block(0x0D, 4) == "stairs"
        assert db.classify_block(0x12, 4) == "object"

    def test_tileset4_unknown(self) -> None:
        from src.core.ram_reader import _MapDB

        db = _MapDB.__new__(_MapDB)
        assert db.classify_block(0xFF, 4) == "unknown"

    def test_block_0x0F_always_floor(self) -> None:
        from src.core.ram_reader import _MapDB

        db = _MapDB.__new__(_MapDB)
        assert db.classify_block(0x0F, 99) == "floor"

    def test_other_tilesets_unknown(self) -> None:
        from src.core.ram_reader import _MapDB

        db = _MapDB.__new__(_MapDB)
        assert db.classify_block(0x10, 99) == "unknown"


# ── RAMReader tests (mock emulator + mock _MapDB) ────────────────────────


class TestRAMReaderInit:
    def test_stores_emulator_and_mapdb(self, mock_emu: MagicMock) -> None:
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB") as mock_mapdb_cls:
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            assert reader._emu is mock_emu
            mock_mapdb_cls.assert_called_once_with("/fake/rom.gb")

    def test_default_properties(self, mock_emu: MagicMock) -> None:
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            assert reader.read_u8(0x1234) == _MEMORY.get(0x1234, 0)
            assert reader.read_u16(0x1234) == (
                _MEMORY.get(0x1234, 0) | (_MEMORY.get(0x1235, 0) << 8)
            )


class TestRAMReaderPlayerState:
    def test_player_x(self, mock_emu: MagicMock) -> None:
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            assert reader.player_x() == 5  # 9 - 4 = 5

    def test_player_y(self, mock_emu: MagicMock) -> None:
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            assert reader.player_y() == 3  # 7 - 4 = 3

    def test_player_facing_down(self, mock_emu: MagicMock) -> None:
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            assert reader.player_facing() == "down"

    def test_player_facing_up(self, mock_emu: MagicMock) -> None:
        _MEMORY[0xC109] = 0x04
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            assert reader.player_facing() == "up"

    def test_player_facing_left(self, mock_emu: MagicMock) -> None:
        _MEMORY[0xC109] = 0x08
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            assert reader.player_facing() == "left"

    def test_player_facing_right(self, mock_emu: MagicMock) -> None:
        _MEMORY[0xC109] = 0x0C
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            assert reader.player_facing() == "right"

    def test_is_moving_false(self, mock_emu: MagicMock) -> None:
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            assert reader.is_moving() is False

    def test_is_moving_true(self, mock_emu: MagicMock) -> None:
        _MEMORY[0xCFC5] = 1
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            assert reader.is_moving() is True

    def test_current_map_id(self, mock_emu: MagicMock) -> None:
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            assert reader.current_map_id() == 0x00

    def test_current_map_name_pallet(self, mock_emu: MagicMock) -> None:
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            assert reader.current_map_name() == "Pallet Town"

    def test_current_map_name_unknown(self, mock_emu: MagicMock) -> None:
        _MEMORY[0xD35E] = 0xFF  # unknown map
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            assert reader.current_map_name() == "Map_FF"


class TestRAMReaderScreenType:
    def test_overworld(self, mock_emu: MagicMock) -> None:
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            assert reader.screen_type() == "overworld"

    def test_battle_wild(self, mock_emu: MagicMock) -> None:
        _MEMORY[0xD057] = 1
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            assert reader.screen_type() == "battle"

    def test_battle_trainer(self, mock_emu: MagicMock) -> None:
        _MEMORY[0xD057] = 2
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            assert reader.screen_type() == "battle"

    def test_dialog(self, mock_emu: MagicMock) -> None:
        _MEMORY[0xCF2B] = 1
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            assert reader.screen_type() == "dialog"

    def test_name_entry(self, mock_emu: MagicMock) -> None:
        _MEMORY[0xCC47] = 1
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            assert reader.screen_type() == "name_entry"


class TestRAMReaderAdjacentBlocks:
    def test_adjacent_returns_blocks(self, mock_emu: MagicMock) -> None:
        """Player at (5, 3) on a 4×4 map: (5,3) is just outside map bounds
        (player is at map edge or during transition)."""
        from src.core.ram_reader import RAMReader, _MapDB

        # Mock _MapDB directly with known map data
        with patch("src.core.ram_reader._MapDB") as mock_mapdb_cls:
            mock_db = MagicMock()
            mock_db.get_map.return_value = {
                "tileset": 4,
                "width": 4,
                "height": 4,
                "block_data": [0x0F, 0x10, 0x0F, 0x10,
                               0x10, 0x0D, 0x10, 0x0F,
                               0x0F, 0x10, 0x12, 0x0F,
                               0x10, 0x0F, 0x0F, 0x10],
            }
            mock_mapdb_cls.return_value = mock_db

            # Player at (5,3) — outside 4×4 map — all should be "void"
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            adj = reader.adjacent_blocks()
            assert adj == {"up": "void", "down": "void",
                           "left": "void", "right": "void"}

    def test_adjacent_inside_bounds(self, mock_emu: MagicMock) -> None:
        """Move player to (2,2) on 4×4 map — all 4 adjacent cells exist."""
        _MEMORY[0xD361] = 6  # y = 2
        _MEMORY[0xD362] = 6  # x = 2

        from src.core.ram_reader import RAMReader, _MapDB

        with patch("src.core.ram_reader._MapDB") as mock_mapdb_cls:
            mock_db = MagicMock()
            mock_db.get_map.return_value = {
                "tileset": 4,
                "width": 4,
                "height": 4,
                "block_data": [0x0F, 0x10, 0x0F, 0x10,
                               0x10, 0x0D, 0x10, 0x0F,
                               0x0F, 0x10, 0x12, 0x0F,
                               0x10, 0x0F, 0x0F, 0x10],
            }
            mock_db.classify_block.side_effect = \
                lambda b, t: {0x0F: "floor", 0x10: "wall",
                            0x0D: "stairs", 0x12: "object"}.get(b, "unknown")
            mock_mapdb_cls.return_value = mock_db

            reader = RAMReader(mock_emu, "/fake/rom.gb")
            adj = reader.adjacent_blocks()

            # Player at (2,2): up=(2,1)=0x10=wall, down=(2,3)=0x0F=floor,
            # left=(1,2)=0x10=wall, right=(3,2)=0x0F=floor
            assert adj["up"] == "wall"
            assert adj["down"] == "floor"
            assert adj["left"] == "wall"
            assert adj["right"] == "floor"


class TestRAMReaderBuildMinimap:
    def test_minimap_renders_player_position(self, mock_emu: MagicMock) -> None:
        """Player at (2,2) on a 4×4 map — minimap shows PP at centre."""
        _MEMORY[0xD361] = 6  # y = 2
        _MEMORY[0xD362] = 6  # x = 2

        from src.core.ram_reader import RAMReader, _MapDB

        with patch("src.core.ram_reader._MapDB") as mock_mapdb_cls:
            mock_db = MagicMock()
            mock_db.get_map.return_value = {
                "tileset": 4,
                "width": 4,
                "height": 4,
                "block_data": [0x0F, 0x10, 0x0F, 0x10,
                               0x10, 0x0D, 0x10, 0x0F,
                               0x0F, 0x10, 0x12, 0x0F,
                               0x10, 0x0F, 0x0F, 0x10],
            }
            mock_db.classify_block.side_effect = \
                lambda b, t: {0x0F: "floor", 0x10: "wall",
                            0x0D: "stairs", 0x12: "object"}.get(b, "unknown")
            mock_mapdb_cls.return_value = mock_db

            reader = RAMReader(mock_emu, "/fake/rom.gb")
            minimap = reader.build_minimap(radius=2)

            # At (2,2) with radius 2 on a 4×4 map:
            # rows 0-3, cols 0-3 — the PP marker should appear
            assert "PP" in minimap
            assert "██" in minimap  # some wall
            assert "··" in minimap  # some floor

    def test_minimap_unknown_map(self, mock_emu: MagicMock) -> None:
        from src.core.ram_reader import RAMReader, _MapDB

        with patch("src.core.ram_reader._MapDB") as mock_mapdb_cls:
            mock_db = MagicMock()
            mock_db.get_map.return_value = None
            mock_mapdb_cls.return_value = mock_db

            reader = RAMReader(mock_emu, "/fake/rom.gb")
            minimap = reader.build_minimap()
            assert "No map data" in minimap

    def test_minimap_player_outside_bounds(self, mock_emu: MagicMock) -> None:
        """Player at (5,3) on 4×4 map — outside message shown."""
        from src.core.ram_reader import RAMReader, _MapDB

        with patch("src.core.ram_reader._MapDB") as mock_mapdb_cls:
            mock_db = MagicMock()
            mock_db.get_map.return_value = {
                "tileset": 4,
                "width": 4,
                "height": 4,
                "block_data": [0x0F] * 16,
            }
            mock_db.classify_block.return_value = "unknown"
            mock_mapdb_cls.return_value = mock_db

            reader = RAMReader(mock_emu, "/fake/rom.gb")
            minimap = reader.build_minimap(radius=2)
            assert "outside" in minimap.lower()


class TestRAMReaderObserve:
    def test_returns_structured_dict(self, mock_emu: MagicMock) -> None:
        from src.core.ram_reader import RAMReader, _MapDB

        with patch("src.core.ram_reader._MapDB") as mock_mapdb_cls:
            mock_db = MagicMock()
            mock_db.get_map.return_value = {
                "tileset": 4,
                "width": 4,
                "height": 4,
                "block_data": [0x0F] * 16,
            }
            mock_db.classify_block.return_value = "floor"
            mock_mapdb_cls.return_value = mock_db

            reader = RAMReader(mock_emu, "/fake/rom.gb")
            obs = reader.observe()

            assert isinstance(obs, dict)
            assert obs["result"] == "overworld"
            assert obs["player_x"] == 5
            assert obs["player_y"] == 3
            assert obs["map_name"] == "Pallet Town"
            assert obs["player_facing"] == "down"
            assert "adjacent" in obs
            assert "minimap" in obs
            assert obs["map_dimensions"] == "4×4"
            assert obs["map_tileset"] == 4
            assert obs["suggested_action"] == "explore the area"

    def test_battle_observe(self, mock_emu: MagicMock) -> None:
        _MEMORY[0xD057] = 1
        from src.core.ram_reader import RAMReader, _MapDB

        with patch("src.core.ram_reader._MapDB") as mock_mapdb_cls:
            mock_db = MagicMock()
            mock_db.get_map.return_value = None
            mock_mapdb_cls.return_value = mock_db

            reader = RAMReader(mock_emu, "/fake/rom.gb")
            obs = reader.observe()
            assert obs["result"] == "battle"
            assert obs["suggested_action"] == "choose a battle action"

    def test_dialog_observe(self, mock_emu: MagicMock) -> None:
        _MEMORY[0xCF2B] = 1
        from src.core.ram_reader import RAMReader, _MapDB

        with patch("src.core.ram_reader._MapDB") as mock_mapdb_cls:
            mock_db = MagicMock()
            mock_db.get_map.return_value = None
            mock_mapdb_cls.return_value = mock_db

            reader = RAMReader(mock_emu, "/fake/rom.gb")
            obs = reader.observe()
            assert obs["result"] == "dialog"
            assert obs["suggested_action"] == "advance the dialogue"

    def test_name_entry_observe(self, mock_emu: MagicMock) -> None:
        _MEMORY[0xCC47] = 1
        from src.core.ram_reader import RAMReader, _MapDB

        with patch("src.core.ram_reader._MapDB") as mock_mapdb_cls:
            mock_db = MagicMock()
            mock_db.get_map.return_value = None
            mock_mapdb_cls.return_value = mock_db

            reader = RAMReader(mock_emu, "/fake/rom.gb")
            obs = reader.observe()
            assert obs["result"] == "name_entry"
            assert obs["suggested_action"] == "enter a name"

    def test_exits_detected(self, mock_emu: MagicMock) -> None:
        """Player at (2,2) adjacent to stairs and door."""
        _MEMORY[0xD361] = 6  # y = 2
        _MEMORY[0xD362] = 6  # x = 2

        from src.core.ram_reader import RAMReader, _MapDB

        with patch("src.core.ram_reader._MapDB") as mock_mapdb_cls:
            mock_db = MagicMock()
            mock_db.get_map.return_value = {
                "tileset": 4,
                "width": 4,
                "height": 4,
                "block_data": [0x0F] * 16,
            }
            mock_db.classify_block.side_effect = \
                lambda b, t: {0x0F: "floor"}.get(b, "unknown")
            mock_mapdb_cls.return_value = mock_db

            reader = RAMReader(mock_emu, "/fake/rom.gb")
            obs = reader.observe()

            # Player at (2,2): all adjacent are 0x0F→floor — no exits
            assert obs["visible_exits"] == []
            assert "explore the area" in obs["suggested_action"]
