# ai_plays_poke — dogfood integration report, 2026-10-27

Tick `ai-plays-poke-dogfood-2026-10-27-15-09-28`
Canonical repo `/home/kara/ai_plays_poke`, HEAD `2d75ced1bc5c9f93d8427ac83401389a7e0c7da5` (== origin/main, 0 unpushed).
Executor: the dogfood lane itself (the `dogfood-scheduler-tick.sh` / `dogfooding.ts` driver is retired).

## Verdict

**PROMISING-BUT-ROUGH (re-use) / install PROVEN.** The documented path works end to end: an 80-cycle
run finished `rc=0` in 49.40 s, the fresh-install leg cloned and installed from scratch on a clean
box in ~23 s with zero apt prerequisites, and every closed dashboard row I re-drove still holds.
What is rough is not the plumbing but the *agent's behaviour*: the default (`jev`) arm spends the
last 49 of 80 cycles pinned to two tiles inside Red's House 1F, and the teacher repair path is
blocked 78 times out of 80 by a per-run dedupe.

## 1. How to use it for real (the working path)

```bash
cd <repo>; source .venv/bin/activate          # or .venv/bin/python
python3 cron_runner.py --dry-run                # validation only, no emulator, no LLM
python3 cron_runner.py --dry-run --skip-key-check   # fully offline validation
python3 cron_runner.py --run-id demo1 --cycles 80   # the real thing
```

Real prerequisites a fresh user trips over:

- ROM is **not** bundled. `data/rom/Pokemon - Blue Version (USA, Europe) (SGB Enhanced).gb` must be
  your own dump, otherwise `--dry-run` is `rc=1` with
  `[DRY-RUN] ERROR: ROM not found at ... Fix: you must own the game; place your own dump at ...`.
  That failure is honest and actionable — it is *not* a defect, but note README §"System
  prerequisites" claims the same dry-run is `exit 0`, which only holds when the ROM is already present.
- `OPENROUTER_API_KEY` in `.env` for the controller; `DEEPSEEK_API_KEY` is the optional fallback lane.

Outputs: `cron_logs/run_<id>.jsonl` (one row per event/cycle) and `screenshots/run_<id>/step_NNNN.png`.

## 2. Measured (Step 2b — numbers, not impressions)

| operation | command | warm | cold |
|---|---|---|---|
| validation, offline | `.venv/bin/python cron_runner.py --dry-run --skip-key-check` | 0.11 s (rc=0) | 0.11 s first run |
| validation + key liveness | `... --dry-run` | 1.15 s (rc=0) | — |
| **headline: real gameplay** | `.venv/bin/python cron_runner.py --run-id df1027a --cycles 80` | **49.40 s rc=0 = 0.62 s/cycle** | n/a (one-shot) |
| per-cycle fast path | (inside the run) | ~0.36 s/cycle | — |
| teacher repair (LLM) | 2 calls in the run | 12.05 s / 8.79 s ($0.0015 / $0.0016) | — |
| dashboard routes | `curl` on scratch port 8791 | 0.7–1.3 ms | — |

`time -p`: real 49.40, user 4.44, sys 0.34 — the run is wall-bound on LLM calls, not CPU-bound.
**No PERF row was filed:** the per-cycle path is fast and unchanged since 2026-10-23 (0.58 → 0.62 s/cycle,
noise), and the only large stall is the teacher call, already owned by PERF-2 (closed `8c24d6cc`) and
provider-bound (one `gpt-5.6-luna` patch request). Nothing here is slow enough that a user should act
differently — the problem with this run is progress, not speed.

## 3. What actually happened (run `df1027a`, 80 cycles)

- Boot: `data/boot.state` (md5 `81e4ec4e8d1b62002bc78f619c5fc79c` = `data/baselines/boot_state_pin.json`),
  "skipping intro bypass". **Cycle-1 live ROM topology: map 0 Pallet Town, tile (6,6)** — outside the
  house. (README says Oak's Lab, map 0x28, tile ~(4,4): filed as DF-AIPP-18.)
- Map occupancy over 80 cycles: Pallet Town 2, Red's House 1F 76, Red's House 2F 2. Three transitions:
  Pallet Town→1F at cycle 3, 1F→2F at cycle 22, 2F→1F at cycle 24 (`regression: true`) — and never out again.
- **Treadmill:** cycles 32–80 (49 consecutive cycles) record only tiles (7,6) and (6,6) of map 37;
  cycles 36–80 emit single-direction plans from `{LEFT, RIGHT}` only. The last plan containing `DOWN`
  is cycle 31 of 80. The door the agent must cross is at (5,6) — one tile from where it oscillates.
- `run_autonomy`: autonomy_ratio 0.925 (74/80 jev), transport failures 0, backtrack_events 62
  (backtrack_rate 0.785), 3 map transitions (26.67 decisions/transition), nav-mem 6 hits / 37 fallbacks,
  teacher 2 escalations (1 improved).
- **Handoff delivery:** `handoff_trigger_counts {gap 44, failure 29, confidence 6, other 1}` = 80 triggers,
  `handoff_blocked 78`, 2 deliveries. Every block now carries a reason: `missing_class 'map_topology'
  already escalated this run` ×45, `missing_class 'none' already escalated this run` ×27,
  `navigation gap answered by path memory ...` ×5, `trigger 'other' not in [...]` ×1.

Two rails compose the trap, and they are filed separately because either fix alone is insufficient:

| row | rail | evidence |
|---|---|---|
| DF-AIPP-13-R2 (P1, RECUR of DF-AIPP-13 whose fix `6067427` **is** an ancestor of HEAD) | teacher **delivery**: per-run per-class dedupe blocks 78/80 triggers, so a repair that does not resolve the state is never retried | trigger census + `handoff_blocked_reason` x80 |
| DF-AIPP-17 (P1, new) | route **legality**: `reverse_edge_guard` forbids the only exit from a dead-end map (DOWN to Pallet Town) while the nav planner only plans to *unvisited* maps | `navigation_hold_guard` cycles 8/11/12 (`replacement_direction: UP` — into a wall), `memory_navigation_step_suppressed` at (37,3,6) with `forbidden_directions [DOWN, UP]`, NAV-MEM `no_proven_route_to_unvisited_map` every cycle |

The honest reading of the summary line is worth recording: it prints
`autonomy=74/80 (2 escalated) ... movement-progress: 49/79 comparable cycles changed tile (62%)`,
neither of which reveals that 78 handoffs were blocked and that 49 cycles were spent on two tiles.
The movement observable counts *tile changes*, and a two-tile oscillation changes tiles.

## 4. Fresh-install leg (bunker-mvp, agent `df-aipp-1027`)

Clean Ubuntu 24.04.4 / Python 3.12.3 box, clone-equivalent from `https://github.com/wojons/ai_plays_poke`
at HEAD `2d75ced`:

| step | result |
|---|---|
| `git clone --depth 1` | rc=0, 1 s |
| `python3 -m venv .venv` | rc=0, 4 s |
| `pip install -r requirements.txt` | rc=0, 18 s — PyYAML 6.0.3, pyboy 2.7.0, anthropic 2.3.0, fastapi 0.162.0, numpy 2.5.4, opencv-python-headless 5.0.0.93, Pillow 13.0.0 |
| `python3 cron_runner.py --dry-run` | **rc=1 HONEST** — ROM missing, path named, fix line printed, zero LLM calls |
| `.venv/bin/python cron_runner.py --help` | rc=0 |
| `pip install -r requirements-dev.txt` | rc=0, `--help` still rc=0 |

Zero apt prerequisites. **False red avoided:** the *first* pass on the same agent failed at `--dry-run`
with `ModuleNotFoundError: No module named 'yaml'` — because `pip install` had died on a transient
`ReadTimeoutError ... files.pythonhosted.org` (venv left with 2 packages). The second pass, same tree,
same documented steps, installed cleanly. That is a probe-environment network artifact, not a product
defect, so **no row was filed for it**; recording it here so the next tick does not re-chase it.

## 5. Closed rows re-driven live (all still hold)

- **DF-AIPP-14** (dashboard occupied-port UX): `PTP_DASHBOARD_PORT=8000 python3 -m src.dashboard.main`
  with port 8000 occupied → rc=1, **one** line naming `PTP_DASHBOARD_PORT` and `Errno 98`, success
  banner not printed. Holds.
- **DF-AIPP-15** (no-key banner): keyed server injects `window.ENV.PTP_API_KEY` with no `#env-warning`;
  keyless routes 401 fail-closed. Holds.
- **DF-AIPP-11** (`session_id` transport): `src/dashboard/static/index.html:490–664` now sends
  `session_id` as a query parameter on every read and control fetch. Holds. (A body-only `session_id`
  is still ignored by the handlers — that is the documented query-only contract, not a defect.)
- **PERF-2** (teacher call latency) — cited, not re-filed: this run measured 12.05 s / 8.79 s for the
  two teacher repairs; the row is closed and the wait is provider-bound.

## 6. What the next tick should NOT re-do

- Do not re-file the missing-`yaml`/`pip ReadTimeoutError` shape (harness network artifact, §4).
- Do not re-file the teacher-call latency as a new PERF row (PERF-2, provider-bound).
- Do not re-file the dashboard port/banner/session_id behaviour (all verified live, §5).
- The next genuine angle is the **JEV→memory-navigation handoff under a completed map ladder**: what
  should the planner do when every reachable map is visited and the only forward edge is the reverse
  one (DF-AIPP-17), and whether the run summary should surface blocked handoffs at all (DF-AIPP-13-R2).
