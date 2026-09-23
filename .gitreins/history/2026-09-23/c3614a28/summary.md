# Verdict: GAP-057

**Task:** CI guard against root-level _*.py scratch re-accumulation
**Evaluated:** 2026-09-23T12:58:56.382620
**Result:** ✗ FAIL

## Pipeline Stages

- ✗ **tier1**
  -   ✓ lint: ok (no output)
  ✗ secrets: Command timed out
  ✓ tests: ============================= test session starts ==============================
- ✓ **tier2**
  - COMPLETE
  ✓ A new step/job in .github/workflows/ci.yml fails when a root-level _*.py file appears that is NOT in the baselined allowlist; baseline derived from current 29 files; existing files do not fail.: .github/workflows/ci.yml (commit 85d669d) adds step 'Repo hygiene (no unbaselined root scratch files)' that greps each root _*.py against tools/scratch-baseline.txt and exits 1 on any miss. Baseline has exactly 29 entries; `diff <(ls _*.py|sort) <(sort tools/scratch-baseline.txt)` = IDENTICAL. Running the guard on the baseline state: exit_code=0, output 'OK: no unbaselined root-level _*.py files.' YAML parses valid; step order confirmed.
  ✓ Adding a new scratch file _foo.py at root makes the CI job fail; removing it makes CI green; baseline files do not trip it.: Empirical run of the exact CI step logic: `touch _foo.py` -> exit_code=1 with '::error file=_foo.py::unbaselined root scratch file: _foo.py' + 'Root-level _*.py scratch files must not accumulate.'; `rm _foo.py` -> exit_code=0 'OK: no unbaselined root-level _*.py files.'; force-added tracked _bar.py -> exit_code=1 (tracked-file path also covered). Baseline 29 files produce exit 0, so they do not trip it.
The CI hygiene step and 29-file baseline are committed and empirically verified: baseline passes (exit 0), a new root _foo.py fails (exit 1), and removal restores green.

## Summary

Judge Result: GAP-057

Stage tier1: FAIL
    ✓ lint: ok (no output)
  ✗ secrets: Command timed out
  ✓ tests: ============================= test session starts ==============================

Stage tier2: PASS
  COMPLETE
  ✓ A new step/job in .github/workflows/ci.yml fails when a root-level _*.py file appears that is NOT in the baselined allowlist; baseline derived from current 29 files; existing files do not fail.: .github/workflows/ci.yml (commit 85d669d) adds step 'Repo hygiene (no unbaselined root scratch files)' that greps each root _*.py against tools/scratch-baseline.txt and exits 1 on any miss. Baseline has exactly 29 entries; `diff <(ls _*.py|sort) <(sort tools/scratch-baseline.txt)` = IDENTICAL. Running the guard on the baseline state: exit_code=0, output 'OK: no unbaselined root-level _*.py files.' YAML parses valid; step order confirmed.
  ✓ Adding a new scratch file _foo.py at root makes the CI job fail; removing it makes CI green; baseline files do not trip it.: Empirical run of the exact CI step logic: `touch _foo.py` -> exit_code=1 with '::error file=_foo.py::unbaselined root scratch file: _foo.py' + 'Root-level _*.py scratch files must not accumulate.'; `rm _foo.py` -> exit_code=0 'OK: no unbaselined root-level _*.py files.'; force-added tracked _bar.py -> exit_code=1 (tracked-file path also covered). Baseline 29 files produce exit 0, so they do not trip it.
The CI hygiene step and 29-file baseline are committed and empirically verified: baseline passes (exit 0), a new root _foo.py fails (exit 1), and removal restores green.

Overall: FAIL ✗
