# PTP-01X Chapter 6 Entity Design Document

## Design Version: 1.0
## Created: January 2026
## Status: DESIGN COMPLETE - IMPLEMENTATION PENDING

---

## 1. Module Overview

### 1.1 File Location
- **Primary Module**: `src/core/entity.py`
- **Test File**: `tests/test_entity.py`
- **Data Dependencies**: `src/core/data/species.json`, `src/core/data/moves.json`, `src/core/data/evolution.json`

### 1.2 Module Responsibilities
The Entity Management module handles all Pokemon data tracking, party optimization, and evolution decisions. It serves as the central source of truth for team composition and individual Pokemon value assessment.

### 1.3 Core Components
1. **PokemonData Model** - Data structures for Pokemon information
2. **CarryScoreCalculator** - Battle utility scoring system
3. **EvolutionManager** - Evolution timing and decision logic
4. **TeamCompositionOptimizer** - Party composition optimization

---

## 2. PokemonData Model

### 2.1 Design Rationale
The PokemonData model must capture all relevant information for AI decision-making while maintaining Gen 1 compatibility. Key considerations:
- IVs range from 0-15 (Gen 1)
- EVs range from 0-65535 per stat (Gen 1)
- Experience follows Gen 1 growth curves
- Status conditions affect battle decisions
- Move PP tracking for resource management

### 2.2 Data Classes

```python
@dataclass
class PokemonStats:
    """Individual stat values (calculated from base stats, IVs, EVs, level)"""
    hp: int
    attack: int
    defense: int
    speed: int
    special: int

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

@dataclass
class IndividualValues:
    """Gen 1 IVs (0-15 each)"""
    hp: int
    attack: int
    defense: int
    speed: int
    special: int

    def __post_init__(self):
        self.hp = max(0, min(15, self.hp))
        self.attack = max(0, min(15, self.attack))
        self.defense = max(0, min(15, self.defense))
        self.speed = max(0, min(15, self.speed))
        self.special = max(0, min(15, self.special))

@dataclass
class EffortValues:
    """Gen 1 EVs (0-65535 each, 0-510 total)"""
    hp: int
    attack: int
    defense: int
    speed: int
    special: int

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
        """Return PP as percentage of max"""
        if self.max_pp == 0:
            return 0.0
        return self.pp / self.max_pp

@dataclass
class Experience:
    """Experience tracking with growth curve support"""
    current: int
    to_next_level: int
    growth_rate: str  # "fast", "medium", "slow", "parabolic", "erratic", "fluctuating"

    def level_progress(self) -> float:
        """Return progress to next level as 0-1 float"""
        total = self.current + self.to_next_level
        if total == 0:
            return 0.0
        return self.current / total

@dataclass
class PokemonData:
    """
    Complete Pokemon data model.

    Attributes:
        pokemon_id: Unique identifier for this individual Pokemon
        species_id: Pokedex species identifier (e.g., "BULBASAUR")
        nickname: Player-assigned nickname (if any)
        level: Current level (1-100)
        current_hp: Current HP value
        max_hp: Maximum HP value (calculated)
        base_stats: Immutable species base stats
        ivs: Individual values (0-15)
        evs: Effort values (0-65535 per stat)
        moves: List of up to 4 learned moves
        status: Current status condition
        experience: Experience tracking
        types: Primary and secondary types
        happiness: Base happiness for evolution (0-255)
        is_shiny: Whether this is a shiny Pokemon
        catch_location: Where this Pokemon was caught
        catch_level: Level when caught
        date_caught: Timestamp of capture
        victories: Number of battles won
        defeats: Number of battles lost
        experience_gained: Total experience gained
        critical_battle_wins: Battles won with this Pokemon as MVP
        solo_gym_wins: Gym leaders defeated solo with this Pokemon
    """
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
    happiness: int
    is_shiny: bool
    catch_location: Optional[str]
    catch_level: int
    date_caught: Optional[str]
    victories: int
    defeats: int
    experience_gained: int
    critical_battle_wins: int
    solo_gym_wins: int

    def species_name(self) -> str:
        """Get display name (nickname or species name)"""
        if self.nickname:
            return self.nickname
        return self.base_stats.species_name

    def can_battle(self) -> bool:
        """Check if Pokemon is able to battle"""
        return self.current_hp > 0 and self.status != StatusCondition.FROZEN

    def has_move(self, move_name: str) -> bool:
        """Check if Pokemon has a specific move"""
        return any(m.name.lower() == move_name.lower() for m in self.moves)

    def get_move(self, move_name: str) -> Optional[Move]:
        """Get a specific move by name"""
        for move in self.moves:
            if move.name.lower() == move_name.lower():
                return move
        return None

    def total_pp_remaining(self) -> int:
        """Calculate total PP remaining across all moves"""
        return sum(move.pp for move in self.moves)

    def average_pp_remaining(self) -> float:
        """Calculate average PP percentage remaining"""
        if not self.moves:
            return 0.0
        return sum(move.pp_percentage() for move in self.moves) / len(self.moves)

    def offensive_stat(self) -> int:
        """Get attack or special based on best move category"""
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
        """Get defense or special based on move category usage"""
        if self.base_stats.defense >= self.base_stats.special:
            return self.base_stats.defense + self.ivs.defense + (self.evs.defense // 4)
        return self.base_stats.special + self.ivs.special + (self.evs.special // 4)
```

---

## 3. CarryScoreCalculator

### 3.1 Scoring Components

| Component | Weight | Range | Description |
|-----------|--------|-------|-------------|
| Level Relevance | 0.25 | 0-25 | How well Pokemon level matches upcoming content |
| Type Uniqueness | 0.30 | 0-30 | Unique typing contribution to team coverage |
| Move Coverage | 0.25 | 0-25 | Moves' type coverage and power |
| Stat Efficiency | 0.20 | 0-20 | How well stats are developed for species |

### 3.2 Interface Definition

```python
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

class CarryScoreCalculator:
    """
    Calculates battle utility scores for Pokemon.

    Integration Points:
    - Combat: Uses TypeChart for type effectiveness
    - Vision: Receives Pokemon identification for stats
    - GOAP: Provides scores for goal prioritization
    """

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
        type_chart: 'TypeChart',
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
        """
        Calculate score based on level relative to expected encounters.

        Ideal: Match expected level exactly (20 points)
        Good: Slightly overleveled (up to 3 levels) (18-22 points)
        Acceptable: Slightly underleveled (up to 2 levels) (15-18 points)
        Poor: Significantly underleveled (< 5 points)
        """
        pass  # Stub implementation

    def calculate_type_uniqueness(
        self,
        pokemon: PokemonData,
        current_party: List[Optional[PokemonData]],
        upcoming_battles: List[Dict[str, Any]]
    ) -> float:
        """
        Calculate score based on unique typing contribution.

        Points per unique type: 8
        Quality bonus: Type value multiplier × 4
        Boss weakness bonus: Up to 6 points
        """
        pass  # Stub implementation

    def calculate_move_coverage(
        self,
        pokemon: PokemonData,
        uncovered_enemy_types: Optional[List[PokemonType]] = None
    ) -> float:
        """
        Calculate score based on move type coverage.

        Super effective coverage: 3 points per type
        Neutral coverage: 0.5 points per type
        High power bonus (>90): 1 point
        STAB bonus: 1.2x multiplier
        """
        pass  # Stub implementation

    def calculate_stat_efficiency(
        self,
        pokemon: PokemonData,
        species_potential: BaseStats
    ) -> float:
        """
        Calculate score based on stat development vs species potential.

        Compares current DPS output to expected DPS for species/level.
        Penalizes underperformance with efficiency ratio.
        """
        pass  # Stub implementation

    def apply_rarity_modifier(self, pokemon: PokemonData) -> float:
        """Apply rarity multiplier based on species"""
        pass  # Stub implementation

    def apply_sentimental_modifier(self, pokemon: PokemonData) -> float:
        """
        Apply sentimental modifier based on battle history.

        Hero moments (critical wins): +1.0
        Solo gym leader: +2.0
        Shiny: +1.5
        Hatched from egg: +0.5
        Early game hero: +0.8
        """
        pass  # Stub implementation

    def calculate_carry_score(
        self,
        pokemon: PokemonData,
        current_party: List[Optional[PokemonData]],
        upcoming_battles: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[float, CarryScoreBreakdown]:
        """
        Calculate complete carry score with full breakdown.

        Returns:
            Tuple of (final_score, breakdown_details)
        """
        pass  # Stub implementation

    def should_bench(self, score: float) -> str:
        """
        Determine bench status based on score.

        > 70: Protect from bench
        50-70: Conditional bench
        < 35: Immediate bench
        < 20: HM slave candidate
        """
        pass  # Stub implementation
```

---

## 4. EvolutionManager

### 4.1 Evolution Conditions

| Condition Type | Examples | Trigger |
|---------------|----------|---------|
| Level-based | Most Pokemon | Reach specific level |
| Item-based | Vaporeon, Flareon, Jolteon | Use evolution stone |
| Trade-based | Machamp, Gengar, Alakazam | Trade with another player |
| Happiness-based | Eevee (Espeon/Umbreon) | High happiness + time of day |
| Location-based | Magmar (via trading) | Trading on specific platform |

### 4.2 Interface Definition

```python
@dataclass
class EvolutionCondition:
    """Evolution requirement specification"""
    condition_type: str  # "level", "item", "trade", "happiness", "location"
    required_value: Any  # Level number, item name, etc.
    target_species_id: str
    target_species_name: str
    learnable_moves: List[Dict[str, Any]]  # Moves lost/gained
    stat_changes: Dict[str, int]

@dataclass
class PreEvolutionMove:
    """Critical move available only before evolution"""
    move_id: str
    move_name: str
    learn_level: int
    evolution_level: int  # When evolution becomes available
    value_rating: str  # "STAB_POWERUP", "STRONG_STAB", "HIGH_CRIT", etc.
    power: int

@dataclass
class EvolutionDecision:
    """Evolution timing decision result"""
    decision: str  # "evolve_now", "wait_levels", "consider_waiting"
    wait_levels: Optional[int]
    reason: str
    expected_move: Optional[PreEvolutionMove]
    stat_improvement: float
    net_benefit_score: float

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
    "EEVEE": [],  # All evolutions are item-based
    "ABRA": [
        PreEvolutionMove(
            move_id="PSYCHIC", move_name="Psychic",
            learn_level=38, evolution_level=16,
            value_rating="PSYCHIC_STAB", power=90
        )
    ]
}

class EvolutionManager:
    """
    Manages evolution timing and decision logic.

    Integration Points:
    - Combat: Receives level-up notifications
    - Vision: Identifies evolution animations/triggers
    - Inventory: Checks for evolution stones
    - GOAP: Creates "Evolve Pokemon" goals
    """

    def __init__(
        self,
        evolution_data: Dict[str, List[EvolutionCondition]],
        move_data: Dict[str, Dict[str, Any]],
        type_chart: 'TypeChart'
    ):
        self.evolution_data = evolution_data
        self.move_data = move_data
        self.type_chart = type_chart

    def get_evolution_conditions(
        self,
        species_id: str,
        current_level: int
    ) -> List[EvolutionCondition]:
        """
        Get all possible evolution paths for a Pokemon.

        Returns empty list if no evolution available.
        """
        pass  # Stub implementation

    def check_evolution_available(
        self,
        pokemon: PokemonData
    ) -> Optional[EvolutionCondition]:
        """
        Check if Pokemon can evolve right now.

        Returns EvolutionCondition if available, None otherwise.
        """
        pass  # Stub implementation

    def evaluate_pre_evolution_moves(
        self,
        species_id: str,
        current_level: int,
        evolution_level: int
    ) -> Optional[PreEvolutionMove]:
        """
        Evaluate critical pre-evolution moves.

        Returns the highest value pre-evo move that would be missed.
        """
        pass  # Stub implementation

    def calculate_evolution_vs_wait_tradeoff(
        self,
        pokemon: PokemonData,
        evolution: EvolutionCondition,
        best_pre_evo_move: Optional[PreEvolutionMove]
    ) -> EvolutionDecision:
        """
        Calculate whether to evolve now or wait for moves.

        Evaluates:
        - Stat improvements from evolution
        - Type changes and their impact
        - Value of pre-evo moves
        - Experience investment cost of waiting
        """
        pass  # Stub implementation

    def calculate_move_value(
        self,
        move: Move,
        pokemon: PokemonData
    ) -> float:
        """
        Calculate the strategic value of learning a move.

        Considers:
        - Type effectiveness
        - Power relative to current moves
        - STAB potential
        - Coverage gaps filled
        """
        pass  # Stub implementation

    def should_use_evolution_item(
        self,
        pokemon: PokemonData,
        item_name: str,
        team_needs: Dict[str, Any]
    ) -> bool:
        """
        Determine if evolution stone should be used.

        Factors:
        - Team type coverage needs
        - Pokemon's potential in evolved form
        - Opportunity cost of item
        """
        pass  # Stub implementation

    def get_evolution_readiness(
        self,
        pokemon: PokemonData
    ) -> Dict[str, Any]:
        """
        Get comprehensive evolution status for a Pokemon.

        Returns:
        - current_level
        - evolution_available: bool
        - evolution_conditions: List[EvolutionCondition]
        - critical_pre_evo_moves: List[PreEvolutionMove]
        - recommended_action: str
        - wait_justification: Optional[str]
        """
        pass  # Stub implementation
```

---

## 5. TeamCompositionOptimizer

### 5.1 Role Definitions

| Role | Description | Ideal Stats | Example |
|------|-------------|-------------|---------|
| Sweeper | High damage output | High Atk/Spd | Charizard, Alakazam |
| Tank | High durability | High HP/Def | Blastoise, Onix |
| Support | Status/utility | Balanced + utility moves | Jigglypuff, Venonat |
| Utility | HM slave + field use | Any | Farfetch'd, Graveler |
| Mixed | Balance of offense/defense | Balanced stats | Gyarados, Snorlax |
| Counter | Type-specific counter | Type advantage | Starmie vs. Dragon types |

### 5.2 Interface Definition

```python
@dataclass
class TypeCoverage:
    """Type coverage analysis result"""
    covered_types: Set[PokemonType]
    uncovered_types: Set[PokemonType]
    critical_gaps: Set[PokemonType]  # Types needed for upcoming content
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
    carry_scores: Dict[str, float]  # pokemon_id -> score
    role_assignments: Dict[str, str]  # pokemon_id -> role
    stat_distribution: Dict[str, float]  # "attack", "defense", "speed", "special"
    move_overlap: List[Dict[str, Any]]  # Moves shared by multiple Pokemon
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

class TeamCompositionOptimizer:
    """
    Optimizes team composition for current and upcoming content.

    Integration Points:
    - GOAP: Creates "Optimize Team" goals
    - Combat: Uses analysis for switch decisions
    - Vision: Receives Pokemon identification updates
    - Navigation: Considers grinding route requirements
    """

    def __init__(
        self,
        carry_calculator: CarryScoreCalculator,
        species_data: Dict[str, BaseStats],
        type_chart: 'TypeChart'
    ):
        self.carry_calculator = carry_calculator
        self.species_data = species_data
        self.type_chart = type_chart

    def analyze_type_coverage(
        self,
        party: List[Optional[PokemonData]],
        upcoming_battles: Optional[List[Dict[str, Any]]] = None
    ) -> TypeCoverage:
        """
        Analyze type coverage for current party.

        Identifies:
        - Types the party can hit super-effectively
        - Coverage gaps in the team
        - Critical gaps for upcoming boss battles
        """
        pass  # Stub implementation

    def calculate_stat_distribution(
        self,
        party: List[Optional[PokemonData]]
    ) -> Dict[str, float]:
        """
        Calculate stat distribution across team.

        Returns distribution percentages for Atk, Def, Spd, Special.
        Ideal: Balanced distribution with emphasis on offensive stats.
        """
        pass  # Stub implementation

    def detect_move_overlap(
        self,
        party: List[Optional[PokemonData]]
    ) -> List[Dict[str, Any]]:
        """
        Detect redundant moves across team.

        Returns list of overlapping moves with suggestion to replace.
        """
        pass  # Stub implementation

    def assign_roles(
        self,
        party: List[Optional[PokemonData]]
    ) -> Dict[str, str]:
        """
        Assign optimal roles to each Pokemon.

        Roles: sweeper, tank, support, utility, mixed, counter
        """
        pass  # Stub implementation

    def identify_boss_counters(
        self,
        boss_team: List[Dict[str, Any]],
        available_pokemon: List[PokemonData]
    ) -> List[Dict[str, Any]]:
        """
        Identify best counters for upcoming boss.

        Returns list of (counter_for, counter_pokemon, score, confidence).
        """
        pass  # Stub implementation

    def calculate_battle_usage_priorities(
        self,
        party: List[Optional[PokemonData]],
        enemy_party: List[Dict[str, Any]]
    ) -> List[Tuple[Optional[PokemonData], float]]:
        """
        Calculate usage priority for each Pokemon in battle.

        Lower score = bench, Higher score = lead with.
        Factors:
        - Level balance vs party average
        - Type effectiveness vs enemy
        - HP status
        - Experience needs
        """
        pass  # Stub implementation

    def optimize_party_order(
        self,
        party: List[Optional[PokemonData]],
        battle_type: str
    ) -> List[PartySlot]:
        """
        Optimize party order for upcoming battle type.

        Battle types: "wild", "trainer", "gym", "elite4", "legendary"
        """
        pass  # Stub implementation

    def calculate_experience_rebalance_needed(
        self,
        party: List[Optional[PokemonData]]
    ) -> Dict[str, Any]:
        """
        Check if XP redistribution is needed.

        Returns:
        - level_spread: max - min level
        - needs_rebalance: bool
        - overleveled: List[PokemonData]
        - underleveled: List[PokemonData]
        - recommendations: List[str]
        """
        pass  # Stub implementation

    def analyze_team(
        self,
        party: List[Optional[PokemonData]],
        upcoming_battles: Optional[List[Dict[str, Any]]] = None
    ) -> TeamAnalysis:
        """
        Complete team analysis with all metrics.

        Returns comprehensive analysis for GOAP planning.
        """
        pass  # Stub implementation

    def suggest_party_changes(
        self,
        current_party: List[Optional[PokemonData]],
        box_pokemon: List[PokemonData],
        upcoming_content: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Suggest specific party changes from PC box.

        Returns list of (remove, add, reason) tuples.
        """
        pass  # Stub implementation
```

---

## 6. Team Data Model

```python
@dataclass
class Team:
    """
    Complete team data structure for party management.

    Attributes:
        team_id: Unique identifier for this team
        name: Team nickname (if any)
        party: List of 6 PokemonData (None for empty slots)
        box: List of additional Pokemon in PC
        total_battles: Total battles fought
        total_victories: Total wins
        total_defeats: Total losses
        last_analysis: Timestamp of last team analysis
        avg_level: Average party level
        level_spread: Max - min level
    """
    team_id: str
    name: Optional[str]
    party: List[Optional[PokemonData]]
    box: List[PokemonData]
    total_battles: int
    total_victories: int
    total_defeats: int
    last_analysis: Optional[str]
    avg_level: float
    level_spread: int

    def __post_init__(self):
        if len(self.party) != 6:
            raise ValueError("Party must have exactly 6 slots")
        # Pad party to 6 if needed
        while len(self.party) < 6:
            self.party.append(None)

    def active_pokemon(self) -> List[PokemonData]:
        """Get all non-None Pokemon in party"""
        return [p for p in self.party if p is not None]

    def active_count(self) -> int:
        """Count of non-empty party slots"""
        return len(self.active_pokemon())

    def can_battle(self) -> bool:
        """Check if team has at least one battle-ready Pokemon"""
        return any(p.can_battle() for p in self.active_pokemon())

    def battle_ready_count(self) -> int:
        """Count of Pokemon able to battle"""
        return sum(1 for p in self.active_pokemon() if p.can_battle())

    def average_level(self) -> float:
        """Calculate average level of active Pokemon"""
        active = self.active_pokemon()
        if not active:
            return 0.0
        return sum(p.level for p in active) / len(active)

    def level_spread(self) -> int:
        """Calculate level spread (max - min)"""
        active = self.active_pokemon()
        if len(active) < 2:
            return 0
        return max(p.level for p in active) - min(p.level for p in active)

    def get_lead_pokemon(self) -> Optional[PokemonData]:
        """Get the lead Pokemon (first non-None)"""
        for p in self.party:
            if p is not None:
                return p
        return None

    def has_hm_user(self) -> bool:
        """Check if team has a Pokemon that can use HMs"""
        hm_moves = {"CUT", "FLY", "SURF", "STRENGTH", "FLASH", "WHIRLPOOL", "WATERFALL"}
        for p in self.active_pokemon():
            for move in p.moves:
                if move.name.upper() in hm_moves:
                    return True
        return False

    def get_hm_users(self) -> Dict[str, List[PokemonData]]:
        """Get mapping of HM moves to Pokemon that can use them"""
        hm_moves = {"CUT", "FLY", "SURF", "STRENGTH", "FLASH", "WHIRLPOOL", "WATERFALL"}
        hm_users: Dict[str, List[PokemonData]] = {hm: [] for hm in hm_moves}

        for p in self.active_pokemon():
            for move in p.moves:
                if move.name.upper() in hm_moves:
                    hm_users[move.name.upper()].append(p)

        return {k: v for k, v in hm_users.items() if v}
```

---

## 7. Integration Points

### 7.1 Combat Integration
```python
# From combat module
from src.core.combat import TypeChart, MoveCategory

# Entity provides:
- Pokemon type information for effectiveness checks
- Current stats for damage calculation
- Move lists for move selection
- Status conditions for battle logic
```

### 7.2 GOAP Integration
```python
# From goap module
from src.core.goap import Goal, Action

# Entity provides:
- Carry scores for goal prioritization
- Team analysis for "Optimize Team" goals
- Evolution readiness for "Evolve Pokemon" goals
- Experience needs for "Train Pokemon" goals
```

### 7.3 Vision Integration
```python
# From vision module
from src.vision.sprite import SpriteRecognizer

# Entity receives:
- Pokemon species identification
- Level indicator reading
- Status condition detection
- Move list parsing
- Evolution trigger detection
```

### 7.4 Navigation Integration
```python
# From navigation module
from src.core.navigation import AreaManager

# Entity provides:
- HM user requirements for route planning
- Type coverage needs for area selection
- Level requirements for grinding routes
```

---

## 8. Performance Specifications

### 8.1 Timing Requirements

| Operation | Target Time | Frequency |
|-----------|-------------|-----------|
| Full party scan | 80ms | On level change |
| Carry score calc (6 Pokemon) | 30ms | Per optimization cycle |
| Evolution check | 15ms | Per level up |
| Type coverage analysis | 10ms | Per optimization |
| Party reorder | 20ms | When needed |

### 8.2 Memory Budget

| Component | Memory |
|-----------|--------|
| Party cache (6 Pokemon) | 12KB |
| Species data | 50KB |
| Evolution data | 20KB |
| Type chart | 10KB |
| Carry score cache | 5KB |
| **Total** | **<100KB** |

---

## 9. Implementation Order

### Phase 1: Data Models (Priority 1)
1. Implement PokemonData with all sub-classes
2. Implement Team dataclass
3. Create data loading utilities

### Phase 2: Carry Score Calculator (Priority 2)
1. Implement scoring components (level, type, moves, stats)
2. Implement rarity modifiers
3. Implement sentimental modifiers
4. Create scoring breakdown for debugging

### Phase 3: Evolution Manager (Priority 3)
1. Implement evolution condition detection
2. Implement pre-evo move evaluation
3. Implement tradeoff calculation
4. Create evolution readiness assessment

### Phase 4: Team Optimization (Priority 4)
1. Implement type coverage analysis
2. Implement role assignment
3. Implement move overlap detection
4. Implement party order optimization

### Phase 5: Integration (Priority 5)
1. Integrate with Combat for stat queries
2. Integrate with GOAP for goal creation
3. Integrate with Vision for Pokemon updates
4. Create unit tests (target: 85% coverage)

---

## 10. Known Dependencies

### 10.1 On Other NOT STARTED Items
- **None** - Entity module has no hard dependencies on other NOT STARTED items

### 10.2 On COMPLETED Items
- **2.1 Hierarchical State Machine**: State change triggers for party analysis
- **2.2 Vision & Perception**: Pokemon identification and status detection
- **2.3 Tactical Combat Heuristics**: TypeChart for effectiveness calculations

### 10.3 Data Dependencies
- `src/core/data/species.json` - Base stats for all species
- `src/core/data/moves.json` - Move data for coverage analysis
- `src/core/data/evolution.json` - Evolution conditions and paths

---

## 11. Acceptance Criteria

1. **Pokemon data tracking 100% accurate**
   - All stat calculations match Gen 1 formulas
   - Experience tracking precise to 1 XP
   - Move PP management accurate

2. **Evolution timing optimal**
   - No critical moves missed (>95% success rate)
   - Stat improvements properly evaluated
   - Item usage decisions optimal

3. **Team type coverage > 90%**
   - Analysis covers all 18 types
   - Recommendations fill critical gaps
   - Boss counters properly identified

4. **Carry score correlation with battle success**
   - Score > 70: Rarely benched
   - Score < 35: Frequently benched
   - Correlation coefficient > 0.7 with win rate

---

**Document Version:** 1.0
**Last Updated:** January 2026
**Status:** Ready for Implementation