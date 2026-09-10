# Dogfood Integration Report — 2026-09-09b (second run same day: P0 retest + bunker retry)

**Runner:** dogfood cron (ai-plays-poke-qa pick)
**Repo HEAD at start:** `918d21c` ("foreman tick [ci skip]")
**Verdict:** 🟡 PROMISING-BUT-ROUGH (unchanged from morning run)
**Purpose of this run:** the morning run (2026-09-09, GAP-047..051) found the P0
dead-key phantom-green and skipped the bunker install leg (host down). This run
re-tested the P0 six hours later and retried the install leg on a live host.

## Promise under test

> "A user can run `python3 cron_runner.py --run-id X --cycles N` and watch an
> LLM-driven AI autonomously play Pokémon, validate setup free with `--dry-run`,
> and a fresh user on a clean machine can install and run it from the README."

## What was actually done (real use, not tests)

### 1. Key liveness (STEP ZERO per skill v1.3.0)

| Key | Method | Result |
|---|---|---|
| `OPENROUTER_API_KEY` | `GET /api/v1/key` | **401 Unauthorized — still expired** (6h after GAP-047) |
| `DEEPSEEK_API_KEY` | real `POST /chat/completions` | **LIVE** (served `deepseek-flash`) |

The foreman committed twice since the morning finding (`5782cff` 17:42,
`918d21c` 18:29) — neither touched GAP-047. The P0 is still open with no owner
movement.

### 2. `--dry-run` (local, true exit code captured without pipes)

`VALIDATION OK — exiting 0` **on the dead key** (GAP-048 reconfirmed: presence-
only check). On the bunker the same command correctly exits **1** on a missing
ROM — so the exit-code mechanism itself works; it just doesn't check keys.

### 3. Real 20-cycle run (`dogfood_20260909b_001`)

- Wall ~19s, **exit 0**, `Done. 23 actions.` — **phantom-green reproduced**
  (GAP-047). Circuit breaker opened ("Circuit breaker open - too many
  failures" ×20), `Screens: {'unknown'}`, **1 distinct tile**, 0 lock warnings.
- JSONL re-parse: 20 cycle rows with **zero `llm_status` fields**, events only
  `starter_picked` (boot baseline) + 2 `recovery`. No successful LLM call.
- The "23 actions" are **`parse_fallback` plan `["A"]` blind A-presses**
  (cron_runner.py:932/946) counted as actions in the summary → new GAP-053.

### 4. Library-consumer probe of the DeepSeek escape lane (NEW)

`OpenRouterClient.chat_completion(model="deepseek-chat", ...)` outside the
runner (`/tmp` scratch consumer, project venv):

- **HTTP lane works:** 707 ms, `Success: True`, billed **$0.000255**
  (routing at src/core/ai_client.py:533-536 → api.deepseek.com + live key).
- **Content corrupt:** response content was `{"ok":<|endoftext|> true}` —
  DeepSeek emits `<|endoftext|>` **inline inside JSON content**;
  `json.loads` fails → `controller_plan` falls into `parse_fallback` →
  blind A-presses. So even a user who discovers the hardcoded-model problem
  (GAP-049) and reroutes to the live provider hits content corruption
  → new GAP-052.

### 5. RAM map viewer (keyless path — works)

`ram_map_server.py`: `GET /` → 200, `GET /data.json` → 200 (real map data:
"Red's House 2F", map_id 38, blocks/minimap arrays), `GET /nope` → 404.
Needs **no API keys** — the only entry point fully healthy today.

### 6. Bunker fresh-install leg (las-bunker-03 — RETRY, now PROVEN)

Host was down this morning (GAP-051 skip). This run:

1. `ssh bunker3` reachable; `bunkerd` active; Docker 26.1.5.
2. Server was **not registered** in the local bunker config and the skill-doc
   port (19090) is wrong — bunkerd listens on **10001/10002** (skill-doc drift,
   filed to the dogfood skill, not this repo). Re-registered with the box's own
   token (read over root SSH, kept out of all artifacts).
3. Spawned agent `e7a34e37` (2h TTL).
4. `git clone https://github.com/wojons/ai_plays_poke.git` — **succeeded as a
   fresh anonymous user** (public repo), HEAD `918d21c`.
5. Documented install path: `python3 -m venv .venv && pip install -r
   requirements.txt` → **rc=0 in 98s**. No system packages needed (PyBoy/SDL2
   wheels self-contained on Python 3.13.5 Debian).
6. Documented smoke (`--dry-run`): **exit 1, "ROM not found"** — honest
   failure; `data/rom/` ships a README listing ROMs but no ROM (→ GAP-054).
   `data/boot.state` IS in-repo (167,677 bytes).
7. `bunker destroy e7a34e37` → **destroyed**, 0 agents left.

**GAP-051's unproven-install concern is resolved: installability is PROVEN**
(clean 98s install, zero system deps). The remaining gap is the ROM wall →
GAP-054.

## Friction ledger (this run)

| # | Friction | Sev | Task |
|---|---|---|---|
| 1 | OpenRouter key still expired; all success signals lie (exit 0, `Done.`, dry-run OK) | P0 (open, GAP-047) | GAP-047 |
| 2 | Only working LLM provider unreachable: model hardcoded + `<\|endoftext\|>` JSON corruption on the DeepSeek lane | P1 | **GAP-052** |
| 3 | `parse_fallback` A-presses inflate the summary ("23 actions" from 0 decisions) | P2 | **GAP-053** |
| 4 | Fresh user hits an undocumented ROM wall after a clean install | P2 | **GAP-054** |

## Time-to-first-success

- LLM-driven gameplay: **never** on this deployment (dead key, no override).
- Keyless viewer: ~40 s (server boot) — works.
- Fresh install to honest dry-run on bunker: **~2 min** (clone 12s + install 98s
  + dry-run 2s).

## What to fix first (1 hour of maintainer time)

1. Key-liveness check in `--dry-run` + nonzero exit on dead key (GAP-047/048) —
   it converts every silent dead-key run into a loud one.
2. `--controller-model` flag + `<|endoftext|>` strip (GAP-052) — unlocks the
   live DeepSeek provider immediately.
3. ROM path documentation (GAP-054) — ten README lines.
