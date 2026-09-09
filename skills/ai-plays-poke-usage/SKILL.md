---
name: ai-plays-poke-usage
description: >-
  How to actually USE the ai-plays-poke (PTP-01X) autonomous Pokémon AI system:
  the working E2E runner (cron_runner.py), the cron.sh wrapper, --dry-run setup
  validation (presence-only — does NOT catch expired keys!), the RAM map viewer
  (boots to overworld), MANDATORY pre-run key verification (curl, 2026-09-09
  lesson), cost expectations, JSONL output schema, and open gaps
  (GAP-035..051 — incl. P0 GAP-047: dead-key runs still exit 0).
version: 1.3.0
---

# Using ai-plays-poke (PTP-01X)

Autonomous Pokémon AI benchmarking system: PyBoy emulator + LLM decision loop
that plays Pokémon Blue/Red. Maintained by a coding-hermes foreman (board in
`.coding-hermes/board/tasks.jsonl`, JSONL canonical; `events.jsonl` for events).

## ⚠️ STEP ZERO — verify API keys before ANY run (2026-09-09 lesson)

The runner does NOT fail when the LLM provider rejects every call — it prints
`Done.` and exits 0 after N cycles of zero real decisions (GAP-047). The
dry-run only checks key PRESENCE, not liveness (GAP-048). Always curl first:

```bash
source .env 2>/dev/null
# Controller key (openai/gpt-5.6-luna via OpenRouter) — MUST return a completion:
curl -sS -m 20 https://openrouter.ai/api/v1/chat/completions \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" -H "Content-Type: application/json" \
  -d '{"model":"openai/gpt-5.6-luna","messages":[{"role":"user","content":"say OK"}],"max_tokens":5}'
# Cheap alternative: curl -sS https://openrouter.ai/api/v1/key -H "Authorization: Bearer $OPENROUTER_API_KEY"
# Fallback/state-window key:
curl -sS -m 15 https://api.deepseek.com/chat/completions \
  -H "Authorization: Bearer $DEEPSEEK_API_KEY" -H "Content-Type: application/json" \
  -d '{"model":"deepseek-chat","messages":[{"role":"user","content":"say OK"}],"max_tokens":5}'
```

`{"error":{"message":"API key expired.","code":401,...}}` = DO NOT RUN — fix the
key first (rotating keys is an infra decision, not a repo fix). On 2026-09-09
the OpenRouter key was expired and every documented entry point still "passed".

## Entry points (verified 2026-09-09 by dogfood run)

| Path | Status | Use for |
|---|---|---|
| Key check (curl above) | ✅ **REQUIRED FIRST** | Catches expired keys that every in-repo check misses |
| `python3 cron_runner.py --run-id <id> --cycles N` | ⚠️ Pipeline works, **decision layer dead on expired key** — 20 cycles, 0/20 LLM success, still `Done.` + exit 0 (GAP-047) | Real autonomous gameplay — only after key check passes |
| `python3 cron_runner.py --dry-run` | ⚠️ WORKS but **presence-only key check** (GAP-048): passed on an expired key | Config/ROM/boot-state validation — never a key-liveness proof |
| `bash .coding-hermes/cron.sh --cycles N --run-id <id>` | ⚠️ Same runner inside — inherits GAP-047 | Scheduled wrapper — add key check upstream before trusting it |
| `.venv/bin/python ram_map_server.py` → :8099 | ✅ **WORKS — re-verified 2026-09-09** (`/` 200, `/data.json` 200 real map data Red's House 2F, bad path 404; needs NO API keys) | Live RAM-state viewer |
| `python3 src/game_loop.py --rom <ROM> --max-ticks N` | 🟡 Legacy path; NOT re-verified 2026-09-09 | Legacy/simplified runs — prefer `cron_runner.py` |
| `PYTHONPATH=src .venv/bin/python -m src.ptp_cli \| src.debug_screen \| src.memory_reader --help` | ✅ works (AP-GAP-015/016/017) | Config / screen / RAM debug CLIs |

**Never judge this project by `src/game_loop.py`.** The working system is
`cron_runner.py` + `cron.sh` + the viewer.

## What a DEAD run looks like (2026-09-09 — do not mistake for success)

```
Exception: OpenRouter API error 401: {'error': {'message': 'API key expired.', ...}}   ← x20, then:
Exception: Circuit breaker open - too many failures                                     ← x13
  [CACHE-HIT] frame 1e190af9 → ref a5653621d634 (seen 6x)   ← same frame forever
[dogfood_20260909_001] Done. 23 actions. Screens: {'unknown'} | lock-rate: 0/20 (0%) | distinct tiles: 1
RUN_EXIT=0                                    ← THE LIE: zero decisions happened
```

**A healthy run (2026-08-26 reference) looks like:**

```
[1/20] overworld | RAM reader x6 | 3.2s      ← 1 LLM call/cycle
📡 API: openai/gpt-5.6-luna | 4976ms | In: 3208 | Out: 236 | $0.019580 | Success: True
[dogfood_20260826_001] Done. Screens: {'overworld', '?', 'dialog'} | lock-rate: 4/20 (20%) | distinct tiles: 10
```

**Acceptance bar (GAP-028 + 2026-09-09 amendment):** count `Success: True` API
lines — a run with ZERO successful LLM calls is a failed run regardless of exit
code. Also require: lock-rate well under 50%, ≥2 distinct tiles, coords that
CHANGE across cycles, screenshots present. `Screens: {'unknown'}` +
`distinct tiles: 1` + all-`[CACHE-HIT]` = dead run (GAP-047).

## Quick start (working path)

```bash
cd /home/kara/ai_plays_poke
source .venv/bin/activate          # deps installed; .env has API keys
# 1) curl key check (STEP ZERO above) — BOTH keys
python3 cron_runner.py --dry-run   # config check — ROM/boot-state/pipeline only
python3 cron_runner.py --run-id demo1 --cycles 20
# ~3 min, ~$0.35 when keys are live. Boots from data/boot.state = Oak's Lab, starter pre-picked
```

Outputs:
- `cron_logs/run_<id>.jsonl` — per-cycle JSON (screen, pipeline, plan, intent,
  controller_raw, player_x/y, map_name) + event rows; on dead runs each cycle
  carries the full Python traceback of the failed call (grep for `401`).
- `screenshots/run_<id>/step_000N.png` — 160×144 frames (one per cycle)
- Both gitignored — safe to leave in the tree.

## Cost & time (verified 2026-08-26, keys live)

- ~$0.016–0.019 per overworld cycle (`openai/gpt-5.6-luna` via OpenRouter).
- 20 cycles ≈ 3 min wall, ~$0.35; 80 cycles ≈ 10–15 min, ~$1.40.
- Cost is on stdout (`📡 API: ... | $<cost>`), NOT in the JSONL.
- `deepseek-v4-flash` is the state-window model. NOTE (GAP-049): a valid
  DeepSeek key does NOT help the controller — `openai/gpt-5.6-luna` is
  hardcoded (cron_runner.py:905), no flag/env override exists yet.

## Pitfalls

1. **Phantom-green on dead keys (GAP-047, P0):** expired/invalid
   OPENROUTER_API_KEY → every cycle fails (401 → retries → circuit breaker),
   run still prints `Done.` and exits 0. cron.sh/scheduler/E2E wrappers read
   that as success. Judge runs by the acceptance bar above, never exit code.
2. **Dry-run proves presence, not liveness (GAP-048):** `API keys:
   OPENROUTER_API_KEY=set` + `Validation OK` + exit 0 happened with a key that
   401'd on every real call. Only the curl check catches it.
3. **Single-provider hard dependency (GAP-049):** controller model hardcoded
   (cron_runner.py:905). DeepSeek key valid but unusable as controller → one
   expired provider key zeroes the whole run.
4. PyBoy native noise on stderr at every emulator boot: `Special Game Boy
   color command: 0xe000!` / `Unknown SGB packet sent!` (~10 lines; also in
   ram_map_server). Harmless but clutters output (GAP-050).
5. `src/game_loop.py`: legacy path — all known gaps (GAP-020/021/022/025)
   complete per board; NOT re-verified recently. `--multi-instance` raises
   NotImplementedError (stub).
6. `UserWarning: Using SDL2 binaries` on stderr is harmless.
7. `.env` holds API keys — never commit or copy it.
8. Pre-existing working-tree noise to leave alone: `data/duration_profiles.json`
   (modified), `dagger.db` (untracked) — tracked on the board as QA rows.
9. `--rom` override: `data/boot.state` is a Blue-SGB checkpoint; use
   `--boot-state skip` for other ROMs (GAP-037).
10. Default 20-cycle runs wander Oak's Lab; reaching Route 1 needs ≥80 cycles
    and is LLM-dependent (GAP-038).

## Verifying fixes (L3 standard)

- **cron_runner fixes:** key-check curl first; run ≥ 20 cycles; require >0
  `Success: True` lines, movement (coords CHANGE), lock-rate < 50%,
  `state_saved` events, screenshots present, exit 0.
- **Exit-code fix (GAP-047):** force a dead key (e.g. `OPENROUTER_API_KEY=dead
  python3 cron_runner.py --cycles 2`) → must exit ≠ 0 and print LLM fail
  counts; healthy run still exits 0.
- **cron.sh fixes:** `bash .coding-hermes/cron.sh --cycles 5 --run-id <id>`
  must show cron_runner output and exit 0 — no `ModuleNotFoundError`.
- **--dry-run fix (GAP-048):** expired key → dry-run exits ≠ 0 quoting the
  provider error; add `--skip-key-check` escape hatch for offline use.
- **viewer fixes:** boot server, `GET /data.json` must show
  `screen_type=overworld`, player coords, map blocks.

## Board & fleet context

- Foreman `ai-plays-poke` cooldown 21600s; QA crons flagged it idle since
  2026-09-03 (QA-AI-PLAYS-POKE-3). Open work 2026-09-09: E2E-001, NEVER-DONE,
  GAP-043/045/046, DEPS-003/004, DOC-1/2, CLN-1, QA-AI-PLAYS-POKE-1..5,
  **GAP-047..051 (dogfood 2026-09-09 — GAP-047 is P0)**.
- Board: `.coding-hermes/board/tasks.jsonl` + `events.jsonl` (canonical, git
  tracked; board.db/parquet are gitignored derived caches — foreman resyncs).
  Append rows + an event with `actor=dogfood` (see events 186 and 221).
- Proven E2E evidence: T217 20/20 EXIT 0 (trainer battle, $0.40); T227
  (2026-08-27) 20/20, 24/24 API success, lock-rate 30%, 13 tiles; dogfood
  2026-08-26 20/20 ($0.35). 2026-09-09: 0/20 API success (expired key) —
  first post-T227 live-LLM evidence.
