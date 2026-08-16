---
name: ai-plays-poke-usage
description: >-
  How to actually USE the ai-plays-poke (PTP-01X) autonomous Pokémon AI system:
  the working E2E runner (cron_runner.py — proven through starter pickup), the
  legacy game_loop.py path (crash fixed 2026-08-16 but STILL zero gameplay,
  GAP-020), setup, cost expectations, and the JSONL output schema.
version: 1.1.0
---

# Using ai-plays-poke (PTP-01X)

Autonomous Pokémon AI benchmarking system: PyBoy emulator + LLM decision loop
that plays Pokémon Blue/Red. Maintained by a coding-hermes foreman (board in
`.coding-hermes/board/tasks.jsonl`, JSONL canonical).

## Entry points (IMPORTANT — verified 2026-08-16)

| Path | Status | Use for |
|---|---|---|
| `python3 cron_runner.py --run-id <id> --cycles N` | ✅ **WORKS — proven to pick a starter** | Real autonomous gameplay + benchmarking (fleet E2E fixture) |
| `python3 src/game_loop.py --rom <ROM> --max-ticks N` | 🟠 Crash fixed, **still 0 commands / 0 AI decisions** (GAP-020); **fabricates battle wins** (GAP-021) | Nothing yet — wait for GAP-020 |
| `PYTHONPATH=src .venv/bin/python -m src.ptp_cli --help` | ✅ works (AP-GAP-015) | Config CLI |
| `PYTHONPATH=src .venv/bin/python -m src.debug_screen --help` | ✅ works (AP-GAP-016) | Screen debug |
| `PYTHONPATH=src .venv/bin/python -m src.memory_reader --help` | ✅ works (AP-GAP-017) | RAM dump debug |
| `.venv/bin/python ram_map_server.py` → :8099 | ✅ serves JSON, but boots to `name_entry` and is read-only (GAP-024) | RAM-state schema demo only |

**Never judge this project by `src/game_loop.py`.** The working system is
`cron_runner.py`. Board truth (2026-08-16): GAP-020 (P1), GAP-021 (P1),
GAP-022–024 (P2) pending.

## Quick start (working path — 2026-08-16 proven run)

```bash
cd /home/kara/ai_plays_poke
source .venv/bin/activate          # deps installed; .env has API keys
python3 cron_runner.py --run-id demo1 --cycles 20
# ~4 min, ~$0.16–0.30. Watch: overworld nav → Oak's Lab dialog → starter picked
```

Outputs:
- `cron_logs/run_<id>.jsonl` — per-cycle JSON (screen, plan, intent,
  player_x/y, map_name) + event rows (`recovery`, `state_saved`,
  `starter_selection`, `starter_picked`)
- `screenshots/run_<id>/step_000N.png` — 160×144 frames (one per cycle)

## What a healthy run looks like (2026-08-16, 20 cycles)

```
[1/20] overworld | RAM reader x6 | 3.2s      ← 1 LLM call/cycle, gpt-5.6-luna
[WARN] Direction-locking detected: RIGHT x3   ← recovery ladder working
[RECOVER] Level 0: alternate_direction ...
[RECOVER] dialog_advance — 12× A ...          ← stuck in Oak's dialog
[RECOVER] Level 0: starter_approach — ...     ← tile-locked at Poké Balls
[STARTER] Oak's Lab menu detected at cycle 18; selecting first starter
[STARTER-PICKED] party_count=1 species_hint=Charmander
[dogfood_20260816_001] Done. 23 actions. Screens: {'dialog', '?', 'overworld', 'menu'}
```

Player position MUST change across cycles (verified: 9 unique coords, Pallet
Town (2,3)→Oak's Lab (5,3), map 0→40). If positions never move, the run is
stuck — that's data, not a crash. Starter pick proves the full
intro→dialog→menu→party milestone loop works end-to-end.

## Cost & time

- ~$0.016–0.018 per overworld cycle; dialog cycles ~0.2 s with no API call.
- 20 cycles ≈ 4 min wall, ~$0.16–0.30; 80 cycles ≈ 2.5–10 min, ~$1.10–1.40.
- Model: `openai/gpt-5.6-luna` via OpenRouter (`.env` → `OPENROUTER_API_KEY`);
  `deepseek-v4-flash` fallback for battles.
- Cost is on stdout (`📡 API: ... | $<cost>`), NOT in the JSONL.

## Pitfalls (verified 2026-08-16)

1. `src/game_loop.py`: the 2026-08-07 crash (DF-001) is FIXED — 40/40 real
   vision calls succeed, clean exit, `emulator_state.state` single extension.
   But: 40/40 calls classify the **title screen**, `Commands Sent: 0`,
   `AI Decisions: 0` (GAP-020), and the run records **2 fabricated
   'victory' battles** from the title screen (GAP-021). README:193-196 and
   older copies of this skill say "broken/under repair" — that claim is now
   stale in the opposite direction (GAP-023).
2. game_loop `game_data.db` session rows always log `model_name='stub_ai'`
   even when real vision ran (GAP-022) — don't trust that column. The session
   export also ignores `--save-dir` and lands in the CWD (GAP-025).
3. `ram_map_server.py` boots its emulator to `name_entry` (not overworld as
   usability-tests.md claims) and has no input endpoint — read-only (GAP-024).
4. `--multi-instance` on game_loop raises NotImplementedError (stub).
5. `specs/AGENTS.md` is stray DexDat content — ignore; use root `AGENTS.md`.
6. `UserWarning: SDL2 binaries` on stderr is harmless.
7. `.env` holds API keys — never commit or copy it.
8. Pre-existing working-tree noise to leave alone: `data/duration_profiles.json`
   (modified) and `dagger.db` (untracked).

## Verifying fixes (L3 standard)

- **cron_runner fixes:** run ≥ 20 cycles; require exit 0, ≥ 1 recovery or
  screen transition, player coordinates that CHANGE, and the starter milestone
  (party_count 0→1) on a fresh save. Exit 0 alone proves nothing.
- **game_loop fixes (GAP-020/021):** run 40 ticks with a fresh save-dir;
  require `Commands Sent >= 1`, vision responses that are NOT all "title
  screen", `Battles: 0, Wins: 0` on a non-battle run, and
  `model_name != 'stub_ai'` in the session row (GAP-022).

## Board & fleet context

- Foreman ticks every 6 h (CooldownS=21600, fleet.toml pin); E2E-001 fixture
  runs cron_runner in windowed ticks; NEVER-DONE runs a perpetual audit.
- Board: `.coding-hermes/board/tasks.jsonl` + `events.jsonl` (canonical, git
  tracked; board.db/parquet are gitignored). Task rows are JSON objects, one
  per line, `id`/`title`/`status`/`priority`/`complexity`/... schema; event
  rows use `event_type`/`actor`/`detail`.
- Proven E2E evidence: T167 20/20 (starter picked, $0.1641); dogfood
  2026-08-16 20/20 (starter picked Charmander, 2 recoveries, exit 0);
  luna_v16 80/80 (starter + trainer battle, $0.60/43 calls).
