# Verdict: GAP-053

**Task:** Summary separates real AI decisions from parse_fallback presses
**Evaluated:** 2026-09-23T13:58:08.018022
**Result:** ✗ FAIL

## Pipeline Stages

- ✗ **tier1**
  -   ✓ lint: ok (no output)
  ✗ secrets: secrets: harness state excluded from gitleaks scope (.gitreins/**)
  ✓ tests: ============================= test session starts ==============================
- ✓ **tier2**
  - COMPLETE
  ✓ Final summary line prints real_decisions=N fallback_decisions=M where real = intent not in {parse_fallback, parse_failure_fallback}; DONE line carries real_decisions.: cron_runner.py:989-991 defines FALLBACK_INTENTS = frozenset({"parse_fallback", "parse_failure_fallback"}); cron_runner.py:994-1020 _classify_decision_intents counts real for any row with an 'intent' key whose value is not in FALLBACK_INTENTS (rows lacking 'intent' are skipped), returning (real, fallback). cron_runner.py:1041-1047 _format_summary appends '| real_decisions={real_decisions} fallback_decisions={fallback_decisions}' to the existing 'Done. N actions.' line. Main loop wires it at cron_runner.py:2964 (_classify_decision_intents(results)) -> 2966-2974 (_format_summary(..., real_decisions=..., fallback_decisions=...)) -> 2975 safe_print. The intent values are produced by the real parse path: cron_runner.py:953 sets intent='parse_fallback' and :967 sets intent='parse_failure_fallback', and the main loop stamps intent onto each plan row at cron_runner.py:2430/2550. Direct runtime check: _format_summary('r',6,{'overworld'},0,6,0,real_decisions=2,fallback_decisions=2) => '[r] Done. 6 actions. ... | real_decisions=2 fallback_decisions=2'. Test tests/test_gap053_decision_intent_summary.py::test_summary_line_appends_decision_counts_and_keeps_legacy_shape PASSED.
  ✓ a run summary with known fallback presses shows real_decisions count distinct from total; dead-key run prints real_decisions=0.: tests/test_gap053_decision_intent_summary.py::test_classify_splits_real_from_fallback_decisions builds 4 decision rows (2 fallback, 2 real) plus 2 non-decision rows and asserts _classify_decision_intents(rows) == (2, 2) — real count distinct from the 6-row total. ::test_dead_key_run_counts_every_press_as_fallback builds 23 parse_fallback rows and asserts real == 0, fallback == 23, len(rows) == 23. ::test_dead_key_run_summary_prints_zero_real_decisions asserts 'real_decisions=0' and 'fallback_decisions=23' appear in the formatted line while 'Done. 23 actions.' is preserved. Direct runtime reproduction: _classify_decision_intents on mixed rows => (2, 2); _format_summary('r',23,...,real_decisions=0,fallback_decisions=23) => '... | real_decisions=0 fallback_decisions=23'. Test run evidence: ./venv/bin/pytest tests/test_gap053_decision_intent_summary.py -v => '9 passed in 0.62s'; full suite ./venv/bin/pytest -x --tb=short -q => '3968 passed, 14 skipped in 208.60s' with zero FAILED; LSP diagnostics returned 0 findings.
GAP-053 is fully implemented and verified: _classify_decision_intents splits real vs parse_fallback/parse_failure_fallback presses, the DONE summary line carries real_decisions/fallback_decisions, and both the mixed-run and dead-key-run behaviors are confirmed by passing tests and direct runtime execution.

## Summary

Judge Result: GAP-053

Stage tier1: FAIL
    ✓ lint: ok (no output)
  ✗ secrets: secrets: harness state excluded from gitleaks scope (.gitreins/**)
  ✓ tests: ============================= test session starts ==============================

Stage tier2: PASS
  COMPLETE
  ✓ Final summary line prints real_decisions=N fallback_decisions=M where real = intent not in {parse_fallback, parse_failure_fallback}; DONE line carries real_decisions.: cron_runner.py:989-991 defines FALLBACK_INTENTS = frozenset({"parse_fallback", "parse_failure_fallback"}); cron_runner.py:994-1020 _classify_decision_intents counts real for any row with an 'intent' key whose value is not in FALLBACK_INTENTS (rows lacking 'intent' are skipped), returning (real, fallback). cron_runner.py:1041-1047 _format_summary appends '| real_decisions={real_decisions} fallback_decisions={fallback_decisions}' to the existing 'Done. N actions.' line. Main loop wires it at cron_runner.py:2964 (_classify_decision_intents(results)) -> 2966-2974 (_format_summary(..., real_decisions=..., fallback_decisions=...)) -> 2975 safe_print. The intent values are produced by the real parse path: cron_runner.py:953 sets intent='parse_fallback' and :967 sets intent='parse_failure_fallback', and the main loop stamps intent onto each plan row at cron_runner.py:2430/2550. Direct runtime check: _format_summary('r',6,{'overworld'},0,6,0,real_decisions=2,fallback_decisions=2) => '[r] Done. 6 actions. ... | real_decisions=2 fallback_decisions=2'. Test tests/test_gap053_decision_intent_summary.py::test_summary_line_appends_decision_counts_and_keeps_legacy_shape PASSED.
  ✓ a run summary with known fallback presses shows real_decisions count distinct from total; dead-key run prints real_decisions=0.: tests/test_gap053_decision_intent_summary.py::test_classify_splits_real_from_fallback_decisions builds 4 decision rows (2 fallback, 2 real) plus 2 non-decision rows and asserts _classify_decision_intents(rows) == (2, 2) — real count distinct from the 6-row total. ::test_dead_key_run_counts_every_press_as_fallback builds 23 parse_fallback rows and asserts real == 0, fallback == 23, len(rows) == 23. ::test_dead_key_run_summary_prints_zero_real_decisions asserts 'real_decisions=0' and 'fallback_decisions=23' appear in the formatted line while 'Done. 23 actions.' is preserved. Direct runtime reproduction: _classify_decision_intents on mixed rows => (2, 2); _format_summary('r',23,...,real_decisions=0,fallback_decisions=23) => '... | real_decisions=0 fallback_decisions=23'. Test run evidence: ./venv/bin/pytest tests/test_gap053_decision_intent_summary.py -v => '9 passed in 0.62s'; full suite ./venv/bin/pytest -x --tb=short -q => '3968 passed, 14 skipped in 208.60s' with zero FAILED; LSP diagnostics returned 0 findings.
GAP-053 is fully implemented and verified: _classify_decision_intents splits real vs parse_fallback/parse_failure_fallback presses, the DONE summary line carries real_decisions/fallback_decisions, and both the mixed-run and dead-key-run behaviors are confirmed by passing tests and direct runtime execution.

Overall: FAIL ✗
