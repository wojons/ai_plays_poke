# PTP-01X - Orchestrated Intelligence Framework for Autonomous Pokémon Gameplay

🎮 **A fundamentally different AI gaming approach** that shifts from Reinforcement Learning training loops to Orchestrated Intelligence with hierarchical memory and strategic reasoning.

## The Paradigm Shift

Current AI gaming projects fail because they treat Pokémon as a simple button-pressing problem. **PTP-01X** understands the truth:

- **50+ distinct gameplay states** - not just "battle", "overworld", "menu"
- **20+ hour gameplay journey** with interconnected strategic decisions
- **151 Pokémon** to catalog, learn types, moves, and abilities
- **8 Gyms + Elite Four** requiring team composition planning

### Why Simple AI Fails

| Approach | Problem | PTP-01X Solution |
|----------|---------|------------------|
| Stochastic Parrot | Throws pixels at model, hopes for correlation | Multi-phase state machine recognition |
| Context Amnesia | Treats every tick as independent | 3-tier memory hierarchy (Observer → Strategist → Tactician) |
| Memory Hoarding | Keeps all data until token limits hit | Intelligent compression & retrieval |
| No Strategic Planning | Immediate tactics only | GOAP decision core with hierarchical layers |

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    PTP-01X ORCHESTRATION LAYER                   │
├─────────────────────────────────────────────────────────────────┤
│  Observer (Long-term)  │  Strategist (Session)  │  Tactician   │
│  • Journey progress    │  • Battle lessons      │  • HP/status │
│  • Badge history       │  • Route knowledge     │  • Active    │
│  • Party evolution     │  • Resource strategies │  • Immediate │
│  • Meta-analysis       │  • Failure analysis    │  objectives  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      GOAP DECISION CORE                          │
│  • Goal stack management      • Hierarchical planning layers    │
│  • Critical path analysis     • Action execution with recovery  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    PERCEPTION & EXECUTION                        │
│  • Vision & OCR pipeline      • Hierarchical state machine      │
│  • Battle heuristics          • World navigation & pathfinding  │
│  • Entity management          • Inventory & item logistics      │
│  • Dialogue systems           • Failsafe & recovery protocols   │
└─────────────────────────────────────────────────────────────────┘
```

## Complete Specification

**~53,500 lines** of comprehensive technical documentation covering all aspects of autonomous Pokémon gameplay:

| Chapter | Focus | Lines |
|---------|-------|-------|
| 1 | Vision & Perception Engine | ~1,500 |
| 2 | Hierarchical State Machine | ~1,200 |
| 3 | Tactical Combat Heuristics | ~1,300 |
| 4 | World Navigation & Spatial Memory | ~1,500 |
| 5 | Data Persistence & Cognitive Schema | ~1,400 |
| 6 | Entity Management & Party Optimization | ~1,650 |
| 7 | Inventory & Item Logistics | ~1,400 |
| 8 | Dialogue & Interaction Systems | ~1,600 |
| 9 | GOAP Decision Core | ~1,800 |
| 10 | Failsafe Protocols & System Integrity | ~1,500 |
| — | CLI Control Infrastructure | ~10,000 |
| — | Mode Duration Tracking & Anomaly Detection | ~2,000 |
| — | Edge Cases & Recovery Protocols | ~3,000 |

Each chapter follows a **spec-driven format** with:
- Mermaid flowcharts for visual logic
- Pseudo-code for implementation details
- LLM reasoning prompts for AI decision-making

## Key Components

### 🧠 Tri-Tier Memory Architecture

**Tier 1: Persistent Observer (Long-term Narrative)**
- Journey progress: Badges, gyms defeated, regions explored
- Party evolution: Caught, leveled, released Pokémon
- Strategic milestones: First gym, rare catches, speedrun records

**Tier 2: Strategic Memory (Session-long Learning)**
- Battle lessons: Type matchups, move effectiveness
- Route knowledge: Shortest paths, catch rates, encounter frequencies
- Resource strategies: Healing priorities, money allocation

**Tier 3: Tactical Memory (Immediate Context)**
- Current HP/status of all 6 Pokémon
- Active battle state and turn-by-turn analysis
- Recent actions and immediate objectives

### 🎯 GOAP Decision Core

Hierarchical planning layers operating at different timescales:
- **Strategic Layer (1000+ cycles)**: Team composition, gym preparation
- **Tactical Layer (30-100 cycles)**: Route planning, resource management
- **Operational Layer (5-30 cycles)**: Battle decisions, navigation
- **Reactive Layer (0-5 cycles)**: Emergency responses, immediate threats

### 🛡️ Failsafe Protocols

- Confidence scoring with 5-tier escalation
- Softlock detection (position deadlock, menu loops, battle stalls)
- Death spiral prevention with linear regression analysis
- Emergency recovery (in-place → navigate → reload → reset)

### 📊 Mode Duration Tracking

Statistical deviation detection for anomaly handling:
- Learns normal duration for each mode (e.g., wild battles: 30-120s, p95=300s)
- Triggers break-out when exceeding statistical thresholds
- Adaptive threshold calculation with EWMA-based learning

## ROM Support

**Place your ROM in:** `data/rom/`

| Generation | Games |
|------------|-------|
| Gen 1 (Game Boy) | Red, Blue, Green, Yellow |
| Gen 2 (Game Boy Color) | Gold, Silver |

**To change games:** Edit `config/settings.yaml` and change `rom.path`

## Quick Start

```bash
# 1. Create virtual environment
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set up API key
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY

# 4. Select your game
# Edit config/settings.yaml -> rom.path (default: data/rom/pokemon_blue.gb)

# 5. Run the AI (basic)
python3 src/game_loop.py --rom data/rom/pokemon_blue.gb --save-dir runs/test_001
```

## How to Run

The main entry point is `src/game_loop.py` which accepts the following arguments:

### Required Arguments
| Argument | Description |
|----------|-------------|
| `--rom` | Path to Pokemon ROM file (.gb or .gbc) |

### Optional Arguments
| Argument | Default | Description |
|----------|---------|-------------|
| `--save-dir` | `./game_saves` | Directory for saves, database, and screenshots |
| `--screenshot-interval` | 60 | Ticks between screenshots (60 = ~1 second at 60fps) |
| `--max-ticks` | None | Maximum ticks to run before stopping (optional) |
| `--load-state` | None | Load existing emulator state file |
| `--multi-instance` | False | Run multiple emulator instances simultaneously |
| `--instances` | 3 | Number of instances for multi-instance mode |

### Examples

**Basic run:**
```bash
python3 src/game_loop.py --rom data/rom/pokemon_blue.gb
```

**With screenshots every 30 ticks:**
```bash
python3 src/game_loop.py --rom data/rom/pokemon_blue.gb --screenshot-interval 30 --save-dir runs/screenshots_test
```

**With max ticks limit (10000 ticks ~ 3 minutes at max speed):**
```bash
python3 src/game_loop.py --rom data/rom/pokemon_blue.gb --max-ticks 10000 --save-dir runs/test_001
```

**Complete example with all options:**
```bash
python3 src/game_loop.py \
    --rom data/rom/pokemon_blue.gb \
    --save-dir runs/test_001 \
    --screenshot-interval 60 \
    --max-ticks 10000
```

**Run with different ROM:**
```bash
python3 src/game_loop.py --rom data/rom/pokemon_red.gb --save-dir runs/red_run
```

**Load from saved state:**
```bash
python3 src/game_loop.py --rom data/rom/pokemon_blue.gb --load-state runs/test_001/emulator_state.state
```

### Output Structure

Each run creates the following structure in `--save-dir`:
```
runs/test_001/
├── game_data.db           # SQLite database with all session data
├── emulator_state.state   # Emulator save state
└── screenshots/           # Screenshot captures
    ├── screenshot_0060.png
    ├── screenshot_0120.png
    └── ...
```

## How to Test

### Running All Tests
```bash
# Run all tests with verbose output
pytest tests/ -v

# Run with coverage report
pytest --cov=src --cov-report=html

# Run with coverage and terminal summary
pytest --cov=src --cov-report=term-missing
```

### Running Specific Tests
```bash
# Run a specific test file
pytest tests/test_schemas.py -v

# Run tests in a specific directory
pytest tests/cli/ -v

# Run a specific test function
pytest tests/test_schemas.py::test_command_creation -v

# Run tests matching a pattern
pytest -k "battle" -v
```

### Test Categories
```bash
# Unit tests only (fast)
pytest tests/ -v -m "not integration"

# Integration tests (slower, may require emulator)
pytest tests/ -v -m "integration"

# Run tests in parallel
pytest tests/ -n auto -v
```

### Viewing Coverage Report
```bash
# After running with coverage, view HTML report
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
start htmlcov/index.html  # Windows
```

## Troubleshooting

### Common Errors and Solutions

#### `ROM file not found`
```
ERROR: ROM file not found: data/rom/pokemon_blue.gb
```
**Solution:** Verify the ROM path is correct. ROMs should be in `data/rom/`:
```bash
ls data/rom/
# Should show: pokemon_red.gb, pokemon_blue.gb, etc.
```

#### `No module named 'pyboy'`
```
ModuleNotFoundError: No module named 'pyboy'
```
**Solution:** Install dependencies in your virtual environment:
```bash
source venv/bin/activate
pip install -r requirements.txt
```

#### `OPENAI_API_KEY not set`
```
WARNING: No OpenRouter API key found. Using stub AI mode
```
**Solution:** Create `.env` file with your API key:
```bash
cp .env.example .env
# Edit .env and add your API key
```

#### `Database error` or `sqlite3.OperationalError`
```
sqlite3.OperationalError: unable to open database file
```
**Solution:** Ensure the save directory exists and is writable:
```bash
mkdir -p runs/test_001
python3 src/game_loop.py --rom data/rom/pokemon_blue.gb --save-dir runs/test_001
```

#### Emulator crashes or hangs
```
ERROR: Emulator crashed at tick 150
```
**Solutions:**
1. Try a different ROM (some ROM hacks may have compatibility issues)
2. Reduce screenshot frequency: `--screenshot-interval 120`
3. Limit max ticks: `--max-ticks 5000`
4. Check available memory: `free -h` (Linux) or `Activity Monitor` (macOS)

#### Poor performance / slow execution
**Symptoms:** Low ticks per second, stuttering, high CPU

**Solutions:**
1. Increase screenshot interval: `--screenshot-interval 120`
2. Set max ticks to limit session length
3. Close other applications
4. Ensure virtual environment is activated

### API Key Setup

#### OpenAI API Key
1. Get an API key from https://platform.openai.com/api-keys
2. Add to `.env`:
   ```
   OPENAI_API_KEY=sk-your-key-here
   ```
3. Verify in config/settings.yaml that `models.thinking_model.provider` is set to "openai"

#### OpenRouter (Alternative Provider)
OpenRouter provides access to multiple models including GPT-4 and Claude:
1. Get API key from https://openrouter.ai
2. Add to `.env`:
   ```
   OPENROUTER_API_KEY=your-key-here
   ```
3. Configure in settings.yaml with your preferred model

#### Verifying API Connection
```bash
# Test API key is loaded
source venv/bin/activate
python3 -c "from dotenv import load_dotenv; from pathlib import Path; load_dotenv(Path('.env')); import os; print('API Key set:', bool(os.getenv('OPENAI_API_KEY')))"
```

### Emulator Issues

#### Black screen on startup
**Solutions:**
1. ROM may be corrupted - try a different ROM file
2. Verify ROM is the correct version for your emulator settings
3. Check emulator speed setting in `config/settings.yaml`

#### Save states not loading
**Solutions:**
1. Ensure save state file exists: `ls runs/test_001/emulator_state.state`
2. Try without loading state first to establish baseline
3. Verify ROM version matches the save state

#### Memory reading errors
```
Error reading memory at address 0xD158
```
**Solutions:**
1. This is expected if the game hasn't loaded yet
2. Memory addresses may vary by ROM version
3. Check logs/ directory for detailed error traces

### Getting Help

1. **Check logs:** All errors are logged to `logs/` directory
2. **Run in debug mode:** Increase verbosity by checking console output
3. **Search existing issues:** Check GitHub issues for similar problems
4. **Create new issue:** Include:
   - Full error message and traceback
   - Operating system and Python version
   - ROM file name and version
   - Command used to run

## Requirements

### System Requirements
- Python 3.10+
- 1GB storage for logs/memory
- Internet connection (for API calls)
- PyBoy emulator (Game Boy/Game Boy Color emulation)

### API Keys (Optional)
- OpenAI API Key (GPT-4V/GPT-4o-mini) - enables real AI mode
- Without API key: runs in stub AI mode for testing

### Dependencies
```
# Core dependencies (installed automatically)
pyboy>=1.0.0          # Game Boy emulator
requests>=2.31.0      # HTTP client for LLM APIs
numpy>=1.24.0         # Numerical operations
Pillow>=10.0.0        # Image processing
pydantic>=2.0         # Data validation
python-dotenv>=1.0    # Environment variable management
opencv-python>=4.8.0  # Image processing pipeline

# Development dependencies (optional)
pytest>=7.0           # Testing framework
pytest-cov>=4.0       # Coverage reporting
black>=23.0           # Code formatter
mypy>=1.0             # Type checking
flake8>=6.0           # Linting
```

## Performance Targets

| System | Target |
|--------|--------|
| Vision/OCR | <1 second per screen |
| State transition | <0.5 second |
| Combat move selection | <0.5 second |
| Pathfinding (A*) | <1 second for 50-tile path |
| GOAP goal planning | <3 seconds for full stack |
| Softlock detection | <5 seconds |
| Emergency recovery | <10 seconds |

## Project Structure

```
├── memory-bank/          # Architecture documentation
│   ├── projectBrief.md   # Core vision and paradigm shift
│   ├── productContext.md # Problem statements & solutions
│   ├── activeContext.md  # Current work focus
│   ├── systemPatterns.md # System architecture & patterns
│   ├── techContext.md    # Technologies & setup
│   └── progress.md       # Implementation roadmap
├── specs/                # Technical specifications
│   ├── ptp_01x_detailed/ # 10 complete chapters
│   ├── ptp_01x_cli_control_infrastructure.md
│   ├── ptp_01x_mode_duration_tracking.md
│   └── ptp_01x_edge_cases_recovery.md
├── prompts/              # LLM prompt engineering
│   ├── battle/           # Combat decision-making
│   ├── dialog/           # Dialogue parsing
│   ├── exploration/      # Navigation logic
│   ├── menu/             # Menu interactions
│   └── strategic/        # Long-term strategy
├── src/                  # Implementation framework
│   ├── core/             # AI core systems
│   ├── db/               # Database operations
│   └── schemas/          # Command definitions
└── config/               # Configuration files
```

## Documentation

- **Start Here:** [memory-bank/projectBrief.md](memory-bank/projectBrief.md)
- **Architecture:** [memory-bank/systemPatterns.md](memory-bank/systemPatterns.md)
- **Progress:** [memory-bank/progress.md](memory-bank/progress.md)
- **Specifications:** [specs/ptp_01x_detailed/](specs/ptp_01x_detailed/)
- **API Reference:** [docs/api/index.md](docs/api/index.md) - Complete API documentation for GameLoop, GameAIManager, Database, and data structures

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines.

### Quick Contribution Guide
1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Install development dependencies: `pip install -r requirements-dev.txt`
4. Run tests: `pytest tests/ -v`
5. Format code: `black src/ tests/`
6. Submit a pull request

## License

MIT License - See LICENSE file for details.

---

**PTP-01X** - *Orchestrated Intelligence for Autonomous Gameplay*

*Last Updated: December 31, 2025*