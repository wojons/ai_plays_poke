# ScreenshotManager

Manages screenshot capture, storage, and retrieval.

## Overview

The `ScreenshotManager` class handles capturing screenshots from the emulator, organizing them by game state (battle, overworld, menus), and providing methods for retrieval and visualization. It creates a live view for monitoring game progress.

## Class Signature

```python
class ScreenshotManager:
    def __init__(self, screenshot_dir: str)
```

## Constructor

### `__init__(self, screenshot_dir: str)`

Initialize the screenshot manager.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `screenshot_dir` | `str` | Base directory for storing screenshots |

**Directory Structure Created:**
```
screenshot_dir/
  battles/       # Battle screenshots
  overworld/     # Overworld screenshots
  menus/         # Menu screenshots
  *.png          # Uncategorized screenshots
```

**Example:**

```python
from src.core.screenshot_manager import ScreenshotManager

manager = ScreenshotManager("./game_saves/screenshots")
```

## Methods

### `save_screenshot(self, screenshot: np.ndarray, name_prefix: str, game_state: Optional[str] = None) -> Path`

Save screenshot to appropriate directory.

```python
screenshot = emulator.capture_screen()
path = manager.save_screenshot(
    screenshot,
    name_prefix="tick_1000",
    game_state="battle"
)
print(f"Saved: {path}")
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `screenshot` | `np.ndarray` | RGB numpy array (160x144) |
| `name_prefix` | `str` | Prefix for filename |
| `game_state` | `Optional[str]` | "battle", "overworld", "menu" or None |

**Returns:** `Path` to saved screenshot

---

### `get_latest_screenshot(self, game_state: Optional[str] = None) -> Optional[Path]`

Get path to most recent screenshot.

```python
latest = manager.get_latest_screenshot()
if latest:
    print(f"Latest screenshot: {latest}")
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `game_state` | `Optional[str]` | Filter by game state or None for all |

**Returns:** `Optional[Path]` to latest screenshot, or None

---

### `get_screenshot_as_base64(self, filepath: Path) -> str`

Convert screenshot to base64 for web display or API use.

```python
base64_str = manager.get_screenshot_as_base64(filepath)
# Use in HTML: <img src="data:image/png;base64,{base64_str}">
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `filepath` | `Path` | Path to screenshot file |

**Returns:** `str` - Base64 encoded image

---

### `create_grid_view(self, recent_count: int = 12, output_path: Optional[Path] = None) -> Path`

Create a grid view of recent screenshots.

```python
grid_path = manager.create_grid_view(
    recent_count=12,
    output_path=Path("./game_saves/grid.png")
)
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `recent_count` | `int` | `12` | Number of recent screenshots |
| `output_path` | `Optional[Path]` | `None` | Output path (auto-generated if None) |

**Returns:** `Path` to generated grid image

**Grid Layout:** 4 columns x N rows (based on count)

---

### `cleanup_old_screenshots(self, keep_count: int = 1000)`

Keep only the most recent screenshots.

```python
manager.cleanup_old_screenshots(keep_count=500)
# Deletes all but the 500 most recent screenshots
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `keep_count` | `int` | `1000` | Number of recent screenshots to keep |

---

### `get_screenshot_stats(self) -> Dict[str, int]`

Get statistics about stored screenshots.

```python
stats = manager.get_screenshot_stats()
print(stats)
# {
#     "total": 1500,
#     "battles": 450,
#     "overworld": 900,
#     "menus": 150
# }
```

**Returns:** `Dict[str, int]` with counts by category

---

## LiveView Class

Real-time view of game screenshots for monitoring.

### Constructor

```python
live = LiveView(screenshot_manager)
```

### Methods

#### `start_display(self)`

Start displaying screenshots in real-time.

```python
live.start_display()
# Opens OpenCV window with live view
# Press 'q' to close
```

#### `stop_display(self)`

Stop the live view display.

```python
live.stop_display()
```

#### `update_display(self, screenshot: np.ndarray)`

Update the live view with a new screenshot.

```python
screenshot = emulator.capture_screen()
live.update_display(screenshot)
```

#### `display_screenshot(self, filepath: Path, duration: float = 2.0)`

Display a specific screenshot for a duration.

```python
live.display_screenshot(Path("./screenshot.png"), duration=3.0)
```

## Usage Example

```python
import numpy as np
from pathlib import Path
from src.core.screenshot_manager import ScreenshotManager, LiveView

# Initialize
manager = ScreenshotManager("./game_saves/screenshots")
live = LiveView(manager)

# Start live view
live.start_display()

# Simulate game loop
for tick in range(100):
    # Capture screenshot
    screenshot = emulator.capture_screen()

    # Detect game state (simplified)
    game_state = detect_game_state(screenshot)

    # Save screenshot
    manager.save_screenshot(
        screenshot,
        name_prefix=f"tick_{tick}",
        game_state=game_state
    )

    # Update live view
    live.update_display(screenshot)

# Get stats
stats = manager.get_screenshot_stats()
print(f"Total screenshots: {stats['total']}")
print(f"Battles: {stats['battles']}")

# Create grid view
grid = manager.create_grid_view(recent_count=16)
print(f"Grid saved: {grid}")

# Cleanup old screenshots
manager.cleanup_old_screenshots(keep_count=500)

# Stop live view
live.stop_display()
```

## Integration with GameLoop

The `GameLoop` automatically uses `ScreenshotManager`:

```python
# In GameLoop.__init__
self.screenshot_manager = ScreenshotManager(str(self.save_dir / "screenshots"))

# In GameLoop._capture_and_process_screenshot
screenshot_path = self.screenshot_manager.save_screenshot(
    screenshot,
    f"tick_{self.current_tick}_{timestamp}"
)
```

## See Also

- [GameLoop](game_loop.md) - Main game loop
- [Vision Pipeline](not_implemented) - Screenshot analysis