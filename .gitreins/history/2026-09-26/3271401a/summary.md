# Verdict: DOC-5

**Task:** docs/api/cron_runner.md: document decision-row fields
**Evaluated:** 2026-09-26T19:15:10.550366
**Result:** ✗ FAIL

## Pipeline Stages

- ✗ **tier1**
  -   ✓ lint: ok (no output)
  ✗ secrets: Command timed out
  ✓ tests: ============================= test session starts ==============================
- ✓ **tier2**
  - COMPLETE
  ✓ decision-row fields jev_answered/escalated/missing_class/raw_distribution + run_autonomy summary row documented with real examples from cron_runner.py:963/1317/2128; guard green: docs/api/cron_runner.md:224-227 documents all four fields (jev_answered/escalated/missing_class/raw_distribution) with types+semantics; :233 gives a real example JSON whose keys match cron_runner.py:4286-4325 plan_entry construction exactly (verified against live log cron_logs/run_dgf_0924_pm.jsonl). :250-269 documents the run_autonomy closeout row; its field table matches _autonomy_counters (cron_runner.py:2155-2240) and _write_autonomy_row (2280-2320) exactly, and matches a real log row (cron_logs/*.jsonl run_autonomy). Cited code paths verified: cron_runner.py:963 = starter decision block writing raw_distribution/jev_answered/escalated/missing_class (doc :238 describes it accurately); :1317+ = _jev_overworld_decision docstring naming the four proof fields (doc :205); :2128+ = _autonomy_counters region (doc :240/:252). Guard green: .gitreins/logs/guard-20260926T163704.197186Z.log line 7 'guards: 5 (0 failed, 1 skipped)', [PASS] secrets, [PASS] tests (full) exit_code=0 '4188 passed, 14 skipped in 215.34s', [PASS] static_analysis (mypy clean), [PASS] lsp (pylsp clean), [SKIP] lint (no staged files, benign). Targeted re-run: ./.venv/bin/pytest tests/test_cron_runner_metrics.py tests/test_gap053_decision_intent_summary.py tests/test_jev403_degradation.py tests/test_gap052_controller_model.py -q => 123 passed in 0.85s. Minor non-disqualifying note: doc cites the docstring as 'lines 1317-1318' while it actually starts at 1326, and does not literally print '963'/'2128', but the code at those locations is accurately documented. [resolution 0.49; cron_runner.py:963]
All four decision-row fields and the run_autonomy summary row are documented in docs/api/cron_runner.md with real, code-accurate examples grounded in cron_runner.py:963/1317/2128, and the guard is green (5 guards, 0 failed; 4188 tests passed).

## Summary

Judge Result: DOC-5

Stage tier1: FAIL
    ✓ lint: ok (no output)
  ✗ secrets: Command timed out
  ✓ tests: ============================= test session starts ==============================

Stage tier2: PASS
  COMPLETE
  ✓ decision-row fields jev_answered/escalated/missing_class/raw_distribution + run_autonomy summary row documented with real examples from cron_runner.py:963/1317/2128; guard green: docs/api/cron_runner.md:224-227 documents all four fields (jev_answered/escalated/missing_class/raw_distribution) with types+semantics; :233 gives a real example JSON whose keys match cron_runner.py:4286-4325 plan_entry construction exactly (verified against live log cron_logs/run_dgf_0924_pm.jsonl). :250-269 documents the run_autonomy closeout row; its field table matches _autonomy_counters (cron_runner.py:2155-2240) and _write_autonomy_row (2280-2320) exactly, and matches a real log row (cron_logs/*.jsonl run_autonomy). Cited code paths verified: cron_runner.py:963 = starter decision block writing raw_distribution/jev_answered/escalated/missing_class (doc :238 describes it accurately); :1317+ = _jev_overworld_decision docstring naming the four proof fields (doc :205); :2128+ = _autonomy_counters region (doc :240/:252). Guard green: .gitreins/logs/guard-20260926T163704.197186Z.log line 7 'guards: 5 (0 failed, 1 skipped)', [PASS] secrets, [PASS] tests (full) exit_code=0 '4188 passed, 14 skipped in 215.34s', [PASS] static_analysis (mypy clean), [PASS] lsp (pylsp clean), [SKIP] lint (no staged files, benign). Targeted re-run: ./.venv/bin/pytest tests/test_cron_runner_metrics.py tests/test_gap053_decision_intent_summary.py tests/test_jev403_degradation.py tests/test_gap052_controller_model.py -q => 123 passed in 0.85s. Minor non-disqualifying note: doc cites the docstring as 'lines 1317-1318' while it actually starts at 1326, and does not literally print '963'/'2128', but the code at those locations is accurately documented. [resolution 0.49; cron_runner.py:963]
All four decision-row fields and the run_autonomy summary row are documented in docs/api/cron_runner.md with real, code-accurate examples grounded in cron_runner.py:963/1317/2128, and the guard is green (5 guards, 0 failed; 4188 tests passed).

Overall: FAIL ✗
