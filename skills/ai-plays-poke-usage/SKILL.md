---
name: ai-plays-poke-usage
description: >-
  How to actually USE the ai-plays-poke (PTP-01X) autonomous Pokémon AI system:
  the working E2E runner (cron_runner.py — re-verified 2026-08-26: 20/20 cycles,
  lock-rate 20%, 10 tiles, ~3 min, ~$0.35), the cron.sh wrapper (now genuinely
  runs cron_runner.py), --dry-run setup validation, the RAM map viewer (boots to
  overworld), cost expectations, JSONL output schema, and open P2 gaps
  (GAP-035..038).
version: 1.2.0
---

# Using ai-plays-poke (PTP-01X)

Autonomous Pokémon AI benchmarking system: PyBoy emulator + LLM decision loop
that plays Pokémon Blue/Red. Maintained by a coding-hermes foreman (board in
`.coding-hermes/board/tasks.jsonl`, JSONL canonical; `events.jsonl` for events).

## Entry points (verified 2026-08-26 by dogfood run)

| Path | Status | Use for |
|---|---|---|
| `python3 cron_runner.py --run-id <id> --cycles N` | ✅ **WORKS — re-verified 20/20 EXIT 0** | Real autonomous gameplay + benchmarking (fleet E2E fixture) |
| `python3 cron_runner.py --dry-run` | ✅ WORKS (GAP-032), bare python3 OK | Free setup validation — no boot, no LLM calls, exit 0 |
| `bash .coding-hermes/cron.sh --cycles N --run-id <id>` | ✅ WORKS (GAP-033 re-verified 5/5 EXIT 0) | Scheduled wrapper — genuinely invokes cron_runner.py now |
| `.venv/bin/python ram_map_server.py` → :8099 | ✅ WORKS — boots to **overworld** (Red's House 2F), /data.json full schema, / 200, bad path 404 | Live RAM-state viewer (read-only GET) |
| `python3 src/game_loop.py --rom <ROM> --max-ticks N` | 🟡 Legacy path (GAP-020/021/022/025 all complete per board; NOT re-verified 2026-08-26) | Legacy/simplified runs — prefer `cron_runner.py` |
| `PYTHONPATH=src .venv/bin/python -m src.ptp_cli \| src.debug_screen \| src.memory_reader --help` | ✅ works (AP-GAP-015/016/017) | Config / screen / RAM debug CLIs |

**Never judge this project by `src/game_loop.py`.** The working system is
`cron_runner.py` + `cron.sh` + the viewer.

## Quick start (working path — 2026-08-26 re-verified)

```bash
cd /home/kara/ai_plays_poke
source .venv/bin/activate          # deps installed; .env has API keys
python3 cron_runner.py --dry-run   # free check: ROM/boot-state/config summary, exit 0
python3 cron_runner.py --run-id demo1 --cycles 20
# ~3 min, ~$0.35 (20 LLM calls). Boots from data/boot.state = Oak's Lab, starter pre-picked
```

Outputs:
- `cron_logs/run_<id>.jsonl` — per-cycle JSON (screen, pipeline, plan, intent,
  controller_raw, player_x/y, map_name) + event rows (`starter_picked`,
  `state_saved`, `recovery`)
- `screenshots/run_<id>/step_000N.png` — 160×144 frames (one per cycle)
- Both gitignored — safe to leave in the tree.

## What a healthy run looks like (2026-08-26, 20 cycles)

```
[1/20] overworld | RAM reader x6 | 3.2s      ← 1 LLM call/cycle, gpt-5.6-luna
[STARTER-PICKED] party_count=1 species_hint=Charmander   ← from boot.state checkpoint
📡 API: openai/gpt-5.6-luna | 4976ms | In: 3208 | Out: 236 | $0.019580 | Success: True
[WARN] Direction-locking detected: UP x3     ← recovery ladder working (not a failure)
[STATE] Changed → overworld — recovery counter reset
[CKPT] Saved state to slot 1                 ← cycle 10 & 20 checkpoints
[dogfood_20260826_001] Done. 23 actions. Screens: {'overworld', '?', 'dialog'} | lock-rate: 4/20 (20%) | distinct tiles: 10
RUNNER_EXIT=0
```

**Acceptance bar (GAP-028):** lock-rate well under 50% (20% = healthy; 100% + 1
tile = direction-locked, refresh boot.state) and ≥2 distinct tiles. Player
position MUST change across cycles. Exit 0 alone proves nothing.

## Cost & time (verified 2026-08-26)

- ~$0.016–0.019 per overworld cycle (`openai/gpt-5.6-luna` via OpenRouter).
- 20 cycles ≈ 3 min wall, ~$0.35; 80 cycles ≈ 10–15 min, ~$1.40 (E2E evidence:
  T217 20/20 $0.40, luna_v16 80/80 $0.60/43 calls).
- Cost is on stdout (`📡 API: ... | $<cost>`), NOT in the JSONL.
- `deepseek-v4-flash` is the fallback/non-overworld model (StateWindow flow).

## Pitfalls (verified 2026-08-26)

1. `cron_runner.py --help` shows a stale docstring: "controller (DeepSeek V4
   Flash)" — the REAL overworld controller is `openai/gpt-5.6-luna`
   (cron_runner.py:857; trust `--dry-run` or the `📡 API:` lines, not --help).
   Open: GAP-035.
2. Run summaries print `Screens: {'overworld', '?', 'dialog'}` — `'?'` is the
   RAM-reader classifier's unknown bucket, undocumented. Not a crash. Open:
   GAP-036.
3. `--rom` override: `data/boot.state` is a Blue-SGB checkpoint; booting it into
   another ROM (e.g. `pokemon_red.gb`) loads mismatched RAM with no warning
   (only *.gba is guarded, in cron.sh). Use `--boot-state skip` for other ROMs.
   Open: GAP-037.
4. Default 20-cycle runs wander Oak's Lab (boot.state has the starter pre-picked,
   so the intro→starter journey is NOT reproducible on the default path; it was
   an artifact of the legacy intro bypass). No exploration goal → the run may
   never leave the room. Movement metrics still pass. Open: GAP-038.
5. `src/game_loop.py`: legacy path — all known gaps (GAP-020/021/022/025) are
   complete per board; NOT re-verified in the 2026-08-26 run. The 2026-08-16
   verification: boot progression + command wiring OK, battle recording gated,
   `model_name` real. `--multi-instance` raises NotImplementedError (stub).
6. `UserWarning: Using SDL2 binaries` on stderr is harmless.
7. `.env` holds API keys — never commit or copy it.
8. Pre-existing working-tree noise to leave alone: `data/duration_profiles.json`
   (modified), `dagger.db` (untracked).

## Verifying fixes (L3 standard)

- **cron_runner fixes:** run ≥ 20 cycles; require exit 0, movement (coords that
  CHANGE), lock-rate < 50%, `state_saved` events, and screenshots present.
- **cron.sh fixes:** `bash .coding-hermes/cron.sh --cycles 5 --run-id <id>` must
  show `cron_runner.py` output (RAM reader + lock-rate summary) and exit 0 —
  no `ModuleNotFoundError`.
- **--dry-run:** `python3 cron_runner.py --dry-run` (bare python3) exits 0 with
  config summary, no emulator boot, no API calls.
- **viewer fixes:** boot server, `GET /data.json` must show
  `screen_type=overworld` (NOT `name_entry`), player coords, map blocks.

## Board & fleet context

- Foreman ticks every 6 h (CooldownS=21600, fleet.toml pin); E2E-001 fixture
  runs cron_runner in windowed ticks (next due T222); NEVER-DONE runs a
  perpetual audit. All 49 real tasks complete as of 2026-08-26; open: E2E-001,
  NEVER-DONE, GAP-035..038 (P2, dogfood 2026-08-26).
- Board: `.coding-hermes/board/tasks.jsonl` + `events.jsonl` (canonical, git
  tracked; board.db/parquet are gitignored). Task rows are JSON objects, one per
  line, `id`/`title`/`status`/`priority`/`complexity`/... schema; event rows use
  `event_type`/`actor`/`detail`. To add findings: append rows + an event with
  `actor=dogfood` (see events 130/131/186 for the shape).
- Proven E2E evidence: T217 20/20 EXIT 0 (trainer battle c15→c17, BATTLE-003 win
  path, 26 API calls $0.40); dogfood 2026-08-16 20/20 (starter picked via intro
  bypass); dogfood 2026-08-26 20/20 (boot.state, lock-rate 20%, 10 tiles, $0.35).
