# Verdict: DOC-15

**Task:** Document stdio MCP game-tool interface
**Evaluated:** 2026-10-12T17:17:56.027854
**Result:** ✗ FAIL

## Pipeline Stages

- ✗ **tier1**
  -   ✓ lint: scanners: nice=nice -n 10
  ~ secrets: Command timed out after 120s (step budget)
  ✓ tests: scanners: nice=nice -n 10
- ✓ **tier2**
  - COMPLETE
  ✓ Canonical main contains docs/api/mcp.md linked from docs/api/index.md; fresh initialize/tools/list probe reports protocol 2024-11-05 and all 12 game tools; relative links resolve.: Canonical main (/home/kara/ai_plays_poke, HEAD=main=15e4bae 'docs: document stdio MCP game tools'; git branch --contains 15e4bae => main) contains docs/api/mcp.md (134 lines). docs/api/index.md links it: '| [MCP game tools](mcp.md) | Stdio JSON-RPC MCP interface (scripts/aipp_mcp.py) ...'. Fresh probe `printf initialize+tools/list | .venv/bin/python scripts/aipp_mcp.py` exit=0, empty stderr, output: {"protocolVersion": "2024-11-05", "serverInfo": {"name": "aipp-game", "version": "1.0.0"}} and 12 tools exactly matching the doc's expected list (game_observe, game_screenshot, game_press, game_step, game_pause, game_resume, game_save, game_load, game_list_saves, game_delete_save, game_reset, game_health); the doc's embedded assertion script ran and printed 'protocol=2024-11-05; count=12'. Source of truth scripts/aipp_mcp.py: PROTOCOL_VERSION="2024-11-05" (line 42) and 12 tool "name" entries (lines 74-175). mcp.md tool table lists all 12 game_* tools (grep count=12). All relative links resolve: mcp.md ../bridge.md -> docs/bridge.md OK; index.md all 18 relative links (game_loop.md, mcp.md, ../bridge.md, examples/*.md, ../../specs/technical_specifications_v5_complete.md, ../../docs/architecture.md, ../../README.md) resolve with 0 missing. [resolution 0.05; docs/api/mcp.md, docs/api/index.md]
docs/api/mcp.md exists on canonical main, is linked from docs/api/index.md, the fresh initialize/tools/list probe reports protocol 2024-11-05 with all 12 game tools, and every relative link resolves.

## Summary

Judge Result: DOC-15

Stage tier1: FAIL
  WARNING: coverage is secrets+lint+tests — secrets did not run (skipped at runtime — secrets: timed out after 120s (step budget)); run `gitreins guard` for the full gate
    ✓ lint: scanners: nice=nice -n 10
  ~ secrets: Command timed out after 120s (step budget)
  ✓ tests: scanners: nice=nice -n 10

Stage tier2: PASS
  COMPLETE
  ✓ Canonical main contains docs/api/mcp.md linked from docs/api/index.md; fresh initialize/tools/list probe reports protocol 2024-11-05 and all 12 game tools; relative links resolve.: Canonical main (/home/kara/ai_plays_poke, HEAD=main=15e4bae 'docs: document stdio MCP game tools'; git branch --contains 15e4bae => main) contains docs/api/mcp.md (134 lines). docs/api/index.md links it: '| [MCP game tools](mcp.md) | Stdio JSON-RPC MCP interface (scripts/aipp_mcp.py) ...'. Fresh probe `printf initialize+tools/list | .venv/bin/python scripts/aipp_mcp.py` exit=0, empty stderr, output: {"protocolVersion": "2024-11-05", "serverInfo": {"name": "aipp-game", "version": "1.0.0"}} and 12 tools exactly matching the doc's expected list (game_observe, game_screenshot, game_press, game_step, game_pause, game_resume, game_save, game_load, game_list_saves, game_delete_save, game_reset, game_health); the doc's embedded assertion script ran and printed 'protocol=2024-11-05; count=12'. Source of truth scripts/aipp_mcp.py: PROTOCOL_VERSION="2024-11-05" (line 42) and 12 tool "name" entries (lines 74-175). mcp.md tool table lists all 12 game_* tools (grep count=12). All relative links resolve: mcp.md ../bridge.md -> docs/bridge.md OK; index.md all 18 relative links (game_loop.md, mcp.md, ../bridge.md, examples/*.md, ../../specs/technical_specifications_v5_complete.md, ../../docs/architecture.md, ../../README.md) resolve with 0 missing. [resolution 0.05; docs/api/mcp.md, docs/api/index.md]
docs/api/mcp.md exists on canonical main, is linked from docs/api/index.md, the fresh initialize/tools/list probe reports protocol 2024-11-05 with all 12 game tools, and every relative link resolves.

Overall: FAIL ✗
