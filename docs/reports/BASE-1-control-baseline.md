# BASE-1 — S0 Control Baseline (jev fast tier)

Recorded: 2026-09-27 · Worktree branch `wt/BASE-1` · Artifact:
`data/baselines/base1_control_2026-09-27.json`

## What this is

The S0 control for the agentic benchmark workstream: **N identical episodes of
`cron_runner.py` on the fast tier**, so later stages have a number to beat.

| consumers      | what they compare against                       |
| -------------- | ----------------------------------------------- |
| CTRL-WIN       | llm-vs-jev at the same boot state and cycles    |
| HOLD-1         | regression guard on the fast tier               |
| BASE-REPIN     | re-pin after decision-logic or store changes    |

## Fixed conditions (identical by construction)

- Decision mode: `--decision-mode jev` (fast tier; the run log's
  `run_autonomy.decision_mode` stamps `jev` per episode)
- Boot state: `data/boot.state` (sha256 recorded per episode in the artifact)
- Episode length: `--cycles 5` (fast tier is cheap — 5 cycles answers the
  identical-boot-state question without burning LLM budget)
- Distinct run ids: `base1_ep<1..5>_20260927` (date suffix keeps re-runs
  resume-safe without colliding with a prior day's episode logs)
- Episodes: 5
- Isolation: before every episode the ROM's SRAM twin
  (`data/rom/*.gb.ram`) is restored from a snapshot taken before episode 1
  (same discipline as `scripts/dist1_episodes.py`), so save-file drift can
  never differentiate episode N from episode 1

## Re-running the baseline

One command from the repo root (`.venv` active):

    .venv/bin/python scripts/run_base1_baseline.py run

then aggregate the episode log it prints into the artifact:

    .venv/bin/python scripts/run_base1_baseline.py report \
        cron_logs/base1_<stamp>_episodes.jsonl

`run` is resume-safe: an episode whose `run_autonomy` summary row already
landed in `cron_logs/run_<id>.jsonl` is skipped, so an interrupted battery
continues where it stopped. `report` refuses to write an artifact from fewer
than 5 episodes — a thin baseline is worse than none.

## Metric provenance

All per-episode metrics are derived from what `cron_runner.py` already writes
to `cron_logs/run_<id>.jsonl` (same field names `scripts/long_run.py` and
`scripts/dist1_episodes.py` read). Nothing is invented:

| metric                          | log source                                        |
| ------------------------------- | ------------------------------------------------- |
| cycles                          | max `cycle` over decision rows                    |
| decisions / `jev_answered`      | per decision row (`missing_class` + `plan`)       |
| escalations (jev)               | `escalated: true` decision rows                   |
| escalations (teacher)           | `teacher_escalation` events (floor: `run_autonomy.teacher_escalations.count`) |
| map transitions                 | consecutive decision rows whose `map_name` changes |
| wall time per episode           | driver-side wall clock around the subprocess      |
| model/provider                  | `teacher_escalation.patch.post_ask.model_build` (jev model identity); `None` with reason when no episode escalated |
| boot state hash                 | sha256 of `data/boot.state` at episode time       |

The jev fast tier escalates most decisions by design (the S0 question is how
many escalations a real map transition costs), so a baseline with zero teacher
escalations legitimately records `model_build_seen: null` with the explicit
reason — that is an honest absence, not a missing field.

## What S0 must show

A healthy S0 has: all episodes completing (`run_autonomy` row present),
transport failures ≈ 0 (`jev_ok` false rows), and identical boot hashes across
episodes. The headline number for CTRL-WIN is
`summary.escalations_per_map_transition`; if no episode left the start map
inside the 5-cycle window the value is `null` with a note, never 0 — an
all-censored baseline cannot price a transition it never observed.
