"""
Sprite Recognizer - Pokemon and UI Element Recognition
"""
import json
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass
from pathlib import Path
import numpy as np
from PIL import Image

@dataclass
class SpriteMatch:
    name: str
    confidence: float
    sprite_type: str
    position: Tuple[int, int]
    size: Tuple[int, int]

@dataclass
class HPBarResult:
    current: int
    maximum: int
    percentage: float
    is_low: bool
    is_critical: bool

@dataclass
class MenuCursorResult:
    position: int
    option_count: int
    options: List[str]

class SpriteRecognizer:
    SPRITE_DATABASE_PATH = Path(__file__).parent / "data" / "sprites.json"
    
    def __init__(self):
        self.sprite_templates: Dict[str, np.ndarray] = {}
        self.sprite_metadata: Dict[str, Dict] = {}
        self._load_sprite_database()
        self.hp_bar_colors = {
            "green": ((34, 139, 34), (50, 205, 50)),
            "yellow": ((255, 215, 0), (255, 255, 0)),
            "red": ((220, 20, 60), (255, 69, 0)),
        }
    
    def _load_sprite_database(self):
        if self.SPRITE_DATABASE_PATH.exists():
            try:
                with open(self.SPRITE_DATABASE_PATH, 'r') as f:
                    data = json.load(f)
                    for sprite_info in data.get("sprites", []):
                        name = sprite_info["name"]
                        template = np.array(sprite_info["template"], dtype=np.uint8)
                        self.sprite_templates[name] = template
                        self.sprite_metadata[name] = {
                            "type": sprite_info.get("type", "unknown"),
                            "types": sprite_info.get("types", []),
                        }
                    self.common_pokemon = data.get("common_pokemon", [])
                    self.pokemon_types = data.get("pokemon_types", {})
            except Exception:
                self._create_default_sprite_database()
        else:
            self._create_default_sprite_database()
    
    def _create_default_sprite_database(self):
        self.sprite_templates = {}
        self.sprite_metadata = {}
        common_gen1 = [
            "Pikachu", "Charizard", "Bulbasaur", "Squirtle", "Charmander",
            "Gengar", "Dragonite", "Mewtwo", "Mew", "Eevee", "Vaporeon",
            "Jolteon", "Flareon", "Snorlax", "Lapras", "Arcanine",
            "Nidoking", "Nidoqueen", "Clefable", "Vileplume", "Blastoise",
            "Venusaur", "Alakazam", "Golem", "Machamp", "Gyarados",
        ]
        for name in common_gen1:
            self.sprite_templates[name] = np.zeros((32, 32), dtype=np.uint8)
            self.sprite_metadata[name] = {"type": "pokemon", "types": ["normal"]}
        self.common_pokemon = common_gen1
        self.pokemon_types = {
            "Pikachu": ["Electric"], "Charizard": ["Fire", "Flying"],
            "Bulbasaur": ["Grass", "Poison"], "Squirtle": ["Water"],
            "Charmander": ["Fire"], "Gengar": ["Ghost", "Poison"],
            "Dragonite": ["Dragon", "Flying"], "Mewtwo": ["Psychic"],
            "Mew": ["Psychic"], "Eevee": ["Normal"], "Vaporeon": ["Water"],
            "Jolteon": ["Electric"], "Flareon": ["Fire"], "Snorlax": ["Normal"],
            "Lapras": ["Water", "Ice"], "Arcanine": ["Fire"],
            "Nidoking": ["Poison", "Ground"], "Nidoqueen": ["Poison", "Ground"],
            "Clefable": ["Fairy"], "Vileplume": ["Grass", "Poison"],
            "Blastoise": ["Water"], "Venusaur": ["Grass", "Poison"],
            "Alakazam": ["Psychic"], "Golem": ["Rock", "Ground"],
            "Machamp": ["Fighting"], "Gyarados": ["Water", "Flying"],
        }
        self._save_sprite_database()
    
    def _save_sprite_database(self):
        self.SPRITE_DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
        sprite_list = []
        for name, template in self.sprite_templates.items():
            sprite_list.append({
                "name": name, "template": template.tolist(),
                "type": self.sprite_metadata.get(name, {}).get("type", "unknown"),
                "types": self.sprite_metadata.get(name, {}).get("types", []),
            })
        data = {"sprites": sprite_list, "common_pokemon": self.common_pokemon, "pokemon_types": self.pokemon_types}
        with open(self.SPRITE_DATABASE_PATH, 'w') as f:
            json.dump(data, f, indent=2)
    
    def recognize_pokemon(self, sprite_region: np.ndarray, expected_types: Optional[List[str]] = None) -> Optional[SpriteMatch]:
        if sprite_region.size == 0:
            return None
        best_match = None
        best_score = 0
        candidates = self.common_pokemon
        if expected_types:
            candidates = [name for name in self.common_pokemon if any(t in self.pokemon_types.get(name, []) for t in expected_types)] or self.common_pokemon
        for name in candidates:
            if name not in self.sprite_templates:
                continue
            template = self.sprite_templates[name]
            score = self._template_match(sprite_region, template)
            if score > best_score:
                best_score = score
                best_match = SpriteMatch(name=name, confidence=score, sprite_type="pokemon", position=(0,0), size=sprite_region.shape[:2])
        if best_match and best_match.confidence < 0.4:
            return None
        return best_match
    
    def _template_match(self, region: np.ndarray, template: np.ndarray) -> float:
        region_gray = self._ensure_grayscale(region)
        template_gray = self._ensure_grayscale(template)
        region_resized = self._resize_to_match(region_gray, template_gray.shape)
        if region_resized.shape != template_gray.shape:
            return 0.0
        region_norm = region_gray.astype(float) / 255.0
        template_norm = template_gray.astype(float) / 255.0
        a_mean, b_mean = np.mean(region_norm), np.mean(template_norm)
        a_centered, b_centered = region_norm - a_mean, template_norm - b_mean
        numerator = np.sum(a_centered * b_centered)
        denominator = np.sqrt(np.sum(a_centered**2) * np.sum(b_centered**2))
        if denominator == 0:
            return 0.0
        return max(0.0, numerator / denominator)
    
    def _ensure_grayscale(self, image: np.ndarray) -> np.ndarray:
        if len(image.shape) == 3:
            return np.mean(image, axis=2).astype(np.uint8)
        return image.copy()
    
    def _resize_to_match(self, region: np.ndarray, target_size: Tuple[int, int]) -> np.ndarray:
        th, tw = target_size
        pil_img = Image.fromarray(region)
        resized = pil_img.resize((tw, th), Image.Resampling.LANCZOS)
        return np.array(resized)
    
    def parse_hp_bar(self, hp_bar_image: np.ndarray) -> Optional[HPBarResult]:
        if hp_bar_image.size == 0:
            return None
        gray = np.mean(hp_bar_image, axis=2).astype(np.uint8) if len(hp_bar_image.shape) == 3 else hp_bar_image
        h, w = gray.shape
        bar_width, bar_start = int(w * 0.8), int(w * 0.1)
        bar_region = gray[2:h-2, bar_start:bar_start + bar_width]
        if bar_region.size == 0:
            return None
        center_row = bar_region.shape[0] // 2
        bar_pixels = bar_region[center_row, :]
        filled = bar_pixels > 100
        if not any(filled):
            return None
        filled_ratio = np.mean(filled)
        is_low, is_critical = filled_ratio < 0.3, filled_ratio < 0.1
        percentage = max(0.0, min(100.0, filled_ratio * 100))
        return HPBarResult(current=int(percentage), maximum=100, percentage=percentage, is_low=is_low, is_critical=is_critical)
    
    def detect_menu_cursor(self, menu_image: np.ndarray) -> Optional[MenuCursorResult]:
        if menu_image.size == 0:
            return None
        gray = self._ensure_grayscale(menu_image)
        edges = [(x, y) for y in range(gray.shape[0]) for x in range(gray.shape[1]) if gray[y, x] > 200]
        if not edges:
            return MenuCursorResult(position=0, option_count=4, options=["FIGHT", "POKEMON", "ITEM", "RUN"])
        cursor_y = int(np.median([y for x, y in edges]))
        option_height = menu_image.shape[0] // 4
        return MenuCursorResult(position=cursor_y // option_height, option_count=4, options=["FIGHT", "POKEMON", "ITEM", "RUN"])
    
    def find_pokemon_sprites(self, image: np.ndarray, is_battle: bool = True) -> List[SpriteMatch]:
        matches = []
        if is_battle:
            h, w = image.shape[:2]
            enemy_region = image[int(h*0.1):int(h*0.45), int(w*0.45):int(w*0.9)]
            player_region = image[int(h*0.55):int(h*0.85), int(w*0.05):int(w*0.5)]
            if enemy_region.size > 0:
                match = self.recognize_pokemon(enemy_region)
                if match:
                    match.position = (int(w * 0.6), int(h * 0.15))
                    matches.append(match)
            if player_region.size > 0:
                match = self.recognize_pokemon(player_region)
                if match:
                    match.position = (int(w * 0.15), int(h * 0.6))
                    matches.append(match)
        return matches
    
    def get_pokemon_types(self, name: str) -> List[str]:
        return self.pokemon_types.get(name, ["Unknown"])
    
    def is_shiny(self, sprite_region: np.ndarray) -> bool:
        if sprite_region.size == 0:
            return False
        h, w = sprite_region.shape[:2]
        sparkle_region = sprite_region[max(0, h-20):h, :]
        if sparkle_region.size == 0:
            return False
        sparkle_gray = self._ensure_grayscale(sparkle_region)
        white_ratio = np.sum(sparkle_gray > 250) / sparkle_gray.size
        return white_ratio > 0.05
