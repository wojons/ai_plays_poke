"""
Location Detector - Game World Location Recognition

Identifies game locations including routes, towns, caves, and buildings
using tile pattern matching and feature detection.
"""
import json
import time
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

@dataclass
class LocationResult:
    location_name: str
    location_type: str
    confidence: float
    tile_pattern_hash: str
    features: Dict[str, bool]

@dataclass
class TileInfo:
    tile_type: str
    collision_type: str
    is_interactive: bool
    hash_value: str

class LocationDetector:
    AREA_DATABASE_PATH = Path(__file__).parent / "data" / "areas.json"
    
    def __init__(self):
        self.area_database: Dict = {}
        self.tile_templates: Dict[str, np.ndarray] = {}
        self._load_area_database()
        
        self.tile_classifications = {
            "grass": {"collision": "passable", "interactive": False},
            "tall_grass": {"collision": "passable", "interactive": False},
            "water": {"collision": "water", "interactive": False},
            "wall": {"collision": "blocking", "interactive": False},
            "tree": {"collision": "blocking", "interactive": False},
            "door": {"collision": "interactive", "interactive": True},
            "sign": {"collision": "interactive", "interactive": True},
            "path": {"collision": "passable", "interactive": False},
            "rock": {"collision": "breakable", "interactive": False},
            "ledge": {"collision": "ledge", "interactive": False},
        }
    
    def _load_area_database(self):
        if self.AREA_DATABASE_PATH.exists():
            try:
                with open(self.AREA_DATABASE_PATH, 'r') as f:
                    self.area_database = json.load(f)
            except Exception:
                self._create_default_area_database()
        else:
            self._create_default_area_database()
    
    def _create_default_area_database(self):
        self.area_database = {
            "pallet_town": {
                "name": "Pallet Town",
                "type": "town",
                "tile_patterns": ["grass", "path", "water"],
                "features": {"pokemon_center": True, "pokemart": True, "gym": False},
                "connections": ["route_1"],
                "hash_pattern": ""
            },
            "route_1": {
                "name": "Route 1",
                "type": "route",
                "tile_patterns": ["grass", "path", "tall_grass"],
                "features": {"pokemon_center": False, "pokemart": False, "gym": False},
                "connections": ["pallet_town", "viridian_city"],
                "hash_pattern": ""
            },
            "viridian_city": {
                "name": "Viridian City",
                "type": "city",
                "tile_patterns": ["grass", "path", "water"],
                "features": {"pokemon_center": True, "pokemart": True, "gym": True},
                "connections": ["route_1", "route_2"],
                "hash_pattern": ""
            },
            "viridian_forest": {
                "name": "Viridian Forest",
                "type": "cave",
                "tile_patterns": ["grass", "tree", "path"],
                "features": {"pokemon_center": False, "pokemart": False, "gym": False},
                "connections": ["route_2", "pewter_city"],
                "hash_pattern": ""
            },
            "pewter_city": {
                "name": "Pewter City",
                "type": "city",
                "tile_patterns": ["grass", "path", "rock"],
                "features": {"pokemon_center": True, "pokemart": True, "gym": True},
                "connections": ["route_2", "route_3"],
                "hash_pattern": ""
            },
            "route_22": {
                "name": "Route 22",
                "type": "route",
                "tile_patterns": ["grass", "path", "tall_grass"],
                "features": {"pokemon_center": False, "pokemart": False, "gym": False},
                "connections": ["pallet_town", "route_23"],
                "hash_pattern": ""
            },
            "route_23": {
                "name": "Route 23",
                "type": "route",
                "tile_patterns": ["grass", "path", "water"],
                "features": {"pokemon_center": False, "pokemart": False, "gym": False},
                "connections": ["route_22", "victory_road"],
                "hash_pattern": ""
            },
            "victory_road": {
                "name": "Victory Road",
                "type": "cave",
                "tile_patterns": ["wall", "path", "rock"],
                "features": {"pokemon_center": False, "pokemart": False, "gym": False},
                "connections": ["route_23"],
                "hash_pattern": ""
            },
        }
        self._save_area_database()
    
    def _save_area_database(self):
        self.AREA_DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(self.AREA_DATABASE_PATH, 'w') as f:
            json.dump(self.area_database, f, indent=2)
    
    def detect_location(self, screenshot: np.ndarray) -> LocationResult:
        start_time = time.perf_counter()
        
        tiles = self._extract_tiles(screenshot)
        
        tile_patterns = self._identify_tile_patterns(tiles)
        
        pattern_hash = self._compute_pattern_hash(tile_patterns)
        
        features = self._detect_features(screenshot)
        
        location_name, location_type, confidence = self._match_area(tile_patterns, features, pattern_hash)
        
        processing_time = (time.perf_counter() - start_time) * 1000
        
        return LocationResult(
            location_name=location_name,
            location_type=location_type,
            confidence=confidence,
            tile_pattern_hash=pattern_hash,
            features=features
        )
    
    def _extract_tiles(self, screenshot: np.ndarray) -> List[np.ndarray]:
        tiles = []
        
        if len(screenshot.shape) == 3:
            gray = np.mean(screenshot, axis=2).astype(np.uint8)
        else:
            gray = screenshot
        
        h, w = gray.shape
        
        tile_height = 16
        tile_width = 16
        
        for y in range(0, h - tile_height, tile_height):
            for x in range(0, w - tile_width, tile_width):
                tile = gray[y:y+tile_height, x:x+tile_width]
                tiles.append(tile)
        
        return tiles
    
    def _identify_tile_patterns(self, tiles: List[np.ndarray]) -> Dict[str, int]:
        pattern_counts = {}
        
        for tile in tiles:
            tile_hash = self._compute_tile_hash(tile)
            
            tile_type = self._classify_tile(tile)
            
            pattern_counts[tile_type] = pattern_counts.get(tile_type, 0) + 1
        
        return pattern_counts
    
    def _compute_tile_hash(self, tile: np.ndarray) -> str:
        tile_flat = tile.flatten()
        tile_mean = np.mean(tile_flat)
        tile_std = np.std(tile_flat)
        
        features = f"{tile_mean:.2f}_{tile_std:.2f}_{tile.shape[0]}_{tile.shape[1]}"
        
        return features
    
    def _classify_tile(self, tile: np.ndarray) -> str:
        if tile.size == 0:
            return "unknown"
        
        tile_mean = np.mean(tile)
        tile_std = np.std(tile)
        
        h, w = tile.shape
        
        center_region = tile[h//4:3*h//4, w//4:3*w//4]
        center_mean = np.mean(center_region)
        
        edge_top = tile[0, :]
        edge_bottom = tile[-1, :]
        edge_left = tile[:, 0]
        edge_right = tile[:, -1]
        
        edge_mean = (np.mean(edge_top) + np.mean(edge_bottom) + np.mean(edge_left) + np.mean(edge_right)) / 4
        
        if center_mean > 150 and tile_std < 30:
            return "wall"
        elif center_mean > 100 and tile_std < 50:
            if edge_mean < 80:
                return "door"
            return "path"
        elif tile_mean > 80 and tile_mean < 120 and tile_std > 40:
            return "grass"
        elif tile_mean > 60 and tile_mean < 100 and tile_std > 50:
            return "tall_grass"
        elif tile_mean < 80:
            return "water"
        elif tile_mean > 120:
            if tile_std > 60:
                return "tree"
            return "rock"
        elif edge_mean < center_mean - 20:
            return "sign"
        
        return "path"
    
    def _compute_pattern_hash(self, pattern_counts: Dict[str, int]) -> str:
        sorted_patterns = sorted(pattern_counts.items(), key=lambda x: x[0])
        pattern_str = "_".join([f"{name}:{count}" for name, count in sorted_patterns])
        return pattern_str
    
    def _detect_features(self, screenshot: np.ndarray) -> Dict[str, bool]:
        features = {
            "pokemon_center": False,
            "pokemart": False,
            "gym": False,
            "water_body": False,
            "cave_entrance": False,
            "signpost": False,
        }
        
        h, w = screenshot.shape[:2]
        
        top_left = screenshot[0:int(h*0.2), 0:int(w*0.3)]
        if top_left.size > 0:
            gray = np.mean(top_left, axis=2).astype(np.uint8)
            white_pixels = np.sum(gray > 200)
            if white_pixels > 500:
                features["pokemon_center"] = True
        
        center_area = screenshot[int(h*0.3):int(h*0.7), int(w*0.3):int(w*0.7)]
        if center_area.size > 0:
            gray = np.mean(center_area, axis=2).astype(np.uint8)
            green_pixels = np.sum((gray > 50) & (gray < 120))
            if green_pixels > center_area.size * 0.3:
                features["water_body"] = True
        
        return features
    
    def _match_area(
        self,
        tile_patterns: Dict[str, int],
        features: Dict[str, bool],
        pattern_hash: str
    ) -> Tuple[str, str, float]:
        best_match = None
        best_score = 0
        
        for area_key, area_info in self.area_database.items():
            score = 0.0
            
            for expected_pattern in area_info.get("tile_patterns", []):
                if expected_pattern in tile_patterns:
                    score += 1.0
            
            if features.get("pokemon_center") and area_info.get("features", {}).get("pokemon_center"):
                score += 2.0
            if features.get("pokemart") and area_info.get("features", {}).get("pokemart"):
                score += 2.0
            if features.get("gym") and area_info.get("features", {}).get("gym"):
                score += 2.0
            
            if score > best_score:
                best_score = score
                best_match = (area_info["name"], area_info["type"], score)
        
        if best_match and best_score >= 1:
            confidence = min(1.0, best_score / 5.0)
            return best_match[0], best_match[1], confidence
        
        return "Unknown Area", "unknown", 0.0
    
    def get_tile_collision(self, tile_type: str) -> str:
        return self.tile_classifications.get(tile_type, {}).get("collision", "unknown")
    
    def is_tile_interactive(self, tile_type: str) -> bool:
        return self.tile_classifications.get(tile_type, {}).get("interactive", False)
    
    def get_navigation_graph(self, screenshot: np.ndarray) -> Dict[Tuple[int, int], Dict]:
        tiles = self._extract_tiles(screenshot)
        
        grid_width = int(screenshot.shape[1] / 16)
        grid_height = int(len(tiles) / grid_width)
        
        graph = {}
        
        for y in range(grid_height):
            for x in range(grid_width):
                tile_index = y * grid_width + x
                if tile_index < len(tiles):
                    tile = tiles[tile_index]
                    tile_type = self._classify_tile(tile)
                    collision = self.get_tile_collision(tile_type)
                    
                    graph[(x, y)] = {
                        "tile_type": tile_type,
                        "collision": collision,
                        "interactive": self.is_tile_interactive(tile_type),
                        "passable": collision in ["passable", "water", "ledge"]
                    }
        
        return graph
    
    def find_path_to_target(
        self,
        current_pos: Tuple[int, int],
        target_pos: Tuple[int, int],
        navigation_graph: Dict[Tuple[int, int], Dict]
    ) -> List[Tuple[int, int]]:
        path = [current_pos]
        
        cx, cy = current_pos
        tx, ty = target_pos
        
        while (cx, cy) != target_pos:
            if abs(tx - cx) > abs(ty - cy):
                if tx > cx:
                    cx += 1
                else:
                    cx -= 1
            else:
                if ty > cy:
                    cy += 1
                else:
                    cy -= 1
            
            if (cx, cy) in navigation_graph:
                node = navigation_graph[(cx, cy)]
                if node["passable"] or node["collision"] == "interactive":
                    path.append((cx, cy))
        
        return path
    
    def is_in_battle(self, screenshot: np.ndarray) -> bool:
        h, w = screenshot.shape[:2]
        
        enemy_area = screenshot[int(h*0.1):int(h*0.35), int(w*0.4):w]
        if enemy_area.size == 0:
            return False
        
        gray = np.mean(enemy_area, axis=2).astype(np.uint8)
        
        if np.mean(gray) > 100 and np.std(gray) > 30:
            return True
        
        hp_bar = screenshot[int(h*0.02):int(h*0.12), int(w*0.5):w]
        if hp_bar.size > 0:
            hp_gray = np.mean(hp_bar, axis=2).astype(np.uint8)
            if np.sum(hp_gray > 150) > hp_bar.size * 0.1:
                return True
        
        return False
    
    def is_in_menu(self, screenshot: np.ndarray) -> bool:
        h, w = screenshot.shape[:0]
        
        bottom_menu = screenshot[int(h*0.7):h, :]
        if bottom_menu.size == 0:
            return False
        
        gray = np.mean(bottom_menu, axis=2).astype(np.uint8)
        
        if np.mean(gray) > 100:
            return True
        
        return False
    
    def is_in_dialog(self, screenshot: np.ndarray) -> bool:
        h, w = screenshot.shape[:2]
        
        dialog_area = screenshot[int(h*0.6):h, :]
        if dialog_area.size == 0:
            return False
        
        gray = np.mean(dialog_area, axis=2).astype(np.uint8)
        
        if np.mean(gray) < 80:
            return True
        
        return False
    
    def classify_screen_type(self, screenshot: np.ndarray) -> str:
        if self.is_in_battle(screenshot):
            return "battle"
        elif self.is_in_menu(screenshot):
            return "menu"
        elif self.is_in_dialog(screenshot):
            return "dialog"
        else:
            return "overworld"
