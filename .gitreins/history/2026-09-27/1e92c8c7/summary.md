# Verdict: BOOT-1

**Task:** long-run default boot state = measured Pallet Town baseline + explicit decision-mode passthrough
**Evaluated:** 2026-09-27T22:55:13.869419
**Result:** ✗ FAIL

## Pipeline Stages

- ✗ **tier1**
  -   ✓ lint: ok (no output)
  ✗ secrets: Command timed out
  ✓ tests: ============================= test session starts ==============================
- ✗ **tier2**
  - INCOMPLETE
  ✗ worker completes the board row acceptance criteria; full suite green on merged main: Full suite IS green on merged main: `./.venv/bin/pytest tests/ -q` => '4299 passed, 14 skipped in 275.05s' (0 failed), and the work is merged+pushed (8e870a8 merge of wt/BOOT-1, 47f2deb fix; origin/main==HEAD). But the board row BOOT-1 Done-when is only partially met. Done-when requires: 'the driver takes the boot state and the decision mode as explicit arguments (or env with a loud default) AND STAMPS BOTH INTO THE RUN'S STATUS ROW AND PER-EPISODE RECORDS'. Met: BOOT default = data/baselines/base-1_boot.state (Pallet Town) at scripts/long_run.py:50; resolve_boot_state() env override at :126; resolve_decision_mode()/DECISION_MODE at :132/:165; episode_argv() stamps --boot-state and --decision-mode at :147; per-episode row stamps decision_mode at :490. NOT met: boot_state is stamped NOWHERE — `grep '"boot' scripts/long_run.py` returns nothing; the per-episode row dict (long_run.py:486-511) has keys at,episode,run_id,decision_mode,exit_code,... with no boot field; the status row dict (long_run.py:516-547) has keys run_id,updated,goal,ladder,goal_achieved,elapsed_min,duration_target_min,episodes,totals,degraded,degradation,maps_visited,top_missing_classes,last_episode,episode_log,consecutive_identical,loop_warnings — stamping NEITHER boot_state NOR decision_mode at top level. cron_runner.py's own run row (cron_runner.py:2468-2469) likewise stamps decision_mode/decision_mode_family but no boot_state. So the boot state — the central subject of the task — is not recoverable from any run record, and the 'stamps BOTH into the run's status row and per-episode records' requirement is unmet. tests/test_long_run_boot.py (14 passed) only asserts the default path, env override, and argv stamping; it has no test asserting boot_state is stamped into the status row or episode records.
Full suite is green on merged main (4299 passed/14 skipped) and the Pallet Town default + decision-mode argv passthrough landed, but the board row's requirement to stamp BOTH boot state and decision mode into the run's status row and per-episode records is unmet — boot_state is recorded nowhere.

## Summary

Judge Result: BOOT-1

Stage tier1: FAIL
    ✓ lint: ok (no output)
  ✗ secrets: Command timed out
  ✓ tests: ============================= test session starts ==============================

Stage tier2: FAIL
  INCOMPLETE
  ✗ worker completes the board row acceptance criteria; full suite green on merged main: Full suite IS green on merged main: `./.venv/bin/pytest tests/ -q` => '4299 passed, 14 skipped in 275.05s' (0 failed), and the work is merged+pushed (8e870a8 merge of wt/BOOT-1, 47f2deb fix; origin/main==HEAD). But the board row BOOT-1 Done-when is only partially met. Done-when requires: 'the driver takes the boot state and the decision mode as explicit arguments (or env with a loud default) AND STAMPS BOTH INTO THE RUN'S STATUS ROW AND PER-EPISODE RECORDS'. Met: BOOT default = data/baselines/base-1_boot.state (Pallet Town) at scripts/long_run.py:50; resolve_boot_state() env override at :126; resolve_decision_mode()/DECISION_MODE at :132/:165; episode_argv() stamps --boot-state and --decision-mode at :147; per-episode row stamps decision_mode at :490. NOT met: boot_state is stamped NOWHERE — `grep '"boot' scripts/long_run.py` returns nothing; the per-episode row dict (long_run.py:486-511) has keys at,episode,run_id,decision_mode,exit_code,... with no boot field; the status row dict (long_run.py:516-547) has keys run_id,updated,goal,ladder,goal_achieved,elapsed_min,duration_target_min,episodes,totals,degraded,degradation,maps_visited,top_missing_classes,last_episode,episode_log,consecutive_identical,loop_warnings — stamping NEITHER boot_state NOR decision_mode at top level. cron_runner.py's own run row (cron_runner.py:2468-2469) likewise stamps decision_mode/decision_mode_family but no boot_state. So the boot state — the central subject of the task — is not recoverable from any run record, and the 'stamps BOTH into the run's status row and per-episode records' requirement is unmet. tests/test_long_run_boot.py (14 passed) only asserts the default path, env override, and argv stamping; it has no test asserting boot_state is stamped into the status row or episode records.
Full suite is green on merged main (4299 passed/14 skipped) and the Pallet Town default + decision-mode argv passthrough landed, but the board row's requirement to stamp BOTH boot state and decision mode into the run's status row and per-episode records is unmet — boot_state is recorded nowhere.

Overall: FAIL ✗
