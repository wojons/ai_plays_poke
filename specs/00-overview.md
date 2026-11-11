# Overview — AI-Plays-Poke (PTP-01X)

## Purpose
An autonomous agent that wins Pokémon Blue by understanding, not by scripting: it perceives through
RAM and vision, decides through JEV (fast) with LLM escalation (slow), acts through the bridge, and
shows the operator everything on a local console.

## Actors
- **Operator (Bane)** — drives the console, gives rulings, owns release cuts. Trusted.
- **Agent (cron_runner / long_run)** — the player. Semi-trusted: no in-game action without operator approval outside a declared run.
- **JEV (System One)** — fast decider every cycle. Untrusted output: self-reports uncertainty.
- **LLM (System Two)** — repairs state, not actions, on escalation. Untrusted.
- **Vision model(s)** — OpenRouter vision models, per-mode selectable. Untrusted; measured unreliable for people (FACT-14).
- **Bridge (game_bridge.py)** — the ONLY path to the emulator. Loopback + token (FACT-01).
- **Console (server.py)** — the operator's eyes and hands. No auth (tailnet-only exposure).
- **Fleet lanes (foreman/qa/sync/releng/monitoring)** — build and verify the system. Untrusted workers.
- **gitreins judge** — grades evidence. Currently billing-blocked (402) on tier 2.

## Boundary
Inside: emulator process + bridge, RAM/vision readers, decision core, console, board, DuckBrain
namespace `pokemon-global`. Crossing: OpenRouter API (vision + LLM calls), Telegram (delivery), the
Hermes gateway (cron), the bunker hosts (QA batteries). Nothing outside writes the board or the
emulator except through the bridge's token.

## Invariants (each becomes a `check:` requirement)
- INV-1: ONE grid, ONE symbol set, ONE legend shared by RAM and vision. **Currently VIOLATED** (FACT-05/07).
- INV-2: the bridge is the single writer of emulator state; two drivers never overlap (FACT-26).
- INV-3: decision mode is explicit; a run never silently inherits an arm (FACT-10 shows a violation).
- INV-4: thresholds 0.50/0.40 are operator-fixed (FACT-09).
- INV-5: prompts describe how the game works, never the story.
- INV-6: the operator sees everything — panels self-refresh, nothing hidden (FACT-25).

## Non-goals
- Winning via RAM cheats or scripted walk sequences (agent must understand).
- Multi-game generality (Gen 1 Blue only).
- Hardening the console for public exposure (tailnet trust assumed).
- Voice control.

## Constraints
- Emulator is a frame stepper: nothing moves without inputs (60 fps needs a ticker).
- Vision cost: one reading ≈ 25k input tokens; prompt wording swings accuracy 32 points (FACT-13).
- Free-lane quota (xkiro) is shared fleet-wide; idle ticks consume it.
- QA batteries run on bunker hosts; disk admission gates launches.

## Success criteria (observable)
- S-01: agent reaches Viridian City without scripted steps — ACHIEVED (Sept run, FACT-20).
- S-02: agent reaches Pewter City gym — NOT STARTED (GOAL-2).
- S-03: RAM-vs-vision verdict agreement ≥ 80% on structure cells — best measured 72.2% (FACT-13).
- S-04: people identification ≤ 33% frame failure — currently 66.7% (FACT-14), FAILING.

## Surface inventory (measured 2026-11-11)
| Surface | Where declared | Flow |
|---|---|---|
| Bridge ops (13) | `game_bridge.py:324-362` | FLOW-01 |
| Console GET routes (`/`, `/api/state`, `/api/frame.png`, `/api/health`, SSE `/api/stream`) | `server.py:973-1046` | FLOW-02 |
| Console POST routes (`/api/press`, `/api/step`, `/api/vision`, `/api/live`, `/api/auto`, `/api/chat`, …) | `server.py:1046+` | FLOW-02 |
| Env knobs: `AIPP_DECISION_MODE`, `CRON_DECISION_MODE`, `AIPP_VISION_MODELS`, `AIPP_VISION_MODEL`, `AIPP_VISION_PROVIDER`, `CONSOLE_PORT`, `AIPP_VISION_MIN_GAP`, `AIPP_VISION_MAX_AGE` | `cron_runner.py`, `vision.py`, `server.py` | FLOW-01/02 |
| CLI: `cron_runner.py --run-id --cycles --boot-state --dry-run`; `long_run.py`; `game_bridge.py --token-file` | `cron_runner.py:711+`, `game_bridge.py:25` | FLOW-01 |
| Board JSONL `.coding-hermes/board/tasks.jsonl` | boardctl | FLOW-03 |
| Prometheus `/metrics/prometheus`, node_exporter textfile | MON-AIPP-1/2 | FLOW-03 |
| GitHub releases (v1.1.0) | releng | FLOW-03 |
