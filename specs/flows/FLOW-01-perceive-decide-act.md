# FLOW-01 — Perceive, decide, act (the game loop)

- **trigger:** `cron_runner.py --run-id <id> --cycles N` (or `long_run.py` for episodes); boot from `data/boot.state` (FACT-18).
- **exit:** episode log row appended with the episode's final map, decisions, escalations; emulator state saved.

## Steps
1. **Boot** — `cron_runner` loads the checkpoint, warns on ROM mismatch (FACT-18). *(cron_runner)*
2. **Perceive (RAM)** — `RAMReader.observe()`: map id, player tile, facing, party, collision; renders the 10×9 tile grid with the facing arrow (FACT-03/06). *(MOD-02)*
3. **Perceive (vision)** — `VisionClient`: fetch frame via bridge `frame` op, upscale ×6 LANCZOS cap 1024 (FACT-11), call the configured model with the terse grid prompt (FACT-12/13); parse 9 lines × 10 chars. *(MOD-03)*
4. **Diff** — cell-by-cell RAM vs vision; disagreement is a FINDING, never auto-resolved. Verdict: agree / conflict / facing / both-unknown. **Blocked by INV-1 violation** (FACT-07). *(MOD-03)*
5. **Decide** — JEV answers every cycle (System One); on confidence < 0.50 or ambiguity > 0.40 (FACT-09) it escalates to the LLM (System Two), which **repairs state, not actions**. Mode from `resolve_decision_mode` (FACT-08). *(MOD-04)*
6. **Act** — chosen buttons go to the bridge `press` op; world advances N frames via `step`. *(MOD-01)*
7. **Record** — episode row: final map, decisions, escalations, teacher calls. *(MOD-04)*

## Failure paths
- Bridge unreachable → run fails fast, no phantom episode (bridge refuses without token, FACT-01).
- Vision fails/empty → verdict must record "vision unavailable"; **unverified whether it does** (U-04). Risk: stale reading compared as if fresh.
- Escalation → teacher repairs state; 0 teacher calls in the Sept run (28 eps) — the escalation path is unexercised at scale.

## Concurrency
- Bridge serialises Game access (bound-concurrency fix 640476c). Two drivers must never overlap (FACT-26): operator console session and agent run are mutually exclusive.

## Day-one case
- Fresh clone: no vision cache → console shows "(nothing yet)" until first movement triggers a read.

## Timing
- One vision read ≈ 2.4-4 s and ≈ 25k input tokens (FACT-12/13). Auto-vision re-reads on movement or scene change, ≥ 25 s apart; the 120 s idle timer was removed (2026-10-01).

## The one-row offset (the spec's central defect)
RAM grid: 10 cols × 9 rows, arrow at row 3 (FACT-06). `vision_grid.py`: 9×9, player (4,4) (FACT-05).
Every cell comparison is shifted one row vertically. The verdict numbers are therefore systematically
wrong by one row until VISION-GRID-UNIFY lands.
