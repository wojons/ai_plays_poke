# Agentic status — where the AI Plays Pokémon agent actually is

You asked for four things: a real **turn chain** (context window), real **tool
calling**, **DuckBrain as store-and-retrieve memory**, and **subagent
delegation** — plus a win, with the **pure-LLM benchmark** kept runnable.

This report separates what exists from what was described. Every number here was
read out of the tree, the run logs, or the board during this session. The
uncomfortable ones are included.

## The state in five lines

- The agent plays, for 3 hours and 480 episodes, with **0 errors** — and escalates **99.5% of its decisions**.
- It has left Pallet Town **exactly once**, and that once was because a **credential failed** and the fallback path took over.
- Of your four asks: **one is built and never used**, **one has a substrate with zero world facts in it**, and **two do not exist at all**.
- Five independent models judged my written plan and **contradicted it three times** — including its central mechanism.
- The goal (Viridian City) is **not reached**. The agent can leave Pallet Town and cannot stay gone.

## Your four asks, against the tree

| What you asked for | Reality | Evidence |
|---|---|---|
| A turn chain / context window | **Absent** — every decision is a fresh single-turn request: system + user, no history, no transcript | `cron_runner.py` sends `messages=[system, user]` at 4 sites; zero matches for history/conversation/transcript |
| Real tool calling | **Built, never used** — the client supports native function calling; the decision path never passes tools | `src/core/ai_client.py:562,595,710,861` support it; `'tools'` appears **nowhere** inside `controller_plan`; `_battle_tool_call` (`cron_runner.py:996-1005`) is a fixed vocabulary→transport table |
| DuckBrain label → store → retrieve | **Substrate present, empty of world facts** — the API exists and is written to per-cycle; nothing labeled about the world is in it, and it never reaches the fast tier | `duckbrain_client.py:28,61,110,149,160` (remember/recall/list_keys/get/search); 617 active keys, **0 under `/world/*`**; `state_projection.build(extra_facts=...)` exists at `state_projection.py:111` and `extra_facts` appears **nowhere** in `cron_runner.py` |
| Subagent delegation | **Absent** — zero matches for subagent/delegate/research across `cron_runner.py` and all of `src/core/` | measured grep, 0 hits |
| Win the game | **Not won** — Route 1 reached, Viridian never | run totals below |
| Pure-LLM benchmark kept | **Done** — `--decision-mode jev\|llm`; in `llm` mode the fast tier is never called and every row is stamped | committed `61e96a2`; `tests/test_decision_mode.py` |

## The turn chain — your specific question

You asked: *"are you giving the agent the turns and past events like a coding
agent context window chain?"* The answer at the time was **no**, and it is still
no. What the agent actually gets each cycle:

- the current state, read from emulator RAM (free, instant);
- a **capped** store of memory notes — and the cap is the point;
- the goal string;
- its last action.

There is **no history of its own reasoning**. If it worked out that a door leads
outside on cycle 4, cycle 5 does not contain cycle 4. The only continuity is what
was explicitly written into the capped notes, and the one `study` field that can
fetch a single key into the *next* cycle — a one-step lookup, not a window.

A coding agent's context window accumulates: turn N sees turns 1..N-1. This
harness rebuilds a small package from scratch every cycle. That difference is
the whole of the "agentic" gap, and it is why the same room gets re-derived
every episode.

## The three-hour run — real numbers

Run `long_0926_0014`, 180-minute budget, completed at 100.1%.

| Metric | Value |
|---|---|
| Episodes | 480 |
| Decisions | 14,598 |
| Escalated | 14,524 (**99.5%**) |
| Teacher calls | 518 |
| Teacher repairs that improved state | **0** |
| `map_topology` share of escalations | 13,937 (**96%**) |
| Decisions made unaided | **74 (0.01)** |
| Errors | 0 |
| Goal | not achieved |

Two readings of that table matter. The teacher was invoked 518 times to repair
exactly the missing class and **never once registered an improvement** — escalation
is a treadmill, not a repair loop. And `map_topology` at 96% means the agent is
re-deriving the same world fact, over and over, and paying a teacher call each time.

## Route 1 — the one time it left, and why

The agent reached **Route 1 at episode 203**, stayed 6 episodes, then fell back to
Pallet Town and ended all 271 later episodes there. For an hour I did not know why
that window happened, and I said so rather than guess.

It was measured: **`OR_JEV` returned `HTTP 403 — RBAC: access denied`** on episodes
202-205. JEV answered *nothing* in ep203 (28/28 decisions) and ep204 (25/25), so the
harness fell through to `controller_plan` — the LLM controller — and **the
controller navigated out of Pallet Town.**

That is a natural A/B nobody designed:

| Path | Episodes | Outcome |
|---|---|---|
| JEV answering everything | 208 of 212 | **never left Pallet Town in 202 episodes** |
| JEV dead, controller running | 2 | **Route 1 at cycle 18 of ep203, 0 escalations** |

The same state JEV escalates on 96% of the time was sufficient for the controller
to walk out. The bottleneck is the JEV projection, not the information available.

## The controlled experiment

The natural A/B had a confound — the driver chains episodes, so ep203 started from
wherever ep202 ended. So I ran it properly: **`--decision-mode llm`, 30 cycles, in
an isolated git worktree, from the same boot state** the baseline used (md5
verified identical, `81e4ec4e…`).

Result: **Route 1 at cycle 13.**

| Path | Cycles to first Route 1 | Per transition |
|---|---|---|
| JEV (baseline) | ~6,060 (202 episodes) | 786 escalations |
| Controller (`llm`) | **13** | 27 decisions |

The caveats are real and recorded in the artifact: **n=1**; the transition was
**not held** (back in Pallet Town by c22); the controller **also** struggles
(direction-locking warned on 47% of cycles); and `0 escalations` in `llm` mode is
true by construction, so cycles-to-transition is the only comparable metric.

## Five independent models reviewed the plan — and caught me

I ran a quorum: 5 judge seats, 5 distinct model families, one shared claim
checklist. Three claims met quorum as CONTRADICTED, all against my own draft, and
I re-verified each against raw code before accepting it.

| Claim I made | Verdict | What was true |
|---|---|---|
| Memory is written only at end-of-run | **CONTRADICTED (4 families)** | It is written **per-cycle** (`_apply_agent_memory_outputs`, called at `:3595`) plus a mid-run `study` read |
| The store holds ~50 keys | **CONTRADICTED (3 families)** | **617** active keys. My number came from `list_keys`'s default `limit=50` truncating silently — the phantom-green class, inside the audit written to catch it |
| The plan targets the right decision surface | **CONTRADICTED** | It did not. `controller_plan` is in the **`else`** branch; default mode is `jev`; so **S3/S4 were specified against code the live loop never runs** |

The third one is the one that mattered: my spec pointed at the wrong surface, and
`extra_facts` — the hook that would fix it — sits built and unwired at
`state_projection.py:111`.

## What changed as a result

- **The spec was retargeted** to the JEV projection, with the wrong numbers **kept in the document** so the error stays auditable.
- **`MEM-PROJ` was added** — the missing stage: retrieved world facts must reach `state_projection.build(extra_facts=…)`.
- **`BASE-1` now comes first** — the baseline a later claim must beat, which the plan previously lacked entirely.
- **`HOLD-1` was added** — holding a transition is a different problem from making one, and nothing covered it.
- **`JEV-403` was found and fixed** — commit `17402d7`: degradation is now stamped per-row and alarmed loudly, with an auth preflight that fails **before** the emulator boots. Judged PASS.

## The board — what the foreman picks up

139 tasks (99 complete, 40 pending), dependency-chained so the work cannot be
taken out of order:

- `SPEC-AGENTIC` ✅ → `BASE-1` (control baseline) ✅ → `MEM-API` (S1)
- `MEM-API` → `MEM-POP` (S2) → `MEM-PROJ` (S2b, the stage that can move the number)
- `{CTX-WIN, TOOLS-1}` branch off S2 and **no longer gate** navigation
- `DELEG-1` (S5) → `BENCH-PAR` (S7) → **before** any navigation verdict
- `NAV-MEM` (S6) now requires `HOLD-1` — escaping is not winning

## What moved and what did not

**Moved:** the diagnosis, the plan's correctness, the board's ordering, one real
defect fixed (`JEV-403`), and the discovery that the controller path reaches Route 1
in 13 cycles where JEV took 202 episodes.

**Did not move:** the agent still cannot hold Route 1 and has not reached Viridian;
the teacher's repair rate is still **0 across 518 calls**; `/world/*` is still **0**.

## The two decisions waiting on you

1. **Which path to fund for navigation** — give the fast tier the topology it lacks (`MEM-PROJ`, weeks of plumbing), or promote the controller that already proved it can do it (cheap, but every decision becomes a paid LLM call). The distribution experiment below is the tiebreaker.
2. **Teacher repair is broken and nobody knows which side** — 518 calls, 0 improvements. Either the teacher cannot repair this class or the counter cannot increment. `TEACH-1` asks which, and it is cheap.

**Next subgoal:** repeat the experiment as a distribution — N episodes, both modes,
same boot state — because one 30-cycle sample is a signal, not an answer.
