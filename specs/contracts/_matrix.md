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
