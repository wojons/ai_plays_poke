---
title: long_run.py — multi-hour operator driver
---

# `scripts/long_run.py` — multi-hour operator driver

`scripts/long_run.py` chains `cron_runner.py` episodes back to back for hours. It
exists for one failure mode: a marathon that ground through 330 episodes of a
poisoned checkpoint. Every episode's end state is therefore **booted and read back**
before it is allowed to become the next episode's boot state; a state that does not
prove a live overworld map is rejected and the driver falls back to the last one
that passed.

Everything on this page is verified against `scripts/long_run.py` at base commit
`0fbd009`.

> ### ⚠️ `--help` does not print help — it starts a real run
>
> `scripts/long_run.py` has **no argument parser** (no `import argparse`, no
> `argv` handling anywhere in the module). The entry point is:
>
> ```python
> if __name__ == "__main__":
>     raise SystemExit(main())
> ```
>
> `main()` takes no arguments, so `python3 scripts/long_run.py --help`, `-h`, or
> any other flag is **silently ignored and the run starts immediately** — a
> multi-hour run that spawns real `cron_runner.py` subprocesses (and therefore
> spends real LLM calls unless the child preflight fails). There is no help
> screen to accidentally request safely.
>
> To inspect the configuration without starting anything, read the constants
> (`grep -nE '^DURATION_S|^EPISODE_CYCLES|^RUN_ID|^BOOT' scripts/long_run.py`)
> and validate the *child* runner offline:
>
> ```bash
> ./.venv/bin/python cron_runner.py --dry-run --skip-key-check
> ```
>
> which is a separate program with a real parser (see
> [cron_runner](cron_runner.md)).

## Environment keys

The driver is configured **only** by environment variables — there are no flags.
All are read at import time except the boot-state override and the decision mode,
which are resolved by functions (`scripts/long_run.py:126-128` and `:132-144`).

| Env key | Module constant | Default | What it controls |
|---|---|---|---|
| `LONG_RUN_SECONDS` | `DURATION_S` (`long_run.py:34`) | `3 * 3600` (3 hours) | Wall-clock budget for the whole run. The loop stops when `time.time() >= start + DURATION_S` (with a floor of 300 s, minus minutes already elapsed on a resume). One episode cannot overrun its budget by more than the 1800 s per-episode subprocess timeout. |
| `LONG_RUN_CYCLES` | `EPISODE_CYCLES` (`:35`) | `30` | Cycles per episode, forwarded to each child as `cron_runner.py --cycles <N>`. Decision cycles, not seconds. |
| `LONG_RUN_ID` | `RUN_ID` (`:36`) | `long_<MMDD>_<HHMM>` from `datetime.now()` | Label for every output path and for the resume check. Setting it explicitly is what makes a restart *continue* the same run instead of starting a new one. |
| `LONG_RUN_BOOT_STATE` | resolved by `resolve_boot_state()` (`:126-128`) | `data/baselines/base-1_boot.state` (`BOOT`, `:50`) | Explicit boot-state override. An empty value falls back to the default. It only applies while no `long_run/<RUN_ID>_good.state` exists: from the second episode on (and on any restart of the same `LONG_RUN_ID`) the validated good state is what boots. |
| `AIPP_DECISION_MODE` | `DECISION_MODE` via `resolve_decision_mode()` (`:132`) | — (checked first) | Decision-mode arm, forwarded to each episode as `cron_runner.py --decision-mode <mode>`. Highest precedence. |
| `CRON_DECISION_MODE` | same | — (checked second) | Same arm; used when `AIPP_DECISION_MODE` is unset/blank. |
| *(neither set)* | same | `jev` | `resolve_decision_mode()` returns `"jev"` after lower-casing and stripping the chosen value; unrecognised spellings are re-resolved (and degraded to the child's own default) by `cron_runner.py` itself. |

`scripts/long_run.py` keeps its own minimal mirror of `cron_runner`'s
decision-mode precedence (it does not import `cron_runner`), so a restart of the
driver resolves the arm the same way the child would. The resolved value is
stamped into the child argv **and** into every record, so an episode's arm is
recoverable from its log line rather than inferred from ambient environment.

Example — a four-hour run, 40 cycles per episode, explicit label, controller arm:

```bash
LONG_RUN_SECONDS=$((4*3600)) \
LONG_RUN_CYCLES=40 \
LONG_RUN_ID=long_1029_1700 \
AIPP_DECISION_MODE=llm \
  ./.venv/bin/python scripts/long_run.py
```

## Outputs

| Path | Written when | Contents |
|---|---|---|
| `cron_logs/long_run_<RUN_ID>_episodes.jsonl` | one row appended per episode | Episode index, child `run_id`, stamped `decision_mode` and `boot_state`, child `exit_code`, `duration_s`, decisions / JEV-answered / escalated counts, teacher calls and improvements, JEV transport failures and error rows, `degraded` flag, maps seen and the final map, the state-validation verdict, and the goal flag. |
| `long_run_status.json` | rewritten after every episode | Live totals for the whole run (episodes, cumulative decisions/escalations/teacher calls, `jev_failure_rate`, `degraded`, `maps_visited`, `top_missing_classes`), plus `last_episode`, the episode-log path, `consecutive_identical`, and `loop_warnings`. Also **read** at startup: if its `run_id` equals the current `RUN_ID`, the driver resumes the cumulative totals and episode counter instead of zeroing the benchmark. |
| `long_run/<RUN_ID>_good.state` | only when a candidate state passes validation | The last state that proved a live overworld. This, not the newest file on disk, is what the next episode boots from. |

The child also produces its normal per-episode artifacts — `cron_logs/run_<RUN_ID>_epNNN.jsonl`,
screenshots, and checkpoints under `checkpoints/*.state` — which the driver reads
but never rewrites. Every 300 s (and immediately on a goal hit or a new loop
warning) a compressed status row is also written to DuckBrain under
`/game/long-run/<RUN_ID>/status`; that write is best-effort and its failure is
logged without stopping the run.

## Boot-state read-back validation loop

Per episode, after the child exits (`scripts/long_run.py:458-468`):

1. `newest_checkpoint(t0)` (`:168`) picks the newest `checkpoints/*.state` with an
   mtime **after this episode started**. A stale file from a previous episode can
   therefore never be mistaken for this one's progress.
2. `probe_state()` (`:71`) boots that state in a fresh `Emulator`, loads it, ticks
   30 frames, and reads the map back through `RAMReader`
   (`current_map_id` / `current_map_name`, with the map DB as a name fallback).
3. Acceptance is `map_name` resolved **or** `0 <= map_id < 250`. The bounds are
   deliberately inclusive of **0**: Pallet Town is map id 0 (the first map in
   Gen 1), and an exclusive check rejected the most important state in the early
   game — the driver rolled back to a previous map on every episode and replayed
   the same segment forever.
4. Passed → the file is copied over `long_run/<RUN_ID>_good.state` and becomes the
   next boot. Rejected → the log records `state rejected (<error>)` and the run
   chains the last good state instead of the poisoned one. No new checkpoint at
   all → the current boot state is reused.

Validation failure never aborts the run; it is a chaining decision.

## Loop and stop conditions

The episode loop (`:404`) ends on any of:

- wall-clock budget reached (`duration reached — stopping`);
- the goal is reached — `tail_maps()`'s **final** map of an episode contains the
  goal marker (`viridian`), i.e. the run must *end* an episode in Viridian City,
  not merely glimpse it. `maps_visited` is evidence and deliberately does not
  satisfy the goal: a single-cycle sighting used to halt a 4 h window at episode 21;
- 10 000 episodes (the `range` guard).

Three consecutive episodes with an identical `(final_map, decisions, escalated,
teacher_calls)` signature raise a **loop warning** and continue — a stalled game is
a finding to surface, not a reason to quit. `Ctrl+C` is a normal way to stop: the status
file from the last completed episode is already on disk, and re-running with the same
`LONG_RUN_ID` resumes from it (rebuilding the totals, `maps_visited`, and the episode
counter, and continuing from the validated good state).

## Related

- [cron_runner](cron_runner.md) — the per-episode runner this driver spawns, and the
  authority for its flags (including the `--dry-run` exit-code contract).
- [BENCH-1 head-to-head](../reports/BENCH-1-head-to-head-benchmark.md) — the
  decision-arm comparison that consumes the same boot state.
- [E2E-002 L2 acceptance](../e2e-l2-acceptance.md) — the single-episode acceptance
  instrument for the 80-cycle claim.
