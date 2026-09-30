# Verdict: DF-USE-1

**Task:** Add movement progress observable to run summary
**Evaluated:** 2026-09-29T17:11:25.008034
**Result:** ✗ FAIL

## Pipeline Stages

- ✗ **tier1**
  -   ✓ lint: ok (no output)
  ✗ secrets: Command timed out
  ✓ tests: ============================= test session starts ==============================
- ✓ **tier2**
  - COMPLETE
  ✓ Final run summary reports movement progress beyond total distinct tiles, with regression coverage proving treadmill behavior is visible: cron_runner.py:2570-2572 appends ' | movement-progress: {movement_progress_cycles}/{movement_observed_cycles} comparable cycles changed tile ({movement_rate:.0%})' to _format_summary, alongside the pre-existing '| distinct tiles: {distinct_tiles}' at cron_runner.py:2565 — a new observable beyond distinct tiles. The metric is derived from consecutive RAM tile observations via _movement_progress_delta (cron_runner.py:832-843: returns (0,0) if either tile is None, else (int(current_tile != last_tile), 1)), explicitly never from decisions/actions. Wired end-to-end: counters initialized at cron_runner.py:4336-4337, accumulated per cycle at cron_runner.py:4479-4483, passed to _format_summary at cron_runner.py:5629-5630, and persisted via _record_run_memory extra at cron_runner.py:5645-5646 (attributes movement_progress_cycles / movement_observed_cycles / movement_progress_rate written at cron_runner.py:2665-2677). Regression coverage proving treadmill behavior is visible: tests/test_cron_runner_metrics.py:80-95 test_treadmill_actions_do_not_count_as_movement_progress (5 real decisions, 0 tile changes -> asserts 'movement-progress: 0/4 comparable cycles changed tile (0%)'); TestMovementProgressDelta tests/test_cron_runner_metrics.py:111-137 prove only consecutive valid tile observations create a comparable cycle and only a changed tuple counts; tests/test_gap053_decision_intent_summary.py:228-230 assert the persisted attributes. TEST EVIDENCE: ./.venv/bin/pytest tests/test_cron_runner_metrics.py tests/test_autonomy_counters.py tests/test_gap053_decision_intent_summary.py tests/test_teacher_escalation.py -q --tb=short => '95 passed in 0.89s' (exit 0); focused -k 'Movement or movement or treadmill or summary' => '10 passed, 50 deselected in 0.83s' (exit 0); full suite ./.venv/bin/pytest tests/ -q --tb=line => '4313 passed, 14 skipped in 231.66s' (exit 0).
The final run summary now reports a movement-progress observable derived from consecutive RAM tile changes (not decisions) alongside distinct tiles, with passing regression tests proving treadmill behavior (actions without tile change) is visible.

## Summary

Judge Result: DF-USE-1

Stage tier1: FAIL
    ✓ lint: ok (no output)
  ✗ secrets: Command timed out
  ✓ tests: ============================= test session starts ==============================

Stage tier2: PASS
  COMPLETE
  ✓ Final run summary reports movement progress beyond total distinct tiles, with regression coverage proving treadmill behavior is visible: cron_runner.py:2570-2572 appends ' | movement-progress: {movement_progress_cycles}/{movement_observed_cycles} comparable cycles changed tile ({movement_rate:.0%})' to _format_summary, alongside the pre-existing '| distinct tiles: {distinct_tiles}' at cron_runner.py:2565 — a new observable beyond distinct tiles. The metric is derived from consecutive RAM tile observations via _movement_progress_delta (cron_runner.py:832-843: returns (0,0) if either tile is None, else (int(current_tile != last_tile), 1)), explicitly never from decisions/actions. Wired end-to-end: counters initialized at cron_runner.py:4336-4337, accumulated per cycle at cron_runner.py:4479-4483, passed to _format_summary at cron_runner.py:5629-5630, and persisted via _record_run_memory extra at cron_runner.py:5645-5646 (attributes movement_progress_cycles / movement_observed_cycles / movement_progress_rate written at cron_runner.py:2665-2677). Regression coverage proving treadmill behavior is visible: tests/test_cron_runner_metrics.py:80-95 test_treadmill_actions_do_not_count_as_movement_progress (5 real decisions, 0 tile changes -> asserts 'movement-progress: 0/4 comparable cycles changed tile (0%)'); TestMovementProgressDelta tests/test_cron_runner_metrics.py:111-137 prove only consecutive valid tile observations create a comparable cycle and only a changed tuple counts; tests/test_gap053_decision_intent_summary.py:228-230 assert the persisted attributes. TEST EVIDENCE: ./.venv/bin/pytest tests/test_cron_runner_metrics.py tests/test_autonomy_counters.py tests/test_gap053_decision_intent_summary.py tests/test_teacher_escalation.py -q --tb=short => '95 passed in 0.89s' (exit 0); focused -k 'Movement or movement or treadmill or summary' => '10 passed, 50 deselected in 0.83s' (exit 0); full suite ./.venv/bin/pytest tests/ -q --tb=line => '4313 passed, 14 skipped in 231.66s' (exit 0).
The final run summary now reports a movement-progress observable derived from consecutive RAM tile changes (not decisions) alongside distinct tiles, with passing regression tests proving treadmill behavior (actions without tile change) is visible.

Overall: FAIL ✗
