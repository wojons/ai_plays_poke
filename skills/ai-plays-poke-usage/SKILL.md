---
name: ai-plays-poke-usage
description: Teaches agents how to use PTP-01X for autonomous Pokémon gameplay — entry points, run commands, common pitfalls, and the "right way" patterns.
version: 1.0.0
category: software-development
---

# Using PTP-01X for Autonomous Pokémon Gameplay

## Core Purpose
PTP-01X is an autonomous AI agent that plays Pokémon through emulation using:
- PyBoy emulator for perfect state extraction
- RAM reader for instant, free game state access  
- LLM controllers (OpenRouter) for strategic decisions
- Hierarchical State Machine (69 states) for gameplay orchestration
- DuckBrain context memory for learning persistence

## Entry Points

### Primary: cron_runner.py (Recommended)
This is the **real autonomous gameplay** path that bypasses expensive vision APIs:

```bash
source .venv/bin/activate
python3 cron_runner.py --run-id <label> --cycles <N>
```

**Key features:**
- Reads game state directly from emulator RAM (zero cost per tick)
- Uses LLM calls only for decisions (~$0.001 per cycle)
- Built-in recovery for direction locks and stuck states
- Checkpoint system for consistent boot states

### Legacy: src/game_loop.py (Historical)
> **⚠️ Deprecated** - Use `cron_runner.py` instead. The legacy path has known issues with vision pipeline and requires PYTHONPATH manipulation.

### RAM-map viewer: ram_map_server.py (Manual debugging)

Start the live RAM-map viewer from the repository root:

```bash
source .venv/bin/activate
python3 ram_map_server.py
# Open http://localhost:8099/
```

This is an interactive viewer, not a read-only dashboard. `GET /` (and
`/index.html`) serves the viewer controls, and `GET /data.json` reads the current RAM
state only. Viewer buttons send `POST /input` requests that drive the server's live
emulator. For example, send `{"button":"a"}`; `buttons` or `combo` lists and a
positive integer `frames` are also supported. Valid buttons are `a`, `b`, `up`, `down`,
`left`, `right`, `start`, and `select`; invalid payloads return `400` without applying
input.

> **Safety:** `POST /input` changes emulator state. The server listens on all interfaces
> without authentication, so keep port 8099 private and do not use untrusted clients.

## Run Commands

### Basic Autonomous Run
```bash
source .venv/bin/activate
python3 cron_runner.py --run-id autonomous-demo --cycles 80
```

### Dry Run (Validation Only)
```bash
source .venv/bin/activate
python3 cron_runner.py --dry-run
# Validates ROM, boot state, API keys — exits 0, zero LLM/API calls
```

### Custom Configuration
```bash
source .venv/bin/activate
# Override ROM path
python3 cron_runner.py --run-id custom-rom --cycles 40 --rom data/rom/pokemon_red.gb

# Force legacy intro bypass (not recommended)
python3 cron_runner.py --run-id no-checkpoint --cycles 20 --boot-state skip

# Use specific checkpoint
python3 cron_runner.py --run-id from-save --cycles 60 --boot-state data/boot.state
```

### Flags Reference
| Flag | Default | Description |
|------|---------|-------------|
| `--run-id` | auto-generated timestamp | Label for logs/screenshots |
| `--cycles` | 20 | Number of AI decision cycles |
| `--rom` | data/rom/Pokemon - Blue Version (USA, Europe) (SGB Enhanced).gb | Path to Gen-1 GB ROM |
| `--boot-state` | data/boot.state if present | Checkpoint to boot from; `skip` forces legacy bypass |

## Common Pitfalls & Fixes

### 1. ModuleNotFoundError: No module named 'numpy'
**Symptom:** Error when importing numpy despite having requirements.txt
**Fix:** Always activate the virtual environment first:
```bash
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. API Key Not Found
**Symptom:** `WARNING: No OpenRouter API key found. Using stub AI mode`
**Fix:** 
```bash
cp .env.example .env
# Edit .env and add your OPENROUTER_API_KEY from https://openrouter.ai
```

### 3. ROM File Not Found
**Symptom:** `ERROR: ROM file not found: data/rom/Pokemon - Blue Version...`
**Fix:**
```bash
ls data/rom/
# Ensure the exact filename matches (case-sensitive)
# Place your .gb or .gbc ROM in data/rom/
```

### 4. Database Errors
**Symptom:** `sqlite3.OperationalError: unable to open database file`
**Fix:**
```bash
mkdir -p runs/test_001  # Ensure save directory exists
python3 src/game_loop.py --rom "...rom file..." --save-dir runs/test_001
```

### 5. Poor Performance / Slow Execution
**Symptoms:** Low ticks per second, stuttering, high CPU usage
**Fixes:**
1. Increase screenshot interval: `--screenshot-interval 120` (default 60)
2. Limit session length: `--max-ticks 5000`
3. Close other applications to free resources
4. Verify virtual environment is activated

## Performance Characteristics

### Timing Measurements (dogfood run, 2026-10-27, HEAD 2d75ced)
Measured with the project venv on a normally loaded host; re-measure before quoting.

| operation | exact command | time |
|---|---|---|
| offline validation (cold) | `.venv/bin/python cron_runner.py --dry-run --skip-key-check` | 0.11 s (rc=0) |
| validation + key liveness | `.venv/bin/python cron_runner.py --dry-run` | 1.15 s (rc=0) |
| **headline: real gameplay** | `/usr/bin/time -p .venv/bin/python cron_runner.py --run-id <id> --cycles 80` | **49.40 s (rc=0) = 0.62 s/cycle** |
| per-cycle fast path (jev) | (inside the run) | ~0.36 s/cycle |
| teacher repair (LLM call) | 2 calls inside the run | 12.05 s / 8.79 s ($0.0015 / $0.0016) |
| dashboard route (`/status`, `/metrics`) | `curl` on a scratch port | 0.7–1.3 ms |

`time -p` split for the 80-cycle run: real 49.40, user 4.44, sys 0.34 — the run is wall-bound on LLM
calls, not CPU-bound. Historical (2026-09-26, DOGFOOD-PERF-001): 22.42 s for 5 cycles cold / 8.02 s warm,
i.e. ~4.5 s per cycle; that is where the numbers above came from, so treat anything older than the dated
row as stale.

### Bottlenecks
1. **Teacher escalation LLM calls** — two synchronous calls cost 12.0 s + 8.8 s in the 2026-10-27 run
   (21 s of the 49.4 s wall). One `--dry-run` with key liveness also pays ~1 s of provider round-trips.
2. **Frame caching** — initial population takes time; repeats are `[CACHE-HIT]` and cheap.
3. **Recovery systems** — direction-lock detection adds negligible overhead (lock-rate 3/80 in the
   2026-10-27 run).


### Optimization Notes
- The RAM reader pipeline eliminates vision API costs entirely
- Frame cache reduces redundant processing after warm start
- Recovery systems are lightweight and only trigger on actual stuck states

## Integration Depth

### What You Actually Integrate With
When using PTP-01X, you integrate with:
1. **RAM Reader Subsystem** - Direct memory access to PyBoy emulator
2. **LLM Controller Interface** - JSON-based prompts/responses to OpenRouter
3. **Recovery System** - Automatic handling of direction locks and stuck states
4. **Checkpoint System** - Persistent boot states for consistent runs

### What You Don't Need to Worry About
- Vision/OCR processing (completely bypassed)
- Manual frame-by-frame analysis
- Paid API calls per game tick
- Emulator speed/timing issues (handled internally)

## The "Right Way" Patterns

### For New Users
1. **Always use the virtual environment** - dependencies are isolated there
2. **Start with cron_runner.py** - it's the proven, performant path
3. **Begin with 20 cycles** - enough to see overworld navigation and decision-making
4. **Check the logs** - `cron_logs/run_<id>.jsonl` shows every decision
5. **Review screenshots** - visual validation of what the AI actually saw

### For Advanced Usage
1. **Experiment with different ROMs** - Red vs Blue have slight differences
2. **Adjust cycle count based on goals** - longer runs do not automatically leave the starting area:
   the shipped `data/boot.state` boots in **Pallet Town (map 0, tile (6,6))** and the 2026-10-27
   80-cycle run spent 76 of its cycles inside Red's House 1F; treat "reached the next map" as the
   measurement, not the cycle count
3. **Monitor the lock-rate** - shown in final summary; healthy runs <50% (3/80 = 4% on 2026-10-27)
4. **Use custom run IDs** - makes it easy to find specific logs/screenshots
5. **Read the run's `run_autonomy` row, not just the summary line** - it carries
   `handoff_trigger_counts`, `handoff_blocked` and `escalation_rate_by_missing_class`, which is how you
   see that a high-autonomy run was actually pinned (2026-10-27: autonomy 0.925 with 78 of 80 handoff
   triggers blocked)


## Validation & Testing

### Smoke Test
```bash
source .venv/bin/activate
python3 cron_runner.py --dry-run
```
Two legitimate outcomes — read which one you got:
- **rc=0** with `[DRY-RUN] Validation OK` — the checkout has the ROM (`data/rom/...gb`) and the keys
  resolve. This is what you get on an already-provisioned box (measured 1.15 s with key liveness,
  0.11 s with `--skip-key-check`).
- **rc=1** with `[DRY-RUN] ERROR: ROM not found at data/rom/Pokemon - Blue Version (USA, Europe) (SGB
  Enhanced).gb ... Fix: you must own the game; place your own dump at ...` — expected on a **fresh
  clone**, because ROMs are not bundled. Measured on a clean Ubuntu 24.04.4 box (2026-10-27): rc=1,
  zero LLM calls. This is not a broken install; supply the ROM and re-run.

Offline variant that never touches the network: `python3 cron_runner.py --dry-run --skip-key-check`.


### Quick Functional Test
```bash
source .venv/bin/activate  
python3 cron_runner.py --run-id smoke-test --cycles 5
# Should complete 5 cycles, produce logs and screenshots
```

### Full Test Suite
```bash
source .venv/bin/activate
pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests/ -v
```

## Maintenance Notes

### When Things Break
1. **Check logs/** directory for detailed error traces
2. **Verify virtual environment activation** - most import errors stem from this
3. **Confirm API key is set** in .env file
4. **Ensure ROM file exists** in data/rom/ with exact filename match

### Updating Dependencies
```bash
source .venv/bin/activate
pip install -r requirements.txt  # runtime
pip install -r requirements-dev.txt  # + development tools
```

## Troubleshooting Flowchart
```
Start → Activate venv? → No → source .venv/bin/activate
        ↓ Yes
Install deps? → No → pip install -r requirements.txt  
        ↓ Yes
API key set? → No → Edit .env with OPENROUTER_API_KEY
        ↓ Yes
ROM exists? → No → Place .gb/.gbc file in data/rom/
        ↓ Yes
Run cron_runner.py → Check exit code and logs
```

## Cost Estimates
- **Per 20-cycle run**: ~$0.02 in API calls (OpenRouter pricing)
- **Per hour of gameplay**: ~$0.60 (at 20 cycles/minute estimate)
- **Storage**: Minimal - logs and screenshots (~10MB/hour)
- **Compute**: Low - mostly waiting on API responses

## Safety Notes
- No permanent modifications to system or data
- All runs are self-contained in the repository
- Save directory can be customized with `--save-dir`
- Emergency stop: Ctrl+C safely terminates the process

## Pitfalls verified live 2026-10-19 (read these before driving the bridge, MCP or dashboard)

### 1. A drawn menu does not make the screen say `menu`
`SCREEN: overworld` in the projection (bridge `observe`, MCP `game_observe`, anything that renders
`state_projection`) stays `overworld` **while the START menu is open**. `RAMReader.screen_type()`
(`src/core/ram_reader.py:1157-1185`) only detects a two-item YES/NO prompt
(`_has_yes_no_menu()`, `:1202-1206`, `wMaxMenuItem == 1`); list menus fall through to overworld.
So: after any `START` press, do not trust the tile/facing for walkability — check whether the frame
changed (or press `B` once) before concluding a direction is blocked. Tracked as DF-AIPP-10.

### 2. Hold buttons long enough, and verify by pixels not by the summary text
`play.py --frames 30 press START` is what opens the menu (`--frames 5` = one tap, and the press
summary still reads `state_changed: False` either way). The honest discriminator is the frame:
`play.py frame before` / `frame after` and compare — the menu is ~12.5 % of the pixels, and a
30-frame `B` restores the first frame byte-for-byte. Diagnostic buttons (`START`, `SELECT`, `A` on
title) need 15–30 frames; movement needs 5.

### 3. `session_id` is a QUERY parameter on every dashboard route
`python3 -m src.dashboard.main` starts a server whose REST routes all take `?session_id=` and default
to `default` (`src/dashboard/main.py:245-373`). Passing `session_id` in a JSON **body** is silently
ignored (the handlers declare it as a scalar query param) — the call succeeds against `default`
instead, e.g. pausing the wrong session with a `200`. The shipped UI has this bug on its control
buttons (DF-AIPP-11); always pass it as a query string when scripting the API:
`curl -X POST -H "X-API-Key: $KEY" ".../control/pause?session_id=$ID"`.
Auth is fail-closed: with no `PTP_API_KEY` every authenticated route answers 401.

### 4. Port attribution before you blame the product
On a host that already runs other services, the documented dashboard default port (`8000`) can be
held by an unrelated process (here: `dexdat-api` behind `docker-proxy`). Confirm
`ss -ltnp | grep <port>` names *your* pid, and use `PTP_DASHBOARD_PORT` for scratch instances.

### 5. The 1-second preflight, and exit codes read directly
`.venv/bin/python cron_runner.py --dry-run` validates ROM/boot-state/keys with zero API calls and
exits 0 in ~1.1 s; it exits **1** on a missing ROM (a fresh clone), naming the file to place. Capture
`$?` directly — a status read through a pipe reports the last pipeline element, not the runner.

### 6. Fresh installs resolve newer versions than the repo venv
`requirements.txt` carries lower bounds (`pyboy>=1.0.0,<2.8.0`, `fastapi>=0.142.2`, …), so a clean
box installing today gets fastapi 0.150.0 / Pillow 13.0.0 / websockets 17.3 even though the repo
venv may hold 0.146.0. Install is still rc=0 and 26 s on a clean box (clone 1 s + venv 4 s + pip
20 s), with the ROM wall as the only honest failure.
