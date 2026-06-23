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

### [ ] DEMO-2: Vision-only headless test (no API key needed)
**Priority:** medium
**Model:** deepseek-v4-pro (foreman direct)
**Files:** tests/test_vision_headless.py (new)
**Description:** Tests the vision pipeline without requiring an API key. Uses placeholder screenshots or statically-generated frame buffers to verify OCR text extraction, screen classification, and prompt assembly. Fast, reproducible, no network.
**Verify:** `source venv/bin/activate && python -m pytest tests/test_vision_headless.py -v --tb=short -x`
**AC:**
- AC-006: VisionClient.classify returns valid ScreenClassification for known screen types
- AC-007: OCR extracts recognizable text from frame buffer regions
- AC-008: PromptStack assembles correctly from vision output
**Status:** ready

### [ ] CHORE-1: Fix test_validate_valid_config ROM dependency
**Priority:** low
**Model:** deepseek-v4-pro (foreman direct)
**Files:** tests/ptp_cli/test_flags.py
**Description:** test_validate_valid_config fails because it looks for ROM at /tmp/test_pokemon.gb which doesn't exist. Either mock the ROM path check or create a temp ROM file in the test.
**Verify:** `source venv/bin/activate && python -m pytest tests/ptp_cli/test_flags.py::TestCLIFlagParser::test_validate_valid_config -v --tb=short -x`
**AC:**
- AC-009: test_validate_valid_config passes without requiring a real ROM file
**Status:** ready
