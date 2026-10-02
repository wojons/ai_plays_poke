# Verdict: VIS-PEOPLE-1

**Task:** People-identification prompt with sprite-cell-scored measurement
**Evaluated:** 2026-10-02T05:20:41.773172
**Result:** ✗ FAIL

## Pipeline Stages

- ✗ **tier1**
  -   ✓ lint: ok (no output)
  ✓ secrets: secrets: harness state excluded from gitleaks scope (.gitreins/**)
  ✗ tests: Command timed out
- ✓ **tier2**
  - COMPLETE
  ✓ A dedicated people-identification prompt exists (terse style per VIS-ALIGN-1 lesson), it names each visible person with a cell and a distinguishing feature, and it is scored against the reader's RAM sprite table across a multi-frame set with the failure rate reported honestly (no whole-grid cell-match gaming). Evidence: a measurement script or doc capturing prompt, frames, model answers, sprite-cell ground truth, and per-frame pass/fail.: Dedicated terse prompt at prompts/vision_people.md (6 lines, matching VIS-ALIGN-1 lesson that terse wording moves agreement 30+ points): 'Identify every visible non-player person in the 9x9 window with the player at cell (4,3)' returning {"people":[{"name":"girl","cell":[1,4],"feature":"facing up"}]} — names each person with a cell and a distinguishing feature. Scored against the reader's RAM sprite table: scripts/vision_people_probe.py visible_people() reads wSpriteStateData1 at SPRITE_TABLE=0xC100 (16 records x 16 bytes), excludes player slot 0, filters non-person sprites (NON_PERSON_SPRITES 0x05/0x09/0x38/0x3C) and still objects (>=FIRST_STILL_SPRITE 0x3D), and computes player-relative 9x9 cells. Multi-frame set: docs/vision_people_findings.md runs 3 frames (start, pallet_outside_house_20260929, slot1) via repeated --slot args. Failure rate reported honestly: 'frames failed: 2/3 (66.7% failure rate)', 'RAM person cells matched: 1/5'. No whole-grid gaming: score_predictions() scores exact sprite-cell presence only (docstring 'Score only sprite-cell presence'), and print_results() emits 'score basis: exact RAM sprite cells only; no whole-grid percentage'. Evidence doc captures prompt, frames, model answers (openai/gpt-4o-mini), sprite-cell ground truth, and per-frame CORRECT/MISS with failure lines. Tests: venv/bin/python -m pytest tests/test_vision_people_probe.py -v => '5 passed in 0.56s' (exit 0), covering visible_people RAM-cell extraction, parse validation, wrong-cell/missed/hallucinated scoring, and diagnostic-only facing conflicts.
The terse people-identification prompt, RAM sprite-table scoring probe, multi-frame measurement doc with an honest 66.7% failure rate, and 5 passing focused tests all satisfy the criterion.

## Summary

Judge Result: VIS-PEOPLE-1

Stage tier1: FAIL
    ✓ lint: ok (no output)
  ✓ secrets: secrets: harness state excluded from gitleaks scope (.gitreins/**)
  ✗ tests: Command timed out

Stage tier2: PASS
  COMPLETE
  ✓ A dedicated people-identification prompt exists (terse style per VIS-ALIGN-1 lesson), it names each visible person with a cell and a distinguishing feature, and it is scored against the reader's RAM sprite table across a multi-frame set with the failure rate reported honestly (no whole-grid cell-match gaming). Evidence: a measurement script or doc capturing prompt, frames, model answers, sprite-cell ground truth, and per-frame pass/fail.: Dedicated terse prompt at prompts/vision_people.md (6 lines, matching VIS-ALIGN-1 lesson that terse wording moves agreement 30+ points): 'Identify every visible non-player person in the 9x9 window with the player at cell (4,3)' returning {"people":[{"name":"girl","cell":[1,4],"feature":"facing up"}]} — names each person with a cell and a distinguishing feature. Scored against the reader's RAM sprite table: scripts/vision_people_probe.py visible_people() reads wSpriteStateData1 at SPRITE_TABLE=0xC100 (16 records x 16 bytes), excludes player slot 0, filters non-person sprites (NON_PERSON_SPRITES 0x05/0x09/0x38/0x3C) and still objects (>=FIRST_STILL_SPRITE 0x3D), and computes player-relative 9x9 cells. Multi-frame set: docs/vision_people_findings.md runs 3 frames (start, pallet_outside_house_20260929, slot1) via repeated --slot args. Failure rate reported honestly: 'frames failed: 2/3 (66.7% failure rate)', 'RAM person cells matched: 1/5'. No whole-grid gaming: score_predictions() scores exact sprite-cell presence only (docstring 'Score only sprite-cell presence'), and print_results() emits 'score basis: exact RAM sprite cells only; no whole-grid percentage'. Evidence doc captures prompt, frames, model answers (openai/gpt-4o-mini), sprite-cell ground truth, and per-frame CORRECT/MISS with failure lines. Tests: venv/bin/python -m pytest tests/test_vision_people_probe.py -v => '5 passed in 0.56s' (exit 0), covering visible_people RAM-cell extraction, parse validation, wrong-cell/missed/hallucinated scoring, and diagnostic-only facing conflicts.
The terse people-identification prompt, RAM sprite-table scoring probe, multi-frame measurement doc with an honest 66.7% failure rate, and 5 passing focused tests all satisfy the criterion.

Overall: FAIL ✗
