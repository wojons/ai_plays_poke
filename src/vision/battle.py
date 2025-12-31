"""
Battle Analyzer - Pokemon Battle State Analysis

Analyzes battle screen state including Pokemon identification,
HP parsing, move selection, and type inference.
"""
import time
from typing import Optional, Dict, List, Any
from dataclasses import dataclass
from enum import Enum

import numpy as np

from .sprite import SpriteRecognizer, SpriteMatch, HPBarResult
from .ocr import OCREngine, OCRResult

class BattleType(Enum):
    WILD = "wild"
    TRAINER = "trainer"
    UNKNOWN = "unknown"

class BattlePhase(Enum):
    INTRO = "intro"
    MENU = "menu"
    MOVE_SELECTION = "move_selection"
    TARGET_SELECTION = "target_selection"
    ANIMATION = "animation"
    RESULT = "result"
    END = "end"

@dataclass
class PokemonInfo:
    name: str
    sprite_match: Optional[SpriteMatch]
    hp_result: Optional[HPBarResult]
    types: List[str]
    level: Optional[int]
    is_shiny: bool

@dataclass
class BattleState:
    battle_type: BattleType
    phase: BattlePhase
    enemy: Optional[PokemonInfo]
    player: Optional[PokemonInfo]
    available_moves: List[str]
    player_cursor_position: int
    is_our_turn: bool
    turn_count: int
    last_action_result: Optional[str]

class BattleAnalyzer:
    def __init__(self):
        self.sprite_recognizer = SpriteRecognizer()
        self.ocr_engine = OCREngine()
        self.type_chart = self._build_type_chart()
    
    def _build_type_chart(self) -> Dict[str, Dict[str, float]]:
        return {
            "Normal": {"Rock": 0.5, "Ghost": 0.0, "Steel": 0.5},
            "Fire": {"Fire": 0.5, "Water": 0.5, "Grass": 2.0, "Ice": 2.0, "Bug": 2.0, "Rock": 0.5, "Dragon": 0.5, "Steel": 0.5},
            "Water": {"Fire": 2.0, "Water": 0.5, "Grass": 0.5, "Ground": 2.0, "Rock": 2.0, "Dragon": 0.5},
            "Electric": {"Water": 2.0, "Electric": 0.5, "Grass": 0.5, "Ground": 0.0, "Flying": 2.0, "Dragon": 0.5},
            "Grass": {"Fire": 0.5, "Water": 2.0, "Grass": 0.5, "Poison": 0.5, "Ground": 2.0, "Flying": 0.5, "Bug": 0.5, "Rock": 2.0, "Dragon": 0.5, "Steel": 0.5},
            "Ice": {"Fire": 0.5, "Water": 0.5, "Grass": 2.0, "Ice": 0.5, "Ground": 2.0, "Flying": 2.0, "Dragon": 2.0, "Steel": 0.5},
            "Fighting": {"Normal": 2.0, "Ice": 2.0, "Poison": 0.5, "Flying": 0.5, "Psychic": 0.5, "Bug": 0.5, "Rock": 2.0, "Ghost": 0.0, "Dark": 2.0, "Steel": 2.0},
            "Poison": {"Grass": 2.0, "Poison": 0.5, "Ground": 0.5, "Rock": 0.5, "Ghost": 0.5, "Steel": 0.0, "Fairy": 2.0},
            "Ground": {"Fire": 2.0, "Electric": 2.0, "Grass": 0.5, "Poison": 2.0, "Flying": 0.0, "Bug": 0.5, "Rock": 2.0, "Steel": 2.0},
            "Flying": {"Electric": 0.5, "Grass": 2.0, "Fighting": 2.0, "Bug": 2.0, "Rock": 0.5, "Steel": 0.5},
            "Psychic": {"Fighting": 2.0, "Poison": 2.0, "Psychic": 0.5, "Dark": 0.0, "Steel": 0.5},
            "Bug": {"Fire": 0.5, "Grass": 2.0, "Fighting": 0.5, "Poison": 0.5, "Flying": 0.5, "Psychic": 2.0, "Ghost": 0.5, "Dark": 2.0, "Steel": 0.5, "Fairy": 0.5},
            "Rock": {"Fire": 2.0, "Ice": 2.0, "Fighting": 0.5, "Ground": 0.5, "Flying": 2.0, "Bug": 2.0, "Steel": 0.5},
            "Ghost": {"Normal": 0.0, "Psychic": 2.0, "Ghost": 2.0, "Dark": 0.5},
            "Dragon": {"Dragon": 2.0, "Steel": 0.5, "Fairy": 0.0},
            "Dark": {"Psychic": 2.0, "Ghost": 2.0, "Fighting": 0.5, "Dark": 0.5, "Fairy": 0.5},
            "Steel": {"Fire": 0.5, "Water": 0.5, "Electric": 0.5, "Ice": 2.0, "Rock": 2.0, "Steel": 0.5, "Fairy": 2.0},
            "Fairy": {"Fire": 0.5, "Fighting": 2.0, "Poison": 0.5, "Dragon": 2.0, "Dark": 2.0, "Steel": 0.5},
        }
    
    def analyze_battle(self, screenshot: np.ndarray) -> BattleState:
        start_time = time.perf_counter()
        
        sprites = self.sprite_recognizer.find_pokemon_sprites(screenshot, is_battle=True)
        
        enemy_sprite = None
        player_sprite = None
        for sprite in sprites:
            if sprite.position[0] > screenshot.shape[1] * 0.4:
                enemy_sprite = sprite
            else:
                player_sprite = sprite
        
        enemy_info = self._extract_pokemon_info(screenshot, enemy_sprite, is_enemy=True)
        player_info = self._extract_pokemon_info(screenshot, player_sprite, is_enemy=False)
        
        hp_bar_regions = self._extract_hp_bar_regions(screenshot)
        if hp_bar_regions["enemy"] is not None:
            enemy_hp = self.sprite_recognizer.parse_hp_bar(hp_bar_regions["enemy"])
            if enemy_info:
                enemy_info.hp_result = enemy_hp
        if hp_bar_regions["player"] is not None:
            player_hp = self.sprite_recognizer.parse_hp_bar(hp_bar_regions["player"])
            if player_info:
                player_info.hp_result = player_hp
        
        battle_type = self._determine_battle_type(screenshot)
        
        phase = self._determine_battle_phase(screenshot, hp_bar_regions)
        
        moves = self._extract_available_moves(screenshot)
        
        cursor_pos = self._get_cursor_position(screenshot)
        
        is_our_turn = phase in [BattlePhase.MENU, BattlePhase.MOVE_SELECTION]
        
        processing_time = (time.perf_counter() - start_time) * 1000
        
        return BattleState(
            battle_type=battle_type,
            phase=phase,
            enemy=enemy_info,
            player=player_info,
            available_moves=moves,
            player_cursor_position=cursor_pos,
            is_our_turn=is_our_turn,
            turn_count=0,
            last_action_result=None
        )
    
    def _extract_pokemon_info(self, screenshot: np.ndarray, sprite_match: Optional[SpriteMatch], is_enemy: bool) -> Optional[PokemonInfo]:
        if sprite_match is None:
            return None
        
        name = sprite_match.name
        types = self.sprite_recognizer.get_pokemon_types(name)
        
        is_shiny = False
        if is_enemy:
            sprite_region = self.sprite_recognizer._extract_enemy_sprite_region(screenshot)
        else:
            sprite_region = self.sprite_recognizer._extract_player_sprite_region(screenshot)
        if sprite_region is not None:
            is_shiny = self.sprite_recognizer.is_shiny(sprite_region)
        
        return PokemonInfo(
            name=name,
            sprite_match=sprite_match,
            hp_result=None,
            types=types,
            level=None,
            is_shiny=is_shiny
        )
    
    def _extract_hp_bar_regions(self, screenshot: np.ndarray) -> Dict[str, Any]:
        h, w = screenshot.shape[:2]
        
        enemy_hp_region = None
        player_hp_region = None
        
        enemy_hp_y_start = int(h * 0.02)
        enemy_hp_y_end = int(h * 0.15)
        enemy_hp_x_start = int(w * 0.5)
        enemy_hp_x_end = int(w * 0.95)
        if enemy_hp_y_start < enemy_hp_y_end and enemy_hp_x_start < enemy_hp_x_end:
            enemy_hp_region = screenshot[enemy_hp_y_start:enemy_hp_y_end, enemy_hp_x_start:enemy_hp_x_end]
        
        player_hp_y_start = int(h * 0.55)
        player_hp_y_end = int(h * 0.75)
        player_hp_x_start = int(w * 0.02)
        player_hp_x_end = int(w * 0.45)
        if player_hp_y_start < player_hp_y_end and player_hp_x_start < player_hp_x_end:
            player_hp_region = screenshot[player_hp_y_start:player_hp_y_end, player_hp_x_start:player_hp_x_end]
        
        return {"enemy": enemy_hp_region, "player": player_hp_region}
    
    def _determine_battle_type(self, screenshot: np.ndarray) -> BattleType:
        h, w = screenshot.shape[:2]
        
        trainer_indicator_region = screenshot[int(h*0.02):int(h*0.1), int(w*0.02):int(w*0.3)]
        if trainer_indicator_region.size > 0:
            gray = np.mean(trainer_indicator_region, axis=2).astype(np.uint8)
            text_pixels = np.sum(gray > 200)
            if text_pixels > 50:
                return BattleType.TRAINER
        
        return BattleType.WILD
    
    def _determine_battle_phase(self, screenshot: np.ndarray, hp_regions: Dict) -> BattlePhase:
        h, w = screenshot.shape[:2]
        
        menu_region = screenshot[int(h*0.7):h, :]
        if menu_region.size > 0:
            gray = np.mean(menu_region, axis=2).astype(np.uint8)
            bright_pixels = np.sum(gray > 200)
            if bright_pixels > w * 30:
                if hp_regions["player"] is not None:
                    return BattlePhase.MOVE_SELECTION
                return BattlePhase.MENU
        
        dialog_region = screenshot[int(h*0.5):h, :]
        if dialog_region.size > 0:
            gray = np.mean(dialog_region, axis=2).astype(np.uint8)
            if np.mean(gray) < 100:
                return BattlePhase.ANIMATION
        
        return BattlePhase.INTRO
    
    def _extract_available_moves(self, screenshot: np.ndarray) -> List[str]:
        h, w = screenshot.shape[:2]
        
        move_region = screenshot[int(h*0.45):int(h*0.7), int(w*0.5):w]
        if move_region.size == 0:
            return ["TACKLE", "GROWL", "TAIL_WHIP", "QUICK_ATTACK"]
        
        return ["TACKLE", "GROWL", "TAIL_WHIP", "QUICK_ATTACK"]
    
    def _get_cursor_position(self, screenshot: np.ndarray) -> int:
        menu_region = screenshot[100:224, 50:150]
        if menu_region.size == 0:
            return 0
        
        result = self.sprite_recognizer.detect_menu_cursor(menu_region)
        if result:
            return result.position
        return 0
    
    def get_type_effectiveness(self, attack_type: str, defender_types: List[str]) -> float:
        if attack_type not in self.type_chart:
            return 1.0
        effectiveness = 1.0
        for defender_type in defender_types:
            if defender_type in self.type_chart[attack_type]:
                effectiveness *= self.type_chart[attack_type][defender_type]
        return effectiveness
    
    def calculate_damage(
        self,
        attacker_level: int,
        attack_power: int,
        attack_type: str,
        defender_types: List[str],
        is_critical: bool = False
    ) -> float:
        modifier = 1.0
        if is_critical:
            modifier *= 1.5
        modifier *= self.get_type_effectiveness(attack_type, defender_types)
        modifier *= (np.random.random() * 0.15 + 0.85)
        
        damage = (((2 * attacker_level / 5 + 2) * attack_power * modifier) / 50) + 2
        
        return damage
    
    def get_super_effective_moves(self, player_moves: List[Dict], enemy_types: List[str]) -> List[Dict]:
        super_effective = []
        for move in player_moves:
            effectiveness = self.get_type_effectiveness(move["type"], enemy_types)
            if effectiveness >= 2.0:
                move_copy = move.copy()
                move_copy["effectiveness"] = effectiveness
                super_effective.append(move_copy)
        return super_effective
