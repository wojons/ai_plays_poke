# Verdict: E2E-001-T270

**Task:** E2E fixture run T270: 80-cycle live pipeline health check
**Evaluated:** 2026-10-02T22:03:55.839783
**Result:** ✗ FAIL

## Pipeline Stages

- ✗ **tier1**
  -   ✓ lint: ok (no output)
  ✓ secrets: secrets: harness state excluded from gitleaks scope (.gitreins/**)
  ✗ tests: Command timed out
- ✓ **tier2**
  - COMPLETE
  ✓ cron_runner exit 0 with 80 real decisions, autonomy ratio 1.0, measured peak RSS < 300MB via ps sampling, zero invalid-transition spam, starter picked: All six sub-claims reproduced from raw artifacts in /home/kara/ai_plays_poke. (1) EXIT 0: cron_logs/e2e001_20261002_t270_evidence.txt = 'RUN_EXIT=0 PEAK_RSS_KB=86564 SAMPLES=4'; driver /tmp/ai_plays_poke_t270_e2e.sh does `wait $PID; EXIT=$?`. (2) 80 REAL DECISIONS: stdout:420 'real_decisions=80 fallback_decisions=0'; JSONL run_e2e001_20261002_t270.jsonl has exactly 80 per-cycle decision rows and stdout has exactly 80 '[N/80]' markers (grep -c = 80); run_autonomy event decisions_total=80, jev_answered=80. (3) AUTONOMY 1.0: JSONL run_autonomy event {"decisions_total":80,"jev_answered":80,"escalated":38,"autonomy_ratio":1.0,"jev_transport_failures":0,"degraded":false}; stdout 'autonomy=80/80 (38 escalated)'. (4) PEAK RSS VIA ps SAMPLING: /tmp/ai_plays_poke_t270_e2e.sh contains a real `ps -o rss= -p $PID >> "$RSS"` 10s poll loop; cron_logs/e2e001_20261002_t270_rss.txt = [22384,86388,86564,86328]; sort -n|tail -1 = 86564 KB = 84.5 MB < 300MB. (5) ZERO INVALID-TRANSITION SPAM: pattern is src/core/state_machine.py:636 logger.warning('Invalid transition attempted: ...'); grep -ci 'invalid.transition' = 0 on stdout AND 0 on JSONL; also 0 tracebacks/MemoryError. (6) STARTER PICKED: stdout:11 '[STARTER-PICKED] party_count=1 species_hint=Charmander'; JSONL {"cycle":1,"event":"starter_picked","party_count":1,"species_hint":"Charmander","source":"boot_baseline"}. Run is genuinely LIVE, not mocked: 2 real teacher API calls ('API: openai/gpt-5.6-luna | 3826ms | In: 3144 | Out: 313 | $0.001004 | Success: True'), 2 teacher_escalation events with real patches, 67 screenshots, 1000 unique frames; driver contains no mock/patch/fake; artifact mtimes sequential (rss 16:12:58 -> jsonl/stdout 16:13:04 -> evidence 16:13:09). Board corroboration: ai_plays_poke/.coding-hermes/board/events.jsonl:462 tick_summary tick 270 and tasks.jsonl E2E-001 worker_summary/foreman_note record identical numbers. Note: this is a live-run fixture task whose acceptance evidence is the run artifacts themselves (repo test_command ./.venv/bin/pytest -x --tb=short is the 4377-test full suite, not applicable to a live-run criterion); every claimed number was independently recomputed from the raw files.
The T270 live fixture run's raw artifacts independently confirm all six sub-claims: exit 0, 80 real decisions, autonomy_ratio 1.0, ps-sampled peak RSS 84.5MB < 300MB, zero invalid-transition spam, and starter picked at cycle 1.

## Summary

Judge Result: E2E-001-T270

Stage tier1: FAIL
    ✓ lint: ok (no output)
  ✓ secrets: secrets: harness state excluded from gitleaks scope (.gitreins/**)
  ✗ tests: Command timed out

Stage tier2: PASS
  COMPLETE
  ✓ cron_runner exit 0 with 80 real decisions, autonomy ratio 1.0, measured peak RSS < 300MB via ps sampling, zero invalid-transition spam, starter picked: All six sub-claims reproduced from raw artifacts in /home/kara/ai_plays_poke. (1) EXIT 0: cron_logs/e2e001_20261002_t270_evidence.txt = 'RUN_EXIT=0 PEAK_RSS_KB=86564 SAMPLES=4'; driver /tmp/ai_plays_poke_t270_e2e.sh does `wait $PID; EXIT=$?`. (2) 80 REAL DECISIONS: stdout:420 'real_decisions=80 fallback_decisions=0'; JSONL run_e2e001_20261002_t270.jsonl has exactly 80 per-cycle decision rows and stdout has exactly 80 '[N/80]' markers (grep -c = 80); run_autonomy event decisions_total=80, jev_answered=80. (3) AUTONOMY 1.0: JSONL run_autonomy event {"decisions_total":80,"jev_answered":80,"escalated":38,"autonomy_ratio":1.0,"jev_transport_failures":0,"degraded":false}; stdout 'autonomy=80/80 (38 escalated)'. (4) PEAK RSS VIA ps SAMPLING: /tmp/ai_plays_poke_t270_e2e.sh contains a real `ps -o rss= -p $PID >> "$RSS"` 10s poll loop; cron_logs/e2e001_20261002_t270_rss.txt = [22384,86388,86564,86328]; sort -n|tail -1 = 86564 KB = 84.5 MB < 300MB. (5) ZERO INVALID-TRANSITION SPAM: pattern is src/core/state_machine.py:636 logger.warning('Invalid transition attempted: ...'); grep -ci 'invalid.transition' = 0 on stdout AND 0 on JSONL; also 0 tracebacks/MemoryError. (6) STARTER PICKED: stdout:11 '[STARTER-PICKED] party_count=1 species_hint=Charmander'; JSONL {"cycle":1,"event":"starter_picked","party_count":1,"species_hint":"Charmander","source":"boot_baseline"}. Run is genuinely LIVE, not mocked: 2 real teacher API calls ('API: openai/gpt-5.6-luna | 3826ms | In: 3144 | Out: 313 | $0.001004 | Success: True'), 2 teacher_escalation events with real patches, 67 screenshots, 1000 unique frames; driver contains no mock/patch/fake; artifact mtimes sequential (rss 16:12:58 -> jsonl/stdout 16:13:04 -> evidence 16:13:09). Board corroboration: ai_plays_poke/.coding-hermes/board/events.jsonl:462 tick_summary tick 270 and tasks.jsonl E2E-001 worker_summary/foreman_note record identical numbers. Note: this is a live-run fixture task whose acceptance evidence is the run artifacts themselves (repo test_command ./.venv/bin/pytest -x --tb=short is the 4377-test full suite, not applicable to a live-run criterion); every claimed number was independently recomputed from the raw files.
The T270 live fixture run's raw artifacts independently confirm all six sub-claims: exit 0, 80 real decisions, autonomy_ratio 1.0, ps-sampled peak RSS 84.5MB < 300MB, zero invalid-transition spam, and starter picked at cycle 1.

Overall: FAIL ✗
