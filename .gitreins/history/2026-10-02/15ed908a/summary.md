# Verdict: QA-CONSOLE-3

**Task:** Wire console QA tools to an unattended runner
**Evaluated:** 2026-10-02T12:03:52.185547
**Result:** ✗ FAIL

## Pipeline Stages

- ✗ **tier1**
  -   ✓ lint: ok (no output)
  ✗ secrets: Command timed out
  ✗ tests: Command timed out
- ✓ **tier2**
  - COMPLETE
  ✓ Runner starts console if down, runs test_controls+test_pass, fails loudly on non-200/ignored toggle, explicitly skips movement buttons: tools/console/run_qa.py (commit 7c9ea78) satisfies all four parts. (1) Starts console if down: _ensure_console() (lines 83-107) checks GET /api/health via _healthy(), runs `systemctl --user start aipp-console.service`, and polls 30s. (2) Runs both tools: main() calls _run_tool(TOOLS/'test_controls.py') and _run_tool(TOOLS/'test_pass.py', block_movement=True). (3) Fails loudly: executed _validate_control_results with a 500 stub -> ['GET /api/state returned HTTP 500, expected 200']; executed _toggle_round_trips with an ignored toggle -> 4 failure strings ('POST /api/live ignored on=False: echo=None, state=False'); main() prints FAIL lines and returns 1. (4) Skips movement: _movement_safe_urlopen blocks /api/press, _movement_safe_run blocks the save-state restore, and _validate_pass_results prints 'SKIP | <name> [movement changes game state]' for the 3 MOVEMENT_RESULTS (proven: returned [] with all 3 movement rows marked FAIL). Dry-run executed: `.venv/bin/python tools/console/run_qa.py --dry-run` -> exit 0, output 'SKIP: movement button request blocked; unattended QA must not change game state' and 'PASS: unattended movement skip path is active'. Contracts confirmed: test_controls.py exposes CHECKS (line 61) + call (line 24); test_pass.py exposes RESULTS (line 26) with the 3 movement result names (lines 215/222/326). No pytest test for the runner exists, but the criterion text does not require one and behavior was verified by direct execution.
The unattended console QA runner is fully wired: it health-checks/starts the console, runs test_controls and test_pass, fails loudly on non-200 or ignored toggles, and explicitly blocks/skips movement buttons — all verified by execution.

## Summary

Judge Result: QA-CONSOLE-3

Stage tier1: FAIL
    ✓ lint: ok (no output)
  ✗ secrets: Command timed out
  ✗ tests: Command timed out

Stage tier2: PASS
  COMPLETE
  ✓ Runner starts console if down, runs test_controls+test_pass, fails loudly on non-200/ignored toggle, explicitly skips movement buttons: tools/console/run_qa.py (commit 7c9ea78) satisfies all four parts. (1) Starts console if down: _ensure_console() (lines 83-107) checks GET /api/health via _healthy(), runs `systemctl --user start aipp-console.service`, and polls 30s. (2) Runs both tools: main() calls _run_tool(TOOLS/'test_controls.py') and _run_tool(TOOLS/'test_pass.py', block_movement=True). (3) Fails loudly: executed _validate_control_results with a 500 stub -> ['GET /api/state returned HTTP 500, expected 200']; executed _toggle_round_trips with an ignored toggle -> 4 failure strings ('POST /api/live ignored on=False: echo=None, state=False'); main() prints FAIL lines and returns 1. (4) Skips movement: _movement_safe_urlopen blocks /api/press, _movement_safe_run blocks the save-state restore, and _validate_pass_results prints 'SKIP | <name> [movement changes game state]' for the 3 MOVEMENT_RESULTS (proven: returned [] with all 3 movement rows marked FAIL). Dry-run executed: `.venv/bin/python tools/console/run_qa.py --dry-run` -> exit 0, output 'SKIP: movement button request blocked; unattended QA must not change game state' and 'PASS: unattended movement skip path is active'. Contracts confirmed: test_controls.py exposes CHECKS (line 61) + call (line 24); test_pass.py exposes RESULTS (line 26) with the 3 movement result names (lines 215/222/326). No pytest test for the runner exists, but the criterion text does not require one and behavior was verified by direct execution.
The unattended console QA runner is fully wired: it health-checks/starts the console, runs test_controls and test_pass, fails loudly on non-200 or ignored toggles, and explicitly blocks/skips movement buttons — all verified by execution.

Overall: FAIL ✗
