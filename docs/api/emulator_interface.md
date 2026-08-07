# Emulator

Unified PyBoy emulator wrapper for Pokemon games.

## Overview

The `Emulator` class (in `src/core/emulator.py`) provides real PyBoy emulator integration for Pokemon games. It handles button presses, screenshot capture, state save/load, RAM reads, and lifecycle management. There is **no stub fallback**: if the ROM file does not exist, the constructor raises `FileNotFoundError`.

## Class Signature

```python
class Emulator:
    def __init__(self, rom_path: str | Path) -> None
```

The module also exports a `Button` compat object with the button names `A`, `B`, `START`, `SELECT`, `UP`, `DOWN`, `LEFT`, `RIGHT` (each maps to a lowercase string such as `"a"`, `"start"`).

## Constructor

### `__init__(self, rom_path: str | Path)`

Initialize the emulator with a ROM path.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `rom_path` | `str` \| `Path` | Path to Pokemon ROM file (.gb) |

**Behavior:**
- Resolves the path and raises `FileNotFoundError` if the ROM file does not exist
- Creates a headless PyBoy instance (`window="null"`, `sound=False`)
- Sets `is_gb = True` (PyBoy only supports GB/GBC)

**Example:**

```python
from src.core.emulator import Emulator

# Initialize with ROM
emulator = Emulator("data/rom/Pokemon - Blue Version (USA, Europe) (SGB Enhanced).gb")

# Properties
print(emulator.is_gb)       # True
print(emulator.platform)    # "gb"
print(emulator.rom_path)    # PosixPath('.../Pokemon - Blue Version (USA, Europe) (SGB Enhanced).gb')
```

## Properties

### `is_gb` -> `bool`

Whether the loaded ROM is a Game Boy (GB/GBC) game. Always `True` for PyBoy.

### `platform` -> `str`

Platform name, always `"gb"`.

### `rom_path` -> `Path`

Resolved path of the loaded ROM file.

## Methods

### `start(self)`

Compatibility alias for `reset()` — (re)starts the emulator.

```python
emulator.start()
```

---

### `stop(self)`

Stop the emulator and release resources.

```python
emulator.stop()
```

**Behavior:**
- Stops PyBoy and sets the internal running flag to `False`
- Safe to call multiple times

---

### `reset(self)`

Reset the emulator to its initial state (stops the current PyBoy instance and creates a fresh one from the same ROM).

```python
emulator.reset()
```

---

### `tick(self, frames: int = 1)`

Advance by *frames* frames (one frame = one Game Boy tick; 60 ticks ≈ 1 second).

```python
emulator.tick()       # advance 1 frame
emulator.tick(60)     # advance 1 second
```

**Returns:** `None`

---

### `wait(self, frames: int)`

Advance by *frames* frames without pressing any button.

```python
emulator.wait(30)
```

---

### `fast_forward(self, frames: int)`

Run *frames* at maximum emulator speed without rendering (the screen is re-rendered on the next `capture()` call).

```python
emulator.fast_forward(120)
```

---

### `capture(self) -> np.ndarray`

Capture the current game screen as an RGB numpy array.

```python
screenshot = emulator.capture()
print(f"Screen shape: {screenshot.shape}")  # (144, 160, 3)
```

**Returns:** `numpy.ndarray` of shape `(144, 160, 3)` — RGB image

---

### `capture_screen(self) -> np.ndarray`

Compatibility alias for `capture()`.

```python
screenshot = emulator.capture_screen()
```

**Returns:** `numpy.ndarray` of shape `(144, 160, 3)` — RGB image

---

### `press_button(self, button: str, frames: int = 5)`

Press and hold a single button for *frames*, then release it.

```python
from src.core.emulator import Emulator, Button

# Single button press
emulator.press_button(Button.A)

# Press for duration (2 seconds at 60 fps)
emulator.press_button(Button.UP, frames=120)
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `button` | `str` | Button name: `a`, `b`, `start`, `select`, `up`, `down`, `left`, `right` (case-insensitive) |
| `frames` | `int` | How long to hold (60 = 1 second) |

**Raises:** `ValueError` if the button name is unknown

**Button Mapping:**

| Button | String value |
|--------|--------------|
| `Button.A` | `"a"` |
| `Button.B` | `"b"` |
| `Button.START` | `"start"` |
| `Button.SELECT` | `"select"` |
| `Button.UP` | `"up"` |
| `Button.DOWN` | `"down"` |
| `Button.LEFT` | `"left"` |
| `Button.RIGHT` | `"right"` |

---

### `combo(self, buttons: list[str], frames: int = 5)`

Press multiple buttons simultaneously for *frames*, then release them all.

```python
emulator.combo(["a", "up"], frames=30)
```

**Raises:** `ValueError` if any button name is unknown

---

### `skip_intro(self, *, press_frames: int = 30, wait_frames: int = 60, repetitions: int = 16)`

Advance past the game intro by A-mashing.

```python
emulator.skip_intro()
```

---

### `bypass_title(self)`

Press START to get past the Gen 1 title screen.

```python
emulator.bypass_title()
```

---

### `enter_name(self, name: str = "ASH")`

Mechanically enter a name on the Gen 1 keyboard screen (uppercased, max 7 chars).

```python
emulator.enter_name("ASH")
```

---

### `submit_name(self)`

Confirm the entered name (navigates from the A key to END and accepts).

```python
emulator.submit_name()
```

---

### `save_state(self, slot: int)`

Save a full emulator checkpoint to a numbered slot under `checkpoints/`.

```python
emulator.save_state(1)  # writes checkpoints/1.state
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `slot` | `int` | Checkpoint slot number |

**Returns:** `None` — the state file is `checkpoints/{slot}.state`

---

### `load_state(self, slot: int)`

Restore a full emulator checkpoint from a numbered slot.

```python
emulator.load_state(1)  # reads checkpoints/1.state
```

**Raises:** `FileNotFoundError` if the checkpoint slot does not exist

---

### `read_u8(self, addr: int) -> int`

Read a single byte from emulated Game Boy memory.

```python
value = emulator.read_u8(0xC0A0)
```

---

### `read_u16(self, addr: int) -> int`

Read a 16-bit little-endian word from memory.

```python
value = emulator.read_u16(0xC0A0)
```

---

## Usage Example

```python
from src.core.emulator import Emulator, Button

# Initialize
emulator = Emulator("data/rom/Pokemon - Blue Version (USA, Europe) (SGB Enhanced).gb")

# Main loop
for tick in range(1000):
    # Advance emulator
    emulator.tick()

    # Capture and analyze screen every 60 ticks
    if tick % 60 == 0:
        screenshot = emulator.capture()
        # Process screenshot...

    # Press button every 120 ticks
    if tick % 120 == 0:
        emulator.press_button(Button.A, frames=30)

    # Save state every 1000 ticks
    if tick % 1000 == 0:
        emulator.save_state(1)

# Stop
emulator.stop()
```

## PyBoy Integration

The `Emulator` wrapper uses PyBoy internally:

- `pyboy.screen.ndarray` — For screenshot capture (RGBA converted to RGB, `(144, 160, 3)`)
- `pyboy.send_input(WindowEvent.PRESS_*)` / `WindowEvent.RELEASE_*` — For input
- `pyboy.tick(frames, render=...)` — Frame advancement (render disabled during fast-forward)
- `pyboy.save_state(fh)` / `pyboy.load_state(fh)` — Checkpoint serialization (slots under `checkpoints/`)
- `pyboy.memory[addr]` — Direct memory reads
- The emulator is created with `window="null"` and `sound=False` (headless)

## See Also

- [GameLoop](game_loop.md) - Main game loop
- [Button](../ai_command.md#button-enum) - Button names
- [AICommand](ai_command.md) - Command structure
