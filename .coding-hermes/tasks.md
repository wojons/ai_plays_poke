# AI Plays Pokémon — Model Router Task Matrix

> **Core purpose:** Autonomous AI agent that plays Pokémon through emulation — RAM reader for perfect state, DeepSeek-powered controller, HSM-driven gameplay, DuckBrain context memory.
> **Language:** Python 3.x | **Stack:** PyBoy emulator, DeepSeek V4 Flash controller, 69-state HSM, Streamlit dashboard
> **Status:** All gameplay tasks complete. Maintenance mode — 28 idle ticks. Cooldown: 43200s.

## Active Tasks

| ID | Task | Pri | Cpx | Deps | Tags | Model | Lvl | Fallback |
|----|------|-----|-----|------|------|-------|-----|----------|
| E2E-001 | E2E Testing Tick (self-improving loop) 🔁 Recurring every 5-10 ticks | High | 4 | ROM + server | ++browser, ++screenshots, ++verification | GPT-5.6 Luna | High | Step 3.7 Flash |
| NEVER-DONE | 11-point audit sweep | Medium | 2 | — | ++code-review, +testing | DeepSeek V4 Pro | Medium | GLM-5.2 |

## Completed (all gameplay tasks done)

Core pipeline: RAM reader → StateWindow → HSM → Controller prompt → DuckBrain → PyBoy execution. All features implemented and tested.

| Component | Key outcomes |
|-----------|--------------|
| Emulator | PyBoy GB/GBC, save/load states, fast-forward, unified interface |
| RAM Reader | 98% coverage, 65 tests, battle state, overworld coordinates, menu detection |
| State Machine | 69-state HSM, 105 tests, transition logging to DuckBrain |
| Controller | Compact RAM-based prompts (~35 tokens), battle agent with HP/moves/type awareness |
| State Window | HSM integration, recent actions memory (5-action sliding window), battle routing |
| Vision Pipeline | Sprite detection (94%), location detection (70%+), OCR (93%), 179+ tests |
| Recovery | Escalating 5-level recovery, void detection, A-press loop fix, intro bypass |
| Dashboard | 16 endpoints, Streamlit UI, CI green (last 5 runs) |
| Testing | 3393 pass, 8 skip, 392 deselected, ruff clean, mypy clean, 0 vulns |
| Deps | pydantic_core blocked (pydantic pin), 11 minor outdated deps (non-blocking) |

## Assumptions

- ROM present for GB/GBC Pokémon (tested with Blue). GBA ROMs rejected by PyBoy
- 28 idle ticks — project stable. No code gaps. 12 cooldown reversions total
- pydantic_core 2.46.4→2.47.0 blocked by pydantic 2.13.4 exact pin
- DuckBrain MCP intermittently unavailable
- Cooldown reversion (daemon restart) persists — 12+ reversions, fleet TOML root cause

## Routing Notes

- **NEVER-DONE audit:** Foreman-direct (V4 Pro) — full context, terminal, file search, test runner
- **E2E testing:** GPT-5.6 Luna for browser/screenshots ($100/mo flat) or Step 3.7 Flash for CLI/API ($0.09/1M)
- **If new Python tasks emerge:** MiniMax-M3 primary (flat-rate prepaid) for bounded implementation, V4 Pro for complex/debugging
- Project is effectively a zombie — 28 idle ticks, zero actionable gaps, all gameplay features complete

## Execution Order

1. NEVER-DONE (runs every tick, creates tasks if gaps found)
2. E2E-001 (periodic, every 5-10 ticks)

## Escalation Conditions

- NEVER-DONE finds code gap → create task, assign MiniMax-M3 or V4 Pro per complexity
- E2E reveals gameplay regression → create BUG task, escalate to V4 Pro
- pydantic releases 2.14+ → re-enable pydantic_core upgrade
- DuckBrain becomes consistently available → sync gameplay learnings
- Idle counter continues past 30 → strong Bane escalation: disable project
