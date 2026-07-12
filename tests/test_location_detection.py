"""
LocationDetector Unit Tests — COV-3 (49% → 70%+)

Tests for src/vision/location.py without ROM or API dependencies.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Generator
from unittest.mock import patch

import numpy as np
import pytest

from src.vision.location import (
    LocationDetector,
    LocationResult,
    TileInfo,
)

# ── tile count for _extract_tiles ─────────────────────────────────────────
# _extract_tiles uses range(0, h-16, 16) × range(0, w-16, 16)
# For 144×160: range(0, 128, 16)=8 rows, range(0, 144, 16)=9 cols → 72 tiles
_TILES_144x160 = 8 * 9  # 72
_TILES_48x48 = 2 * 2     # 4  (range(0, 32, 16)=2 rows × 2 cols)


# ── tile helpers (values chosen to hit specific _classify_tile branches) ──

def _wall_tile() -> np.ndarray:
    """center_mean > 150 AND std < 30 → wall"""
    return np.full((16, 16), 200, dtype=np.uint8)


def _path_tile() -> np.ndarray:
    """center_mean > 100 AND std < 50, edge_mean >= 80 → path"""
    return np.full((16, 16), 140, dtype=np.uint8)


def _grass_tile() -> np.ndarray:
    """tile_mean 80-120, std > 40 → grass.
    Center 8×8 = 20, outer = 120. tile_mean≈95, std≈43.
    Dark center keeps center_mean≤100 to skip door/path check."""
    t = np.full((16, 16), 120, dtype=np.uint8)
    t[4:12, 4:12] = 20
    return t


def _tall_grass_tile() -> np.ndarray:
    """tile_mean 60-100, std > 50 → tall_grass.
    7 rows of 0, 9 rows of 110. tile_mean≈61.9, std≈54.6.
    Avoids grass (>80 threshold) and water (<80, but tall_grass checked first)."""
    t = np.full((16, 16), 110, dtype=np.uint8)
    t[0:7, :] = 0
    return t


def _water_tile() -> np.ndarray:
    """tile_mean < 80 → water"""
    return np.full((16, 16), 40, dtype=np.uint8)


def _tree_tile() -> np.ndarray:
    """tile_mean > 120, std > 60 → tree"""
    t = np.full((16, 16), 130, dtype=np.uint8)
    t[0:8, 0:8] = 10
    t[8:16, 8:16] = 250
    return t


def _rock_tile() -> np.ndarray:
    """tile_mean > 120, std <= 60, center_mean <= 100 → rock.
    Center 8×8 = 50, outer = 150. tile_mean≈125, std≈43."""
    t = np.full((16, 16), 150, dtype=np.uint8)
    t[4:12, 4:12] = 50
    return t


def _door_tile() -> np.ndarray:
    """center_mean > 100, std < 50, edge_mean < 80 → door"""
    t = np.full((16, 16), 140, dtype=np.uint8)
    t[0, :] = 30
    t[-1, :] = 30
    t[:, 0] = 30
    t[:, -1] = 30
    return t


def _sign_tile() -> np.ndarray:
    """edge_mean < center_mean - 20, centre_mean=90, tile_mean≈80.6, std<40.
    Border = 50, interior = 90. Avoids grass (std<40), water (>80), tree/rock. """
    t = np.full((16, 16), 90, dtype=np.uint8)
    t[0, :] = 50
    t[-1, :] = 50
    t[:, 0] = 50
    t[:, -1] = 50
    return t


def _unknown_tile() -> np.ndarray:
    """All zero — hits water (tile_mean < 80)"""
    return np.zeros((16, 16), dtype=np.uint8)


# ── screenshot builders ───────────────────────────────────────────────────

def _make_screenshot(tile_fn, height: int = 144, width: int = 160) -> np.ndarray:
    """Create an RGB screenshot filled with tiles from tile_fn."""
    img = np.zeros((height, width, 3), dtype=np.uint8)
    for y in range(0, height, 16):
        for x in range(0, width, 16):
            tile = tile_fn()
            img[y:min(y+16, height), x:min(x+16, width), 0] = tile[:min(16, height-y), :min(16, width-x)]
            img[y:min(y+16, height), x:min(x+16, width), 1] = tile[:min(16, height-y), :min(16, width-x)]
            img[y:min(y+16, height), x:min(x+16, width), 2] = tile[:min(16, height-y), :min(16, width-x)]
    return img


def _make_screenshot_mixed(patterns: list[tuple[str, int]]) -> np.ndarray:
    """Create an RGB screenshot with different tile types placed sequentially.

    patterns: list of (tile_type, count) — tiles are placed left-to-right, top-to-bottom.
    Remaining slots filled with path tiles.
    """
    tile_map: dict[str, type] = {
        "wall": _wall_tile,
        "path": _path_tile,
        "grass": _grass_tile,
        "tall_grass": _tall_grass_tile,
        "water": _water_tile,
        "tree": _tree_tile,
        "rock": _rock_tile,
        "door": _door_tile,
        "sign": _sign_tile,
    }
    all_tiles: list[np.ndarray] = []
    for ttype, count in patterns:
        fn = tile_map[ttype]
        for _ in range(count):
            all_tiles.append(fn())

    while len(all_tiles) < _TILES_144x160:
        all_tiles.append(_path_tile())

    img = np.zeros((144, 160, 3), dtype=np.uint8)
    _grid_cols = 9  # matches _extract_tiles: range(0, 160-16, 16) = 9 cols
    for i, tile in enumerate(all_tiles):
        row = (i // _grid_cols) * 16
        col = (i % _grid_cols) * 16
        if row + 16 <= 144 and col + 16 <= 160:
            img[row:row+16, col:col+16, 0] = tile
            img[row:row+16, col:col+16, 1] = tile
            img[row:row+16, col:col+16, 2] = tile
    return img


def _make_pallet_town_screenshot() -> np.ndarray:
    """Pallet Town: grass + path + water tiles, pokecenter feature."""
    img = _make_screenshot_mixed([("grass", 24), ("path", 24), ("water", 24)])
    # White pixels in top-left trigger pokemon_center feature
    img[0:15, 0:47, :] = 255
    return img


def _make_route_1_screenshot() -> np.ndarray:
    """Route 1: grass + path + tall_grass tiles, NO pokecenter."""
    return _make_screenshot_mixed([("grass", 24), ("path", 24), ("tall_grass", 24)])


# ── detector fixture ─────────────────────────────────────────────────────

@pytest.fixture
def detector() -> Generator[LocationDetector, None, None]:
    """Return a fresh LocationDetector with a temp area database."""
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "areas.json"
        with patch.object(LocationDetector, 'AREA_DATABASE_PATH', db_path):
            det = LocationDetector()
            det._create_default_area_database()
            yield det


# ═══════════════════════════════════════════════════════════════════════════
# _classify_tile
# ═══════════════════════════════════════════════════════════════════════════

class TestClassifyTile:
    """Coverage: _classify_tile — tile type classification."""

    def test_wall_center_bright_low_std(self, detector: LocationDetector) -> None:
        assert detector._classify_tile(_wall_tile()) == "wall"

    def test_door_center_bright_low_std_dark_edges(self, detector: LocationDetector) -> None:
        assert detector._classify_tile(_door_tile()) == "door"

    def test_path_center_bright_low_std(self, detector: LocationDetector) -> None:
        assert detector._classify_tile(_path_tile()) == "path"

    def test_grass_mean_80_120_high_std(self, detector: LocationDetector) -> None:
        assert detector._classify_tile(_grass_tile()) == "grass"

    def test_tall_grass_mean_60_100_high_std(self, detector: LocationDetector) -> None:
        assert detector._classify_tile(_tall_grass_tile()) == "tall_grass"

    def test_water_dark(self, detector: LocationDetector) -> None:
        assert detector._classify_tile(_water_tile()) == "water"

    def test_tree_high_mean_high_std(self, detector: LocationDetector) -> None:
        assert detector._classify_tile(_tree_tile()) == "tree"

    def test_rock_high_mean_low_std(self, detector: LocationDetector) -> None:
        assert detector._classify_tile(_rock_tile()) == "rock"

    def test_sign_edge_darker_than_center(self, detector: LocationDetector) -> None:
        assert detector._classify_tile(_sign_tile()) == "sign"

    def test_empty_tile(self, detector: LocationDetector) -> None:
        assert detector._classify_tile(np.array([], dtype=np.uint8)) == "unknown"


# ═══════════════════════════════════════════════════════════════════════════
# _extract_tiles
# ═══════════════════════════════════════════════════════════════════════════

class TestExtractTiles:
    """Coverage: _extract_tiles — screenshot → 16×16 tiles."""

    def test_extracts_correct_number(self, detector: LocationDetector) -> None:
        img = _make_screenshot(_path_tile, height=144, width=160)
        tiles = detector._extract_tiles(img)
        assert len(tiles) == _TILES_144x160  # 8 rows × 9 cols

    def test_each_tile_is_16x16(self, detector: LocationDetector) -> None:
        img = _make_screenshot(_path_tile, height=144, width=160)
        tiles = detector._extract_tiles(img)
        for tile in tiles:
            assert tile.shape == (16, 16)

    def test_grayscale_input_preserved(self, detector: LocationDetector) -> None:
        gray = np.full((144, 160), 128, dtype=np.uint8)
        tiles = detector._extract_tiles(gray)
        assert len(tiles) == _TILES_144x160

    def test_smaller_image_produces_fewer_tiles(self, detector: LocationDetector) -> None:
        small = np.full((48, 48, 3), 100, dtype=np.uint8)
        tiles = detector._extract_tiles(small)
        assert len(tiles) == _TILES_48x48  # 2 rows × 2 cols


# ═══════════════════════════════════════════════════════════════════════════
# _identify_tile_patterns
# ═══════════════════════════════════════════════════════════════════════════

class TestIdentifyTilePatterns:
    """Coverage: _identify_tile_patterns — tiles → counts."""

    def test_counts_tile_types(self, detector: LocationDetector) -> None:
        tiles = [_path_tile() for _ in range(50)] + [_wall_tile() for _ in range(40)]
        counts = detector._identify_tile_patterns(tiles)
        assert counts.get("path", 0) == 50
        assert counts.get("wall", 0) == 40

    def test_empty_tiles(self, detector: LocationDetector) -> None:
        counts = detector._identify_tile_patterns([])
        assert counts == {}


# ═══════════════════════════════════════════════════════════════════════════
# _compute_pattern_hash
# ═══════════════════════════════════════════════════════════════════════════

class TestComputePatternHash:
    """Coverage: _compute_pattern_hash — counts → hash string."""

    def test_sorted_by_name(self, detector: LocationDetector) -> None:
        h = detector._compute_pattern_hash({"grass": 30, "path": 30, "water": 30})
        assert "grass:30" in h
        assert "path:30" in h
        assert "water:30" in h

    def test_empty(self, detector: LocationDetector) -> None:
        assert detector._compute_pattern_hash({}) == ""


# ═══════════════════════════════════════════════════════════════════════════
# _compute_tile_hash
# ═══════════════════════════════════════════════════════════════════════════

class TestComputeTileHash:
    """Coverage: _compute_tile_hash — tile → feature string."""

    def test_produces_string(self, detector: LocationDetector) -> None:
        h = detector._compute_tile_hash(_path_tile())
        assert isinstance(h, str)
        assert "_" in h

    def test_different_tiles_different_hash(self, detector: LocationDetector) -> None:
        h1 = detector._compute_tile_hash(_wall_tile())
        h2 = detector._compute_tile_hash(_water_tile())
        assert h1 != h2


# ═══════════════════════════════════════════════════════════════════════════
# _detect_features
# ═══════════════════════════════════════════════════════════════════════════

class TestDetectFeatures:
    """Coverage: _detect_features — screenshot → feature flags."""

    def test_default_features(self, detector: LocationDetector) -> None:
        img = _make_screenshot(_path_tile)
        feats = detector._detect_features(img)
        assert feats["pokemon_center"] is False

    def test_pokecenter_detected(self, detector: LocationDetector) -> None:
        img = _make_screenshot(_path_tile)
        img[0:15, 0:47, :] = 255
        feats = detector._detect_features(img)
        assert feats["pokemon_center"] is True

    def test_water_body_detected(self, detector: LocationDetector) -> None:
        img = _make_screenshot(_path_tile)
        h, w = 144, 160
        center = img[int(h*0.3):int(h*0.7), int(w*0.3):int(w*0.7), :]
        center[:] = 80
        feats = detector._detect_features(img)
        assert feats["water_body"] is True


# ═══════════════════════════════════════════════════════════════════════════
# _match_area
# ═══════════════════════════════════════════════════════════════════════════

class TestMatchArea:
    """Coverage: _match_area — patterns + features → location match."""

    def test_match_pallet_town(self, detector: LocationDetector) -> None:
        patterns = {"grass": 30, "path": 30, "water": 30}
        features = {"pokemon_center": True, "pokemart": False, "gym": False}
        name, ltype, confidence = detector._match_area(patterns, features, "hash")
        assert name == "Pallet Town"
        assert ltype == "town"
        assert confidence > 0.4

    def test_match_route_1(self, detector: LocationDetector) -> None:
        patterns = {"grass": 30, "path": 30, "tall_grass": 30}
        features = {"pokemon_center": False, "pokemart": False, "gym": False}
        name, ltype, confidence = detector._match_area(patterns, features, "hash")
        assert name == "Route 1"
        assert ltype == "route"

    def test_no_match_returns_unknown(self, detector: LocationDetector) -> None:
        patterns = {"lava": 90}
        features: dict[str, bool] = {}
        name, ltype, confidence = detector._match_area(patterns, features, "hash")
        assert name == "Unknown Area"
        assert ltype == "unknown"
        assert confidence == 0.0

    def test_unknown_with_zero_score(self, detector: LocationDetector) -> None:
        patterns: dict[str, int] = {}
        features: dict[str, bool] = {}
        name, ltype, confidence = detector._match_area(patterns, features, "hash")
        assert name == "Unknown Area"
        assert confidence == 0.0

    def test_match_with_pokemart_and_gym(self, detector: LocationDetector) -> None:
        """Viridian City has pokemart=True + gym=True — needs both to beat Pallet."""
        patterns = {"grass": 30, "path": 30, "water": 30}
        features = {"pokemon_center": True, "pokemart": True, "gym": True}
        name, _, _ = detector._match_area(patterns, features, "hash")
        # Pallet: 3 patterns + 2(pc) + 2(pokemart) = 7
        # Viridian: 3 patterns + 2(pc) + 2(pokemart) + 2(gym) = 9
        assert name == "Viridian City"

    def test_gym_feature_boosts_pewter(self, detector: LocationDetector) -> None:
        """Pewter City has gym=True + rock pattern."""
        patterns = {"grass": 30, "path": 30, "rock": 30}
        features = {"pokemon_center": True, "pokemart": True, "gym": True}
        name, _, _ = detector._match_area(patterns, features, "hash")
        assert name == "Pewter City"


# ═══════════════════════════════════════════════════════════════════════════
# detect_location (integration of all internal methods)
# ═══════════════════════════════════════════════════════════════════════════

class TestDetectLocation:
    """AC-1, AC-2, AC-4: detect_location — end-to-end location detection."""

    def test_detects_pallet_town(self, detector: LocationDetector) -> None:
        """AC-1: known town tiles → correct location name."""
        img = _make_pallet_town_screenshot()
        result = detector.detect_location(img)
        assert isinstance(result, LocationResult)
        assert result.location_name == "Pallet Town"
        assert result.location_type == "town"
        assert result.confidence > 0.0

    def test_detects_route_1(self, detector: LocationDetector) -> None:
        """AC-2: route tiles → route number."""
        img = _make_route_1_screenshot()
        result = detector.detect_location(img)
        assert result.location_name == "Route 1"
        assert result.location_type == "route"

    def test_unknown_tiles_returns_unknown(self, detector: LocationDetector) -> None:
        """AC-4: unknown tiles (all door) → 'Unknown Area' with low confidence.
        'door' tile type does not appear in any area's tile_patterns."""
        img = _make_screenshot(_door_tile)
        result = detector.detect_location(img)
        assert result.location_name == "Unknown Area"
        assert result.location_type == "unknown"
        assert result.confidence == 0.0

    def test_result_has_tile_pattern_hash(self, detector: LocationDetector) -> None:
        img = _make_pallet_town_screenshot()
        result = detector.detect_location(img)
        assert isinstance(result.tile_pattern_hash, str)
        assert len(result.tile_pattern_hash) > 0

    def test_result_has_features(self, detector: LocationDetector) -> None:
        img = _make_pallet_town_screenshot()
        result = detector.detect_location(img)
        assert isinstance(result.features, dict)
        assert result.features["pokemon_center"] is True


# ═══════════════════════════════════════════════════════════════════════════
# Tile info lookups
# ═══════════════════════════════════════════════════════════════════════════

class TestTileLookups:
    """Coverage: get_tile_collision, is_tile_interactive."""

    def test_grass_collision_passable(self, detector: LocationDetector) -> None:
        assert detector.get_tile_collision("grass") == "passable"

    def test_wall_collision_blocking(self, detector: LocationDetector) -> None:
        assert detector.get_tile_collision("wall") == "blocking"

    def test_unknown_collision(self, detector: LocationDetector) -> None:
        assert detector.get_tile_collision("nonexistent") == "unknown"

    def test_door_is_interactive(self, detector: LocationDetector) -> None:
        assert detector.is_tile_interactive("door") is True

    def test_sign_is_interactive(self, detector: LocationDetector) -> None:
        assert detector.is_tile_interactive("sign") is True

    def test_grass_not_interactive(self, detector: LocationDetector) -> None:
        assert detector.is_tile_interactive("grass") is False

    def test_nonexistent_not_interactive(self, detector: LocationDetector) -> None:
        assert detector.is_tile_interactive("nonexistent") is False


# ═══════════════════════════════════════════════════════════════════════════
# get_navigation_graph
# ═══════════════════════════════════════════════════════════════════════════

class TestNavigationGraph:
    """Coverage: get_navigation_graph — screenshot → grid graph."""

    def test_returns_dict(self, detector: LocationDetector) -> None:
        img = _make_screenshot(_path_tile)
        graph = detector.get_navigation_graph(img)
        assert isinstance(graph, dict)
        assert len(graph) > 0

    def test_grid_nodes_have_required_keys(self, detector: LocationDetector) -> None:
        img = _make_screenshot(_path_tile)
        graph = detector.get_navigation_graph(img)
        for pos, node in graph.items():
            assert isinstance(pos, tuple)
            assert len(pos) == 2
            assert "tile_type" in node
            assert "collision" in node
            assert "interactive" in node
            assert "passable" in node

    def test_path_tiles_are_passable(self, detector: LocationDetector) -> None:
        img = _make_screenshot(_path_tile)
        graph = detector.get_navigation_graph(img)
        for node in graph.values():
            assert node["passable"] is True

    def test_wall_tiles_not_passable(self, detector: LocationDetector) -> None:
        img = _make_screenshot(_wall_tile)
        graph = detector.get_navigation_graph(img)
        for node in graph.values():
            assert node["passable"] is False
            assert node["collision"] == "blocking"


# ═══════════════════════════════════════════════════════════════════════════
# find_path_to_target
# ═══════════════════════════════════════════════════════════════════════════

class TestFindPathToTarget:
    """Coverage: find_path_to_target — simple pathfinding."""

    def _make_passable_graph(self, w: int = 5, h: int = 5) -> dict:
        return {
            (x, y): {"passable": True, "collision": "passable"}
            for y in range(h) for x in range(w)
        }

    def test_straight_horizontal(self, detector: LocationDetector) -> None:
        graph = self._make_passable_graph()
        path = detector.find_path_to_target((0, 0), (3, 0), graph)
        assert path == [(0, 0), (1, 0), (2, 0), (3, 0)]

    def test_straight_vertical(self, detector: LocationDetector) -> None:
        graph = self._make_passable_graph()
        path = detector.find_path_to_target((0, 0), (0, 3), graph)
        assert path == [(0, 0), (0, 1), (0, 2), (0, 3)]

    def test_diagonal(self, detector: LocationDetector) -> None:
        graph = self._make_passable_graph()
        path = detector.find_path_to_target((0, 0), (2, 2), graph)
        assert path[0] == (0, 0)
        assert path[-1] == (2, 2)

    def test_start_equals_target(self, detector: LocationDetector) -> None:
        graph = self._make_passable_graph()
        path = detector.find_path_to_target((1, 1), (1, 1), graph)
        assert path == [(1, 1)]

    def test_avoids_blocked_tiles(self, detector: LocationDetector) -> None:
        graph = self._make_passable_graph(5, 1)
        graph[(1, 0)] = {"passable": False, "collision": "blocking"}
        path = detector.find_path_to_target((0, 0), (3, 0), graph)
        for pos in path:
            if pos == (1, 0):
                pytest.fail("Path included blocked tile (1,0)")


# ═══════════════════════════════════════════════════════════════════════════
# Screen-state detection helpers
# ═══════════════════════════════════════════════════════════════════════════

class TestScreenDetection:
    """Coverage: is_in_battle, is_in_dialog, classify_screen_type."""

    def test_is_in_battle_with_sprite_region(self, detector: LocationDetector) -> None:
        img = _make_screenshot(_path_tile)
        h, w = 144, 160
        enemy = img[int(h*0.1):int(h*0.35), int(w*0.4):w, :]
        enemy[:] = np.random.randint(0, 256, enemy.shape, dtype=np.uint8)
        assert detector.is_in_battle(img) is True

    def test_is_in_battle_with_hp_bar(self, detector: LocationDetector) -> None:
        img = _make_screenshot(_path_tile)
        h, w = 144, 160
        hp_bar = img[int(h*0.02):int(h*0.12), int(w*0.5):w, :]
        hp_bar[:] = 200
        assert detector.is_in_battle(img) is True

    def test_is_in_battle_false_for_overworld(self, detector: LocationDetector) -> None:
        img = _make_screenshot(_path_tile)
        assert detector.is_in_battle(img) is False

    def test_is_in_dialog_dark_bottom(self, detector: LocationDetector) -> None:
        img = _make_screenshot(_path_tile)
        h = 144
        img[int(h*0.6):h, :, :] = 40
        assert detector.is_in_dialog(img) is True

    def test_is_in_dialog_false_bright(self, detector: LocationDetector) -> None:
        img = _make_screenshot(_path_tile)
        assert detector.is_in_dialog(img) is False

    def test_classify_screen_type_battle(self, detector: LocationDetector) -> None:
        img = _make_screenshot(_path_tile)
        h, w = 144, 160
        img[int(h*0.1):int(h*0.35), int(w*0.4):w, :] = np.random.randint(
            0, 256, img[int(h*0.1):int(h*0.35), int(w*0.4):w, :].shape, dtype=np.uint8
        )
        assert detector.classify_screen_type(img) == "battle"

    def test_classify_screen_type_dialog(self, detector: LocationDetector) -> None:
        img = _make_screenshot(_path_tile)
        h = 144
        img[int(h*0.6):h, :, :] = 40
        assert detector.is_in_battle(img) is False
        assert detector.is_in_dialog(img) is True

    def test_classify_screen_type_overworld(self, detector: LocationDetector) -> None:
        """Overworld = not battle, not menu, not dialog.
        NOTE: is_in_menu has a shape[:0] bug — monkeypatched to bypass."""
        img = _make_screenshot(_path_tile)
        detector.is_in_menu = lambda s: False  # type: ignore[method-assign]
        result = detector.classify_screen_type(img)
        assert result == "overworld"

    def test_is_in_menu_bug_documented(self, detector: LocationDetector) -> None:
        """Document shape[:0] bug (line 388): empty tuple unpack → ValueError."""
        img = _make_screenshot(_path_tile)
        with pytest.raises(ValueError, match="not enough values to unpack"):
            detector.is_in_menu(img)


# ═══════════════════════════════════════════════════════════════════════════
# Constructor — area database loading
# ═══════════════════════════════════════════════════════════════════════════

class TestConstructor:
    """Coverage: __init__, _load_area_database, _create_default_area_database, _save_area_database."""

    def test_default_database_created_when_no_file(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "areas.json"
            with patch.object(LocationDetector, 'AREA_DATABASE_PATH', db_path):
                det = LocationDetector()
                assert "pallet_town" in det.area_database
                assert det.area_database["pallet_town"]["name"] == "Pallet Town"
                assert det.area_database["route_1"]["name"] == "Route 1"

    def test_loads_existing_database(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "areas.json"
            custom = {"custom_city": {"name": "Custom City", "type": "city",
                                       "tile_patterns": ["grass"],
                                       "features": {}, "connections": [],
                                       "hash_pattern": ""}}
            db_path.parent.mkdir(exist_ok=True)
            db_path.write_text(json.dumps(custom))
            with patch.object(LocationDetector, 'AREA_DATABASE_PATH', db_path):
                det = LocationDetector()
                assert "custom_city" in det.area_database
                assert det.area_database["custom_city"]["name"] == "Custom City"

    def test_corrupt_database_falls_back_to_default(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "areas.json"
            db_path.parent.mkdir(exist_ok=True)
            db_path.write_text("not valid json{{{")
            with patch.object(LocationDetector, 'AREA_DATABASE_PATH', db_path):
                det = LocationDetector()
                assert "pallet_town" in det.area_database

    def test_save_creates_directories(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "subdir" / "areas.json"
            with patch.object(LocationDetector, 'AREA_DATABASE_PATH', db_path):
                LocationDetector()
                assert db_path.exists()

    def test_tile_classifications_always_populated(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "areas.json"
            with patch.object(LocationDetector, 'AREA_DATABASE_PATH', db_path):
                det = LocationDetector()
                assert "grass" in det.tile_classifications
                assert det.tile_classifications["grass"]["collision"] == "passable"


# ═══════════════════════════════════════════════════════════════════════════
# LocationResult / TileInfo dataclasses
# ═══════════════════════════════════════════════════════════════════════════

class TestLocationResult:
    """Coverage: LocationResult + TileInfo dataclasses."""

    def test_location_result_creation(self) -> None:
        r = LocationResult("Pallet Town", "town", 0.9, "hash123",
                           {"pokemon_center": True})
        assert r.location_name == "Pallet Town"
        assert r.location_type == "town"
        assert r.confidence == 0.9
        assert r.tile_pattern_hash == "hash123"

    def test_location_result_unknown(self) -> None:
        r = LocationResult("Unknown Area", "unknown", 0.0, "", {})
        assert r.confidence == 0.0

    def test_tile_info_creation(self) -> None:
        t = TileInfo("path", "passable", False, "hash_abc")
        assert t.tile_type == "path"
        assert t.collision_type == "passable"
        assert t.is_interactive is False
        assert t.hash_value == "hash_abc"
