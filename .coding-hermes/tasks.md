# AI Plays Pokémon — Coding Hermes Tasks
# Foreman: deepseek-v4-pro | Coding model: ollama-cloud/minimax-m3

## Active Queue

### [x] PHASE-1: Unified Emulator + Tool Executor ✅ (d372832)
### [x] PHASE-2: Prompt Config System ✅ (a26540e)
### [x] PHASE-3: Vision Pipeline ✅ (ea6a2c6)
### [x] PHASE-4: Decision Pipeline ✅ (348b372)

### [ ] PHASE-5: Autonomous Cron Loop
**Model:** deepseek-v4-pro (foreman direct)
**Goal:** Set up cron job that runs the decision loop autonomously with checkpoint commits
**Files:** .coding-hermes/cron.sh, hermes cron job config
**Status:** ready

### [ ] BUGFIX: Advance past game intro
The intro sequence (copyright → Game Freak → title → Oak) requires specific button sequences.
Need to script the full intro skip so the AI starts at actual gameplay (Pallet Town overworld).
Add to emulator.py: `skip_intro()` method that handles the full sequence.
