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

### Timing Measurements (from dogfood run)
- **Cold start** (5 cycles): 22.42 seconds real time
- **Warm start** (5 cycles): 8.02 seconds real time  
- **Per API call**: ~4-6 seconds (primary bottleneck)
- **Per cycle average**: 4.5s cold, 1.6s warm

### Bottlenecks
1. **LLM API calls** (~80% of time) - OpenRouter latency
2. **Frame caching** - Initial population takes time
3. **Recovery systems** - Direction lock detection adds overhead

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
2. **Adjust cycle count based on goals** - 80+ cycles reliably exits Oak's Lab
3. **Monitor the lock-rate** - shown in final summary; healthy runs <50%
4. **Use custom run IDs** - makes it easy to find specific logs/screenshots

## Validation & Testing

### Smoke Test
```bash
source .venv/bin/activate
python3 cron_runner.py --dry-run
# Should exit with code 0 and print validation success
```

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