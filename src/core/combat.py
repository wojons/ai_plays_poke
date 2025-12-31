"""
Tactical Combat Heuristics for PTP-01X Pokemon AI

Implements combat decision-making logic with survival-first priority:
- DamageCalculator with Gen 1 exact formula
- TypeChart for Gen 1 type effectiveness (18 types, 306 interactions)
- MoveSelector with priority heuristics (STAB, type effectiveness, PP management)
- EnemyPredictor for enemy move set prediction and behavior analysis
- BattleStrategist for switch decisions, stat boosting, catch probability, risk assessment
- CombatSystem for HP clamping, validation, and damage calculation with edge case handling
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional, Tuple, Any, Union
import random
import logging

logger = logging.getLogger(__name__)


class PokemonType(Enum):
    """All 18 Pokemon types (Gen 1 + future types)"""
    NORMAL = "Normal"
    FIRE = "Fire"
    WATER = "Water"
    ELECTRIC = "Electric"
    GRASS = "Grass"
    ICE = "Ice"
    FIGHTING = "Fighting"
    POISON = "Poison"
    GROUND = "Ground"
    FLYING = "Flying"
    PSYCHIC = "Psychic"
    BUG = "Bug"
    ROCK = "Rock"
    GHOST = "Ghost"
    DRAGON = "Dragon"
    DARK = "Dark"
    STEEL = "Steel"
    FAIRY = "Fairy"


class StatusCondition(Enum):
    """Battle status conditions"""
    NONE = "none"
    POISONED = "poisoned"
    BADLY_POISONED = "badly_poisoned"
    BURNED = "burned"
    PARALYZED = "paralyzed"
    ASLEEP = "asleep"
    FROZEN = "frozen"
    CONFUSED = "confused"
    FLINCHED = "flinched"
    LEECH_SEEDED = "leech_seeded"


class MoveCategory(Enum):
    """Move damage category"""
    PHYSICAL = "physical"
    SPECIAL = "special"
    STATUS = "status"


class StatStage(Enum):
    """Stat modification stages (-6 to +6)"""
    NEGATIVE_6 = -6
    NEGATIVE_5 = -5
    NEGATIVE_4 = -4
    NEGATIVE_3 = -3
    NEGATIVE_2 = -2
    NEGATIVE_1 = -1
    ZERO = 0
    POSITIVE_1 = 1
    POSITIVE_2 = 2
    POSITIVE_3 = 3
    POSITIVE_4 = 4
    POSITIVE_5 = 5
    POSITIVE_6 = 6

    @property
    def multiplier(self) -> float:
        """Get stat stage multiplier (Gen 1 formula)"""
        stage_values = {
            -6: 0.25, -5: 0.2857, -4: 0.3333, -3: 0.4,
            -2: 0.5, -1: 0.6667, 0: 1.0,
            1: 1.5, 2: 2.0, 3: 2.5, 4: 3.0, 5: 3.5, 6: 4.0
        }
        return stage_values[self.value]


@dataclass
class Move:
    """Pokemon move representation"""
    name: str
    move_type: PokemonType
    power: int
    accuracy: int
    pp: int
    max_pp: int
    category: MoveCategory
    priority: int = 0
    is_high_crit: bool = False
    target_self: bool = False
    affects_all: bool = False


@dataclass
class Pokemon:
    """Pokemon state representation for combat calculations"""
    name: str
    level: int
    types: List[PokemonType]
    max_hp: int
    current_hp: int
    attack: int
    defense: int
    speed: int
    special: int
    moves: List[Move]
    status: StatusCondition = StatusCondition.NONE
    attack_stage: int = 0
    defense_stage: int = 0
    speed_stage: int = 0
    special_stage: int = 0
    accuracy_stage: int = 0
    evasion_stage: int = 0
    toxic_counter: int = 0


@dataclass
class DamageRange:
    """Damage range with prediction bounds"""
    min_damage: int
    max_damage: int
    expected_damage: int
    critical_min: int
    critical_max: int
    ko_probability: float


@dataclass
class MoveScore:
    """Scored move option"""
    move: Move
    score: float
    damage_range: Optional[DamageRange]
    ko_likely: bool
    effectiveness: float
    has_stab: bool
    notes: List[str] = field(default_factory=list)


@dataclass
class SwitchCandidate:
    """Evaluated switch option"""
    pokemon_name: str
    score: float
    defensive_score: float
    offensive_score: float
    type_advantage: float
    survival_turns: float
    reasoning: str


@dataclass
class CatchAttempt:
    """Catch probability calculation result"""
    catch_rate: float
    ball_factor: float
    status_factor: float
    hp_factor: float
    success_probability: float
    recommended_ball: str
    notes: List[str] = field(default_factory=list)


def clamp_hp(current: int, max_hp: int) -> int:
    """
    Ensure HP is between 0 and max_hp.

    Args:
        current: The current HP value
        max_hp: The maximum HP for the Pokemon

    Returns:
        HP value clamped to [0, max_hp] range
    """
    return max(0, min(current, max_hp))


def calculate_hp_after_damage(current_hp: int, damage: int, max_hp: int) -> int:
    """
    Calculate new HP after taking damage with clamping.

    Args:
        current_hp: Current HP before damage
        damage: Amount of damage to subtract
        max_hp: Maximum HP for the Pokemon

    Returns:
        New HP value after damage, clamped to [0, max_hp]
    """
    new_hp = current_hp - damage
    return clamp_hp(new_hp, max_hp)


def get_default_stat(stat_name: str, default_value: int = 50) -> int:
    """
    Get default value for missing Pokemon stats.

    Args:
        stat_name: Name of the stat
        default_value: Default value to use

    Returns:
        Default stat value
    """
    defaults = {
        "level": 50,
        "attack": 50,
        "defense": 50,
        "speed": 50,
        "special": 50,
        "max_hp": 100,
        "current_hp": 100,
    }
    return defaults.get(stat_name, default_value)


def validate_pokemon_data(data: Dict[str, Any], required_fields: List[str] = None) -> None:
    """
    Validate Pokemon data for completeness.

    Args:
        data: Pokemon data dictionary
        required_fields: List of required field names

    Raises:
        ValueError: If required fields are missing or invalid
        TypeError: If data is not a dictionary
    """
    if not isinstance(data, dict):
        raise TypeError("Pokemon data must be a dictionary")

    if required_fields is None:
        required_fields = ["name"]

    for field_name in required_fields:
        if field_name not in data:
            raise ValueError(f"Missing required field: {field_name}")


class TypeChart:
    """
    Gen 1 type effectiveness chart with 18 types and 306 interactions.
    
    Effectiveness values:
    - 0.0: Immune (no damage)
    - 0.25: Very not effective (Gen 2+ dual types)
    - 0.5: Not very effective
    - 1.0: Neutral
    - 2.0: Super effective
    - 4.0: Very super effective (dual type)
    """

    _chart: Dict[PokemonType, Dict[PokemonType, float]] = {}

    def __init__(self) -> None:
        self._initialize_chart()

    def _initialize_chart(self) -> None:
        """Initialize the complete type effectiveness chart"""
        self._chart = {
            PokemonType.NORMAL: {
                PokemonType.ROCK: 0.5, PokemonType.GHOST: 0.0, PokemonType.STEEL: 0.5
            },
            PokemonType.FIRE: {
                PokemonType.FIRE: 0.5, PokemonType.WATER: 0.5, PokemonType.GRASS: 2.0,
                PokemonType.ICE: 2.0, PokemonType.BUG: 2.0, PokemonType.ROCK: 0.5,
                PokemonType.DRAGON: 0.5, PokemonType.STEEL: 0.5
            },
            PokemonType.WATER: {
                PokemonType.FIRE: 2.0, PokemonType.WATER: 0.5, PokemonType.GRASS: 0.5,
                PokemonType.GROUND: 2.0, PokemonType.ROCK: 2.0, PokemonType.DRAGON: 0.5
            },
            PokemonType.ELECTRIC: {
                PokemonType.WATER: 2.0, PokemonType.ELECTRIC: 0.5, PokemonType.GRASS: 0.5,
                PokemonType.GROUND: 0.0, PokemonType.FLYING: 2.0, PokemonType.DRAGON: 0.5
            },
            PokemonType.GRASS: {
                PokemonType.FIRE: 0.5, PokemonType.WATER: 2.0, PokemonType.GRASS: 0.5,
                PokemonType.POISON: 0.5, PokemonType.GROUND: 2.0, PokemonType.FLYING: 0.5,
                PokemonType.BUG: 0.5, PokemonType.ROCK: 2.0, PokemonType.DRAGON: 0.5,
                PokemonType.STEEL: 0.5
            },
            PokemonType.ICE: {
                PokemonType.FIRE: 0.5, PokemonType.WATER: 0.5, PokemonType.GRASS: 2.0,
                PokemonType.ICE: 0.5, PokemonType.GROUND: 2.0, PokemonType.FLYING: 2.0,
                PokemonType.DRAGON: 2.0, PokemonType.STEEL: 0.5
            },
            PokemonType.FIGHTING: {
                PokemonType.NORMAL: 2.0, PokemonType.ICE: 2.0, PokemonType.POISON: 0.5,
                PokemonType.FLYING: 0.5, PokemonType.PSYCHIC: 0.5, PokemonType.BUG: 0.5,
                PokemonType.ROCK: 2.0, PokemonType.GHOST: 0.0, PokemonType.DARK: 2.0,
                PokemonType.STEEL: 2.0
            },
            PokemonType.POISON: {
                PokemonType.GRASS: 2.0, PokemonType.POISON: 0.5, PokemonType.GROUND: 0.5,
                PokemonType.ROCK: 0.5, PokemonType.GHOST: 0.5, PokemonType.STEEL: 0.0,
                PokemonType.FAIRY: 2.0
            },
            PokemonType.GROUND: {
                PokemonType.FIRE: 2.0, PokemonType.ELECTRIC: 2.0, PokemonType.GRASS: 0.5,
                PokemonType.POISON: 2.0, PokemonType.FLYING: 0.0, PokemonType.BUG: 0.5,
                PokemonType.ROCK: 2.0, PokemonType.STEEL: 2.0
            },
            PokemonType.FLYING: {
                PokemonType.ELECTRIC: 0.5, PokemonType.GRASS: 2.0, PokemonType.FIGHTING: 2.0,
                PokemonType.BUG: 2.0, PokemonType.ROCK: 0.5, PokemonType.STEEL: 0.5
            },
            PokemonType.PSYCHIC: {
                PokemonType.FIGHTING: 2.0, PokemonType.POISON: 2.0, PokemonType.PSYCHIC: 0.5,
                PokemonType.DARK: 0.0, PokemonType.STEEL: 0.5
            },
            PokemonType.BUG: {
                PokemonType.FIRE: 0.5, PokemonType.GRASS: 2.0, PokemonType.FIGHTING: 0.5,
                PokemonType.POISON: 0.5, PokemonType.FLYING: 0.5, PokemonType.PSYCHIC: 2.0,
                PokemonType.GHOST: 0.5, PokemonType.DARK: 2.0, PokemonType.STEEL: 0.5,
                PokemonType.FAIRY: 0.5
            },
            PokemonType.ROCK: {
                PokemonType.FIRE: 2.0, PokemonType.ICE: 2.0, PokemonType.FIGHTING: 0.5,
                PokemonType.GROUND: 0.5, PokemonType.FLYING: 2.0, PokemonType.BUG: 2.0,
                PokemonType.STEEL: 0.5
            },
            PokemonType.GHOST: {
                PokemonType.NORMAL: 0.0, PokemonType.PSYCHIC: 2.0, PokemonType.GHOST: 2.0,
                PokemonType.DARK: 0.5
            },
            PokemonType.DRAGON: {
                PokemonType.DRAGON: 2.0, PokemonType.STEEL: 0.5, PokemonType.FAIRY: 0.0
            },
            PokemonType.DARK: {
                PokemonType.PSYCHIC: 2.0, PokemonType.GHOST: 2.0, PokemonType.FIGHTING: 0.5,
                PokemonType.DARK: 0.5, PokemonType.FAIRY: 0.5
            },
            PokemonType.STEEL: {
                PokemonType.FIRE: 0.5, PokemonType.WATER: 0.5, PokemonType.ELECTRIC: 0.5,
                PokemonType.ICE: 2.0, PokemonType.ROCK: 2.0, PokemonType.STEEL: 0.5,
                PokemonType.FAIRY: 2.0
            },
            PokemonType.FAIRY: {
                PokemonType.FIRE: 0.5, PokemonType.FIGHTING: 2.0, PokemonType.POISON: 0.5,
                PokemonType.DRAGON: 2.0, PokemonType.DARK: 2.0, PokemonType.STEEL: 0.5
            },
        }

    def get_effectiveness(self, attack_type: PokemonType, 
                          defender_types: List[PokemonType]) -> float:
        """Calculate type effectiveness for attack vs defender"""
        if attack_type not in self._chart:
            return 1.0
        
        effectiveness = 1.0
        for defender_type in defender_types:
            if defender_type in self._chart[attack_type]:
                effectiveness *= self._chart[attack_type][defender_type]
        
        return effectiveness

    def is_immune(self, attack_type: PokemonType, defender_types: List[PokemonType]) -> bool:
        """Check if attack type is completely immune"""
        return self.get_effectiveness(attack_type, defender_types) == 0.0

    def is_super_effective(self, attack_type: PokemonType, 
                           defender_types: List[PokemonType]) -> bool:
        """Check if attack is super effective (>= 2.0)"""
        return self.get_effectiveness(attack_type, defender_types) >= 2.0

    def is_not_very_effective(self, attack_type: PokemonType,
                               defender_types: List[PokemonType]) -> bool:
        """Check if attack is not very effective (<= 0.5)"""
        return 0.0 < self.get_effectiveness(attack_type, defender_types) <= 0.5


class DamageCalculator:
    """
    Gen 1 damage calculation with exact formula.
    
    Damage = (((2 * Level / 5 + 2) * Power * A / D) / 50 + 2) * Modifier
    Modifier = STAB * TypeEffectiveness * Critical * Random
    
    Stat modifiers applied: Effective = Base * (1 + stage/2)
    """

    def __init__(self, type_chart: Optional[TypeChart] = None) -> None:
        self.type_chart = type_chart or TypeChart()

    def calculate_base_damage(
        self,
        level: int,
        power: int,
        attack: float,
        defense: float,
        stab: float = 1.0,
        type_effectiveness: float = 1.0,
        is_critical: bool = False,
        random_factor: float = 1.0
    ) -> int:
        """Calculate final damage with Gen 1 formula"""
        base_damage = (((2 * level / 5 + 2) * power * attack / defense) / 50) + 2
        
        modifier = stab * type_effectiveness * random_factor
        if is_critical:
            modifier *= 2.0
        
        final_damage = int(base_damage * modifier)
        
        return max(1, final_damage)

    def calculate_effective_stat(self, base_stat: int, stage: int) -> float:
        """Calculate effective stat with stage modifier"""
        multiplier = 1.0 + (stage / 2)
        return base_stat * multiplier

    def calculate_stab(self, move_type: PokemonType, pokemon_types: List[PokemonType]) -> float:
        """Calculate Same Type Attack Bonus (1.5x if move type matches)"""
        if move_type in pokemon_types:
            return 1.5
        return 1.0

    def calculate_damage_range(
        self,
        attacker: Pokemon,
        defender: Pokemon,
        move: Move,
        include_criticals: bool = True
    ) -> DamageRange:
        """Calculate min/max damage range for conservative planning"""
        if move.category == MoveCategory.STATUS:
            return DamageRange(
                min_damage=0, max_damage=0, expected_damage=0,
                critical_min=0, critical_max=0, ko_probability=0.0
            )

        attack = self.calculate_effective_stat(
            attacker.attack if move.category == MoveCategory.PHYSICAL else attacker.special,
            attacker.attack_stage if move.category == MoveCategory.PHYSICAL else attacker.special_stage
        )
        defense = self.calculate_effective_stat(
            defender.defense if move.category == MoveCategory.PHYSICAL else defender.special,
            defender.defense_stage if move.category == MoveCategory.PHYSICAL else defender.special_stage
        )

        stab = self.calculate_stab(move.move_type, attacker.types)
        type_effectiveness = self.type_chart.get_effectiveness(
            move.move_type, defender.types
        )

        min_damage = self.calculate_base_damage(
            attacker.level, move.power, attack, defense,
            stab, type_effectiveness, is_critical=False, random_factor=0.85
        )
        max_damage = self.calculate_base_damage(
            attacker.level, move.power, attack, defense,
            stab, type_effectiveness, is_critical=False, random_factor=1.0
        )

        expected_damage = (min_damage + max_damage) // 2

        if include_criticals and move.is_high_crit:
            crit_min = min_damage * 2
            crit_max = max_damage * 2
        else:
            crit_min = min_damage
            crit_max = max_damage

        if defender.current_hp > 0:
            min_ko_prob = min_damage / defender.current_hp
            max_ko_prob = max_damage / defender.current_hp
            ko_probability = (min_ko_prob + max_ko_prob) / 2
        else:
            ko_probability = 1.0

        return DamageRange(
            min_damage=min_damage,
            max_damage=max_damage,
            expected_damage=expected_damage,
            critical_min=crit_min,
            critical_max=crit_max,
            ko_probability=ko_probability
        )

    def can_ko(self, damage_range: DamageRange, defender_hp: int, 
               include_criticals: bool = False) -> Tuple[bool, bool, bool]:
        """
        Determine KO possibilities.
        
        Returns: (guaranteed_ko, likely_ko, possible_ko)
        """
        if include_criticals:
            possible = damage_range.critical_max >= defender_hp
            likely = damage_range.critical_min >= defender_hp
            guaranteed = damage_range.critical_min >= defender_hp
        else:
            possible = damage_range.max_damage >= defender_hp
            likely = damage_range.expected_damage >= defender_hp * 0.8
            guaranteed = damage_range.min_damage >= defender_hp
        
        return guaranteed, likely, possible

    def get_crit_chance(self, attacker: Pokemon, move: Move) -> float:
        """Calculate critical hit probability (Gen 1 mechanics)"""
        base_crit_rate = 0.0625  # 1/16 = 6.25%

        if move.is_high_crit:
            base_crit_rate = 0.25  # 25% for high crit moves

        speed_factor = attacker.speed // 2
        crit_stage = min(base_crit_rate + (speed_factor / 256), 1.0)

        return crit_stage


class MoveSelector:
    """
    Intelligent move selection with priority heuristics:
    - STAB bonus calculation
    - Type effectiveness weighting
    - Power vs accuracy trade-off
    - Status move utility
    - PP management
    """

    def __init__(self, type_chart: Optional[TypeChart] = None) -> None:
        self.type_chart = type_chart or TypeChart()

    def score_move(
        self,
        move: Move,
        attacker: Pokemon,
        defender: Pokemon,
        risk_averse: bool = True,
        setup_opportunity: bool = False,
        opponent_weakened: bool = False
    ) -> MoveScore:
        """Score a single move for selection"""
        notes: List[str] = []
        ko_likely = False

        if move.category == MoveCategory.STATUS:
            return self._score_status_move(move, defender, notes)

        damage_range = DamageCalculator(self.type_chart).calculate_damage_range(
            attacker, defender, move
        )

        effectiveness = self.type_chart.get_effectiveness(
            move.move_type, defender.types
        )
        has_stab = move.move_type in attacker.types

        guaranteed_ko, likely_ko, _ = DamageCalculator(
            self.type_chart
        ).can_ko(damage_range, defender.current_hp)

        base_score = move.power / 10.0

        effectiveness_multiplier = effectiveness
        if effectiveness >= 2.0:
            notes.append("Super effective!")
            effectiveness_multiplier = 2.0
        elif effectiveness == 0.0:
            notes.append("Immune - avoid!")
            return MoveScore(
                move=move, score=0.0, damage_range=damage_range,
                ko_likely=False, effectiveness=effectiveness,
                has_stab=has_stab, notes=notes
            )
        elif effectiveness <= 0.5:
            notes.append("Not very effective")
            effectiveness_multiplier = 0.5

        if has_stab:
            base_score *= 1.5
            notes.append("STAB bonus")

        if guaranteed_ko:
            base_score *= 3.0
            notes.append("GUARANTEED KO!")
            ko_likely = True
        elif likely_ko:
            base_score *= 1.5
            notes.append("Likely KO")
            ko_likely = True

        accuracy_factor = move.accuracy / 100.0
        if risk_averse and move.accuracy < 80:
            accuracy_factor *= 0.8
            notes.append(f"Low accuracy ({move.accuracy}%)")

        if move.priority > 0:
            if attacker.speed < defender.speed:
                base_score *= 1.5
                notes.append("Priority advantage")
            else:
                base_score *= 1.1
                notes.append("Priority move")

        if setup_opportunity and move.category != MoveCategory.STATUS:
            if self._is_setup_move(move):
                if damage_range.expected_damage < defender.current_hp * 0.3:
                    base_score *= 2.0
                    notes.append("Good setup opportunity")

        coverage_bonus = 1.0
        attacker_move_types = [m.move_type for m in attacker.moves if m != move]
        if move.move_type not in attacker_move_types:
            coverage_bonus = 1.1
            notes.append("New type coverage")

        final_score = (base_score * effectiveness_multiplier * 
                      accuracy_factor * coverage_bonus)

        return MoveScore(
            move=move,
            score=final_score,
            damage_range=damage_range,
            ko_likely=ko_likely,
            effectiveness=effectiveness,
            has_stab=has_stab,
            notes=notes
        )

    def _score_status_move(self, move: Move, defender: Pokemon, 
                          notes: List[str]) -> MoveScore:
        """Score a status move"""
        if defender.status != StatusCondition.NONE:
            notes.append("Target already statused")
            return MoveScore(
                move=move, score=0.0, damage_range=None,
                ko_likely=False, effectiveness=1.0, has_stab=False, notes=notes
            )

        score = 1.5
        if move.accuracy < 100:
            score *= move.accuracy / 100.0

        return MoveScore(
            move=move,
            score=score,
            damage_range=None,
            ko_likely=False,
            effectiveness=1.0,
            has_stab=False,
            notes=notes
        )

    def _is_setup_move(self, move: Move) -> bool:
        """Check if move is a setup move (raises stats)"""
        setup_moves = ["Swords Dance", "Agility", "Tail Whip", "Leer", 
                       "Growl", "Flash", "Sand Attack", "Kinesis"]
        return move.name in setup_moves

    def select_best_move(
        self,
        attacker: Pokemon,
        defender: Pokemon,
        risk_averse: bool = True,
        setup_opportunity: bool = False,
        opponent_weakened: bool = False,
        prefer_powerful: bool = False
    ) -> MoveScore:
        """Select the best move from available options"""
        available_moves = [m for m in attacker.moves if m.pp > 0]

        if not available_moves:
            fallback_move = attacker.moves[0] if attacker.moves else Move(
                name="Struggle", move_type=PokemonType.NORMAL, power=50,
                accuracy=100, pp=10, max_pp=10, category=MoveCategory.PHYSICAL
            )
            return MoveScore(
                move=fallback_move,
                score=0.0, damage_range=None,
                ko_likely=False, effectiveness=1.0, has_stab=False
            )

        scored_moves = [
            self.score_move(m, attacker, defender, risk_averse, 
                          setup_opportunity, opponent_weakened)
            for m in available_moves
        ]

        scored_moves.sort(key=lambda x: x.score, reverse=True)

        return scored_moves[0]

    def get_move_order(self, attacker: Pokemon, defender: Pokemon,
                       risk_averse: bool = True) -> List[MoveScore]:
        """Get all moves ranked by score"""
        available_moves = [m for m in attacker.moves if m.pp > 0]

        scored_moves = [
            self.score_move(m, attacker, defender, risk_averse)
            for m in available_moves
        ]

        return sorted(scored_moves, key=lambda x: x.score, reverse=True)


class EnemyPredictor:
    """
    Predict enemy behavior based on Pokemon species and trainer patterns.
    """

    _base_move_sets: Dict[str, List[str]] = {
        "Pikachu": ["Thunder Shock", "Growl", "Tail Whip", "Quick Attack"],
        "Charmander": ["Ember", "Growl", "Scratch", "Focus"],
        "Squirtle": ["Water Gun", "Tackle", "Tail Whip", "Withdraw"],
        "Bulbasaur": ["Vine Whip", "Tackle", "Growl", "Razor Leaf"],
        "Pidgey": ["Gust", "Tackle", "Sand Attack", "Quick Attack"],
        "Rattata": ["Tackle", "Quick Attack", "Hyper Fang", "Focus"],
        "Geodude": ["Tackle", "Defense Curl", "Magnitude", "Rock Throw"],
        "Zubat": ["Leech Life", "Supersonic", "Bite", "Wing Attack"],
        "Magikarp": ["Splash", "Tackle", "Flail"],
        "Gyarados": ["Bite", "Dragon Rage", "Hydro Pump", "Hyper Beam"],
        "Mewtwo": ["Confusion", "Disable", "Psychic", "Safeguard"],
        "Mew": ["Pound", "Reflect Type", "Transform", "Psychic"],
        "Gengar": ["Lick", "Hypnosis", "Dream Eater", "Shadow Ball"],
        "Snorlax": ["Body Slam", "Rest", "Sleep Talk", "Hyper Beam"],
        "Dragonite": ["Thunder Wave", "Agility", "Safeguard", "Outrage"],
    }

    _trainer_behaviors: Dict[str, Dict[str, Any]] = {
        "youngster": {
            "aggression": 0.7,
            "prefer_strong_moves": True,
            "switch_frequency": 0.1,
            "heal_threshold": 0.3
        },
        "lass": {
            "aggression": 0.5,
            "prefer_strong_moves": False,
            "switch_frequency": 0.2,
            "heal_threshold": 0.4
        },
        "bug_catcher": {
            "aggression": 0.4,
            "prefer_strong_moves": False,
            "switch_frequency": 0.3,
            "heal_threshold": 0.5
        },
        "hiker": {
            "aggression": 0.8,
            "prefer_strong_moves": True,
            "switch_frequency": 0.1,
            "heal_threshold": 0.2
        },
        "gym_leader": {
            "aggression": 0.9,
            "prefer_strong_moves": True,
            "switch_frequency": 0.4,
            "heal_threshold": 0.6
        },
        "rival": {
            "aggression": 0.85,
            "prefer_strong_moves": True,
            "switch_frequency": 0.5,
            "heal_threshold": 0.5
        },
        "champion": {
            "aggression": 0.95,
            "prefer_strong_moves": True,
            "switch_frequency": 0.6,
            "heal_threshold": 0.7
        },
    }

    def __init__(self, type_chart: Optional[TypeChart] = None) -> None:
        self.type_chart = type_chart or TypeChart()
        self._learned_patterns: Dict[str, Dict[str, Any]] = {}

    def predict_moves(self, species: str, level: int) -> List[str]:
        """Predict likely moves for a Pokemon species"""
        return self._base_move_sets.get(species, 
            ["Tackle", "Growl", "Scratch", "Ember"])

    def get_trainer_behavior(self, trainer_type: str) -> Dict[str, Any]:
        """Get behavior patterns for a trainer type"""
        return self._trainer_behaviors.get(trainer_type, 
            self._trainer_behaviors["youngster"])

    def predict_enemy_damage(
        self,
        enemy: Pokemon,
        player: Pokemon,
        move_name: str,
        power: int,
        accuracy: int
    ) -> DamageRange:
        """Predict damage range from enemy move"""
        move_type = self._get_move_type(move_name)
        move_category = self._get_move_category(move_name)

        move = Move(
            name=move_name,
            move_type=move_type,
            power=power,
            accuracy=accuracy,
            pp=30,
            max_pp=30,
            category=move_category
        )

        return DamageCalculator(self.type_chart).calculate_damage_range(
            enemy, player, move
        )

    def predict_threat_level(self, enemy: Pokemon, player: Pokemon) -> float:
        """Calculate threat level of enemy (0.0 = no threat, 1.0 = lethal)"""
        max_damage = 0
        for move in enemy.moves:
            if move.category != MoveCategory.STATUS and move.pp > 0:
                damage_range = DamageCalculator(
                    self.type_chart
                ).calculate_damage_range(enemy, player, move)
                max_damage = max(max_damage, damage_range.max_damage)

        if player.current_hp == 0:
            return 1.0

        threat = max_damage / player.current_hp
        return min(1.0, threat)

    def _get_move_type(self, move_name: str) -> PokemonType:
        """Infer move type from move name"""
        type_keywords = {
            "Thunder": PokemonType.ELECTRIC, "Shock": PokemonType.ELECTRIC,
            "Water": PokemonType.WATER, "Bubble": PokemonType.WATER,
            "Fire": PokemonType.FIRE, "Ember": PokemonType.FIRE, "Flamethrower": PokemonType.FIRE,
            "Grass": PokemonType.GRASS, "Vine": PokemonType.GRASS, "Leaf": PokemonType.GRASS,
            "Ice": PokemonType.ICE, "Blizzard": PokemonType.ICE,
            "Psychic": PokemonType.PSYCHIC, "Confusion": PokemonType.PSYCHIC,
            "Ghost": PokemonType.GHOST, "Shadow": PokemonType.GHOST,
            "Rock": PokemonType.ROCK, "Stone": PokemonType.ROCK,
            "Ground": PokemonType.GROUND, "Earthquake": PokemonType.GROUND,
            "Flying": PokemonType.FLYING, "Wing": PokemonType.FLYING,
            "Fighting": PokemonType.FIGHTING, "Punch": PokemonType.FIGHTING,
            "Bug": PokemonType.BUG, "Pin": PokemonType.BUG,
            "Poison": PokemonType.POISON, "Toxic": PokemonType.POISON,
            "Normal": PokemonType.NORMAL, "Tackle": PokemonType.NORMAL,
            "Dragon": PokemonType.DRAGON, "Rage": PokemonType.DRAGON,
        }

        for keyword, move_type in type_keywords.items():
            if keyword.lower() in move_name.lower():
                return move_type

        return PokemonType.NORMAL

    def _get_move_category(self, move_name: str) -> MoveCategory:
        """Infer move category from move name"""
        status_moves = ["Growl", "Tail Whip", "Leech Seed", "Thunder Wave", 
                       "Sleep Powder", "Toxic", "Reflect", "Light Screen",
                       "Rest", "Substitute", "Protect", "Detect"]

        if any(s.lower() in move_name.lower() for s in status_moves):
            return MoveCategory.STATUS

        physical_keywords = ["Tackle", "Scratch", "Bite", "Punch", "Kick",
                           "Slash", "Cut", "Fly", "Dig", "Rock Throw"]

        if any(k.lower() in move_name.lower() for k in physical_keywords):
            return MoveCategory.PHYSICAL

        return MoveCategory.SPECIAL


class BattleStrategist:
    """
    High-level battle strategy decisions:
    - Switch decision logic (when to switch)
    - Stat boosting priority
    - Catch probability (wild Pokemon)
    - Risk assessment (1 HP enemies, setup opportunities)
    """

    def __init__(self, type_chart: Optional[TypeChart] = None) -> None:
        self.type_chart = type_chart or TypeChart()

    def should_switch(
        self,
        current: Pokemon,
        opponent: Pokemon,
        party: List[Pokemon],
        move_selector: MoveSelector
    ) -> Tuple[bool, str, Optional[SwitchCandidate]]:
        """
        Determine if switching is the optimal choice.
        
        Returns: (should_switch, reason, best_candidate)
        """
        if current.current_hp == 0:
            return True, "Current Pokemon fainted", None

        if current.current_hp / current.max_hp < 0.1:
            return True, "Critical HP - emergency switch", None

        move_calculator = DamageCalculator(self.type_chart)
        for move in current.moves:
            if move.category != MoveCategory.STATUS and move.pp > 0:
                damage_range = move_calculator.calculate_damage_range(
                    current, opponent, move
                )
                guaranteed_ko, likely_ko, _ = move_calculator.can_ko(
                    damage_range, opponent.current_hp
                )
                if guaranteed_ko:
                    return False, "Can KO opponent", None

        threat_calculator = EnemyPredictor(self.type_chart)
        threat = threat_calculator.predict_threat_level(opponent, current)

        incoming_damage = 0
        most_threatening_move_type = opponent.moves[0].move_type if opponent.moves else PokemonType.NORMAL
        for move in opponent.moves:
            if move.category != MoveCategory.STATUS:
                damage_range = move_calculator.calculate_damage_range(
                    opponent, current, move
                )
                incoming_damage = max(incoming_damage, damage_range.max_damage)
                if damage_range.max_damage == incoming_damage:
                    most_threatening_move_type = move.move_type

        if incoming_damage >= current.current_hp:
            type_disadvantage = self.type_chart.get_effectiveness(
                most_threatening_move_type, current.types
            )
            if type_disadvantage >= 2.0:
                return True, "Type disadvantage - switch recommended", None

        candidates = self.evaluate_switch_candidates(
            current, opponent, party, move_selector
        )

        if candidates and candidates[0].score > 0.5:
            return True, f"Better matchup: {candidates[0].reasoning}", candidates[0]

        return False, "Current Pokemon is optimal", None

    def evaluate_switch_candidates(
        self,
        current: Pokemon,
        opponent: Pokemon,
        party: List[Pokemon],
        move_selector: MoveSelector
    ) -> List[SwitchCandidate]:
        """Evaluate all possible switch candidates"""
        candidates: List[SwitchCandidate] = []

        for pokemon in party:
            if pokemon == current or pokemon.current_hp == 0:
                continue

            damage_calculator = DamageCalculator(self.type_chart)
            incoming_damage = 0
            for move in opponent.moves:
                if move.category != MoveCategory.STATUS:
                    damage_range = damage_calculator.calculate_damage_range(
                        opponent, pokemon, move
                    )
                    incoming_damage = max(incoming_damage, damage_range.max_damage)

            survival_turns = pokemon.current_hp / max(incoming_damage, 1)

            defensive_score = min(survival_turns / 3.0, 1.0) if survival_turns >= 1 else 0.0

            best_move = move_selector.select_best_move(pokemon, opponent)
            offensive_score = best_move.score if best_move else 0.0

            type_effectiveness = self.type_chart.get_effectiveness(
                opponent.moves[0].move_type if opponent.moves else PokemonType.NORMAL,
                pokemon.types
            ) if opponent.moves else 1.0

            if type_effectiveness <= 0.5:
                matchup_bonus = 0.5
                reasoning = f"Resists opponent (0.5x effectiveness)"
            elif type_effectiveness >= 2.0:
                matchup_bonus = 1.2
                reasoning = f"Strong matchup (2x effectiveness)"
            else:
                matchup_bonus = 1.0
                reasoning = "Neutral matchup"

            total_score = (defensive_score * 0.4 + offensive_score * 0.6) * matchup_bonus

            candidates.append(SwitchCandidate(
                pokemon_name=pokemon.name,
                score=total_score,
                defensive_score=defensive_score,
                offensive_score=offensive_score,
                type_advantage=type_effectiveness,
                survival_turns=survival_turns,
                reasoning=reasoning
            ))

        return sorted(candidates, key=lambda x: x.score, reverse=True)

    def calculate_catch_probability(
        self,
        species: str,
        max_hp: int,
        current_hp: int,
        status: StatusCondition,
        ball_type: str
    ) -> CatchAttempt:
        """Calculate catch probability for wild Pokemon"""
        base_catch_rates = {
            "Pikachu": 190, "Charmander": 45, "Squirtle": 45, "Bulbasaur": 45,
            "Pidgey": 255, "Rattata": 255, "Zubat": 255, "Magikarp": 255,
            "Geodude": 255, "Gyarados": 45, "Mewtwo": 3, "Mew": 3,
            "Gengar": 45, "Snorlax": 25, "Dragonite": 45,
            "legendary": 3, "rare": 45, "common": 255
        }

        catch_rate = base_catch_rates.get(species, base_catch_rates["common"])

        ball_factors = {
            "Poke Ball": 1.0, "Great Ball": 1.5, "Ultra Ball": 2.0,
            "Master Ball": 255.0, "Safari Ball": 1.5
        }
        ball_factor = ball_factors.get(ball_type, 1.0)

        status_factors = {
            StatusCondition.NONE: 1.0,
            StatusCondition.POISONED: 1.5,
            StatusCondition.BURNED: 1.5,
            StatusCondition.PARALYZED: 1.5,
            StatusCondition.ASLEEP: 2.5,
            StatusCondition.FROZEN: 2.5
        }
        status_factor = status_factors.get(status, 1.0)

        hp_factor = ((3 * max_hp - 2 * current_hp) * catch_rate) / (3 * max_hp)
        hp_factor = max(1.0, hp_factor)

        success_probability = min(1.0, (hp_factor * ball_factor * status_factor) / 255)

        if ball_type == "Master Ball":
            recommended = "Master Ball"
            notes = ["Master Ball guarantees capture"]
        elif status in [StatusCondition.ASLEEP, StatusCondition.FROZEN]:
            recommended = "Poke Ball" if ball_factors.get("Poke Ball", 0) >= 5 else "Great Ball"
            notes = ["Status applied - good catch odds"]
        elif current_hp / max_hp < 0.2:
            recommended = "Great Ball"
            notes = ["Low HP - good catch odds"]
        else:
            recommended = "Poke Ball"
            notes = ["Consider weakening further or applying status"]

        return CatchAttempt(
            catch_rate=catch_rate,
            ball_factor=ball_factor,
            status_factor=status_factor,
            hp_factor=hp_factor,
            success_probability=success_probability,
            recommended_ball=recommended,
            notes=notes
        )

    def assess_setup_opportunity(
        self,
        attacker: Pokemon,
        defender: Pokemon
    ) -> Tuple[bool, float, str]:
        """
        Assess if setup (stat boosting) is safe.
        
        Returns: (is_safe, opportunity_score, reasoning)
        """
        move_calculator = DamageCalculator(self.type_chart)

        incoming_damage = 0
        for move in defender.moves:
            if move.category != MoveCategory.STATUS:
                damage_range = move_calculator.calculate_damage_range(
                    defender, attacker, move
                )
                incoming_damage = max(incoming_damage, damage_range.max_damage)

        survival_turns = attacker.current_hp / max(incoming_damage, 1)

        if survival_turns >= 3:
            return True, 1.0, "Safe to set up - can survive 3+ hits"
        elif survival_turns >= 2:
            return True, 0.7, "Moderately safe - can survive 2 hits"
        elif survival_turns >= 1:
            return False, 0.3, "Risky - can only survive 1 hit"
        else:
            return False, 0.0, "Unsafe - will be KO'd next hit"

    def assess_1_hp_risk(
        self,
        attacker: Pokemon,
        defender: Pokemon,
        move: Move
    ) -> Tuple[bool, str]:
        """
        Assess risk when enemy is at 1 HP.
        
        Returns: (is_safe, reasoning)
        """
        move_calculator = DamageCalculator(self.type_chart)
        damage_range = move_calculator.calculate_damage_range(
            attacker, defender, move
        )

        guaranteed_ko, likely_ko, _ = move_calculator.can_ko(
            damage_range, defender.current_hp
        )

        if guaranteed_ko:
            return True, "GUARANTEED KO - safe to attack"
        elif likely_ko:
            return True, "HIGH chance KO - worth the risk"
        elif move.accuracy < 90:
            return False, f"Miss risk too high ({move.accuracy}% accuracy)"
        else:
            return False, "Miss would give enemy another chance"

    def select_stat_boost_item(
        self,
        pokemon: Pokemon,
        opponent: Pokemon,
        inventory: Dict[str, int]
    ) -> Tuple[Optional[str], str]:
        """Select optimal stat boost item to use"""
        if "X Attack" in inventory and pokemon.attack_stage < 4:
            return "X Attack", "Boost attack for physical moves"
        if "X Defense" in inventory and pokemon.defense_stage < 4:
            return "X Defense", "Boost defense against strong attacks"
        if "X Speed" in inventory and pokemon.speed_stage < 4:
            return "X Speed", "Boost speed for priority"
        if "X Special" in inventory and pokemon.special_stage < 4:
            return "X Special", "Boost special for special moves"

        return None, "No stat boost items needed"


class CombatSystem:
    """
    Combat system with HP clamping, validation, and edge case handling.
    
    Provides simple interface for damage calculation and HP management
    with proper validation and defaults for missing data.
    """

    def __init__(self) -> None:
        self.type_chart = TypeChart()
        self.damage_calculator = DamageCalculator(self.type_chart)

    def clamp_hp(self, current: int, max_hp: int) -> int:
        """
        Ensure HP is between 0 and max_hp.

        Args:
            current: The current HP value
            max_hp: The maximum HP for the Pokemon

        Returns:
            HP value clamped to [0, max_hp] range
        """
        return clamp_hp(current, max_hp)

    def calculate_hp_after_damage(self, current_hp: int, damage: int, max_hp: int = None) -> int:
        """
        Calculate new HP after taking damage with clamping.

        Args:
            current_hp: Current HP before damage
            damage: Amount of damage to subtract
            max_hp: Maximum HP for the Pokemon (defaults to current_hp if not provided)

        Returns:
            New HP value after damage, clamped to [0, max_hp]
        """
        if max_hp is None:
            max_hp = current_hp
        return calculate_hp_after_damage(current_hp, damage, max_hp)

    def calculate_damage(
        self,
        attacker: Dict[str, Any],
        defender: Dict[str, Any],
        move: Dict[str, Any]
    ) -> int:
        """
        Calculate damage from attacker to defender with a move.
        
        Handles missing data by using defaults for stats.
        
        Args:
            attacker: Attacker Pokemon data dict
            defender: Defender Pokemon data dict  
            move: Move data dict with 'power' key
            
        Returns:
            Calculated damage (0 for status moves or missing power)
        """
        power = move.get("power", 0)
        
        if power is None or power == 0:
            return 0
        
        level = attacker.get("level", get_default_stat("level"))
        attack = attacker.get("attack", get_default_stat("attack"))
        defense = defender.get("defense", get_default_stat("defense"))
        
        stab = 1.0
        if "type" in attacker and "type" in move:
            if attacker["type"] == move["type"]:
                stab = 1.5
        
        type_effectiveness = 1.0
        
        damage = self.damage_calculator.calculate_base_damage(
            level=level,
            power=power,
            attack=attack,
            defense=defense,
            stab=stab,
            type_effectiveness=type_effectiveness,
            is_critical=False,
            random_factor=1.0
        )
        
        return damage

    def analyze_battle_state(self, battle_state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze a battle state and return insights.
        
        Args:
            battle_state: Battle state dictionary
            
        Returns:
            Analysis results dictionary
            
        Raises:
            ValueError: If battle state is invalid
            TypeError: If battle state is not a dictionary
        """
        validate_pokemon_data(battle_state, required_fields=[])
        
        if "player" not in battle_state and "enemy" not in battle_state:
            raise ValueError("Battle state must contain 'player' and/or 'enemy' keys")
        
        return {
            "valid": True,
            "has_player": "player" in battle_state,
            "has_enemy": "enemy" in battle_state,
        }


class CombatManager:
    """
    Main combat system coordinating all combat heuristics.
    """

    def __init__(self) -> None:
        self.type_chart = TypeChart()
        self.damage_calculator = DamageCalculator(self.type_chart)
        self.move_selector = MoveSelector(self.type_chart)
        self.enemy_predictor = EnemyPredictor(self.type_chart)
        self.strategist = BattleStrategist(self.type_chart)

    def get_combat_state(
        self,
        player_pokemon: Pokemon,
        enemy_pokemon: Pokemon,
        battle_type: str
    ) -> Dict[str, Any]:
        """Get comprehensive combat state for AI decision making"""
        best_move = self.move_selector.select_best_move(
            player_pokemon, enemy_pokemon
        )

        threat = self.enemy_predictor.predict_threat_level(
            enemy_pokemon, player_pokemon
        )

        should_switch, switch_reason, candidate = self.strategist.should_switch(
            player_pokemon, enemy_pokemon, [], self.move_selector
        )

        return {
            "best_move": best_move.move.name if best_move.move else None,
            "best_move_score": best_move.score,
            "best_move_ko_likely": best_move.ko_likely,
            "best_move_notes": best_move.notes,
            "threat_level": threat,
            "should_switch": should_switch,
            "switch_reason": switch_reason,
            "switch_candidate": candidate.pokemon_name if candidate else None,
            "can_ko_enemy": best_move.ko_likely if best_move.damage_range else False,
            "enemy_can_ko": threat >= 1.0,
        }

    def calculate_catch_odds(
        self,
        species: str,
        max_hp: int,
        current_hp: int,
        status: StatusCondition,
        ball_type: str
    ) -> CatchAttempt:
        """Calculate catch odds for wild Pokemon"""
        return self.strategist.calculate_catch_probability(
            species, max_hp, current_hp, status, ball_type
        )