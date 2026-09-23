# PTP-01X — Product Requirements v3: Fast-Decisions + Teacher, with DuckBrain as the World Model

**Date:** 2026-09-23 · **Author:** Kara (Hermes) · **Status:** proposed · **Trigger:** Bane — *"build me a new prd on the new way we are trying to build the project and the tasks you done, how we are using duckbrain in the project"*
**Supersedes:** PRD v2 (Lifecycle Edition) §4 sequencing. **Inherits:** v2's ladder, north star and honesty doctrine. **Anchor skill:** `ai-plays-poke-lifecycle`.

---

## 1. One-liner

Replace the project's hidden **deterministic assist layer** — the code that has been quietly playing the game — with a **two-tier decision architecture**: a cheap System One model (JEV) makes every per-cycle decision and self-reports when it lacks the state to decide, and a reasoning LLM is called only to **repair the state** (not to play), using DuckBrain as the recovered world model. Success is measured as **autonomy**, not completions.

---

## 2. Why v3 exists: the case file

### 2.1 The measured problem — the 2-hour marathon

On 2026-09-23 a 2-hour wall-clock marathon ran from a true fresh save: **330 episodes**. Audit of the run JSONLs (`cron_logs/run_marathon_fresh_ep*.jsonl`):

| Measure | Value |
|---|---|
| Total LLM decisions (rows carrying a real controller `plan`) | **34** |
| Deterministic harness actions (hardcoded presses/events) | **24,714** |
| Episodes with **zero** model involvement | **329 of 330** |

Episode 1 was genuinely agentic — 34 real decisions, a real plan with reasoning, the agent walked out of the house, crossed Pallet Town and entered the lab on its own. Then the harness took the wheel. Episodes 2–330 were a poison-checkpoint loop: the run ended on a Pokédex dialog (see §2.2), the chaining driver re-booted that state 330 times, each episode spun 80 cycles with **no model calls at all**, and re-saved the same broken state.

### 2.2 What was actually hardcoded — the assist inventory

Read from `cron_runner.py` and confirmed against run logs:

| # | Assist | Where | What it really does |
|---|---|---|---|
| A1 | **Starter "choice"** | `_approach_first_starter()` :454-457 | Walks to a **fixed tile (6,4)** by arithmetic — `down*(4-tile_y)` + `right*(6-tile_x)`. That tile is the left ball. Charmander, every run, forever. |
| A2 | **LLM evicted from the decision** | `_should_select_starter()` :411-427 | Docstring: *"must bypass the LLM"*. Oak's Lab + empty party + any menu → the model is never asked. |
| A3 | **The "pick"** | `_select_starter_from_menu()` :493-509 | Press A, mash B. Never reads which species is highlighted. `species_hint` is read *afterwards* and logged as though it were a choice. |
| A4 | **Battles** | `_escalating_recovery()` :638-643 | In any battle, unconditionally issues `select_move(move_number: 1)`. One move, always. No type matchup, no HP, no PP. |
| A5 | **Recovery ladder** | `:648-685` | rotate direction → START/B/B menu redraw → step back → load checkpoint → 20× A-mash. A scripted state machine standing in for decisions. |
| A6 | **Dialogue** | `dialog_advance` path | 12× A per invocation. |
| A7 | **Per-map steering hints** | `_MAP_HINTS` + `_suggested_map_action()` | Hardcoded per-map directions for bedroom/house/Pallet/Oak's Lab, injected as `suggested_action`. |
| A8 | **Intro + naming** | `:1145-1240` | Deterministic A-mash with programmatic `submit_name()` — the source of the "AAAAAAA" player name. |
| A9 | **Auto-checkpointing** | run loop | Saves a state slot every ~10 cycles unconditionally. |

**The finding that matters:** there was no inventory of A1–A9 anywhere. Each rung was added incrementally to stop a stall, and each silently absorbed a decision the model should have made. A1–A4 are the ones that most damaged the demo, because those are the moments that *look* most like agency.

### 2.3 The honesty failure this caused

The narrated video of that marathon reported the script's behaviour as the agent's — "chosen by the agent itself" for a species the code had selected by tile arithmetic. Bane caught it in one read: *"that's not the ai selecting that's hard coded."*

**PRD rule (inherited and now enforced mechanically):** a run reports **autonomy counts** (§6) in its own log. No claim of agent behaviour may be made from a run whose dominant actions were deterministic.

---

## 3. The new way: one architectural decision, resolved

The decision is **where the intelligence lives per decision**, and it is resolved as a two-tier split with an explicit hand-back contract. The contract between the tiers is the product; either implementation is swappable.

### 3.1 Tier 1 — JEV makes the decision (System One)

`typesafe/jev-1.13` via OpenRouter's decisions endpoint. Non-generative: **state in, typed probabilistic decisions out**, so it cannot hallucinate and cannot type-error. One batched request answers every question for one flat cost.

Measured live on this project (real emulator states, 2026-09-23):

| Property | Measured |
|---|---|
| Model build | `typesafe/jev-1.13-20260917` (pinned and logged) |
| Latency | 0.30–0.76 s |
| Cost | **$0.000050–$0.000064 per decision** (all questions) |
| Questions per request | 7 (action, phase, sufficiency, missing-class, confidence, ambiguity, progress) |

The per-cycle question set: `next_action` (choice over the action vocabulary — the vocabulary **switches to the move list in battle**, a bug the first probe exposed), `phase` (choice), `sufficient_state` (noul), `missing_class` (choice), `action_confidence` (noul), `ambiguity` (noul), `progress` (score 0–3).

### 3.2 The hand-back gate — JEV decides when to escalate

Three independent triggers, thresholds in **code, never in the model**:

1. **Failure.** The last action produced no state change → escalate regardless of confidence. *This is the trigger that would have caught the 330-episode loop.*
2. **Self-reported gap.** `sufficient_state` below floor, or a named `missing_class` → JEV is itself deciding to hand back.
3. **Layered confidence.** Low action confidence **and** high ambiguity must agree; irreversible phases (battle turn, menu commit) escalate on confidence alone.

Design lineage: the layered gate and the failure-trigger rule are borrowed from the published confidence-gated JEV/LLM pattern (JevLoop, Apache-2.0), whose stated principle is *"escalate decisions, not just text generation."* TypeSafe's own reference demo is Doom at 10 queries/second on structured state (not images) — the same shape as this project's RAM reader.

### 3.3 Tier 2 — the reasoning LLM repairs the STATE, it does not play

This is the core of Bane's design and the part that is genuinely different from the published patterns.

The LLM is not asked "what button next". It receives:

- JEV's tentative answer plus the **full distributions** for every question
- the `missing_class` JEV named (the failing question, precisely scoped)
- the last N events and the major milestone events (not every button)
- **DuckBrain-retrieved memory** — prior run summaries, save state, the mechanics/learning layers (§5)
- the current bounded state projection

and returns a **typed state patch**:

```
missing_facts[]      what is absent from the state
fact_source[]        where to get it (RAM / must-interact / memory key / mechanics rule)
instruction_patch    the heuristic to add to JEV's instructions, with applies_when
one_shot_action      optional; only when there is no time to repair
confidence
```

The patch is applied, **JEV is re-asked**, and if it is now confident it continues. Patches are versioned in git with `evidence: [run_id, cycle]`, so the same gap never escalates twice.

### 3.4 Two live proofs

**Proof 1 — supplying the missing fact restores JEV's ability to decide** (same state, one fact added):

| | Control (state as the harness produces it) | Patched (+ the fact JEV named) |
|---|---|---|
| `sufficient_state` | 0.22 | **0.60** |
| `missing_class` | `map_topology` | **`none`** |
| `next_action` | A | DOWN |

**Proof 2 — the projection fixes the gap and JEV names the next one.** Feeding the real, enriched projection (real minimap, real repeat counts, real event log): `sufficient_state` rose 0.22 → 0.34 and `missing_class` moved `map_topology` → **`object_purpose`** — a more specific and genuinely unanswerable-from-RAM blocker, which is precisely the teacher's job.

### 3.5 The honesty metric that comes out of this for free

Because every decision is typed and logged, each run reports:

- `decisions_total`, `jev_answered`, `escalated`
- **`autonomy_ratio`** = JEV-answered / total (the number the old demo had no way to state)
- `escalation_rate_by_missing_class` (must fall run over run — if a class keeps escalating, the patch is not working)
- `cost_per_cycle`

---

## 4. The pipeline end to end

Every stage marked **PROVEN** (measured on live hardware) or **NOT BUILT**.

| # | Stage | Input → Output | State |
|---|---|---|---|
| 1 | Boot & state load | ROM + `.state` → live emulator | **PROVEN** |
| 2 | RAM observation | emulator → `observe()` dict (map, tile, screen, party, adjacency, minimap, exits, battle/menu/dialog) | **PROVEN** (the project's strongest asset) |
| 3 | **State projection** | `observe()` → bounded factual text (~1.4 KB) | **PROVEN** (`src/core/state_projection.py`, verified on real RAM) |
| 4 | **Boot memory injection** | DuckBrain → MECHANICS/SAVE/RUNS-INDEX/LEARNING blocks in the prompt | **PROVEN** (MEM-2; cross-run proof: run B logged `[MEM] boot injection: 322 chars` carrying run A's party) |
| 5 | **Tier-1 decision** | projection → typed answers + confidence | **PROVEN** (`src/core/jev_client.py`, live, model build pinned) |
| 6 | **Hand-back gate** | decision + last-action result → escalate / execute | **PROVEN** (3 triggers, live) |
| 7 | **Teacher escalation** | distributions + missing_class + events + DuckBrain → typed state patch | **NOT BUILT** |
| 8 | **Patch promotion** | patch → versioned scenario file w/ evidence → re-ask JEV | **NOT BUILT** |
| 9 | Action execution | chosen action → emulator input | **PROVEN** |
| 10 | End-of-run recorder | RAM truth → `/game/save/*` + run summary | **PROVEN** (MEM-1) |
| 11 | Autonomy reporting | counters → run log + report | **PARTIAL** (counters exist; `autonomy_ratio` not yet emitted) |
| 12 | Assist retirement | delete A1–A4 paths once JEV covers them | **NOT BUILT** |

**The build is stages 7, 8, 12 plus the reporting half of 11.** Stages 1–6 and 9–10 are live.

---

## 5. How we use DuckBrain in this project

DuckBrain is the project's **memory of record**, and it now has **two distinct jobs** — an old one (the agent's notebook) and a new one (the teacher's reading material).

### 5.1 Two namespaces, two purposes — never conflated

| Namespace | Purpose | Verified live 2026-09-23 |
|---|---|---|
| `pokemon-global` | **The game's memory.** All game/save/run knowledge under `/game/`. | **50 keys** |
| `ai-plays-poke` | **The project's memory.** Fleet/tick/status state for the repo — *not* game state. | 2 keys |

`pokemon-global` is hardcoded at every writer call site in `cron_runner.py` and pinned by the boot reader constant `BOOT_MEMORY_NAMESPACE`. In `duckbrain_client.py` it is a per-function keyword default, not a named constant.

### 5.2 The four layers under `/game/` (prefix = table)

| Layer | Keys | Written by | Live state |
|---|---|---|---|
| **MECHANICS** | `/game/mechanics/{controls,menus,battle,text}` | **no writer exists** | **ABSENT** — the boot reader requests them and gets nothing |
| **SAVE-STATE** | `/game/save/party`, `/game/save/location` | end-of-run recorder from RAM truth | **PRESENT** |
| | `/game/save/items` | requires an item reader — none exists | **ABSENT** (every run logs `save items skipped: no public item reader`) |
| **RUNS** | `/game/runs/<id>/summary`, rolling `/game/runs/index` | end-of-run recorder | **PRESENT** |
| | `/game/runs/<id>/lessons` | agent notes/goals folded at end of run | **ABSENT** in the live namespace despite the writer landing |
| **LEARNING** | `/game/learning/{battle,navigation,strategy,self}` | **no writer exists** | **ABSENT** — two of four PRD layers can never fill today |

### 5.3 The agent's own memory tools (how the controller writes)

- `memory_note` → `/notes/overworld-<cycle>` — **46 such keys live**
- `memory_goal` → `/goals/current` — **present**
- `memory_study` → **reads only**, writes nothing

Notes and goals are folded into `/game/runs/<id>/lessons` at end of run.

### 5.4 The new job: DuckBrain as the teacher's context

This is what v3 adds. On escalation the teacher LLM does not reason from the current frame alone — it retrieves:

1. **`/game/runs/index`** — the rolling last-10 run digest (what has been tried)
2. **prior `/game/runs/<id>/summary`** — what happened last time in this situation
3. **`/game/save/*`** — what this save actually has (party, location)
4. **`/game/mechanics/*` and `/game/learning/*`** — the durable knowledge layers, *when a writer exists*

**This closes a real loop the project could not close before:** the reason `/game/mechanics/*` and `/game/learning/*` are empty is that nothing has ever *authored* them. A teacher LLM that has just diagnosed a state gap is exactly the author. **The teacher writes the layer the agent later boots from** — mechanics rules and distilled learning are produced as a by-product of repair, with run evidence attached, instead of being hand-seeded.

### 5.5 Honesty rules for the memory layer

- An absent key renders **"not captured"**, never 0 and never silent.
- A layer with no writer is marked **design-only in every doc**, so no worker inherits a fiction.
- The live namespace is the source of truth for what exists — the PRD's key tables are re-derived from it at review time (§5.2 was re-derived from a live key listing, which is how `/game/save/items`, `mechanics/*`, `learning/*` and `runs/<id>/lessons` were caught as absent).

---

## 6. What the fleet actually shipped since v2

All commits verified on `origin/main`. This is the list of tasks done, not a plan.

| Row | Commit | Deliverable |
|---|---|---|
| **MEM-1** | `7bd1e30` | End-of-run recorder: RAM truth → `/game/save/party` + `/game/save/location`; `/game/runs/<id>/summary` + rolling index |
| **MEM-2** | `1fe0d3c`, merge `549e577` | **Boot injection** — MECHANICS / SAVE / RUNS-INDEX / LEARNING blocks into the controller prompt, bounded, degrade-to-placeholder, plus narrative-ladder injection. Cross-run proof live. |
| **GAP-055 / FM#23** | `85ccd01` | Door-aware exit targeting for Oak's Lab (map 40) — the movement blocker that gated the organic rival battle |
| **DF-AIPP-1** | `f29db21` | `memory_events` in the run ladder was **always 0** (events went to the log, never to the counted list) — fixed, which unblocks `/game/runs/<id>/lessons` |
| **DF-AIPP-2** | `39ec6f4` | `battle_events` **double-counted** (nested state-window lists + top-level rows: ladder said 6, reality was 2) — deduped |
| **DF-AIPP-4** | `a559bf3` | PRD R3 namespace + SAVE-STATE claims **reconciled to the code** (this is why §5.2 can be trusted) |
| **GAP-053** | `67e6f45` | Final summary separates **real AI decisions from `parse_fallback` presses** — the first honest decision counter |
| **GAP-052** | `d5919fb` | LLM escape hatch: `--controller-model` flag + env override + think-token strip + parse-failure retry |
| **GAP-048** | `7a18ee4` | `--dry-run` API-key **liveness** probe (it validated presence only, and printed green with a dead key) |
| **GAP-057** | `80de287` | CI guard: fails on unbaselined root-level `_*.py` scratch files (29-file baseline) |
| **INT-GL-1** | `295315f` | gitleaks allowlist for env/review artifacts + de-literalised a dashboard API key |
| **QA-AI-PLAYS-POKE-6** | `4fbbc50` | `pyproject.toml [dev]` extras completed (requests-mock, pytest-benchmark, pytest-timeout) |
| **Dogfood DF-AIPP-3/5/6** | `6cd56d5` | MEM-layer real-use findings: no writer for MECHANICS/LEARNING; PRD-vs-code namespace drift; install ROM wall re-proven on a third box; perf baselines (cold boot ~107 s, ~6 s/cycle, $0.42–0.45 per 20-cycle run) |
| **Key provisioning** | (this session) | Dedicated OpenRouter key minted for the project — closes the root cause of **GAP-047** (the P0 that made runs exit 0 with every LLM call dead: *phantom green*) |
| **JEV tier** | `959e…` | `src/core/jev_client.py` (batched decisions + gate, fail-closed), `src/core/state_projection.py`, `scripts/jev_projection_probe.py` |

**Lane state:** all 5 lanes (`ai-plays-poke`, `-dogfood`, `-pm`, `-qa`, `-sync`) re-enabled and verified, all delivering to this thread; satellite board symlinks created (they were missing, which is why satellites reported "board-unreadable"); the `ai-plays-poke-duckbrain-sync` cron resumed. The base lane had not ticked in 10 days — which is *why* the assist layer in §2.2 went unnoticed for so long.

**Board:** 98 rows — 75 complete, 21 pending, 2 in the legacy completed state.

---

## 7. User stories

1. **As the project owner**, I watch a run and can see *from the run's own log* how many decisions the agent made versus how many the harness made, so I never again mistake scripted behaviour for agency.
2. **As the project owner**, I see the agent choose its own starter and its own battle moves from information it read in the game, so the two moments that most look like intelligence are actually intelligence.
3. **As the agent** (machine customer), when a state is genuinely ambiguous or my last action changed nothing, I hand the problem to a slower reasoner that fixes my state and hands control back — instead of pressing A until something happens.
4. **As the teacher LLM** (machine customer), when I am escalated to, I receive the failing question, the distributions, the recent events and the relevant memory, so I can repair the world model rather than guess a button.
5. **As the fleet foreman** (machine customer), I pick up a row whose acceptance criteria are typed and proof-carrying, so I execute without reinterpreting the intent.
6. **As a future contributor**, I read a PRD whose every claim names the file, the commit or the measured number behind it, so I never inherit a fiction.

---

## 8. Acceptance criteria

`AC-n: Given <state>, when <action>, then <observable result> — proof: <command / artifact / number>. (T|C|M)`

**AC-1 (story 1) — autonomy is measured, not asserted.** Given a completed run, when the run closes, then the run log contains `decisions_total`, `jev_answered`, `escalated` and `autonomy_ratio` — proof: `grep -c '"autonomy_ratio"' cron_logs/run_<id>.jsonl` ≥ 1 and the ratio equals `jev_answered/decisions_total`. **(T)**
*Anti-gaming:* the counters must be derived from per-decision rows, not incremented by the summary printer — a green-but-doing-nothing implementation reports `decisions_total = 0` and fails the ratio assertion.

**AC-2 (story 2a) — the starter is a real choice.** Given a fresh save in Oak's Lab with an empty party, when the starter decision fires, then the chosen species is recorded with the JEV distribution that produced it and the `choice` question's criteria name all three species — proof: run log contains a `starter_decision` row with `next_action` ∈ {MOVE/confirm on a selected ball} **and** `species_chosen` whose value is not derivable from a fixed tile; re-running with a different forced `next_action` selects a different species. **(T)**
*Anti-gaming:* the old code walks to tile (6,4) — a test that asserts only "a starter was obtained" passes on the hardcoded path and therefore does not count.

**AC-3 (story 2b) — battles are reasoned.** Given an active battle with ≥2 moves and PP > 0, when the turn decision fires, then the selected move comes from a JEV `choice` whose criteria are the party's actual move list — proof: run log shows `phase=BATTLE` with a `battle_action` ∈ {MOVE_1..4, SWITCH, ITEM, RUN} and the raw distribution present; no `select_move(1)`-only signature (an observable: the chosen move index varies across turns with different type matchups). **(T)**

**AC-4 (story 3) — the hand-back gate fires on failure.** Given two consecutive actions that produce no state change, when the next decision is made, then the gate escalates with reason `failure: last action changed nothing` regardless of `action_confidence` — proof: gate unit test over recorded decisions, plus a live run where the stuck-lab state escalates. **(T)**

**AC-5 (story 3) — JEV self-reports the gap.** Given a state lacking map topology, when JEV is asked, then `sufficient_state` < 0.5 and `missing_class` ∈ {`map_topology`, `object_purpose`, …} — proof: `scripts/jev_projection_probe.py` output on a real checkpoint shows both fields populated and `escalate=True`. **(C)**

**AC-6 (story 4) — the teacher repairs state and control returns.** Given an escalation, when the teacher responds, then it returns a typed patch (`missing_facts`, `fact_source`, `instruction_patch`, optional `one_shot_action`), the patch is applied, JEV is re-asked, and the re-ask's `sufficient_state` is ≥ the pre-patch value with `missing_class` cleared or narrowed — proof: a recorded escalation pair (pre-ask, patch, post-ask) in the run log; the measured live example is 0.22 → 0.60 with `map_topology` → `none`. **(T)**

**AC-7 (story 4) — a patch is durable and evidence-bearing.** Given a promoted instruction patch, when the same situation recurs in a later run, then no escalation occurs for that class — proof: `escalation_rate_by_missing_class` for the patched class is 0 in the next run **and** the patch file carries `evidence: [run_id, cycle]`. **(T)**
*Anti-gaming:* a patch that is never re-consulted cannot pass — the counter must come from the gate's own decision path.

**AC-8 (story 5) — no assist without an entry.** Given a merge to `main`, when the diff adds a deterministic action path in the decision loop, then the assist inventory (§2.2) is updated in the same commit — proof: the inventory row count is asserted by a test that fails when a new `emu.press_button(` call site appears outside the declared assist set. **(T)**
*This is the criterion that makes the §2.2 rot structurally impossible to repeat, and it is the one a green-but-idle implementation cannot fake.*

**AC-9 (story 6) — memory absence is honest.** Given a boot with no `/game/mechanics/*` records, when the prompt is composed, then the block renders "not captured" and never a value that reads as data — proof: unit test asserts the placeholder string for each empty layer. **(T)**

**AC-10 — the key is alive or the run refuses.** Given a dead or missing controller key, when a run starts, then it exits non-zero with a named reason and **no** `battle_end`/milestone events are emitted — proof: reproduce by running with a revoked key; the log contains the liveness failure and exit code ≠ 0. **(C)**
*This closes GAP-047's phantom-green class by construction.*

---

## 9. Success criteria as replayable proofs

1. **Replay the 330-episode incident:** run the marathon driver's state-chaining logic against the poisoned checkpoint. The **failure-triggered escalation fires on the first stuck episode** instead of re-running it 330 times; the run log shows an escalation with reason `failure:` rather than a 330th silent repeat.
2. **Replay the hardcoded-starter incident:** boot a fresh save to Oak's Lab. The run log contains a JEV `choice` distribution over the starter options; `_should_select_starter()` no longer short-circuits to a deterministic path (grep the run log for the absence of the `confirm_first_starter_then_decline_nickname` signature).
3. **Replay the missing-fact experiment end-to-end in a live run:** the stuck-lab state escalates, the teacher returns a patch naming map/object facts, the re-ask clears `missing_class`, and the agent reaches the ball without the tile-(6,4) hardcode ever executing.
4. **Autonomy floor:** a 80-cycle run reports `autonomy_ratio ≥ 0.5` with `escalation_rate` falling versus the previous run of the same shape. (The published JevLoop experience — 2 of 22 steps avoiding an LLM call with copied thresholds — is the number this criterion exists to beat, and it is why thresholds are tuned here rather than borrowed.)
5. **L2 gate unchanged:** the v2 §5 L2 acceptance run still passes, and now passes with its autonomy counts printed.

---

## 10. Scope

**In scope:** the state projection; the JEV decision tier and its gate; the teacher tier and patch promotion; DuckBrain as the teacher's retrieval source **and** the writer of the MECHANICS/LEARNING layers; assist retirement (A1–A4 first); autonomy reporting; the assist inventory guard (AC-8).

**Out of scope:** the plugin/vision cartography path (superseded); `game_loop.py` and the unwired GOAP/combat/map-integrator modules (v2 R1 quarantine decision still stands); L3/L4 progression targets; any story scripting — the north star (mechanics, never story) is unchanged.

---

## 11. Open decisions (the owner's, ranked)

1. **Retire A1–A4 outright, or keep them behind a declared flag?** *Recommendation: retire A1 (starter tile) and A4 (battle move 1) outright — both are one RAM read from being answerable, and both are the moments that most damage the demo's credibility. Keep A5's checkpoint-recovery rung as a declared safety net with its use logged per run.*
2. **Autonomy floor for accepting a run as evidence.** *Recommendation: `autonomy_ratio ≥ 0.5` for L2-class claims, rising to ≥ 0.8 for L3. Below the floor the run is reported as a pipeline test, never as progress.*
3. **Who authors MECHANICS — the teacher, or a separate distillation pass?** *Recommendation: the teacher, gated by "2+ runs observe the same mechanic", with the key written only on the second observation. One-run learning is how a wrong rule becomes permanent.*
4. **Escalation budget.** *Recommendation: cap escalations per run (e.g. 25% of cycles) and make exceeding the cap a loud run-level warning rather than a silent cost — otherwise the failure mode is a very expensive way to run the old script.*
5. **Does the teacher get vision, or state text only?** *Recommendation: state text only for the first build. It is what JEV gets, it keeps the two tiers comparable, and vision adds a second source of truth that would need its own honesty rules.*

---

## 12. Risks

- **Escalation-rate blowout** — the documented failure of copied thresholds (2/22 avoided an LLM call). Mitigated by AC-7 + decision 4; measured every run.
- **The teacher becomes the player** — if most escalations return `one_shot_action`, the architecture has collapsed back to ordinary LLM play at higher cost. Mitigated by AC-6 requiring a *patch*, with `one_shot_action` as the exception, and by tracking the ratio.
- **State projection too thin** — already observed: JEV flagged `map_topology` on a trivial overworld state with the original projection. The projection is the highest-leverage surface and must be treated as a first-class deliverable.
- **Assist creep returns by a new route** — a hint injected into the *projection* is an assist wearing a state's clothes. Mitigated by `state_projection.py` deliberately excluding `_MAP_HINTS`/`suggested_action`, and by AC-8.
- **Two active lanes, one workdir** — enabling lanes arms ticks that clean untracked files in the workdir (measured this session: an uncommitted JEV client and 8 scripts were deleted by a tick's cleanup pass). Mitigated by committing or staging outside the tree before enabling any lane.
- **Run variance** — a single pass is not a level; the L2 gate still requires two consecutive green runs.

---

## 13. What this PRD does NOT change

- The north star: mechanics are taught, story never is; minimal guidance; the agent wins on its own with only the tools it is given.
- The proven assets: RAM reader, StateWindow, guardrails, frame cache, checkpoints as instruments.
- The foreman/scheduler/board machinery and the ladder's level boundaries — only the *decision architecture inside the loop* changes, plus the honesty instrumentation that makes its claims checkable.

---

*End of PRD v3. Next actions per §4: build stages 7–8 (teacher + patch promotion), emit the AC-1 counters, then retire A1 and A4 and re-run the L2 acceptance instrument with autonomy printed.*
