# AICommand

Represents an AI-generated command for the emulator.

## Overview

The `AICommand` dataclass encapsulates a button press or action to be executed by the emulator. It includes the command type, reasoning, confidence, and timing information.

## Class Signature

```python
@dataclass
class AICommand:
    command_type: CommandType
    reasoning: str
    confidence: float
    tick: int
    timestamp: str

    # Optional command-specific fields
    button: Optional[Button] = None
    button_sequence: Optional[List[Button]] = None
    duration_ms: Optional[int] = None
    wait_ticks: int = 60
    batch_direction: Optional[str] = None
    batch_steps: int = 0
```

## Fields

### Core Fields

| Field | Type | Description |
|-------|------|-------------|
| `command_type` | `CommandType` | Type of command (PRESS, HOLD, RELEASE, SEQUENCE, BATCH, WAIT) |
| `reasoning` | `str` | AI's reasoning for this command |
| `confidence` | `float` | AI confidence in this command (0.0-1.0) |
| `tick` | `int` | Tick when command was created |
| `timestamp` | `str` | ISO timestamp of command creation |

### Command-Specific Fields

| Field | Type | Used With | Description |
|-------|------|-----------|-------------|
| `button` | `Optional[Button]` | PRESS, HOLD, RELEASE | Button to press |
| `button_sequence` | `Optional[List[Button]]` | SEQUENCE | List of buttons in sequence |
| `duration_ms` | `Optional[int]` | HOLD | Duration to hold in milliseconds |
| `wait_ticks` | `int` | WAIT | Number of ticks to wait |
| `batch_direction` | `Optional[str]` | BATCH | Direction (UP, DOWN, LEFT, RIGHT) |
| `batch_steps` | `int` | BATCH | Number of steps |

## CommandType Enum

```python
class CommandType(str, Enum):
    PRESS = "press"       # Single button press
    HOLD = "hold"         # Hold button for duration
    RELEASE = "release"   # Release held button
    SEQUENCE = "sequence" # Sequence of buttons
    BATCH = "batch"       # Batched movement
    WAIT = "wait"         # Wait for specified time
```

## Button Enum

```python
class Button(str, Enum):
    A = "A"
    B = "B"
    START = "START"
    SELECT = "SELECT"
    UP = "UP"
    DOWN = "DOWN"
    LEFT = "LEFT"
    RIGHT = "RIGHT"
```

## Methods

### `to_dict(self) -> Dict[str, Any]`

Convert to dictionary for logging.

```python
cmd = AICommand(...)
data = cmd.to_dict()
# {
#     "command_type": "press",
#     "button": "A",
#     "reasoning": "Use Ember attack",
#     "confidence": 0.85,
#     ...
# }
```

**Returns:** `Dict[str, Any]` - Dictionary representation

---

### `to_string(self) -> str`

Convert to simple string format.

```python
cmd = AICommand(
    command_type=CommandType.PRESS,
    button=Button.A,
    ...
)
print(cmd.to_string())  # "press:A"

# Sequence
cmd = AICommand(
    command_type=CommandType.SEQUENCE,
    button_sequence=[Button.UP, Button.UP, Button.A],
    ...
)
print(cmd.to_string())  # "sequence:UP,UP,A"

# Batch
cmd = AICommand(
    command_type=CommandType.BATCH,
    batch_direction="UP",
    batch_steps=10,
    ...
)
print(cmd.to_string())  # "batch:UPx10"

# Wait
cmd = AICommand(
    command_type=CommandType.WAIT,
    wait_ticks=120,
    ...
)
print(cmd.to_string())  # "wait:120"
```

**Returns:** `str` - String representation

---

## Factory Functions

### `create_press_command(button: Button, reasoning: str, tick: int, confidence: float = 0.8) -> AICommand`

Create a simple press button command.

```python
from schemas.commands import Button, create_press_command

cmd = create_press_command(
    button=Button.A,
    reasoning="Use Ember attack",
    tick=1500,
    confidence=0.85
)
```

---

### `create_batch_command(direction: str, steps: int, reasoning: str, tick: int, confidence: float = 0.8) -> AICommand`

Create a batch navigation command.

```python
cmd = create_batch_command(
    direction="UP",
    steps=5,
    reasoning="Navigate north",
    tick=1500
)
```

---

## Helper Functions

### `parse_command_string(command_str: str) -> Optional[Dict[str, Any]]`

Parse command string to components.

```python
result = parse_command_string("press:A")
# {"command_type": "press", "button": "A"}

result = parse_command_string("batch:UPx10")
# {"command_type": "batch", "batch_direction": "UP", "batch_steps": 10}

result = parse_command_string("sequence:UP,UP,LEFT,A")
# {"command_type": "sequence", "button_sequence": ["UP", "UP", "LEFT", "A"]}
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `command_str` | `str` | Command string (e.g., "press:A") |

**Returns:** `Optional[Dict[str, Any]]` - Parsed components or None if invalid

---

## Usage Examples

### Basic Press Command

```python
from schemas.commands import AICommand, CommandType, Button

cmd = AICommand(
    command_type=CommandType.PRESS,
    button=Button.A,
    reasoning="Attack with ThunderShock",
    confidence=0.9,
    tick=1500,
    timestamp="2025-12-31T12:00:00"
)

# Convert to string for logging
print(cmd.to_string())  # "press:A"
```

### Sequence Command

```python
cmd = AICommand(
    command_type=CommandType.SEQUENCE,
    button_sequence=[Button.UP, Button.UP, Button.LEFT, Button.A],
    reasoning="Navigate menu to select option",
    confidence=0.75,
    tick=1600,
    timestamp="2025-12-31T12:01:00"
)

print(cmd.to_string())  # "sequence:UP,UP,LEFT,A"
```

### Batch Movement

```python
cmd = AICommand(
    command_type=CommandType.BATCH,
    batch_direction="DOWN",
    batch_steps=10,
    reasoning="Walk down path",
    confidence=0.8,
    tick=1700,
    timestamp="2025-12-31T12:02:00"
)

print(cmd.to_string())  # "batch:DOWNx10"
```

### Using Factory Functions

```python
from schemas.commands import create_press_command, create_batch_command, Button

# Create press command
cmd = create_press_command(
    button=Button.A,
    reasoning="Select move",
    tick=100,
    confidence=0.85
)

# Create batch command
cmd = create_batch_command(
    direction="RIGHT",
    steps=20,
    reasoning="Move to next area",
    tick=200
)
```

### Parsing Command Strings

```python
from schemas.commands import parse_command_string

# Parse various formats
press = parse_command_string("press:A")
sequence = parse_command_string("sequence:UP,DOWN,LEFT,RIGHT")
batch = parse_command_string("batch:UPx5")

if press:
    print(f"Command: {press['command_type']}, Button: {press['button']}")
```

## See Also

- [Button](#button) - Button enum
- [CommandType](#commandtype) - Command type enum
- [GameState](game_state.md) - Game state context for commands
- [GameAIManager](game_ai_manager.md) - AI that generates commands