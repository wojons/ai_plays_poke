---
name: ai-plays-poke
description: "Autonomous Pokémon AI benchmarking system — PyBoy emulator, RAM-based game state reader, GOAP planner, vision pipeline. ~53,500 lines of specifications."
version: 0.3.0
language: Python
platforms: [linux]
---

# AI Plays Pokémon (PTP-01X)

Autonomous Pokémon AI benchmarking system using PyBoy 2.7.0 emulator with RAM-based game state reading, GOAP hierarchical planning, and LLM-driven decision making.

## Quick Start

```bash
# Setup
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run tests
pytest tests/ -v

# Start RAM map viewer
python ram_map_server.py
# Then open http://localhost:8099

# Run autonomous game loop
python cron_runner.py
```

## Architecture

- **RAM Reader** (`src/core/ram_reader.py`) — Reads game state directly from emulator memory (instant, no LLM cost)
- **Emulator** (`src/core/emulator.py`) — PyBoy wrapper with read_u8/read_u16, tick, screenshot
- **GOAP Planner** (`src/core/goap.py`) — Hierarchical goal-oriented action planning
- **State Machine** (`src/core/state_machine.py`) — 50+ gameplay states with hierarchical transitions
- **State Window** (`src/core/state_window.py`) — AI decision context window for LLM prompts
- **Vision Pipeline** (`src/core/vision/`) — Screenshot preprocessing, sprite detection, OCR, location detection
- **Database** (`src/core/db/`) — SQLite session metrics, screenshots, AI thoughts, commands
- **Cron Runner** (`cron_runner.py`) — Autonomous game loop with RAM reader or vision cartographer

## Test Suite

```bash
# Full suite (3357 tests, 8 skipped)
pytest tests/ -v

# Fast run (skip ROM/API tests)
pytest tests/ -x -q --tb=short -k "not rom and not live"

# With coverage
pytest tests/ -v --cov=src --cov-report=html --cov-report=term-missing

# Parallel
pytest tests/ -n auto -v
```

## Lint & Type Check

```bash
ruff check src/
ruff check --fix src/
mypy --strict src/
```

## Key Files

| File | Lines | Purpose |
|------|-------|---------|
| `src/core/ram_reader.py` | 1049 | RAM-based game state reader + text renderer |
| `src/core/emulator.py` | ~450 | PyBoy emulator wrapper |
| `src/core/goap.py` | ~744 | GOAP hierarchical planner |
| `src/core/state_machine.py` | ~432 | Hierarchical state machine |
| `src/core/state_window.py` | ~250 | AI decision window |
| `cron_runner.py` | 888 | Autonomous game loop |
| `ram_map_server.py` | 138 | Live RAM map viewer server |
| `specs/` | 53,500+ | Detailed specifications |

## ROM

Place Pokémon Red `.gb` ROM at `data/rom/pokemon_red.gb`.
