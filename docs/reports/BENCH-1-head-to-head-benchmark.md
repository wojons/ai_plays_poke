# BENCH-1 — the LLM-core benchmark (llm vs jev, one command)

Recorded: 2026-09-28 · Branch `wt/BENCH-1` · Driver:
`scripts/benchmark_llm_vs_jev.py`

## What this is

The head-to-head behind CTRL-WIN as ONE reproducible command: both decision
arms run from the same boot state and the same cycle budget, and the
comparison table is regenerated from the arm run logs alone — no manually
entered figures.

    .venv/bin/python scripts/benchmark_llm_vs_jev.py run
    .venv/bin/python scripts/benchmark_llm_vs_jev.py report \
        cron_logs/bench1_<stamp>_episodes.jsonl

`run` executes the battery and appends one JSON row per episode to
`cron_logs/bench1_<stamp>_episodes.jsonl`; `report` aggregates that log into
`data/baselines/bench1_headtohead_<date>.json` (override with
`BENCH1_OUTPUT_PATH`).

## Fixed conditions (identical by construction)

- Decision modes: `--decision-mode llm` and `--decision-mode jev`, one episode
  each, interleaved episode-by-episode (`llm ep1, jev ep1, llm ep2, ...`) so a
  code or host change mid-battery hits both arms instead of confounding one.
- Boot state: `data/boot.state` (the S0/CTRL-WIN conditions; `--boot-state` /
  `BENCH1_BOOT_STATE` overrides, sha256 stamped per episode).
- Episode length: `--cycles` (default 5, env `BENCH1_CYCLES`) — identical for
  both arms.
- Episodes per arm: 5 (`--episodes`, env `BENCH1_EPISODES`).
- Distinct run ids: `bench1_<mode>_ep<N>_<date>` (resume-safe; an episode
  whose `run_autonomy` row landed is skipped).
- Isolation: the ROM's SRAM twin is restored from a snapshot before every
  episode (same discipline as BASE-1 / DIST-1).

## The fail-closed purity guard (the load-bearing rule)

A benchmark-labelled run **fails closed** when the pure-LLM arm is not pure:

- `JEV_ANSWERED_IN_PURE_LLM_ARM` — any decision row in the `llm` arm carries
  `jev_answered=True`. The battery aborts (rc 3) at the first rejected
  episode and `report` refuses to write an artifact. A contaminated arm is
  not a measurement.
- `MODE_MISMATCH_IN_ARM` — an episode's own `run_autonomy` row stamps a
  decision_mode other than the arm that was requested.

The guard is re-run over every row when `report` reads the log back, so an
artifact can never be produced from a rejected battery even after the fact.
The jev arm is unaffected by design: `jev_answered=True` is the expected
state there — the guard keys on WHERE the field is true, not on the field.

The same change closed the two remaining places a pure-LLM run could consult
the fast tier at all: battle recovery and starter selection now check
`_llm_mode_fast_tier_blocked()` (same predicate `_jev_or_none` uses for the
overworld path) and stamp `jev_ok=None` + `jev_blocked_reason` instead of
asking. Tests: `tests/test_benchmark_llm_vs_jev.py`.

## Comparison table (regenerated from logs alone)

One row per arm (`comparison.table` in the artifact), every figure derived
from `cron_logs/run_<id>.jsonl` plus the per-run stdout log:

| metric | log source |
| --- | --- |
| mode | the arm the driver ran (cross-checked against `run_autonomy.decision_mode`) |
| decisions / real / fallback | decision rows (rows carrying `intent`, cron_runner's own population; fallback = `FALLBACK_INTENTS` intents) |
| cost_usd | every numeric `cost_usd` in the log (same rule as DIST-1: honest lower bound of LLM spend) |
| tiles visited | distinct `player_tile_x/player_tile_y` pairs over decision rows |
| maps reached / transitions / first transition cycle | consecutive decision-row `map_name` changes |
| lock-rate | the runner's own `lock-rate: W/T` stdout summary line |
| teacher calls / model | `teacher_escalation` events (floor: `run_autonomy.teacher_escalations.count`) |
| errors | `recovery_exhausted` events + rows carrying an `error` field |

A measurement the logs cannot support is `null` with an explicit reason in
the artifact (censored first-transition cycles, a missing stdout lock-rate) —
never 0, never hand-entered. `summary.decision_row_parity_mismatches` lists
any episode where the counted decision rows disagree with the log's own
`decisions_total` self-report, and `comparison.comparability_notes` records
mixed boot hashes, mismatched cycle budgets, incomplete arms and zero-decision
arms instead of averaging over them.

## Why the new decision-row population

`scripts/run_base1_baseline.py` counts decisions only from rows with a
non-null `missing_class` — an escalation-shaped population. On a pure-LLM log
that reads `decisions: 0` beside `autonomy.decisions_total: 12`, which is
exactly what the committed ctrlwin artifact shows
(`data/baselines/ctrlwin_llm_2026-09-27.json`). BENCH-1 counts cron_runner's
own decision population (rows carrying `intent`, the population
`_autonomy_counters` uses), so both arms are comparable to their logs'
self-reports. Reproduce the hole: `.venv/bin/python scripts/bench1_red_evidence.py`.
