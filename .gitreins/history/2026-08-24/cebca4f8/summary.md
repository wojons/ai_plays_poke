# Verdict: GAP-034

**Task:** Add heavy/fast test tier markers (or document tiers) so -m 'not heavy' matches the documented fast tier
**Evaluated:** 2026-08-24T16:24:43.499884
**Result:** ✗ FAIL

## Pipeline Stages

- ✗ **tier1**
  -   ✓ lint: 
  ✗ secrets: [90m11:18AM[0m [32mINF[0m [1mscanned ~175636350 bytes (175.64 MB) in 8.69s[0m
[90m11:18AM[0m
  ✓ tests: ============================= test session starts ==============================
platform linux -- P
- ✓ **tier2**
  - COMPLETE
  ✓ pytest tests/ -q -m 'not heavy' (via .venv/bin/python -m pytest) completes in ~70-90s with ~3867 passed / ~8 skipped, matching the documented fast tier result (-m 'not integration and not slow'); any new markers (heavy/fast) are registered in pyproject.toml markers list so --strict-markers stays clean; README fast-tier section documents the heavy/fast tier names: Test run `.venv/bin/python -m pytest tests/ -q -m 'not heavy'` completed in 70.79s with '3878 passed, 8 skipped, 62 deselected' (matches README-documented ~3878 passed/8 skipped, within ~70-90s). Markers 'heavy' and 'fast' registered in pyproject.toml markers list (HEAD:pyproject.toml lines 53-54); --strict-markers in addopts and run completed with 0 failures/no unknown-marker error, so strict-markers is clean. README fast-tier section (HEAD:README.md lines 363-378) documents 'Fast tier' and 'Heavy tier' names with both `-m "not heavy"` and equivalent `-m "not integration and not slow"` commands. Equivalence confirmed: every test file containing integration/slow markers (test_ai_client, test_edge_cases, test_gameplay_demo, test_integration, test_live_demo, test_memory_reader, test_mode_duration, test_performance) also carries heavy markers (21 heavy-mark occurrences across 8 files).
GAP-034 fully satisfied: -m 'not heavy' runs in 70.79s with 3878 passed/8 skipped matching the documented fast tier, heavy/fast markers registered in pyproject.toml keeping --strict-markers clean, and README documents the fast/heavy tier names.

## Summary

Judge Result: GAP-034

Stage tier1: FAIL
    ✓ lint: 
  ✗ secrets: [90m11:18AM[0m [32mINF[0m [1mscanned ~175636350 bytes (175.64 MB) in 8.69s[0m
[90m11:18AM[0m
  ✓ tests: ============================= test session starts ==============================
platform linux -- P

Stage tier2: PASS
  COMPLETE
  ✓ pytest tests/ -q -m 'not heavy' (via .venv/bin/python -m pytest) completes in ~70-90s with ~3867 passed / ~8 skipped, matching the documented fast tier result (-m 'not integration and not slow'); any new markers (heavy/fast) are registered in pyproject.toml markers list so --strict-markers stays clean; README fast-tier section documents the heavy/fast tier names: Test run `.venv/bin/python -m pytest tests/ -q -m 'not heavy'` completed in 70.79s with '3878 passed, 8 skipped, 62 deselected' (matches README-documented ~3878 passed/8 skipped, within ~70-90s). Markers 'heavy' and 'fast' registered in pyproject.toml markers list (HEAD:pyproject.toml lines 53-54); --strict-markers in addopts and run completed with 0 failures/no unknown-marker error, so strict-markers is clean. README fast-tier section (HEAD:README.md lines 363-378) documents 'Fast tier' and 'Heavy tier' names with both `-m "not heavy"` and equivalent `-m "not integration and not slow"` commands. Equivalence confirmed: every test file containing integration/slow markers (test_ai_client, test_edge_cases, test_gameplay_demo, test_integration, test_live_demo, test_memory_reader, test_mode_duration, test_performance) also carries heavy markers (21 heavy-mark occurrences across 8 files).
GAP-034 fully satisfied: -m 'not heavy' runs in 70.79s with 3878 passed/8 skipped matching the documented fast tier, heavy/fast markers registered in pyproject.toml keeping --strict-markers clean, and README documents the fast/heavy tier names.

Overall: FAIL ✗
