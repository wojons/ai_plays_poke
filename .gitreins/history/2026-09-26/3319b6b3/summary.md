# Verdict: FLAKY-1

**Task:** Load-robust timing tests via min-of-N
**Evaluated:** 2026-09-26T16:13:32.674248
**Result:** ✓ PASS

## Pipeline Stages

- ✓ **tier1**
  -   ✓ lint: ok (no output)
  ✓ secrets: secrets: harness state excluded from gitleaks scope (.gitreins/**)
  ✓ tests: ============================= test session starts ==============================
- ✓ **tier2**
  - COMPLETE
  ✓ tests/test_performance.py timing tests use min-of-5 attempts with original budgets kept (init <0.15s, selection <0.05s), per-attempt ceiling 1.0s, perf_counter used, no skip-gates; falsification proof shows tests still fail when they should; ruff check+format clean, mypy clean, targeted tests pass.: tests/test_performance.py:25-37 defines _min_over_attempts(fn, attempts, ceiling_s) using time.perf_counter() (lines 31,33) and asserting each attempt < ceiling_s (line 34). Both target tests call it with attempts=5, ceiling_s=1.0 (lines 118-122, 133-137) and keep original budgets: `assert min(selection_times) < 0.05` (line 124) and `assert min(init_times) < 0.15` (line 139). No skip-gates: grep of lines 109-145 for skip/xfail = 0 and no pytest.mark on TestAIDecisionTime. Falsification: /tmp/aipp247_FLAKY-1_falsification.txt shows test_simple_ai_decision_time FAILED at a 0.0001s budget; supplemental shows both FAIL at 1e-7. Independently reproduced: tightening init budget to 1e-7 -> '1 failed, 1 passed'; tightening ceiling_s to 1e-7 -> '2 failed'; file restored clean (git status empty). ruff check tests/test_performance.py -> 'All checks passed!' exit 0; ruff format --check -> '1 file already formatted' exit 0; mypy tests/test_performance.py --ignore-missing-imports -> 'Success: no issues found in 1 source file' exit 0; .venv/bin/pytest tests/test_performance.py -k TestAIDecisionTime -v -> '2 passed, 12 deselected in 0.43s'. Merged tree matches work commit f01027e (git diff f01027e HEAD -- tests/test_performance.py empty). [resolution 0.39; tests/test_performance.py]
All FLAKY-1 requirements verified: min-of-5 with perf_counter, original 0.15s/0.05s budgets, 1.0s per-attempt ceiling, no skip-gates, falsification reproduced (tests fail when budgets tightened), ruff/mypy clean, targeted tests pass.

## Summary

Judge Result: FLAKY-1

Stage tier1: PASS
    ✓ lint: ok (no output)
  ✓ secrets: secrets: harness state excluded from gitleaks scope (.gitreins/**)
  ✓ tests: ============================= test session starts ==============================

Stage tier2: PASS
  COMPLETE
  ✓ tests/test_performance.py timing tests use min-of-5 attempts with original budgets kept (init <0.15s, selection <0.05s), per-attempt ceiling 1.0s, perf_counter used, no skip-gates; falsification proof shows tests still fail when they should; ruff check+format clean, mypy clean, targeted tests pass.: tests/test_performance.py:25-37 defines _min_over_attempts(fn, attempts, ceiling_s) using time.perf_counter() (lines 31,33) and asserting each attempt < ceiling_s (line 34). Both target tests call it with attempts=5, ceiling_s=1.0 (lines 118-122, 133-137) and keep original budgets: `assert min(selection_times) < 0.05` (line 124) and `assert min(init_times) < 0.15` (line 139). No skip-gates: grep of lines 109-145 for skip/xfail = 0 and no pytest.mark on TestAIDecisionTime. Falsification: /tmp/aipp247_FLAKY-1_falsification.txt shows test_simple_ai_decision_time FAILED at a 0.0001s budget; supplemental shows both FAIL at 1e-7. Independently reproduced: tightening init budget to 1e-7 -> '1 failed, 1 passed'; tightening ceiling_s to 1e-7 -> '2 failed'; file restored clean (git status empty). ruff check tests/test_performance.py -> 'All checks passed!' exit 0; ruff format --check -> '1 file already formatted' exit 0; mypy tests/test_performance.py --ignore-missing-imports -> 'Success: no issues found in 1 source file' exit 0; .venv/bin/pytest tests/test_performance.py -k TestAIDecisionTime -v -> '2 passed, 12 deselected in 0.43s'. Merged tree matches work commit f01027e (git diff f01027e HEAD -- tests/test_performance.py empty). [resolution 0.39; tests/test_performance.py]
All FLAKY-1 requirements verified: min-of-5 with perf_counter, original 0.15s/0.05s budgets, 1.0s per-attempt ceiling, no skip-gates, falsification reproduced (tests fail when budgets tightened), ruff/mypy clean, targeted tests pass.

Overall: PASS ✓
