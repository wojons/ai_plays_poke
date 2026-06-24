"""
Unit tests for tile_utils — TSV strip format + tile extraction.

Tests cover:
- strip_to_tsv / tsv_to_strip roundtrip
- normalize_strip_terrain (detect packed vs TSV)
- pad_strip_terrain
- extract_tile_strip (N/S horizontal, E/W vertical → horizontal)
- OBS_PATCH TSV parsing (terrain_tsv, objects_tsv)
- MapIntegrator applying TSV strips
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import numpy as np

from src.core.tile_utils import (
    strip_to_tsv,
    tsv_to_strip,
    normalize_strip_terrain,
    pad_strip_terrain,
    extract_tile_strip,
    GB_SCREEN_PX,
    GB_TILE_PX,
    GB_VIEWPORT_TILES,
    VIEWPORT_TILE_WIDTH,
    SAMPLE_STRIP_TSV,
    SAMPLE_STRIP_PACKED,
)
from src.core.obs_patch import parse_obs_patch
from src.core.map_integrator import MapIntegrator


# ═════════════════════════════════════════════════════════════════════════════
# TSV conversion tests
# ═════════════════════════════════════════════════════════════════════════════


class TestStripToTsv:
    """Tests for strip_to_tsv."""

    def test_simple(self):  # type: ignore
        assert strip_to_tsv("T.g") == "T\t.\tg"

    def test_all_same(self):  # type: ignore
        assert strip_to_tsv("....") == ".\t.\t.\t."

    def test_single_char(self):  # type: ignore
        assert strip_to_tsv("T") == "T"

    def test_empty_string(self):  # type: ignore
        assert strip_to_tsv("") == ""

    def test_mixed_terrain(self):  # type: ignore
        packed = "TTT....ggg....T"
        tsv = strip_to_tsv(packed)
        assert "\t" in tsv
        # Roundtrip: TSV back to packed
        assert tsv_to_strip(tsv) == packed

    def test_sample_constant_matches(self):  # type: ignore
        """SAMPLE_STRIP_TSV should be the TSV form of SAMPLE_STRIP_PACKED."""
        assert strip_to_tsv(SAMPLE_STRIP_PACKED) == SAMPLE_STRIP_TSV


class TestTsvToStrip:
    """Tests for tsv_to_strip."""

    def test_simple(self):  # type: ignore
        assert tsv_to_strip("T\t.\tg") == "T.g"

    def test_with_whitespace(self):  # type: ignore
        """Tokens are preserved as-is — spaces are meaningful (e.g. for objects)."""
        assert tsv_to_strip("T\t .\tg ") == "T .g "

    def test_consecutive_tabs(self):  # type: ignore
        """Consecutive tabs produce empty tokens (stripped to '')."""
        assert tsv_to_strip("T\t\tg") == "Tg"

    def test_trailing_tab(self):  # type: ignore
        assert tsv_to_strip("T.\t") == "T."

    def test_empty_string(self):  # type: ignore
        assert tsv_to_strip("") == ""

    def test_no_tabs(self):  # type: ignore
        """Pass-through for non-TSV strings."""
        assert tsv_to_strip("TTTggg") == "TTTggg"


class TestNormalizeStripTerrain:
    """Tests for normalize_strip_terrain."""

    def test_packed_passthrough(self):  # type: ignore
        assert normalize_strip_terrain("TTTggg") == "TTTggg"

    def test_tsv_detected_and_converted(self):  # type: ignore
        result = normalize_strip_terrain("T\t.\tg")
        assert result == "T.g"

    def test_empty_string(self):  # type: ignore
        assert normalize_strip_terrain("") == ""

    def test_mixed_format(self):  # type: ignore
        """Full strip TSV → packed."""
        tsv = strip_to_tsv("TTT....ggg....T")
        result = normalize_strip_terrain(tsv)
        assert result == "TTT....ggg....T"


class TestPadStripTerrain:
    """Tests for pad_strip_terrain."""

    def test_pads_short(self):  # type: ignore
        result = pad_strip_terrain("TTT", target_length=15)
        assert len(result) == 15
        assert result == "TTT????????????"

    def test_exact_length(self):  # type: ignore
        result = pad_strip_terrain("TTT....ggg....T", target_length=15)
        assert result == "TTT....ggg....T"

    def test_truncates_long(self):  # type: ignore
        result = pad_strip_terrain("TTT....ggg....TTTT", target_length=15)
        assert len(result) == 15
        assert result == "TTT....ggg....T"

    def test_default_target(self):  # type: ignore
        result = pad_strip_terrain("T")
        assert len(result) == VIEWPORT_TILE_WIDTH  # 15


# ═════════════════════════════════════════════════════════════════════════════
# Tile extraction tests
# ═════════════════════════════════════════════════════════════════════════════


class TestExtractTileStrip:
    """Tests for extract_tile_strip.

    Creates synthetic screenshots and extracts tile strips from them.
    """

    @staticmethod
    def _make_screen() -> np.ndarray:
        """Create a synthetic GB-sized RGB screen (144 rows × 160 cols)."""
        # Fill with a gradient so tiles are distinguishable
        screen = np.zeros((GB_SCREEN_PX[1], GB_SCREEN_PX[0], 3), dtype=np.uint8)
        for y in range(GB_SCREEN_PX[1]):
            for x in range(GB_SCREEN_PX[0]):
                tile_x = x // GB_TILE_PX
                tile_y = y // GB_TILE_PX
                # Color-code tiles: red channel = tile_x * 25, green = tile_y * 28
                screen[y, x, 0] = tile_x * 25
                screen[y, x, 1] = tile_y * 28
                screen[y, x, 2] = 128
        return screen

    def test_extract_north_strip(self):  # type: ignore
        """Extract top row of tiles (N edge)."""
        screen = self._make_screen()
        # Top row of tiles is at y_px = 0
        strip = extract_tile_strip(screen, "N", 0, start=0, length=10)

        assert strip is not None
        # Height should be one tile (16 px)
        assert strip.shape[0] == GB_TILE_PX
        # Width should be 10 tiles × 16 px = 160 px
        assert strip.shape[1] == 10 * GB_TILE_PX
        assert strip.shape[2] == 3

        # Verify first tile: should be tile (0,0) — red chan 0, green 0
        first_tile = strip[:, 0:16, :]
        assert np.all(first_tile[:, :, 0] == 0)  # tile_x=0 → red=0
        assert np.all(first_tile[:, :, 1] == 0)  # tile_y=0 → green=0

        # Last tile: tile (9,0) — red chan 225, green 0
        last_tile = strip[:, -16:, :]
        assert np.all(last_tile[:, :, 0] == 9 * 25)  # tile_x=9 → red=225
        assert np.all(last_tile[:, :, 1] == 0)

    def test_extract_south_strip(self):  # type: ignore
        """Extract bottom row of tiles (S edge)."""
        screen = self._make_screen()
        # Bottom row of tiles is at y_px = (9-1)*16 = 128
        y_px = (GB_VIEWPORT_TILES[1] - 1) * GB_TILE_PX
        strip = extract_tile_strip(screen, "S", y_px, start=0, length=10)

        assert strip is not None
        assert strip.shape[0] == GB_TILE_PX
        assert strip.shape[1] == 10 * GB_TILE_PX

        # Green channel should be (8 * 28) = 224 for bottom row
        first_tile = strip[:, 0:16, :]
        assert np.all(first_tile[:, :, 1] == 8 * 28)

    def test_extract_east_strip(self):  # type: ignore
        """E/W movement: column of tiles extracted and arranged horizontally."""
        screen = self._make_screen()
        # Rightmost column at x_px = (10-1)*16 = 144
        x_px = (GB_VIEWPORT_TILES[0] - 1) * GB_TILE_PX
        strip = extract_tile_strip(screen, "E", x_px, start=0, length=9)

        assert strip is not None
        # Height = tile_px (16), Width = 9 tiles * 16 = 144
        assert strip.shape[0] == GB_TILE_PX
        assert strip.shape[1] == 9 * GB_TILE_PX

        # First tile in strip: tile (9, 0) — red=225, green=0
        first_tile = strip[:, 0:16, :]
        assert np.all(first_tile[:, :, 0] == 9 * 25)
        assert np.all(first_tile[:, :, 1] == 0)

        # Last tile in strip: tile (9, 8) — red=225, green=224
        last_tile = strip[:, -16:, :]
        assert np.all(last_tile[:, :, 0] == 9 * 25)
        assert np.all(last_tile[:, :, 1] == 8 * 28)

    def test_extract_west_strip(self):  # type: ignore
        """Extract leftmost column (W edge)."""
        screen = self._make_screen()
        strip = extract_tile_strip(screen, "W", 0, start=0, length=9)

        assert strip is not None
        assert strip.shape[0] == GB_TILE_PX
        assert strip.shape[1] == 9 * GB_TILE_PX

        # All tiles have red=0 (column 0)
        for i in range(9):
            tile = strip[:, i * 16 : (i + 1) * 16, :]
            assert np.all(tile[:, :, 0] == 0)

    def test_east_strip_is_horizontal_layout(self):  # type: ignore
        """E/W strips must be horizontal (single row of tiles).

        The whole point is that the vision model always sees one
        horizontal row regardless of movement direction.
        """
        screen = self._make_screen()
        x_px = (GB_VIEWPORT_TILES[0] - 1) * GB_TILE_PX
        strip = extract_tile_strip(screen, "E", x_px, start=0, length=9)

        # Height must be exactly one tile (16)
        assert strip.shape[0] == GB_TILE_PX  # type: ignore
        # Width > height (horizontal strip)
        assert strip.shape[1] > strip.shape[0]  # type: ignore

    def test_out_of_bounds_returns_none(self):  # type: ignore
        """Extracting beyond screen edges returns None."""
        screen = self._make_screen()
        # y too large
        assert extract_tile_strip(screen, "N", 200) is None
        # negative y
        assert extract_tile_strip(screen, "S", -1) is None
        # x too large
        assert extract_tile_strip(screen, "E", 200) is None

    def test_partial_strip_truncated(self):  # type: ignore
        """If length extends beyond screen, return what we can."""
        screen = self._make_screen()
        # Start at tile 8, request 5 tiles — only 2 tiles fit (8, 9)
        strip = extract_tile_strip(screen, "N", 0, start=8, length=5)
        assert strip is not None
        assert strip.shape[1] == 2 * GB_TILE_PX  # only 2 tiles fit


# ═════════════════════════════════════════════════════════════════════════════
# OBS_PATCH TSV parsing tests
# ═════════════════════════════════════════════════════════════════════════════


class TestObsPatchTsvParsing:
    """Tests that OBS_PATCH parser accepts terrain_tsv."""

    def test_terrain_tsv_overrides_empty_terrain(self):  # type: ignore
        """terrain_tsv should be used when terrain is empty."""
        data = {
            "prev_tick": 0,
            "tick": 1,
            "movement": {
                "input": "DOWN",
                "result": "moved",
                "player_delta": [0, 1],
                "facing": "S",
                "mode": "walk",
            },
            "viewport": {
                "origin_delta": [0, 1],
                "new_edge": "S",
            },
            "strip": {
                "edge": "S",
                "global_y": 5,
                "x_start": 2,
                "terrain": "",
                "terrain_tsv": "T\t.\tg\t.\tT",
            },
        }
        patch = parse_obs_patch(data)
        assert patch.strip is not None
        assert patch.strip.terrain == "T.g.T"

    def test_terrain_takes_priority_over_terrain_tsv(self):  # type: ignore
        """When both provided, terrain (packed) wins."""
        data = {
            "strip": {
                "edge": "N",
                "global_y": 0,
                "x_start": 0,
                "terrain": "T..#",
                "terrain_tsv": "g\tg\tg\tg",
            },
        }
        patch = parse_obs_patch(data)
        assert patch.strip is not None
        assert patch.strip.terrain == "T..#"

    def test_objects_tsv(self):  # type: ignore
        """objects_tsv works the same way."""
        data = {
            "strip": {
                "edge": "N",
                "global_y": 3,
                "x_start": 0,
                "objects_tsv": "D\t \tI\t ",
            },
        }
        patch = parse_obs_patch(data)
        assert patch.strip is not None
        assert patch.strip.objects == "D I "

    def test_actors_tsv(self):  # type: ignore
        """actors_tsv works the same way."""
        data = {
            "strip": {
                "edge": "N",
                "global_y": 2,
                "x_start": 0,
                "actors_tsv": "u\t \tP\t ",
            },
        }
        patch = parse_obs_patch(data)
        assert patch.strip is not None
        assert patch.strip.actors == "u P "


# ═════════════════════════════════════════════════════════════════════════════
# MapIntegrator TSV strip tests
# ═════════════════════════════════════════════════════════════════════════════


class TestMapIntegratorTsvStrip:
    """Tests that MapIntegrator.apply works with TSV-formatted strips."""

    def test_apply_tsv_strip_north(self):  # type: ignore
        """MapIntegrator accepts TSV terrain in a north-movement patch."""
        mi = MapIntegrator()
        mi.world.init_blank(20, 20)
        mi.world.player.pos = (5, 5)
        mi.world.player.facing = "N"
        mi.world.viewport.origin = (0, 0)

        patch_data = {
            "prev_tick": 0,
            "tick": 1,
            "movement": {
                "input": "UP",
                "result": "moved",
                "player_delta": [0, -1],
                "facing": "N",
                "mode": "walk",
            },
            "viewport": {
                "origin_delta": [0, -1],
                "new_edge": "N",
            },
            "strip": {
                "edge": "N",
                "global_y": 0,
                "x_start": 0,
                "terrain_tsv": "T\tT\t.\t.\tg\tg\t#\t#\t~\t~\t.\t.\t.\t.\tT",
            },
        }
        result = mi.apply(patch_data)
        assert result is True

        # Verify terrain was written correctly
        assert mi.world.terrain_at(0, 0) == "T"
        assert mi.world.terrain_at(1, 0) == "T"
        assert mi.world.terrain_at(2, 0) == "."
        assert mi.world.terrain_at(4, 0) == "g"
        assert mi.world.terrain_at(6, 0) == "#"
        assert mi.world.terrain_at(8, 0) == "~"
        assert mi.world.terrain_at(14, 0) == "T"

    def test_apply_tsv_strip_east(self):  # type: ignore
        """MapIntegrator accepts TSV terrain in an east-movement patch."""
        mi = MapIntegrator()
        mi.world.init_blank(20, 20)
        mi.world.player.pos = (5, 5)
        mi.world.player.facing = "E"
        mi.world.viewport.origin = (0, 0)

        patch_data = {
            "prev_tick": 0,
            "tick": 1,
            "movement": {
                "input": "RIGHT",
                "result": "moved",
                "player_delta": [1, 0],
                "facing": "E",
                "mode": "walk",
            },
            "viewport": {
                "origin_delta": [1, 0],
                "new_edge": "E",
            },
            "strip": {
                "edge": "E",
                "global_x": 15,
                "y_start": 0,
                "terrain_tsv": "T\tg\t.\t#\t~",
            },
        }
        result = mi.apply(patch_data)
        assert result is True

        # Verify terrain written vertically along column x=15
        assert mi.world.terrain_at(15, 0) == "T"
        assert mi.world.terrain_at(15, 1) == "g"
        assert mi.world.terrain_at(15, 2) == "."
        assert mi.world.terrain_at(15, 3) == "#"
        assert mi.world.terrain_at(15, 4) == "~"

    def test_apply_mixed_packed_and_tsv(self):  # type: ignore
        """MapIntegrator handles terrain as packed, objects as TSV."""
        mi = MapIntegrator()
        mi.world.init_blank(20, 20)
        mi.world.player.pos = (5, 5)
        mi.world.player.facing = "S"
        mi.world.viewport.origin = (0, 0)

        patch_data = {
            "prev_tick": 0,
            "tick": 1,
            "movement": {
                "input": "DOWN",
                "result": "moved",
                "player_delta": [0, 1],
                "facing": "S",
                "mode": "walk",
            },
            "viewport": {
                "origin_delta": [0, 1],
                "new_edge": "S",
            },
            "strip": {
                "edge": "S",
                "global_y": 10,
                "x_start": 0,
                "terrain": "TTT....ggg....T",  # packed
                "objects_tsv": "D\t \t \tI\t \t \t \t \t \t \t \t \t \t \t ",  # TSV
            },
        }
        result = mi.apply(patch_data)
        assert result is True

        assert mi.world.terrain_at(0, 10) == "T"
        assert mi.world.terrain_at(4, 10) == "."
        assert mi.world.terrain_at(7, 10) == "g"
        assert mi.world.object_at(0, 10) == "D"
        assert mi.world.object_at(3, 10) == "I"


# ═════════════════════════════════════════════════════════════════════════════
# Viewport constant verification
# ═════════════════════════════════════════════════════════════════════════════


class TestViewportConstants:
    """Verify tile/px constants are internally consistent."""

    def test_gb_screen_dimensions(self):  # type: ignore
        assert GB_SCREEN_PX[0] == 160  # width
        assert GB_SCREEN_PX[1] == 144  # height

    def test_tiles_fit_screen_evenly(self):  # type: ignore
        """Tile count × tile size should equal screen dimensions."""
        assert GB_VIEWPORT_TILES[0] * GB_TILE_PX == GB_SCREEN_PX[0]  # 10 × 16 = 160
        assert GB_VIEWPORT_TILES[1] * GB_TILE_PX == GB_SCREEN_PX[1]  # 9 × 16 = 144

    def test_viewport_tile_width_reasonable(self):  # type: ignore
        """The canonical viewport tile width should be at least the visible width."""
        assert VIEWPORT_TILE_WIDTH >= GB_VIEWPORT_TILES[0]  # 15 >= 10
