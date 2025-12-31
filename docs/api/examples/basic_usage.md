# Basic Usage Example

## Initialize and Run

This example demonstrates how to initialize the game loop and run a basic session.

```python
from pathlib import Path
from src.core.game_loop import GameLoop

# Configure the game loop
loop = GameLoop(
    rom_path=Path("pokemon_red.gb"),
    save_dir=Path("./game_saves"),
    screenshot_interval=1.0,  # Capture every second
    ai_response_delay=0.5     # Wait 500ms for AI
)

# Start the session
loop.start()

# Run for a specific number of ticks
for _ in range(1000):
    loop.run_single_tick()

# Stop and save
loop.stop()

print(f"Session completed: {loop.metrics['total_ticks']} ticks")
print(f"Commands executed: {loop.metrics['commands_sent']}")
```

## Accessing Results

After a session completes, you can access various metrics and data:

```python
from pathlib import Path
from src.core.game_loop import GameLoop

loop = GameLoop(
    rom_path=Path("pokemon_red.gb"),
    save_dir=Path("./results")
)

loop.start()

# Run session
for _ in range(5000):
    loop.run_single_tick()

loop.stop()

# Get session statistics
print(f"Duration ticks: {loop.metrics['total_ticks']}")
print(f"Screenshots captured: {loop.metrics['screenshots_taken']}")
print(f"Commands sent: {loop.metrics['commands_sent']}")
print(f"Battles encountered: {loop.metrics['battles_encountered']}")

# Access state
print(f"Current tick: {loop.current_tick}")
```

## Database Integration

The game loop automatically logs to a SQLite database:

```python
from pathlib import Path
from src.core.game_loop import GameLoop

loop = GameLoop(
    rom_path=Path("pokemon_red.gb"),
    save_dir=Path("./data")
)

loop.start()

# Run session
for _ in range(1000):
    loop.run_single_tick()

loop.stop()

# Access database directly
from src.db.database import GameDatabase
db = GameDatabase("./data/game_data.db")

# Get session summary
summary = db.get_session_summary(session_id=1)
print(f"Session summary: {summary}")

# Export data
export_path = db.export_session_data(session_id=1)
print(f"Exported to: {export_path}")
```

## Error Handling

The game loop handles errors gracefully:

```python
from pathlib import Path
from src.core.game_loop import GameLoop

loop = GameLoop(
    rom_path=Path("pokemon_red.gb"),
    save_dir=Path("./saves")
)

try:
    loop.start()

    # Run with error handling
    for tick in range(1000):
        try:
            loop.run_single_tick()
        except Exception as e:
            print(f"Error at tick {tick}: {e}")
            continue

    loop.stop()

except KeyboardInterrupt:
    print("\nInterrupted by user")
    loop.stop()

except Exception as e:
    print(f"Fatal error: {e}")
    raise
```

## CLI Usage

The game loop also supports CLI arguments:

```bash
# Basic run with default settings
python -m src.core.game_loop --rom "pokemon_red.gb" --save-dir "./saves"

# Fast screenshots (500ms interval)
python -m src.core.game_loop --rom "pokemon_red.gb" --screenshot-interval 0.5

# Start from existing save state
python -m src.core.game_loop --rom "pokemon_red.gb" --load-state "checkpoint.state"

# Run for specific number of ticks
python -m src.core.game_loop --rom "pokemon_red.gb" --max-ticks 10000
```

## Next Steps

- [Custom AI Integration](custom_ai.md) - Integrate custom AI models
- [Data Export](data_export.md) - Export and analyze session data
- [API Reference](../index.md) - Full API documentation