# GameDatabase

SQLite database for tracking all game events and AI decisions.

## Overview

The `GameDatabase` class provides persistent storage for:
- Session tracking and performance metrics
- AI commands sent to emulator
- AI thinking processes and reasoning
- Battle events (start, end, turns)
- Pokemon encounters
- Screenshot metadata
- Model comparison training runs

## Class Signature

```python
class GameDatabase:
    def __init__(self, db_path: str)
```

## Constructor

### `__init__(self, db_path: str)`

Initialize database at specified path.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `db_path` | `str` | Path to SQLite database file (created if not exists) |

**Database Tables Created:**
- `sessions` - Overall AI run tracking
- `screenshots` - Screenshot capture events
- `commands` - Commands sent to emulator
- `ai_thoughts` - AI thinking processes
- `battles` - Battle tracking
- `battle_turns` - Per-turn battle data
- `pokemon` - Pokemon encounters
- `performance_metrics` - Performance snapshots
- `training_runs` - Model comparison data

**Example:**

```python
from src.db.database import GameDatabase

db = GameDatabase("./game_data.db")
```

## Session Management

### `start_session(self, rom_path: str, model_name: str = "unknown") -> int`

Start a new tracked session.

```python
session_id = db.start_session(
    rom_path="pokemon_red.gb",
    model_name="gpt-4o"
)
print(f"Session {session_id} started")
```

**Returns:** `int` - New session ID

---

### `end_session(self, final_metrics: Dict[str, Any])`

End current session with final metrics.

```python
db.end_session({
    "total_ticks": 5000,
    "total_commands": 1200,
    "total_battles": 45,
    "badges_earned": 3,
    "final_state": {"location": "Cerulean City"}
})
```

**Parameters:**

| Field | Type | Description |
|-------|------|-------------|
| `total_ticks` | `int` | Total ticks executed |
| `total_commands` | `int` | Commands sent |
| `total_battles` | `int` | Battles encountered |
| `badges_earned` | `int` | Gym badges earned |
| `final_state` | `Dict` | Final game state |

---

## Logging Methods

### `log_screenshot(self, tick: int, file_path: str, game_state: Dict[str, Any])`

Log a screenshot capture event.

```python
db.log_screenshot(
    tick=1500,
    file_path="./game_saves/screenshots/tick_1500.png",
    game_state={"screen_type": "battle", "enemy": "Pidgey"}
)
```

---

### `log_command(self, command_data: Dict[str, Any])`

Log a command sent to emulator.

```python
db.log_command({
    "tick": 1500,
    "command_type": "press",
    "command_value": "A",
    "reasoning": "Use Tackle attack",
    "confidence": 0.85,
    "success": True,
    "execution_time_ms": 50
})
```

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `tick` | `int` | Current tick |
| `command_type` | `str` | "press", "hold", "sequence", "batch" |
| `command_value` | `str` | Actual button/command |
| `reasoning` | `str` | AI reasoning |
| `confidence` | `float` | Confidence (0-1) |
| `success` | `bool` | Whether command succeeded |
| `execution_time_ms` | `float` | Execution time |

---

### `log_ai_thought(self, thought_data: Dict[str, Any])`

Log AI thinking process.

```python
db.log_ai_thought({
    "tick": 1500,
    "thought_process": "Analyzing battle options",
    "reasoning": "Enemy is Grass type, use Fire",
    "game_context": {"enemy_hp": 50, "player_hp": 75},
    "proposed_action": "Use Ember",
    "confidence": 0.9,
    "model_used": "gpt-4o",
    "tokens_used": 500
})
```

---

### `log_battle_start(self, battle_data: Dict[str, Any]) -> int`

Start tracking a battle.

```python
battle_id = db.log_battle_start({
    "tick": 1500,
    "enemy_pokemon": "Pidgey",
    "enemy_level": 5,
    "player_pokemon": "Charmander",
    "player_level": 6
})
```

**Returns:** `int` - Battle ID

---

### `log_battle_end(self, battle_id: int, outcome: str, turns_taken: int)`

End a battle with outcome.

```python
db.log_battle_end(
    battle_id=1,
    outcome="victory",
    turns_taken=3
)
```

**Outcome Values:** `"victory"`, `"defeat"`, `"fled"`, `"caught"`

---

### `log_battle_turn(self, battle_id: int, turn_data: Dict[str, Any])`

Log a single battle turn.

```python
db.log_battle_turn(1, {
    "turn_number": 2,
    "player_action": "Ember",
    "enemy_action": "Tackle",
    "player_hp_before": 75,
    "player_hp_after": 60,
    "enemy_hp_before": 50,
    "enemy_hp_after": 25,
    "effectiveness": "super-effective"
})
```

---

## Query Methods

### `get_session_summary(self, session_id: int) -> Dict[str, Any]`

Get summary statistics for a session.

```python
summary = db.get_session_summary(1)
print(summary)
# {
#     "session_id": 1,
#     "total_ticks": 5000,
#     "total_battles": 45,
#     "wins": 40,
#     "losses": 5,
#     "win_rate": 0.89
# }
```

**Returns:** `Dict[str, Any]` with session and battle statistics

---

### `export_session_data(self, session_id: int, format: str = "json") -> str`

Export all session data for analysis.

```python
output_path = db.export_session_data(1)
print(f"Exported to: {output_path}")
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `session_id` | `int` | — | Session to export |
| `format` | `str` | `"json"` | Output format (json only for now) |

**Returns:** `str` - Path to exported file

**Exported Structure:**
```json
{
    "session": {...},
    "commands": [...],
    "thoughts": [...],
    "battles": [...],
    "screenshots": [...]
}
```

## Database Schema

### sessions

| Column | Type | Description |
|--------|------|-------------|
| session_id | INTEGER | Primary key |
| start_time | TEXT | Session start timestamp |
| end_time | TEXT | Session end timestamp |
| rom_path | TEXT | Path to ROM file |
| model_name | TEXT | AI model used |
| total_ticks | INTEGER | Total ticks executed |
| total_commands | INTEGER | Commands sent |
| total_battles | INTEGER | Battles encountered |
| badges_earned | INTEGER | Gym badges earned |
| final_state | TEXT | JSON final state |

### battles

| Column | Type | Description |
|--------|------|-------------|
| battle_id | INTEGER | Primary key |
| start_tick | INTEGER | Tick when battle started |
| end_tick | INTEGER | Tick when battle ended |
| enemy_pokemon | TEXT | Enemy species |
| enemy_level | INTEGER | Enemy level |
| player_pokemon | TEXT | Player's Pokemon |
| player_level | INTEGER | Player's Pokemon level |
| outcome | TEXT | victory/defeat/fled/caught |
| turns_taken | INTEGER | Number of turns |
| session_id | INTEGER | Foreign key |

## Usage Example

```python
from src.db.database import GameDatabase

# Initialize
db = GameDatabase("./game_data.db")

# Start session
session_id = db.start_session(
    rom_path="pokemon_red.gb",
    model_name="gpt-4o"
)

# Simulate gameplay
for tick in range(100):
    # ... game logic ...

    # Log command
    db.log_command({
        "tick": tick,
        "command_type": "press",
        "command_value": "A",
        "reasoning": "Action description",
        "confidence": 0.85,
        "success": True,
        "execution_time_ms": 50
    })

# Start battle
battle_id = db.log_battle_start({
    "tick": 150,
    "enemy_pokemon": "Rattata",
    "enemy_level": 3,
    "player_pokemon": "Pikachu",
    "player_level": 5
})

# Log turns
for turn in range(3):
    db.log_battle_turn(battle_id, {
        "turn_number": turn + 1,
        "player_action": "ThunderShock",
        "enemy_action": "Quick Attack",
        "player_hp_before": 100,
        "player_hp_after": 85,
        "enemy_hp_before": 100,
        "enemy_hp_after": 50,
        "effectiveness": "super-effective"
    })

# End battle
db.log_battle_end(battle_id, "victory", turns_taken=3)

# End session
db.end_session({
    "total_ticks": 500,
    "total_commands": 150,
    "total_battles": 5,
    "badges_earned": 0,
    "final_state": {"location": "Pallet Town"}
})

# Get summary
summary = db.get_session_summary(session_id)
print(f"Session completed: {summary}")

# Export for analysis
db.export_session_data(session_id)
```

## See Also

- [GameLoop](game_loop.md) - Session management
- [AICommand](ai_command.md) - Command logging
- [BattleState](battle_state.md) - Battle information