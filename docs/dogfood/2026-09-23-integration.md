# Dogfood Integration — 2026-09-23 (MEM layer, real use)

**Angle:** the memory layer (MEM-1 recorder + MEM-2 boot injection, merged 2026-09-23)
exercised as a real user, not via tests. Past dogfood runs (08-07/16/26, 09-09, 09-09b)
covered CLI/cron/install; this is the first real USE of the memory circuit.

## Promise tested

> A user can run autonomous Pokémon gameplay (`cron_runner.py`) whose controller boots
> with memory from previous runs (MEM-2) and records run truth to DuckBrain for future
> runs (MEM-1).

## How to reproduce this exact run

```bash
cd <repo> && source .venv/bin/activate
# Step zero (the 09-09 lesson): verify the controller key BEFORE any run
curl -s https://openrouter.ai/api/v1/models -H "Authorization: Bearer $(grep -oP '(?<=OPENROUTER_API_KEY=).*' .env)" | head -c 40

python3 cron_runner.py --run-id dgf_a --cycles 20   # run A (cold boot ~107s)
python3 cron_runner.py --run-id dgf_b --cycles 20   # run B (warm boot ~32s)
# then inspect the store:
jq -r '.key' ~/duckbrain/namespaces/pokemon-global/data/memories-$(date +%F).jsonl | sort | uniq -c
```

## What worked (verified live)

1. **MEM-1 write path** — after each run, `~/duckbrain/namespaces/pokemon-global/data/`
   gained `/game/runs/<id>/summary` (with ladder + log_path), `/game/save/party`
   (party_count 1, species Charmander), `/game/save/location`, and an updated
   rolling `/game/runs/index` (last-10). Verified by reading the JSONL, not by test.
2. **MEM-2 cross-run injection** — run B printed `[MEM] boot injection: 322 chars
   across 5 block markers`; re-building the blocks by hand rendered:
   `[SAVE] party: 1 party member(s); first species Charmander` + location +
   `[RUN HISTORY] dgf_0923a … map=Oak's Lab, starter=yes`. Run A (booted before any
   of today's writes) correctly injected nothing — fresh-store placeholder behavior.
3. **Runs are healthy** — both 20-cycle runs: exit 0, battles fought and won, 11-12
   distinct tiles, lock-rate 15-30%, ~$0.42-0.45 per run (27 LLM calls each).

## What does NOT work (findings → board DF-AIPP-1..6)

| Finding | Evidence |
|---|---|
| `memory_events` always 0 in run ladder | run B wrote 2 goals + 1 note live; ladder recorded 0; event dicts go to `log_file` but never to `results` (cron_runner.py:2299-2338 vs counter at :1048). Also kills `/game/runs/<id>/lessons`. |
| `battle_events` double-counted | ladder=6 on run B for 2 real battles (nested lists + top-level rows both counted; cron_runner.py:1037-1044). |
| MECHANICS/LEARNING boot layers have no writer | prompt tells the agent `study → /game/mechanics/*`; the study handler only READS. Nothing in the repo writes either layer — they are permanently empty outside tests. |
| PRD vs code drift | PRD R3 says ns `ai-plays-poke`, save keys quests/acquired; code uses `pokemon-global` and writes party/items/location only (`[MEM] save items skipped: no public item reader` every run). |
| `scripts/marathon_driver.py` is gone | referenced by skills as "repo scripts/marathon_driver.py"; absent from every commit (676 scanned) and worktree. Its 330 `/game/save/current` records (through 09-19) are unread by MEM-2. |
| Fresh-install ROM wall | bunker leg: 54s install, zero system deps — but a fresh clone cannot run the headline workflow (ROM not in repo, no obtain instructions in Quick Start). `--dry-run` fails honestly (exit 1), which is the one good behavior here. |

## Errors hit, and their fixes

- `bunker exec` avoided for long legs (stream deadlines) — used direct ssh per skill.
- First `jq` one-liner errored on non-string keys (`.key` is null on some rows) —
  not a store bug; the JSONL has heterogeneous rows from different writers.
- The `python3 -c` / heredoc shell patterns are blocked on unattended surfaces —
  scripts written to /tmp and run with the repo venv python instead.

## Numbers (perf, from real use)

| Metric | Value |
|---|---|
| Cold boot (venv + PyBoy + state load → first decision) | ~107s |
| Warm boot → first decision | ~32s |
| Warm run, 20 cycles wall | ~2min (~6s/cycle incl. 3-6s LLM latency) |
| LLM cost per 20-cycle run | $0.42-0.45 (27 calls: ~14 overworld @ $0.016-0.020 + 13 battle @ $0.012-0.017) |
| Fresh install (bunker, clone+venv+pip) | 54s |

Nothing was slow enough that a user would notice, beyond the one-time cold boot and
the ROM wall — so no separate PERF row; the numbers live here and in the DF rows.

## The right way (as of this run)

1. Verify keys live before ANY run (`curl /models`).
2. Judge runs by: exit 0 AND lock-rate < 50% AND ≥2 distinct tiles AND coords changing.
3. Judge the memory circuit by reading the DuckBrain JSONL — never trust the ladder
   numbers until DF-AIPP-1/2 land (memory_events is always 0; battle_events inflated).
4. MEM-2 injection only shows itself with `[MEM] boot injection: N chars` at run start.
   Absent line = empty store (or the four BOOT keys are absent) — not necessarily a bug;
   check the store before filing.
5. Boot memory namespaces: code lives in `pokemon-global` (cron_runner.py:1209);
   PRD R3 says `ai-plays-poke`. Trust the code until the PRD row (DF-AIPP-4) closes.