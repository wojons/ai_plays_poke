# AI Plays Pokémon — Coding Hermes Tasks
# Foreman: deepseek-v4-pro | Coding model: ollama-cloud/minimax-m3

## Active Queue

### [ ] PHASE-1: Unified Emulator + Tool Executor
**Model:** ollama-cloud/minimax-m3
**Files:** src/core/emulator.py (rewrite), src/core/tools.py (new), src/core/rom_detect.py (new)
**Verify:** `python -c "from src.core.emulator import Emulator; e = Emulator('data/rom/Pokemon - Blue Version (USA, Europe) (SGB Enhanced).gb'); print(e.capture()); e.press_button('A', 5); print('OK')"`
**Status:** ready to spawn

### [ ] PHASE-2: Prompt Config System
**Model:** ollama-cloud/minimax-m3
**Files:** configs/prompts/**/*.yaml (new), src/core/prompt_assembler.py (new)
**Verify:** Python imports, YAML parses, assembler produces valid prompt string with all layers

### [ ] PHASE-3: Vision Pipeline
**Model:** ollama-cloud/minimax-m3
**Files:** src/core/vision.py (new/rewrite), tests/test_vision_pipeline.py
**Verify:** Can call Gemma 12B with a screenshot, receive valid JSON back

### [ ] PHASE-4: Decision Pipeline
**Model:** ollama-cloud/minimax-m3
**Files:** src/core/decision.py (new), src/game_loop.py (rewrite decision methods)
**Verify:** Full loop: screenshot → vision → assemble → think → tool call → execute → repeat

### [ ] PHASE-5: Cron Loop
**Model:** deepseek-v4-pro (foreman direct)
**Files:** .coding-hermes/cron.sh, hermes cron job config
**Verify:** Autonomous ticks with checkpoint commits
