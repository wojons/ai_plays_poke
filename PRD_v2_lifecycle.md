# PTP-01X — Product Requirements & Refactor Brief (v2, Lifecycle Edition)

**Date:** 2026-09-11 · **Author:** Kara (Hermes) · **Trigger:** Bane — "rebuild the PRD from the top, find where we need to refactor and redesign to get the value we are looking for"
**Anchor:** skill `ai-plays-poke-lifecycle` (ladder + slop doctrine) · Supersedes the Dec-2025 framing in README/AGENTS.

---

## 1. The value we are looking for (restated from the top)

An autonomous agent that **plays Pokémon by understanding it** — reading the screen,
deciding for itself, remembering what it learned — with no scripting of the story and
no human-hand on the controller. The deliverable that proves the value is a **run,
not a repo**: the agent walks the early game organically, wins its battles, remembers
across sessions, and every claim is backed by run evidence in `cron_logs/`.

The benchmark question (Bane, 2026-08-09, unchanged):
> *Can an AI figure out a kids' game with minimal guidance — using only the tools it is given?*

**What value is NOT:** green gates, clean audits, 3,900 passing tests, 163K words of
specs. Those are the health of the scaffolding. The Aug–Sep 2026 tick history shows
weeks of scaffolding polish while the actual gameplay level did not move. This PRD
re-aims the project at the ladder.

### The ladder (value levels, evidence-gated)

| Level | Value delivered | Evidence gate |
|---|---|---|
| L0 | Pipeline runs end-to-end | run jsonl: exit 0, 0 API failures |
| L1 | Scripted milestones: starter + rival battle WON (checkpoint assists allowed) | `battle_start`→`battle_end` in one run — **DONE** (`battlefix_win1` c1→c3, commit f31d620) |
| **L2 — CURRENT TARGET** | **One organic run: intro → self-set goal → starter → rival battle WON → lab exit → Route 1, memory channel firing** | map 40→11 progression + battle_end + ≥1 agent-written note/goal in DuckBrain, all from boot.state WITHOUT the battle checkpoint |
| L3 | Sustained multi-session progression (beat Brock organically; goals persist across runs) | organic Brock battle_end + cross-run goal continuity |
| L4 | Full game (Elite Four) at low HINT_LEVEL | Hall of Fame from a low-hint run |

**L2 is the PRD's center of gravity.** Everything below either serves L2 or is
explicitly budgeted maintenance.

---

## 2. Reality audit — what actually runs vs what the docs claim

Verified 2026-09-11 against `cron_runner.py` imports and the run logs.

### 2a. LIVE (the real product — keep, this is the asset)

| Component | Role | Verdict |
|---|---|---|
| `cron_runner.py` | main loop: boot → observe → decide → execute | ✅ the spine |
| `src/core/emulator.py` (PyBoy) | input, fast-forward, save/load state | ✅ solid |
| `src/core/ram_reader.py` | hallucination-free state; battle structs re-pinned empirically (f31d620) | ✅ strongest asset |
| `src/core/state_window.py` + HSM (`state_machine.py`) | per-state LLM windows; HSM wired here | ✅ keep — but HSM is ~13 state classes doing less than its billing |
| `configs/prompts/gen1/*` + hints 01–04 | mechanics-first prompt stack (core.yaml v2 = game-agnostic) | ✅ aligned with north star |
| `src/core/frame_cache.py` | dedup across runs, real cost savings (65% hit rates) | ✅ keep |
| DuckBrain memory channel (9f815b1): 5 tools + note/goal/study in overworld loop | agent self-tracking | ✅ built — ❌ starving (see 3b) |
| Battle guardrails (tools.py: menu normalize, flee bound, query_global bound) | deterministic safety net | ✅ proven in the win run |
| Checkpoints: `boot.state`, `boot.battle.state` | deterministic test fixtures | ✅ keep as instruments |

### 2b. DEAD / UNWIRED (claims without a product — refactor targets)

| Claimed | Reality | Action |
|---|---|---|
| **GOAP decision core** (README centerpiece; spec ch09) | `src/core/goap.py` exists; ZERO imports in the live path | **Wire-or-delete decision** (see R1) |
| **3-tier memory hierarchy** (Observer/Strategist/Tactician, README centerpiece) | Does not exist as such; reality is GlobalContext (in-run) + StateWindow history + DuckBrain channel | Redesign: fold into one honest memory model (R3) |
| **Vision cartographer** (Gemma) | Superseded by RAM reading months ago; still a spec chapter + prompt | Demote to fallback/legacy |
| **`src/game_loop.py` legacy path** | Broken imports; AGENTS.md already calls it superseded | Delete or quarantine from specs/docs |
| `map_integrator.py`, `failsafe.py`, `combat.py`, `goap.py` etc. | Not imported by `cron_runner.py` | Same wire-or-delete sweep |
| **specs/ tree (39 files, ~163K words)** | Chapters 3 (cartography), 9 (GOAP), parts of 2 (memory) describe unwired systems; **foreign DexDat platform AGENTS.md content sits inside the tree** (different project entirely) | Re-scope per R1; purge foreign content |

### 2c. The docs lie (the slop engine)

README/AGENTS describe an architecture ("GOAP core", "20+ hour journey",
"hierarchical memory") that no run has ever executed. Every worker/tick that reads
them inherits the fiction — that's where scope creep and rejected tasks come from.
**The PRD rule: docs describe what runs, or say explicitly that they don't.**

---

## 3. The three structural gaps blocking L2 (the actual redesign work)

### 3a. FM#23 — Oak's Lab wander (the movement blocker)
The agent moves but never targets the lab exit door (tileset-5 block 0x04,
bottom-center, map 40). The rival battle lives at that door; without exit targeting,
no organic run reaches the battle. `_suggested_map_action()` has door-aware steering
for bedroom/house/Pallet — **map 40 was never added.** UNFILED as a board row.

### 3b. Memory starvation (the intelligence blocker)
The READ→NOTE→ACT channel exists and works (smoke-proven: agent set its own goal from
Oak's dialog), but post-T123 runs logged **0 memory events** — 20-cycle checkpoint
runs boot past the narrative that gives the agent something to note. Memory must be
exercised *within* the run shape that produces narrative, and *across* runs (the
Alice-video finding: memory across attempts was the single biggest lever).

### 3c. The E2E instrument measures L0 (the measurement blocker)
The recurring E2E fixture fires 20-cycle runs and gates on exit-0/leak/lock-rate.
That proves the pipeline, not progress. Same map distribution for 5+ windows was
reported as green. **Redesign the instrument:** ladder scoring (forward map movement,
organic battle events, memory events) replaces exit-0 as the headline; 80-cycle
narrative runs become the L2 instrument; the 20-cycle run is demoted to smoke.

---

## 4. Refactor & redesign plan (R1–R6, sequenced)

### R1 — Architecture honesty sweep (1 tick, no gameplay risk)
- Rewrite README/AGENTS "Paradigm Shift" sections to describe the LIVE loop
  (RAM-observe → StateWindow → plan → execute → DuckBrain memory), keeping the north
  star intact.
- specs/: mark ch09 GOAP + ch03 cartography **DESIGN-ONLY (unwired)**; delete the
  foreign DexDat AGENTS.md content; add `SPEC_STATUS.md` with wired/design-only/dead
  per chapter.
- Delete or `legacy/`-quarantine: `game_loop.py`, `goap.py`, `map_integrator.py`,
  `failsafe.py`, `combat.py` **only after** the wire-or-delete decision in 4b —
  default is quarantine, not deletion.

### R2 — FM#23 door-aware exit targeting (THE unblocking gameplay row)
Add map-40 to `_suggested_map_action()`: when party ≥1 and map==40, steer toward the
door block (0x04) at bottom-center (tile ~(5,6)), then trigger the rival. Acceptance:
in a 80-cycle run from `boot.state`, agent reaches the door and the battle fires
organically (`battle_start` without `--boot-state battle`).

### R3 — Memory architecture: four layers, one namespace (Bane-designed 09-11)

All layers live in DuckBrain ns `pokemon-global` under `/game/` prefixes (prefix = table).
**Namespace, verified 2026-09-23 against the code:** `namespace: pokemon-global` —
`cron_runner.py` hardcodes it at every writer call site (lines 1083, 1102, 1119, 1142,
1166, 1173, 1194) and the boot reader pins the named constant
`BOOT_MEMORY_NAMESPACE = "pokemon-global"` (cron_runner.py:1311). In
`src/core/duckbrain_client.py` it is the per-function keyword default
`namespace: str = "pokemon-global"` on `remember`/`recall`/`list_keys`/`get`/`search`
(lines 33/66/112/151/162) — there is **no named `DEFAULT_NAMESPACE` constant**; the
default is a literal on each signature. The legacy ns **`ai-plays-poke` is
retired/pre-migration**: it holds the old DuckBrain store layout plus only two
`/project/ai-plays-poke/*` status records and **no `/game/*` data** — nothing in the
repo reads or writes it.

| Layer | Keys | Scope | Written by | Read by |
|---|---|---|---|---|
| **MECHANICS** | `/game/mechanics/controls`, `/menus`, `/battle`, `/text` | The game itself — universal, survives save resets | **design-only — no writer in the code today** (target: `memory_study` + verified distillation) | boot reader requests them (cron_runner.py:1312–1317) |
| **SAVE-STATE** | `/game/save/party`, `/game/save/items`, `/game/save/location` — **these three only** | This save file: what I have, where I am | **RAM-truth at end-of-run** (`_record_run_memory()`, cron_runner.py:1105–1169): `party` + `location` land on every run; `items` lands **only when a public item reader exists** — none exists today, so every run logs `[MEM] save items skipped: no public item reader` (cron_runner.py:1146–1147) and **no `/game/save/items` record is written** | Boot reader requests exactly these three (`BOOT_SAVE_KEYS`, cron_runner.py:1318–1322) |
| **RUNS** | `/game/runs/<run_id>/summary` + `/lessons`, rolling `/game/runs/index` | One attempt, append-only evidence | end-of-run recorder `_record_run_memory()` (machine) + agent notes/goals folded into `/lessons` | boot reader requests `/game/runs/index` only (cron_runner.py:1329) |
| **LEARNING** | `/game/learning/battle`, `/navigation`, `/strategy`, `/self` | Distilled cross-run lessons — the Alice layer (target) | **design-only — no writer in the code today** (target: distillation validated by 2+ runs) | boot reader requests them (cron_runner.py:1323–1327) |

**NOT implemented — keys the PRD must not claim (verified against the write path 2026-09-23):**

- `/game/save/quests` and `/game/save/acquired` **are not implemented**. No code writes
  them (no write site in `cron_runner.py` or `src/`), they are absent from the boot
  reader's key list, and the live ns holds zero such records. The controller prompt
  still tells the agent that notes/goals feed "the save-state quests"
  (cron_runner.py:867 and :869) — **that prompt text is wrong**; the write path below is
  what actually happens.
- `/game/mechanics/*` and `/game/learning/*` are **read-only targets**: the boot reader
  requests them (cron_runner.py:1312–1327) but **no writer exists** in the repo and the
  live ns holds no such records. MECHANICS and LEARNING stay design-only until a writer
  lands — today a boot read of them yields "no boot memory".

**The 1:1 tool mapping — as the code actually routes it (verified 2026-09-23):**
`memory_note` → `/notes/overworld-<cycle>` (domain `concept`, default ns;
cron_runner.py:1230–1240), folded into `/game/runs/<id>/lessons` at end-of-run ·
`memory_goal` → `/goals/current` (cron_runner.py:1258–1263), also folded into
`/game/runs/<id>/lessons` · `memory_study` → **reads** the key the agent names
(cron_runner.py:1271–1287) and writes nothing.

**"Handle both" property (Bane):** in the target design a fresh save boots with MECHANICS
and LEARNING intact (controls/menus knowledge is not buried in a dead run) and a resumed
save boots knowing its party/location from SAVE-STATE — **today the save half is real
(party/location) while the MECHANICS/LEARNING half is still empty**, because no writer
populates those keys. Neither depends on the other.

**Boot injection (MEM-2, shipped):** prompt template gains compact MECHANICS + SAVE +
runs/index (last-10 digest) + relevant LEARNING blocks. End-of-run recorder in
cron_runner.py (`_record_run_memory()`) writes `/game/save/party` + `/game/save/location`
from RAM truth (+ `/game/save/items` once an item reader lands) and
`/game/runs/<id>/summary` + `/game/runs/<id>/lessons` + the rolling `/game/runs/index`.

*R3 namespace + SAVE-STATE claims in this section were reconciled against the
implementation by board row DF-AIPP-4 (2026-09-23); this section now describes what the
code writes, and marks the rest design-only.*

**Sequencing update:** R3 (recorder + injection) can land before or parallel to R2 —
they are independent; memory wiring is hot because the design is fresh.

### R4 — Run-shape redesign (the instrument)
- `E2E-001` becomes: 80-cycle narrative run from `boot.state` (not the battle
  checkpoint), scored on the L2 gate. Keep a separate 20-cycle smoke if gates demand
  it.
- Board row for the E2E fixture updated to carry the ladder scoring, so the foreman
  stops reporting exit-0 as progress.

### R5 — Bench hygiene (bounded, per slop doctrine)
- Freeze (hand-fix or close, no re-dispatch): DEPS-004 (4 rejects), GAP-045 (3
  rejects), GAP-043/046 (supersede with one batched hygiene commit).
- Dedupe QA-injected rows (QA-AI-PLAYS-POKE-1..5 exist 2–3× each).
- Chores get ONE batched attempt per realignment cycle; they never out-prioritize
  R2.

### R6 — Key rotation (human dependency)
`ai-plays-poke-2` OpenRouter key expired 09-08 (401 confirmed 09-11). Until Bane
issues a fresh restricted key, L2 runs use the live fallback key from
`~/.hermes/env-file` via explicit env. **No run before 09-08 counts as milestone
evidence** (phantom-green rule).

---

## 5. L2 acceptance criteria (the gate, verbatim)

One run, `--boot-state data/boot.state --cycles 80` (NO battle checkpoint), fresh
run-id, live key:

1. Agent reads intro/dialog and **writes ≥1 note or goal itself** (memory_note /
   memory_goal event in the jsonl, verifiable in DuckBrain).
2. Starter picked (may use the deterministic branch — it's an L1 assist, allowed).
3. **battle_start → battle_end organically** (battle fires from gameplay, not from a
   battle-start checkpoint).
4. Map progression 40 → 11 (Route 1) at any point post-battle.
5. Run survives the 4 GB cap; 0 API failures.
6. Review page + replay video delivered (Bane reviews screenshots, per convention).

**Honest caveat carried in the PRD:** the deterministic starter branch and battle
guardrails are scaffolding assists. They are allowed at L2 because the LEVEL's claim
is "organic arc exists" — but L3 tightens: goal-setting, navigation choices, and
battle play must be agent-reasoned with no deterministic takeover beyond safety nets.

---

## 6. Sequencing (what order, and why)

| # | Item | Cost | Unblocks |
|---|---|---|---|
| 1 | R6 key decision (Bane) + R5 freeze list applied to board | minutes | everything |
| 2 | **R2 FM#23 door targeting** (the one gameplay row) | 1 worker tick | organic battle |
| 3 | R4 E2E instrument redesign + R1 docs sweep (parallel-safe) | 1 tick each | honest measurement |
| 4 | **First L2 acceptance run** (80 cycles, ~$1–2) | 1 run | the level |
| 5 | R3 memory tuning from what the run shows | 1 tick | L3 path |
| 6 | L3 planning (Brock, cross-run goals) — only after L2 lands | — | — |

---

## 7. Risks

- **Run variance:** single-run pass ≠ stable level. L2 needs the gate met twice
  (T172-precedent: re-run before declaring).
- **Deterministic-assist creep:** every assist added for L2 must be listed in the run
  report; anything beyond starter-branch + safety nets voids the level claim.
- **Scope gravity:** specs/docs work will try to re-occupy ticks. The lifecycle
  skill's doctrine is the defense: gameplay rows first, chores budgeted, slop frozen.
- **Cost:** 80-cycle runs ≈ $1–2 each; trivially affordable vs the weeks of idle
  ticks, but a failing loop of them needs diagnosis between attempts, not blind
  retries.

---

## 8. What this PRD does NOT change

- North-star directives (mechanics-not-story; self-tracking; minimal guidance).
- The foreman/scheduler/board machinery — it stays; only its priorities re-aim.
- The proven assets (RAM reader, StateWindow, guardrails, frame cache) — they are the
  foundation L2–L4 stand on.

*End of PRD v2. Next action per §6: apply the R5 freeze list, file R2, fire the L2 run.*
