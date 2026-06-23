# AI Plays Pokémon — Coding Hermes Tasks
# Foreman: deepseek-v4-pro | Coding model: ollama-cloud/minimax-m3

## Active Queue

### [x] PHASE-1: Unified Emulator + Tool Executor ✅ (d372832)
### [x] PHASE-2: Prompt Config System ✅ (a26540e)
### [x] PHASE-3: Vision Pipeline ✅ (ea6a2c6)
### [x] PHASE-4: Decision Pipeline ✅ (348b372)

### [x] PHASE-5: Autonomous Cron Loop
**Model:** deepseek-v4-pro (foreman direct)
**Result:** Created .coding-hermes/cron.sh wrapper script. DecisionLoop runner that skips intro, runs N cycles, reports results. Executable, venv-aware, API-key aware.
**Commit:** (pending)

### [x] BUGFIX: Advance past game intro
**Model:** deepseek-v4-pro (foreman direct)
**Result:** Added `Emulator.skip_intro()` method — presses A for 30 frames + waits 60 frames, repeated 16×. Defaults work for GBA gen3 (LeafGreen/FireRed). Configurable press_frames, wait_frames, repetitions.
**Commit:** (pending)

