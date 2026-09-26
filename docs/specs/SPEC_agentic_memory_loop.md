# SPEC — Agentic Memory Loop (label, store, retrieve, delegate)

**Status:** design authority for the agentic workstream. Implementation rows derive from this
document; if code and this spec disagree, this spec wins until amended here.
**Scope:** `ai-plays-poke` harness (`cron_runner.py`, `src/core/*`).

---

## 0. Why this exists (measured, not assumed)

Audit of the live harness, 2026-09-26:

- **No context window.** Every cycle is a fresh single-turn request:
  `messages=[{"role":"system",...},{"role":"user",...}]` and nothing else. No message history, no
  persisted transcript anywhere in the repo. The past survives only as `_mem_notes` (capped at **6**
  entries, joined and truncated to **300 chars**) and a single `_mem_goal` string, plus an in-run
  `results` list that JEV/teacher read as "recent events" — an event log, not a window.
- **No tool calling.** `src/core/ai_client.py` *does* support native OpenAI function calling (`tools`
  param, `tool_calls` parsing, text-only-model fallback). The controller path never uses it: it
  returns a JSON **plan** (a list of button presses). `_battle_tool_call` looks like tool use but is a
  **fixed translation table** from JEV battle vocabulary (`MOVE_n`/`RUN`/`SWITCH`) to emulator
  transport calls — the model is not choosing tools.
- **No delegation.** A grep for subagent/delegate/research across `cron_runner.py` and `src/core/`
  returns nothing.
- **DuckBrain is write-only.** The client (`src/core/duckbrain_client.py`, namespace
  `pokemon-global`) exposes `remember / recall / get / list_keys / search`, but the loop uses it only
  for an end-of-run summary row and a boot-memory block. The agent cannot **label** its own knowledge
  and **pull it back** on demand — which is the entire point of the tool.

**Consequence, in one number:** `map_topology` is **1,219 of 1,352 escalations (90%)**. The agent
cannot remember "I have been in this room; the exit is south". It re-derives the same world fact
every episode, forever, and spends a teacher call on it each time.

---

## 1. Principles

1. **Memory is the substrate, not a log.** If a fact is worth acting on twice, it is labeled and stored.
2. **Everything learned is addressable.** Stable key + labels; retrievable by exact key, by label, or
   by similarity.
3. **The context window is bounded and rebuilt from memory each cycle** — never an unbounded transcript.
4. **Tools are real and model-chosen.** Every call and its result is logged; a failed tool returns its
   error to the model instead of silently falling back to a blind A-press.
5. **Bounded by construction.** Caps on window size, tool calls per cycle, retrieval count, subagent
   budget — so cost per cycle stays predictable and the benchmark stays comparable.
6. **No status surface may report health it did not verify.** (See the three phantom greens already
   recorded in this project's rows.)

---

## 2. Memory contract (DuckBrain)

### 2.1 Namespaces

- `pokemon-global` — cross-run, world-level truth (maps, objects, mechanics)
- `pokemon-run:<run_id>` — per-run working memory (goal, failures, current attempt)

### 2.2 Label taxonomy (the labeling scheme the agent must use)

| domain label | holds | written when |
|---|---|---|
| `world/map/<map_id>` | name, exits (tile + destination), landmarks, tiles visited | first visit, and on any new exit found |
| `world/object/<map_id>/<x>_<y>` | object identity, purpose, the interaction result | on `interact` returning text/state change |
| `world/npc/<map_id>/<x>_<y>` | who/what, what they said, what they want | on NPC dialog |
| `world/path/<from_map>-><to_map>` | a *proven* traversable route + the door tile | when a map transition is observed |
| `world/dialog/<text_hash>` | dialog text + the correct response (advance / yes-no / menu) | on read_dialog |
| `world/mechanics/<topic>` | how the game works (learned, never seeded story) | when the teacher supplies a rule |
| `run/<run_id>/goal` | current goal + the reason for it | on goal set/change |
| `run/<run_id>/failure/<sig>` | a state that produced no progress + what was tried | on the failure trigger |

Every write carries: `key`, `domain`, `attributes` (typed facts), `embedding_text`, `confidence`,
`evidence` (run id, cycle, map, tile), and `applies_when` where the fact is conditional — reusing the
`applies_when` shape the teacher patch layer already proves works.

### 2.3 Retrieval the agent gets as tools

- `memory.get(key)` — exact
- `memory.query(labels=[...], limit=N)` — by label/domain
- `memory.search(text, limit=N)` — by similarity

Retrieval must work **after a process restart** — i.e. it reads the store, not in-process state.

---

## 3. Context window contract

Each cycle's request is assembled, bounded, and logged:

1. `system` — role + how the game works (unchanged; no story)
2. **rolling window** — the last *N* turns as (decision, action, result) triples; default `N=12`
3. **compressed summary** — earlier turns of this run, rebuilt as the window slides, capped chars
4. **relevant-memory block** — top-*K* retrieved facts for the current map/tile/screen; default `K=8`
5. current projection + screenshot (respecting the existing frame cache)

Hard caps: window, summary, and memory block each carry a character ceiling, so per-cycle input cost
is predictable and the run cannot silently grow.

---

## 4. Tool surface (model-chosen)

| tool | effect |
|---|---|
| `walk(direction, tiles)` | move, with verification that movement occurred |
| `interact(target)` | press A while facing a tile; return resulting text / state change |
| `read_dialog()` | return the current text-box content verbatim |
| `remember(key, domain, facts, applies_when)` | write a labeled memory |
| `recall(key \| labels \| query)` | retrieve |
| `delegate_research(question, budget)` | spawn a bounded research subagent; return a compressed finding |
| `set_goal(text, reason)` / `check_goal()` | goal bookkeeping |

Rules: the harness executes with verification; every call + result is a decision row (so the autonomy
counters count tool use honestly); a failed call surfaces its error to the model.

---

## 5. Delegation contract

`delegate_research` spawns a bounded subagent: max wall-clock, max tool calls, max cost. It receives
only the question plus declared public context, and may search the web. It returns finding text
(capped), sources, and confidence. The harness compresses the return into `world/*` or `run/*` memory
and injects it into the parent's next context. **Acceptance requires the finding to be consumed in a
LATER cycle** — visible in the log, not asserted.

---

## 6. Stages and acceptance criteria

> **CORRECTION after Quorum #1 (5 seats, 5 families) — read this before the table.**
>
> The first draft of this spec put S3 (context window) and S4 (tool calling) on
> `controller_plan`. **That path does not run.** Verified in raw code and re-verified by the
> coordinator: `cron_runner.py:3554` is `if _jev_decision: decision = _jev_decision` with
> `decision = controller_plan(...)` in the **else** at `:3566`, and `DEFAULT_DECISION_MODE = "jev"`
> (`:110`). JEV answered 100% of the measured decisions, so `controller_plan` is dead code in the
> live loop. **Memory that reaches only the controller prompt cannot move `escalated` or
> `map_topology`, because those are JEV-emitted fields.** S6's metric is structurally immune to
> S3 and S4 as originally written.
>
> The surface that matters is `state_projection.build()` (`src/core/state_projection.py:102`),
> which **already accepts `extra_facts`** (`:111`, consumed `:199-201`) and where `extra_facts`
> appears **nowhere** in `cron_runner.py`. The plumbing is built and unwired. That is the missing
> stage, and it is added below as **S2b `MEM-PROJ`**.
>
> Corrected facts (the earlier draft's numbers were wrong and are kept here so the error is
> auditable): the store holds **617 active unique keys** — 555 `/game/runs/*`, 50 `/notes/*`,
> 3 `/game/save/*`, **0 `/world/*`** — not "~50 keys". The old count came from
> `duckbrain_client.list_keys`'s default `limit: int = 50` (`:113`) silently truncating.
> Memory is also **not** end-of-run-only: `_apply_agent_memory_outputs` (`:2209`) is called
> per-cycle at `:3595`, and a `study` field reads a key mid-run into the next cycle. What is
> missing is not *writing* — it is **labeled retrieval reaching the fast tier**.

| stage | id | acceptance |
|---|---|---|
| **S0** control baseline | `BASE-1` | a baseline artifact names boot state, cycles/episode, decision-mode and model, with escalations-per-map-transition over ≥N episodes from a CLEAN store — **before S2**, so S6 has something to beat |
| **S1** memory API | `MEM-API` | a written fact is retrievable by key AND by label AND by similarity, **after a process restart** |
| **S2** memory population | `MEM-POP` | a 30-cycle run writes ≥1 `world/map/*` and ≥1 `world/object/*`; the NEXT cycle retrieves one. **Deterministic writers on observed map transitions**, not model goodwill — `/notes/*` already tries to record exits and still fails to structure them |
| **S2b** memory reaches the fast tier | `MEM-PROJ` | a run log shows the **JEV projection** carrying ≥1 retrieved `world/*` fact via `state_projection.build(extra_facts=...)`, and that class's escalation rate falls against S0 |
| **S3** context window | `CTX-WIN` | the log shows prior turns in the request, and the agent answers about a cycle >N back from the summary |
| **S4** tool calling | `TOOLS-1` | the log shows ≥1 **model-chosen** tool call with its result; a failed call is visible to the model |
| **S5** delegation | `DELEG-1` | ≥1 delegated finding written to memory and **consumed in a later cycle** |
| **S6** memory-driven navigation | `NAV-MEM` | using `world/map/*` + `world/path/*`, cycles-to-first-map-transition drops vs the **S0** baseline, and the route is cited from memory |
| **S7** benchmark parity | `BENCH-PAR` | both `--decision-mode jev` and `llm` run the new loop; mode stamped; logs comparable — **run before S6 is judged**, so the effect is attributable |

**Dependencies (corrected):** S0 → S1 → S2 → S2b → S6; {S3, S4} branch off S2 and do **not** gate S6;
S5 after S4; S7 before the S6 verdict.
S5 delegation is **not** a precondition for navigating a room already walked — the old
`NAV-MEM depends_on [CTX-WIN, DELEG-1]` ordering was backwards and is fixed on the board.

---

## 7. Non-goals

- No seeded story or walkthrough content — mechanics only.
- Not a replacement for the JEV fast tier; it remains the default decision path.
- No unbounded transcript growth; the window is rebuilt, not accumulated.
- Not a change to the pure-LLM benchmark's meaning — the benchmark gets the same tool surface, or its
  logs say explicitly which surface it ran with.
