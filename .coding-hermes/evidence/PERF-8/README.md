# PERF-8 — post-JEV-404 timing gate (repo-visible projection)

PERF-8's gate is "re-run the exact warm command after the JEV-404 escalation fix and record
real/user/sys, the `teacher_escalation` count and the `patch.latency_s` sum". The run log is
`cron_logs/run_perf8.jsonl`, which this repo gitignores, so the measurement is projected here.

| measurement | pre-fix (PERF-8 row, `run_df1120a`) | post-fix (`run_perf8`) |
|---|---|---|
| cycles | 80 | 80 |
| wall | 611.90 s | **56.09 s** |
| mean wall / cycle | 7.65 s | **0.701 s** |
| best baseline (2026-10-27) | 0.62 s/cycle | 0.62 s/cycle |
| ratio to baseline | 12.4x | **1.14x** |
| `teacher_escalation` rows | 78 | **4** |
| `patch.latency_s` sum | 556.97 s (91% of wall) | **24.366 s (43.4% of wall)** |
| local CPU (user+sys) | 6.74 s (1.1%) | 3.61 s (6.4%) |

Acceptance (mean wall per cycle under 1.3 s) is met at 0.701 s/cycle.

## Reproduce

```bash
/usr/bin/time -f 'REAL=%e USER=%U SYS=%S' \
  ./venv/bin/python cron_runner.py --run-id perf8 --cycles 80 --decision-mode jev
```

## Verify from the tracked tree

```bash
jq -r '.claim_confirmed' .coding-hermes/evidence/PERF-8/run-perf8-summary.json
jq -r '.mean_wall_per_cycle_s, .teacher_escalation_rows, .patch_latency_s_sum' \
  .coding-hermes/evidence/PERF-8/run-perf8-summary.json
jq -r 'select(.escalated) | .cycle' .coding-hermes/evidence/PERF-8/run_perf8-cycles.jsonl | wc -l
```

## Residual risk (stated, not hidden)

Absolute wall clock moves with fleet load on this shared host, and the "best baseline" is a single
2026-10-27 sample. The robust signals are the escalation count (78 -> 4) and the drop in teacher
share (91% -> 43%): the remaining 24.4 s is four live teacher round-trips, i.e. intrinsic network
cost that PERF-8's criteria explicitly allow when stated numerically.
