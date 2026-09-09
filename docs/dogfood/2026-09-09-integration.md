# Dogfood Integration Report — 2026-09-09 (ai-plays-poke / PTP-01X)

**Run:** cron-selected field test, ~40 min real use. Verdict:
**🟡 PROMISING-BUT-ROUGH** (down from ✅ SHIPPABLE on 2026-08-26 — not because
code regressed, but because the deployment's OpenRouter key expired and every
in-repo success signal is key-blind).

## Promise under test

"A user can run `python3 cron_runner.py --run-id <id> --cycles N` and watch an
LLM-driven AI autonomously play Pokémon (RAM-reader state, real OpenRouter
decisions, recovery, checkpoints, JSONL + screenshots), validate setup free
with `--dry-run`, and watch live RAM state in the browser viewer."

## What I actually did

1. **Step-Zero key probes (manual, since nothing in the repo does it):**
   - `curl https://openrouter.ai/api/v1/key` → `401 "API key expired"` —
     the `.env` OpenRouter key is DEAD.
   - `curl api.deepseek.com/chat/completions` (deepseek-chat) → real
     completion (`"OK"`), DeepSeek key LIVE.
2. **`python3 cron_runner.py --dry-run`** → exit 0 in <1 s: ROM OK, boot.state
   OK, pipeline RAM reader, `controller=openai/gpt-5.6-luna (OpenRouter)`,
   `API keys: OPENROUTER_API_KEY=set` — passed on the expired key
   (presence-only check).
3. **Real run:** `cron_runner.py --run-id dogfood_20260909_001 --cycles 20` →
   EXIT 0 in **19 s** (vs ~3 min when decisions happen):
   - Every controller call failed: 20× `OpenRouter API error 401: API key
     expired` → retries exhausted → 13× `Circuit breaker open - too many
     failures`.
   - Final line: `Done. 23 actions. Screens: {'unknown'} | lock-rate: 0/20
     (0%) | distinct tiles: 1` — **phantom-green**. Zero decisions, zero
     movement, exit 0. (GAP-047)
4. **RAM map viewer:** `ram_map_server.py` → `GET /` 200, `GET /data.json` 200
   with real map data (`Red's House 2F`, map_id 38, 4×4 blocks with
   block_types), `GET /nonexistent` 404. Boots via the legacy intro bypass
   (name-entry auto-driver), needs **no API keys**. Still fully working.
5. **Bunker install leg:** las-bunker-03 (100.69.3.13) UNREACHABLE — ssh
   connect timeout ×2 (bunker3 + bunker-las-03 aliases), ping 100% loss;
   local `bunker 0.1.3` healthy, so it's host-side. Per skill contract:
   **SKIPPED-install-bunker** filed as GAP-051, never a silent pass.

## The three-layer read

- **L1 (code runs):** ✅ — emulator boots, RAM reader classifies (into
  `unknown` here), frames captured, JSONL + screenshots written, checkpoints
  logic intact.
- **L2 (it works mechanically):** ⚠️ — pipeline executes; but the only paid,
  decision-bearing leg is dead, and the machine-facing success signals
  (exit code, `Done.`, dry-run OK) all report green.
- **L3 (it works for a user):** ❌ for the headline promise — a user who
  follows the README Quick Start gets a 19-second run that plays nothing and
  tells them it succeeded. The cure is a valid key + (missing) liveness check.

## Friction log (all evidence-backed)

| # | Friction | Sev | Task |
|---|---|---|---|
| 1 | Dead key → `Done.` + exit 0, 0/20 LLM success | P0 | GAP-047 |
| 2 | `--dry-run` checks key presence, not liveness | P1 | GAP-048 |
| 3 | Controller model hardcoded (valid DeepSeek key unusable) | P1 | GAP-049 |
| 4 | PyBoy SGB native log spam on every boot | P2 | GAP-050 |
| 5 | Install leg unprovable; native prereqs undocumented | P2 | GAP-051 (SKIPPED-install-bunker) |

Time-to-first-success: **never, for the LLM promise** (blocked by deployment
key, unverifiable by any in-repo check). For the viewer: **~20 s** (boot +
first GET). Friction count: 5.

## What still works (be fair to the project)

- Viewer E2E: boot → overworld → live JSON, no keys needed.
- Emulator/RAM-reader/capture/JSONL machinery: all executed cleanly.
- Dry-run, logs, screenshots, checkpoint paths: correct formats.
- Docs (README Quick Start, docs/api/cron_runner.md, skill) are accurate
  about *how* to run — they just can't detect *dead credentials*.

## What I'd fix first with one hour

1. GAP-047: fail the run (≠0) when successful LLM calls == 0 + add LLM
   success/fail counts to the summary line. (Small, kills the phantom-green
   for every wrapper.)
2. GAP-048: liveness probe in dry-run.
3. Rotate the OpenRouter key (infra, outside the repo).
