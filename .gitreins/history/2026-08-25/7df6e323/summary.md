# Verdict: e2e-t217

**Task:** E2E-001 window T217-T222 live run
**Evaluated:** 2026-08-25T04:45:09.821531
**Result:** ✗ FAIL

## Pipeline Stages

- ✗ **tier1**
  -   ✓ lint: 
  ✗ secrets: [90m11:41PM[0m [32mINF[0m [1mscanned ~174927864 bytes (174.93 MB) in 7.87s[0m
[90m11:41PM[0m
  ✓ tests: ============================= test session starts ==============================
platform linux -- P
- ✗ **tier2**
  - INCOMPLETE
  ✗ cron_runner.py --run-id e2e_t217 --cycles 20 exits 0 with real LLM decisions (API success), starter-pick or battle milestone logged, no memory-leak regression (RSS flat <300MB), log written to cron_logs/run_e2e_t217.jsonl: Most elements pass: exits 0 (commit 76e08d3 + T217 board event: 'run_e2e_t217 20/20 RUN_EXIT 0'), real LLM decisions (T217 event: '26 API calls 0 failures (luna overworld + deepseek battle loop), ~$0.40 est'), starter-pick AND battle milestones logged (cron_logs/run_e2e_t217.jsonl has starter_picked c1 Charmander, battle_start c15 trainer, battle_end c17), log file exists (11810 bytes, 25 lines, cycles 1-20). BUT the 'RSS flat <300MB' requirement is NOT demonstrated: the only memory evidence is 'ulimit 4GB cap never tripped -> no leak regression' (T217 event + commit). No actual RSS measurement exists for this run — the JSONL log has no RSS/memory field, and no .mem.log/stdout log was produced. A process under a 4GB ulimit can still exceed 300MB RSS. Notably the prior T212 run documented 'peak RSS 109MB flat no leak', showing RSS measurement was the expected standard, but T217 did not record one.
The E2E run completed with exit 0, real LLM API calls, starter-pick and battle milestones logged, and the log file written, but the required 'RSS flat <300MB' memory-leak evidence is absent — only a 4GB ulimit cap is cited, not an actual RSS measurement.

## Summary

Judge Result: e2e-t217

Stage tier1: FAIL
    ✓ lint: 
  ✗ secrets: [90m11:41PM[0m [32mINF[0m [1mscanned ~174927864 bytes (174.93 MB) in 7.87s[0m
[90m11:41PM[0m
  ✓ tests: ============================= test session starts ==============================
platform linux -- P

Stage tier2: FAIL
  INCOMPLETE
  ✗ cron_runner.py --run-id e2e_t217 --cycles 20 exits 0 with real LLM decisions (API success), starter-pick or battle milestone logged, no memory-leak regression (RSS flat <300MB), log written to cron_logs/run_e2e_t217.jsonl: Most elements pass: exits 0 (commit 76e08d3 + T217 board event: 'run_e2e_t217 20/20 RUN_EXIT 0'), real LLM decisions (T217 event: '26 API calls 0 failures (luna overworld + deepseek battle loop), ~$0.40 est'), starter-pick AND battle milestones logged (cron_logs/run_e2e_t217.jsonl has starter_picked c1 Charmander, battle_start c15 trainer, battle_end c17), log file exists (11810 bytes, 25 lines, cycles 1-20). BUT the 'RSS flat <300MB' requirement is NOT demonstrated: the only memory evidence is 'ulimit 4GB cap never tripped -> no leak regression' (T217 event + commit). No actual RSS measurement exists for this run — the JSONL log has no RSS/memory field, and no .mem.log/stdout log was produced. A process under a 4GB ulimit can still exceed 300MB RSS. Notably the prior T212 run documented 'peak RSS 109MB flat no leak', showing RSS measurement was the expected standard, but T217 did not record one.
The E2E run completed with exit 0, real LLM API calls, starter-pick and battle milestones logged, and the log file written, but the required 'RSS flat <300MB' memory-leak evidence is absent — only a 4GB ulimit cap is cited, not an actual RSS measurement.

Overall: FAIL ✗
