# Verdict: E2E-001

**Task:** E2E fixture run tick 285
**Evaluated:** 2026-10-06T15:55:19.894028
**Result:** ✗ FAIL

## Pipeline Stages

- ✗ **tier1**
  -   ✓ lint: scanners: nice=nice -n 10
  ~ secrets: Command timed out after 120s (step budget)
  ✓ tests: scanners: nice=nice -n 10
- ✓ **tier2**
  - COMPLETE
  ✓ cron_runner live run exit 0, 80 cycles, autonomy 80/80, lock-rate 0, peak RSS measured < 300MB: All five sub-conditions verified from measured artifacts. (1) exit 0: cron_logs/e2e_t20261006_1508_evidence.txt line 1 'RUN_EXIT=0'. (2) 80 cycles: cron_logs/run_e2e_t20261006_1508.jsonl has 80 decision rows across distinct cycles 1..80. (3) autonomy 80/80: run_autonomy row in same jsonl => decisions_total=80, jev_answered=80, autonomy_ratio=1.0. (4) lock-rate 0: cron_logs/e2e001_20261003_t275_stdout.log summary 'lock-rate: 0/80 cycles with direction-lock warnings (0%) | real_decisions=80 fallback_decisions=0 autonomy=80/80'; latest run jsonl contains 0 direction-lock entries. (5) peak RSS: e2e_t20261006_1508_evidence.txt 'PEAK_RSS_KB=91108' (91.1 MB < 300MB) from 5 ps samples (19780/88388/89104/90116/91108 KB). Corroborated by cron_logs/e2e001_20261002_t270_evidence.md (exit 0, autonomy_ratio 1.0, peak RSS 86564KB).


## Summary

Judge Result: E2E-001

Stage tier1: FAIL
  WARNING: coverage is secrets+lint+tests — secrets did not run (skipped at runtime — secrets: timed out after 120s (step budget)); run `gitreins guard` for the full gate
    ✓ lint: scanners: nice=nice -n 10
  ~ secrets: Command timed out after 120s (step budget)
  ✓ tests: scanners: nice=nice -n 10

Stage tier2: PASS
  COMPLETE
  ✓ cron_runner live run exit 0, 80 cycles, autonomy 80/80, lock-rate 0, peak RSS measured < 300MB: All five sub-conditions verified from measured artifacts. (1) exit 0: cron_logs/e2e_t20261006_1508_evidence.txt line 1 'RUN_EXIT=0'. (2) 80 cycles: cron_logs/run_e2e_t20261006_1508.jsonl has 80 decision rows across distinct cycles 1..80. (3) autonomy 80/80: run_autonomy row in same jsonl => decisions_total=80, jev_answered=80, autonomy_ratio=1.0. (4) lock-rate 0: cron_logs/e2e001_20261003_t275_stdout.log summary 'lock-rate: 0/80 cycles with direction-lock warnings (0%) | real_decisions=80 fallback_decisions=0 autonomy=80/80'; latest run jsonl contains 0 direction-lock entries. (5) peak RSS: e2e_t20261006_1508_evidence.txt 'PEAK_RSS_KB=91108' (91.1 MB < 300MB) from 5 ps samples (19780/88388/89104/90116/91108 KB). Corroborated by cron_logs/e2e001_20261002_t270_evidence.md (exit 0, autonomy_ratio 1.0, peak RSS 86564KB).


Overall: FAIL ✗
