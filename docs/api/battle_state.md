# BattleState

Detailed battle information for AI strategists and tacticians.

## Overview

The `BattleState` dataclass provides comprehensive battle information including Pokemon details, HP percentages, type matchups, and available moves. This data is used by the Vision System and AI decision making.

## Class Signature

```python
@dataclass
class BattleState:
    tick: int
    timestamp: str
    enemy_pokemon: str
    enemy_level: int
    enemy_hp_percent: float
    player_pokemon: str
    player_level: int
    player_hp_percent: float

    # Optional enriched data
    battle_id: Optional[int] = None
    enemy_types: Optional[List[str]] = None
    enemy_base_stats: Optional[Dict[str, int]] = None
    enemy_weaknesses: Optional[List[str]] = None
    enemy_resistances: Optional[List[str]] = None
    turn_number: int = 0
    available_moves: Optional[List[str]] = None
```

## Fields

### Core Battle Fields

| Field | Type | Description |
|-------|------|-------------|
| `tick` | `int` | Current tick count |
| `timestamp` | `str` | ISO timestamp |
| `enemy_pokemon` | `str` | Enemy Pokemon species name |
| `enemy_level` | `int` | Enemy Pokemon level |
| `enemy_hp_percent` | `float` | Enemy HP percentage (0-100) |
| `player_pokemon` | `str` | Player's active Pokemon |
| `player_level` | `int` | Player Pokemon level |
| `player_hp_percent` | `float` | Player HP percentage (0-100) |

### Turn Tracking

| Field | Type | Description |
|-------|------|-------------|
| `turn_number` | `int` | Current turn number (1, 2, 3, ...) |
| `battle_id` | `Optional[int]` | Database battle ID |

### Type Information

| Field | Type | Description |
|-------|------|-------------|
| `enemy_types` | `Optional[List[str]]` | Enemy Pokemon types (e.g., ["Grass", "Poison"]) |
| `enemy_weaknesses` | `Optional[List[str]]` | Types super-effective against enemy |
| `enemy_resistances` | `Optional[List[str]]` | Types not very effective |

### Stats and Moves

| Field | Type | Description |
|-------|------|-------------|
| `enemy_base_stats` | `Optional[Dict[str, int]]` | Base stats (HP, Atk, Def, Spd, Spc) |
| `available_moves` | `Optional[List[str]]` | Player's available moves |

## Methods

### `get_type_advice(self) -> str`

Generate type matchup advice string.

```python
battle = BattleState(
    tick=1500,
    timestamp="2025-12-31T12:00:00",
    enemy_pokemon="Bulbasaur",
    enemy_level=5,
    enemy_hp_percent=100.0,
    player_pokemon="Charmander",
    player_level=5,
    player_hp_percent=100.0,
    enemy_types=["Grass", "Poison"],
    enemy_weaknesses=["Fire", "Ice", "Flying", "Psychic"]
)

advice = battle.get_type_advice()
print(advice)  # "Use Fire, Ice, Flying, Psychic type moves for super-effective damage"
```

**Returns:** `str` - Type advice message

---

## Usage Examples

### Basic Battle State

```python
from schemas.commands import BattleState

battle = BattleState(
    tick=1500,
    timestamp="2025-12-31T12:00:00",
    enemy_pokemon="Pidgey",
    enemy_level=5,
    enemy_hp_percent=50.0,
    player_pokemon="Pikachu",
    player_level=5,
    player_hp_percent=75.0
)

print(f"Enemy: {battle.enemy_pokemon} Lv{battle.enemy_level} ({battle.enemy_hp_percent}%)")
print(f"Player: {battle.player_pokemon} Lv{battle.player_level} ({battle.player_hp_percent}%)")
```

### Enriched Battle State with Type Info

```python
battle = BattleState(
    tick=1600,
    timestamp="2025-12-31T12:01:00",
    enemy_pokemon="Geodude",
    enemy_level=8,
    enemy_hp_percent=100.0,
    player_pokemon="Pikachu",
    player_level=7,
    player_hp_percent=100.0,
    enemy_types=["Rock", "Ground"],
    enemy_weaknesses=["Water", "Grass", "Ice", "Steel"],
    enemy_resistances=["Poison", "Rock"],
    available_moves=["ThunderShock", "Quick Attack", "Growl", "Tail Whip"]
)

# Get type advice
print(battle.get_type_advice())
# "Use Water, Grass, Ice, Steel type moves for super-effective damage"
```

### Turn-by-Turn Battle

```python
# Turn 1
turn1 = BattleState(
    tick=1500,
    timestamp="2025-12-31T12:00:00",
    enemy_pokemon="Caterpie",
    enemy_level=3,
    enemy_hp_percent=100.0,
    player_pokemon="Pikachu",
    player_level=5,
    player_hp_percent=100.0,
    turn_number=1
)

# Turn 2 (after damage)
turn2 = BattleState(
    tick=1550,
    timestamp="2025-12-31T12:00:01",
    enemy_pokemon="Caterpie",
    enemy_level=3,
    enemy_hp_percent=40.0,  # Damaged
    player_pokemon="Pikachu",
    player_level=5,
    player_hp_percent=90.0,  # Took some damage
    turn_number=2
)
```

### Strategic Decision Using Battle State

```python
def choose_move(battle: BattleState) -> str:
    if not battle.available_moves:
        return "No moves available"

    if battle.enemy_hp_percent < 20:
        # Low health - try to catch
        return "Use Poké Ball"

    # Check type effectiveness
    if battle.enemy_weaknesses:
        for move in battle.available_moves:
            if move in battle.enemy_weaknesses:
                return f"Use {move}"

    # Default to first move
    return f"Use {battle.available_moves[0]}"

battle = BattleState(...)
action = choose_move(battle)
```

### Type Matchup Analysis

```python
def analyze_matchup(battle: BattleState) -> dict:
    analysis = {
        "favorable": False,
        "advice": battle.get_type_advice(),
        "recommended_types": battle.enemy_weaknesses or []
    }

    if battle.player_pokemon:
        # Check if player has favorable types
        player_types = get_pokemon_types(battle.player_pokemon)
        if player_types:
            favorable = any(t in battle.enemy_weaknesses for t in player_types)
            analysis["favorable"] = favorable

    return analysis
```

## Integration with Vision System

The Vision Pipeline extracts and enriches battle data:

```python
# From vision/battle.py
def analyze_battle(screenshot: np.ndarray) -> BattleState:
    # Extract basic info
    enemy = extract_enemy_pokemon(screenshot)
    player = extract_player_pokemon(screenshot)

    # Enrich with Pokédex data
    enriched = enrich_with_pokedex(enemy)

    return BattleState(
        tick=current_tick,
        timestamp=datetime.now().isoformat(),
        enemy_pokemon=enemy.species,
        enemy_level=enemy.level,
        enemy_hp_percent=enemy.hp_percent,
        player_pokemon=player.species,
        player_level=player.level,
        player_hp_percent=player.hp_percent,
        enemy_types=enriched.types,
        enemy_weaknesses=enriched.weaknesses,
        enemy_base_stats=enriched.base_stats,
        available_moves=player.moves
    )
```

## See Also

- [GameState](game_state.md) - General game state
- [AICommand](ai_command.md) - Commands generated from battle state
- [GameAIManager](game_ai_manager.md) - AI that uses battle state
- [Combat System](not_implemented) - Damage calculation and type effectiveness