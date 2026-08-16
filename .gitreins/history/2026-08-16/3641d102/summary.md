# Verdict: GAP-026

**Task:** README 'How to Test' overpromises: add fast test subset + mark heavy integration classes
**Evaluated:** 2026-08-16T18:56:04.705737
**Result:** ✗ FAIL

## Pipeline Stages

- ✗ **tier1**
  -   ✓ lint: 
  ✗ secrets: [90m1:47PM[0m [32mINF[0m [1mscanned ~173439771 bytes (173.44 MB) in 9.12s[0m
[90m1:47PM[0m 
  ✓ tests: ============================= test session starts ==============================
platform linux -- P
- ✓ **tier2**
  - COMPLETE
  ✓ README documents a fast test command (e.g. -k 'not integration and not gameplay' or a fast marker) that completes in under 90s on a fresh checkout: README.md (commit 0f35360) documents `.venv/bin/python -m pytest tests/ -q -m "not integration and not slow"` claiming 'Completes in ~70–85s on a fresh checkout (3825 passed / 8 skipped, 62 deselected)'. Actual run: 3825 passed, 8 skipped, 62 deselected in 66.91s (<90s) — /tmp/fast_test.log.
  ✓ Heavy classes in tests/test_integration.py are marked @pytest.mark.integration so -m 'not integration' excludes them: Commit 0f35360 added @pytest.mark.integration to TestFullTickCycle, TestBattleTransition, TestDialogFlow, TestCommandExecution, TestErrorRecovery in tests/test_integration.py. Verified: `-m "integration"` collects 29 tests; `-m "not integration"` deselects all 29 (0 selected).
  ✓ README states realistic runtime for the full suite: README.md states '~3 min: 3881 passed / 14 skipped on a fresh checkout'. Actual full suite run: 3881 passed, 14 skipped in 170.04s (2:50) — /tmp/full_test.log, exactly matching the README claim.
All three GAP-026 criteria verified: README documents a fast subset command that ran in 66.91s (<90s), integration classes are marked @pytest.mark.integration (29 tests deselected by -m 'not integration'), and the full-suite runtime claim (~3 min, 3881 passed/14 skipped) matches the actual 170.04s run.

## Summary

Judge Result: GAP-026

Stage tier1: FAIL
    ✓ lint: 
  ✗ secrets: [90m1:47PM[0m [32mINF[0m [1mscanned ~173439771 bytes (173.44 MB) in 9.12s[0m
[90m1:47PM[0m 
  ✓ tests: ============================= test session starts ==============================
platform linux -- P

Stage tier2: PASS
  COMPLETE
  ✓ README documents a fast test command (e.g. -k 'not integration and not gameplay' or a fast marker) that completes in under 90s on a fresh checkout: README.md (commit 0f35360) documents `.venv/bin/python -m pytest tests/ -q -m "not integration and not slow"` claiming 'Completes in ~70–85s on a fresh checkout (3825 passed / 8 skipped, 62 deselected)'. Actual run: 3825 passed, 8 skipped, 62 deselected in 66.91s (<90s) — /tmp/fast_test.log.
  ✓ Heavy classes in tests/test_integration.py are marked @pytest.mark.integration so -m 'not integration' excludes them: Commit 0f35360 added @pytest.mark.integration to TestFullTickCycle, TestBattleTransition, TestDialogFlow, TestCommandExecution, TestErrorRecovery in tests/test_integration.py. Verified: `-m "integration"` collects 29 tests; `-m "not integration"` deselects all 29 (0 selected).
  ✓ README states realistic runtime for the full suite: README.md states '~3 min: 3881 passed / 14 skipped on a fresh checkout'. Actual full suite run: 3881 passed, 14 skipped in 170.04s (2:50) — /tmp/full_test.log, exactly matching the README claim.
All three GAP-026 criteria verified: README documents a fast subset command that ran in 66.91s (<90s), integration classes are marked @pytest.mark.integration (29 tests deselected by -m 'not integration'), and the full-suite runtime claim (~3 min, 3881 passed/14 skipped) matches the actual 170.04s run.

Overall: FAIL ✗
