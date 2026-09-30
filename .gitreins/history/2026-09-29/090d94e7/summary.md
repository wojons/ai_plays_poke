# Verdict: PERCEPT-2

**Task:** derive outdoor terrain labels from ROM behavior
**Evaluated:** 2026-09-29T08:30:33.745765
**Result:** ✓ PASS

## Pipeline Stages

- ✓ **tier1**
  -   ✓ lint: ok (no output)
  ✓ secrets: secrets: harness state excluded from gitleaks scope (.gitreins/**)
  ✓ tests: ============================= test session starts ==============================
- ✓ **tier2**
  - COMPLETE
  ✓ Pallet Town plain ground is not classified as grass; grass labels remain tied to authoritative ROM behavior; regression test proves the distinction: Bug fixed: old code (git show HEAD:src/core/ram_reader.py:392-397) had _TILESET0_CLASSES mapping block 0x01 -> 'grass', misclassifying Pallet plain ground. New code removes that table and derives outdoor terrain from ROM behavior via tile_terrain()/_terrain_from_raw() (src/core/ram_reader.py:462-514). Grass is tied to authoritative ROM behavior: _tileset_behavior() reads the grass_tile byte from the tileset header at header+10 (ram_reader.py:395) and _terrain_from_raw compares the encounter raw tile against it (ram_reader.py:478-480); verified live grass_tile byte = 0x52. Regression tests exist and pass: tests/test_ram_reader.py:2487 test_pallet_plain_ground_is_not_grass (asserts grid row '..GG↑...??' and tile_terrain(0,5,6)=='floor'), :1111 test_terrain_comes_from_rom_behavior, :1121 test_block_summary_does_not_reintroduce_block_id_guess (classify_block(0x01,0)=='floor', classify_block(0x0B,0)=='grass'). NON-VACUOUS PROOF: running the 3 new tests against the OLD implementation (git show HEAD:src/core/ram_reader.py) made all 3 FAIL, including 'assert GG..↑GGG?? == ..GG↑...??' for test_pallet_plain_ground_is_not_grass — proving the old code painted plain ground as grass; file restored, diff clean. Test run: `./.venv/bin/pytest tests/test_ram_reader.py -q` -> 150 passed in 0.18s (exit 0); targeted 3 tests -> 3 passed. LSP diagnostics: 0.
Pallet plain ground is now correctly classified as floor (not grass) via ROM-behavior-derived terrain, with non-vacuous regression tests that fail against the old block-ID table and pass against the new code.

## Summary

Judge Result: PERCEPT-2

Stage tier1: PASS
    ✓ lint: ok (no output)
  ✓ secrets: secrets: harness state excluded from gitleaks scope (.gitreins/**)
  ✓ tests: ============================= test session starts ==============================

Stage tier2: PASS
  COMPLETE
  ✓ Pallet Town plain ground is not classified as grass; grass labels remain tied to authoritative ROM behavior; regression test proves the distinction: Bug fixed: old code (git show HEAD:src/core/ram_reader.py:392-397) had _TILESET0_CLASSES mapping block 0x01 -> 'grass', misclassifying Pallet plain ground. New code removes that table and derives outdoor terrain from ROM behavior via tile_terrain()/_terrain_from_raw() (src/core/ram_reader.py:462-514). Grass is tied to authoritative ROM behavior: _tileset_behavior() reads the grass_tile byte from the tileset header at header+10 (ram_reader.py:395) and _terrain_from_raw compares the encounter raw tile against it (ram_reader.py:478-480); verified live grass_tile byte = 0x52. Regression tests exist and pass: tests/test_ram_reader.py:2487 test_pallet_plain_ground_is_not_grass (asserts grid row '..GG↑...??' and tile_terrain(0,5,6)=='floor'), :1111 test_terrain_comes_from_rom_behavior, :1121 test_block_summary_does_not_reintroduce_block_id_guess (classify_block(0x01,0)=='floor', classify_block(0x0B,0)=='grass'). NON-VACUOUS PROOF: running the 3 new tests against the OLD implementation (git show HEAD:src/core/ram_reader.py) made all 3 FAIL, including 'assert GG..↑GGG?? == ..GG↑...??' for test_pallet_plain_ground_is_not_grass — proving the old code painted plain ground as grass; file restored, diff clean. Test run: `./.venv/bin/pytest tests/test_ram_reader.py -q` -> 150 passed in 0.18s (exit 0); targeted 3 tests -> 3 passed. LSP diagnostics: 0.
Pallet plain ground is now correctly classified as floor (not grass) via ROM-behavior-derived terrain, with non-vacuous regression tests that fail against the old block-ID table and pass against the new code.

Overall: PASS ✓
