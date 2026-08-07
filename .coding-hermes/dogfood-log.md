# Dogfood Log — ai-plays-poke (PTP-01X)

| Date | Verdict | Runner | Time-to-first-success | Top findings |
|---|---|---|---|---|
| 2026-08-07 | 🟡 PROMISING-BUT-ROUGH | dogfood cron | ~6 min (cron_runner 10-cycle E2E) | DF-001 (P0) game_loop.py AI pipeline dead — vision None-HP crash 15/15 ticks, 0 AI decisions; DF-002 .state.state double ext; DF-003 working path (cron_runner) undocumented; DF-004 specs/AGENTS.md is DexDat content; DF-005 pass criteria too shallow |

## Run 2026-08-07 (dogfood cron)

**Promise:** "A user can run `python3 src/game_loop.py --rom <ROM>` and watch an LLM-driven AI autonomously play Pokémon (vision pipeline, GOAP decisions, battle heuristics), with screenshots, saves, and a session DB."

**What was actually done (real use, not tests):**
1. `src/game_loop.py --help` → OK (exit 0; cosmetic SDL2 UserWarning on stderr).
2. `src/game_loop.py --rom /nonexistent.gb` → `❌ ROM file not found`, exit 1 ✅.
3. `src/game_loop.py --rom <real Blue ROM> --max-ticks 40` → exit 0, clean exit (GAP-001 fix holds), but **0 screenshots, 0 commands, 0 AI decisions**, 15/15 ticks print `❌ Vision analysis failed: unsupported format string passed to NoneType.__format__`, 128.6s for 40 ticks (3.2s/tick). Save file is `emulator_state.state.state`.
4. `cron_runner.py --run-id dogfood_20260807_0015 --cycles 10` → **10/10 cycles, 13 actions, player moved (2,3)→(7,1) in Pallet Town with coherent LLM intents, 13/13 OpenRouter calls OK (~$0.17), recovery fired 2× (direction-lock), 10 screenshots (160×144), JSONL event log, EXIT 0.** This is the real, working gameplay path — and it is undocumented for users.

**Verdict: 🟡 PROMISING-BUT-ROUGH.** The core promise genuinely works (cron_runner plays the game with real LLM decisions and observable progress), but the README-documented entry point silently fails its AI pipeline on every tick while still exiting 0 — the "exit-0 false success" pattern. Time-to-first-success on the working path: ~6 min (setup + 10-cycle run). Friction count: 4 real frictions (dead AI path, no docs for working path, .state.state, stray DexDat AGENTS.md).

**Board:** DF-001 (P0), DF-002..005 (P2) added via events parquet (actor=dogfood, event 54).

**Artifacts left:** docs/dogfood/2026-08-07-integration.md, docs/dogfood/diagnostics.md, skills/ai-plays-poke-usage/SKILL.md.
