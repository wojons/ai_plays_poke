# ai-plays-poke — Real-Use Integration Report (2026-08-16)

Dogfood run by the coding-hermes cron. This run re-verified the paths flagged on
2026-08-07 (DF-001 crash, DF-002 double extension, missing docs) **and** the
board claims made since (AP-GAP-001 "game_loop verified working", AP-GAP-015/16/17
CLI fixes). Verdict: the primary path is genuinely better than August 7 — it now
picks a starter end-to-end — but the "repaired" legacy path still delivers **zero
gameplay** and now **fabricates battle wins**.

## TL;DR

| Surface | Status 2026-08-07 | Status 2026-08-16 (verified) |
|---|---|---|
| `cron_runner.py --cycles 20` | ✅ 10/10 cycles, movement | ✅ **20/20 cycles, starter PICKED (Charmander, party 0→1)** |
| `src/game_loop.py --max-ticks 40` | 🔴 vision crash every tick, 0 decisions | 🟠 crash FIXED, but **0 commands / 0 AI decisions / stuck on title screen / 2 fabricated wins** |
| `python -m src.ptp_cli --help` | 🔴 ModuleNotFoundError | ✅ exit 0, full usage |
| `python -m src.debug_screen --help` | 🔴 booted emulator, no help | ✅ exit 0 in ~0.1s |
| `python -m src.memory_reader --help` | 🔴 booted emulator, no help | ✅ exit 0 in ~0.02s |
| `ram_map_server.py` :8099 | 12/15 documented | ✅ 200/200/404, full JSON schema — but **boots to `name_entry`, not overworld** |

**Use `cron_runner.py` for real gameplay. It works, and it just got its first
starter-pick milestone in a dogfood run.**

## The working path — autonomous E2E runner (verified 2026-08-16)

```bash
cd /home/kara/ai_plays_poke
source .venv/bin/activate
python3 cron_runner.py --run-id dogfood_20260816_001 --cycles 20
```

### What actually happened (20/20 cycles, exit 0, ~4 min wall)

1. Cycles 1–8: **overworld navigation** — player moved across 9 unique
   coordinates in Pallet Town (e.g. (2,3) → (2,4) → (4,4) → (5,3)) with coherent
   LLM intents ("Move east toward Pallet Town's north exit alignment..."),
   `openai/gpt-5.6-luna` via OpenRouter, ~3.2 s and ~$0.016–0.018 per cycle.
2. Cycles 9–16: entered the lab, **dialog mode** — the AI spammed A through
   Oak's dialog; recovery ladder fired twice:
   - `[RECOVER] dialog_advance — 12× A — advancing dialog text (screen-locked (dialog x5))`
   - `[RECOVER] Level 0: starter_approach — moved to the first Poké Ball and pressed A (tile-locked (map 40 @ (5,3) x8 cycles))`
3. Cycle 18: **`[STARTER] Oak's Lab menu detected... selecting first starter` →
   `[STARTER-PICKED] party_count=1 species_hint=Charmander`** — the
   GAMEPLAY-STARTER-001 feature (party 0→1 milestone via RAM) fired live.
4. Cycles 19–20: back to **overworld** with the Charmander in party.
5. Outputs: `cron_logs/run_dogfood_20260816_001.jsonl` (23 rows: 20 cycles + 3
   event rows — 2 `state_saved`, 2 `recovery`, `starter_selection`,
   `starter_picked`), `screenshots/run_dogfood_20260816_001/step_0001..0020.png`
   (160×144), frame cache 284 unique / 767 refs.

### JSONL event rows (verified)

```json
{"cycle": 18, "screen": "menu", "event": "starter_selection",
 "action": "confirm_first_starter_then_decline_nickname", "map_id": 40,
 "party_count_before": 0, "party_count_after": 1, "player_tile_x": 6, "player_tile_y": 4}
{"cycle": 18, "event": "starter_picked", "party_count": 1, "species_hint": "Charmander"}
```

Note: per-cycle cost is NOT in the JSONL (stdout only, `📡 API: ... $0.018390`).
Run totals: 20 cycles ≈ $0.16–0.30.

## The legacy path — `src/game_loop.py` (crash fixed, gameplay still absent)

```bash
timeout 600 .venv/bin/python src/game_loop.py \
  --rom "data/rom/Pokemon - Blue Version (USA, Europe) (SGB Enhanced).gb" \
  --max-ticks 40 --save-dir /tmp/dogfood-game_loop
```

### What actually happened (GAMELOOP_EXIT=0, 272.5 s)

- ✅ **DF-001 crash is GONE**: 0 × `Vision analysis failed`; 40/40 real
  OpenRouter vision calls succeed (`📡 API: openai/gpt-5.6-luna | ~2700ms |
  $0.0049–0.0056 | Success: True`), HP formatting safe (`HP: 100%/100%`).
- ✅ **DF-002 double extension is GONE**: save file is `emulator_state.state`
  (single extension). Clean exit, DB written. ⚠️ The session export
  (`session_<id>_export.json`) is written to the **CWD, not the save-dir**
  (database.py:504) — my run dropped `session_1_export.json` in the repo root
  (GAP-025).
- ❌ **40/40 vision calls classify the screen as the Pokémon Blue TITLE SCREEN**
  ("This is the Pokémon Blue title screen. Press A/START"). The game never
  leaves the title. The tick-16 boot-progression START press
  (`game_loop.py:268-282`, fires only `if ai_decisions == 0 and not
  pending_commands`) either didn't fire or didn't advance the game — one START
  on the Gen-1 title screen just blinks the "PRESS START" text; the code never
  verifies a transition or presses a second time.
- ❌ **Final stats: Commands Sent: 0, AI Decisions: 0, Screenshots: 1**.
  Vision `recommended_action` (press:A / press:START) is logged but never
  becomes a queued command.
- ❌❌ **Battles: 2, Wins: 2** — fabricated. The `battles` table contains
  `('unknown (dark silhouette)', status='victory')` and
  `('unidentified (sprite unclear)', status='victory')` from a run that never
  left the title screen. The battle detector fires on unverified screen
  transitions during boot and records "victory" for unidentified sprites.
- 💸 ~$0.21 spent on vision for zero progress (still ~$0.005/tick, better than
  the old $0.013 but all of it wasted).

**Bottom line:** AP-GAP-001's crash fix is real, but its acceptance claim
("≥ 1 AI decision") did **not** reproduce (T101 saw 4 decisions; today 0).
The board closed a "P0 documented entry point dead → verified working" task
while the path still produces no gameplay — the three-layer termination check
(L3: it WORKS for a user) was not met. Now tracked as GAP-020 (P1).

## Web map viewer — `ram_map_server.py` (verified 2026-08-16)

```bash
.venv/bin/python ram_map_server.py   # http://localhost:8099
```

- `GET /` → 200 (HTML, "PTP-01X — RAM Map Viewer"), `GET /data.json` → 200 with
  full schema (`map_name, map_id, tileset, w, h, blocks (16), block_types
  (floor/object/stairs/wall), player_x/y, facing, moving, screen_type,
  adjacent, minimap`), `GET /nonexistent` → 404. All instant (~1 ms).
- ⚠️ Boot lands at **`screen_type: "name_entry"`** (Red's House 2F, map 38) —
  the docs' claim "Emulator reaches overworld state after title bypass + intro
  skip" did not reproduce. The server is read-only (only `do_GET`, no input
  endpoint), so the emulator is permanently stuck pre-game: the viewer can
  never show actual gameplay. → GAP-024.

## CLI surface (all previously broken, all verified fixed)

| Command | Result |
|---|---|
| `PYTHONPATH=src .venv/bin/python -m src.ptp_cli --help` | exit 0, full flag usage (AP-GAP-015 ✅) |
| `PYTHONPATH=src .venv/bin/python -m src.debug_screen --help` | exit 0, no emulator boot (AP-GAP-016 ✅) |
| `PYTHONPATH=src .venv/bin/python -m src.memory_reader --help` | exit 0, no emulator boot (AP-GAP-017 ✅) |
| `python3 cron_runner.py --help` | exit 0, clean usage |

## Cost & resource expectations (measured 2026-08-16)

- cron_runner: ~$0.016–0.018/cycle (gpt-5.6-luna, 1 LLM call/cycle, RAM reader
  state free); 20 cycles ≈ $0.16–0.30; ~4 min wall; dialog cycles ~0.2 s
  (button presses, no API call), overworld cycles ~3.2 s.
- game_loop.py: ~0.005/tick vision call even when the game is stuck on the
  title screen. Do not run it for "gameplay" until GAP-020 lands.
- No memory growth observed in the 20-cycle run; frame cache persists.

## Pitfalls (updated for 2026-08-16)

1. **Still: judge this project by `cron_runner.py`, not `src/game_loop.py`.**
   The README legacy section and the usage SKILL.md both carry stale
   "broken/under repair" claims (GAP-023) — the crash is fixed, but the path
   still does nothing, and its metrics can fabricate wins (GAP-021).
2. game_loop session rows in `game_data.db` always say `model_name='stub_ai'`
   even when real vision ran (GAP-022) — don't trust that column.
3. `emulator_state.state` (single ext) + `session_1_export.json` now land in
   the save-dir — the old `.state.state` bug is fixed.
4. The ram_map_server's own emulator boots to `name_entry` and cannot be
   driven (no input endpoint) — use it as a RAM/schema demo, not a gameplay
   viewer (GAP-024).
5. Harmless: `UserWarning: SDL2 binaries from pysdl2-dll` on stderr;
   `[WARN] Direction-locking` lines in cron_runner are the recovery ladder
   working as designed.
6. `.env` holds API keys — never commit it. Both `OPENROUTER_API_KEY` and
   `DEEPSEEK_API_KEY` are set in this checkout.
