# Verdict: QA-AI-PLAYS-POKE-7

**Task:** Fresh-tree pytest collection poisoning fix
**Evaluated:** 2026-09-24T21:47:14.660970
**Result:** ✓ PASS

## Pipeline Stages

- ✓ **tier1**
  -   ✓ lint: ok (no output)
  ✓ secrets: secrets: harness state excluded from gitleaks scope (.gitreins/**)
  ✓ tests: ============================= test session starts ==============================
- ✓ **tier2**
  - COMPLETE
  ✓ From a clean clone with no ROM present, pytest tests/ --co -q exits 0 — both integration modules guarded or excluded by committed repo content — and CI's pytest leg flags (ci.yml:81) still pass: Verified empirically in a fresh clone (`git clone /home/kara/ai_plays_poke /tmp/cleanclone`, HEAD 95fddf8 = merge of 32a1d6b) where `ls data/rom/` contains only README.md and `find . -name '*.gb' -o -name '*.gbc' -o -name '*.gba'` returns nothing. (1) `pytest tests/ --co -q` with OPENROUTER_API_KEY/OPENAI_API_KEY/PTP_LIVE unset → EXIT_CODE=0, '4068 tests collected in 1.26s', zero collection errors; grep for 'test_phase4_integration|test_vision_integration' in the collection output = 0 matches, i.e. both modules are excluded. (2) The exclusion is committed repo content: commit 32a1d6b adds `collect_ignore = ["test_phase4_integration.py", "test_vision_integration.py"]` at tests/conftest.py:25-30, and both files are git-tracked (git ls-files confirms) with module-level side effects (test_phase4_integration.py:16 constructs `Emulator("data/rom/Pokemon - Blue Version (USA, Europe) (SGB Enhanced).gb")` at import time and calls sys.exit(1) at line 73; test_vision_integration.py:21 calls sys.exit(1) when the API key is absent). (3) CI's pytest leg flags at ci.yml:81 still pass — ran the exact flag set (`pytest tests/ -q --tb=line -k "not live" --ignore=tests/test_live_demo.py --ignore=tests/test_phase4_integration.py --ignore=tests/test_vision_integration.py --deselect=tests/test_edge_cases.py::TestROMHandling::test_rom_path_with_spaces`) → '4003 passed, 20 skipped, 41 deselected in 208.09s', zero failures/errors; the collection-only variant of the same flags exits 0 with '4023/4064 tests collected (41 deselected)'. ci.yml:81 itself was not modified by this task (last edit 80de287, unrelated) and its --ignore flags for both integration modules remain intact. Note: --timeout=30 was omitted locally only because pytest-timeout is not installed in the local .venv; it is a per-test timeout, not a collection gate, and CI installs it explicitly. [resolution 0.30; ci.yml:81]
A clean clone with no ROM collects 4068 tests with exit 0 (both integration modules excluded via committed tests/conftest.py collect_ignore), and the ci.yml:81 pytest leg flags run green at 4003 passed / 20 skipped / 0 failed.

## Summary

Judge Result: QA-AI-PLAYS-POKE-7

Stage tier1: PASS
    ✓ lint: ok (no output)
  ✓ secrets: secrets: harness state excluded from gitleaks scope (.gitreins/**)
  ✓ tests: ============================= test session starts ==============================

Stage tier2: PASS
  COMPLETE
  ✓ From a clean clone with no ROM present, pytest tests/ --co -q exits 0 — both integration modules guarded or excluded by committed repo content — and CI's pytest leg flags (ci.yml:81) still pass: Verified empirically in a fresh clone (`git clone /home/kara/ai_plays_poke /tmp/cleanclone`, HEAD 95fddf8 = merge of 32a1d6b) where `ls data/rom/` contains only README.md and `find . -name '*.gb' -o -name '*.gbc' -o -name '*.gba'` returns nothing. (1) `pytest tests/ --co -q` with OPENROUTER_API_KEY/OPENAI_API_KEY/PTP_LIVE unset → EXIT_CODE=0, '4068 tests collected in 1.26s', zero collection errors; grep for 'test_phase4_integration|test_vision_integration' in the collection output = 0 matches, i.e. both modules are excluded. (2) The exclusion is committed repo content: commit 32a1d6b adds `collect_ignore = ["test_phase4_integration.py", "test_vision_integration.py"]` at tests/conftest.py:25-30, and both files are git-tracked (git ls-files confirms) with module-level side effects (test_phase4_integration.py:16 constructs `Emulator("data/rom/Pokemon - Blue Version (USA, Europe) (SGB Enhanced).gb")` at import time and calls sys.exit(1) at line 73; test_vision_integration.py:21 calls sys.exit(1) when the API key is absent). (3) CI's pytest leg flags at ci.yml:81 still pass — ran the exact flag set (`pytest tests/ -q --tb=line -k "not live" --ignore=tests/test_live_demo.py --ignore=tests/test_phase4_integration.py --ignore=tests/test_vision_integration.py --deselect=tests/test_edge_cases.py::TestROMHandling::test_rom_path_with_spaces`) → '4003 passed, 20 skipped, 41 deselected in 208.09s', zero failures/errors; the collection-only variant of the same flags exits 0 with '4023/4064 tests collected (41 deselected)'. ci.yml:81 itself was not modified by this task (last edit 80de287, unrelated) and its --ignore flags for both integration modules remain intact. Note: --timeout=30 was omitted locally only because pytest-timeout is not installed in the local .venv; it is a per-test timeout, not a collection gate, and CI installs it explicitly. [resolution 0.30; ci.yml:81]
A clean clone with no ROM collects 4068 tests with exit 0 (both integration modules excluded via committed tests/conftest.py collect_ignore), and the ci.yml:81 pytest leg flags run green at 4003 passed / 20 skipped / 0 failed.

Overall: PASS ✓
