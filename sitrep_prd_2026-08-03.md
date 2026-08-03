# SITREP PRD — AI Plays Pokémon (ai-plays-poke) — E2E Tick T72

**Project:** PTP-01X — Autonomous Pokémon (Gen 1) Gameplay AI Benchmark
**SITREP Date:** 2026-08-03 | **Tick:** T72 (E2E-001 fixture, first tick of due window T72–T77)
**Status:** 🟡 STABLE-WITH-CRITICAL-FINDING — STARTER PICKED LIVE; BATTLE-PHASE MEMORY LEAK BLOCKS ROUTE-1 RUNS
**Repo:** `/home/kara/ai_plays_poke` | **HEAD:** `0f57908` (pre-tick)

---

## 1. EXECUTIVE SUMMARY

The recurring E2E testing tick (E2E-001) ran five live gameplay sessions of the
Luna-controller pipeline (`cron_runner.py`, `openai/gpt-5.6-luna` via OpenRouter
+ deepseek-v4-flash battle loop). Two milestones, one critical finding:

**✅ Milestone 1 — Starter Pokémon picked LIVE (T68 fix verified).**
Runs 3 and 4 both broke the Oak's Lab starter loop that had blocked the project
since T62. The new same-tile stuck detector (MAX_SAME_TILE_CYCLES=8) fired at
map 40 tile (5,3), the deterministic `starter_approach` branch moved the agent
to the Poké Ball, and the party count transitioned 0→1 (starter_selection +
starter_picked events at cycles 21 and 18 respectively). Nickname prompt
declined via the B-press path — no name-entry stall.

**✅ Milestone 2 — Full recovery ladder exercised live.**
All three recovery dimensions fired in one run (run 3): direction-locked
(RIGHT x4, cycle 3 → alternate_direction), screen-locked dialog (x5, cycle 17 →
dialog_advance), tile-locked (x8, cycle 20 → starter_approach). The escalating
recovery ladder is real, not stubbed.

**🚨 CRITICAL FINDING — Battle-phase native memory leak (~70–100 MB/s).**
Every run that engaged a wild battle leaked memory at 70–100 MB/s and died at
~50 GB RSS within ~9 minutes (runs 1–4; two killed by the OOM-pressure
environment, two by explicit ulimit caps). Python heap is clean (tracemalloc:
10 MB total at battle start), pure-emulator ticking is flat (66 MB over 24k
frames), and a run that never entered a battle (run 5) stayed at 134 MB for 10+
minutes — **the leak engages only during real battle cycles**. First
manifestation today because T67's run never reached Route 1: the starter fix
let the agent out of the lab, exposing a pre-existing battle-path leak.
New P0 board task: **GAMEPLAY-LEAK-001**.

**Secondary finding:** HSM rejects `BOOT.INITIALIZE → BATTLE.BATTLE_MENU` and
spams "Invalid transition attempted" in an infinite loop when battle detection
races the HSM (run 5, cycle 56) — included in GAMEPLAY-LEAK-001 scope.

---

## 2. RUN LOG (2026-08-03, all `luna_v11_*`)

| Run | Cycles reached | Starter | Battle | Death | Leak observed |
|---|---|---|---|---|---|
| 1 (05:20Z) | 29 | — | cycle 22 | SIGTERM ~05:29Z | yes (48 GB RSS at kill) |
| 2 (05:32Z) | 41 | — | cycle 34 | killed ~05:41Z | yes (50 GB RSS) |
| 3 (05:59Z) | 75 | ✅ cycle 21 | cycle 75 | 12 GB ulimit | yes (~8.7 GB at cycle 75) |
| 4 (06:09Z) | 26 | ✅ cycle 18 | cycle 24 | 16 GB ulimit | yes (1.5 GB in 20 s) |
| 5 (06:18Z) | 56 (stuck) | — | det. race | killed (stuck) | **no** (134 MB flat, no battle loop) |

Run 3 detail (`_analyze_run.py`): 89 entries; screens — overworld 55 (62%),
dialog 16, unknown 16, menu 1, battle 1. Recovery events: cycle 3
direction-locked, 17 screen-locked dialog, 20 tile-locked → starter_approach,
21 starter_picked, 75 battle_start. Frame cache: 76 unique frames / 159 refs.

---

## 3. SCREENSHOT REPORT (run 3 — `run_luna_v11_20260803_055934`)

### 3.1 Oak's Lab tile-lock → starter approach (cycle 20)
![Tile-locked at (5,3)](screenshots/run_luna_v11_20260803_055934/step_0020.png)
*RAM reader reports map 40 @ (5,3) for 8 consecutive cycles. The T68
tile-locked detector fires and the deterministic `starter_approach` branch
walks the agent to the first Poké Ball and presses A.*

### 3.2 Starter selection menu (cycle 21)
![Starter selection](screenshots/run_luna_v11_20260803_055934/step_0021.png)
*`starter_selection` event: confirm_first_starter_then_decline_nickname.
Party count 0→1, nickname declined with the B-press sequence (verified live:
0 name_entry cycles after selection).*

### 3.3 Post-starter overworld (cycle 22)
![Charmander obtained](screenshots/run_luna_v11_20260803_055934/step_0022.png)
*Agent walks away from the Poké Ball with party_count=1. This is the state
T62–T67 could never reach.*

### 3.4 First wild battle (cycle 75)
![Wild battle](screenshots/run_luna_v11_20260803_055934/step_0075.png)
*First Route-1 wild battle. The battle StateWindow loop (deepseek-v4-flash,
STATE_STEPS=12) starts; memory leak engages immediately (~70 MB/s) — see
Section 5.*

---

## 4. CAPABILITY MATRIX

| Capability | Status | Evidence |
|---|---|---|
| Boot ROM, skip intro, name entry | ✅ | deterministic A-mash bypass |
| Navigate Pallet Town | ✅ | 8+ positions, direction-locked recovery |
| Enter Oak's Lab (map 40) | ✅ | tileset 5 classified |
| Dialog advance (A-mash) | ✅ | dialog_advance recovery, no menu_redraw trap |
| **Starter selection** | ✅ **NEW (T68 fix verified)** | picked at cycle 21 (run 3) / 18 (run 4), party 0→1 |
| Same-tile stuck detection | ✅ **NEW** | fired at (5,3) x8 → starter_approach |
| Leave lab / Route 1 | 🟡 | reaches grass, first battle at cycle 24–75 |
| Wild battle loop | 🚨 **LEAK** | battle engages but process dies at ~50 GB |
| Frame cache dedup | ✅ | 76/159 refs, cross-run persistence |

---

## 5. MEMORY LEAK FINDING (GAMEPLAY-LEAK-001, P0)

**Symptoms:** RSS grows linearly at ~70–100 MB/s from the first real battle
cycle. Process reaches ~50 GB and is killed (system memory pressure + SIGTERM,
or explicit ulimit). JSONL/stdout truncate mid-line at the battle_events print
— death is instant, no Python traceback.

**Evidence chain:**
1. mem-monitor (systemd, 30 s snapshots): avail 49 G → 4.3 G with a
   `venv/bin/python` at 48–50 GB RSS across two runs; freed within 30 s of the
   process death. cgroup events: `oom 0` — not a cgroup OOM.
2. tracemalloc (in-process, run 5): traced Python heap **10 MB flat** through
   battle start — not a Python-object leak.
3. Pure-emulator bisect: 24,000 ticks + screen captures from 5 checkpoints —
   **66–72 MB flat**. Not plain ticking.
4. Run 5 control: battle never engaged (HSM reject loop) → 134 MB flat for 10+
   minutes, 23 Luna calls, dialog auto-A cycles. **No battle loop = no leak.**
5. All leaking runs share the battle StateWindow loop: 12 steps of
   deepseek-v4-flash calls + battle tools (select_move/switch_pokemon/
   run_from_battle) + `wait(60)+fast_forward(180)` animation spans.

**Ruled out:** Python heap growth (tracemalloc), frame cache (metadata-only,
LRU 1000), state_window history (bounded, recreated per cycle),
OpenRouterClient (stateless `requests.post`), plain emulator ticking.

**Prime suspects (in order):** (a) pyboy native rendering during battle
sprites/animations at fast-forward rates; (b) SDL2 audio queue when the
emulator runs flat-out during battle animation spans (SGB ROM);
(c) interaction of battle RAM reads with pyboy's memory view under rapid
fast-forward.

**Next step (worker task):** instrument with `py-spy`/`smaps` during a live
battle, bisect pyboy version / SDL2 audio disable / SGB border disable, and
land a fix + regression test. Until fixed, E2E runs that reach Route 1 will
die at ~9 minutes.

---

## 6. NEVER-DONE AUDIT (11-point, all clean)

| Check | Result |
|---|---|
| git status | CLEAN except `data/duration_profiles.json` (runtime bookkeeping, committed this tick) |
| GitReins guard (full) | ✅ PASS 5/5 (secrets/lint/tests/static_analysis/lsp) |
| mypy | ✅ 0 errors / 61 files |
| ruff | ✅ PASS (src/ tests/ cron_runner.py) |
| compileall | ✅ PASS |
| TODO/FIXME | ✅ 0 |
| GitReins tasks | ✅ 4/4 complete, 0 pending |
| CI (gh run list) | ✅ green 5/5 (last: T71 push 3m4s) |
| Scheduler | ✅ Enabled=true, CooldownS=7200 (fleet.toml pin matches — no PUT) |
| Remote | ✅ 0 unpushed, origin/main clean, no external commits |
| Board | ✅ T72 event appended; GAMEPLAY-LEAK-001 created |

**E2E-001 disposition:** executed at first tick of due window (T72–T77).
Next due: T77 (cadence 5–10). Fixture remains pending (recurring).

---

*Generated by Hermes foreman, T72 — 2026-08-03.*
