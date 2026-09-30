# Verdict: DF-USE-1

**Task:** Add movement progress observable to run summary
**Evaluated:** 2026-09-29T16:50:02.045151
**Result:** ✗ FAIL

## Pipeline Stages

- ✗ **tier1**
  -   ✓ lint: ok (no output)
  ✗ secrets: Command timed out
  ✓ tests: ============================= test session starts ==============================
- ✓ **tier2**
  - COMPLETE
  ✓ Final run summary reports movement progress beyond total distinct tiles, with regression coverage proving treadmill behavior is visible: cron_runner.py:2570-2572 appends '| movement-progress: {progress}/{observed} comparable cycles changed tile ({rate}%)' to the final summary alongside the pre-existing 'distinct tiles: N'; _record_run_memory (cron_runner.py:2665-2677) persists movement_progress_cycles/movement_observed_cycles/movement_progress_rate attributes. The metric is derived from consecutive RAM tile observations via _movement_progress_delta (cron_runner.py:832-843), explicitly not from decisions/actions, so it is a new observable beyond distinct tiles. Regression coverage: tests/test_cron_runner_metrics.py:80-95 test_treadmill_actions_do_not_count_as_movement_progress (5 real decisions, 0 tile changes -> 'movement-progress: 0/4 comparable cycles changed tile (0%)') proves the treadmill signature is visible; TestMovementProgressDelta (lines 111-137) proves only consecutive valid tile observations create a comparable cycle and only a changed tuple counts; test_gap053_decision_intent_summary.py:228-230 proves the attributes are persisted. TEST EVIDENCE: ./.venv/bin/pytest tests/test_cron_runner_metrics.py tests/test_autonomy_counters.py tests/test_gap053_decision_intent_summary.py tests/test_teacher_escalation.py -q => '95 passed in 0.88s' (exit 0); broader ./.venv/bin/pytest tests/ -q -k 'summary or metrics or autonomy or movement' => '136 passed, 1 skipped' (exit 0). LSP diagnostics: 0 findings.
The run summary now reports a movement-progress observable derived from consecutive RAM tile changes (not decisions) alongside distinct tiles, with passing regression tests proving treadmill behavior (actions without tile change) is visible.

## Summary

Judge Result: DF-USE-1

Stage tier1: FAIL
    ✓ lint: ok (no output)
  ✗ secrets: Command timed out
  ✓ tests: ============================= test session starts ==============================

Stage tier2: PASS
  COMPLETE
  ✓ Final run summary reports movement progress beyond total distinct tiles, with regression coverage proving treadmill behavior is visible: cron_runner.py:2570-2572 appends '| movement-progress: {progress}/{observed} comparable cycles changed tile ({rate}%)' to the final summary alongside the pre-existing 'distinct tiles: N'; _record_run_memory (cron_runner.py:2665-2677) persists movement_progress_cycles/movement_observed_cycles/movement_progress_rate attributes. The metric is derived from consecutive RAM tile observations via _movement_progress_delta (cron_runner.py:832-843), explicitly not from decisions/actions, so it is a new observable beyond distinct tiles. Regression coverage: tests/test_cron_runner_metrics.py:80-95 test_treadmill_actions_do_not_count_as_movement_progress (5 real decisions, 0 tile changes -> 'movement-progress: 0/4 comparable cycles changed tile (0%)') proves the treadmill signature is visible; TestMovementProgressDelta (lines 111-137) proves only consecutive valid tile observations create a comparable cycle and only a changed tuple counts; test_gap053_decision_intent_summary.py:228-230 proves the attributes are persisted. TEST EVIDENCE: ./.venv/bin/pytest tests/test_cron_runner_metrics.py tests/test_autonomy_counters.py tests/test_gap053_decision_intent_summary.py tests/test_teacher_escalation.py -q => '95 passed in 0.88s' (exit 0); broader ./.venv/bin/pytest tests/ -q -k 'summary or metrics or autonomy or movement' => '136 passed, 1 skipped' (exit 0). LSP diagnostics: 0 findings.
The run summary now reports a movement-progress observable derived from consecutive RAM tile changes (not decisions) alongside distinct tiles, with passing regression tests proving treadmill behavior (actions without tile change) is visible.

Overall: FAIL ✗
