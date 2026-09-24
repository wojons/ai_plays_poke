# Dogfood Integration Report — 2026-09-24 (ai-plays-poke-pm lane)

**Angle:** past dogfood runs swept the CLI/cron surface (08-07, 08-16, 08-26,
09-09, 09-09b) and the memory layer (09-23). This run took the surface those
runs never touched with real use: **the JEV / PRD-v3 decision tier that the
board claims is done** (JEV-1/2/4 all `complete`, merged 09-23/09-24).

**Promise tested:** "A run's decisions are made by the JEV tier (System One,
~$0.00006/decision) with a hand-back gate that escalates to the teacher, and
every run reports honest autonomy counters (AC-1) — the de-hardcoded starter
(JEV-routed, AC-2) and battle decisions (AC-3) are live."

**Reality:** the *instruments* all work; the *loop* doesn't use them.
Two fresh 20-cycle runs (keys verified live first — the 09-09 lesson):
autonomy `0/16` both times. The overworld decision is still
`controller_plan()` (Luna); the rows that feed the autonomy counters read
payload keys the controller never sets. The teacher is unreachable from the
game loop (single caller = probe script) and dead at the API anyway: its
500-token budget is eaten entirely by reasoning tokens. Battles still run
through the StateWindow's `select_move(1)` loop. PRD v3 stages 5-8 are
"PROVEN" only via `scripts/jev_projection_probe.py`, which is a harness, not
the game.

What *is* genuinely good: the underlying runner is healthy and the probe
harness is excellent — the same numbers the board asserts were re-provable
from a real checkpoint in one command.

## What was done (real use, not tests)

1. **STEP ZERO key liveness** (curl `/api/v1/key`): OPENROUTER_API_KEY live
   (limit_remaining $49.99), DEEPSEEK_API_KEY live. `.venv/bin/python
   cron_runner.py --dry-run` → `Validation OK`, rc=0 — its new liveness
   precheck (GAP-048 fix) correctly probes both keys.
2. **Run A** `dgf_0924_pm --cycles 20` → exit 0, 20/20 cycles, 25/25 API
   success (16 Luna overworld + 9 deepseek battle-window), 10 distinct tiles,
   lock-rate 30%, printed cost ≈ $0.42, boot-memory injection fired (423
   chars). `run_autonomy` row: `jev_answered: 0, decisions_total: 16,
   autonomy_ratio: 0.0, teacher_escalations: 0`.
3. **Run B** `dgf_0924_warm2 --cycles 20` (warm) → 62s wall, 26/26 success,
   8 tiles, lock-rate 5%, ≈ $0.4198. Same autonomy row shape: 0/16.
4. **JEV live probe** (the project's own harness, real checkpoint):
   `scripts/jev_projection_probe.py data/boot.state` → ok=True,
   model=typesafe/jev-1.13-20260917, 0.41s, $0.000064, correct typed answers,
   gate escalates on "failure: last action changed nothing". The client and
   gate genuinely work.
5. **Teacher escalation probe** (`--escalate`, 6 live attempts): **5/6
   failed** — `"error": "teacher response contained no JSON object"`, two
   with empty content, three with truncated JSON. One attempt succeeded
   end-to-end (patch ok → re-ask sufficient_state 0.37 → 0.60-class
   improvement, $0.00105) — proving the *pipeline* is right and the *call
   shape* is wrong.
6. **Root cause isolated outside the repo** (direct OpenRouter call, same
   prompt shape): `finish_reason: length`, `content: ""`,
   `usage.completion_tokens_details.reasoning_tokens: 500` — **the model
   spends the whole budget on reasoning tokens**. Same request with
   `thinking={"type":"disabled"}` + same budget: 3/4 parse. With disabled +
   bigger budget: 4/4. The controller path already disables thinking
   (cron_runner.py retry, :1574); `request_patch()` does not
   (src/core/teacher_client.py:249).
7. **Bunker fresh-install leg** (bunker-las-03, agent 7a941edf, destroyed
   after): clone from GitHub origin (public) + `python3 -m venv .venv` +
   `pip install -r requirements.txt` = **33s, zero system deps** (better
   than the 54s/98s prior runs — PyBoy wheels cached upstream now).
   Documented `--dry-run` smoke: honest fail on the ROM wall (rc=1, names
   the exact ROM path) — no silent pass. Fresh-tree `pytest --collect-only`
   exits 0 (QA-AI-PLAYS-POKE-7's conftest fix verified on a third box).
8. **Perf (headline operation, warm + cold):** warm 20-cycle run = **62s**
   (~3.1s/cycle, of which ~2.5s is LLM latency); cold-boot cycle 1 = 7.1s;
   fresh install = 33s. Nothing user-noticeable is slow → no PERF row beyond
   these headline numbers.

## The working example (for the next agent)

```bash
cd ~/ai-plays-poke && source .venv/bin/activate
# 0) key liveness FIRST (curl /api/v1/key) — dry-run presence checks lie (GAP-048)
.venv/bin/python cron_runner.py --dry-run            # config + key liveness, rc=0
.venv/bin/python cron_runner.py --run-id demo1 --cycles 20
# Judge by the acceptance bar in skills/ai-plays-poke-usage, never exit code:
#   count Success:True lines, tiles>2, lock-rate<50%, coords change.
# JEV tier alone (works today, ~$0.00006/decision, 300-770ms):
.venv/bin/python scripts/jev_projection_probe.py data/boot.state
.venv/bin/python scripts/jev_projection_probe.py data/boot.state --escalate  # teacher
# Autonomy truth of ANY run:
jq -c 'select(.event=="run_autonomy")' cron_logs/run_<id>.jsonl
grep -c '"jev_answered": true' cron_logs/run_<id>.jsonl   # 0 today, see DF-JEV-1
```

## Frictions hit (all filed on the board — DF-JEV-1..5)

| # | Sev | One line |
|---|-----|----------|
| DF-JEV-1 | P1 | JEV tier not wired into the loop: autonomy 0/16 on every real run while JEV-1/2/4 sit complete |
| DF-JEV-2 | P1 | Teacher dead at API (reasoning tokens eat 500-token budget, no thinking-disable) AND unreachable in-game |
| DF-JEV-3 | P1 | AC-3 battle observable absent: battles run through StateWindow select_move(1), not the JEV battle vocabulary |
| DF-JEV-4 | P2 | Cost telemetry is the gpt-4-era default pricing table for every model actually used ($0.012 printed for a ~$0.0003 deepseek call) |
| DF-JEV-5 | P3 | Bare `python3 cron_runner.py --help` dies on numpy — only --dry-run gets the import-light precheck |

## Time-to-first-success

- Working path (cron_runner 20-cycle run): ~2 min warm (dry-run 5s + 62s run).
- JEV tier via probe: ~40s (one command, real checkpoint).
- Teacher: reachable only via probe, and then 5/6 dead → effectively never
  for a new user following PRD v3's story.

Friction count: 5 (3×P1, 1×P2, 1×P3), none blocking the *legacy* gameplay
path, all blocking the *v3* story the board says is done.
