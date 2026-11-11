# Spec index — AI-Plays-Poke (PTP-01X) design spec set

Status: DRAFT v0.1, 2026-11-11. Facts measured; quorum NOT yet convened.

| artifact | status | notes |
|---|---|---|
| 00-frame.md | WRITTEN | spine: responsibilities, not paths |
| _facts.md | 26 facts, all measured/read-from-code | measured 2026-11-11 unless dated |
| _rumsfeld.md | 4 quadrants populated | Q-01..03, U-01..04, N-01..03 with sinks |
| 00-overview.md | actors, boundary, invariants, surfaces | INV-1 measured VIOLATED |
| flows/ FLOW-01, FLOW-02 | perceive-decide-act; operator console; fleet loop | failure paths + day-one + concurrency |
| modules/ MOD-01..06 | bridge, RAM reader, vision, decision core, console, fleet | owns / does-not-own / failure modes |
| contracts/_matrix.md | CT-01..07 + R-001..R-010 | 3 measured violations named |
| handbook SET (10 sheets) | RENDERED, merged, folio-verified | docs/handbook/aipp-handbook.pdf |

## Coverage statement (areas measured 2026-11-11)
- src/core/: ram_reader.py, vision.py, vision_grid.py — COVERED (MOD-02/03)
- scripts/: game_bridge.py, cron_runner.py, long_run.py, perception_diff.py, vision_people_probe.py — COVERED (MOD-01/04/03)
- console (~/aipp-console): server.py, static/index.html — COVERED (MOD-05)
- tests/: covered only as assertion targets; test files not individually documented
- .coding-hermes/ fleet plumbing: FLOW-03 only; scheduler internals OUT OF SCOPE (own repo)

## Known gaps (filed, not hidden)
- VISION-GRID-UNIFY (P1): one grid definition shared by RAM + vision (R-001) — the set's central defect
- ARM-2-R1 (P1): remove long_run.py's silent 'jev' fallback (R-003)
- Quorum (Phase 10): NOT convened — this set has had no independent panel round
