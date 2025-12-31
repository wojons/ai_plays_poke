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
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set up API key
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY

# 4. Select your game
# Edit config/settings.yaml -> rom.path

# 5. Run the AI
python -m src.main
```

## Requirements

- Python 3.10+
- OpenAI API key (GPT-4V/GPT-4o-mini)
- 1GB storage for logs/memory
- Internet connection (API calls)
- PyBoy emulator (for Game Boy emulation)

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

## License

MIT License - See LICENSE file for details.

---

**PTP-01X** - *Orchestrated Intelligence for Autonomous Gameplay*

*Last Updated: December 31, 2025*