# AI Plays Pokémon — Coding Hermes Tasks
# Foreman: deepseek-v4-pro | Coding model: ollama-cloud/glm-5.2

## Active Queue

### [x] PHASE-1: Unified Emulator + Tool Executor ✅ (d372832)
### [x] PHASE-2: Prompt Config System ✅ (a26540e)
### [x] PHASE-3: Vision Pipeline ✅ (ea6a2c6)
### [x] PHASE-4: Decision Pipeline ✅ (348b372)

### [x] PHASE-5: Autonomous Cron Loop ✅ (8d19a6c)
**Model:** deepseek-v4-pro (foreman direct)
**Result:** Created .coding-hermes/cron.sh wrapper script. DecisionLoop runner that skips intro, runs N cycles, reports results.

### [x] BUGFIX: Advance past game intro ✅ (8d19a6c)
**Model:** deepseek-v4-pro (foreman direct)
**Result:** Added `Emulator.skip_intro()` method — presses A for 30 frames + waits 60 frames, repeated 16×. Defaults work for GBA gen3.

### [x] DEMO-1: Gameplay integration test ✅ (b20d033)
**Model:** deepseek-v4-pro (foreman direct — thin composition)
**Files:** src/core/demo_runner.py (new), tests/test_gameplay_demo.py (new)
**Result:** DemoRunner with run() + run_headless(). 12 tests (10 unit + 2 headless ROM) all pass. Live API tests gated behind OPENROUTER_API_KEY.

### [x] DEMO-2: Vision-only headless test (no API key needed) ✅ (384c511)
**Model:** deepseek-v4-pro (foreman direct)
**Files:** tests/test_vision_headless.py (new)
**Result:** 56 headless vision tests — VisionClient parsing (18 tests), encoding/OCR extraction (10 tests), PromptStack assembly + helpers (28 tests). All pass without ROM or API key. Covers AC-006, AC-007, AC-008.

### [x] CHORE-1: Fix test_validate_valid_config ROM dependency ✅ (384c511)
**Model:** deepseek-v4-pro (foreman direct)
**Files:** tests/ptp_cli/test_flags.py
**Result:** Replaced hardcoded `/tmp/test_pokemon.gb` paths with `tmp_path` fixture (temporary files). 4 tests fixed — test_validate_valid_config, test_validate_verbose_quiet_conflict, test_parse_and_validate_success, test_parse_and_validate_error. All pass. AC-009 satisfied.

### [x] BUGFIX: ROM edge-case tests — EmulatorInterface→Emulator rename ✅ (b04a17b)
**Model:** deepseek-v4-pro (foreman direct — mechanical fix)
**Files:** tests/test_edge_cases.py
**Result:** Fixed all 7 ROM handling tests for the `EmulatorInterface`→`Emulator` class rename. Updated assertion patterns from `pyboy is None` checks to `pytest.raises(Exception)` wrappers (new class eagerly validates ROMs). Also fixed test_api_key_empty_string to clear both OPENAI_API_KEY and OPENROUTER_API_KEY. 297/298 tests pass (pre-existing test_database_locked failure).

### [x] LIVE-DEMO: End-to-end gameplay test with real API calls ✅
**Priority:** high
**Model:** deepseek-v4-pro (foreman direct — test only)
**Files:** tests/test_live_demo.py (new)
**Result:** 4 live tests (AC-010 through AC-013) all pass — 269s with real ROM (GBA LeafGreen) + owl-alpha vision/thinking. Test file: +270 lines. Screenshots validated at (160,240,3) for GBA. Tool calls verified against TOOL_SCHEMA. Summary fields checked for completeness.

### [ ] COVERAGE: Add unit tests for ToolExecutor class
**Priority:** medium
**Model:** ollama-cloud/minimax-m3 (1 file, mechanical)
**Files:** tests/test_tools.py (new)
**Verify:** `source venv/bin/activate && python -m pytest tests/test_tools.py -v`
**AC:**
- AC-014: test_parse_tool_call_code_fenced — code-fenced JSON → correct tool name + args
- AC-015: test_parse_tool_call_inline — inline "ACTION:" format → extracted action
- AC-016: test_execute_tool_call_press_button — press_button call → emulator receives correct method
- AC-017: test_execute_tool_call_wait — wait call → emulator advances correct frames
- AC-018: test_execute_tool_call_invalid — unknown tool name → handled gracefully
**Status:** ready
