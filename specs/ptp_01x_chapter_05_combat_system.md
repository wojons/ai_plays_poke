# PTP-01X Chapter 5: Combat Mechanics & Battle Heuristics

## Executive Summary

This chapter defines the complete battle system for Generation I Pokémon games, including:
- **Damage Calculation Formula** (Gen 1 specific)
- **Type Effectiveness Matrix** (15×15 for Gen 1)
- **Stat Modifier Logic** (stages and multipliers)
- **Kill Threshold Calculations**
- **Switch and Sacrifice Protocols**

**Key Gen 1 Differences from Modern Games:**
- Special stat is single value (not Sp. Atk / Sp. Def)
- No critical hit stat modifiers (always +1 stage)
- Damage variance is 0.85-1.0 (not 0.85-1.0 like modern)
- Bug/ Poison were super effective against each other
- Ghost had no effect on Psychic (glitch, not fixed until Gen 2)
- Ice wasn't very effective on Fire (neutral instead)

---

## 5.1 Generation I Damage Formula

### Complete Formula

```
Damage = ((((2 × Level / 5 + 2) × BasePower × A/D) / 50) + 2) × Modifier
```

Where **Modifier** = `TypeEffectiveness × STAB × Critical × Random × Other`

### Step-by-Step Calculation

**Step 1: Calculate Base Damage**
```
Base = (2 × Level / 5 + 2)
```

**Step 2: Apply Attack/Defense**
```
Intermediate = Base × BasePower × (Attack / Defense)
```

**Step 3: Divide by 50**
```
Divided = Intermediate / 50
```

**Step 4: Add 2**
```
Added = Divided + 2
```

**Step 5: Apply Modifiers**
```
FinalDamage = Added × Type × STAB × Critical × Random × Other
```

### Python Implementation

```python
def calculate_damage_gen1(
    level: int,
    base_power: int,
    attack: int,
    defense: int,
    type_effectiveness: float,
    is_stab: bool,
    is_critical: bool,
    move_type: str,
    attacker_type1: str,
    attacker_type2: str = None,
) -> tuple[int, int]:
    """
    Calculate damage range for Gen 1 Pokemon
    
    Args:
        level: Attacker level (1-100)
        base_power: Move base power
        attack: Attacker's Attack stat (not Special in Gen 1)
        defense: Defender's Defense stat (not Special in Gen 1)
        type_effectiveness: Multiplier (0, 0.25, 0.5, 1, 2, 4)
        is_stab: Same-Type Attack Bonus (1.5 if move type matches attacker)
        is_critical: Critical hit (1.5x damage, ignores stat modifiers)
        move_type: Type of the move
        attacker_type1: Attacker's primary type
        attacker_type2: Attacker's secondary type (or None)
    
    Returns:
        Tuple of (min_damage, max_damage)
    """
    # Step 1: Base calculation
    base = (2 * level / 5 + 2)
    
    # Step 2: Attack/Defense application
    intermediate = base * base_power * (attack / defense)
    
    # Step 3: Divide by 50
    divided = intermediate / 50
    
    # Step 4: Add 2
    added = divided + 2
    
    # Step 5: Apply modifiers
    modifier = type_effectiveness
    
    # STAB (Same-Type Attack Bonus)
    if is_stab:
        modifier *= 1.5
    
    # Critical hit (Gen 1: always 1.5x, ignores stat modifiers)
    if is_critical:
        modifier *= 1.5
    
    # Random variance (0.85-1.0)
    random_min = 0.85
    random_max = 1.0
    
    # Calculate range
    min_damage = int(added * modifier * random_min)
    max_damage = int(added * modifier * random_max)
    
    # Ensure at least 1 damage if move is effective
    if type_effectiveness > 0 and min_damage < 1:
        min_damage = 1
    
    return (min_damage, max_damage)
```

---

## 5.2 Type Effectiveness Matrix (Gen 1)

### The 15-Type System (Gen 1)

Gen 1 had **15 types** (no Dark, Steel, or Fairy):

```
Types: Normal, Fire, Water, Electric, Grass, Ice, 
       Fighting, Poison, Ground, Flying, Psychic, 
       Bug, Rock, Ghost, Dragon
```

### Complete Type Chart (Generation I)

| Def → | Normal | Fire | Water | Electric | Grass | Ice | Fighting | Poison | Ground | Flying | Psychic | Bug | Rock | Ghost | Dragon |
|--------|--------|------|-------|----------|-------|-----|----------|--------|--------|--------|---------|-----|------|-------|--------|
| **Normal** | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | ½ | 0 | 1 |
| **Fire** | 1 | ½ | ½ | 1 | 2 | 2 | 1 | 1 | 1 | 1 | 1 | 2 | ½ | 1 | ½ |
| **Water** | 1 | 2 | ½ | 1 | ½ | 1 | 1 | 1 | 2 | 1 | 1 | 1 | 2 | 1 | ½ |
| **Electric** | 1 | 1 | 2 | ½ | ½ | 1 | 1 | 1 | 0 | 2 | 1 | 1 | 1 | 1 | ½ |
| **Grass** | 1 | ½ | 2 | 1 | ½ | 1 | 1 | ½ | 2 | ½ | 1 | ½ | 2 | 1 | ½ |
| **Ice** | 1 | ½ | ½ | 1 | 2 | ½ | 1 | 1 | 2 | 2 | 1 | 1 | 1 | 1 | 2 |
| **Fighting** | 2 | 1 | 1 | 1 | 1 | 2 | 1 | 1 | 1 | ½ | ½ | ½ | 2 | 0 | 1 |
| **Poison** | 1 | 1 | 1 | 1 | 2 | 1 | 1 | ½ | ½ | 1 | 1 | 2 | ½ | ½ | 1 |
| **Ground** | 1 | 2 | 1 | 2 | ½ | 1 | 1 | 2 | 1 | 0 | 1 | ½ | 2 | 1 | 1 |
| **Flying** | 1 | 1 | 1 | ½ | 2 | 1 | 2 | 1 | 1 | 1 | 1 | 2 | ½ | 1 | 1 |
| **Psychic** | 1 | 1 | 1 | 1 | 1 | 1 | 2 | 2 | 1 | 1 | ½ | 1 | 1 | 1 | 1 |
| **Bug** | 1 | ½ | 1 | 1 | 2 | 1 | ½ | ½ | 1 | ½ | 2 | 1 | 1 | ½ | 1 |
| **Rock** | 1 | 2 | 1 | 1 | 1 | 2 | ½ | 1 | ½ | 2 | 1 | 2 | 1 | 1 | 1 |
| **Ghost** | 0 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 0 | 1 | 1 | 2 | 1 |
| **Dragon** | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 2 |

### Gen 1 Specific Quirks

| Issue | Type A | Type B | Gen 1 | Modern (Gen 2+) |
|-------|--------|--------|-------|-----------------|
| Bug/Poison | Bug | Poison | 2× (super effective) | ½× (not very) |
| Ghost/Psychic | Ghost | Psychic | 0× (no effect) | 2× (super effective) |
| Ice/Fire | Ice | Fire | 1× (neutral) | ½× (not very) |
| Normal/Ghost | Normal | Ghost | 0× (no effect) | 1× (normal) |

### Python Type Chart Implementation

```python
GEN1_TYPE_CHART = {
    # (attacking_type, defending_type) = effectiveness
    # Normal
    ('Normal', 'Normal'): 1.0, ('Normal', 'Fire'): 1.0, ('Normal', 'Water'): 1.0,
    ('Normal', 'Electric'): 1.0, ('Normal', 'Grass'): 1.0, ('Normal', 'Ice'): 1.0,
    ('Normal', 'Fighting'): 1.0, ('Normal', 'Poison'): 1.0, ('Normal', 'Ground'): 1.0,
    ('Normal', 'Flying'): 1.0, ('Normal', 'Psychic'): 1.0, ('Normal', 'Bug'): 1.0,
    ('Normal', 'Rock'): 0.5, ('Normal', 'Ghost'): 0.0, ('Normal', 'Dragon'): 1.0,
    
    # Fire
    ('Fire', 'Normal'): 1.0, ('Fire', 'Fire'): 0.5, ('Fire', 'Water'): 0.5,
    ('Fire', 'Electric'): 1.0, ('Fire', 'Grass'): 2.0, ('Fire', 'Ice'): 2.0,
    ('Fire', 'Fighting'): 1.0, ('Fire', 'Poison'): 1.0, ('Fire', 'Ground'): 1.0,
    ('Fire', 'Flying'): 1.0, ('Fire', 'Psychic'): 1.0, ('Fire', 'Bug'): 2.0,
    ('Fire', 'Rock'): 0.5, ('Fire', 'Ghost'): 1.0, ('Fire', 'Dragon'): 0.5,
    
    # ... (complete chart for all 15 types)
}

def get_type_effectiveness(move_type: str, defender_type1: str, 
                           defender_type2: str = None) -> float:
    """
    Calculate type effectiveness for Gen 1
    
    Returns:
        0.0, 0.25, 0.5, 1.0, 2.0, or 4.0
    """
    multiplier = 1.0
    
    # Check against primary type
    key1 = (move_type, defender_type1)
    multiplier *= GEN1_TYPE_CHART.get(key1, 1.0)
    
    # Check against secondary type
    if defender_type2:
        key2 = (move_type, defender_type2)
        multiplier *= GEN1_TYPE_CHART.get(key2, 1.0)
    
    return multiplier
```

---

## 5.3 Stat Modifiers (Stage System)

### Stat Stages in Gen 1

Gen 1 has **7 stat stages** (-6 to +6):

| Stage | Multiplier | Description |
|-------|------------|-------------|
| +6 | 4.0 | Maximum boost |
| +5 | 3.5 | - |
| +4 | 3.0 | - |
| +3 | 2.5 | - |
| +2 | 2.0 | - |
| +1 | 1.5 | - |
| 0 | 1.0 | No change |
| -1 | 0.66 | - |
| -2 | 0.5 | - |
| -3 | 0.4 | - |
| -4 | 0.33 | - |
| -5 | 0.28 | - |
| -6 | 0.25 | Maximum penalty |

### Stat Modifier Implementation

```python
STAGE_MULTIPLIERS = {
    -6: 0.25, -5: 0.28, -4: 0.33, -3: 0.40, -2: 0.50, -1: 0.66,
    0: 1.00,
    1: 1.50, 2: 2.00, 3: 2.50, 4: 3.00, 5: 3.50, 6: 4.00
}

def apply_stat_modifier(base_stat: int, stage: int) -> int:
    """
    Apply stat stage modifier to base stat
    
    Gen 1: Special is single stat (not Sp. Atk / Sp. Def)
    """
    multiplier = STAGE_MULTIPLIERS.get(stage, 1.0)
    return int(base_stat * multiplier)

def get_stat_with_modifiers(base_stat: int, attack_stage: int, 
                           defense_stage: int, is_critical: bool = False) -> tuple[int, int]:
    """
    Calculate effective Attack and Defense for damage formula
    
    Args:
        base_stat: Base stat value
        attack_stage: Attacker's stat stage
        defense_stage: Defender's stat stage
        is_critical: Whether this is a critical hit
    
    Returns:
        Tuple of (effective_attack, effective_defense)
    """
    if is_critical:
        # Critical hits ignore stat modifiers (use stage 0)
        effective_attack = base_stat
        effective_defense = base_stat
    else:
        effective_attack = apply_stat_modifier(base_stat, attack_stage)
        effective_defense = apply_stat_modifier(base_stat, defense_stage)
    
    return (effective_attack, effective_defense)
```

---

## 5.4 Critical Hit Calculation

### Gen 1 Critical Hit Mechanics

**Key Differences from Modern Games:**
- Critical hits always deal 1.5× damage (not 2×)
- Critical hits **ignore the defender's stat modifiers** (but use attacker's)
- No "critical hit stage" - always 1/16 base chance (or 1/8 for Focus Energy)

### Python Implementation

```python
import random

CRITICAL_HIT_CHANCE_BASE = 1/16  # 6.25%
FOCUS_ENERGY_CHANCE = 1/8  # 12.5%

def calculate_critical_hit(
    is_focus_energy: bool = False,
    high_crit_move: bool = False,
    opponent_slower: bool = False,
) -> bool:
    """
    Calculate if a critical hit occurs
    
    Gen 1 mechanics:
    - Base chance: 1/16
    - Focus Energy: 1/8
    - "High crit" moves: 1/8 (later gens: 1/4 or higher)
    - Speed check: If attacker faster, +1 stage (later gens)
    """
    chance = CRITICAL_HIT_CHANCE_BASE
    
    if is_focus_energy:
        chance = FOCUS_ENERGY_CHANCE
    
    if high_crit_move:
        chance = max(chance, 1/8)
    
    return random.random() < chance
```

---

## 5.5 Kill Threshold Logic

### Priority System for Move Selection

```python
from enum import Enum, auto

class KillPriority(Enum):
    """Move selection priority levels"""
    GUARANTEED_KO = auto()      # Priority 1: Will definitely kill
    SURVIVABLE_ATTACK = auto()  # Priority 2: Can survive enemy hit
    SWITCH_REQUIRED = auto()    # Priority 3: Need to switch
    LAST_RESORT = auto()        # Priority 4: Any move that hits
    NO_MOVE = auto()            # Priority 5: Cannot attack (0 effectiveness)

def calculate_move_priority(
    move_min_damage: int,
    move_max_damage: int,
    enemy_current_hp: int,
    my_current_hp: int,
    enemy_move_power: int,
    enemy_attack: int,
    my_defense: int,
) -> KillPriority:
    """
    Determine priority level for a move
    
    Returns priority level based on:
    1. Can this move guarantee a KO?
    2. Can I survive the enemy's next attack?
    3. Should I switch instead?
    """
    
    # Priority 1: Guaranteed KO
    if move_min_damage >= enemy_current_hp:
        return KillPriority.GUARANTEED_KO
    
    # Calculate if I can survive enemy's attack
    enemy_damage_range = calculate_damage_gen1(
        level=50,  # Assumed level for calculation
        base_power=enemy_move_power,
        attack=enemy_attack,
        defense=my_defense,
        type_effectiveness=1.0,  # Assume neutral
        is_stab=False,
        is_critical=False,
        move_type='normal',
        attacker_type1='normal',
    )
    
    max_enemy_damage = enemy_damage_range[1]
    
    # Priority 2: Survivable attack
    if my_current_hp > max_enemy_damage:
        return KillPriority.SURVIVABLE_ATTACK
    
    # Priority 3: Need to switch or use priority move
    return KillPriority.SWITCH_REQUIRED
```

---

## 5.6 Complete Battle Heuristic System

```python
from dataclasses import dataclass
from typing import Optional
from enum import Enum

class BattlePhase(Enum):
    """Battle phase states"""
    OPPONENT_SEND_OUT = "opp_send_out"
    PLAYER_SEND_OUT = "player_send_out"
    MOVE_SELECTION = "move_selection"
    PLAYER_ATTACK = "player_attack"
    ENEMY_ATTACK = "enemy_attack"
    SWITCH_PROMPT = "switch_prompt"
    ITEM_PROMPT = "item_prompt"
    BATTLE_END = "battle_end"

@dataclass
class BattleState:
    """Complete battle state snapshot"""
    phase: BattlePhase
    turn: int
    player_pokemon: dict
    enemy_pokemon: dict
    player_party: list
    available_moves: list
    player_hp_percent: float
    enemy_hp_percent: float
    should_switch: bool
    recommended_action: str

class BattleHeuristics:
    """
    Complete battle decision system for Gen 1 Pokemon
    """
    
    def __init__(self, type_chart: dict, move_data: dict, pokemon_stats: dict):
        self.type_chart = type_chart
        self.move_data = move_data
        self.pokemon_stats = pokemon_stats
    
    def analyze_battle_state(
        self,
        player_party: list,
        enemy_pokemon: dict,
        battle_context: dict,
    ) -> BattleState:
        """
        Analyze current battle and recommend action
        """
        # Get current Pokemon
        current_pokemon = player_party[0]
        
        # Calculate HP percentages
        player_hp = current_pokemon['current_hp']
        player_max_hp = current_pokemon['max_hp']
        player_hp_percent = (player_hp / player_max_hp) * 100
        
        enemy_hp = enemy_pokemon.get('current_hp', 100)
        enemy_max_hp = enemy_pokemon.get('max_hp', 100)
        enemy_hp_percent = (enemy_hp / enemy_max_hp) * 100
        
        # Determine phase from context
        phase = self._determine_phase(battle_context)
        
        # Evaluate move options
        available_moves = current_pokemon.get('moves', [])
        move_analysis = self._analyze_moves(
            current_pokemon, enemy_pokemon, available_moves
        )
        
        # Determine if switching is needed
        should_switch = self._should_switch(
            current_pokemon, enemy_pokemon, player_hp_percent
        )
        
        # Select best action
        recommended_action = self._select_action(
            phase, move_analysis, should_switch
        )
        
        return BattleState(
            phase=phase,
            turn=battle_context.get('turn', 1),
            player_pokemon=current_pokemon,
            enemy_pokemon=enemy_pokemon,
            player_party=player_party,
            available_moves=available_moves,
            player_hp_percent=player_hp_percent,
            enemy_hp_percent=enemy_hp_percent,
            should_switch=should_switch,
            recommended_action=recommended_action,
        )
    
    def _analyze_moves(
        self, 
        attacker: dict, 
        defender: dict,
        moves: list,
    ) -> list:
        """Analyze all available moves and their effectiveness"""
        move_analysis = []
        
        for move_id in moves:
            move = self.move_data.get(move_id, {})
            move_type = move.get('type', 'normal')
            base_power = move.get('power', 0)
            
            # Get types
            attacker_types = [attacker.get('type1'), attacker.get('type2')]
            defender_types = [defender.get('type1'), defender.get('type2')]
            
            # Calculate effectiveness
            type_eff = 1.0
            for def_type in defender_types:
                if def_type:
                    type_eff *= self.type_chart.get(
                        (move_type, def_type), 1.0
                    )
            
            # Calculate STAB
            is_stab = move_type in attacker_types
            
            # Calculate damage range
            damage_range = calculate_damage_gen1(
                level=attacker.get('level', 50),
                base_power=base_power,
                attack=attacker.get('attack', 100),
                defense=defender.get('defense', 100),
                type_effectiveness=type_eff,
                is_stab=is_stab,
                is_critical=False,
                move_type=move_type,
                attacker_type1=attacker_types[0],
                attacker_type2=attacker_types[1],
            )
            
            move_analysis.append({
                'move_id': move_id,
                'move_name': move.get('name', 'Unknown'),
                'type': move_type,
                'power': base_power,
                'type_effectiveness': type_eff,
                'is_stab': is_stab,
                'damage_range': damage_range,
                'pp': attacker.get('move_pp', [0, 0, 0, 0])[moves.index(move_id)],
            })
        
        # Sort by expected damage
        move_analysis.sort(key=lambda m: m['damage_range'][1], reverse=True)
        return move_analysis
    
    def _should_switch(
        self,
        attacker: dict,
        defender: dict,
        hp_percent: float,
    ) -> bool:
        """Determine if switching is recommended"""
        # Switch if HP is critical (< 20%)
        if hp_percent < 20:
            return True
        
        # Switch if opponent has super-effective counter
        attacker_types = [attacker.get('type1'), attacker.get('type2')]
        defender_move_type = 'fire'  # Example: Assume strong counter-type
        
        # Check if defender's likely moves are super effective
        for atk_type in attacker_types:
            if atk_type:
                eff = self.type_chart.get((defender_move_type, atk_type), 1.0)
                if eff >= 2.0:
                    return True
        
        return False
    
    def _determine_phase(self, context: dict) -> BattlePhase:
        """Determine current battle phase"""
        if context.get('enemy_fainted', False):
            return BattlePhase.OPPONENT_SEND_OUT
        if context.get('player_fainted', False):
            return BattlePhase.PLAYER_SEND_OUT
        if context.get('switch_requested', False):
            return BattlePhase.SWITCH_PROMPT
        if context.get('item_requested', False):
            return BattlePhase.ITEM_PROMPT
        return BattlePhase.MOVE_SELECTION
    
    def _select_action(
        self,
        phase: BattlePhase,
        move_analysis: list,
        should_switch: bool,
    ) -> str:
        """Select the best action based on analysis"""
        if phase == BattlePhase.SWITCH_PROMPT and should_switch:
            return "SWITCH"
        
        if phase == BattlePhase.MOVE_SELECTION and move_analysis:
            best_move = move_analysis[0]
            
            # If move has 0 effectiveness, suggest switching
            if best_move['type_effectiveness'] == 0:
                return "SWITCH"
            
            # If move is super effective, prefer it
            if best_move['type_effectiveness'] >= 2.0:
                return f"MOVE:{best_move['move_id']}"
            
            return f"MOVE:{best_move['move_id']}"
        
        return "WAIT"
```

---

## 5.7 Expected Damage Table (Quick Reference)

### Level 50 Damage Ranges

| Move Power | Min Damage | Max Damage | Average |
|-----------|-----------|-----------|---------|
| 20 | 6-7 | 8-10 | 8 |
| 40 | 13-15 | 17-20 | 17 |
| 60 | 20-23 | 26-30 | 26 |
| 80 | 27-31 | 35-41 | 35 |
| 100 | 34-39 | 44-52 | 44 |
| 120 | 41-47 | 53-62 | 53 |
| 150 | 51-59 | 66-78 | 66 |
| 200 | 68-79 | 88-104 | 88 |

*Assuming 100 Attack vs 100 Defense, neutral type, no STAB*

---

## 5.8 Summary: Battle Decision Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    BATTLE DECISION FLOW                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. GET STATE                                                   │
│     ├── Read player Pokemon from party                          │
│     ├── Read enemy Pokemon from battle memory                   │
│     ├── Calculate HP percentages                                │
│     └── Get available moves with PP                             │
│                                                                  │
│  2. ANALYZE MOVES                                               │
│     ├── For each move:                                          │
│     │   ├── Get move type and power                             │
│     │   ├── Calculate type effectiveness                        │
│     │   ├── Check STAB                                          │
│     │   ├── Calculate damage range (min/max)                    │
│     │   └── Store analysis                                      │
│     └── Sort by expected damage                                 │
│                                                                  │
│  3. EVALUATE SWITCH                                              │
│     ├── HP < 20%? → Switch                                      │
│     ├── Type disadvantage? → Switch                             │
│     └── Enemy super-effective counter? → Switch                 │
│                                                                  │
│  4. SELECT ACTION                                               │
│     ├── Priority 1: Guaranteed KO move                          │
│     ├── Priority 2: Super-effective move                        │
│     ├── Priority 3: Any damaging move                           │
│     └── Priority 4: Switch if no good move                      │
│                                                                  │
│  5. EXECUTE                                                     │
│     └── Press button for selected action                        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 5.9 References

1. **Bulbapedia Damage**: https://bulbapedia.bulbagarden.net/wiki/Damage
2. **Smogon Damage Calc**: https://deepwiki.com/smogon/damage-calc/3.2-generation-specific-mechanics
3. **Gen 1 Type Chart**: https://pokeprint.kimbachu.com/printables/rb/type-effectiveness-chart
4. **Pokemon Database Type Chart**: https://pokemondb.net/type/old

---

**Document Version:** 1.0  
**Last Updated:** December 31, 2025  
**Protocol:** PTP-01X - Chapter 5: Combat System  
**Formula Source:** Bulbapedia damage calculation article  
**Type Chart Source:** PokePrint Gen 1 printable chart