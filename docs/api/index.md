---
title: PTP-01X API Documentation
---

# PTP-01X API Documentation

## Overview

This section documents all public APIs and interfaces for PTP-01X - an orchestrated intelligence framework for autonomous Pokémon gameplay. The API provides programmatic access to the game loop, AI decision making, screenshot management, and data persistence.

## Quick Links

### Core Classes

| Class | Description |
|-------|-------------|
| [GameLoop](game_loop.md) | Main game loop orchestration |
| [GameAIManager](game_ai_manager.md) | AI decision making and model coordination |
| [ScreenshotManager](screenshot_manager.md) | Screenshot capture and organization |
| [Database](database.md) | SQLite data persistence |
| [EmulatorInterface](emulator_interface.md) | PyBoy emulator control |

### Data Structures

| Class | Description |
|-------|-------------|
| [AICommand](ai_command.md) | Command representation for emulator actions |
| [GameState](game_state.md) | Game state snapshot for AI context |
| [BattleState](battle_state.md) | Detailed battle information |

### Examples

| Example | Description |
|---------|-------------|
| [Basic Usage](examples/basic_usage.md) | Initialize and run a game session |
| [Custom AI Integration](examples/custom_ai.md) | Integrate custom AI models |
| [Data Export](examples/data_export.md) | Export session data for analysis |

## Installation

```bash
# API documentation is generated from docstrings
# No additional installation required
```

## Usage

Import and use the classes directly:

```python
from src.core.game_loop import GameLoop
from src.core.ai_client import GameAIManager
from src.db.database import GameDatabase
from src.schemas.commands import AICommand, Button

# Initialize components
db = GameDatabase("game_data.db")
ai_manager = GameAIManager()

# Create game loop with emulator interface
from src.core.emulator_interface import EmulatorInterface
emulator = EmulatorInterface("pokemon_red.gb")

# Run session
loop = GameLoop(
    rom_path=Path("pokemon_red.gb"),
    save_dir=Path("./saves"),
    screenshot_interval=1.0
)
loop.start()
```

## Version

- **Last Updated:** December 2025
- **API Version:** 1.0.0
- **Framework Version:** PTP-01X

## Related Documentation

- [Technical Specifications](../../specs/technical_specifications_v5_complete.md)
- [Architecture Documentation](../../docs/architecture.md)
- [Runbook](../../README.md)