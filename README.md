# PTP-01X - Orchestrated Intelligence Framework for Autonomous Pokémon Gameplay

[![CI](https://github.com/wojons/ai_plays_poke/actions/workflows/ci.yml/badge.svg)](https://github.com/wojons/ai_plays_poke/actions/workflows/ci.yml)

🎮 **A fundamentally different AI gaming approach** that shifts from Reinforcement Learning training loops to Orchestrated Intelligence with hierarchical memory and strategic reasoning.

## The Paradigm Shift

PTP-01X treats autonomous Pokémon play as a repeated observe-decide-act loop with durable evidence, not as an unstructured stream of screenshots and button presses. The repository separates what runs today from the larger spec-driven ambition:

- **Live today:** `cron_runner.py` boots Pokémon Blue, projects emulator RAM into structured state, selects decisions through configurable System-1/System-2 modes, executes tools, and records each cycle.
- **Live memory and evidence:** decision rows are appended to per-run JSONL logs, while reusable goals, notes, studies, and route knowledge can persist through DuckBrain.
- **SPEC-DRIVEN / design-only:** the 69-state gameplay machine, GOAP decision core, Observer → Strategist → Tactician tri-tier memory hierarchy, multi-phase vision/OCR recognition, and the complete 20+ hour journey are ambitions documented under `specs/`. They are not wired into the running `cron_runner.py` loop yet.
- **Long-range scope:** cataloging 151 Pokémon and planning through eight Gyms plus the Elite Four remain product goals, not claims that a current run completes them.

### Why Simple AI Fails

| Failure mode | Live response | Design goal |
|--------------|---------------|-------------|
| Pixel-only observation | Default gameplay state comes directly from emulator RAM instead of a paid vision call each tick. | The multi-phase vision/OCR state machine remains design-only in `specs/`. |
| Context amnesia | Structured JSONL decision history and DuckBrain persistence carry evidence and selected knowledge across cycles and runs. | The Observer → Strategist → Tactician tri-tier hierarchy remains a design-only specification. |
| One policy for every situation | The default `jev` hybrid uses fast System-1 decisions and invokes an LLM System-2 teacher on configured handoff triggers. | The GOAP planning core remains a design-only specification. |
| Unverifiable autonomy | Every cycle records the selected mode, decision evidence, action, and outcome where available. | End-to-end completion of the designed 20+ hour journey is not yet a shipped capability. |

## Architecture Overview

The live autonomous path is implemented by `cron_runner.py` and the modules it imports. Its loop is:

```text
ROM + data/boot.state checkpoint (or intro-bypass fallback)
                              │
                              ▼
cron_runner.py boots PyBoy and captures the current game state
                              │
                              ▼
src/core/state_projection.py
RAM projection → StateWindow flow for structured game state
                              │
                              ▼
src/core/jev_client.py
--decision-mode flag > AIPP_DECISION_MODE / CRON_DECISION_MODE > jev default
jev = fast System-1 policy + LLM System-2 teacher on handoff triggers
                              │
                              ▼
src/core/tools.py :: execute_tool_call
validated emulator button/tool execution
                              │
                              ▼
cron_logs/run_<id>.jsonl decision rows + DuckBrain persistence
```

The selectable decision modes are `system1`, `system2`/`llm`, `system1+system2`/`hybrid`/`jev`, and `agentic`; `jev` is the default spelling for the hybrid family. Boot-state recovery, RAM observation, decision routing, tool execution, structured logging, and DuckBrain integration are the running architecture.

**Runtime boundary:** the later Complete Specification and Key Components sections catalog design documents. Their 69-state machine, GOAP core, tri-tier memory hierarchy, and vision/OCR pipeline are **SPEC-DRIVEN / design-only** and are not imported or executed by `cron_runner.py`.

## Complete Specification

**28,002 lines** across the 24 top-level spec documents under `specs/` — 46,574 lines across all 39 `*.md` files under `specs/` once the 14 chapter files in `specs/ptp_01x_detailed/` are included (measured 2026-10-17 with `wc -l specs/*.md` → 28,002 and `find specs -name '*.md' -exec cat {} + | wc -l` → 46,574) — covering all aspects of autonomous Pokémon gameplay:

| Chapter | Focus | Lines |
|---------|-------|-------|
| 1 | Vision & Perception Engine | 564 |
| 2 | Hierarchical State Machine | 818 |
| 3 | Tactical Combat Heuristics | 1,019 |
| 4 | World Navigation & Spatial Memory | 1,214 |
| 5 | Data Persistence & Cognitive Schema | 1,520 |
| 5b | Tri-Tier Memory Architecture | 776 |
| 6 | Entity Management & Party Optimization | 1,996 |
| 7 | Inventory & Item Logistics | 4,227 |
| 8 | Dialogue & Interaction Systems | 1,592 |
| 9 | GOAP Decision Core | 1,922 |
| 10 | Failsafe Protocols & System Integrity | 2,410 |
| — | CLI Control Infrastructure | 2,591 |
| — | Mode Duration Tracking & Anomaly Detection | 1,952 |
| — | Edge Cases & Recovery Protocols | 272 |

The 14 rows above total **22,873 lines**: the ten chapters + 5b
(`specs/ptp_01x_detailed/`, 18,058 of those lines — that directory's 14 files total
18,409, the extra 351 being `SPECIFICATION_COMPLETE.md`) plus the three cross-cutting
specs (`ptp_01x_cli_control_infrastructure.md` 2,591 +
`ptp_01x_mode_duration_tracking.md` 1,952 + `ptp_01x_edge_cases_recovery.md` 272 =
4,815). The remaining 5,129 lines of the 28,002 sit in the other 21 top-level spec
documents under `specs/` (design variants, API integration, database schema,
executive summary, and SPECIFICATION_COMPLETE).

Rows 6 and 7 are the sum of two files each (`chapter_06_entity_design.md` 1,113 +
`chapter_06_entity_management.md` 883 = 1,996; `chapter_07_inventory.md` 2,250 +
`chapter_07_inventory_system.md` 1,977 = 4,227); every other Lines value is a single
file. All counts above measured 2026-10-17 with `wc -l`.

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

> **SPEC-DRIVEN / design-only** — not wired into the running `cron_runner.py` loop (see Runtime boundary below).

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

ROM files are not included. You must own the game and supply your own dump. For the
default configuration, place it at
`data/rom/Pokemon - Blue Version (USA, Europe) (SGB Enhanced).gb`.

| Generation | Games |
|------------|-------|
| Gen 1 (Game Boy) | Red, Blue, Green, Yellow |
| Gen 2 (Game Boy Color) | Gold, Silver |

**To change games:** pass `--rom /path/to/your.rom` to `cron_runner.py` (the
default lives on the `ROM` constant in `cron_runner.py`; `config/settings.yaml`
is not read by any maintained code path). A non-Blue ROM also needs
`--boot-state skip` unless you supply a matching checkpoint — the shipped
`data/boot.state` was captured from Pokemon Blue.

## Web-Based Live Viewer

Open `web/index.html` in a browser to run a live Game Boy emulator with RAM state overlay.

1. Open `web/index.html` in Chrome/Firefox/Edge
2. Click "Load ROM" and select a Pokémon Red/Blue .gb ROM
3. Use keyboard controls: Arrow keys = D-Pad, Z = A, X = B, Enter = Start, Shift = Select
4. Press `/` or click "Toggle Overlay" to show/hide RAM state information

The overlay shows player position, current map, screen type, and party Pokémon — the same data the Python RAM reader extracts.

### RAM-map viewer (Python)

`ram_map_server.py` starts a separate live RAM-map viewer on
`http://localhost:8099/`:

```bash
source .venv/bin/activate
python3 ram_map_server.py
```

This viewer is interactive, not read-only. `GET /` (or `/index.html`) serves the
controls, while `GET /data.json` only reads the current emulator state. The page polls
that read endpoint every second. Its buttons send `POST /input` JSON requests, such as
`{"button":"up"}`, which drive the live emulator. The endpoint also accepts a
`buttons` or `combo` list and an optional positive integer `frames`; it accepts only
`a`, `b`, `up`, `down`, `left`, `right`, `start`, and `select`. Invalid payloads return
`400` without applying input.

> **Safety:** `POST /input` changes the emulator state. The server binds to all network
> interfaces and has no authentication, so do not expose port 8099 or use it with
> untrusted clients.

## Quick Start (working path)

The primary working entry point for autonomous gameplay is `cron_runner.py` — an E2E runner
that reads game state directly from emulator RAM (free, instant) and uses LLM calls only for
game decisions.

Before running the first setup command:

- ROM files are not bundled. You must own the game and supply your own legally obtained dump
  of a compatible Pokémon Blue ROM at
  `data/rom/Pokemon - Blue Version (USA, Europe) (SGB Enhanced).gb`.
- `OPENROUTER_API_KEY` is required for real AI decisions.
- `DEEPSEEK_API_KEY` is an optional fallback provider key for DeepSeek models; when it is set,
  those models route directly to DeepSeek instead of OpenRouter.

### System prerequisites

- Runtime deps install cleanly from wheels (`pyboy 2.7.0`, `pysdl2 0.9.17`,
  `pysdl2-dll 2.32.10`) — verified 2026-10-09 on a fresh `python3` venv:
  `pip install -r requirements.txt` (exit 0) then `python3 cron_runner.py --dry-run`
  (exit 0, even with zero API keys).
- On glibc x86_64 Linux no system packages are required: `pysdl2-dll` bundles the SDL2
  runtime and PyBoy ships prebuilt wheels.
- On musl (Alpine) or non-x86_64 without wheels, PyBoy builds from source and needs SDL2
  dev headers plus a C++ toolchain (`apk add sdl2-dev build-base` /
  `apt install libsdl2-dev build-essential`).
- ROMs are not included — supply your own dump (see [ROM Support](#rom-support)).

```bash
# 1. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Supply the ROM (ROM files are not included)
# You must own the game. Place your own dump at this exact path:
# data/rom/Pokemon - Blue Version (USA, Europe) (SGB Enhanced).gb

# 4. Set up API keys
cp .env.example .env
# Edit .env — OPENROUTER_API_KEY is required for real AI decisions.
# DEEPSEEK_API_KEY is optional fallback for DeepSeek models.

# 5. Run (example: 80 AI decision cycles)
python3 cron_runner.py --run-id demo1 --cycles 80
```

> **Run `cron_runner.py` with the project venv:** every invocation — even
> `python3 cron_runner.py --help` — should use the venv
> (`.venv/bin/python cron_runner.py --help`, or `source .venv/bin/activate`
> first). `cron_runner.py` imports its third-party dependencies at module level,
> before argparse is reached (`cron_runner.py:721` → `src/core/prompt_loader.py:16`),
> so on an interpreter that lacks them even the help screen exits 1 with
> `ModuleNotFoundError: No module named 'yaml'`. Measured 2026-10-17:
> `env -i /usr/bin/python3 -S cron_runner.py --help` → that `yaml` traceback, rc 1;
> `.venv/bin/python cron_runner.py --help` → full usage, rc 0. (PyYAML is the first
> module to fail — not numpy.)

**What this does:** Each cycle reads the game state directly from emulator RAM (no paid
vision API calls per tick), sends the spatial data to the LLM controller
(`openai/gpt-5.6-luna` for overworld navigation, `deepseek-v4-flash` for battles), and
executes the returned button plan with built-in recovery (direction-lock detection,
checkpoint rollback).

**Boot state (what a fresh run starts from):** `cron_runner.py` boots from the shipped
known-good checkpoint `data/boot.state` when present — the player is standing in Oak's
Lab in Pallet Town with the starter already picked (map 0x28, tile ~(4,4), party of 1),
no dialog open. The run skips the title-screen intro bypass entirely. If the checkpoint
is missing (or `--boot-state skip` is passed), the runner falls back to the legacy
intro bypass: it A-mashes from the title screen through Oak's intro, names the player
ASH and rival GARY, and walks out of the house into Pallet Town — this path can land in
a degenerate wall-facing overworld state that direction-locks immediately, which is why
the checkpoint boot is the default.

**First cycles (what to expect):** cycle 1 observes the overworld via RAM and sends the
spatial state to the controller; the first plan usually walks toward the lab exit.
Because the same frames repeat while the character animates, you will see `[CACHE-HIT]`
frame-reference lines and occasionally `[WARN] Direction-locking detected: <dir> x3` —
that warning fires whenever a single plan contains 3+ consecutive presses of the same
direction (a straight hallway walk triggers it even while moving). It is NOT a failure
by itself: the runner only escalates to recovery when the stuck detector sees 4+
consecutive same-direction presses *across* cycles without progress, and recovery
resets the counter. The final summary line reports the **lock-rate** — the fraction of
cycles that contained at least one direction-lock warning (`lock-rate: 5/20 cycles
(25%)`) — plus the number of distinct map tiles visited. Healthy runs are well under
50% lock-rate and visit multiple tiles; a run stuck at 100% lock-rate with 1 tile is
direction-locked and the boot state should be refreshed. The `Screens` set printed at
the end of the summary line (e.g. `Screens: {'overworld', 'dialog'}`) lists every
screen type observed during the run; it may include `"unknown"` for cycles that
produced no screen classification (e.g. skipped/error frames, or the RAM reader's
unknown bucket) rather than a specific screen type.

**Outputs:**
- `cron_logs/run_<id>.jsonl` — one JSON line per event (cycle decisions among
  them): screen type, button plan, LLM
  intent, player coordinates (x/y), map name, plus event rows (recovery, state saved).
- `screenshots/run_<id>/step_NNNN.png` — 160×144 RGB frame per cycle.

**Flags:**

| Flag | Default | Description |
|------|---------|-------------|
| `--run-id` | auto-generated timestamp | Label for this run's logs and screenshots |
| `--cycles` | 20 | Number of AI decision cycles |
| `--rom` | `data/rom/Pokemon - Blue Version (USA, Europe) (SGB Enhanced).gb` | Path to the Gen-1 GB ROM to boot (overrides the module default) |
| `--boot-state` | `data/boot.state` if present | Path to a known-good `.state` checkpoint to boot from instead of the intro bypass; `skip` forces the legacy intro bypass |
| `--dry-run` | off | Validate setup (ROM + boot-state paths, config summary, API-key liveness) and exit 0 — zero LLM/API calls, no emulator boot |
| `--skip-key-check` | off | With `--dry-run`: skip the API-key liveness probes and report key presence only (fully offline validation) |

Step 5 above needs a real key in `.env` (`OPENROUTER_API_KEY`, or the
`DEEPSEEK_API_KEY` fallback) because it starts live AI decisions. Without a key,
validate the setup offline instead:

```bash
python3 cron_runner.py --dry-run --skip-key-check
```

**Full reference:** [docs/api/cron_runner.md](docs/api/cron_runner.md) — CLI flags,
pipeline stages, JSONL log schema, checkpoint/rollback behavior, and cost notes.

**Proven results:** 10/10 cycles in dogfood runs (real LLM decisions, map movement,
recovery firing); 80/80 cycles in E2E (RSS flat ~110 MB, $0.60 for 43 LLM calls).
First-run behavior is deterministic thanks to the shipped boot checkpoint: every run
starts in Oak's Lab (starter picked), so the first cycles are overworld navigation with
real movement — GAP-028 acceptance measured 2/20 lock-rate cycles (10%) with 2+ distinct
tiles on a fresh 20-cycle run (see the `lock-rate` field in the summary line above for
your own runs).

**Default 20-cycle demo behavior:** A short 20-cycle run (`--cycles 20`) typically
demonstrates overworld navigation and AI decision-making inside Oak's Lab — the agent
interacts with objects, moves between tiles, and fires recovery logic. Whether the agent
reaches the lab exit and transitions to Route 1 within 20 cycles is LLM-dependent and
not guaranteed. For a run that reliably exits Oak's Lab, use `--cycles 80` or higher.
The default exploration goal (`cron_runner.py` seeds "Leave Oaks Lab and head toward
Route 1" when no stored goal exists) provides direction, but the controller's adherence
varies by run.

**Scheduled runs & QA tooling:**

- `.coding-hermes/cron.sh` — scheduled decision-loop runner used by the Hermes cron
  (wraps `cron_runner.py`; flags `--cycles N` / `--rom path` / `--run-id` /
  `--boot-state` / `--dry-run`; defaults 20 cycles on the Gen-1 SGB Blue ROM;
  writes `cron_logs/run_<id>.jsonl` logs + `screenshots/run_<id>/` frames).
- `.coding-hermes/usability-tests.md` — QA checklist for the live map viewer
  (`ram_map_server.py`, `http://localhost:8099`): HTTP endpoints, JSON schema,
  boot/navigation probes with pass results.

> **Note:** `src/game_loop.py` (documented below) is the legacy/simplified entry point.
> The AP-GAP-001 vision crash is fixed: boot progression + command wiring landed
> 2026-08-16 (GAP-020), battle recording is gated on verified battle-screen evidence
> (GAP-021), and session DB `model_name` reflects the real AI config (GAP-022). It
> remains the legacy path — use `cron_runner.py` for real autonomous gameplay.

## Quick Start (legacy game_loop.py)

> **⚠️ Use the project venv for the legacy path:** the commands below need an
> interpreter that has the project dependencies installed (`.venv`). A fresh clone has
> no `.venv`, and the system `python3` has no `pyboy`, so the run stops at
> `ModuleNotFoundError: No module named 'pyboy'` (`src/core/emulator.py:13`).
>
> `PYTHONPATH=src` is **not** required for these commands: `src/game_loop.py` inserts
> its own parent directory on `sys.path` (`src/game_loop.py:23-24`), so `db.*`/`core.*`
> resolve when they are run from the repo root as documented. Measured 2026-10-17 in a
> fresh `git clone --depth 1` with no `PYTHONPATH` and no API key: the imports succeed
> and the run proceeds past them to the `OPENROUTER_API_KEY` check — it does **not**
> fail with an import error for the `db`/`core` packages.
>
> ```bash
> source .venv/bin/activate
> ```

```bash
# 1. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set up API key
cp .env.example .env
# Edit .env and add your OPENROUTER_API_KEY (required) and DEEPSEEK_API_KEY (fallback)

# 4. Select your game
# Pass --rom on the command line (default: "data/rom/Pokemon - Blue Version (USA, Europe) (SGB Enhanced).gb").
# (config/settings.yaml is legacy — no maintained code reads it.)

# 5. Run the AI (basic)
python3 src/game_loop.py --rom "data/rom/Pokemon - Blue Version (USA, Europe) (SGB Enhanced).gb" --save-dir runs/test_001
```

## How to Run (legacy game_loop.py)

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
python3 src/game_loop.py --rom "data/rom/Pokemon - Blue Version (USA, Europe) (SGB Enhanced).gb"
```

**With screenshots every 30 ticks:**
```bash
python3 src/game_loop.py --rom "data/rom/Pokemon - Blue Version (USA, Europe) (SGB Enhanced).gb" --screenshot-interval 30 --save-dir runs/screenshots_test
```

**With max ticks limit (10000 ticks ~ 3 minutes at max speed):**
```bash
python3 src/game_loop.py --rom "data/rom/Pokemon - Blue Version (USA, Europe) (SGB Enhanced).gb" --max-ticks 10000 --save-dir runs/test_001
```

**Complete example with all options:**
```bash
python3 src/game_loop.py \
    --rom "data/rom/Pokemon - Blue Version (USA, Europe) (SGB Enhanced).gb" \
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
python3 src/game_loop.py --rom "data/rom/Pokemon - Blue Version (USA, Europe) (SGB Enhanced).gb" --load-state runs/test_001/emulator_state.state
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

> Commands below use `.venv/bin/python -m pytest` so they work from a **fresh shell**
> (system `python3` has no pytest/numpy — the project venv is `.venv`; see
> [Quick Start](#quick-start-working-path) to create it). If you have the venv
> activated (`source .venv/bin/activate`), plain `pytest` works identically.
>
> **Fresh clone:** after creating the venv, install the development dependencies so
> the pytest commands below (including `--cov` and `-n auto`) are available:
> `pip install -r requirements.txt && pip install -r requirements-dev.txt`

### Running All Tests
```bash
# Run all tests in parallel (recommended — the ~14s figure is parallel-only,
# measured with pytest-xdist: 4416 collected / 62 heavy-deselected; exact pass
# counts drift as tests are added — check the run summary, not this comment)
.venv/bin/python -m pytest tests/ -n auto -v

# Run all tests serially (same suite takes ~210s / ~3.5 min — only if xdist is unavailable)
.venv/bin/python -m pytest tests/ -v

# Run with coverage report
.venv/bin/python -m pytest --cov=src --cov-report=html

# Run with coverage and terminal summary
.venv/bin/python -m pytest --cov=src --cov-report=term-missing
```

### Running Specific Tests
```bash
# Run a specific test file
.venv/bin/python -m pytest tests/test_schemas.py -v

# Run tests in a specific directory
.venv/bin/python -m pytest tests/ptp_cli/ -v

# Run a specific test function
.venv/bin/python -m pytest tests/test_schemas.py::TestCommandTypeEnum::test_command_type_values_exist -v

# Run tests matching a pattern
.venv/bin/python -m pytest -k "battle" -v
```

### Test Categories
```bash
# Fast tier (recommended for day-to-day work) — the unit-test set, plus the one
# ROM-gated live probe that carries no heavy mark (see the note below).
# Serial wall time ~190s on an unloaded box (measured 189.95s, 2026-09-27;
# ~65–90s if pytest-xdist parallelizes it). 4452 collected / 4514
# (62 deselected; measured 2026-10-17) — counts drift as tests are added,
# so check the run summary. Excludes @pytest.mark.heavy tests — the same
# tests that carry @pytest.mark.integration (game-loop component flows)
# and @pytest.mark.slow (network retry/backoff, memory & performance
# benchmarks).
.venv/bin/python -m pytest tests/ -q -m "not heavy"

# Near-equivalent fast-tier selection (kept for compatibility). The two are
# NOT identical: this one collects 4451 / 4514 (63 deselected; measured
# 2026-10-17), one fewer than above. The single delta is
# tests/test_long_run_boot.py::test_default_boot_probes_pallet_town_map_0_live
# (@pytest.mark.live + @pytest.mark.integration, skipif when the ROM is
# absent): it carries no heavy mark, so "not heavy" collects it, while
# "not integration and not slow" deselects it.
.venv/bin/python -m pytest tests/ -q -m "not integration and not slow"

# Heavy tier — integration tests (slower, may require emulator)
.venv/bin/python -m pytest tests/ -v -m "integration"

# Heavy tier — slow tests only (network retry/backoff, memory & performance benchmarks)
.venv/bin/python -m pytest tests/ -v -m "slow"
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
ERROR: ROM file not found: data/rom/Pokemon - Blue Version (USA, Europe) (SGB Enhanced).gb
```
**Solution:** ROMs are not included in a fresh clone. You must own the game and place
your own dump at the exact configured path:
```bash
test -f "data/rom/Pokemon - Blue Version (USA, Europe) (SGB Enhanced).gb" \
  && echo "ROM is present"
```
The default `data/boot.state` was captured from that exact Pokemon Blue ROM and needs
the matching ROM. If you intentionally configure a different owned game, also use
`--boot-state skip` unless you have a matching checkpoint.

#### `No module named 'pyboy'`
```
ModuleNotFoundError: No module named 'pyboy'
```
**Solution:** Install dependencies in your virtual environment:
```bash
source .venv/bin/activate
pip install -r requirements.txt
```

#### `OPENROUTER_API_KEY environment variable is not set`
```
ValueError: OPENROUTER_API_KEY environment variable is not set. Create a .env file or export the variable.
```
**Solution:** Create `.env` from the template and add your key. There is no stub mode:
`cron_runner.py` refuses to boot with `controller key OPENROUTER_API_KEY is not set`
(exit 2), and the legacy `src/game_loop.py` exits 1 with the `ValueError` traceback
above, raised at `src/core/vision.py:88`.
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
python3 src/game_loop.py --rom "data/rom/Pokemon - Blue Version (USA, Europe) (SGB Enhanced).gb" --save-dir runs/test_001
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

#### OpenRouter API Key (primary — required for live AI decisions)
1. Get an API key from https://openrouter.ai
2. Add to `.env`:
   ```
   OPENROUTER_API_KEY=sk-or-your-key-here
   ```
3. (Optional fallback provider) Add `DEEPSEEK_API_KEY` to `.env` — used when the
   OpenRouter call path falls back (ai_client.py:532, cron_runner.py:760).
4. No settings.yaml step is needed — no maintained code reads `config/settings.yaml`.
   Routing is automatic: `OPENROUTER_API_KEY` is used first; when `DEEPSEEK_API_KEY`
   is set, DeepSeek models (the `deepseek-v4-flash` thinking model) route direct to
   `api.deepseek.com`. Validate either with `python3 cron_runner.py --dry-run`.

#### Verifying API Connection
The command below only verifies that `.env` loads and prints `API Key set:
True/False` for whether the key is **present** — it does not contact OpenRouter.
Real key liveness (expired/invalid keys) is checked by the dry run:

```bash
source .venv/bin/activate
python3 -c "from dotenv import load_dotenv; from pathlib import Path; load_dotenv(Path('.env')); import os; print('API Key set:', bool(os.getenv('OPENROUTER_API_KEY')))"

# Real liveness check (validates ROM, boot state, and live API keys; zero LLM calls)
python3 cron_runner.py --dry-run
```

### Emulator Issues

#### Black screen on startup
**Solutions:**
1. ROM may be corrupted - try a different ROM file
2. Verify ROM is the correct version for your emulator settings
3. `config/settings.yaml` is legacy (no maintained code reads it) and carries no
   emulator-speed setting — try a different ROM dump or `--boot-state skip`

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

### API Keys
- `OPENROUTER_API_KEY` (required) - enables real AI mode
- `DEEPSEEK_API_KEY` (optional) - fallback provider for DeepSeek models
- Without a key there is **no stub mode**: the legacy `src/game_loop.py` exits 1 with
  `ValueError: OPENROUTER_API_KEY environment variable is not set`
  (`src/core/vision.py:88`), and `cron_runner.py` refuses to boot with
  `controller key OPENROUTER_API_KEY is not set` (exit 2).

### Dependencies
Exact pins, quoted from the two requirement files (`pip install -r requirements.txt`
/ `-r requirements-dev.txt`); measured 2026-10-25 (UTC).

```
# Core dependencies (requirements.txt)
pyboy>=1.0.0,<2.8.0           # Game Boy emulator (upper bound pinned - see the comment in the file)
requests>=2.34.2              # HTTP client for LLM APIs
anthropic>=1.15.0             # Anthropic SDK
numpy>=1.26.4                 # Numerical operations
Pillow>=10.4.0                # Image processing
pydantic>=2.14.1              # Data validation
python-dotenv>=1.2.4          # Environment variable management
tqdm>=4.70.1                  # Progress bars
PyYAML>=6.0.3                 # YAML config / prompt loading
opencv-python-headless>=4.14.0.94  # Image processing pipeline
fastapi>=0.152.0              # Observability dashboard
uvicorn>=0.54.0               # Observability dashboard server
websockets>=12.0              # Live streams
psutil>=5.9.8                 # System health monitoring

# Development dependencies (requirements-dev.txt)
pytest>=7.0                   # Testing framework
pytest-cov>=4.0               # Coverage reporting
pytest-xdist>=3.0             # Parallel test execution
pytest-benchmark>=4.0         # Benchmarks
pytest-timeout>=2.1           # Per-test timeouts
requests-mock>=1.12           # HTTP mocking
black>=26.10.0                # Code formatter
mypy>=2.4.0                   # Type checking
flake8>=7.4.1                 # Linting
pre-commit>=4.7.0             # Pre-commit hooks
python-lsp-server>=1.13.0     # LSP support
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
│   ├── ptp_cli/          # PTP CLI commands
│   ├── schemas/          # Command definitions
│   ├── dashboard/        # FastAPI dashboard (src.dashboard.main:app)
│   └── vision/           # Vision pipeline
├── tests/                # Test suite
│   └── ptp_cli/          # CLI tests
├── tools/                # Utilities (console/, incl. bench_vision_accuracy.py)
├── web/                  # Browser-based live viewer (index.html + JS overlay)
├── cron_runner.py        # Primary entry point (autonomous gameplay runner)
├── ram_map_server.py     # Live RAM-map viewer server (:8099)
├── make_run_video.py     # Run footage → MP4 review video with HUD overlay
├── web_viewer.py         # Browser run viewer
└── config/               # Configuration files
```

Only tracked files are listed above — every entry exists in a fresh clone
(`git ls-files`). Local scratch/diagnostic helpers (`live_viewer.py`,
`simple_viewer.py`, `push_intro.py`, `intro_blast.py`, `diag_*.py`, `_*.py`) are
gitignored and are **not** part of the repository.

### Review tooling

Convert a finished run's screenshot sequence into a review video (MP4 with a
burned-in HUD showing cycle #, screen type, and action taken):

```bash
.venv/bin/python make_run_video.py <run_id> [--fps 2]    # writes videos/<run_id>.mp4; --force rebuilds
.venv/bin/python make_run_video.py run_luna_v10_20260802_0515
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
4. Run tests: `.venv/bin/python -m pytest tests/ -v`
5. Format code: `black src/ tests/`
6. Submit a pull request

## License

MIT License - See LICENSE file for details.

---

**PTP-01X** - *Orchestrated Intelligence for Autonomous Gameplay*

*Last Updated: October 17, 2026*