# Dogfood Integration Report — 2026-08-26

**Project:** ai-plays-poke (PTP-01X) — autonomous Pokémon AI benchmarking system
**Verdict:** ✅ SHIPPABLE (with P2 debt GAP-035..038)
**Runner:** dogfood cron (real use, not test suite)
**Cost of this run:** 25 LLM calls ≈ $0.43 (20-cycle run ~$0.35 + 5-cycle cron.sh run ~$0.08)

## Promise (null hypothesis)

> "A user can run `python3 cron_runner.py --run-id demo1 --cycles 80` and watch an
> LLM-driven AI autonomously play Pokémon Blue: RAM-reader state observation, real
> OpenRouter decisions (`openai/gpt-5.6-luna` overworld / `deepseek-v4-flash`
> non-overworld), direction-lock recovery, checkpoint saves, JSONL logs and
> screenshots per cycle. `--dry-run` validates setup without cost. The
> README-documented `.coding-hermes/cron.sh` wrapper runs the same pipeline. A
> browser viewer (`ram_map_server.py:8099`) shows live RAM state."

## What I actually did (real use, in order)

### 1. `--dry-run` (GAP-032 verification) — PASS, exit 0

```bash
python3 cron_runner.py --dry-run   # bare python3, no venv needed
```

Prints ROM path + boot-state checks, cycles, run-id, pipeline (RAM reader), the
real model/provider config, and API-key presence, then `Validation OK — exiting 0`.
No emulator boot, no LLM calls. **Time-to-first-success: ~1 min** (including
reading README).

### 2. Real 20-cycle autonomous run — 20/20, EXIT 0

```bash
.venv/bin/python cron_runner.py --run-id dogfood_20260826_001 --cycles 20
```

- **20/20 cycles, RUNNER_EXIT=0.** 23 actions. 20/20 LLM calls `Success: True`
  (`openai/gpt-5.6-luna`, ~$0.016–0.019 each).
- Summary: `Screens: {'overworld', '?', 'dialog'} | lock-rate: 4/20 (20%) |
  distinct tiles: 10`.
- Real movement: 5 unique coords in Oak's Lab
  `(2,2)→(1,1)→(2,1)→(2,2)→(1,1)→(2,2)→(1,2)→(3,2)→…` (boot.state puts the
  player in Oak's Lab with the starter pre-picked — documented behavior).
- Checkpoint saves at cycles 10 and 20 (`state_saved` events), frame cache saved
  (376 unique / 1046 refs).
- Outputs: `cron_logs/run_dogfood_20260826_001.jsonl` (23 rows: cycle rows with
  screen/pipeline/plan/intent/controller_raw + `starter_picked`/`state_saved`
  event rows), `screenshots/run_dogfood_20260826_001/step_0001..0020.png`
  (160×144).
- Wall time ≈ 3 min.

### 3. README-documented `cron.sh` wrapper (GAP-033 verification) — PASS, exit 0

```bash
bash .coding-hermes/cron.sh --cycles 5 --run-id dogfood_cronsh_20260826
```

- 5/5 cycles, EXIT 0, 5 real LLM calls, `lock-rate: 0/5 (0%)`, 5 distinct tiles,
  `=== Cron tick complete ===`. Wrapper now genuinely invokes `cron_runner.py`
  (GAP-033 fix verified at L3 — no `ModuleNotFoundError: No module named 'db'`).

### 4. Browser viewer — PASS (previous friction gone)

```bash
.venv/bin/python ram_map_server.py   # → http://localhost:8099
```

- `GET /` → 200; `GET /data.json` → 200 with full schema (map_name, map_id,
  tileset, w/h, blocks, block_types, player_x/y, facing, moving, screen_type,
  adjacent); `GET /nonexistent` → 404.
- **Boots to a real overworld now** (`Red's House 2F`, player (1,3) facing up,
  screen_type=overworld) — the GAP-024 `name_entry` lock is fixed.

## Errors / friction encountered (all minor, all P2)

| # | Friction | Evidence | Task |
|---|---|---|---|
| 1 | `--help` says overworld controller is "DeepSeek V4 Flash"; actual model is `openai/gpt-5.6-luna` (module docstring stale, cron_runner.py:6 vs :857) | `--help` vs `--dry-run` output side by side | GAP-035 |
| 2 | Summary `Screens:` set contains unexplained `'?'` value (unknown classifier bucket); undocumented in README/API doc | `{'overworld', '?', 'dialog'}` in both runs today; also in T217 E2E | GAP-036 |
| 3 | `--rom pokemon_red.gb` + default `data/boot.state` = Blue checkpoint loaded into Red with no warning (`_resolve_boot_state` checks path only) | code read cron_runner.py:903 | GAP-037 |
| 4 | 20-cycle run never left Oak's Lab / never sought the exit — no exploration goal; demo is room-wandering | coords + intents in JSONL | GAP-038 |

No P0/P1 findings. Both documented entry points deliver end-to-end.

## What held up vs the promise

- ✅ Real LLM decisions every overworld cycle (visible `📡 API: ... | $cost` lines).
- ✅ Lock-rate/direction-lock recovery, checkpoint saves, JSONL + screenshots.
- ✅ `--dry-run` zero-cost validation, works under bare python3.
- ✅ cron.sh wrapper parity with cron_runner (README claim now true).
- ✅ Viewer serves live RAM state with proper HTTP semantics.
- ✅ README + docs/api/cron_runner.md + skill are current and match reality
  (only the `--help` docstring and the `'?'` screen value are undocumented).
- ⚠️ "The first plan usually walks toward the lab exit" — today's run didn't
  (wandered instead); pass criteria (lock-rate <50%, ≥2 tiles) still met.

## The "aha" (for future agents)

The system is **RAM-reader-first**: game state comes from emulator memory (free,
instant), and the LLM only decides buttons from spatial text. That's why 20
cycles cost ~$0.35 and take ~3 min. `data/boot.state` is a known-good
starter-picked checkpoint — every run is deterministic from Oak's Lab, so the
intro→starter journey is NOT part of the default path anymore. Use
`--boot-state skip` to see the legacy title-screen intro bypass (can land
direction-locked — that's why the checkpoint is default).

## Reuse recipe (verified today)

```bash
cd /home/kara/ai_plays_poke
source .venv/bin/activate
python3 cron_runner.py --dry-run                          # free setup check (1 min)
python3 cron_runner.py --run-id demo1 --cycles 20         # real run (~3 min, ~$0.35)
bash .coding-hermes/cron.sh --cycles 5 --run-id tick_x    # scheduled wrapper
.venv/bin/python ram_map_server.py                        # viewer → :8099
```

Artifacts: `cron_logs/run_<id>.jsonl`, `screenshots/run_<id>/step_NNNN.png`
(both gitignored).
