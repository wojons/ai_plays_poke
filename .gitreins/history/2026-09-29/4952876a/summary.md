# Verdict: PERCEPT-NPC-TERRAIN

**Task:** Sprite layer: NPCs render as N and sprite cells block movement
**Evaluated:** 2026-09-29T05:53:16.745025
**Result:** ✗ FAIL

## Pipeline Stages

- ✓ **tier1**
  -   ✓ lint: ok (no output)
  ✓ secrets: secrets: harness state excluded from gitleaks scope (.gitreins/**)
  ✓ tests: ============================= test session starts ==============================
- ✗ **tier2**
  - INCOMPLETE
  ✗ Given a fabricated sprite table with a person inside the visible window, at least one grid cell renders as N and sits at the derived (col,row) while sprite 0 derives to the reader's own player cell; a state with no other sprite yields zero N cells; a cell occupied by a sprite reads blocked in the adjoining-walkability verdict while the same cell reads walkable with the sprite absent; existing tests stay green.: No sprite/NPC layer was implemented. render_tile_grid (src/core/ram_reader.py:1221-1340) has a cell loop at lines 1283-1325 whose only branches are: off-map '?', player glyph, walkable-None '?', water 'W', grass 'G', walkable 'D'/'.', tree 'T', object '1'-'9', else 'B' — there is NO branch that emits 'N' and no read of the sprite table (only ADDR_SPRITE_STATE_DATA+9 for facing at line 955 and the active flag at line 1017). The legend at line 1333 advertises 'N=person' but nothing ever produces that glyph, so the fabricated-sprite-table case cannot render an N at a derived (col,row). grep for sprite_table|sprite_cells|npc_cells|blocked_by_sprite|sprite_block across src/ and tests/ returns nothing. adjacent_walkability (src/core/ram_reader.py:1417-1435) consults only self._mapdb.tile_walkability(map_id, tile_x+dx, tile_y+dy) with no sprite-occupancy subtraction, so a sprite-occupied cell still reads 'walkable' — the exact silent-failure the task asks to fix. No test fabricates a sprite table or asserts N cells / sprite blocking: grep 'sprite' in tests/test_ram_reader.py hits only the player_screen_px column tests (lines 2404, 2452-2469) and the sprite-active byte at line 110. The board entry PERCEPT-5 in .coding-hermes/board/tasks.jsonl:190 is still status 'pending' and describes this work as NEEDED ('FIX: subtract occupied sprite cells from walkability before reporting it'). Existing tests do stay green: ./.venv/bin/pytest tests/test_ram_reader.py -q => '155 passed in 0.21s', exit_code 0 — but that only satisfies the last clause of the criterion, not the sprite-rendering or sprite-blocking behaviour.
The sprite layer is entirely absent — render_tile_grid never emits 'N' and adjacent_walkability never accounts for sprite occupancy, so only the 'existing tests stay green' clause is met.

## Summary

Judge Result: PERCEPT-NPC-TERRAIN

Stage tier1: PASS
    ✓ lint: ok (no output)
  ✓ secrets: secrets: harness state excluded from gitleaks scope (.gitreins/**)
  ✓ tests: ============================= test session starts ==============================

Stage tier2: FAIL
  INCOMPLETE
  ✗ Given a fabricated sprite table with a person inside the visible window, at least one grid cell renders as N and sits at the derived (col,row) while sprite 0 derives to the reader's own player cell; a state with no other sprite yields zero N cells; a cell occupied by a sprite reads blocked in the adjoining-walkability verdict while the same cell reads walkable with the sprite absent; existing tests stay green.: No sprite/NPC layer was implemented. render_tile_grid (src/core/ram_reader.py:1221-1340) has a cell loop at lines 1283-1325 whose only branches are: off-map '?', player glyph, walkable-None '?', water 'W', grass 'G', walkable 'D'/'.', tree 'T', object '1'-'9', else 'B' — there is NO branch that emits 'N' and no read of the sprite table (only ADDR_SPRITE_STATE_DATA+9 for facing at line 955 and the active flag at line 1017). The legend at line 1333 advertises 'N=person' but nothing ever produces that glyph, so the fabricated-sprite-table case cannot render an N at a derived (col,row). grep for sprite_table|sprite_cells|npc_cells|blocked_by_sprite|sprite_block across src/ and tests/ returns nothing. adjacent_walkability (src/core/ram_reader.py:1417-1435) consults only self._mapdb.tile_walkability(map_id, tile_x+dx, tile_y+dy) with no sprite-occupancy subtraction, so a sprite-occupied cell still reads 'walkable' — the exact silent-failure the task asks to fix. No test fabricates a sprite table or asserts N cells / sprite blocking: grep 'sprite' in tests/test_ram_reader.py hits only the player_screen_px column tests (lines 2404, 2452-2469) and the sprite-active byte at line 110. The board entry PERCEPT-5 in .coding-hermes/board/tasks.jsonl:190 is still status 'pending' and describes this work as NEEDED ('FIX: subtract occupied sprite cells from walkability before reporting it'). Existing tests do stay green: ./.venv/bin/pytest tests/test_ram_reader.py -q => '155 passed in 0.21s', exit_code 0 — but that only satisfies the last clause of the criterion, not the sprite-rendering or sprite-blocking behaviour.
The sprite layer is entirely absent — render_tile_grid never emits 'N' and adjacent_walkability never accounts for sprite occupancy, so only the 'existing tests stay green' clause is met.

Overall: FAIL ✗
