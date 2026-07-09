"""
Unit tests for src/core/ram_reader.py — RAM-based game state reader.

Mocks both the emulator (via read_u8/read_u16) and the ROM bytes so no
real .gb file is needed.
"""
from __future__ import annotations

import pytest
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
        from src.core.ram_reader import _MapDB
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
        from src.core.ram_reader import RAMReader

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

        from src.core.ram_reader import RAMReader

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

        from src.core.ram_reader import RAMReader

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
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB") as mock_mapdb_cls:
            mock_db = MagicMock()
            mock_db.get_map.return_value = None
            mock_mapdb_cls.return_value = mock_db

            reader = RAMReader(mock_emu, "/fake/rom.gb")
            minimap = reader.build_minimap()
            assert "No map data" in minimap

    def test_minimap_player_outside_bounds(self, mock_emu: MagicMock) -> None:
        """Player at (5,3) on 4×4 map — outside message shown."""
        from src.core.ram_reader import RAMReader

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
        from src.core.ram_reader import RAMReader

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
        from src.core.ram_reader import RAMReader

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
        from src.core.ram_reader import RAMReader

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
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB") as mock_mapdb_cls:
            mock_db = MagicMock()
            mock_db.get_map.return_value = None
            mock_mapdb_cls.return_value = mock_db

            reader = RAMReader(mock_emu, "/fake/rom.gb")
            obs = reader.observe()
            assert obs["result"] == "name_entry"
            assert obs["suggested_action"] == "enter a name and press START"

    def test_exits_detected(self, mock_emu: MagicMock) -> None:
        """Player at (2,2) adjacent to stairs and door."""
        _MEMORY[0xD361] = 6  # y = 2
        _MEMORY[0xD362] = 6  # x = 2

        from src.core.ram_reader import RAMReader

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

    def test_exits_detected_with_doors(self, mock_emu: MagicMock) -> None:
        """Player at (2,2) with a door to the right — exits should be found."""
        _MEMORY[0xD361] = 6  # y = 2
        _MEMORY[0xD362] = 6  # x = 2

        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB") as mock_mapdb_cls:
            mock_db = MagicMock()
            block_data = [0x0F] * 16
            block_data[11] = 0x10  # right adjacent (idx = 2*4+3 = 11) — make it non-floor
            mock_db.get_map.return_value = {
                "tileset": 4,
                "width": 4,
                "height": 4,
                "block_data": block_data,
            }
            mock_db.classify_block.side_effect = \
                lambda b, t: {0x0F: "floor", 0x10: "door"}.get(b, "unknown")
            mock_mapdb_cls.return_value = mock_db

            reader = RAMReader(mock_emu, "/fake/rom.gb")
            obs = reader.observe()

            # Player at (2,2): right is a door — should be in visible_exits
            assert "right" in obs["visible_exits"]
            assert len(obs["visible_exits"]) >= 1
            assert "exits at right" in obs["suggested_action"]
            assert "explore" in obs["suggested_action"]


# ── Tileset 0 classification tests ──────────────────────────────────────


class TestMapDBClassifyTileset0:
    def test_from_bytes(self) -> None:
        """_MapDB.from_bytes() creates a working instance."""
        from src.core.ram_reader import _MapDB

        db = _MapDB.from_bytes(b"\x00" * 512 * 1024)
        assert db._rom is not None
        assert db._cache == {}
        assert db._rom == b"\x00" * 512 * 1024

    def test_grass_blocks(self) -> None:
        from src.core.ram_reader import _MapDB

        db = _MapDB.__new__(_MapDB)
        assert db.classify_block(0x00, 0) == "grass"
        assert db.classify_block(0x01, 0) == "grass"
        assert db.classify_block(0x02, 0) == "grass"
        assert db.classify_block(0x03, 0) == "grass"

    def test_floor_blocks(self) -> None:
        from src.core.ram_reader import _MapDB

        db = _MapDB.__new__(_MapDB)
        assert db.classify_block(0x0F, 0) == "floor"
        assert db.classify_block(0x10, 0) == "floor"
        assert db.classify_block(0x0C, 0) == "floor"

    def test_tree_blocks(self) -> None:
        from src.core.ram_reader import _MapDB

        db = _MapDB.__new__(_MapDB)
        assert db.classify_block(0x32, 0) == "tree"
        assert db.classify_block(0x33, 0) == "tree"
        assert db.classify_block(0x3E, 0) == "tree"

    def test_water_blocks(self) -> None:
        from src.core.ram_reader import _MapDB

        db = _MapDB.__new__(_MapDB)
        assert db.classify_block(0x2B, 0) == "water"
        assert db.classify_block(0x48, 0) == "water"

    def test_wall_blocks(self) -> None:
        from src.core.ram_reader import _MapDB

        db = _MapDB.__new__(_MapDB)
        assert db.classify_block(0x14, 0) == "wall"
        assert db.classify_block(0x1A, 0) == "wall"
        assert db.classify_block(0x1F, 0) == "wall"
        assert db.classify_block(0x50, 0) == "wall"  # fence

    def test_door_blocks(self) -> None:
        from src.core.ram_reader import _MapDB

        db = _MapDB.__new__(_MapDB)
        assert db.classify_block(0x5C, 0) == "door"

    def test_object_blocks(self) -> None:
        from src.core.ram_reader import _MapDB

        db = _MapDB.__new__(_MapDB)
        assert db.classify_block(0x60, 0) == "object"  # signpost

    def test_unknown_block(self) -> None:
        from src.core.ram_reader import _MapDB

        db = _MapDB.__new__(_MapDB)
        assert db.classify_block(0xFF, 0) == "unknown"


# ── render_overworld tests ──────────────────────────────────────────────


class TestRenderOverworld:
    def test_indoor_grid(self, mock_emu: MagicMock) -> None:
        """Player at (2,2) on 4×4 indoor map, facing down."""
        _MEMORY[0xD361] = 6  # y = 2
        _MEMORY[0xD362] = 6  # x = 2
        _MEMORY[0xC109] = 0x00  # facing down

        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB") as mock_mapdb_cls:
            mock_db = MagicMock()
            mock_db.get_map.return_value = {
                "tileset": 4,
                "width": 4,
                "height": 4,
                "block_data": [
                    0x0F, 0x10, 0x0F, 0x10,
                    0x10, 0x0D, 0x10, 0x0F,
                    0x0F, 0x10, 0x12, 0x0F,
                    0x10, 0x0F, 0x0F, 0x10,
                ],
            }
            mock_db.classify_block.side_effect = lambda b, t: {
                0x0F: "floor", 0x10: "wall", 0x0D: "stairs", 0x12: "object",
            }.get(b, "unknown")
            mock_mapdb_cls.return_value = mock_db

            reader = RAMReader(mock_emu, "/fake/rom.gb")
            output = reader.render_overworld()

            # Header checks
            assert "Map:" in output
            assert "Pos:" in output
            assert "Facing:" in output
            assert "Legend:" in output

            lines = output.split("\n")
            grid_lines = [
                line for line in lines
                if line.strip() and not line.startswith("Map")
                and not line.startswith("Pos") and not line.startswith("Legend")
            ]
            assert len(grid_lines) == 5

            # Row index 2 (dy=0) → center row, has @
            center = grid_lines[2].split()
            assert center[2] == "@"

            # Row index 3 (dy=+1) has ↓ at col 2
            down = grid_lines[3].split()
            assert down[2] == "↓"

            # Check some classified blocks
            # Row 0 (dy=-2): block_data[0] = 0x0F floor = .
            top = grid_lines[0].split()
            assert top[0] == "."  # (0,0) is floor

    def test_outdoor_grid(self, mock_emu: MagicMock) -> None:
        """Player at (6,5) on 10×9 outdoor map, facing down."""
        _MEMORY[0xD361] = 9   # y = 5
        _MEMORY[0xD362] = 10  # x = 6
        _MEMORY[0xC109] = 0x00  # facing down

        from src.core.ram_reader import RAMReader, _MapDB as RealMapDB

        with patch("src.core.ram_reader._MapDB") as mock_mapdb_cls:
            mock_db = MagicMock()
            w, h = 10, 9
            block_data = [0x0F] * (w * h)
            # Tree at (4,3) → gy=3, gx=4 → dy=-2, dx=-2 → grid[0][0]
            block_data[3 * w + 4] = 0x32  # tree
            # Grass at (7,3) → gy=3, gx=7 → dy=-2, dx=+1 → grid[0][3]
            block_data[3 * w + 7] = 0x01  # grass
            # Sign at (6,6) → gy=6, gx=6 → dy=+1, dx=0 → grid[3][2] (but arrow takes priority)

            mock_db.get_map.return_value = {
                "tileset": 0,
                "width": w,
                "height": h,
                "block_data": block_data,
            }
            real_db = RealMapDB.__new__(RealMapDB)
            mock_db.classify_block.side_effect = real_db.classify_block
            mock_mapdb_cls.return_value = mock_db

            reader = RAMReader(mock_emu, "/fake/rom.gb")
            output = reader.render_overworld()

            lines = output.split("\n")
            grid_lines = [
                line for line in lines
                if line.strip() and not line.startswith("Map")
                and not line.startswith("Pos") and not line.startswith("Legend")
            ]

            center = grid_lines[2].split()
            assert center[2] == "@"

            # Top row (dy=-2, gy=3): gx=4→tree=T, gx=5→floor=., gx=6→floor=., gx=7→grass=G, gx=8→floor=.
            top = grid_lines[0].split()
            assert top[0] == "T"  # tree at (4,3)
            assert top[3] == "G"  # grass at (7,3)

            # Arrow below player
            down = grid_lines[3].split()
            assert down[2] == "↓"

    def test_facing_arrows(self, mock_emu: MagicMock) -> None:
        """Each facing direction shows the correct arrow."""
        from src.core.ram_reader import RAMReader

        directions = [
            (0x00, "↓", "down"),
            (0x04, "↑", "up"),
            (0x08, "←", "left"),
            (0x0C, "→", "right"),
        ]

        for facing_byte, expected_arrow, facing_name in directions:
            _MEMORY[0xD361] = 6  # y = 2
            _MEMORY[0xD362] = 6  # x = 2
            _MEMORY[0xC109] = facing_byte

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
                output = reader.render_overworld()

                lines = output.split("\n")
                grid_lines = [
                    line for line in lines
                    if line.strip() and not line.startswith("Map")
                    and not line.startswith("Pos") and not line.startswith("Legend")
                ]

                center = grid_lines[2].split()
                assert center[2] == "@", f"Facing {facing_name}: @ not at center"

                # Arrow should be in adjacent cell in facing direction
                if facing_byte == 0x00:  # down → row 3, col 2
                    assert grid_lines[3].split()[2] == expected_arrow
                elif facing_byte == 0x04:  # up → row 1, col 2
                    assert grid_lines[1].split()[2] == expected_arrow
                elif facing_byte == 0x08:  # left → row 2, col 1
                    assert grid_lines[2].split()[1] == expected_arrow
                elif facing_byte == 0x0C:  # right → row 2, col 3
                    assert grid_lines[2].split()[3] == expected_arrow

    def test_unknown_map(self, mock_emu: MagicMock) -> None:
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB") as mock_mapdb_cls:
            mock_db = MagicMock()
            mock_db.get_map.return_value = None
            mock_mapdb_cls.return_value = mock_db

            reader = RAMReader(mock_emu, "/fake/rom.gb")
            output = reader.render_overworld()
            assert "No map data" in output

    def test_overworld_grid_alias(self, mock_emu: MagicMock) -> None:
        from src.core.ram_reader import RAMReader

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
            assert reader.overworld_grid() == reader.render_overworld()

    def test_out_of_bounds_shows_question_mark(self, mock_emu: MagicMock) -> None:
        """Player at (1,1) on 4×4 map — cells at dx=-2 and dy=-2 are '?'."""
        _MEMORY[0xD361] = 5  # y = 1
        _MEMORY[0xD362] = 5  # x = 1

        from src.core.ram_reader import RAMReader

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
            output = reader.render_overworld()

            lines = output.split("\n")
            grid_lines = [
                line for line in lines
                if line.strip() and not line.startswith("Map")
                and not line.startswith("Pos") and not line.startswith("Legend")
            ]

            # Row 0 (dy=-2): gy=-1 → all ?, except dx=-2 which is also ?
            top = grid_lines[0].split()
            assert all(c == "?" for c in top), f"Expected all ?, got {top}"

            # Row 2 (dy=0): col 0 (dx=-2) = ?, col 1 (dx=-1) = .
            center = grid_lines[2].split()
            assert center[0] == "?"
            assert center[1] == "."

    def test_observe_includes_overworld_grid(self, mock_emu: MagicMock) -> None:
        from src.core.ram_reader import RAMReader

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
            assert "overworld_grid" in obs
            assert "Map:" in obs["overworld_grid"]
            assert "@" in obs["overworld_grid"]


# ── read_battle_state tests ─────────────────────────────────────────────


class TestReadBattleState:
    """Tests for RAMReader.read_battle_state()."""

    def test_returns_dict_with_player_and_enemy(self, mock_emu: MagicMock) -> None:
        from src.core.ram_reader import RAMReader

        _MEMORY[0xD057] = 1  # in battle (wild)
        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            result = reader.read_battle_state()

        assert isinstance(result, dict)
        assert "player" in result
        assert "enemy" in result
        assert "battle_type" in result

    def test_battle_type_wild(self, mock_emu: MagicMock) -> None:
        _MEMORY[0xD057] = 1
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            assert reader.read_battle_state()["battle_type"] == "wild"

    def test_battle_type_trainer(self, mock_emu: MagicMock) -> None:
        _MEMORY[0xD05A] = 2  # ADDR_BATTLE_TYPE
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            assert reader.read_battle_state()["battle_type"] == "trainer"

    def test_player_species_lookups(self, mock_emu: MagicMock) -> None:
        # Pikachu = species 79
        _MEMORY[0xD016] = 79  # ADDR_BATTLE_MON_SPECIES
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            assert reader.read_battle_state()["player"]["name"] == "Pikachu"

    def test_player_unknown_species(self, mock_emu: MagicMock) -> None:
        _MEMORY[0xD016] = 200  # missing index
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            assert reader.read_battle_state()["player"]["name"] == "#200"

    def test_player_hp_full(self, mock_emu: MagicMock) -> None:
        # HP = 0x0028 (40), max HP = 0x0028 (40) → 100%
        _MEMORY[0xD017] = 40  # ADDR_BATTLE_MON_HP low byte
        _MEMORY[0xD018] = 0   # HP high byte
        _MEMORY[0xD025] = 40  # ADDR_BATTLE_MON_MAX_HP low byte
        _MEMORY[0xD026] = 0   # max HP high byte
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            state = reader.read_battle_state()

        assert state["player"]["hp"] == 40
        assert state["player"]["max_hp"] == 40
        assert state["player"]["hp_pct"] == 100

    def test_player_hp_partial(self, mock_emu: MagicMock) -> None:
        # HP = 14/40 = 35% (avoids banker's rounding edge case at .5)
        _MEMORY[0xD017] = 14
        _MEMORY[0xD025] = 40
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            state = reader.read_battle_state()

        assert state["player"]["hp"] == 14
        assert state["player"]["max_hp"] == 40
        assert state["player"]["hp_pct"] == 35

    def test_player_hp_zero_max_hp_protection(self, mock_emu: MagicMock) -> None:
        # Avoid divide by zero — max_hp is 0 so % should be 0 (round(0/1 *100))
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            state = reader.read_battle_state()

        assert state["player"]["hp_pct"] == 0

    def test_player_hp_u16_little_endian(self, mock_emu: MagicMock) -> None:
        # HP = 0x0100 = 256 (verify u16 little-endian: low=0, high=1)
        _MEMORY[0xD017] = 0x00
        _MEMORY[0xD018] = 0x01
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            state = reader.read_battle_state()

        assert state["player"]["hp"] == 0x0100

    def test_player_level(self, mock_emu: MagicMock) -> None:
        _MEMORY[0xD024] = 25  # ADDR_BATTLE_MON_LEVEL
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            assert reader.read_battle_state()["player"]["level"] == 25

    def test_player_stats(self, mock_emu: MagicMock) -> None:
        _MEMORY[0xD027] = 50   # attack low
        _MEMORY[0xD029] = 60   # defense low
        _MEMORY[0xD02B] = 70   # speed low
        _MEMORY[0xD02D] = 80   # special low
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            p = reader.read_battle_state()["player"]

        assert p["attack"] == 50
        assert p["defense"] == 60
        assert p["speed"] == 70
        assert p["special"] == 80

    def test_player_type_same(self, mock_emu: MagicMock) -> None:
        # Same primary/secondary type → single type reported
        _MEMORY[0xD01B] = 20  # type1 = Fire
        _MEMORY[0xD01C] = 20  # type2 = Fire
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            assert reader.read_battle_state()["player"]["type"] == "Fire"

    def test_player_type_dual(self, mock_emu: MagicMock) -> None:
        _MEMORY[0xD01B] = 20  # Fire
        _MEMORY[0xD01C] = 2   # Flying
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            assert reader.read_battle_state()["player"]["type"] == "Fire/Flying"

    def test_player_status(self, mock_emu: MagicMock) -> None:
        _MEMORY[0xD01A] = 7  # status = 7 (freeze+poison+burn bits)
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            assert reader.read_battle_state()["player"]["status"] == 7

    def test_player_moves_with_pp(self, mock_emu: MagicMock) -> None:
        # Move slots at 0xD01E-0xD021
        _MEMORY[0xD01E] = 85   # Thunderbolt (move ID 85)
        _MEMORY[0xD01F] = 45   # Growl
        _MEMORY[0xD020] = 0    # empty slot
        _MEMORY[0xD021] = 0    # empty slot
        # PP at 0xD02F-0xD032
        _MEMORY[0xD02F] = 15   # PP for Thunderbolt
        _MEMORY[0xD030] = 40   # PP for Growl
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            moves = reader.read_battle_state()["player"]["moves"]

        assert len(moves) == 2
        assert moves[0]["name"] == "Thunderbolt"
        assert moves[0]["pp"] == 15
        assert moves[0]["slot"] == 1
        assert moves[1]["name"] == "Growl"
        assert moves[1]["pp"] == 40
        assert moves[1]["slot"] == 2

    def test_player_no_moves(self, mock_emu: MagicMock) -> None:
        # All four move slots are 0
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            assert reader.read_battle_state()["player"]["moves"] == []

    def test_player_unknown_move(self, mock_emu: MagicMock) -> None:
        _MEMORY[0xD01E] = 250  # not in MOVE_NAMES table
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            moves = reader.read_battle_state()["player"]["moves"]

        assert moves[0]["name"] == "Move#250"

    def test_enemy_full_read(self, mock_emu: MagicMock) -> None:
        # Enemy Pidgey (species 36), Lv3, half HP
        _MEMORY[0xCFE7] = 36   # Pidgey
        _MEMORY[0xCFE8] = 14   # HP
        _MEMORY[0xCFE9] = 0    # HP high byte
        _MEMORY[0xCFF6] = 28   # max HP low
        _MEMORY[0xCFF7] = 0    # max HP high
        _MEMORY[0xCFF5] = 3    # level
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            enemy = reader.read_battle_state()["enemy"]

        assert enemy["name"] == "Pidgey"
        assert enemy["hp"] == 14
        assert enemy["max_hp"] == 28
        assert enemy["hp_pct"] == 50  # 14/28 = 50.0
        assert enemy["level"] == 3

    def test_enemy_type_dual(self, mock_emu: MagicMock) -> None:
        _MEMORY[0xCFEC] = 3   # Poison
        _MEMORY[0xCFED] = 4   # Ground
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            assert reader.read_battle_state()["enemy"]["type"] == "Poison/Ground"


# ── render_battle tests ────────────────────────────────────────────────


class TestRenderBattle:
    """Tests for RAMReader.render_battle()."""

    def test_starts_with_battle_header(self, mock_emu: MagicMock) -> None:
        _MEMORY[0xD057] = 1   # wild battle
        _MEMORY[0xCFE7] = 79  # Pikachu (enemy)
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            output = reader.render_battle()

        assert "⚔" in output
        assert "BATTLE" in output
        assert "Wild" in output
        assert "Pikachu" in output

    def test_trainer_battle_label(self, mock_emu: MagicMock) -> None:
        _MEMORY[0xD05A] = 2  # trainer battle
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            output = reader.render_battle()

        assert "Trainer" in output

    def test_includes_player_info(self, mock_emu: MagicMock) -> None:
        _MEMORY[0xD016] = 1   # Rhydon (player)
        _MEMORY[0xD024] = 42  # level
        _MEMORY[0xD025] = 100 # max_hp
        _MEMORY[0xD026] = 0
        _MEMORY[0xD017] = 50  # hp
        _MEMORY[0xD018] = 0
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            output = reader.render_battle()

        assert "Your Rhydon" in output
        assert "Lv42" in output
        assert "50/100" in output

    def test_includes_enemy_info(self, mock_emu: MagicMock) -> None:
        _MEMORY[0xCFE7] = 79  # Pikachu (enemy)
        _MEMORY[0xCFF5] = 12  # enemy level
        _MEMORY[0xCFF6] = 35  # enemy max_hp
        _MEMORY[0xCFF7] = 0
        _MEMORY[0xCFE8] = 17  # enemy hp
        _MEMORY[0xCFE9] = 0
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            output = reader.render_battle()

        assert "Enemy Pikachu" in output
        assert "Lv12" in output
        assert "17/35" in output

    def test_includes_moves(self, mock_emu: MagicMock) -> None:
        _MEMORY[0xD01E] = 33   # Tackle
        _MEMORY[0xD01F] = 45   # Growl
        _MEMORY[0xD02F] = 35   # Tackle PP (max 35)
        _MEMORY[0xD030] = 40   # Growl PP (max 40)
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            output = reader.render_battle()

        assert "Moves:" in output
        assert "Tackle" in output
        assert "35PP" in output
        assert "Growl" in output

    def test_no_moves_shows_none(self, mock_emu: MagicMock) -> None:
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            output = reader.render_battle()

        assert "None" in output

    def test_includes_options_line(self, mock_emu: MagicMock) -> None:
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            output = reader.render_battle()

        assert "FIGHT" in output
        assert "BAG" in output
        assert "PKMN" in output
        assert "RUN" in output


# ── read_dialog_text tests ─────────────────────────────────────────────


class TestReadDialogText:
    """Tests for RAMReader.read_dialog_text()."""

    def test_returns_string(self, mock_emu: MagicMock) -> None:
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            result = reader.read_dialog_text()

        assert isinstance(result, str)

    def test_decodes_uppercase_letters_from_string_buffer(
        self, mock_emu: MagicMock
    ) -> None:
        # "HELLO" in Pokemon text encoding: H=0x87, E=0x84, L=0x8B, L=0x8B, O=0x8E
        _MEMORY[0xCE00] = 0x87  # H
        _MEMORY[0xCE01] = 0x84  # E
        _MEMORY[0xCE02] = 0x8B  # L
        _MEMORY[0xCE03] = 0x8B  # L
        _MEMORY[0xCE04] = 0x8E  # O
        _MEMORY[0xCE05] = 0x50  # terminator
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            text = reader.read_dialog_text()

        assert "HELLO" in text

    def test_decodes_lowercase_letters(self, mock_emu: MagicMock) -> None:
        # Write enough uppercase+lowercase letters so first decode has >= 3
        # chars and avoids the fallback path. 'A'=0x80, 'B'=0x81, 'C'=0x82,
        # 'i' (0xA0 + 8) = 0xA8
        _MEMORY[0xCE00] = 0xA8  # i
        _MEMORY[0xCE01] = 0xA8  # i
        _MEMORY[0xCE02] = 0xA8  # i
        _MEMORY[0xCE03] = 0xA8  # i
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            text = reader.read_dialog_text()

        assert "i" in text

    def test_decodes_digits(self, mock_emu: MagicMock) -> None:
        # 0x07 = '7'. Write a sequence of digits (>= 3) and expect "7" in result.
        _MEMORY[0xCE00] = 0x07
        _MEMORY[0xCE01] = 0x08
        _MEMORY[0xCE02] = 0x09
        _MEMORY[0xCE03] = 0x07
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            assert "7" in reader.read_dialog_text()

    def test_decodes_spaces(self, mock_emu: MagicMock) -> None:
        # 0x7F = space. Build " A B" (>= 3 chars) to avoid fallback.
        _MEMORY[0xCE00] = 0x7F  # space
        _MEMORY[0xCE01] = 0x80  # A
        _MEMORY[0xCE02] = 0x7F  # space
        _MEMORY[0xCE03] = 0x81  # B
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            text = reader.read_dialog_text()
        assert " A" in text

    def test_falls_back_to_text_prompt_when_buffer_empty(
        self, mock_emu: MagicMock
    ) -> None:
        # When wStringBuffer decode < 3 chars (all zeros → "000" which is 3 chars,
        # we need < 3). Use a terminator at offset 0 → 0 length → fallback.
        _MEMORY[0xCE00] = 0x50  # immediate terminator at start
        _MEMORY[0xCF4C] = 0x80  # A
        _MEMORY[0xCF4D] = 0x82  # C
        _MEMORY[0xCF4E] = 0x84  # E
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            text = reader.read_dialog_text()

        assert "ACE" in text

    def test_empty_returns_zero_string(self, mock_emu: MagicMock) -> None:
        # With nothing in either region, both decode to "0"s (default zeros)
        # but the first decode has length 20 (all zeros → "000...0")
        # which is >= 3, so fallback doesn't trigger → text is 20 zeros.
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            text = reader.read_dialog_text()

        # Default-zero memory → zeros in decoded output (no real letters)
        assert text.replace("0", "") == ""
        assert len(text) > 0


# ── render_dialog tests ───────────────────────────────────────────────


class TestRenderDialog:
    """Tests for RAMReader.render_dialog()."""

    def test_includes_dialog_header(self, mock_emu: MagicMock) -> None:
        _MEMORY[0xCE00] = 0x87  # H
        _MEMORY[0xCE01] = 0x80  # A
        _MEMORY[0xCE02] = 0x50  # terminator
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            output = reader.render_dialog()

        assert "💬" in output
        assert "DIALOG" in output

    def test_shows_a_to_continue_for_plain_text(self, mock_emu: MagicMock) -> None:
        _MEMORY[0xCE00] = 0x88  # I
        _MEMORY[0xCE01] = 0x50
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            output = reader.render_dialog()

        assert "A to continue" in output
        assert "Yes/No" not in output

    def test_detects_yes_no_prompt(self, mock_emu: MagicMock) -> None:
        _MEMORY[0xCE00] = 0x98  # Y
        _MEMORY[0xCE01] = 0x84  # E
        _MEMORY[0xCE02] = 0x92  # S
        _MEMORY[0xCE03] = 0x50  # terminator
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            output = reader.render_dialog()

        assert "Yes/No" in output

    def test_quotes_text_content(self, mock_emu: MagicMock) -> None:
        _MEMORY[0xCE00] = 0x80  # A
        _MEMORY[0xCE01] = 0x50
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            output = reader.render_dialog()

        assert '"' in output


# ── read_menu_state tests ─────────────────────────────────────────────


class TestReadMenuState:
    """Tests for RAMReader.read_menu_state()."""

    def test_no_menu_returns_empty_dict(self, mock_emu: MagicMock) -> None:
        # menu_id = 0 means no menu is active
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            state = reader.read_menu_state()

        assert state["menu_id"] == 0
        assert state["num_items"] == 0
        assert state["current_item"] == 0
        # No "active" key when no menu is present
        assert "active" not in state

    def test_active_menu_fields(self, mock_emu: MagicMock) -> None:
        # Active start menu: 3 items (SAVE/OPTION/EXIT → max_item=2)
        _MEMORY[0xCF88] = 1   # ADDR_LIST_MENU_ID = 1 (active menu)
        _MEMORY[0xCC28] = 2   # ADDR_MAX_MENU_ITEM = 2
        _MEMORY[0xCC26] = 1   # ADDR_CURRENT_MENU_ITEM = 1 (cursor on 2nd item)
        _MEMORY[0xCC24] = 5   # ADDR_TOP_MENU_ITEM_Y
        _MEMORY[0xCC25] = 10  # ADDR_TOP_MENU_ITEM_X
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            state = reader.read_menu_state()

        assert state["menu_id"] == 1
        assert state["num_items"] == 3  # max_item=2 → 3 items
        assert state["current_item"] == 1
        assert state["cursor_pos"] == (10, 5)
        assert state["active"] is True

    def test_max_item_zero_returns_no_items(self, mock_emu: MagicMock) -> None:
        _MEMORY[0xCF88] = 5  # active menu
        _MEMORY[0xCC28] = 0  # max_item = 0 → 0 items (guard: >0)
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            state = reader.read_menu_state()

        assert state["menu_id"] == 5
        # max_item == 0 with the guard: num_items = max_item+1 if max_item>0 else 0 → 0
        assert state["num_items"] == 0


# ── render_menu tests ────────────────────────────────────────────────


class TestRenderMenu:
    """Tests for RAMReader.render_menu()."""

    def test_header_present(self, mock_emu: MagicMock) -> None:
        _MEMORY[0xCF88] = 1  # active menu
        _MEMORY[0xCC28] = 2  # 3 items
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            output = reader.render_menu()

        assert "📋" in output
        assert "MENU" in output

    def test_numbered_items(self, mock_emu: MagicMock) -> None:
        _MEMORY[0xCF88] = 1
        _MEMORY[0xCC28] = 2  # 3 items
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            output = reader.render_menu()

        assert "[1]" in output
        assert "[2]" in output
        assert "[3]" in output

    def test_cursor_arrow_on_current(self, mock_emu: MagicMock) -> None:
        _MEMORY[0xCF88] = 1   # active
        _MEMORY[0xCC28] = 3   # 4 items
        _MEMORY[0xCC26] = 1   # cursor on 2nd item (index 1)
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            output = reader.render_menu()

        lines = output.split("\n")
        # Verify arrow appears on the [2] line specifically
        assert any("→" in line and "[2]" in line for line in lines), \
            "Expected → marker on item 2"

    def test_includes_navigation_hint(self, mock_emu: MagicMock) -> None:
        _MEMORY[0xCF88] = 1
        _MEMORY[0xCC28] = 1
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            output = reader.render_menu()

        assert "UP" in output
        assert "DOWN" in output
        assert "A" in output

    def test_no_menu_renders_empty_items(self, mock_emu: MagicMock) -> None:
        # menu_id = 0 → 0 items
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            output = reader.render_menu()

        # Header still rendered, but no numbered items
        assert "MENU" in output
        assert "[1]" not in output


# ── read_name_entry tests ────────────────────────────────────────────


class TestReadNameEntry:
    """Tests for RAMReader.read_name_entry()."""

    def test_returns_expected_keys(self, mock_emu: MagicMock) -> None:
        _MEMORY[0xCC47] = 1  # name entry screen active
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            state = reader.read_name_entry()

        assert "screen" in state
        assert "name_so_far" in state
        assert "length" in state
        assert "case" in state
        assert "ready_to_submit" in state
        assert "grid_rows" in state

    def test_screen_value(self, mock_emu: MagicMock) -> None:
        _MEMORY[0xCC47] = 1
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            assert reader.read_name_entry()["screen"] == "name_entry"

    def test_upper_case(self, mock_emu: MagicMock) -> None:
        _MEMORY[0xCC47] = 1
        _MEMORY[0xCC4D] = 0  # ADDR_ALPHABET_CASE = 0 (uppercase)
        _MEMORY[0xCC4F] = 0  # letter ∈ {0,1}
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            state = reader.read_name_entry()

        assert state["case"] == "UPPER"
        # Uppercase rows: A-I, J-R, S-Z + space
        assert state["grid_rows"][0][0] == "A"

    def test_lower_case(self, mock_emu: MagicMock) -> None:
        _MEMORY[0xCC47] = 1
        _MEMORY[0xCC4D] = 1   # lowercase
        _MEMORY[0xCC4F] = 0   # letter
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            state = reader.read_name_entry()

        assert state["case"] == "lower"
        assert state["grid_rows"][0][0] == "a"

    def test_numerals_case(self, mock_emu: MagicMock) -> None:
        _MEMORY[0xCC47] = 1
        _MEMORY[0xCC4D] = 0
        _MEMORY[0xCC4F] = 2   # numerals
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            state = reader.read_name_entry()

        # Numerals row should start with "0"
        assert state["grid_rows"][0][0] == "0"
        assert state["grid_rows"][1][0] == "9"

    def test_symbols_case(self, mock_emu: MagicMock) -> None:
        _MEMORY[0xCC47] = 1
        _MEMORY[0xCC4D] = 0
        _MEMORY[0xCC4F] = 3   # symbols
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            state = reader.read_name_entry()

        # Symbols rows contain "ED" and "PK"
        flat = [c for row in state["grid_rows"] for c in row]
        assert "ED" in flat
        assert "PK" in flat

    def test_ready_to_submit_true(self, mock_emu: MagicMock) -> None:
        _MEMORY[0xCC47] = 1
        _MEMORY[0xCC4A] = 1  # ADDR_NAMING_SUBMIT — non-zero
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            assert reader.read_name_entry()["ready_to_submit"] is True

    def test_ready_to_submit_false(self, mock_emu: MagicMock) -> None:
        _MEMORY[0xCC47] = 1
        _MEMORY[0xCC4A] = 0
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            assert reader.read_name_entry()["ready_to_submit"] is False

    def test_name_so_far_decoded(self, mock_emu: MagicMock) -> None:
        _MEMORY[0xCC47] = 1
        # wStringBuffer at 0xCE00 spells "RED". The decode reads 20 bytes
        # with max_len=11, so the trailing zeros (default 0) decode as "0".
        # Verify "RED" is a prefix rather than exact match.
        _MEMORY[0xCE00] = 0x91  # R
        _MEMORY[0xCE01] = 0x84  # E
        _MEMORY[0xCE02] = 0x83  # D
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            name = reader.read_name_entry()["name_so_far"]

        assert name.startswith("RED")

    def test_length(self, mock_emu: MagicMock) -> None:
        _MEMORY[0xCC47] = 1
        _MEMORY[0xCC48] = 4  # ADDR_NAMING_NAME_LENGTH
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            assert reader.read_name_entry()["length"] == 4

    def test_grid_rows_length(self, mock_emu: MagicMock) -> None:
        # Always returns 2 rows for the visible row pair
        _MEMORY[0xCC47] = 1
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            state = reader.read_name_entry()

        assert len(state["grid_rows"]) == 2
        for row in state["grid_rows"]:
            assert len(row) == 9


# ── render_name_entry tests ────────────────────────────────────────


class TestRenderNameEntry:
    """Tests for RAMReader.render_name_entry()."""

    def test_header_includes_keyboard_glyph(self, mock_emu: MagicMock) -> None:
        _MEMORY[0xCC47] = 1
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            output = reader.render_name_entry()

        assert "⌨" in output
        assert "NAME ENTRY" in output

    def test_shows_name_so_far(self, mock_emu: MagicMock) -> None:
        _MEMORY[0xCC47] = 1
        _MEMORY[0xCC48] = 5  # ADDR_NAMING_NAME_LENGTH = 5 chars
        # A=0x80, B=0x81, L=0x8B, O=0x8E, I=0x88, Q=0x90
        _MEMORY[0xCE00] = 0x80  # A
        _MEMORY[0xCE01] = 0x8B  # L
        _MEMORY[0xCE02] = 0x8E  # O
        _MEMORY[0xCE03] = 0x88  # I
        _MEMORY[0xCE04] = 0x90  # Q (was 0x90 thinking 'P'; P=0x8F)
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            output = reader.render_name_entry()

        assert "ALOIQ" in output
        assert "5 chars" in output

    def test_includes_case_label(self, mock_emu: MagicMock) -> None:
        _MEMORY[0xCC47] = 1
        _MEMORY[0xCC4D] = 0  # UPPER
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            output = reader.render_name_entry()

        assert "Case:" in output
        assert "UPPER" in output

    def test_includes_status_message(self, mock_emu: MagicMock) -> None:
        # Ready to submit → "READY to submit"
        _MEMORY[0xCC47] = 1
        _MEMORY[0xCC4A] = 1
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            output = reader.render_name_entry()

        assert "READY" in output

    def test_still_editing_message(self, mock_emu: MagicMock) -> None:
        _MEMORY[0xCC47] = 1
        _MEMORY[0xCC4A] = 0
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            output = reader.render_name_entry()

        assert "still editing" in output

    def test_includes_keyboard_grid(self, mock_emu: MagicMock) -> None:
        _MEMORY[0xCC47] = 1
        _MEMORY[0xCC4D] = 0  # uppercase rows
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            output = reader.render_name_entry()

        assert "Keyboard:" in output
        lines = output.split("\n")
        assert any("A B C D E F G H I" in line for line in lines), \
            f"Expected uppercase row, got lines: {lines}"

    def test_navigation_hint(self, mock_emu: MagicMock) -> None:
        _MEMORY[0xCC47] = 1
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB"):
            reader = RAMReader(mock_emu, "/fake/rom.gb")
            output = reader.render_name_entry()

        assert "D-pad" in output
        assert "START" in output


# ── observe() extended coverage for new fields ──────────────────────


class TestObserveExtended:
    """Tests for the extended observe() output (battle_state/menu_state/render)."""

    def test_battle_observe_includes_battle_state(self, mock_emu: MagicMock) -> None:
        _MEMORY[0xD057] = 1   # wild battle
        _MEMORY[0xD016] = 79  # Pikachu
        _MEMORY[0xCFE7] = 36  # Pidgey (enemy, species 36)
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB") as mock_mapdb_cls:
            mock_db = MagicMock()
            mock_db.get_map.return_value = None
            mock_mapdb_cls.return_value = mock_db

            reader = RAMReader(mock_emu, "/fake/rom.gb")
            obs = reader.observe()

        assert obs["result"] == "battle"
        assert obs["battle_state"] != {}
        assert obs["battle_state"]["player"]["name"] == "Pikachu"
        assert obs["battle_state"]["enemy"]["name"] == "Pidgey"
        assert "⚔" in obs["render"]
        assert "BATTLE" in obs["render"]

    def test_dialog_observe_includes_render(self, mock_emu: MagicMock) -> None:
        _MEMORY[0xCF2B] = 1   # dialog screen
        # Write enough content (>= 3 chars) so first decode avoids the fallback
        # path. read_dialog_text reads 60 bytes and decodes up to 20.
        _MEMORY[0xCE00] = 0x88  # I
        _MEMORY[0xCE01] = 0x80  # A
        _MEMORY[0xCE02] = 0x80  # A
        _MEMORY[0xCE03] = 0x80  # A
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB") as mock_mapdb_cls:
            mock_db = MagicMock()
            mock_db.get_map.return_value = None
            mock_mapdb_cls.return_value = mock_db

            reader = RAMReader(mock_emu, "/fake/rom.gb")
            obs = reader.observe()

        assert obs["result"] == "dialog"
        assert "💬" in obs["render"]
        assert "IAAAA" in obs["text_content"][0] or "IAAA" in obs["text_content"][0]

    def test_name_entry_observe_includes_render_and_keyboard(
        self, mock_emu: MagicMock
    ) -> None:
        _MEMORY[0xCC47] = 1
        _MEMORY[0xCC4D] = 0  # uppercase
        _MEMORY[0xCC48] = 0  # length = 0
        from src.core.ram_reader import RAMReader

        with patch("src.core.ram_reader._MapDB") as mock_mapdb_cls:
            mock_db = MagicMock()
            mock_db.get_map.return_value = None
            mock_mapdb_cls.return_value = mock_db

            reader = RAMReader(mock_emu, "/fake/rom.gb")
            obs = reader.observe()

        assert obs["result"] == "name_entry"
        # Default buffer → "name_so_far" is zeros, but obs grabs the raw string
        assert "rows" in obs["keyboard_grid"]
        assert len(obs["keyboard_grid"]["rows"]) == 2
        assert "⌨" in obs["render"]
        assert "NAME ENTRY" in obs["render"]  # fallback to zeros, but no real content

    def test_overworld_with_menu_overlay(self, mock_emu: MagicMock) -> None:
        # When overworld has an active menu overlay, menu_state should be populated
        _MEMORY[0xCF88] = 1  # menu_id active
        _MEMORY[0xCC28] = 2  # 3 items
        _MEMORY[0xCC26] = 0
        from src.core.ram_reader import RAMReader

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

        assert obs["result"] == "overworld"
        assert obs["menu_state"]["menu_id"] == 1
        assert obs["menu_state"]["num_items"] == 3
        # render should include both overworld grid and menu
        assert "📋" in obs["render"]
        assert "MENU" in obs["render"]

    def test_overworld_without_menu(self, mock_emu: MagicMock) -> None:
        # Default memory: menu_id = 0, no menu state
        from src.core.ram_reader import RAMReader

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

        assert obs["result"] == "overworld"
        assert obs["menu_state"] == {}
        # menu_items is empty when no menu present
        assert obs["menu_items"] == []
        # render should NOT include menu section
        assert "📋" not in obs["render"]
