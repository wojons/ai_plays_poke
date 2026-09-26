# PTP-01X Dogfood Integration Report - 2026-09-26

## How to Use PTP-01X for Real Autonomous Pokémon Gameplay

### Entry Point
The primary working entry point for autonomous gameplay is `cron_runner.py` — an E2E runner that reads game state directly from emulator RAM (free, instant) and uses LLM calls only for game decisions.

### Quick Start (Working Path)
1. Create virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Set up API key:
   ```bash
   cp .env.example .env
   # Edit .env — add your OPENROUTER_API_KEY
   ```

4. Run (example: 80 AI decision cycles):
   ```bash
   python3 cron_runner.py --run-id demo1 --cycles 80
   ```

### What This Does
Each cycle reads the game state directly from emulator RAM (no paid vision API calls per tick), sends the spatial data to the LLM controller (`openai/gpt-5.6-luna` for overworld navigation, `deepseek-v4-flash` for battles), and executes the returned button plan with built-in recovery (direction-lock detection, checkpoint rollback).

### Boot State
`cron_runner.py` boots from the shipped known-good checkpoint `data/boot.state` when present — the player is standing in Oak's Lab in Pallet Town with the starter already picked (map 0x28, tile ~(4,4), party of 1), no dialog open.

### First Cycles Expectation
Cycle 1 observes the overworld via RAM and sends the spatial state to the controller; the first plan usually walks toward the lab exit. You will see `[CACHE-HIT]` frame-reference lines and occasionally `[WARN] Direction-locking detected: <dir> x3` warnings (straight hallway walks trigger them even while moving). This is NOT a failure by itself.

### Outputs
- `cron_logs/run_<id>.jsonl` — one JSON line per cycle: screen type, button plan, LLM intent, player coordinates (x/y), map name, plus event rows (recovery, state saved)
- `screenshots/run_<id>/step_NNNN.png` — 160×144 RGB frame per cycle

### Performance Characteristics (from dogfood run)
- Cold start (5 cycles): 22.42 seconds
- Warm start (5 cycles): 8.02 seconds
- Per cycle average: ~4.5 seconds cold, ~1.6 seconds warm
- Primary bottleneck: LLM API calls (~4-6 seconds per call)

### Integration Notes
- The project is currently DISABLED in the scheduler (CooldownS=43200) as all gameplay tasks are marked complete
- To re-enable for testing, manual intervention via Bane is required
- The RAM reader pipeline provides perfect state extraction without vision APIs
- LLM calls are only used for decision-making, not perception
- Recovery systems handle direction locks and stuck states automatically

### Troubleshooting
- If numpy is missing: ensure virtual environment is activated and dependencies installed
- For API key errors: verify .env file contains OPENROUTER_API_KEY
- For emulator issues: check ROM path in config/settings.yaml