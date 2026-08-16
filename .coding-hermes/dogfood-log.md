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

| 2026-08-16 | 🟡 PROMISING-BUT-ROUGH | dogfood cron | ~4 min (cron_runner 20-cycle E2E) | GAP-020 (P1) game_loop 0 commands/0 decisions, stuck on title 40/40 vision calls — AP-GAP-001 acceptance did NOT reproduce; GAP-021 (P1) 2 fabricated 'victory' battles from title-screen run; GAP-022/023/024 (P2) stub_ai telemetry lie, stale docs, viewer name_entry |

## Run 2026-08-16 (dogfood cron)

**Promise:** "A user can run `python3 cron_runner.py --run-id X --cycles N` and watch an
LLM-driven AI autonomously play Pokémon (RAM-reader state, real LLM decisions, recovery
ladder) — and the README-documented `src/game_loop.py` path, dead on 2026-08-07 (DF-001),
is now repaired (AP-GAP-001 complete)."

**What was actually done (real use, not tests):**
1. `cron_runner.py --run-id dogfood_20260816_001 --cycles 20` → **20/20 cycles, EXIT 0**:
   overworld nav across 9 unique coords (Pallet Town), Oak's Lab dialog + menu, 2 recoveries
   (dialog_advance, starter_approach), **`[STARTER-PICKED] party_count=1 species_hint=Charmander`
   at cycle 18** — full intro→starter milestone end-to-end; 20 screenshots (160×144), JSONL
   log with starter_selection/starter_picked event rows, ~$0.16–0.30, no memory growth.
2. `src/game_loop.py --rom <SGB Blue> --max-ticks 40 --save-dir /tmp/dogfood-game_loop` →
   EXIT 0, 272.5s. **DF-001 crash FIXED** (0 vision failures, 40/40 real gpt-5.6-luna calls
   ~$0.005 each) and DF-002 fixed (`emulator_state.state` single ext, clean export). **BUT**:
   40/40 vision calls classify the title screen, `Commands Sent: 0`, `AI Decisions: 0`,
   `Screenshots: 1` — the tick-16 single START press (game_loop.py:268) doesn't get past the
   Gen-1 title, and vision recommended_action is never queued as a command. **AND** the run
   recorded **2 fabricated battles with status 'victory'** (unknown silhouette) → stats claim
   Wins: 2 from a run that never left the title. AP-GAP-001's '>= 1 AI decision' acceptance
   did NOT reproduce (T101 saw 4; today 0).
3. `ram_map_server.py` → / 200, /data.json 200 (full schema: map_name/map_id/blocks/player/
   minimap/adjacent), /nonexistent 404 — but emulator boots to `screen_type=name_entry`
   (Red's House 2F, map 38), not overworld; server read-only (GET only) → viewer stuck pre-game.
4. CLI probes: `python -m src.ptp_cli|debug_screen|memory_reader --help` all EXIT 0 instantly
   (AP-GAP-015/016/017 verified fixed).

**Verdict: 🟡 PROMISING-BUT-ROUGH.** The primary promise now delivers a full milestone
(starter picked, party 0→1, real LLM decisions, recoveries) — genuinely close to shippable.
But the second documented entry point still delivers zero gameplay and now quietly
fabricates win metrics; board acceptance claims (AP-GAP-001) did not reproduce at L3;
docs/skill drifted stale in the opposite direction. Time-to-first-success: ~4 min.
Friction count: 4 real frictions (game_loop no gameplay + phantom wins, stub_ai telemetry,
stale docs, viewer name_entry lock).

**Board:** GAP-020 (P1), GAP-021 (P1), GAP-022..024 (P2) appended to tasks.jsonl, event 130
(actor=dogfood).

**Artifacts left:** docs/dogfood/2026-08-16-integration.md (new),
docs/dogfood/diagnostics.md (2026-08-16 section appended),
skills/ai-plays-poke-usage/SKILL.md (v1.1.0 refresh).
