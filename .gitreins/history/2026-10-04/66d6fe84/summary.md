# Verdict: DOC-6

**Task:** Full CLI Flags table in docs/api/cron_runner.md
**Evaluated:** 2026-10-04T17:44:31.065540
**Result:** ✗ FAIL

## Pipeline Stages

- ✗ **tier1**
  -   ✓ lint: scanners: nice=nice -n 10
  ~ secrets: Command timed out after 120s (step budget)
  ✓ tests: scanners: nice=nice -n 10
- ✓ **tier2**
  - COMPLETE
  ✓ docs/api/cron_runner.md CLI Flags table has a row for every argparse flag in cron_runner.py _main_parser; defaults match help text: AST walk of cron_runner.py _main_parser (lines 4887-5002) yields exactly 14 add_argument calls: --run-id, --cycles, --rom, --boot-state, --dry-run, --skip-key-check, --skip-preflight, --controller-model, --decision-mode, --handoff, --handoff-confidence, --handoff-ambiguity, --handoff-classes, --teacher-max-per-episode. docs/api/cron_runner.md CLI Flags table (lines 81-95) has a row for all 14 (plus -h/--help). Defaults verified against code and live argparse help output: --cycles=20 (CYCLES=20, cron_runner.py:51), --controller-model=openai/gpt-5.6-luna (DEFAULT_CONTROLLER_MODEL, line 65), --decision-mode=jev/system1+system2 (DEFAULT_DECISION_MODE, line 117), --handoff=any (DEFAULT_HANDOFF, line 200), --handoff-confidence=0.50 (line 201), --handoff-ambiguity=0.40 (line 202), --rom default ROM (line 46), --boot-state default data/boot.state (line 47). print_help() confirms '(default 0.5)'/'(default 0.4)' matching doc 0.50/0.40. No subparsers exist. [resolution 0.26; docs/api/cron_runner.md, cron_runner.py]
The CLI Flags table documents every argparse flag in _main_parser with defaults matching the code and help text.

## Summary

Judge Result: DOC-6

Stage tier1: FAIL
  WARNING: coverage is secrets+lint+tests — secrets did not run (skipped at runtime — secrets: timed out after 120s (step budget)); run `gitreins guard` for the full gate
    ✓ lint: scanners: nice=nice -n 10
  ~ secrets: Command timed out after 120s (step budget)
  ✓ tests: scanners: nice=nice -n 10

Stage tier2: PASS
  COMPLETE
  ✓ docs/api/cron_runner.md CLI Flags table has a row for every argparse flag in cron_runner.py _main_parser; defaults match help text: AST walk of cron_runner.py _main_parser (lines 4887-5002) yields exactly 14 add_argument calls: --run-id, --cycles, --rom, --boot-state, --dry-run, --skip-key-check, --skip-preflight, --controller-model, --decision-mode, --handoff, --handoff-confidence, --handoff-ambiguity, --handoff-classes, --teacher-max-per-episode. docs/api/cron_runner.md CLI Flags table (lines 81-95) has a row for all 14 (plus -h/--help). Defaults verified against code and live argparse help output: --cycles=20 (CYCLES=20, cron_runner.py:51), --controller-model=openai/gpt-5.6-luna (DEFAULT_CONTROLLER_MODEL, line 65), --decision-mode=jev/system1+system2 (DEFAULT_DECISION_MODE, line 117), --handoff=any (DEFAULT_HANDOFF, line 200), --handoff-confidence=0.50 (line 201), --handoff-ambiguity=0.40 (line 202), --rom default ROM (line 46), --boot-state default data/boot.state (line 47). print_help() confirms '(default 0.5)'/'(default 0.4)' matching doc 0.50/0.40. No subparsers exist. [resolution 0.26; docs/api/cron_runner.md, cron_runner.py]
The CLI Flags table documents every argparse flag in _main_parser with defaults matching the code and help text.

Overall: FAIL ✗
