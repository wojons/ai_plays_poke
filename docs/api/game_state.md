# GameState

Current game state snapshot for AI context.

## Overview

The `GameState` dataclass represents a snapshot of the current game state, used to provide context to AI models for decision making. It captures screen type, battle status, menu state, and other relevant information.

## Class Signature

```python
@dataclass
class GameState:
    tick: int
    timestamp: str
    screen_type: str

    # Battle state
    is_battle: bool
    is_menu: bool
    has_dialog: bool

    # Optional detailed state
    can_move: bool = True
    turn_number: int = 0
    enemy_pokemon: Optional[str] = None
    enemy_hp_percent: Optional[float] = None
    player_hp_percent: Optional[float] = None
    menu_type: Optional[str] = None
    cursor_position: Optional[tuple] = None
    dialog_text: Optional[str] = None
    location: Optional[str] = None
```

## Fields

### Core Fields

| Field | Type | Description |
|-------|------|-------------|
| `tick` | `int` | Current tick count |
| `timestamp` | `str` | ISO timestamp |
| `screen_type` | `str` | "battle", "overworld", "menu", "dialog", "transition" |

### State Flags

| Field | Type | Description |
|-------|------|-------------|
| `is_battle` | `bool` | Whether in battle |
| `is_menu` | `bool` | Whether menu is open |
| `has_dialog` | `bool` | Whether dialog is displayed |
| `can_move` | `bool` | Whether player can move (default: True) |

### Battle Information

| Field | Type | Description |
|-------|------|-------------|
| `turn_number` | `int` | Current battle turn (0 if not in battle) |
| `enemy_pokemon` | `Optional[str]` | Enemy Pokemon name |
| `enemy_hp_percent` | `Optional[float]` | Enemy HP percentage (0-100) |
| `player_hp_percent` | `Optional[float]` | Player Pokemon HP percentage (0-100) |

### Menu Information

| Field | Type | Description |
|-------|------|-------------|
| `menu_type` | `Optional[str]` | "pokemon", "bag", "main", "options", etc. |
| `cursor_position` | `Optional[tuple]` | (x, y) position on menu grid |

### Dialog Information

| Field | Type | Description |
|-------|------|-------------|
| `dialog_text` | `Optional[str]` | Current dialog text content |
| `location` | `Optional[str]` | Current location name |

## Screen Types

| Value | Description |
|-------|-------------|
| `"battle"` | Active Pokemon battle |
| `"overworld"` | Free movement in game world |
| `"menu"` | Menu screen open |
| `"dialog"` | Text dialog displayed |
| `"transition"` | Screen transition occurring |

## Methods

### `to_dict(self) -> Dict[str, Any]`

Convert to dictionary for API/logging.

```python
state = GameState(
    tick=1500,
    timestamp="2025-12-31T12:00:00",
    screen_type="battle",
    is_battle=True,
    is_menu=False,
    has_dialog=False,
    enemy_pokemon="Pidgey",
    enemy_hp_percent=50.0,
    player_hp_percent=75.0
)

data = state.to_dict()
```

**Returns:** `Dict[str, Any]` - Dictionary representation

---

## Usage Examples

### Creating a Battle State

```python
from schemas.commands import GameState

battle_state = GameState(
    tick=1500,
    timestamp="2025-12-31T12:00:00",
    screen_type="battle",
    is_battle=True,
    is_menu=False,
    has_dialog=False,
    turn_number=2,
    enemy_pokemon="Pidgey",
    enemy_hp_percent=50.0,
    player_hp_percent=75.0
)

print(f"Enemy: {battle_state.enemy_pokemon} ({battle_state.enemy_hp_percent}%)")
print(f"Player: {battle_state.player_hp_percent}%")
```

### Creating an Overworld State

```python
overworld_state = GameState(
    tick=100,
    timestamp="2025-12-31T12:00:00",
    screen_type="overworld",
    is_battle=False,
    is_menu=False,
    has_dialog=False,
    location="Pallet Town"
)
```

### Creating a Menu State

```python
menu_state = GameState(
    tick=200,
    timestamp="2025-12-31T12:01:00",
    screen_type="menu",
    is_battle=False,
    is_menu=True,
    has_dialog=False,
    menu_type="bag",
    cursor_position=(0, 1)  # Second item in list
)
```

### Creating a Dialog State

```python
dialog_state = GameState(
    tick=300,
    timestamp="2025-12-31T12:02:00",
    screen_type="dialog",
    is_battle=False,
    is_menu=False,
    has_dialog=True,
    dialog_text="Hello! I'm Professor Oak!"
)
```

### Using with AI Decision Making

```python
def make_decision(state: GameState) -> str:
    if state.screen_type == "battle":
        if state.enemy_hp_percent and state.enemy_hp_percent < 20:
            return "Use Poké Ball to catch"
        else:
            return "Use attack move"
    elif state.screen_type == "menu":
        return "Select menu item"
    elif state.has_dialog:
        return "Press A to advance dialog"
    else:
        return "Move in current direction"

state = GameState(...)
action = make_decision(state)
```

### Serialization

```python
import json
from schemas.commands import GameState

state = GameState(...)

# To JSON
json_str = json.dumps(state.to_dict())

# From JSON
state_dict = json.loads(json_str)
state = GameState(**state_dict)
```

## Integration with GameLoop

The `GameLoop` uses `GameState` to track current state:

```python
# In GameLoop._analyze_screenshot
game_state = GameState(
    tick=self.current_tick,
    timestamp=datetime.now().isoformat(),
    screen_type=self._detect_screen_type(screenshot),
    is_battle=self._detect_battle(screenshot),
    is_menu=self._detect_menu(screenshot),
    has_dialog=self._detect_dialog(screenshot)
)
```

## See Also

- [BattleState](battle_state.md) - Detailed battle information
- [AICommand](ai_command.md) - Commands generated from game state
- [GameAIManager](game_ai_manager.md) - AI that uses game state for decisions