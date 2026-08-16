# Verdict: GAP-024

**Task:** ram_map_server boots to name_entry, not overworld
**Evaluated:** 2026-08-16T20:55:12.164737
**Result:** ✗ FAIL

## Pipeline Stages

- ✗ **tier1**
  -   ✓ lint: 
  ✗ secrets: [90m3:47PM[0m [32mINF[0m [1mscanned ~173936285 bytes (173.94 MB) in 8.03s[0m
[90m3:47PM[0m 
  ✓ tests: ============================= test session starts ==============================
platform linux -- P
- ✓ **tier2**
  - COMPLETE
  ✓ Boot is deterministic: after server start, /data.json screen_type is not name_entry (overworld / Red's House 2F reached via enter_name+submit_name or known-good boot.state): ram_map_server.py boot_emulator() calls _advance_to_overworld() which drives through Gen 1 player+rival name-entry screens (enter_name('ASH')/submit_name()) to overworld, raising if not reached after max_cycles. Test test_boot_emulator_wires_advance (tests/test_ram_map_server.py) verifies wiring; commit 632458b msg confirms live boot landed Red's House 2F screen_type=overworld.
  ✓ POST /input endpoint accepts button presses and drives the emulator (viewer can actually play): handle_input() in ram_map_server.py accepts {"button":..}/{"buttons":..}/{"combo":..} with optional frames, drives emulator via press_button()/combo(), returns 200 ok:true or 400 on bad payloads; do_POST routes /input. ram_map_viewer.html button row wired to POST /input via fetch (lines 295-311). 19 unit tests pass covering all cases.
  ✓ usability-tests.md BLOCK 2 claim updated to match real boot behavior: .coding-hermes/usability-tests.md lines 26/30 updated: 'Emulator deterministically reaches overworld state after title bypass + intro skip + name-entry progression (player & rival name screens, GAP-024)' and result notes real boot 2026-08-16 lands Red's House 2F screen_type=overworld NOT the previous stuck name_entry.
  ✓ Full test suite passes (pytest tests/ -q), mypy clean, ruff clean: ./venv/bin/pytest tests/ -q => 3914 passed, 14 skipped in 166.75s (exit 0). ./venv/bin/mypy src/ --ignore-missing-imports => 'Success: no issues found in 63 source files'. ./venv/bin/ruff check src/ tests/ cron_runner.py ram_map_server.py => 'All checks passed'. LSP diagnostics empty.
GAP-024 complete: ram_map_server deterministically boots past name-entry to overworld via _advance_to_overworld, POST /input drives the emulator with viewer wiring, usability-tests.md BLOCK 2 updated, and full suite (3914 passed), mypy, and ruff are all clean.

## Summary

Judge Result: GAP-024

Stage tier1: FAIL
    ✓ lint: 
  ✗ secrets: [90m3:47PM[0m [32mINF[0m [1mscanned ~173936285 bytes (173.94 MB) in 8.03s[0m
[90m3:47PM[0m 
  ✓ tests: ============================= test session starts ==============================
platform linux -- P

Stage tier2: PASS
  COMPLETE
  ✓ Boot is deterministic: after server start, /data.json screen_type is not name_entry (overworld / Red's House 2F reached via enter_name+submit_name or known-good boot.state): ram_map_server.py boot_emulator() calls _advance_to_overworld() which drives through Gen 1 player+rival name-entry screens (enter_name('ASH')/submit_name()) to overworld, raising if not reached after max_cycles. Test test_boot_emulator_wires_advance (tests/test_ram_map_server.py) verifies wiring; commit 632458b msg confirms live boot landed Red's House 2F screen_type=overworld.
  ✓ POST /input endpoint accepts button presses and drives the emulator (viewer can actually play): handle_input() in ram_map_server.py accepts {"button":..}/{"buttons":..}/{"combo":..} with optional frames, drives emulator via press_button()/combo(), returns 200 ok:true or 400 on bad payloads; do_POST routes /input. ram_map_viewer.html button row wired to POST /input via fetch (lines 295-311). 19 unit tests pass covering all cases.
  ✓ usability-tests.md BLOCK 2 claim updated to match real boot behavior: .coding-hermes/usability-tests.md lines 26/30 updated: 'Emulator deterministically reaches overworld state after title bypass + intro skip + name-entry progression (player & rival name screens, GAP-024)' and result notes real boot 2026-08-16 lands Red's House 2F screen_type=overworld NOT the previous stuck name_entry.
  ✓ Full test suite passes (pytest tests/ -q), mypy clean, ruff clean: ./venv/bin/pytest tests/ -q => 3914 passed, 14 skipped in 166.75s (exit 0). ./venv/bin/mypy src/ --ignore-missing-imports => 'Success: no issues found in 63 source files'. ./venv/bin/ruff check src/ tests/ cron_runner.py ram_map_server.py => 'All checks passed'. LSP diagnostics empty.
GAP-024 complete: ram_map_server deterministically boots past name-entry to overworld via _advance_to_overworld, POST /input drives the emulator with viewer wiring, usability-tests.md BLOCK 2 updated, and full suite (3914 passed), mypy, and ruff are all clean.

Overall: FAIL ✗
