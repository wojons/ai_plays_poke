"""
Entity Management & Party Optimization for PTP-01X Pokemon AI

Implements Pokemon data tracking, carry score calculation, evolution management,
and team composition optimization.

Components:
- PokemonData Model: Complete Pokemon representation with stats, moves, status
- CarryScoreCalculator: Battle utility scoring system
- EvolutionManager: Evolution timing and decision logic
- TeamCompositionOptimizer: Party composition optimization

Integration Points:
- Combat: TypeChart for effectiveness, stat calculations
- GOAP: Goal prioritization, team optimization goals
- Vision: Pokemon identification, status detection, evolution triggers
- Navigation: HM requirements, grinding route planning

Performance:
- Full party scan: <80ms
- Carry score calc (6 Pokemon): <30ms
- Evolution check: <15ms
- Type coverage analysis: <10ms
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING, Dict, List, Optional, Set, Tuple, Any
import logging

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    pass


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


class GrowthRate(Enum):
    """Experience growth rates"""
    FAST = "fast"
    MEDIUM = "medium"
    SLOW = "slow"
    PARABOLIC = "parabolic"
    ERRATIC = "erratic"
    FLUCTUATING = "fluctuating"


class TeamRole(Enum):
    """Pokemon team roles"""
    SWEEPER = "sweeper"
    TANK = "tank"
    SUPPORT = "support"
    UTILITY = "utility"
    MIXED = "mixed"
    COUNTER = "counter"


class TypeChart:
    """Gen 1 type effectiveness chart with 18 types."""
    
    _chart: Dict[PokemonType, Dict[PokemonType, float]] = {}
    
    def __init__(self) -> None:
        self._initialize_chart()
    
    def _initialize_chart(self) -> None:
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
        if attack_type not in self._chart:
            return 1.0
        
        effectiveness = 1.0
        for defender_type in defender_types:
            if defender_type in self._chart[attack_type]:
                effectiveness *= self._chart[attack_type][defender_type]
        
        return effectiveness
    
    def is_immune(self, attack_type: PokemonType, defender_types: List[PokemonType]) -> bool:
        return self.get_effectiveness(attack_type, defender_types) == 0.0
    
    def is_super_effective(self, attack_type: PokemonType, 
                           defender_types: List[PokemonType]) -> bool:
        return self.get_effectiveness(attack_type, defender_types) >= 2.0


@dataclass
class PokemonStats:
    """Individual stat values (calculated from base stats, IVs, EVs, level)"""
    hp: int
    attack: int
    defense: int
    speed: int
    special: int

    def total(self) -> int:
        return self.hp + self.attack + self.defense + self.speed + self.special


@dataclass
class BaseStats:
    """Species base stats (immutable per species)"""
    species_id: str
    species_name: str
    hp: int
    attack: int
    defense: int
    speed: int
    special: int
    type_primary: PokemonType
    type_secondary: Optional[PokemonType]
    catch_rate: int
    base_experience_yield: int
    growth_rate: GrowthRate


@dataclass
class IndividualValues:
    """Gen 1 IVs (0-15 each)"""
    hp: int = 0
    attack: int = 0
    defense: int = 0
    speed: int = 0
    special: int = 0

    def __post_init__(self):
        self.hp = max(0, min(15, self.hp))
        self.attack = max(0, min(15, self.attack))
        self.defense = max(0, min(15, self.defense))
        self.speed = max(0, min(15, self.speed))
        self.special = max(0, min(15, self.special))

    def total(self) -> int:
        return self.hp + self.attack + self.defense + self.speed + self.special


@dataclass
class EffortValues:
    """Gen 1 EVs (0-65535 each, 0-510 total before Gen 2)"""
    hp: int = 0
    attack: int = 0
    defense: int = 0
    speed: int = 0
    special: int = 0

    def total(self) -> int:
        return self.hp + self.attack + self.defense + self.speed + self.special

    def __post_init__(self):
        self.hp = max(0, min(65535, self.hp))
        self.attack = max(0, min(65535, self.attack))
        self.defense = max(0, min(65535, self.defense))
        self.speed = max(0, min(65535, self.speed))
        self.special = max(0, min(65535, self.special))


@dataclass
class Move:
    """Individual move with PP tracking"""
    move_id: str
    name: str
    move_type: PokemonType
    power: int
    accuracy: int
    pp: int
    max_pp: int
    category: MoveCategory

    def pp_percentage(self) -> float:
        if self.max_pp == 0:
            return 0.0
        return self.pp / self.max_pp


@dataclass
class Experience:
    """Experience tracking with growth curve support"""
    current: int
    to_next_level: int
    growth_rate: str = "medium"

    def level_progress(self) -> float:
        total = self.current + self.to_next_level
        if total == 0:
            return 0.0
        return self.current / total


@dataclass
class PokemonData:
    """Complete Pokemon data model."""
    pokemon_id: str
    species_id: str
    nickname: Optional[str]
    level: int
    current_hp: int
    max_hp: int
    base_stats: BaseStats
    ivs: IndividualValues
    evs: EffortValues
    moves: List[Move]
    status: StatusCondition
    experience: Experience
    types: Tuple[PokemonType, Optional[PokemonType]]
    happiness: int = 100
    is_shiny: bool = False
    catch_location: Optional[str] = None
    catch_level: int = 1
    date_caught: Optional[str] = None
    victories: int = 0
    defeats: int = 0
    experience_gained: int = 0
    critical_battle_wins: int = 0
    solo_gym_wins: int = 0

    def species_name(self) -> str:
        if self.nickname:
            return self.nickname
        return self.base_stats.species_name

    def can_battle(self) -> bool:
        return self.current_hp > 0 and self.status != StatusCondition.FROZEN

    def has_move(self, move_name: str) -> bool:
        return any(m.name.lower() == move_name.lower() for m in self.moves)

    def get_move(self, move_name: str) -> Optional[Move]:
        for move in self.moves:
            if move.name.lower() == move_name.lower():
                return move
        return None

    def total_pp_remaining(self) -> int:
        return sum(move.pp for move in self.moves)

    def average_pp_remaining(self) -> float:
        if not self.moves:
            return 0.0
        return sum(move.pp_percentage() for move in self.moves) / len(self.moves)

    def offensive_stat(self) -> int:
        best_physical = max(
            (m for m in self.moves if m.category == MoveCategory.PHYSICAL),
            default=None,
            key=lambda m: m.power
        )
        best_special = max(
            (m for m in self.moves if m.category == MoveCategory.SPECIAL),
            default=None,
            key=lambda m: m.power
        )

        if best_physical and best_physical.power > (best_special.power if best_special else 0):
            return self.base_stats.attack + self.ivs.attack + (self.evs.attack // 4)
        return self.base_stats.special + self.ivs.special + (self.evs.special // 4)

    def defensive_stat(self) -> int:
        if self.base_stats.defense >= self.base_stats.special:
            return self.base_stats.defense + self.ivs.defense + (self.evs.defense // 4)
        return self.base_stats.special + self.ivs.special + (self.evs.special // 4)

    def is_overleveled(self, avg_level: float) -> bool:
        return self.level > avg_level + 3

    def is_underleveled(self, avg_level: float) -> bool:
        return self.level < avg_level - 3

    def get_best_move(self) -> Optional[Move]:
        valid_moves = [m for m in self.moves if m.pp > 0 and m.category != MoveCategory.STATUS]
        if not valid_moves:
            return None
        return max(valid_moves, key=lambda m: m.power)

    def get_dps_potential(self) -> float:
        best_move = self.get_best_move()
        if not best_move:
            return 10.0
        
        attack_stat = self.offensive_stat()
        speed_factor = (self.base_stats.speed + self.ivs.speed + self.evs.speed // 4) / 100
        speed_weight = speed_factor ** 0.5
        
        stab = 1.2 if best_move.move_type in self.types else 1.0
        dps = (best_move.power * attack_stat / 100) * speed_weight * stab
        return max(dps, 1.0)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pokemon_id": self.pokemon_id,
            "species_id": self.species_id,
            "nickname": self.nickname,
            "level": self.level,
            "current_hp": self.current_hp,
            "max_hp": self.max_hp,
            "base_stats": {
                "species_id": self.base_stats.species_id,
                "species_name": self.base_stats.species_name,
                "hp": self.base_stats.hp,
                "attack": self.base_stats.attack,
                "defense": self.base_stats.defense,
                "speed": self.base_stats.speed,
                "special": self.base_stats.special,
                "types": [self.base_stats.type_primary.value, self.base_stats.type_secondary.value if self.base_stats.type_secondary else None]
            },
            "ivs": {
                "hp": self.ivs.hp,
                "attack": self.ivs.attack,
                "defense": self.ivs.defense,
                "speed": self.ivs.speed,
                "special": self.ivs.special
            },
            "moves": [{"name": m.name, "pp": m.pp, "max_pp": m.max_pp, "power": m.power} for m in self.moves],
            "status": self.status.value,
            "experience": {
                "current": self.experience.current,
                "to_next_level": self.experience.to_next_level
            },
            "types": [t.value for t in self.types if t],
            "happiness": self.happiness,
            "is_shiny": self.is_shiny,
            "victories": self.victories,
            "defeats": self.defeats,
            "experience_gained": self.experience_gained
        }


@dataclass
class Team:
    """Complete team data structure for party management."""
    team_id: str
    name: Optional[str]
    party: List[Optional[PokemonData]]
    box: List[PokemonData]
    total_battles: int = 0
    total_victories: int = 0
    total_defeats: int = 0
    last_analysis: Optional[str] = None

    def __post_init__(self):
        if len(self.party) != 6:
            raise ValueError("Party must have exactly 6 slots")
        while len(self.party) < 6:
            self.party.append(None)

    def active_pokemon(self) -> List[PokemonData]:
        return [p for p in self.party if p is not None]

    def active_count(self) -> int:
        return len(self.active_pokemon())

    def can_battle(self) -> bool:
        return any(p.can_battle() for p in self.active_pokemon())

    def battle_ready_count(self) -> int:
        return sum(1 for p in self.active_pokemon() if p.can_battle())

    def average_level(self) -> float:
        active = self.active_pokemon()
        if not active:
            return 0.0
        return sum(p.level for p in active) / len(active)

    def level_spread(self) -> int:
        active = self.active_pokemon()
        if len(active) < 2:
            return 0
        return max(p.level for p in active) - min(p.level for p in active)

    def get_lead_pokemon(self) -> Optional[PokemonData]:
        for p in self.party:
            if p is not None:
                return p
        return None

    def has_hm_user(self) -> bool:
        hm_moves = {"CUT", "FLY", "SURF", "STRENGTH", "FLASH", "WHIRLPOOL", "WATERFALL"}
        for p in self.active_pokemon():
            for move in p.moves:
                if move.name.upper() in hm_moves:
                    return True
        return False

    def get_hm_users(self) -> Dict[str, List[PokemonData]]:
        hm_moves = {"CUT", "FLY", "SURF", "STRENGTH", "FLASH", "WHIRLPOOL", "WATERFALL"}
        hm_users: Dict[str, List[PokemonData]] = {hm: [] for hm in hm_moves}

        for p in self.active_pokemon():
            for move in p.moves:
                if move.name.upper() in hm_moves:
                    hm_users[move.name.upper()].append(p)

        return {k: v for k, v in hm_users.items() if v}

    def needs_rebalancing(self) -> bool:
        return self.level_spread() > 6


@dataclass
class TypeValueWeights:
    """Type value multipliers for uniqueness calculation"""
    ELECTRIC: float = 1.5
    PSYCHIC: float = 1.4
    ICE: float = 1.3
    GHOST: float = 1.3
    DRAGON: float = 1.3
    GROUND: float = 1.2
    FIRE: float = 1.2
    WATER: float = 1.1
    GRASS: float = 1.0
    FLYING: float = 1.0
    FIGHTING: float = 1.0
    BUG: float = 0.8
    POISON: float = 0.7
    NORMAL: float = 0.6
    ROCK: float = 0.6

    def get_weight(self, type_obj: PokemonType) -> float:
        return getattr(self, type_obj.name, 1.0)


@dataclass
class CarryScoreBreakdown:
    """Detailed breakdown of carry score calculation"""
    level_relevance: float
    type_uniqueness: float
    move_coverage: float
    stat_efficiency: float
    rarity_modifier: float
    sentimental_modifier: float
    final_score: float

    def to_dict(self) -> Dict[str, float]:
        return {
            "level_relevance": self.level_relevance,
            "type_uniqueness": self.type_uniqueness,
            "move_coverage": self.move_coverage,
            "stat_efficiency": self.stat_efficiency,
            "rarity_modifier": self.rarity_modifier,
            "sentimental_modifier": self.sentimental_modifier,
            "final_score": self.final_score
        }


@dataclass
class EvolutionCondition:
    """Evolution requirement specification"""
    condition_type: str
    required_value: Any
    target_species_id: str
    target_species_name: str
    learnable_moves: List[Dict[str, Any]]
    stat_changes: Dict[str, int]


@dataclass
class PreEvolutionMove:
    """Critical move available only before evolution"""
    move_id: str
    move_name: str
    learn_level: int
    evolution_level: int
    value_rating: str
    power: int


@dataclass
class EvolutionDecision:
    """Evolution timing decision result"""
    decision: str
    wait_levels: Optional[int]
    reason: str
    expected_move: Optional[PreEvolutionMove]
    stat_improvement: float
    net_benefit_score: float


@dataclass
class TypeCoverage:
    """Type coverage analysis result"""
    covered_types: Set[PokemonType]
    uncovered_types: Set[PokemonType]
    critical_gaps: Set[PokemonType]
    coverage_percentage: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "covered_types": [t.value for t in self.covered_types],
            "uncovered_types": [t.value for t in self.uncovered_types],
            "critical_gaps": [t.value for t in self.critical_gaps],
            "coverage_percentage": self.coverage_percentage
        }


@dataclass
class TeamAnalysis:
    """Complete team analysis result"""
    type_coverage: TypeCoverage
    carry_scores: Dict[str, float]
    role_assignments: Dict[str, str]
    stat_distribution: Dict[str, float]
    move_overlap: List[Dict[str, Any]]
    recommendations: List[str]
    team_score: float


@dataclass
class PartySlot:
    """Party slot with Pokemon and optimization score"""
    slot_index: int
    pokemon: Optional[PokemonData]
    score: float
    recommended_role: str
    suggested_moves: List[str]


CRITICAL_PRE_EVO_MOVES: Dict[str, List[PreEvolutionMove]] = {
    "BULBASAUR": [
        PreEvolutionMove(
            move_id="RAZOR_LEAF", move_name="Razor Leaf",
            learn_level=27, evolution_level=16,
            value_rating="STAB_POWERUP", power=55
        )
    ],
    "CHARMANDER": [
        PreEvolutionMove(
            move_id="FLAMETHROWER", move_name="Flamethrower",
            learn_level=38, evolution_level=16,
            value_rating="STRONG_STAB", power=90
        ),
        PreEvolutionMove(
            move_id="SLASH", move_name="Slash",
            learn_level=33, evolution_level=16,
            value_rating="HIGH_CRIT", power=70
        )
    ],
    "SQUIRTLE": [
        PreEvolutionMove(
            move_id="HYDRO_PUMP", move_name="Hydro Pump",
            learn_level=42, evolution_level=16,
            value_rating="WATER_NUKE", power=110
        )
    ],
    "PIKACHU": [
        PreEvolutionMove(
            move_id="THUNDER", move_name="Thunder",
            learn_level=43, evolution_level=999,
            value_rating="ELECTRIC_STAB", power=110
        )
    ],
    "GROWLITHE": [
        PreEvolutionMove(
            move_id="FLAMETHROWER", move_name="Flamethrower",
            learn_level=50, evolution_level=999,
            value_rating="STRONG_STAB", power=90
        )
    ],
    "EEVEE": [],
    "ABRA": [
        PreEvolutionMove(
            move_id="PSYCHIC", move_name="Psychic",
            learn_level=38, evolution_level=16,
            value_rating="PSYCHIC_STAB", power=90
        )
    ]
}


class CarryScoreCalculator:
    """Calculates battle utility scores for Pokemon."""

    RARITY_MULTIPLIERS: Dict[str, float] = {
        "BULBASAUR": 1.15, "IVYSAUR": 1.15, "VENUSAUR": 1.15,
        "CHARMANDER": 1.15, "CHARMELEON": 1.15, "CHARIZARD": 1.15,
        "SQUIRTLE": 1.15, "WARTORTLE": 1.15, "BLASTOISE": 1.15,
        "MEWTWO": 1.3, "MEW": 1.3,
        "ARTICUNO": 1.25, "ZAPDOS": 1.25, "MOLTRES": 1.25,
        "DRAGONITE": 1.2,
        "GYARADOS": 1.15,
        "ALAKAZAM": 1.1, "MACHAMP": 1.1, "GENGAR": 1.1,
        "PIDGEY": 0.7, "PIDGEOTTO": 0.7, "PIDGEOT": 0.7,
        "RATTATA": 0.8, "RATICATE": 0.8,
        "CATERPIE": 0.6, "METAPOD": 0.6, "BUTTERFREE": 0.6,
        "WEEDLE": 0.6, "KAKUNA": 0.6, "BEEDRILL": 0.6
    }

    def __init__(
        self,
        type_chart: TypeChart,
        species_data: Dict[str, BaseStats]
    ):
        self.type_chart = type_chart
        self.species_data = species_data
        self.type_values = TypeValueWeights()

    def calculate_level_relevance(
        self,
        pokemon: PokemonData,
        expected_encounter_level: int
    ) -> float:
        if expected_encounter_level <= 0:
            return 15.0

        level_diff = pokemon.level - expected_encounter_level

        if level_diff == 0:
            base_score = 20.0
        elif level_diff > 0:
            excess = level_diff
            if excess <= 3:
                base_score = 22.0 - (excess * 0.5)
            elif excess <= 8:
                base_score = 20.0 - (excess * 0.3)
            else:
                base_score = max(8.0, 15.0 - (excess * 0.1))
        else:
            deficit = abs(level_diff)
            if deficit <= 2:
                base_score = 18.0 - (deficit * 1.5)
            elif deficit <= 5:
                base_score = 12.0 - (deficit * 0.8)
            else:
                base_score = max(2.0, 5.0 - (deficit * 0.2))

        return max(0.0, min(25.0, base_score))

    def calculate_type_uniqueness(
        self,
        pokemon: PokemonData,
        current_party: List[Optional[PokemonData]],
        upcoming_battles: Optional[List[Dict[str, Any]]] = None
    ) -> float:
        party_types: Set[PokemonType] = set()
        for member in current_party:
            if member and member != pokemon:
                for t in member.types:
                    if t:
                        party_types.add(t)

        unique_types = [t for t in pokemon.types if t and t not in party_types]

        if not unique_types:
            return 0.0

        base_uniqueness = len(unique_types) * 8.0

        quality_bonus = sum(self.type_values.get_weight(t) * 4.0 for t in unique_types)

        boss_bonus = 0.0
        if upcoming_battles:
            for battle in upcoming_battles:
                boss_types = battle.get("boss_types", [])
                for unique_type in unique_types:
                    for boss_type_name in boss_types:
                        try:
                            boss_type = PokemonType(boss_type_name)
                            effectiveness = self.type_chart.get_effectiveness(
                                unique_type, [boss_type]
                            )
                            if effectiveness >= 2.0:
                                boss_bonus += 2.0
                        except ValueError:
                            continue

        final_score = base_uniqueness + quality_bonus + min(boss_bonus, 6.0)
        return max(0.0, min(30.0, final_score))

    def calculate_move_coverage(
        self,
        pokemon: PokemonData,
        uncovered_enemy_types: Optional[List[PokemonType]] = None
    ) -> float:
        all_types = list(PokemonType)
        target_types = uncovered_enemy_types or all_types

        coverage_score = 0.0

        for move in pokemon.moves:
            if move.pp <= 0 or move.category == MoveCategory.STATUS:
                continue

            move_score = 0.0
            for target_type in target_types:
                effectiveness = self.type_chart.get_effectiveness(
                    move.move_type, [target_type]
                )

                if effectiveness >= 2.0:
                    move_score += 3.0
                elif effectiveness == 1.0:
                    move_score += 0.5
                elif effectiveness >= 0.5:
                    move_score += 0.1

            if move.power >= 90:
                move_score += 1.0
            elif move.power >= 70:
                move_score += 0.5

            if move.move_type in pokemon.types:
                move_score *= 1.2

            coverage_score += move_score

        return max(0.0, min(25.0, coverage_score))

    def calculate_stat_efficiency(
        self,
        pokemon: PokemonData,
        species_potential: BaseStats
    ) -> float:
        current_dps = pokemon.get_dps_potential()

        expected_dps_multiplier = 1.0 + (pokemon.level / 100.0)

        base_attack = species_potential.attack
        base_special = species_potential.special
        base_speed = species_potential.speed

        expected_speed_stat = base_speed + pokemon.ivs.speed + (pokemon.evs.speed // 4)

        best_base_stat = max(base_attack, base_special)

        speed_factor = (expected_speed_stat / 100) ** 0.5
        expected_dps = (best_base_stat * expected_dps_multiplier) * speed_factor

        if expected_dps > 0:
            efficiency_ratio = current_dps / expected_dps
        else:
            efficiency_ratio = 1.0

        if efficiency_ratio < 0.6:
            score = efficiency_ratio * 20.0 * 0.5
        elif efficiency_ratio < 0.8:
            score = efficiency_ratio * 20.0 * 0.8
        else:
            score = min(efficiency_ratio * 20.0, 30.0)

        return max(0.0, min(20.0, score))

    def apply_rarity_modifier(self, pokemon: PokemonData) -> float:
        return self.RARITY_MULTIPLIERS.get(pokemon.species_id, 1.0)

    def apply_sentimental_modifier(self, pokemon: PokemonData) -> float:
        hero_score = 0.0

        if pokemon.critical_battle_wins > 3:
            hero_score += 1.0

        if pokemon.solo_gym_wins > 0:
            hero_score += 2.0

        if pokemon.is_shiny:
            hero_score += 1.5

        if pokemon.level < 20 and pokemon.victories > 10:
            hero_score += 0.8

        if pokemon.level > 50:
            hero_score *= 0.3
        elif pokemon.level > 35:
            hero_score *= 0.5
        elif pokemon.level > 20:
            hero_score *= 0.7

        return min(1.0 + (hero_score * 0.1), 1.3)

    def calculate_carry_score(
        self,
        pokemon: PokemonData,
        current_party: List[Optional[PokemonData]],
        upcoming_battles: Optional[List[Dict[str, Any]]] = None,
        expected_encounter_level: int = 25
    ) -> Tuple[float, CarryScoreBreakdown]:
        level_relevance = self.calculate_level_relevance(pokemon, expected_encounter_level)
        type_uniqueness = self.calculate_type_uniqueness(pokemon, current_party, upcoming_battles)
        move_coverage = self.calculate_move_coverage(pokemon)

        species_potential = self.species_data.get(pokemon.species_id, pokemon.base_stats)
        stat_efficiency = self.calculate_stat_efficiency(pokemon, species_potential)

        rarity_mod = self.apply_rarity_modifier(pokemon)
        sentimental_mod = self.apply_sentimental_modifier(pokemon)

        base_score = (
            level_relevance * 0.25 +
            type_uniqueness * 0.30 +
            move_coverage * 0.25 +
            stat_efficiency * 0.20
        )

        final_score = base_score * rarity_mod * sentimental_mod

        breakdown = CarryScoreBreakdown(
            level_relevance=level_relevance,
            type_uniqueness=type_uniqueness,
            move_coverage=move_coverage,
            stat_efficiency=stat_efficiency,
            rarity_modifier=rarity_mod,
            sentimental_modifier=sentimental_mod,
            final_score=final_score
        )

        return final_score, breakdown

    def should_bench(self, score: float) -> str:
        if score > 70:
            return "protect"
        elif score > 50:
            return "conditional"
        elif score > 35:
            return "bench"
        else:
            return "immediate_bench"


class EvolutionManager:
    """Manages evolution timing and decision logic."""

    def __init__(
        self,
        evolution_data: Dict[str, List[EvolutionCondition]],
        move_data: Dict[str, Dict[str, Any]],
        type_chart: TypeChart
    ):
        self.evolution_data = evolution_data
        self.move_data = move_data
        self.type_chart = type_chart

    def get_evolution_conditions(
        self,
        species_id: str,
        current_level: int
    ) -> List[EvolutionCondition]:
        return self.evolution_data.get(species_id, [])

    def check_evolution_available(
        self,
        pokemon: PokemonData
    ) -> Optional[EvolutionCondition]:
        conditions = self.get_evolution_conditions(pokemon.species_id, pokemon.level)

        for condition in conditions:
            if condition.condition_type == "level":
                if pokemon.level >= condition.required_value:
                    return condition
        return None

    def evaluate_pre_evolution_moves(
        self,
        species_id: str,
        current_level: int,
        evolution_level: int
    ) -> Optional[PreEvolutionMove]:
        important_moves = CRITICAL_PRE_EVO_MOVES.get(species_id, [])

        for move_data in important_moves:
            if move_data.learn_level <= evolution_level and move_data.learn_level > current_level:
                return move_data

        return None

    def calculate_evolution_vs_wait_tradeoff(
        self,
        pokemon: PokemonData,
        evolution: EvolutionCondition,
        best_pre_evo_move: Optional[PreEvolutionMove]
    ) -> EvolutionDecision:
        stat_improvement = 0.0
        for stat_name, change in evolution.stat_changes.items():
            stat_improvement += abs(change)

        stat_improvement_score = min(stat_improvement * 2.0, 30.0)

        if best_pre_evo_move:
            wait_benefit = 15.0
            wait_benefit = wait_benefit * (best_pre_evo_move.power / 100.0)
            wait_cost = best_pre_evo_move.learn_level - pokemon.level
        else:
            wait_benefit = 0.0
            wait_cost = 0

        net_benefit = stat_improvement_score - (wait_cost * 0.5)

        if best_pre_evo_move and wait_benefit > net_benefit * 1.2:
            return EvolutionDecision(
                decision=f"wait_{best_pre_evo_move.learn_level - pokemon.level}_levels",
                wait_levels=best_pre_evo_move.learn_level - pokemon.level,
                reason=f"Wait for {best_pre_evo_move.move_name} (Power: {best_pre_evo_move.power})",
                expected_move=best_pre_evo_move,
                stat_improvement=stat_improvement,
                net_benefit_score=net_benefit
            )
        elif best_pre_evo_move and wait_benefit > net_benefit * 0.9:
            return EvolutionDecision(
                decision="consider_waiting",
                wait_levels=best_pre_evo_move.learn_level - pokemon.level,
                reason=f"Consider waiting for {best_pre_evo_move.move_name}",
                expected_move=best_pre_evo_move,
                stat_improvement=stat_improvement,
                net_benefit_score=net_benefit
            )
        else:
            return EvolutionDecision(
                decision="evolve_now",
                wait_levels=None,
                reason="Evolution provides best overall benefit",
                expected_move=None,
                stat_improvement=stat_improvement,
                net_benefit_score=net_benefit
            )

    def calculate_move_value(
        self,
        move: Move,
        pokemon: PokemonData
    ) -> float:
        value = 0.0

        if move.category == MoveCategory.STATUS:
            return 5.0

        if move.power >= 90:
            value += 3.0
        elif move.power >= 70:
            value += 2.0
        elif move.power >= 50:
            value += 1.0

        if move.move_type in pokemon.types:
            value *= 1.5

        for target_type in PokemonType:
            effectiveness = self.type_chart.get_effectiveness(move.move_type, [target_type])
            if effectiveness >= 2.0:
                value += 1.0

        return min(value, 15.0)

    def should_use_evolution_item(
        self,
        pokemon: PokemonData,
        item_name: str,
        team_needs: Dict[str, Any]
    ) -> bool:
        evolution = self.check_evolution_available(pokemon)
        if not evolution:
            return False

        if evolution.condition_type != "item":
            return False

        type_needs = team_needs.get("type_coverage_needed", [])
        current_types = list(pokemon.types)

        for needed_type in type_needs:
            if PokemonType(needed_type) not in current_types:
                return True

        return False

    def get_evolution_readiness(
        self,
        pokemon: PokemonData
    ) -> Dict[str, Any]:
        evolution = self.check_evolution_available(pokemon)

        if not evolution:
            return {
                "current_level": pokemon.level,
                "evolution_available": False,
                "evolution_conditions": [],
                "critical_pre_evo_moves": [],
                "recommended_action": "continue_training",
                "wait_justification": None
            }

        best_pre_evo = self.evaluate_pre_evolution_moves(
            pokemon.species_id,
            pokemon.level,
            evolution.required_value if evolution.condition_type == "level" else 999
        )

        decision = self.calculate_evolution_vs_wait_tradeoff(pokemon, evolution, best_pre_evo)

        return {
            "current_level": pokemon.level,
            "evolution_available": True,
            "evolution_conditions": [evolution],
            "critical_pre_evo_moves": CRITICAL_PRE_EVO_MOVES.get(pokemon.species_id, []),
            "recommended_action": decision.decision,
            "wait_justification": decision.reason,
            "decision_details": {
                "decision": decision.decision,
                "wait_levels": decision.wait_levels,
                "stat_improvement": decision.stat_improvement,
                "net_benefit_score": decision.net_benefit_score
            }
        }


class TeamCompositionOptimizer:
    """Optimizes team composition for current and upcoming content."""

    def __init__(
        self,
        carry_calculator: CarryScoreCalculator,
        species_data: Dict[str, BaseStats],
        type_chart: TypeChart
    ):
        self.carry_calculator = carry_calculator
        self.species_data = species_data
        self.type_chart = type_chart

    def analyze_type_coverage(
        self,
        party: List[Optional[PokemonData]],
        upcoming_battles: Optional[List[Dict[str, Any]]] = None
    ) -> TypeCoverage:
        all_types = set(PokemonType)
        covered_types: Set[PokemonType] = set()
        party_move_types: Set[PokemonType] = set()

        for pokemon in party:
            if pokemon is None:
                continue
            for move in pokemon.moves:
                if move.pp > 0 and move.category != MoveCategory.STATUS:
                    party_move_types.add(move.move_type)

        for move_type in party_move_types:
            for target_type in all_types:
                effectiveness = self.type_chart.get_effectiveness(move_type, [target_type])
                if effectiveness >= 2.0:
                    covered_types.add(target_type)
                    break

        uncovered = all_types - covered_types

        critical_gaps: Set[PokemonType] = set()
        if upcoming_battles:
            for battle in upcoming_battles:
                boss_types = battle.get("boss_types", [])
                for boss_type_name in boss_types:
                    try:
                        boss_type = PokemonType(boss_type_name)
                        effective_counters = [
                            t for t in all_types
                            if self.type_chart.get_effectiveness(t, [boss_type]) >= 2.0
                        ]
                        if not any(counter in party_move_types for counter in effective_counters):
                            critical_gaps.add(boss_type)
                    except ValueError:
                        continue

        coverage_pct = len(covered_types) / len(all_types) if all_types else 0.0

        return TypeCoverage(
            covered_types=covered_types,
            uncovered_types=uncovered,
            critical_gaps=critical_gaps,
            coverage_percentage=coverage_pct
        )

    def calculate_stat_distribution(
        self,
        party: List[Optional[PokemonData]]
    ) -> Dict[str, float]:
        active = [p for p in party if p is not None]
        if not active:
            return {"attack": 0.0, "defense": 0.0, "speed": 0.0, "special": 0.0}

        total_attack = sum(p.base_stats.attack for p in active)
        total_defense = sum(p.base_stats.defense for p in active)
        total_speed = sum(p.base_stats.speed for p in active)
        total_special = sum(p.base_stats.special for p in active)
        grand_total = total_attack + total_defense + total_speed + total_special

        if grand_total == 0:
            return {"attack": 0.25, "defense": 0.25, "speed": 0.25, "special": 0.25}

        return {
            "attack": total_attack / grand_total,
            "defense": total_defense / grand_total,
            "speed": total_speed / grand_total,
            "special": total_special / grand_total
        }

    def detect_move_overlap(
        self,
        party: List[Optional[PokemonData]]
    ) -> List[Dict[str, Any]]:
        move_owners: Dict[str, List[str]] = {}

        for pokemon in party:
            if pokemon is None:
                continue
            for move in pokemon.moves:
                if move.name not in move_owners:
                    move_owners[move.name] = []
                move_owners[move.name].append(pokemon.species_name())

        overlaps = []
        for move_name, owners in move_owners.items():
            if len(owners) > 1:
                overlaps.append({
                    "move_name": move_name,
                    "owners": owners,
                    "redundancy_level": len(owners),
                    "recommendation": f"Consider replacing {move_name} on some team members"
                })

        return overlaps

    def assign_roles(
        self,
        party: List[Optional[PokemonData]]
    ) -> Dict[str, str]:
        roles: Dict[str, str] = {}

        for pokemon in party:
            if pokemon is None:
                continue

            pokemon_id = pokemon.pokemon_id

            attack_ratio = pokemon.base_stats.attack / max(pokemon.base_stats.special, 1)
            speed_score = pokemon.base_stats.speed
            defense_score = pokemon.base_stats.hp + pokemon.base_stats.defense

            has_status_moves = any(m.category == MoveCategory.STATUS for m in pokemon.moves)
            has_utility = any(m.name.upper() in {"TOXIC", "THUNDER_WAVE", "WILL_O_WISP", "STUN_SPORE"} for m in pokemon.moves)

            if has_utility or has_status_moves:
                if defense_score > 150 and attack_ratio < 1.2:
                    roles[pokemon_id] = "support"
                else:
                    roles[pokemon_id] = "mixed"
            elif attack_ratio > 1.3 and speed_score > 70:
                roles[pokemon_id] = "sweeper"
            elif defense_score > 180 and attack_ratio > 0.8:
                roles[pokemon_id] = "tank"
            else:
                roles[pokemon_id] = "mixed"

        return roles

    def identify_boss_counters(
        self,
        boss_team: List[Dict[str, Any]],
        available_pokemon: List[PokemonData]
    ) -> List[Dict[str, Any]]:
        counters = []

        for boss_data in boss_team:
            boss_species = boss_data.get("species_id", "")
            boss_types = boss_data.get("types", [])
            boss_level = boss_data.get("level", 30)

            best_counter = None
            best_score = -1.0

            for candidate in available_pokemon:
                candidate_types = list(candidate.types)

                defensive_effectiveness: List[float] = []
                for boss_type_name in boss_types:
                    try:
                        boss_type = PokemonType(boss_type_name)
                        for cand_type in candidate_types:
                            if cand_type:
                                eff = self.type_chart.get_effectiveness(boss_type, [cand_type])
                                defensive_effectiveness.append(eff)
                    except ValueError:
                        continue

                if defensive_effectiveness:
                    def_score = max(defensive_effectiveness)
                    if def_score <= 0.5:
                        defensive_score = 3.0
                    elif def_score <= 1.0:
                        defensive_score = 2.0
                    else:
                        defensive_score = 1.0
                else:
                    defensive_score = 2.0

                offensive_score = 0.0
                for boss_type_name in boss_types:
                    try:
                        boss_type = PokemonType(boss_type_name)
                        for cand_type in candidate_types:
                            if cand_type:
                                eff = self.type_chart.get_effectiveness(cand_type, [boss_type])
                                if eff >= 2.0:
                                    offensive_score = 3.0
                                    break
                                elif eff >= 1.0:
                                    offensive_score = max(offensive_score, 2.0)
                    except ValueError:
                        continue

                level_score = min(candidate.level / boss_level, 1.5) if boss_level > 0 else 1.0

                overall_score = (defensive_score * 0.4 + offensive_score * 0.4 + level_score * 0.2)

                if overall_score > best_score:
                    best_score = overall_score
                    best_counter = candidate

            if best_counter:
                counters.append({
                    "for_boss": boss_species,
                    "counter_pokemon": best_counter.species_id,
                    "counter_name": best_counter.species_name(),
                    "score": best_score,
                    "confidence": min(best_score / 3.0, 1.0)
                })

        return counters

    def calculate_battle_usage_priorities(
        self,
        party: List[Optional[PokemonData]],
        enemy_party: List[Dict[str, Any]]
    ) -> List[Tuple[Optional[PokemonData], float]]:
        party_avg_level = 0.0
        active = [p for p in party if p is not None]
        if active:
            party_avg_level = sum(p.level for p in active) / len(active)

        priorities: List[Tuple[Optional[PokemonData], float]] = []

        for pokemon in party:
            if pokemon is None:
                priorities.append((None, 0.0))
                continue

            level_delta = pokemon.level - party_avg_level

            if level_delta > 5:
                base_priority = 30.0
            elif level_delta > 3:
                base_priority = 50.0
            elif level_delta > -3:
                base_priority = 80.0
            elif level_delta > -5:
                base_priority = 100.0
            else:
                base_priority = 130.0

            if not pokemon.can_battle():
                base_priority = 0.0
            else:
                for enemy in enemy_party:
                    enemy_types = enemy.get("types", [])
                    for move in pokemon.moves:
                        if move.category != MoveCategory.STATUS:
                            for enemy_type_name in enemy_types:
                                try:
                                    enemy_type = PokemonType(enemy_type_name)
                                    effectiveness = self.type_chart.get_effectiveness(
                                        move.move_type, [enemy_type]
                                    )
                                    if effectiveness >= 2.0:
                                        base_priority += 20.0
                                        break
                                    elif effectiveness <= 0.5:
                                        base_priority = max(20.0, base_priority - 15.0)
                                except ValueError:
                                    continue

            priorities.append((pokemon, max(0.0, min(150.0, base_priority))))

        return priorities

    def optimize_party_order(
        self,
        party: List[Optional[PokemonData]],
        battle_type: str
    ) -> List[PartySlot]:
        scored_party: List[PartySlot] = []

        for slot_index, pokemon in enumerate(party):
            if pokemon is None:
                scored_party.append(PartySlot(
                    slot_index=slot_index,
                    pokemon=None,
                    score=0.0,
                    recommended_role="empty",
                    suggested_moves=[]
                ))
                continue

            score = 0.0
            role = "mixed"

            if battle_type == "wild":
                speed_stat = pokemon.base_stats.speed
                best_move = pokemon.get_best_move()
                pp_sustainability = pokemon.total_pp_remaining() / 50.0

                score = (min(speed_stat / 100.0, 1.2) * 0.3 +
                        (1.0 if best_move and best_move.power >= 50 else 0.5) * 0.3 +
                        pp_sustainability * 0.2 +
                        (1.0 if pokemon.level < 50 else 0.7) * 0.2)
                role = "sweeper"

            elif battle_type == "trainer":
                score = pokemon.get_dps_potential() / 100.0 * 0.5
                score += (pokemon.base_stats.speed / 120.0) * 0.3
                if len([m for m in pokemon.moves if m.category != MoveCategory.STATUS]) >= 3:
                    score += 0.2
                role = "sweeper" if pokemon.base_stats.attack > pokemon.base_stats.defense else "mixed"

            elif battle_type == "gym":
                score = pokemon.defensive_stat() / 100.0 * 0.4
                score += (pokemon.base_stats.speed / 100.0) * 0.2
                hp_percent = pokemon.current_hp / max(pokemon.max_hp, 1)
                score *= max(0.5, hp_percent)
                role = "tank"

            elif battle_type == "elite4":
                versatility = len(set(m.category for m in pokemon.moves if m.category != MoveCategory.STATUS))
                score = (versatility / 3.0) * 0.5
                score += (pokemon.level / 60.0) * 0.3
                score += pokemon.get_dps_potential() / 150.0 * 0.2
                role = "mixed"

            elif battle_type == "legendary":
                score = (pokemon.defensive_stat() / 120.0) * 0.4
                has_status = any(m.category == MoveCategory.STATUS for m in pokemon.moves)
                score += 0.3 if has_status else 0.0
                score += (pokemon.current_hp / max(pokemon.max_hp, 1)) * 0.3
                role = "support" if has_status else "tank"

            else:
                score = pokemon.get_dps_potential() / 100.0

            health_multiplier = pokemon.current_hp / max(pokemon.max_hp, 1)
            score *= max(0.3, health_multiplier)

            scored_party.append(PartySlot(
                slot_index=slot_index,
                pokemon=pokemon,
                score=score,
                recommended_role=role,
                suggested_moves=[]
            ))

        scored_party.sort(key=lambda x: x.score, reverse=True)
        return scored_party

    def calculate_experience_rebalance_needed(
        self,
        party: List[Optional[PokemonData]]
    ) -> Dict[str, Any]:
        active = [p for p in party if p is not None]
        if len(active) < 2:
            return {
                "level_spread": 0,
                "needs_rebalance": False,
                "overleveled": [],
                "underleveled": [],
                "recommendations": []
            }

        avg_level = sum(p.level for p in active) / len(active)
        level_spread = max(p.level for p in active) - min(p.level for p in active)

        overleveled = [p for p in active if p.is_overleveled(avg_level)]
        underleveled = [p for p in active if p.is_underleveled(avg_level)]

        recommendations = []
        if level_spread > 10:
            recommendations.append("Severe level imbalance - prioritize training underleveled Pokemon")
        elif level_spread > 6:
            recommendations.append("Moderate level imbalance - consider adjusting battle rotation")

        return {
            "level_spread": level_spread,
            "needs_rebalance": level_spread > 6,
            "overleveled": [p.species_id for p in overleveled],
            "underleveled": [p.species_id for p in underleveled],
            "recommendations": recommendations
        }

    def analyze_team(
        self,
        party: List[Optional[PokemonData]],
        upcoming_battles: Optional[List[Dict[str, Any]]] = None
    ) -> TeamAnalysis:
        type_coverage = self.analyze_type_coverage(party, upcoming_battles)

        carry_scores: Dict[str, float] = {}
        for pokemon in party:
            if pokemon:
                score, _ = self.carry_calculator.calculate_carry_score(
                    pokemon, party, upcoming_battles
                )
                carry_scores[pokemon.pokemon_id] = score

        role_assignments = self.assign_roles(party)

        stat_distribution = self.calculate_stat_distribution(party)

        move_overlap = self.detect_move_overlap(party)

        recommendations = []
        if type_coverage.coverage_percentage < 0.6:
            recommendations.append("Improve type coverage - add Pokemon with missing types")
        if len(move_overlap) > 3:
            recommendations.append("Reduce move redundancy - replace duplicate moves")
        for gap in type_coverage.critical_gaps:
            recommendations.append(f"Critical gap: Add {gap.value} type coverage")

        team_score = sum(carry_scores.values()) / max(len(carry_scores), 1) if carry_scores else 0.0

        return TeamAnalysis(
            type_coverage=type_coverage,
            carry_scores=carry_scores,
            role_assignments=role_assignments,
            stat_distribution=stat_distribution,
            move_overlap=move_overlap,
            recommendations=recommendations,
            team_score=team_score
        )

    def suggest_party_changes(
        self,
        current_party: List[Optional[PokemonData]],
        box_pokemon: List[PokemonData],
        upcoming_content: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        suggestions: List[Dict[str, Any]] = []

        analysis = self.analyze_team(current_party)
        type_coverage = analysis.type_coverage

        for gap_type in type_coverage.critical_gaps:
            best_candidate = None
            best_score = -1.0

            for pokemon in box_pokemon:
                if gap_type in pokemon.types:
                    score, _ = self.carry_calculator.calculate_carry_score(
                        pokemon, current_party
                    )
                    if score > best_score:
                        best_score = score
                        best_candidate = pokemon

            if best_candidate:
                suggestions.append({
                    "action": "add",
                    "pokemon": best_candidate.species_id,
                    "reason": f"Provides needed {gap_type.value} type coverage",
                    "priority": "high"
                })

        for pokemon in current_party:
            if pokemon:
                score, _ = self.carry_calculator.calculate_carry_score(pokemon, current_party)
                bench_status = self.carry_calculator.should_bench(score)
                if bench_status == "immediate_bench":
                    for box_mon in box_pokemon:
                        box_score, _ = self.carry_calculator.calculate_carry_score(
                            box_mon, current_party
                        )
                        if box_score > score:
                            suggestions.append({
                                "action": "replace",
                                "remove": pokemon.species_id,
                                "add": box_mon.species_id,
                                "reason": f"{box_mon.species_id} has higher carry score ({box_score:.1f} vs {score:.1f})",
                                "priority": "medium"
                            })
                            break

        return suggestions


class EntityManager:
    """Main entity management class coordinating all sub-components."""

    def __init__(
        self,
        type_chart: Optional[TypeChart] = None,
        species_data: Optional[Dict[str, BaseStats]] = None,
        evolution_data: Optional[Dict[str, List[EvolutionCondition]]] = None,
        move_data: Optional[Dict[str, Dict[str, Any]]] = None
    ):
        chart = type_chart if type_chart is not None else TypeChart()
        data = species_data if species_data is not None else {}
        evo_data = evolution_data if evolution_data is not None else {}
        m_data = move_data if move_data is not None else {}
        
        self.carry_calculator = CarryScoreCalculator(chart, data)
        self.evolution_manager = EvolutionManager(evo_data, m_data, chart)
        self.team_optimizer = TeamCompositionOptimizer(
            self.carry_calculator, data, chart
        )
        self.team: Optional[Team] = None
        self.species_data = data

    def set_team(self, team: Team) -> None:
        self.team = team

    def update_pokemon(self, pokemon_id: str, updates: Dict[str, Any]) -> bool:
        if not self.team:
            return False

        for pokemon in self.team.active_pokemon():
            if pokemon.pokemon_id == pokemon_id:
                for key, value in updates.items():
                    if hasattr(pokemon, key):
                        setattr(pokemon, key, value)
                return True

        for pokemon in self.team.box:
            if pokemon.pokemon_id == pokemon_id:
                for key, value in updates.items():
                    if hasattr(pokemon, key):
                        setattr(pokemon, key, value)
                return True

        return False

    def get_pokemon(self, pokemon_id: str) -> Optional[PokemonData]:
        if not self.team:
            return None

        for pokemon in self.team.active_pokemon():
            if pokemon.pokemon_id == pokemon_id:
                return pokemon

        for pokemon in self.team.box:
            if pokemon.pokemon_id == pokemon_id:
                return pokemon

        return None

    def calculate_all_carry_scores(
        self,
        upcoming_battles: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, float]:
        if not self.team:
            return {}

        scores: Dict[str, float] = {}
        for pokemon in self.team.active_pokemon():
            score, _ = self.carry_calculator.calculate_carry_score(
                pokemon, self.team.party, upcoming_battles
            )
            scores[pokemon.pokemon_id] = score

        return scores

    def analyze_team(
        self,
        upcoming_battles: Optional[List[Dict[str, Any]]] = None
    ) -> TeamAnalysis:
        if not self.team:
            return TeamAnalysis(
                TypeCoverage(set(), set(), set(), 0.0),
                {}, {}, {}, [], [], 0.0
            )

        return self.team_optimizer.analyze_team(self.team.party, upcoming_battles)

    def get_evolution_recommendations(
        self,
        pokemon_id: str
    ) -> Dict[str, Any]:
        pokemon = self.get_pokemon(pokemon_id)
        if not pokemon:
            return {}

        return self.evolution_manager.get_evolution_readiness(pokemon)

    def get_party_optimization_suggestions(
        self,
        upcoming_content: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        if not self.team:
            return []

        return self.team_optimizer.suggest_party_changes(
            self.team.party, self.team.box, upcoming_content
        )

    def check_experience_balance(self) -> Dict[str, Any]:
        if not self.team:
            return {
                "level_spread": 0,
                "needs_rebalance": False,
                "overleveled": [],
                "underleveled": [],
                "recommendations": []
            }

        return self.team_optimizer.calculate_experience_rebalance_needed(self.team.party)

    def full_party_scan(self) -> Dict[str, Any]:
        if not self.team:
            return {"error": "No team set"}

        analysis = self.analyze_team()
        scores = self.calculate_all_carry_scores()
        exp_balance = self.check_experience_balance()

        return {
            "team_score": analysis.team_score,
            "type_coverage": analysis.type_coverage.to_dict(),
            "carry_scores": scores,
            "role_assignments": analysis.role_assignments,
            "experience_balance": exp_balance,
            "recommendations": analysis.recommendations,
            "mvp_candidates": sorted(scores.items(), key=lambda x: x[1], reverse=True)[:3]
        }

    def get_bench_status(self) -> List[Dict[str, Any]]:
        if not self.team:
            return []

        status_list: List[Dict[str, Any]] = []
        for pokemon in self.team.active_pokemon():
            score, breakdown = self.carry_calculator.calculate_carry_score(
                pokemon, self.team.party
            )
            bench_status = self.carry_calculator.should_bench(score)

            status_list.append({
                "pokemon_id": pokemon.pokemon_id,
                "species": pokemon.species_id,
                "nickname": pokemon.nickname,
                "score": score,
                "breakdown": breakdown.to_dict(),
                "bench_status": bench_status,
                "level": pokemon.level,
                "current_hp": pokemon.current_hp,
                "max_hp": pokemon.max_hp
            })

        status_list.sort(key=lambda x: x["score"], reverse=True)
        return status_list