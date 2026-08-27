# Verdict: GAP-036

**Task:** P2 — run summary 'Screens' set includes an unexplained '?' value
**Evaluated:** 2026-08-27T08:02:06.178850
**Result:** ✗ FAIL

## Pipeline Stages

- ✗ **tier1**
  -   ✓ lint: 
  ✗ secrets: [90m2:54AM[0m [32mINF[0m [1mscanned ~174971960 bytes (174.97 MB) in 7.85s[0m
[90m2:54AM[0m 
  ✓ tests: ============================= test session starts ==============================
platform linux -- P
- ✓ **tier2**
  - COMPLETE
  ✓ README and/or docs/api/cron_runner.md document '?'/'unknown' as a possible screen value with its meaning (unknown/transition frame), or the summary prints a named value instead of '?'; full test suite passes; guard 5/5: cron_runner.py:2202 now uses r.get("screen","unknown") so the summary prints 'unknown' instead of '?'; README.md:191-195 and docs/api/cron_runner.md:75,128,149 document 'unknown' as a possible screen value (skipped/error frames or RAM reader's unknown bucket). Full suite: `./venv/bin/pytest -x --tb=short` → 3940 passed, 14 skipped in 182.98s. Guard 5/5: gitleaks 'no leaks found' (579 commits), ruff 'All checks passed!', mypy 'Success: no issues found in 63 source files', LSP 0 diagnostics, tests pass.
GAP-036 complete: the run summary now prints 'unknown' instead of '?' for unclassified screens, documented in README and API docs, with full test suite (3940 passed) and guard 5/5 green.

## Summary

Judge Result: GAP-036

Stage tier1: FAIL
    ✓ lint: 
  ✗ secrets: [90m2:54AM[0m [32mINF[0m [1mscanned ~174971960 bytes (174.97 MB) in 7.85s[0m
[90m2:54AM[0m 
  ✓ tests: ============================= test session starts ==============================
platform linux -- P

Stage tier2: PASS
  COMPLETE
  ✓ README and/or docs/api/cron_runner.md document '?'/'unknown' as a possible screen value with its meaning (unknown/transition frame), or the summary prints a named value instead of '?'; full test suite passes; guard 5/5: cron_runner.py:2202 now uses r.get("screen","unknown") so the summary prints 'unknown' instead of '?'; README.md:191-195 and docs/api/cron_runner.md:75,128,149 document 'unknown' as a possible screen value (skipped/error frames or RAM reader's unknown bucket). Full suite: `./venv/bin/pytest -x --tb=short` → 3940 passed, 14 skipped in 182.98s. Guard 5/5: gitleaks 'no leaks found' (579 commits), ruff 'All checks passed!', mypy 'Success: no issues found in 63 source files', LSP 0 diagnostics, tests pass.
GAP-036 complete: the run summary now prints 'unknown' instead of '?' for unclassified screens, documented in README and API docs, with full test suite (3940 passed) and guard 5/5 green.

Overall: FAIL ✗
