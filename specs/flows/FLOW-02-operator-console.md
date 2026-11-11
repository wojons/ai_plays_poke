# FLOW-02 — Operator console session

- **trigger:** operator opens `http://<tailnet-ip>:8899/` (or LAN); no auth (tailnet trust, FACT-15).
- **exit:** operator sees 13 live panels and can drive the emulator; every action lands in the event log.

## Steps
1. **Load** — `GET /` serves `static/index.html`; panels render from `/api/state` (FACT-15).
2. **Refresh** — SSE `/api/stream` pushes state; image refetches at 200 ms while live; vision age ticks every 10 s with NO model call (FACT-25).
3. **Act** — `POST /api/press {buttons:[...]}` / `/api/step {n}` go through the same bridge the agent uses (FACT-15/26).
4. **Read** — `POST /api/vision` starts a background job with a paired frozen snapshot; `POST /api/live {on}` / `POST /api/auto {on}` toggles strict-bool (FACT-16).
5. **Comment** — notes, checklist, event comments; everything persists to `data/*.json`.

## Failure paths
- Bridge starved (serial, one op at a time): measured 25 s batches under load; mitigation = frame cache + reduced rates (2026-09-29).
- Live ticker degrades video after ~4,000 frames (FACT-17): restart the bridge; the console must show frame age so a stale picture is visible.

## Rules
- Panels never blank on a failure: `/api/state` answers a 500 BODY instead of dropping the socket.
- Nothing is hidden from the operator (INV-6).

## FLOW-03 — Build and verify (the fleet loop)
- **trigger:** scheduler tick, admission_mode=tasks.
- **exit:** board row closed with evidence, or an honest dry_run.
- Steps: foreman reads board → picks highest-value pending row → dispatches one worker → verifies (build, tests, judge) → closes row with events → narrates to DuckBrain.
- Defect (filed SCHED-GAP-NODRAIN): the waiver counts blocked/dep-gated rows as work, so the lane re-admits every ~3 min when the board holds only unworkable rows (measured 42 dry ticks / 6 h / 8.3 M tokens on this project alone).
- Defect (behaviour): the foreman declined 6 workable P3/P4 rows — selection policy, unexplained (Q-02).
