# Verdict: MYPY-CLEANUP-001

**Task:** Fix 6 pre-existing mypy errors in tracked files (guard static_analysis blocker)
**Evaluated:** 2026-08-02T00:32:09.299892
**Result:** ✗ FAIL

## Pipeline Stages

- ✗ **tier1**
  -   ✓ lint: F841 Local variable `cache` is assigned to but never used
  --> tests/test_frame_cache.py:76:5
   |

  ✓ secrets: 
    ○
    │╲
    │ ○
    ○ ░
    ░    gitleaks

[90m7:21PM[0m [32mINF[0m [1mscanned ~149111043
  ✗ tests: Command timed out
- ✗ **tier2**
  - INCOMPLETE
  ✓ venv/bin/mypy src/ --ignore-missing-imports reports zero errors in tracked files (game_loop.py:109, battle.py:274/278, ai_client.py:1385, frame_cache.py:101, test_global_context.py:28): venv/bin/mypy src/ --ignore-missing-imports → 'Success: no issues found in 61 source files'. The 5 specific files (game_loop.py, battle.py, ai_client.py, frame_cache.py, test_global_context.py) also pass mypy with zero issues.
  ✓ SpriteRecognizer._extract_enemy_sprite_region and _extract_player_sprite_region methods exist in src/vision/sprite.py (latent AttributeError fix — methods were called but never defined): src/vision/sprite.py:271 defines _extract_enemy_sprite_region and line 276 defines _extract_player_sprite_region (confirmed via grep).
  ✗ No new type: ignore comments added — misplaced ignores removed/relocated to the correct lines: Commit 94d7a40 added 3 NEW '# type: ignore[arg-type]' comments in tests/test_vision_pipeline.py at lines 189, 407, 461 (vp.validate_screenshot_dimensions(None), vp.process(None), vp.process_with_timeout(None)). These are new type: ignore comments added to tracked files, violating the 'No new type: ignore comments added' requirement.
  ✓ Full test suite passes: venv/bin/pytest tests/ -k 'not benchmark' (3808 passed, 8 skipped) AND benchmark test test_bench_ram_reader_observe passes (mock updated with 0xC100 sprite-state byte so screen_type returns overworld): Full suite: '3808 passed, 8 skipped, 5 deselected in 395.72s'. Benchmark test_bench_ram_reader_observe: '1 passed in 2.26s'. Mock updated with 0xC100:1 (wSpriteStateData1) at tests/test_performance.py:220; screen_type() returns SCREEN_OVERWORLD when read_u8(0xC100) != 0 (src/core/ram_reader.py:886-910).
  ✓ Commit has Co-authored-by: Alexis Okuwa <wojonstech@gmail.com> trailer: Commit 190717b (HEAD) contains 'Co-authored-by: Alexis Okuwa <wojonstech@gmail.com>' trailer; also present in fix commits 7ecf121 and 94d7a40.
4 of 5 criteria pass (mypy clean, sprite methods exist, tests pass, trailer present), but criterion 3 fails because commit 94d7a40 added 3 new '# type: ignore[arg-type]' comments in tests/test_vision_pipeline.py.

## Summary

Judge Result: MYPY-CLEANUP-001

Stage tier1: FAIL
    ✓ lint: F841 Local variable `cache` is assigned to but never used
  --> tests/test_frame_cache.py:76:5
   |

  ✓ secrets: 
    ○
    │╲
    │ ○
    ○ ░
    ░    gitleaks

[90m7:21PM[0m [32mINF[0m [1mscanned ~149111043
  ✗ tests: Command timed out

Stage tier2: FAIL
  INCOMPLETE
  ✓ venv/bin/mypy src/ --ignore-missing-imports reports zero errors in tracked files (game_loop.py:109, battle.py:274/278, ai_client.py:1385, frame_cache.py:101, test_global_context.py:28): venv/bin/mypy src/ --ignore-missing-imports → 'Success: no issues found in 61 source files'. The 5 specific files (game_loop.py, battle.py, ai_client.py, frame_cache.py, test_global_context.py) also pass mypy with zero issues.
  ✓ SpriteRecognizer._extract_enemy_sprite_region and _extract_player_sprite_region methods exist in src/vision/sprite.py (latent AttributeError fix — methods were called but never defined): src/vision/sprite.py:271 defines _extract_enemy_sprite_region and line 276 defines _extract_player_sprite_region (confirmed via grep).
  ✗ No new type: ignore comments added — misplaced ignores removed/relocated to the correct lines: Commit 94d7a40 added 3 NEW '# type: ignore[arg-type]' comments in tests/test_vision_pipeline.py at lines 189, 407, 461 (vp.validate_screenshot_dimensions(None), vp.process(None), vp.process_with_timeout(None)). These are new type: ignore comments added to tracked files, violating the 'No new type: ignore comments added' requirement.
  ✓ Full test suite passes: venv/bin/pytest tests/ -k 'not benchmark' (3808 passed, 8 skipped) AND benchmark test test_bench_ram_reader_observe passes (mock updated with 0xC100 sprite-state byte so screen_type returns overworld): Full suite: '3808 passed, 8 skipped, 5 deselected in 395.72s'. Benchmark test_bench_ram_reader_observe: '1 passed in 2.26s'. Mock updated with 0xC100:1 (wSpriteStateData1) at tests/test_performance.py:220; screen_type() returns SCREEN_OVERWORLD when read_u8(0xC100) != 0 (src/core/ram_reader.py:886-910).
  ✓ Commit has Co-authored-by: Alexis Okuwa <wojonstech@gmail.com> trailer: Commit 190717b (HEAD) contains 'Co-authored-by: Alexis Okuwa <wojonstech@gmail.com>' trailer; also present in fix commits 7ecf121 and 94d7a40.
4 of 5 criteria pass (mypy clean, sprite methods exist, tests pass, trailer present), but criterion 3 fails because commit 94d7a40 added 3 new '# type: ignore[arg-type]' comments in tests/test_vision_pipeline.py.

Overall: FAIL ✗
