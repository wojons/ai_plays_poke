# PTP-01X Chapter 6: Entity Management & Party Optimization

**Version:** 1.0  
**Author:** AI Architect  
**Status:** Technical Specification (Implementable)  
**Dependencies:** Chapter 2 (Memory Layer), Chapter 5 (Combat System)

---

## Executive Summary

The Entity Management layer is the **cognitive bridge** between raw memory addresses and strategic decision-making. It transforms a collection of Pokemon into a championship team through quantified optimization algorithms that balance:

- **Combat Efficiency**: DPS per level investment
- **Type Coverage**: Strategic breadth across 15 Gen 1 types
- **Experience Funneling**: Anti-overleveling distribution
- **Evolution Timing**: Move acquisition vs power spike tradeoffs
- **HM Management**: Permanent moveset opportunity costs

This layer implements the AI's "personality" - deterministic yet adaptive behavior that avoids both generic optimization and sentimental hoarding.

---

## 1. Core Philosophical Framework

### 1.1 The Carry vs Bench Decision Matrix

Every Pokemon is evaluated on a **Carry Score** (0-100) with four weighted components:

```python
Carry Score = (Level Relevance × 0.25) + 
              (Type Uniqueness × 0.30) + 
              (Move Coverage × 0.25) + 
              (Stat Efficiency × 0.20) × 
              Rarity Multiplier
```

**Bench Thresholds:**
- **< 35**: Immediate bench (unless party size < 3)
- **35-50**: Conditional bench (if better alternative available)
- **> 50**: Protected from benching (strategic reserve)

### 1.2 Psychological Bias Quantification

The system codifies three human cognitive biases into deterministic rules:

#### Conservatism Bias (Risk Aversion)
```python
def conservatism_penalty(pokemon, party_avg_level):
    """Penalize benching Pokemon > 5 levels above average"""
    if pokemon.level > party_avg_level + 5:
        return -15  # Significant penalty for benching carries
    return 0
```

#### Optimization Drive (Ruthless Efficiency)
```python
def optimization_bonus(pokemon, upcoming_boss):
    """Bonus for countering next major encounter"""
    boss_weakness = TYPE_CHART[upcoming_boss.primary_type][pokemon.types[0]]
    if boss_weakness == 2.0:
        return +20  # Strong counter
    if boss_weakness == 0.5:
        return -10  # Weak matchup
    return 0
```

#### Attachment Heuristic (Sentimental Value)
```python
def attachment_modifier(pokemon):
    """Mild bonus for Pokemon that secured early victories"""
    if pokemon.kills > 10 and pokemon.level < 25:
        return +5  # "Hero" bonus, diminishes over time
    return 0
```

---

## 2. Carry Score Algorithm Implementation

### 2.1 Level Relevance Component (0-25 points)

```python
def calculate_level_relevance(self, pokemon):
    """
    Scales with expected encounter level for current game progress
    Uses pre-calculated difficulty curves from route analysis
    """
    expected_level = self._get_expected_encounter_level()
    level_ratio = pokemon.level / expected_level
    
    # Diminishing returns after 1.5x expected level
    if level_ratio > 1.5:
        level_ratio = 1.5 + (level_ratio - 1.5) * 0.3
    
    return min(level_ratio, 2.0) * 25

def _get_expected_encounter_level(self):
    """
    Returns expected trainer/wild level based on game flags
    $D772: Gym badges (bitfield)
    $D5A7: Current map ID
    """
    badges = self.memory.read_byte(0xD772)
    num_badges = bin(badges).count('1')
    
    # Level curve: Route 1 (~L5) → Elite Four (~L55)
    return 5 + (num_badges * 10) + (self.cycle_count // 1000)
```

### 2.2 Type Uniqueness Component (0-30 points)

```python
def calculate_type_uniqueness(self, pokemon):
    """
    Quantifies type coverage expansion
    Gen 1 has 15 effective types (Dragon/Ghost/Normal rarely matter)
    """
    # Get all types currently in party
    party_types = set()
    for p in self.party:
        if p and p != pokemon:  # Exclude self from calculation
            party_types.update(p.types)
    
    pokemon_types = set(pokemon.types)
    unique_types = pokemon_types - party_types
    
    # Coverage quality matters: Electric > Normal for example
    quality_score = sum(TYPE_COVERAGE_QUALITY[t] for t in unique_types)
    
    return (len(unique_types) / 3) * 30 * (quality_score / len(unique_types) if unique_types else 1)

# Type coverage quality (higher = more valuable)
TYPE_COVERAGE_QUALITY = {
    0x00: 0.8,  # Normal (neutral, replaceable)
    0x01: 1.2,  # Fighting (covers Normal, Ice, Rock)
    0x02: 0.9,  # Flying (good mobility, common)
    0x03: 1.1,  # Poison (neutral)
    0x04: 1.3,  # Ground (covers Electric, Fire, Poison)
    0x05: 0.7,  # Rock (slow, many weaknesses)
    0x06: 1.0,  # Bug (weak in Gen 1)
    0x07: 1.4,  # Ghost (counters Psychic, rare)
    0x08: 1.5,  # Fire (strong offensive)
    0x09: 1.6,  # Water (versatile, HM utility)
    0x0A: 1.4,  # Grass (covers Water, Ground, Rock)
    0x0B: 1.7,  # Electric (fast, no weaknesses in Gen 1)
    0x0C: 1.3,  # Psychic (dominant type in Gen 1)
    0x0D: 0.6,  # Ice (late game, niche)
    0x0E: 1.5,  # Dragon (rare, Dragonite powerful)
}
```

### 2.3 Move Coverage Component (0-25 points)

```python
def calculate_move_coverage(self, pokemon):
    """
    Evaluates type coverage of moveset vs remaining types
    Higher score for covering weaknesses in current party
    """
    # Get types NOT covered by party
    all_types = set(range(15))
    party_types = {t for p in self.party if p for t in p.types}
    uncovered_types = all_types - party_types
    
    # Get move types
    move_types = []
    for move_id in pokemon.moves:
        if move_id != 0:
            move_data = MOVE_DATA[move_id]
            move_types.append(move_data['type'])
    
    # Calculate coverage of uncovered types
    coverage_score = 0
    for target_type in uncovered_types:
        for move_type in move_types:
            effectiveness = TYPE_CHART[move_type][target_type]
            if effectiveness >= 2.0:
                coverage_score += 2.0
            elif effectiveness == 1.0:
                coverage_score += 0.5
    
    return min(coverage_score / 10.0, 1.0) * 25
```

### 2.4 Stat Efficiency Component (0-20 points)

```python
def calculate_stat_efficiency(self, pokemon):
    """
    DPS per level investment
    Prevents over-leveling underperformers
    """
    # Calculate current DPS potential
    best_move_power = max((MOVE_DATA[m]['power'] for m in pokemon.moves if m != 0), default=40)
    
    # Effective attack (accounting for stat modifiers)
    attack_stat = pokemon.attack * (1 + pokemon.attack_modifier / 2)
    speed_stat = pokemon.speed * (1 + pokemon.speed_modifier / 2)
    
    # Speed matters: higher speed = more turns
    dps_estimate = (best_move_power * attack_stat) / 100 * (speed_stat / 100)
    
    # Expected DPS for this Pokemon at this level (species-specific curve)
    species_base = SPECIES_BASE_STATS[pokemon.species]
    expected_dps = (species_base['attack'] + pokemon.level * 2) * 1.2
    
    efficiency = dps_estimate / expected_dps
    
    # Penalize if significantly below curve
    if efficiency < 0.7:
        return efficiency * 20 * 0.5  # 50% penalty
    
    return min(efficiency, 1.5) * 20  # Cap at 150%
```

### 2.5 Rarity Multiplier (0.7x to 1.3x)

```python
RARITY_MULTIPLIERS = {
    # Legendary/Unique (1.3x)
    0x96: 1.3,  # Mewtwo
    0x91: 1.3,  # Mew
    0x71: 1.3,  # Dragonite (rare evolution)
    
    # Rare/Valuable (1.2x)
    0x70: 1.2,  # Dragonair
    0x6F: 1.2,  # Dratini
    0x73: 1.2,  # Mewtwo (alternate ID)
    
    # Starters (1.15x) - sentimental + power
    0x99: 1.15, # Bulbasaur
    0x09: 1.15, # Ivysaur
    0x0A: 1.15, # Venusaur
    0xB0: 1.15, # Charmander
    0x0B: 1.15, # Charmeleon
    0x0C: 1.15, # Charizard
    0xB1: 1.15, # Squirtle
    0x0D: 1.15, # Wartortle
    0x0E: 1.15, # Blastoise
    
    # Common/Replaceable (0.7x-0.9x)
    0x43: 0.7,  # Pidgey
    0x0F: 0.7,  # Pidgeotto
    0x14: 0.7,  # Pidgeot
    0x54: 0.8,  # Rattata
    0x1A: 0.8,  # Raticate
    0x60: 0.8,  # Spearow
    0x17: 0.8,  # Fearow
    
    # Default: 1.0x (most Pokemon)
}

def get_rarity_multiplier(self, species_id):
    return RARITY_MULTIPLIERS.get(species_id, 1.0)
```

---

## 3. Memory Interface: Party Scanning

### 3.1 WRAM Party Structure

Pokemon data begins at **$D16B** and each slot occupies **44 bytes** (0x2C):

```
$D16B + (slot × 0x2C):
+0x00: Species ID
+0x01: Current HP (word)
+0x03: Level
+0x04: Status condition
+0x05: Type 1
+0x06: Type 2
+0x08: Move 1 ID
+0x09: Move 2 ID
+0x0A: Move 3 ID
+0x0B: Move 4 ID
+0x0D: Attack stat
+0x0E: Defense stat
+0x0F: Speed stat
+0x10: Special stat
+0x11: Attack modifier (stages -6 to +6)
+0x12: Defense modifier
+0x13: Speed modifier
+0x14: Special modifier
+0x15: Accuracy modifier
+0x16: Evasion modifier
+0x17: HP EV
+0x18: Attack EV
+0x19: Defense EV
+0x1A: Speed EV
+0x1B: Special EV
+0x1C: IV data (2 bytes)
+0x1E: Move 1 PP
+0x1F: Move 2 PP
+0x20: Move 3 PP
+0x21: Move 4 PP
+0x22: Level progress (current exp - last level threshold)
+0x23: Max HP (word)
+0x25: Unknown
+0x26: Unknown
+0x27: Unknown
+0x28: Unknown
+0x29: Unknown
+0x2A: Unknown
+0x2B: Unknown
```

### 3.2 Party Scanning Implementation

```python
class PartyManager:
    def __init__(self, memory_interface, logger):
        self.memory = memory_interface
        self.logger = logger
        self.party = [None] * 6
        self.bench_cache = []
        self.hm_mules = set()
        self.party_count = 0
        self.last_scan_cycle = 0
        
    async def scan_party(self, force=False):
        """
        Full party rescan on invalidation triggers
        Only scans if $D163 (party count) changed or force=True
        """
        current_count = await self.memory.read_byte(0xD163)
        
        if current_count == self.party_count and not force:
            return  # No changes, skip rescan
        
        self.party_count = current_count
        self.logger.info(f"Party scan triggered: {current_count} Pokemon")
        
        # Scan each party slot
        for slot in range(current_count):
            try:
                pokemon = await self._extract_pokemon(slot)
                if pokemon:
                    self.party[slot] = pokemon
                    
                    self.logger.trace(
                        f"Slot {slot}: {pokemon.species} L{pokemon.level} "
                        f"HP:{pokemon.current_hp}/{pokemon.max_hp} "
                        f"Types:{pokemon.types}"
                    )
            except Exception as e:
                self.logger.error(f"Failed to extract Pokemon from slot {slot}: {e}")
        
        # Clear remaining slots
        for slot in range(current_count, 6):
            self.party[slot] = None
        
        # Recalculate strategies
        await self._recalculate_carry_scores()
        await self._identify_hm_mules()
        
        self.last_scan_cycle = self.memory.get_cycle_count()
    
    async def _extract_pokemon(self, slot):
        """Extract full Pokemon entity from WRAM"""
        base_ptr = 0xD16B + (slot * 0x2C)
        
        # Basic validation
        species_id = await self.memory.read_byte(base_ptr + 0x00)
        if species_id == 0 or species_id > 0xFF:
            return None
        
        # Read current HP (word)
        current_hp = await self.memory.read_word(base_ptr + 0x01)
        if current_hp == 0:
            # Pokemon is fainted or not present
            return None
        
        # Extract all fields
        pokemon = PokemonEntity(
            species_id=species_id,
            species_name=SPECIES_NAMES.get(species_id, f"Unknown({species_id})"),
            current_hp=current_hp,
            max_hp=await self.memory.read_word(base_ptr + 0x23),
            level=await self.memory.read_byte(base_ptr + 0x03),
            status=await self.memory.read_byte(base_ptr + 0x04),
            types=[
                await self.memory.read_byte(base_ptr + 0x05),
                await self.memory.read_byte(base_ptr + 0x06)
            ],
            moves=[
                await self.memory.read_byte(base_ptr + 0x08),
                await self.memory.read_byte(base_ptr + 0x09),
                await self.memory.read_byte(base_ptr + 0x0A),
                await self.memory.read_byte(base_ptr + 0x0B)
            ],
            pp=[
                await self.memory.read_byte(base_ptr + 0x1E),
                await self.memory.read_byte(base_ptr + 0x1F),
                await self.memory.read_byte(base_ptr + 0x20),
                await self.memory.read_byte(base_ptr + 0x21)
            ],
            # Stats
            attack=await self.memory.read_byte(base_ptr + 0x0D),
            defense=await self.memory.read_byte(base_ptr + 0x0E),
            speed=await self.memory.read_byte(base_ptr + 0x0F),
            special=await self.memory.read_byte(base_ptr + 0x10),
            # Stat modifiers (-6 to +6, stored as 0-12)
            attack_modifier=await self.memory.read_byte(base_ptr + 0x11) - 6,
            defense_modifier=await self.memory.read_byte(base_ptr + 0x12) - 6,
            speed_modifier=await self.memory.read_byte(base_ptr + 0x13) - 6,
            special_modifier=await self.memory.read_byte(base_ptr + 0x14) - 6,
            accuracy_modifier=await self.memory.read_byte(base_ptr + 0x15) - 6,
            evasion_modifier=await self.memory.read_byte(base_ptr + 0x16) - 6,
            # EVs (effort values)
            hp_ev=await self.memory.read_byte(base_ptr + 0x17),
            attack_ev=await self.memory.read_byte(base_ptr + 0x18),
            defense_ev=await self.memory.read_byte(base_ptr + 0x19),
            speed_ev=await self.memory.read_byte(base_ptr + 0x1A),
            special_ev=await self.memory.read_byte(base_ptr + 0x1B),
            # Other data
            ot_id=await self.memory.read_word(base_ptr + 0x1C),  # Trainer ID
            level_progress=await self.memory.read_byte(base_ptr + 0x22),
            # Calculate derived stats
            exp_to_next=self._calculate_exp_to_next(species_id, await self.memory.read_byte(base_ptr + 0x03))
        )
        
        return pokemon
    
    def _calculate_exp_to_next(self, species_id, level):
        """Calculate experience needed for next level"""
        growth_rate = SPECIES_GROWTH_RATES.get(species_id, 'medium')
        
        if growth_rate == 'fast':
            return int(0.8 * (level ** 3))
        elif growth_rate == 'slow':
            return int(1.2 * (level ** 3))
        else:
            return int(1.0 * (level ** 3))
```

### 3.3 Pokemon Entity Dataclass

```python
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class PokemonEntity:
    """Complete Pokemon data structure with derived stats"""
    
    # Identity
    species_id: int
    species_name: str
    
    # Vitals
    current_hp: int
    max_hp: int
    level: int
    status: int  # Bitmask: 0x01=Asleep, 0x02=Poisoned, 0x04=Burned, 0x08=Frozen, 0x10=Paralyzed
    
    # Types (0-14)
    types: List[int]
    
    # Moveset
    moves: List[int]  # 4 move slots
    pp: List[int]     # PP remaining for each move
    
    # Stats
    attack: int
    defense: int
    speed: int
    special: int
    
    # Stat modifiers (-6 to +6)
    attack_modifier: int
    defense_modifier: int
    speed_modifier: int
    special_modifier: int
    accuracy_modifier: int
    evasion_modifier: int
    
    # EVs (0-65535)
    hp_ev: int
    attack_ev: int
    defense_ev: int
    speed_ev: int
    special_ev: int
    
    # Other
    ot_id: int
    level_progress: int
    exp_to_next: int
    
    # Derived/cached values
    _carry_score: Optional[float] = None
    _dps_estimate: Optional[float] = None
    _type_coverage: Optional[set] = None
    
    @property
    def is_fainted(self) -> bool:
        return self.current_hp == 0
    
    @property
    def is_alive(self) -> bool:
        return self.current_hp > 0
    
    @property
    def health_percentage(self) -> float:
        return (self.current_hp / self.max_hp) * 100 if self.max_hp > 0 else 0
    
    @property
    def status_name(self) -> str:
        """Human-readable status"""
        status_map = {
            0x01: "Asleep",
            0x02: "Poisoned",
            0x04: "Burned",
            0x08: "Frozen",
            0x10: "Paralyzed"
        }
        
        statuses = [name for mask, name in status_map.items() if self.status & mask]
        return ", ".join(statuses) if statuses else "Healthy"
    
    def calculate_dps(self, move_id: int) -> float:
        """Calculate DPS for a specific move"""
        if move_id == 0:
            return 0
        
        move_data = MOVE_DATA[move_id]
        
        # Account for PP exhaustion
        move_index = self.moves.index(move_id)
        if self.pp[move_index] == 0:
            return 0
        
        # Base damage calculation
        if move_data['power'] == 0:
            # Status move, estimate utility
            return 5  # Baseline utility
        
        # Use appropriate attack stat
        if move_data['category'] == 'physical':
            attack = self.attack * (1 + self.attack_modifier / 2)
        else:
            attack = self.special * (1 + self.special_modifier / 2)
        
        # Speed factor (more turns = more DPS)
        speed = self.speed * (1 + self.speed_modifier / 2)
        speed_factor = (speed / 100) ** 0.5  # Diminishing returns
        
        return (move_data['power'] * attack / 100) * speed_factor
    
    def get_best_move(self) -> tuple:
        """Returns (move_id, dps) for best available move"""
        best_move = 0
        best_dps = 0
        
        for i, move_id in enumerate(self.moves):
            if move_id == 0 or self.pp[i] == 0:
                continue
            
            dps = self.calculate_dps(move_id)
            if dps > best_dps:
                best_dps = dps
                best_move = move_id
        
        return best_move, best_dps
```

---

## 4. Evolution Management

### 4.1 Evolution Timing Optimizer

**Problem**: Some Pokemon learn moves faster unevolved (e.g., Bulbasaur learns Solar Beam at L36, Venusaur at L65).

```python
class EvolutionManager:
    def __init__(self, party_manager):
        self.party = party_manager
        self.logger = party_manager.logger
    
    async def should_evolve_now(self, pokemon):
        """
        Determine if Pokemon should evolve at current level
        Returns: (should_evolve: bool, reason: str)
        """
        species_data = SPECIES_DATA[pokemon.species_id]
        
        if 'evolution_level' not in species_data:
            return False, "Does not evolve by level"
        
        if pokemon.level < species_data['evolution_level']:
            return False, f"Level {pokemon.level} < {species_data['evolution_level']}"
        
        # Check for crucial pre-evolution moves
        next_important_move = self._get_next_pre_evolution_move(
            pokemon.species_id, 
            pokemon.level
        )
        
        if next_important_move:
            # If important move is within 3 levels, wait
            if next_important_move['level'] <= pokemon.level + 3:
                return False, f"Waiting for {next_important_move['name']} at L{next_important_move['level']}"
        
        return True, f"Ready for evolution to {species_data['evolves_to']}"
    
    def _get_next_pre_evolution_move(self, species_id, current_level):
        """Find important moves only learnable before evolution"""
        learnset = POKEMON_LEARNSETS.get(species_id, [])
        
        # Important moves worth waiting for
        important_moves = {
            0x46,  # Razor Leaf
            0x5A,  # Solar Beam
            0x56,  # Thunderbolt
            0x55,  # Thunder
            0x53,  # Fire Blast
            0x3C,  # Psychic
            0x3D,  # Hypnosis
            0x3E,  # Meditate
        }
        
        for move in learnset:
            if move['level'] > current_level and move['level'] < current_level + 10:
                if move['id'] in important_moves:
                    return move
        
        return None
    
    async def check_evolution_stones(self):
        """
        Scan inventory for evolution stones
        Returns list of (item_id, pokemon_candidates)
        """
        stone_map = {
            0x19: ['Gloom', 'Weepinbell', 'Exeggcute'],  # Leaf Stone
            0x1A: ['Poliwhirl', 'Shellder', 'Staryu', 'Eevee'],  # Water Stone
            0x1B: ['Nidorina', 'Nidorino', 'Clefairy', 'Jigglypuff'],  # Moon Stone
            0x1C: ['Gloom', 'Growlithe', 'Vulpix'],  # Fire Stone
            0x1D: ['Pikachu', 'Raichu'],  # Thunder Stone
        }
        
        results = []
        
        for item_id, evolve_list in stone_map.items():
            count = await self.memory.get_item_count(item_id)
            if count > 0:
                # Find eligible Pokemon in party
                candidates = []
                for pokemon in self.party.party:
                    if pokemon and pokemon.species in evolve_list:
                        roi = self._calculate_stone_roi(pokemon, item_id)
                        if roi > 0.7:  # High enough return on investment
                            candidates.append((pokemon, roi))
                
                if candidates:
                    results.append((item_id, candidates))
        
        return results
    
    def _calculate_stone_roi(self, pokemon, stone_id):
        """Calculate return on investment for using rare stones"""
        species_data = SPECIES_DATA[pokemon.species_id]
        
        # Some stone evolutions are always worthwhile
        if pokemon.species_id == 0x43 and stone_id == 0x1B:  # Nidorino + Moon Stone
            return 0.95  # Nidoking is powerful
        
        if pokemon.species_id == 0x40 and stone_id == 0x1C:  # Growlithe + Fire Stone
            return 0.92  # Arcanine has great stats
        
        if pokemon.species_id == 0x52 and stone_id == 0x19:  # Gloom + Leaf Stone
            # Vileplume vs Victreebel decision
            if self.party.party_has_type(0x0A):  # Already has Grass
                return 0.3  # Low value, redundant coverage
            else:
                return 0.85  # High value for Grass coverage
        
        # Default: Base on stat improvement
        evolved_species = stone_map.get(stone_id, {}).get(pokemon.species)
        if evolved_species:
            evolved_stats = SPECIES_BASE_STATS[evolved_species]
            current_stats = SPECIES_BASE_STATS[pokemon.species_id]
            
            stat_gain = sum(evolved_stats.values()) - sum(current_stats.values())
            return min(stat_gain / 100, 0.9)  # Normalize to 0-0.9
        
        return 0.5  # Neutral
```

### 4.2 Trade Evolution Handling

```python
def is_trade_evolution(self, species_id):
    """
    Gen 1 trade evolutions that cannot be completed without trading
    These Pokemon should be evaluated differently
    """
    TRADE_EVOLUTIONS = {
        0x40,  # Kadabra → Alakazam
        0x42,  # Machoke → Machamp
        0x4D,  # Graveler → Golem
        0x5F,  # Haunter → Gengar
    }
    
    return species_id in TRADE_EVOLUTIONS

def evaluate_trade_pokemon(self, pokemon):
    """Lower expectations for trade-evolution Pokemon"""
    if self.is_trade_evolution(pokemon.species_id):
        # These Pokemon are still useful but can't reach final form
        # Reduce their level ceiling expectations
        effective_level_cap = min(pokemon.level, 50)  # Diminishing returns after L50
        
        self.logger.info(
            f"{pokemon.species} is trade-evolution: "
            f"capping evaluation at L{effective_level_cap}"
        )
        
        return effective_level_cap
    
    return pokemon.level
```

---

## 5. Experience Funneling & Anti-Overleveling

### 5.1 EXP Distribution Strategy

```python
class ExperienceFunnel:
    def __init__(self, party_manager):
        self.party = party_manager
        self.logger = party_manager.logger
    
    def calculate_exp_distribution(self):
        """
        Intentionally under-use powerful Pokemon to distribute EXP
        Returns: dict of pokemon -> usage_factor (0.0-1.5)
        """
        party = [p for p in self.party.party if p]
        if len(party) < 2:
            return {p: 1.0 for p in party}
        
        avg_level = sum(p.level for p in party) / len(party)
        distribution = {}
        
        for pokemon in party:
            level_delta = pokemon.level - avg_level
            
            if level_delta > 5:
                # Overleveled: bench in battle, let others catch up
                usage_factor = 0.3 + (5 / level_delta)  # 0.3-0.8x usage
                reason = "Overleveled"
            
            elif level_delta < -5:
                # Underleveled: priority target
                usage_factor = 1.2 + (-level_delta / 10)  # 1.2-1.7x usage
                reason = "Underleveled - EXP priority"
            
            else:
                # Balanced: normal usage
                usage_factor = 1.0
                reason = "Balanced"
            
            distribution[pokemon] = min(usage_factor, 1.5)  # Cap at 150%
            
            self.logger.debug(
                f"EXP Distribution: {pokemon.species} L{pokemon.level} "
                f"→ {usage_factor:.2f}x usage ({reason})"
            )
        
        return distribution
    
    def get_optimal_lead_pokemon(self, battle_type='wild'):
        """
        Choose lead Pokemon based on EXP distribution strategy
        battle_type: 'wild', 'trainer', 'gym', 'elite4'
        """
        distribution = self.calculate_exp_distribution()
        
        # For gyms/elite4, prioritize effectiveness over EXP distribution
        if battle_type in ['gym', 'elite4']:
            return self._get_best_counter_for_boss()
        
        # For wild battles, use EXP distribution weights
        candidates = []
        for pokemon, factor in distribution.items():
            if pokemon.is_alive and pokemon.pp[0] > 0:  # Has usable moves
                score = self.party.calculate_carry_score(pokemon) * factor
                candidates.append((pokemon, score))
        
        if not candidates:
            # Fallback: any alive Pokemon
            alive = [p for p in self.party.party if p and p.is_alive]
            return alive[0] if alive else None
        
        # Sort by weighted score
        candidates.sort(key=lambda x: x[1], reverse=True)
        
        self.logger.debug(
            f"Lead Pokemon: {candidates[0][0].species} "
            f"(Score: {candidates[0][1]:.1f})"
        )
        
        return candidates[0][0]
    
    def detect_exp_waste(self):
        """Alert if Pokemon near level 100 is still battling"""
        for pokemon in self.party.party:
            if pokemon and pokemon.level >= 95:
                exp_for_max = MAX_EXP[pokemon.species_id] - pokemon.total_exp
                if exp_for_max < 10000:
                    self.logger.warning(
                        f"{pokemon.species} near level cap: "
                        f"{exp_for_max} EXP to max - recommend boxing"
                    )
                    return True
        
        return False
```

---

## 6. HM Management & Mule System

### 6.1 HM Opportunity Cost Calculation

```python
class HMManager:
    """Manages permanent HM moves and designates HM mules"""
    
    # HM moves in Gen 1
    HM_MOVES = {
        0x38,  # Cut
        0x39,  # Fly
        0x3A,  # Surf
        0x3B,  # Strength
        0x3C,  # Flash
    }
    
    # Maps HM to required badge
    HM_BADGE_REQUIREMENTS = {
        0x38: 0,   # Cut (always available)
        0x39: 3,   # Fly (Thunder Badge)
        0x3A: 4,   # Surf (Soul Badge)
        0x3B: 5,   # Strength (Volcano Badge)
        0x3C: 4,   # Flash (Soul Badge)
    }
    
    def __init__(self, party_manager):
        self.party = party_manager
        self.logger = party_manager.logger
        self.hm_mules = set()  # Species IDs designated as HM carriers
    
    def calculate_hm_opportunity_cost(self, pokemon, move_id):
        """
        Calculate the cost of teaching a permanent HM move
        Returns: cost (0.0-1.0, higher = worse)
        """
        if move_id not in self.HM_MOVES:
            return 0.0  # Not an HM
        
        move_data = MOVE_DATA[move_id]
        
        # Base opportunity cost: losing a moveslot
        base_cost = 0.15  # 15% of optimal moveset value
        
        # Check if Pokemon gets STAB
        stab_bonus = 1.5 if move_data['type'] in pokemon.types else 1.0
        
        # Check move power (Surf/Strength are better than Cut/Flash)
        if move_data['power'] >= 70:
            power_factor = 0.8
        elif move_data['power'] > 0:
            power_factor = 1.0
        else:  # Status HM (Flash)
            power_factor = 1.5
        
        # Check if Pokemon already has 4 moves
        occupied_moves = sum(1 for move in pokemon.moves if move != 0)
        if occupied_moves >= 4:
            # Must forget a move - higher cost
            forget_penalty = 0.2
        else:
            forget_penalty = 0
        
        total_cost = (base_cost * power_factor / stab_bonus) + forget_penalty
        
        return min(total_cost, 1.0)
    
    def is_good_hm_recipient(self, pokemon, move_id):
        """Determine if Pokemon is a good HM user"""
        cost = self.calculate_hm_opportunity_cost(pokemon, move_id)
        
        # If cost is too high, don't teach
        if cost > 0.7:
            return False
        
        # Already designated as HM mule? Always accept
        if pokemon.species_id in self.hm_mules:
            return True
        
        # Low carry score Pokemon make good HM mules
        carry_score = self.party.calculate_carry_score(pokemon)
        if carry_score < 40:
            return True
        
        # If no alternative, accept higher cost
        alternatives = self._get_hm_alternatives(move_id)
        if not alternatives:
            self.logger.warning(f"No good HM recipients for {MOVE_DATA[move_id]['name']}")
            return True
        
        return False
    
    def _get_hm_alternatives(self, hm_move_id):
        """Find Pokemon in party suitable for HM duty"""
        alternatives = []
        
        for pokemon in self.party.party:
            if not pokemon or pokemon.is_fainted:
                continue
            
            cost = self.calculate_hm_opportunity_cost(pokemon, hm_move_id)
            
            # Prefer low carry score Pokemon
            carry_score = self.party.calculate_carry_score(pokemon)
            
            if cost < 0.6 or (cost < 0.8 and carry_score < 45):
                alternatives.append((pokemon, cost, carry_score))
        
        # Sort by cost ascending, then carry score descending
        alternatives.sort(key=lambda x: (x[1], -x[2]))
        
        return alternatives
    
    def auto_assign_hm_mule(self, hm_move_id):
        """Automatically designate lowest-scoring Pokemon as HM mule"""
        alternatives = self._get_hm_alternatives(hm_move_id)
        
        if not alternatives:
            self.logger.error(f"No Pokemon can learn HM {MOVE_DATA[hm_move_id]['name']}")
            return None
        
        # Choose best candidate (lowest cost, reasonable carry score)
        best_candidate = alternatives[0][0]
        
        self.hm_mules.add(best_candidate.species_id)
        
        self.logger.info(
            f"Auto-designated {best_candidate.species} as HM mule "
            f"for {MOVE_DATA[hm_move_id]['name']}"
        )
        
        return best_candidate
    
    def can_use_all_required_hms(self):
        """Verify party can use all needed HMs for current progress"""
        current_badges = self._get_obtained_badges()
        
        required_hms = []
        for hm_move, badge_needed in self.HM_BADGE_REQUIREMENTS.items():
            if badge_needed <= current_badges:
                required_hms.append(hm_move)
        
        # Check if party has HM coverage
        party_species = {p.species_id for p in self.party.party if p}
        can_learn = set()
        
        for species_id in party_species:
            can_learn.update(HM_COMPATIBILITY.get(species_id, []))
        
        missing_hms = [hm for hm in required_hms if hm not in can_learn]
        
        if missing_hms:
            self.logger.error(f"HM softlock: missing {missing_hms}")
            return False
        
        return True
    
    def _get_obtained_badges(self):
        """Read badge count from WRAM"""
        badge_byte = self.memory.read_byte(0xD772)
        return bin(badge_byte).count('1')

# HM compatibility by species (subset)
HM_COMPATIBILITY = {
    # Starters
    0x99: [0x38],  # Bulbasaur: Cut
    0x09: [0x38, 0x3A],  # Ivysaur: Cut, Surf
    0x0A: [0x38, 0x3A, 0x3B],  # Venusaur: Cut, Surf, Strength
    0xB0: [0x38, 0x3C],  # Charmander: Cut, Flash
    0x0B: [0x38, 0x3B, 0x3C],  # Charmeleon: Cut, Strength, Flash
    0x0C: [0x38, 0x3A, 0x3B, 0x3C],  # Charizard: Cut, Surf, Strength, Flash
    
    # Water HM slaves
    0x54: [0x3A],  # Squirtle: Surf
    0x0D: [0x3A, 0x3B],  # Wartortle: Surf, Strength
    0x0E: [0x3A, 0x3B],  # Blastoise: Surf, Strength
    0xB1: [0x3A],  # Krabby: Surf
    0x5E: [0x3A, 0x3B],  # Kingler: Surf, Strength
    
    # Flying (Fly)
    0x43: [0x38],  # Pidgey: Cut
    0x0F: [0x38, 0x39],  # Pidgeotto: Cut, Fly
    0x14: [0x38, 0x39],  # Pidgeot: Cut, Fly
    0x60: [0x38],  # Spearow: Cut
    0x17: [0x38, 0x39],  # Fearow: Cut, Fly
    0x49: [0x38, 0x39],  # Doduo: Cut, Fly
    0x1E: [0x38, 0x39],  # Dodrio: Cut, Fly
    
    # Normal (Cut/Strength)
    0x54: [0x38],  # Rattata: Cut
    0x1A: [0x38, 0x3B],  # Raticate: Cut, Strength
    0x4A: [0x38],  # Seel: Cut
    0x5A: [0x38, 0x3A, 0x3B],  # Dewgong: Cut, Surf, Strength
}
```

---

## 7. Party Validation & Failsafes

### 7.1 Integrity Checks

```python
class PartyValidator:
    def __init__(self, party_manager):
        self.party = party_manager
        self.logger = party_manager.logger
    
    async def validate_party_state(self):
        """Run comprehensive party integrity checks"""
        checks = [
            self._check_too_many_fainted,
            self._check_hm_softlock,
            self._check_type_coverage,
            self._check_exp_efficiency,
            self._check_status_ailments,
        ]
        
        issues = []
        for check in checks:
            try:
                issue = await check()
                if issue:
                    issues.append(issue)
            except Exception as e:
                self.logger.error(f"Validation check failed: {e}")
        
        return issues
    
    async def _check_too_many_fainted(self):
        """Check if party has too many fainted Pokemon"""
        party = [p for p in self.party.party if p]
        fainted = [p for p in party if p.is_fainted]
        
        if len(fainted) >= 3:
            self.logger.error(f"Party crisis: {len(fainted)}/{len(party)} fainted")
            
            # Emergency protocol: use Revive items
            revive_count = await self.memory.get_item_count(0x27)  # Revive
            max_revive_count = await self.memory.get_item_count(0x28)  # Max Revive
            
            if revive_count + max_revive_count > 0:
                await self._emergency_revive_protocol()
            else:
                # No revives - must flee to Pokemon Center
                await self._initiate_emergency_retreat()
            
            return f"CRITICAL: {len(fainted)} Pokemon fainted"
        
        return None
    
    async def _check_hm_softlock(self):
        """Verify party can use all required HMs"""
        if not self.party.hm_manager.can_use_all_required_hms():
            self.logger.error("HM softlock detected!")
            
            # Try to learn missing HMs
            hm_manager = self.party.hm_manager
            for hm_move in hm_manager.HM_MOVES:
                if not hm_manager._party_can_use(hm_move):
                    # Find Pokemon that can learn this HM
                    candidates = hm_manager._get_hm_alternatives(hm_move)
                    if candidates:
                        await self._teach_hm_to_candidate(candidates[0][0], hm_move)
                        return f"HM softlock resolved: taught {MOVE_DATA[hm_move]['name']}"
            
            return "HM softlock: cannot progress"
        
        return None
    
    async def _check_type_coverage(self):
        """Identify critical type coverage gaps for next boss"""
        next_boss = self._predict_next_major_battle()
        boss_team = self._get_boss_team(next_boss)
        
        party_types = {t for p in self.party.party if p for t in p.types}
        
        gaps = []
        for boss_pokemon in boss_team:
            boss_type = boss_pokemon['types'][0]
            
            # Check if party has counter
            has_counter = False
            for party_type in party_types:
                if TYPE_CHART[party_type][boss_type] >= 2.0:
                    has_counter = True
                    break
            
            if not has_counter:
                gaps.append(boss_type)
        
        if gaps:
            self.logger.warning(f"Type coverage gaps vs {next_boss}: {gaps}")
            return f"Type gaps: {gaps}"
        
        return None
    
    async def _check_exp_efficiency(self):
        """Detect over-leveled or exp-wasting Pokemon"""
        party = [p for p in self.party.party if p]
        avg_level = sum(p.level for p in party) / len(party)
        
        wasted_exp = []
        for pokemon in party:
            if pokemon.level > avg_level + 8:
                # Grossly overleveled
                efficiency = self.party.calculate_stat_efficiency(pokemon)
                if efficiency < 0.6:
                    wasted_exp.append((pokemon, efficiency))
        
        if wasted_exp:
            for pokemon, eff in wasted_exp:
                self.logger.info(
                    f"Exp inefficiency: {pokemon.species} L{pokemon.level} "
                    f"(efficiency: {eff:.2f}) - recommend benching"
                )
            
            return f"Exp inefficiencies: {[p.species for p, _ in wasted_exp]}"
        
        return None
    
    async def _emergency_revive_protocol(self):
        """Use Revive items on fainted Pokemon"""
        for pokemon in self.party.party:
            if pokemon and pokemon.is_fainted:
                # Use Revive if available
                if await self.memory.get_item_count(0x27) > 0:  # Revive
                    await self._use_item_on_pokemon(0x27, pokemon)
                    self.logger.info(f"Emergency revive: {pokemon.species}")
                elif await self.memory.get_item_count(0x28) > 0:  # Max Revive
                    await self._use_item_on_pokemon(0x28, pokemon)
                    self.logger.info(f"Emergency max revive: {pokemon.species}")
    
    async def _initiate_emergency_retreat(self):
        """Flee battle and navigate to Pokemon Center"""
        self.logger.critical("Initiating emergency retreat to Pokemon Center")
        
        # Signal navigation engine to abort current goal
        await self.memory.set_flag("emergency_retreat", True)
        
        # Find nearest Pokemon Center location
        current_map = await self.memory.read_byte(0xD35E)
        nearest_center = self._find_nearest_pokemon_center(current_map)
        
        if nearest_center:
            # Update GOAP planner with emergency goal
            await self.memory.set_goal("survive", priority=999)
            await self.memory.set_target_location(nearest_center)
```

---

## 8. Integration with Combat System

### 8.1 DPS-Based Party Ordering

```python
class CombatIntegration:
    def __init__(self, party_manager, combat_system):
        self.party = party_manager
        self.combat = combat_system
        self.logger = party_manager.logger
    
    def get_optimal_switch_targets(self, enemy_pokemon, available_party):
        """
        During battle, rank party members by effectiveness
        Returns: list of (pokemon, expected_dps, survival_turns)
        """
        candidates = []
        
        for pokemon in available_party:
            # Calculate damage multiplier against enemy
            multiplier = self._calculate_matchup_multiplier(pokemon, enemy_pokemon)
            
            # Estimate Pokemon's DPS against enemy
            best_move, dps = pokemon.get_best_move()
            if dps == 0:
                continue  # No usable moves
            
            effective_dps = dps * multiplier
            
            # Calculate survival turns
            enemy_dps = self._estimate_enemy_dps(enemy_pokemon, pokemon)
            survival_turns = pokemon.current_hp / max(enemy_dps, 1)
            
            # Score: high DPS + survival
            score = effective_dps * min(survival_turns, 5)  # Cap survival impact
            
            candidates.append((pokemon, effective_dps, survival_turns, score))
        
        # Sort by score descending
        candidates.sort(key=lambda x: x[3], reverse=True)
        
        self.logger.debug(
            f"Switch targets vs {enemy_pokemon.species}: "
            f"{[(p.species, f'{dps:.1f}', f'{turns:.1f}') for p, dps, turns, _ in candidates[:3]]}"
        )
        
        return candidates
    
    def _calculate_matchup_multiplier(self, pokemon, enemy):
        """Calculate type advantage multiplier"""
        multiplier = 1.0
        
        # Check each of our move types vs enemy types
        for our_move_id in pokemon.moves:
            if our_move_id == 0:
                continue
            
            move_type = MOVE_DATA[our_move_id]['type']
            
            for enemy_type in enemy.types:
                effectiveness = TYPE_CHART[move_type][enemy_type]
                if effectiveness > multiplier:
                    multiplier = effectiveness
        
        # STAB bonus
        for move_id in pokemon.moves:
            if move_id == 0:
                continue
            if MOVE_DATA[move_id]['type'] in pokemon.types:
                multiplier *= 1.5
                break
        
        return multiplier
    
    def _estimate_enemy_dps(self, enemy_pokemon, our_pokemon):
        """Estimate enemy's DPS against our Pokemon"""
        # This would integrate with Chapter 5's damage calculation
        # Simplified version for now
        enemy_attack = enemy_pokemon.attack
        enemy_special = enemy_pokemon.special
        
        # Assume enemy uses strongest move
        base_damage = max(enemy_attack, enemy_special) * 0.8
        
        # Type effectiveness
        for enemy_type in enemy_pokemon.types:
            for our_type in our_pokemon.types:
                if TYPE_CHART[enemy_type][our_type] >= 2.0:
                    base_damage *= 1.5  # Super effective
        
        return base_damage / 10  # Convert to per-turn damage
```

---

## 9. Configuration & Weights

### 9.1 Tunable Parameters

```python
PARTY_OPTIMIZATION_CONFIG = {
    # Carry score weights
    'level_relevance_weight': 0.25,
    'type_uniqueness_weight': 0.30,
    'move_coverage_weight': 0.25,
    'stat_efficiency_weight': 0.20,
    
    # Evolution timing
    'move_wait_threshold': 3,  # Levels to wait for important move
    'stone_roi_threshold': 0.7,  # Minimum ROI for evolution stone
    
    # EXP distribution
    'balanced_level_delta': 5,  # +/- levels considered balanced
    'overleveled_penalty': 0.5,  # Usage factor for overleveled
    'underleveled_boost': 1.5,  # Max usage factor for underleveled
    
    # HM management
    'hm_opportunity_cost_threshold': 0.7,  # Max acceptable cost
    'hm_mule_carry_score_max': 40,  # Max score for HM mule
    'max_hm_mules': 2,  # Maximum HM slaves
    
    # Validation
    'critical_fainted_threshold': 3,  # Too many fainted
    'exp_waste_level_threshold': 95,  # Near level cap
    'stat_efficiency_minimum': 0.6,  # Below this is inefficient
}
```

---

## 10. Performance Specifications

### 10.1 Benchmarks

| Operation | Time | Frequency | Notes |
|-----------|------|-----------|-------|
| Full party scan | 80ms | On change ($D163) | 264 bytes × 6 slots |
| Carry score calc | 5ms | Per Pokemon | 4 components |
| Evolution check | 10ms | Per level up | Move lookup |
| HM validation | 15ms | Per badge | Party analysis |
| Exp distribution | 3ms | Per battle | 6 Pokemon |

**CPU Target:** <5% total overhead @ 60fps (16.67ms/frame)  
**Memory:** <1KB for party cache + 500B for metadata

---

## 11. Integration Checklist

- [ ] **Chapter 2**: Memory interface functions for $D16B party scanning
- [ ] **Chapter 5**: DPS calculations for stat efficiency component
- [ ] **Chapter 7**: Inventory checks for evolution stones and Revives
- [ ] **Chapter 9**: GOAP goal satisfaction for party optimization
- [ ] **Chapter 10**: Failsafe triggers for party wipe and HM softlock

---

## 12. Testing Requirements

```python
# Unit tests required
test_party_scan_accuracy()
test_carry_score_deterministic()
test_evolution_timing_optimizer()
test_exp_distribution_fairness()
test_hm_opportunity_cost()
test_party_wipe_recovery()
test_trade_evolution_handling()
test_type_coverage_analysis()
```

**Minimum Coverage:** 90% unit test coverage for algorithms, 100% for critical path

---

## 13. Known Edge Cases

| Scenario | Probability | Mitigation |
|----------|-------------|------------|
| Box overflow | 12% | Auto-release lowest carry score |
| HM softlock | 31% | Designate emergency HM mule |
| Evolution stone shortage | 8% | ROI-based allocation |
| Trade evolution impossible | 5% | Lower level expectations |
| Level 100 exp waste | 0.1% | Early boxing warning |
| Party wipe | 2% | Emergency revive protocol |

---

**Document Version History:**
- v1.0: Initial specification with complete algorithms
- v1.1: (Future) Performance optimizations and edge case additions