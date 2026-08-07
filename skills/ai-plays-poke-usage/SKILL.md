---
name: ai-plays-poke-usage
description: >-
  How to actually USE the ai-plays-poke (PTP-01X) autonomous Pokémon AI system:
  the working E2E runner (cron_runner.py), the broken README path (game_loop.py,
  DF-001), setup, cost expectations, and the JSONL output schema.
version: 1.0.0
---

# Using ai-plays-poke (PTP-01X)

Autonomous Pokémon AI benchmarking system: PyBoy emulator + LLM decision loop that plays Pokémon Blue/Red. Built and actively maintained by a coding-hermes foreman (board in `.coding-hermes/board/`, DuckDB parquet).

## Entry points (IMPORTANT)

| Path | Status | Use for |
|---|---|---|
| `python3 cron_runner.py --run-id <id> --cycles N` | ✅ WORKS | Real autonomous gameplay + benchmarking (what the fleet's E2E fixture runs) |
| `python3 src/game_loop.py --rom <ROM> --max-ticks N` | ❌ AI pipeline broken (DF-001) | Nothing yet — every tick pays a vision call that crashes on null HP; 0 AI decisions |

**Never judge this project by `src/game_loop.py`.** The working system is `cron_runner.py`.

## Quick start

```bash
cd /home/kara/ai_plays_poke
source .venv/bin/activate          # deps already installed; .env has API keys
python3 cron_runner.py --run-id demo1 --cycles 10
# ~30 s, ~$0.15. Watch: intro bypass → RAM reader state → LLM decisions
```

Outputs:
- `cron_logs/run_demo1.jsonl` — per-cycle JSON (screen, plan, intent, player_x/y, map) + `recovery`/`state_saved` event rows
- `screenshots/run_demo1/step_000N.png` — 160×144 frames
- stdout: `[N/10] overworld | RAM reader x6 | 2.6s`, `📡 API: openai/gpt-5.6-luna | <ms> | $<cost>`, `[WARN] Direction-locking`, `[RECOVER] Level 0: ...`

## What a healthy run looks like

```
[1/10] overworld | RAM reader x6 | 3.9s
[WARN] Direction-locking detected: RIGHT x3
[RECOVER] Level 0: alternate_direction — rotated from RIGHT → DOWN
[10/10] overworld | RAM reader x6 | 2.6s
[demo1] Done. 13 actions. Screens: {'?', 'overworld'}
EXIT=0
```

Player position must CHANGE across cycles (verified: (2,3)→(7,1) Pallet Town with coherent intents). If positions never move, the run is stuck — that's data, not a crash.

## Cost & time

- ~$0.013–0.018 per cycle, 1.5–4.5 s/cycle (single LLM call; RAM reader state is free)
- 80 cycles ≈ 2.5 min wall, ~$1.10–1.40, RSS ~110 MB flat
- Model: `openai/gpt-5.6-luna` via OpenRouter (`.env` → `OPENROUTER_API_KEY`)

## Pitfalls

1. `src/game_loop.py` is the README's documented entry and it is broken (DF-001, P0): 15/15 ticks `❌ Vision analysis failed: unsupported format string passed to NoneType.__format__`, 0 AI decisions, ~$0.013/tick wasted. Fix pending on the board. If you must use it, expect no AI behavior.
2. Save files from game_loop come out as `emulator_state.state.state` (double extension, DF-002).
3. `--multi-instance` raises NotImplementedError (stub).
4. `specs/AGENTS.md` is stray DexDat content — ignore; use root `AGENTS.md`.
5. `UserWarning: SDL2 binaries` on stderr is harmless.
6. `.env` holds API keys — never commit or copy it.

## Verifying fixes (L3 standard, per DF-005)

For any fix on the game_loop path, require: 40-tick run with ZERO `Vision analysis failed` lines AND `AI Decisions > 0` in final stats AND per-tick < 1 s. Exit code 0 proves nothing (the run exits 0 while doing nothing).

## Board & fleet context

- Foreman ticks every 2 h (CooldownS=7200, fleet.toml pin); E2E-001 fixture runs cron_runner every 5–10 ticks.
- Board: `.coding-hermes/board/tasks.parquet` + `events.parquet` (append with pandas, keep dtypes: datetime64[us], int8 complexity, float64 attempts).
- Past E2E evidence: luna_v16 80/80 — starter Charmander picked, trainer battle reached, RSS flat, $0.60/43 calls.
