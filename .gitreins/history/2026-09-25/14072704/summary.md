# Verdict: JEV-5

**Task:** Assist-inventory guard: fail build on new deterministic press_button call site outside declared set
**Evaluated:** 2026-09-25T09:14:02.141909
**Result:** ✓ PASS

## Pipeline Stages

- ✓ **tier1**
  -   ✓ lint: ok (no output)
  ✓ secrets: secrets: harness state excluded from gitleaks scope (.gitreins/**)
  ✓ tests: ============================= test session starts ==============================
- ✓ **tier2**
  - COMPLETE
  ✓ CI/pre-commit guard fails when a new emu.press_button call site appears outside the declared assist set; declared set documented; pytest+ruff+mypy green: Guard: scripts/check_assist_inventory.py (312-line stdlib-only AST guard). Clean tree: `python3 scripts/check_assist_inventory.py` -> 'PASS: assist inventory matches 60 press_button call sites.' EXIT=0. Fail-closed verified by live injection: appending `emu.press_button("start", frames=7)` to a cron_runner.py copy -> 'FAIL: assist inventory mismatch (1 new, 0 stale; 61 source sites, 60 declarations).' EXIT=1; appending `emu.press_button("a", frames=30)` to src/core/tools.py copy -> FAIL EXIT=1; renaming enclosing fn `_tap`->`_tap_renamed` -> 'STALE src/core/tools.py _tap' + FAIL EXIT=1 (context is part of the match key). CI wired at .github/workflows/ci.yml step 3 'Guard declared press_button assist inventory' -> `python3 scripts/check_assist_inventory.py` (YAML parses valid; guard is stdlib-only so it runs before deps install). Regression tests tests/test_assist_inventory_guard.py: 3 passed (clean-pass, new-site-fail, stale-declaration-fail). Declared set documented: config/assist_inventory.json carries version/scope ['cron_runner.py','src/**/*.py']/matching/notes plus 60 sites each with non-empty file/context/button/call/reason (0 allow_stale), and docs/prd/PRD_v3_jev_duckbrain.md §2.2 'What was actually hardcoded — the assist inventory' (A1–A9) + AC-8 'no assist without an entry' names the exact `emu.press_button(` guard requirement. Green checks with real output: pytest `./venv/bin/pytest tests/ -q -k 'not live' --ignore=tests/test_live_demo.py --ignore=tests/test_phase4_integration.py --ignore=tests/test_vision_integration.py` -> '4073 passed, 8 skipped, 41 deselected in 317.34s', 0 failed; ruff `./venv/bin/ruff check src/ tests/ cron_runner.py scripts/check_assist_inventory.py` -> 'All checks passed!'; mypy `./venv/bin/mypy src/ --ignore-missing-imports` -> 'Success: no issues found in 66 source files'.
The assist-inventory guard is implemented, CI-wired, fail-closed on new/renamed press_button sites, its declared set is documented in config/assist_inventory.json and PRD §2.2/AC-8, and pytest (4073 passed), ruff, and mypy are all green.

## Summary

Judge Result: JEV-5

Stage tier1: PASS
    ✓ lint: ok (no output)
  ✓ secrets: secrets: harness state excluded from gitleaks scope (.gitreins/**)
  ✓ tests: ============================= test session starts ==============================

Stage tier2: PASS
  COMPLETE
  ✓ CI/pre-commit guard fails when a new emu.press_button call site appears outside the declared assist set; declared set documented; pytest+ruff+mypy green: Guard: scripts/check_assist_inventory.py (312-line stdlib-only AST guard). Clean tree: `python3 scripts/check_assist_inventory.py` -> 'PASS: assist inventory matches 60 press_button call sites.' EXIT=0. Fail-closed verified by live injection: appending `emu.press_button("start", frames=7)` to a cron_runner.py copy -> 'FAIL: assist inventory mismatch (1 new, 0 stale; 61 source sites, 60 declarations).' EXIT=1; appending `emu.press_button("a", frames=30)` to src/core/tools.py copy -> FAIL EXIT=1; renaming enclosing fn `_tap`->`_tap_renamed` -> 'STALE src/core/tools.py _tap' + FAIL EXIT=1 (context is part of the match key). CI wired at .github/workflows/ci.yml step 3 'Guard declared press_button assist inventory' -> `python3 scripts/check_assist_inventory.py` (YAML parses valid; guard is stdlib-only so it runs before deps install). Regression tests tests/test_assist_inventory_guard.py: 3 passed (clean-pass, new-site-fail, stale-declaration-fail). Declared set documented: config/assist_inventory.json carries version/scope ['cron_runner.py','src/**/*.py']/matching/notes plus 60 sites each with non-empty file/context/button/call/reason (0 allow_stale), and docs/prd/PRD_v3_jev_duckbrain.md §2.2 'What was actually hardcoded — the assist inventory' (A1–A9) + AC-8 'no assist without an entry' names the exact `emu.press_button(` guard requirement. Green checks with real output: pytest `./venv/bin/pytest tests/ -q -k 'not live' --ignore=tests/test_live_demo.py --ignore=tests/test_phase4_integration.py --ignore=tests/test_vision_integration.py` -> '4073 passed, 8 skipped, 41 deselected in 317.34s', 0 failed; ruff `./venv/bin/ruff check src/ tests/ cron_runner.py scripts/check_assist_inventory.py` -> 'All checks passed!'; mypy `./venv/bin/mypy src/ --ignore-missing-imports` -> 'Success: no issues found in 66 source files'.
The assist-inventory guard is implemented, CI-wired, fail-closed on new/renamed press_button sites, its declared set is documented in config/assist_inventory.json and PRD §2.2/AC-8, and pytest (4073 passed), ruff, and mypy are all green.

Overall: PASS ✓
