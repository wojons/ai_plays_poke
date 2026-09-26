# SPEC — Decision modes: System One alone, System Two alone, and the hybrid with handoff toggles

**Status:** design authority. Written before the build; the board rows come from it.
**Owner ask:** "support for both system one and system two ai models — jev is system one — we
need the ability to do system one only, system two only a normal llm, system one with system two
with toggles to control settings of when to hand off etc."

## 0. What exists today (measured, not assumed)

`cron_runner.py:110-113`:

```
DEFAULT_DECISION_MODE = "jev"
DECISION_MODES = ("jev", "llm")
```

Two values, and **neither is what the ask describes**:

- `"jev"` is not System One — it is the **hybrid**. JEV decides and may hand off to the teacher.
- `"llm"` is System Two alone, which is right, but it is named for the benchmark rather than the role.
- **There is no way to run System One alone.** With `jev`, a handoff is always possible; the fast tier
  can never be measured on its own.

The handoff decision already lives in code, in `src/core/jev_client.py` — `should_escalate()` with
**three independent triggers, any one sufficient** (`jev_client.py:342-381`):

1. **FAILURE** — the last action changed nothing (`last_action_changed_state`). Fires regardless of
   confidence.
2. **SELF-REPORTED GAP** — JEV says its state is insufficient, or names a `missing_class`.
3. **LAYERED GATE** — low `action_confidence` AND high ambiguity agree, with the thresholds in code,
   never in the model: `ESCALATE_THRESHOLD = 0.50`, `AMBIGUITY_GATE = 0.40` (`jev_client.py:38-39`).
   For irreversible phases (battle move, menu commit) low confidence alone is sufficient.

So the triggers Bane wants toggleable already exist and are individually identifiable. The work is to
**name them, expose them, and stamp which one fired on every row.**

## 1. The three modes

| mode | alias | who decides | fast tier called | teacher reachable |
|---|---|---|---|---|
| `system1` | — | JEV every cycle | yes, every cycle | **never** |
| `system2` | `llm` | the LLM controller every cycle | **never** | n/a (the LLM is already deciding) |
| `system1+system2` | `jev` | JEV, handing off on a trigger | yes, every cycle | yes, on trigger |

Back-compat is a hard requirement: `--decision-mode jev` and `--decision-mode llm` keep their current
meaning, because every existing run, artifact and baseline cites them. The new names are added, not
substituted, and the alias is recorded in the row.

**`system1` is the mode that does not exist yet**, and it is the one that answers a live question:
JEV escalates ~99% of decisions, and with handoff disabled we find out what it does unaided instead of
how often it refuses. That number is currently unknown.

## 2. The handoff toggles

Meaningful in `system1+system2` only. Each maps to a trigger that already exists:

| toggle | default | what it controls |
|---|---|---|
| `--handoff` | `any` | `off` (≡ `system1`), `failure`, `gap`, `confidence`, `any` — which trigger families may fire |
| `--handoff-confidence` | `0.50` | the action-confidence floor (`ESCALATE_THRESHOLD`) |
| `--handoff-ambiguity` | `0.40` | the ambiguity gate (`AMBIGUITY_GATE`) |
| `--handoff-classes` | all | comma list of `missing_class` values allowed to hand off, e.g. `map_topology` |
| `--teacher-max-per-episode` | none | a hard budget; on exhaustion the run continues on JEV and says so |
| `--teacher-model` | current default | unchanged, listed for completeness |

Env equivalents mirror the existing pattern (`AIPP_DECISION_MODE` / `CRON_DECISION_MODE`), resolved
**flag > env > default** exactly as `resolve_decision_mode` already does.

**Every toggle must be visible in the log, not just honoured.** A row carries which trigger fired
(`jev_escalate_reason` exists today; it must be present on *every* escalated row, including
failure-triggered ones) and the effective policy values for the run.

## 3. Acceptance criteria (falsifiable)

- **M1** — a `system1` run has `teacher_calls == 0` and every decision row carries
  `decision_mode=system1`. *Falsifier: any teacher call in a system1 run.*
- **M2** — a `system2` run has `jev_answered=false` on **every** row and zero fast-tier spend.
  *Falsifier: any row with `jev_answered=true`.*
- **M3** — a `system1+system2` run stamps, on every escalated row, **which trigger fired**.
  *Falsifier: an escalated row with no trigger named.*
- **M4** — the toggles bind: with `--handoff failure`, the count of escalated rows whose trigger is
  not `failure` is **zero**. *Falsifier: any escalated row from another trigger.*
- **M5** — the policy is recoverable from the log alone: mode, handoff families, thresholds and
  class filter are recorded in the run's own output. *Falsifier: a run whose mode cannot be
  determined from its log.*
- **M6** — back-compat: `--decision-mode jev` and `llm` produce byte-identical behaviour to before
  this change on the same inputs. *Falsifier: any diff in an existing mode's rows.*

M6 is the regression guard and it is the one to run first: it protects every committed baseline,
including `base-1_long_0926_0014.json` and `ctrl-win_2026-09-26.json`.

## 4. What this is for

The measured state is that JEV answers ~99% of decisions and escalates ~99% of them, with the teacher
repairing **0 of 518** calls. Two questions follow, and this spec exists to make both answerable by a
single flag rather than an argument:

1. **How good is System One alone?** Currently unmeasurable. `system1` measures it.
2. **Is the handoff helping at all?** `system1` vs `system1+system2` on the same boot state answers
   whether the teacher earns its cost, using the escalation rate as the metric.

Neither requires new model plumbing — only the three modes and the triggers that already exist being
named, exposed, and stamped.

## 5. Non-goals

- No new escalation reason invented; the three triggers are the whole set.
- No change to any threshold's default value; the defaults stay `0.50` / `0.40` so cross-run
  comparisons stay valid.
- No change to what the teacher returns, or to teacher state repair.
- Prompts still describe mechanics only — no story content.
