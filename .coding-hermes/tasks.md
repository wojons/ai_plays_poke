# AI Plays Pokémon — Coding Hermes Tasks
# Foreman: deepseek-v4-pro | Coding model: ollama-cloud/glm-5.2

## Active Queue

### [x] PHASE-1: Unified Emulator + Tool Executor ✅ (d372832)
### [x] PHASE-2: Prompt Config System ✅ (a26540e)
### [x] PHASE-3: Vision Pipeline ✅ (ea6a2c6)
### [x] PHASE-4: Decision Pipeline ✅ (348b372)

### [x] PHASE-5: Autonomous Cron Loop ✅ (8d19a6c)
**Model:** deepseek-v4-pro (foreman direct)
**Result:** Created .coding-hermes/cron.sh wrapper script. DecisionLoop runner that skips intro, runs N cycles, reports results. Executable, venv-aware, API-key aware.
**Commit:** 8d19a6c

### [x] BUGFIX: Advance past game intro ✅ (8d19a6c)
**Model:** deepseek-v4-pro (foreman direct)
**Result:** Added `Emulator.skip_intro()` method — presses A for 30 frames + waits 60 frames, repeated 16×. Defaults work for GBA gen3 (LeafGreen/FireRed). Configurable press_frames, wait_frames, repetitions.
**Commit:** 8d19a6c

### [ ] DEMO-1: Gameplay integration test
**Priority:** high
**Model:** ollama-cloud/glm-5.2
**Files:** tests/test_gameplay_demo.py (new), src/core/demo_runner.py (new)
**Description:** End-to-end gameplay test: load ROM, skip intro via Emulator.skip_intro(), run 10 decision cycles with owl-alpha thinking, verify tool execution produces non-trivial game state changes. Must work with OPENROUTER_API_KEY in env.
**Verify:** `OPENROUTER_API_KEY=$(grep OPENROUTER_API_KEY ~/.hermes/.env | cut -d= -f2-) source venv/bin/activate && python -m pytest tests/test_gameplay_demo.py -v --tb=short -k "not live_api" -x`
**AC:**
- AC-001: demo_runner.py loads ROM and skips intro successfully
- AC-002: Vision pipeline classifies screens correctly during gameplay
- AC-003: Decision loop produces tool calls (press A, press B, d-pad) within 5 cycles
- AC-004: Game state changes are detected between cycles (different screen_type or different text)
- AC-005: Failsafe triggers if stuck on same screen for >50 cycles
**Status:** ready

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
