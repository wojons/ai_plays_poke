# Verdict: QA-AI-PLAYS-POKE-16

**Task:** Marker-based live-test exclusion so unit tests gate CI
**Evaluated:** 2026-10-03T17:16:23.600122
**Result:** ✗ FAIL

## Pipeline Stages

- ✗ **tier1**
  -   ✓ lint: scanners: nice=nice -n 10
  ✓ secrets: secrets: harness state excluded from gitleaks scope (.gitreins/**)
  ~ tests: Command timed out after 1800s (step budget)
- ✓ **tier2**
  - COMPLETE
  ✓ pytest tests/test_context_window.py passes at HEAD; CI Test step uses -m 'not live' with registered marker; ruff and mypy src/ clean: Ran ./.venv/bin/pytest tests/test_context_window.py -q: '5 passed in 0.04s', exit 0. CI Test step at .github/workflows/ci.yml:84 uses `-m "not live"`; marker registered in pyproject.toml:69 under [tool.pytest.ini_options] markers ('live: marks tests that require a real API or ROM connection'). Ruff: `ruff check src/` -> 'All checks passed!' exit 0. Mypy: `mypy src/ --ignore-missing-imports` -> 'Success: no issues found in 68 source files' exit 0. All artifacts confirmed present at HEAD (commit 4654912) via git show. [resolution 0.34; tests/test_context_window.py]
All three sub-requirements verified with fresh command output: context-window tests pass, CI uses the registered 'not live' marker, and ruff/mypy are clean.

## Summary

Judge Result: QA-AI-PLAYS-POKE-16

Stage tier1: FAIL
  WARNING: coverage is secrets+lint+tests — tests did not run (skipped at runtime — tests: timed out after 1800s (step budget)); run `gitreins guard` for the full gate
    ✓ lint: scanners: nice=nice -n 10
  ✓ secrets: secrets: harness state excluded from gitleaks scope (.gitreins/**)
  ~ tests: Command timed out after 1800s (step budget)

Stage tier2: PASS
  COMPLETE
  ✓ pytest tests/test_context_window.py passes at HEAD; CI Test step uses -m 'not live' with registered marker; ruff and mypy src/ clean: Ran ./.venv/bin/pytest tests/test_context_window.py -q: '5 passed in 0.04s', exit 0. CI Test step at .github/workflows/ci.yml:84 uses `-m "not live"`; marker registered in pyproject.toml:69 under [tool.pytest.ini_options] markers ('live: marks tests that require a real API or ROM connection'). Ruff: `ruff check src/` -> 'All checks passed!' exit 0. Mypy: `mypy src/ --ignore-missing-imports` -> 'Success: no issues found in 68 source files' exit 0. All artifacts confirmed present at HEAD (commit 4654912) via git show. [resolution 0.34; tests/test_context_window.py]
All three sub-requirements verified with fresh command output: context-window tests pass, CI uses the registered 'not live' marker, and ruff/mypy are clean.

Overall: FAIL ✗
