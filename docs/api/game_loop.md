# GameLoop

Main game loop coordinator for AI Plays Pokemon.

## Overview

The `GameLoop` class manages the complete flow of gameplay automation: capturing screenshots, analyzing game state, making AI decisions, executing commands, and logging results. It coordinates all other components including the emulator, AI manager, screenshot manager, and database.

## Class Signature

```python
class GameLoop:
    def __init__(
        self,
        rom_path: Path,
        save_dir: Path,
        screenshot_interval: float = 1.0,
        ai_response_delay: float = 0.5
    )
```

## Constructor

### `__init__(self, rom_path: Path, save_dir: Path, screenshot_interval: float = 1.0, ai_response_delay: float = 0.5)`

Initialize the game loop with configuration.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `rom_path` | `Path` | — | Path to Pokemon ROM file (.gb) |
| `save_dir` | `Path` | — | Directory for saves, DB, and screenshots |
| `screenshot_interval` | `float` | `1.0` | Seconds between screenshots |
| `ai_response_delay` | `float` | `0.5` | Seconds to wait for AI processing |

**Example:**

```python
from pathlib import Path

loop = GameLoop(
    rom_path=Path("pokemon_red.gb"),
    save_dir=Path("./game_saves"),
    screenshot_interval=0.5,  # Capture every 500ms
    ai_response_delay=1.0     # Wait 1s for AI decisions
)
```

## Methods

### `start(self)`

Start the game loop and initialize the emulator.

```python
loop.start()
```

**Behavior:**
- Starts the PyBoy emulator
- Initializes all internal components
- Begins the main tick loop
- Sets `is_running = True`

**Output:**
```
Starting AI Plays Pokemon
ROM: pokemon_red.gb
Save Directory: ./game_saves
Emulator started. Beginning game loop...
```

---

### `stop(self)`

Stop the game loop and save state.

```python
loop.stop()
```

**Behavior:**
- Saves emulator state to `save_dir/emulator_state.state`
- Logs final metrics to database
- Stops the emulator
- Prints final statistics

**Output:**
```
Stopping game loop...
Emulator state saved to ./game_saves/emulator_state.state
Final Stats:
   Ticks: 1500
   Screenshots: 1500
   Commands: 450
   Battles: 12
```

---

### `run_single_tick(self)`

Execute one iteration of the game loop.

```python
loop.run_single_tick()
```

**Behavior:**
1. Advances the emulator by one tick
2. Captures screenshot if interval elapsed
3. Detects game state changes
4. Executes pending AI commands

**Returns:** `None`

---

### `is_running` (property)

Check if the game loop is active.

```python
if loop.is_running:
    print("Loop is active")
```

**Type:** `bool`

---

## Internal Methods

These methods are used internally and not typically called directly.

### `_capture_and_process_screenshot(self)`

Capture screenshot, save it, and analyze game state.

### `_analyze_screenshot(self, screenshot: np.ndarray) -> Dict[str, Any]`

Analyze screenshot to determine game state.

**Returns:**
```python
{
    "is_battle": bool,
    "has_dialog": bool,
    "is_menu": bool,
    "requires_ai_decision": bool
}
```

### `_detect_battle_transition(self)`

Detect when battle starts/ends.

## Metrics

The game loop tracks performance metrics:

```python
loop.metrics = {
    "total_ticks": int,
    "screenshots_taken": int,
    "commands_sent": int,
    "battles_encountered": int,
    "start_time": datetime
}
```

## Usage Example

```python
from pathlib import Path
from src.core.game_loop import GameLoop

# Initialize
loop = GameLoop(
    rom_path=Path("pokemon_red.gb"),
    save_dir=Path("./saves/run1"),
    screenshot_interval=1.0
)

# Start and run for 100 ticks
loop.start()
for _ in range(100):
    loop.run_single_tick()

# Stop and save
loop.stop()

print(f"Completed {loop.metrics['total_ticks']} ticks")
```

## See Also

- [GameAIManager](game_ai_manager.md) - AI decision making
- [EmulatorInterface](emulator_interface.md) - Emulator control
- [Database](database.md) - Data logging