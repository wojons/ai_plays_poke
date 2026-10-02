# Verdict: E2E-001-T265

**Task:** E2E-001 recurring acceptance run (tick 265)
**Evaluated:** 2026-10-02T08:30:16.868622
**Result:** ✗ FAIL

## Pipeline Stages

- ✗ **tier1**
  -   ✓ lint: ok (no output)
  ✓ secrets: secrets: harness state excluded from gitleaks scope (.gitreins/**)
  ✗ tests: Command timed out
- ✓ **tier2**
  - COMPLETE
  ✓ 80-cycle live run completes with runner exit 0; measured peak RSS (ps sampling) reported and below 300MB; HSM spam 0; run JSONL and evidence written to cron_logs/: 80-cycle run verified: cron_logs/run_e2e001_t265.jsonl has all cycles 1-80 (80 cycle rows) plus a terminal run_autonomy row (decisions_total=80, jev_answered=80, autonomy_ratio=1.0); /tmp/ai_plays_poke_t265_run.log ends with '[e2e001_t265] Done. 187 actions...' and frame-cache save, with 0 tracebacks — run_autonomy/Done are emitted at the end of main() (cron_runner.py:5754-5800), so exit 0. RSS measured via genuine ps sampling: /tmp/ai_plays_poke_t265_e2e.sh runs `ps -o rss= -p $PID` every 10s and captures RC=$?; /tmp/ai_plays_poke_t265_rss.txt holds 4 samples [15468,84016,85128,86496] KB → peak 86496KB = 84.5MB < 300MB. HSM spam = 0: grep 'Invalid transition attempted' (src/core/state_machine.py:636) returns 0 in both the JSONL and the run log. Artifacts present in cron_logs/: run_e2e001_t265.jsonl (728351 bytes) and e2e001_20261002_t265_evidence.md (1646 bytes). Focused tests pass: ./.venv/bin/pytest tests/test_e2e_l2_acceptance.py tests/test_cron_runner_metrics.py -q => 72 passed in 0.51s.
The 80-cycle E2E-001 tick-265 run is fully evidenced: exit 0, ps-sampled peak RSS 84.5MB (<300MB), HSM spam 0, and both JSONL and evidence artifacts written to cron_logs/.

## Summary

Judge Result: E2E-001-T265

Stage tier1: FAIL
    ✓ lint: ok (no output)
  ✓ secrets: secrets: harness state excluded from gitleaks scope (.gitreins/**)
  ✗ tests: Command timed out

Stage tier2: PASS
  COMPLETE
  ✓ 80-cycle live run completes with runner exit 0; measured peak RSS (ps sampling) reported and below 300MB; HSM spam 0; run JSONL and evidence written to cron_logs/: 80-cycle run verified: cron_logs/run_e2e001_t265.jsonl has all cycles 1-80 (80 cycle rows) plus a terminal run_autonomy row (decisions_total=80, jev_answered=80, autonomy_ratio=1.0); /tmp/ai_plays_poke_t265_run.log ends with '[e2e001_t265] Done. 187 actions...' and frame-cache save, with 0 tracebacks — run_autonomy/Done are emitted at the end of main() (cron_runner.py:5754-5800), so exit 0. RSS measured via genuine ps sampling: /tmp/ai_plays_poke_t265_e2e.sh runs `ps -o rss= -p $PID` every 10s and captures RC=$?; /tmp/ai_plays_poke_t265_rss.txt holds 4 samples [15468,84016,85128,86496] KB → peak 86496KB = 84.5MB < 300MB. HSM spam = 0: grep 'Invalid transition attempted' (src/core/state_machine.py:636) returns 0 in both the JSONL and the run log. Artifacts present in cron_logs/: run_e2e001_t265.jsonl (728351 bytes) and e2e001_20261002_t265_evidence.md (1646 bytes). Focused tests pass: ./.venv/bin/pytest tests/test_e2e_l2_acceptance.py tests/test_cron_runner_metrics.py -q => 72 passed in 0.51s.
The 80-cycle E2E-001 tick-265 run is fully evidenced: exit 0, ps-sampled peak RSS 84.5MB (<300MB), HSM spam 0, and both JSONL and evidence artifacts written to cron_logs/.

Overall: FAIL ✗
