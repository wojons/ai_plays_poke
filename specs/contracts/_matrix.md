# Contract matrix

| id | producer → consumer | contract | breaking policy |
|---|---|---|---|
| CT-01 | game_bridge → cron_runner/console | ops: press{buttons}, step{n}, save{slot}, load, frame, raw, observe, health, pause, resume, list_saves, reset, goal; loopback+token; serialised Game access | op removal is breaking; new ops additive |
| CT-02 | ram_reader → console/verdict | `render_tile_grid(cols=10, rows=9)` — 9 rows of 10 chars, arrow in player cell | grid geometry change is breaking to every verdict |
| CT-03 | vision_grid.py → perception_diff | GRID_COLS=9, GRID_ROWS=9, PLAYER_CELL=(4,4) — **CONTRADICTS CT-02** (FACT-05/07) | must be unified to one definition |
| CT-04 | vision client → verdict | 9 lines × 10 chars from the model; fence-stripped; unknown `?` allowed | fewer rows = verdict compares fewer cells (measured 8 vs 9) |
| CT-05 | console POST → state | strict bool: real booleans + true/false/1/0/yes/no/on/off; anything else = leave unchanged | adding new truthy spellings is breaking to the audit |
| CT-06 | env → code | AIPP_DECISION_MODE, CRON_DECISION_MODE, AIPP_VISION_MODELS, AIPP_VISION_MODEL, AIPP_VISION_PROVIDER, CONSOLE_PORT, AIPP_VISION_MIN_GAP/MAX_AGE | renames are breaking; additive only |
| CT-07 | board JSONL → foremen/scheduler | statuses: pending/complete/blocked/failed; default json.dumps separators; events with ids | status vocabulary is closed |
| CT-08 | battle telemetry writer → comparison reader | record identity keys (run_id, episode, encounter_id, turn, map, ts, model_decision, model_vision, provider, decision_arm) + partition path `battle-<run_id>-ep<EEE>-enc<CCC>.jsonl` (≤512 records / ≤262144 B, one encounter per file) + one manifest per run at key `/game/battle/<run_id>/manifest`; see `battle-telemetry.md` | record-field removal or a partition-key change is breaking; additive only |

## Known contract violations (measured)
- CT-02 vs CT-03: one-row vertical offset (FACT-07) — every verdict cell compare shifted.
- CT-04: 8 rows delivered vs 9 expected (measured 2026-10-01 and 2026-11-11).
- ARM-2 criterion 4: `long_run.py` still silently defaults to `'jev'` (FACT-10).

## R-table (the requirements a judge grades)

| id | statement | attaches to | assertion | evidence |
|---|---|---|---|---|
| R-001 | RAM and vision grids MUST share one definition: same cols, rows, origin, player cell | MOD-02/MOD-03 | check: `grep GRID_COLS src/core/vision_grid.py` matches the reader's render | fact: FACT-07 |
| R-002 | the bridge MUST refuse any request without the token | MOD-01 | test: tests/test_bridge_token.py | fact: FACT-01 |
| R-003 | decision mode MUST be explicit; no silent default arm in any entry script | MOD-04 | check: `grep -n "'jev'" scripts/long_run.py` returns no fallback branch | fact: FACT-10 |
| R-004 | thresholds 0.50/0.40 MUST NOT change without an operator ruling | MOD-04 | check: grep DEFAULT_HANDOFF values | fact: FACT-09 |
| R-005 | a vision reading MUST record tokens, finish reason and age, visible in the console | MOD-03/MOD-05 | test: tests/test_vision_people_probe.py | fact: FACT-12 |
| R-006 | console toggles MUST ignore malformed bodies (leave state unchanged) | MOD-05 | test: tests/… strict-bool | fact: FACT-16 |
| R-007 | panels MUST self-refresh and never blank on error | MOD-05 | check: SSE + 500-body | fact: FACT-25 |
| R-008 | only ONE writer may drive the emulator at a time | MOD-01 | check: live + agent run mutually exclusive | fact: FACT-26 |
| R-009 | people claims MUST be scored against RAM sprite cells, never a whole-grid percentage | MOD-03 | test: scripts/vision_people_probe.py | fact: FACT-14 |
| R-010 | the episode log MUST record mode, decisions, escalations, teacher calls per episode | MOD-04 | check: episode log schema | fact: FACT-20 |
| R-011 | battle telemetry MUST be partitioned: one encounter per file, every event file ≤512 records and ≤262144 B, and every event-file name parses to run_id+episode+encounter_id (no aggregate/rollup file) | CT-08 | check: paste-run `specs/contracts/battle-telemetry.md` §7.1 (lines 356-474); prints NO_TELEMETRY_FILES until BTL-STORE-1 writes files, FAILs on any violation (N2/N3/N4/N6/N8/N9) | spec: battle-telemetry.md:337-354 (N1-N9); run-id shape: cron_runner.py:957; namespace root: src/core/duckbrain_client.py:20,24-28 |
| R-012 | a comparison query MUST exclude partitions from the manifest + run_id path prefix alone — no event file may be opened whose manifest entry fails map / opponent species / level band / encounter_id / turn window | CT-08 | check: decision order §5.2 must be implemented verbatim and every answer must report read vs excluded partition counts | spec: battle-telemetry.md:207-270 (§5), manifest keys :149-206; precedent (one bounded index record): cron_runner.py:5935-5966; manifest read path: src/core/duckbrain_client.py:196-205 |
| R-013 | every record MUST carry the identity keys run_id, episode, encounter_id, turn, map, map_resolved, ts, model_decision, model_vision, provider, decision_arm, and for outcome=damage MUST satisfy damage == defender_hp_before − defender_hp_after | CT-08 | check: the required-key loop in §7.1 plus rule R4 §3.3; BTL-STORE-1 must land the pytest form as tests/test_battle_telemetry_partition.py | spec: battle-telemetry.md:58-113 (§3.1-3.3); optional model/provider precedent: cron_runner.py:5513-5522; HP clamp that makes the delta a KO bound: src/core/combat.py:198 |
| R-014 | the contract MUST NOT assert a RAM address; the reader derives addresses from the ROM symbol map, never from this document | CT-08 | check: `grep -nE "0x[0-9A-Fa-f]{4}" specs/contracts/battle-telemetry.md` returns no lines | spec: battle-telemetry.md:476-496 (§8); existing address block the reader owns: src/core/ram_reader.py:31-89; no `.sym` in data/rom as of 2026-11-17 |
