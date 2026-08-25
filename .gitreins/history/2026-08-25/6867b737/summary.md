# Verdict: e2e-t217

**Task:** E2E-001 window T217-T222 live run
**Evaluated:** 2026-08-25T04:51:15.381895
**Result:** ✗ FAIL

## Pipeline Stages

- ✗ **tier1**
  -   ✓ lint: 
  ✗ secrets: [90m11:47PM[0m [32mINF[0m [1mscanned ~174463729 bytes (174.46 MB) in 7.82s[0m
[90m11:47PM[0m
  ✓ tests: ============================= test session starts ==============================
platform linux -- P
- ✓ **tier2**
  - COMPLETE
  ✓ cron_runner.py --run-id e2e_t217 --cycles 20 exits 0 with real LLM decisions (API success), starter-pick or battle milestone logged, no memory-leak regression (RSS flat <300MB), log written to cron_logs/run_e2e_t217.jsonl: All sub-requirements evidenced. (1) exits 0: .coding-hermes/board/tasks.jsonl E2E-001 worker_summary 'run_e2e_t217 20/20 RUN_EXIT 0' + commit 76e08d3. (2) real LLM decisions/API success: worker_summary '26 API calls 0 failures ~$0.40'; cron_logs/run_e2e_t217.jsonl shows varied per-cycle intents/plans, 6 frame_cache misses (real decisions), battle select_move actions. (3) starter-pick or battle milestone: run_e2e_t217.jsonl line1 'starter_picked' (cycle1, Charmander boot_baseline) AND line17 'battle_start' (cycle15 trainer) / line20 'battle_end' (cycle17). (4) RSS flat <300MB: worker_summary 'RSS measured peak 109.6MB flat over 7 samples min 19.2MB' (109.6MB<300MB), 'no leak regression', 'Both runs under ulimit 4GB'. (5) log written: cron_logs/run_e2e_t217.jsonl exists (11810 bytes), 25 valid JSONL lines, 20 distinct cycles (1-20) verified via python json parse.
E2E-001 T217 live run fully evidenced: 20/20 cycles RUN_EXIT 0, 26 API calls 0 failures, starter_picked + trainer battle_start/battle_end milestones logged, RSS peak 109.6MB flat (<300MB, no leak regression), and log written to cron_logs/run_e2e_t217.jsonl.

## Summary

Judge Result: e2e-t217

Stage tier1: FAIL
    ✓ lint: 
  ✗ secrets: [90m11:47PM[0m [32mINF[0m [1mscanned ~174463729 bytes (174.46 MB) in 7.82s[0m
[90m11:47PM[0m
  ✓ tests: ============================= test session starts ==============================
platform linux -- P

Stage tier2: PASS
  COMPLETE
  ✓ cron_runner.py --run-id e2e_t217 --cycles 20 exits 0 with real LLM decisions (API success), starter-pick or battle milestone logged, no memory-leak regression (RSS flat <300MB), log written to cron_logs/run_e2e_t217.jsonl: All sub-requirements evidenced. (1) exits 0: .coding-hermes/board/tasks.jsonl E2E-001 worker_summary 'run_e2e_t217 20/20 RUN_EXIT 0' + commit 76e08d3. (2) real LLM decisions/API success: worker_summary '26 API calls 0 failures ~$0.40'; cron_logs/run_e2e_t217.jsonl shows varied per-cycle intents/plans, 6 frame_cache misses (real decisions), battle select_move actions. (3) starter-pick or battle milestone: run_e2e_t217.jsonl line1 'starter_picked' (cycle1, Charmander boot_baseline) AND line17 'battle_start' (cycle15 trainer) / line20 'battle_end' (cycle17). (4) RSS flat <300MB: worker_summary 'RSS measured peak 109.6MB flat over 7 samples min 19.2MB' (109.6MB<300MB), 'no leak regression', 'Both runs under ulimit 4GB'. (5) log written: cron_logs/run_e2e_t217.jsonl exists (11810 bytes), 25 valid JSONL lines, 20 distinct cycles (1-20) verified via python json parse.
E2E-001 T217 live run fully evidenced: 20/20 cycles RUN_EXIT 0, 26 API calls 0 failures, starter_picked + trainer battle_start/battle_end milestones logged, RSS peak 109.6MB flat (<300MB, no leak regression), and log written to cron_logs/run_e2e_t217.jsonl.

Overall: FAIL ✗
