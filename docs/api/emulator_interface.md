# EmulatorInterface

Interface for Pokemon emulator using PyBoy.

## Overview

The `EmulatorInterface` class provides real PyBoy emulator integration for Pokemon games. It handles button presses, screenshot capture, and state management. Falls back to stub mode if PyBoy is unavailable.

## Class Signature

```python
class EmulatorInterface:
    def __init__(self, rom_path: str)
```

## Constructor

### `__init__(self, rom_path: str)`

Initialize emulator with ROM path.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `rom_path` | `str` | Path to Pokemon ROM file (.gb) |

**Behavior:**
- Attempts to load real PyBoy emulator
- Falls back to stub mode if PyBoy unavailable or ROM not found
- Prints initialization status

**Example:**

```python
from src.core.emulator_interface import EmulatorInterface

# Initialize with ROM
emulator = EmulatorInterface("pokemon_red.gb")

# Check if real emulation is available
if emulator.pyboy is not None:
    print("Using real PyBoy emulator")
else:
    print("Using stub emulator mode")
```

## Methods

### `start(self)`

Start the emulator.

```python
emulator.start()
```

**Behavior:**
- Starts PyBoy emulation if available
- Sets `is_running = True`

---

### `stop(self)`

Stop the emulator.

```python
emulator.stop()
```

**Behavior:**
- Stops PyBoy emulation
- Sets `is_running = False`

---

### `tick(self) -> bool`

Advance one frame (one tick).

```python
while emulator.is_running:
    emulator.tick()
    # 60 ticks = 1 second in GameBoy
```

**Returns:** `bool` - `False` when game should exit, `True` otherwise

---

### `capture_screen(self) -> np.ndarray`

Capture current game screen as RGB array.

```python
screenshot = emulator.capture_screen()
print(f"Screen shape: {screenshot.shape}")  # (144, 160, 3)
```

**Returns:** `numpy.ndarray` of shape `(144, 160, 3)` - RGB image

---

### `press_button(self, button: Button, duration_frames: int = 60)`

Press a button.

```python
from schemas.commands import Button

# Single button press
emulator.press_button(Button.A)

# Press for duration
emulator.press_button(Button.UP, duration_frames=120)  # 2 seconds
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `button` | `Button` | Button to press (A, B, START, SELECT, UP, DOWN, LEFT, RIGHT) |
| `duration_frames` | `int` | How long to hold (60 = 1 second) |

**Button Mapping:**
| Button | PyBoy Mapping |
|--------|---------------|
| `Button.A` | "a" |
| `Button.B` | "b" |
| `Button.START` | "start" |
| `Button.SELECT` | "select" |
| `Button.UP` | "up" |
| `Button.DOWN` | "down" |
| `Button.LEFT` | "left" |
| `Button.RIGHT` | "right" |

---

### `save_state(self, state_path: str) -> bool`

Save emulator state to file.

```python
success = emulator.save_state("./save.state")
if success:
    print("State saved successfully")
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `state_path` | `str` | Path to save state file |

**Returns:** `bool` - `True` if save was successful

---

### `load_state(self, state_path: str) -> bool`

Load emulator state from file.

```python
success = emulator.load_state("./save.state")
if success:
    print("State loaded successfully")
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `state_path` | `str` | Path to state file |

**Returns:** `bool` - `True` if load was successful

---

### `get_state_bytes(self) -> bytes`

Get emulator state as bytes for in-memory storage.

```python
state_data = emulator.get_state_bytes()
# Store in memory/database
```

**Returns:** `bytes` - Emulator state data

---

### `load_state_bytes(self, state_data: bytes) -> bool`

Load emulator state from bytes.

```python
state_data = db.get_saved_state()
emulator.load_state_bytes(state_data)
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `state_data` | `bytes` | State data bytes |

**Returns:** `bool` - `True` if load was successful

---

### `get_game_time(self) -> int`

Get in-game time in ticks.

```python
ticks = emulator.get_game_time()
print(f"Elapsed ticks: {ticks}")
```

**Returns:** `int` - Current tick count

---

### `is_in_battle(self) -> bool`

Check if currently in battle.

```python
if emulator.is_in_battle():
    print("In battle!")
```

**Returns:** `bool` - Whether in battle (stub always returns `False`)

---

### `is_running_state(self) -> bool`

Check if emulator is running.

```python
if emulator.is_running_state():
    print("Emulator is active")
```

**Returns:** `bool` - Running state

---

## EmulatorManager Class

Manager for multiple emulator instances.

### Constructor

```python
manager = EmulatorManager("pokemon_red.gb", instance_count=3)
```

### Methods

#### `get_instance(self, instance_id: str) -> EmulatorInterface`

Get a specific emulator instance.

```python
emulator = manager.get_instance("instance_0")
```

#### `start_all(self)`

Start all emulator instances.

```python
manager.start_all()
```

#### `stop_all(self)`

Stop all emulator instances.

```python
manager.stop_all()
```

#### `tick_all(self) -> dict`

Tick all emulators once.

```python
results = manager.tick_all()
# {"instance_0": True, "instance_1": True, "instance_2": True}
```

## Usage Example

```python
from pathlib import Path
from schemas.commands import Button
from src.core.emulator_interface import EmulatorInterface

# Initialize
emulator = EmulatorInterface("pokemon_red.gb")
emulator.start()

# Main loop
for tick in range(1000):
    # Advance emulator
    emulator.tick()

    # Capture and analyze screen every 60 ticks
    if tick % 60 == 0:
        screenshot = emulator.capture_screen()
        # Process screenshot...

    # Press button every 120 ticks
    if tick % 120 == 0:
        emulator.press_button(Button.A, duration_frames=30)

    # Save state every 1000 ticks
    if tick % 1000 == 0:
        emulator.save_state(f"./checkpoint_{tick}.state")

# Stop
emulator.stop()

# State management
emulator.save_state("./final.state")
```

## PyBoy Integration

When PyBoy is available, the interface uses:
- `pyboy.screen.ndarray` - For screenshot capture
- `pyboy.dumps()` - For state serialization
- `pyboy.loads()` - For state deserialization
- `pyboy.button_press()` / `pyboy.button_release()` - For input

## See Also

- [GameLoop](game_loop.md) - Main game loop
- [Button](../ai_command.md#button) - Button enum
- [AICommand](ai_command.md) - Command structure