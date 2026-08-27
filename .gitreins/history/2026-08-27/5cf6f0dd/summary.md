# Verdict: GAP-040

**Task:** Fix stale suite-duration claims in docs
**Evaluated:** 2026-08-27T14:08:53.635407
**Result:** ✗ FAIL

## Pipeline Stages

- ✗ **tier1**
  -   ✓ lint: 
  ✗ secrets: [90m9:00AM[0m [32mINF[0m [1mscanned ~174864879 bytes (174.86 MB) in 7.67s[0m
[90m9:00AM[0m 
  ✓ tests: ============================= test session starts ==============================
platform linux -- P
- ✓ **tier2**
  - COMPLETE
  ✓ README and AGENTS.md clarify that '14s' is parallel-only (-n auto), or document the serial time (~210s). PASS: re-run pytest tests/ -q shows duration matches the documented claim, or AGENTS.md documents -n auto as default and qualifies 14s as parallel-only.: README.md (commit 9fb2a7d, lines 340-345) now states 'the ~14s figure is parallel-only, measured with pytest-xdist: 3940 passed / 14 skipped' and documents serial time 'same suite takes ~210s / ~3.5 min'. Serial re-run `pytest tests/ -q` completed: '3940 passed, 14 skipped in 177.85s (0:02:57)' — matches the documented ~210s serial claim and the 3940/14 count. PASS branch 1 satisfied.
README.md now qualifies the 14s figure as parallel-only (-n auto) and documents the serial time (~210s); a fresh serial `pytest tests/ -q` run confirmed 3940 passed/14 skipped in 177.85s, matching the documented claim.

## Summary

Judge Result: GAP-040

Stage tier1: FAIL
    ✓ lint: 
  ✗ secrets: [90m9:00AM[0m [32mINF[0m [1mscanned ~174864879 bytes (174.86 MB) in 7.67s[0m
[90m9:00AM[0m 
  ✓ tests: ============================= test session starts ==============================
platform linux -- P

Stage tier2: PASS
  COMPLETE
  ✓ README and AGENTS.md clarify that '14s' is parallel-only (-n auto), or document the serial time (~210s). PASS: re-run pytest tests/ -q shows duration matches the documented claim, or AGENTS.md documents -n auto as default and qualifies 14s as parallel-only.: README.md (commit 9fb2a7d, lines 340-345) now states 'the ~14s figure is parallel-only, measured with pytest-xdist: 3940 passed / 14 skipped' and documents serial time 'same suite takes ~210s / ~3.5 min'. Serial re-run `pytest tests/ -q` completed: '3940 passed, 14 skipped in 177.85s (0:02:57)' — matches the documented ~210s serial claim and the 3940/14 count. PASS branch 1 satisfied.
README.md now qualifies the 14s figure as parallel-only (-n auto) and documents the serial time (~210s); a fresh serial `pytest tests/ -q` run confirmed 3940 passed/14 skipped in 177.85s, matching the documented claim.

Overall: FAIL ✗
