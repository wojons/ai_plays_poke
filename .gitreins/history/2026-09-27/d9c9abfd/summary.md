# Verdict: DIST-1

**Task:** CTRL-WIN as a distribution — N episodes, both modes, same boot state
**Evaluated:** 2026-09-27T10:05:32.348340
**Result:** ✓ PASS

## Pipeline Stages

- ✓ **tier1**
  -   ✓ lint: ok (no output)
  ✓ secrets: secrets: harness state excluded from gitleaks scope (.gitreins/**)
  ✓ tests: ============================= test session starts ==============================
- ✓ **tier2**
  - COMPLETE
  ✓ Both modes have >=5 episodes and cycles-to-transition distributions are reported with spread (not just a mean), same boot state, per-episode metrics recorded: data/baselines/dist1_ctrlwin_distribution_2026-09-27.json: llm mode n_episodes=6 with cycles_to_first_transition=[6,8,12,15,23,26] and spread={min:6,median:13.5,max:26,stdev:8.05} (real spread, not just a mean); jev mode n_episodes=5, all censored at the 30-cycle cap so spread=null with an explicit spread_note (no fabricated number). Same boot state: boot_md5=81e4ec4e8d1b62002bc78f619c5fc79c stamped on all 11 episode records and matches md5sum of data/baselines/base-1_boot.state. Per-episode metrics recorded for every episode (first_transition_cycle, held_the_transition, map_transitions, direction_lock.rate, cost_usd_observed, boot_md5, etc.). Driver scripts/dist1_episodes.py:229 summarise_distribution computes min/median/max/stdev. Tests: ./.venv/bin/pytest tests/test_dist1_episodes.py -v => 16 passed (incl. test_all_censored_reports_no_fabricated_spread, test_report_writes_both_modes_with_spread); combined with tests/test_system_modes.py => 45 passed. Commit b9d771c documents 6 llm vs 5 jev episodes from one boot state.
DIST-1 is fully satisfied: both modes have >=5 episodes from the identical boot state (md5-verified), the llm cycles-to-transition distribution is reported with min/median/max/stdev spread, the all-censored jev mode honestly reports no spread, and per-episode metrics are recorded with 16 passing unit tests.

## Summary

Judge Result: DIST-1

Stage tier1: PASS
    ✓ lint: ok (no output)
  ✓ secrets: secrets: harness state excluded from gitleaks scope (.gitreins/**)
  ✓ tests: ============================= test session starts ==============================

Stage tier2: PASS
  COMPLETE
  ✓ Both modes have >=5 episodes and cycles-to-transition distributions are reported with spread (not just a mean), same boot state, per-episode metrics recorded: data/baselines/dist1_ctrlwin_distribution_2026-09-27.json: llm mode n_episodes=6 with cycles_to_first_transition=[6,8,12,15,23,26] and spread={min:6,median:13.5,max:26,stdev:8.05} (real spread, not just a mean); jev mode n_episodes=5, all censored at the 30-cycle cap so spread=null with an explicit spread_note (no fabricated number). Same boot state: boot_md5=81e4ec4e8d1b62002bc78f619c5fc79c stamped on all 11 episode records and matches md5sum of data/baselines/base-1_boot.state. Per-episode metrics recorded for every episode (first_transition_cycle, held_the_transition, map_transitions, direction_lock.rate, cost_usd_observed, boot_md5, etc.). Driver scripts/dist1_episodes.py:229 summarise_distribution computes min/median/max/stdev. Tests: ./.venv/bin/pytest tests/test_dist1_episodes.py -v => 16 passed (incl. test_all_censored_reports_no_fabricated_spread, test_report_writes_both_modes_with_spread); combined with tests/test_system_modes.py => 45 passed. Commit b9d771c documents 6 llm vs 5 jev episodes from one boot state.
DIST-1 is fully satisfied: both modes have >=5 episodes from the identical boot state (md5-verified), the llm cycles-to-transition distribution is reported with min/median/max/stdev spread, the all-censored jev mode honestly reports no spread, and per-episode metrics are recorded with 16 passing unit tests.

Overall: PASS ✓
