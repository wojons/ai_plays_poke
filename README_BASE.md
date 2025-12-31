# AI Plays Pokemon - Base Foundation

## What's Been Built

We've created the foundational CLI system for the AI Plays Pokemon framework. Here's what's working:

### Core Components

1. **SQLite Database** (`src/db/database.py`)
   - Tracks all game events, AI decisions, battles, and stats
   - Tables: sessions, screenshots, commands, ai_thoughts, battles, performance_metrics
   - Stores AI thinking processes for later analysis
   - Exports session data as JSON

2. **Command Schemas** (`src/schemas/commands.py`)
   - Defines all AI → Emulator commands
   - Button press, hold, sequence, batch commands
   - AI thought process structures
   - Game state data classes

3. **Screenshot Manager** (`src/core/screenshots.py`)
   - Saves screenshots to organized directories
   - Maintains "latest" folder for live viewing
   - Captures metadata alongside images
   - Cleanup utilities

4. **Emulator Interface** (`src/core/emulator.py`)
   - Placeholder stub for PyBoy integration
   - Will wrap real emulator later
   - Currently provides test functionality

5. **Main CLI** (`src/game_loop.py`)
   - Full command-line interface
   - Starts/stops gracefully
   - Logs all actions to database
   - Manages the full loop: Screenshot → AI Decision → Execute → Log

## How to Use

### Basic Run
```bash
python src/game_loop.py --rom pokemon_red.gb --save-dir ./my_run
```

### With Custom Settings
```bash
python src/game_loop.py \
  --rom pokemon_red.gb \
  --save-dir ./my_run \
  --screenshot-interval 30 \
  --max-ticks 500
```

### With Multiple Instances (for comparing AI models later)
```bash
python src/game_loop.py \
  --rom pokemon_red.gb \
  --multi-instance \
  --instances 3
```

## Project Structure

```
ai_plays_poke/
├── src/
│   ├── db/
│   │   └── database.py          # SQLite tracking
│   ├── schemas/
│   │   └── commands.py          # Command definitions
│   └── core/
│       ├── emulator.py          # Emulator interface
│       └── screenshots.py       # Screenshot manager
├── game_saves/                 # Created at runtime
│   ├── game_data.db            # SQLite database
│   ├── screenshots/             # All screenshots
│   │   ├── battles/
│   │   ├── overworld/
│   │   ├── menus/
│   │   └── latest/             # Current screenshots
│   └── emulator_state.state     # Saved emulator state
└── src/game_loop.py             # Main CLI entry point
```

## CLI Flags

- `--rom`: Path to Pokemon ROM file (required)
- `--save-dir`: Directory for saves, DB, and screenshots (default: ./game_saves)
- `--screenshot-interval`: Ticks between screenshots (default: 60)
- `--load-state`: Load existing emulator state
- `--max-ticks`: Maximum ticks to run (optional)
- `--multi-instance`: Run multiple emulator instances
- `--instances`: Number of instances (default: 3)

## Database Schema

Key tables:
- **sessions**: Overall runs, start/end times, final stats
- **screenshots**: Screenshot events with file paths and game states
- **commands**: Every button press sent to emulator
- **ai_thoughts**: AI reasoning behind each decision
- **battles**: Battle start/end, Pokemon involved
- **battle_turns**: Per-turn battle data
- **performance_metrics**: Snapshots of performance over time

## Next Steps

1. **Fix imports**: Python needs proper imports (fix `from src.*` imports)
2. **Add PyBoy**: Integrate real PyBoy emulator
3. **Add AI models**: Connect to LLMs (local or API-based)
4. **Add vision processing**: Detect game state from screenshots
5. **Add Pokédex**: Integrate pypokedex for type matchups

## Run Example

```bash
# Test the foundation (stub mode)
python src/game_loop.py --rom pokemon_red.gb --save-dir ./test_run --max-ticks 500
```

This will run for 500 ticks (~8 seconds) and create:
- Database with session data
- Screenshot directory with images
- Log file with AI decisions
- Emulator state save file
