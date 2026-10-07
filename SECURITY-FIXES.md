# Security fixes: PYSEC-AI-PLAYS-POKE-20261001

## Scope and scanner method

The repository state at the start of this worktree differed from the 2026-10-01 audit snapshot, so the fresh baseline below is the comparison point for this change.

- Ruff command: `./venv/bin/ruff check . --select S108,PT018,S310 --output-format json`
- Bandit command: Bandit was installed under a temporary `/tmp` target and run recursively while excluding the worktree `venv` symlink and tool caches.
- Bandit names the overlapping rules `B108` and `B310`; it has no `PT018` rule. Ruff is therefore the authoritative three-rule count, while Bandit is a second check for the two security rules.

## Before and after

| Scanner rule | Baseline | After | Reduction |
| --- | ---: | ---: | ---: |
| Ruff S108 | 108 | 0 | 100% |
| Ruff PT018 | 25 | 0 | 100% |
| Ruff S310 | 26 | 0 | 100% |
| Bandit B108 | 108 | 102 | 5.6% |
| Bandit B310 | 18 | 0 | 100% |

The combined Ruff target set fell from 159 findings to 0. All baseline S310 call sites already supplied bounded timeouts; Ruff's S310 finding is a URL-scheme audit rather than a missing-timeout check. Fixed HTTP(S) endpoints are now documented at the call site, and the configurable DuckBrain base URL is explicitly restricted to HTTP(S).

## Changes

### Temporary paths (S108/B108)

- `capture.py`: capture output now uses an unpredictable owner-only `NamedTemporaryFile`.
- `scripts/game_bridge.py`: the default bridge log uses an unpredictable owner-only temporary filename; an explicit `--log` remains unchanged.
- `scripts/jev_projection_probe.py`: projection and escalation evidence use distinct owner-only temporary JSON files.
- `scripts/perception_diff.py`: each invocation writes to its own `mkdtemp` directory, created only when `main()` runs.
- `scripts/smoke_deleg_research.py`: the default evidence path is under a unique `mkdtemp` directory; an explicit `--output` remains unchanged.
- Twelve test modules carry narrow S108 file waivers with an adjacent reason because their literal paths are inert sentinels, mocked collaborator inputs, argv expectations, or database metadata rather than shared temporary-file writes.

### Composite assertions (PT018)

Composite assertions were split without changing their truth conditions in:

- `scripts/smoke_deleg_research.py`
- `tests/test_agentic_loop.py`
- `tests/test_autonomy_counters.py`
- `tests/test_cron_runner_metrics.py`
- `tests/test_dialogue.py`
- `tests/test_gap052_controller_model.py`
- `tests/test_hold_transition.py`
- `tests/test_perf_frame_gate.py`
- `tests/test_phase4_integration.py`
- `tests/test_schemas.py`
- `tests/test_screenshot_manager.py`
- `tests/test_symbols.py`
- `tests/test_system_modes.py`
- `tests/test_teacher_escalation.py`
- `tools/console/test_pass.py`

### URL opens (S310/B310)

- `scripts/backfill_runs.py` now rejects missing, `file:`, FTP, and other non-HTTP(S) base URLs before constructing a request.
- `cron_runner.py`, `src/core/jev_client.py`, `scripts/perception_diff.py`, `scripts/vision_people_probe.py`, and the console diagnostics document fixed HTTP(S) endpoint provenance and retain their existing bounded timeouts.
- `tests/test_security_fixes.py` covers invalid/valid base URL handling, randomized temporary paths, JSON persistence, and owner-only file modes.

## Remaining target findings

Ruff has no remaining S108, PT018, or S310 findings.

Bandit still reports 102 B108 findings. They are deliberately not rewritten because they are test-only inert path values, not production writes:

| File | B108 | Reason |
| --- | ---: | --- |
| `tests/ptp_cli/test_flags.py` | 9 | CLI parsing/forwarding sentinels; no file creation. |
| `tests/test_core_game_loop.py` | 18 | Paths are passed to mocked collaborators. |
| `tests/test_demo_runner.py` | 2 | Deliberately nonexistent error-path sentinels. |
| `tests/test_demo_runner_mocked.py` | 1 | Mocked emulator input; no file creation. |
| `tests/test_exceptions.py` | 2 | Exception context values only. |
| `tests/test_game_database.py` | 39 | ROM and screenshot strings stored as database metadata. |
| `tests/test_game_loop.py` | 16 | Isolated fixtures or mocked collaborator inputs. |
| `tests/test_gameplay_demo.py` | 10 | Validation/error-path sentinels. |
| `tests/test_integration.py` | 1 | Screenshot metadata consumed by a fixture. |
| `tests/test_long_run_boot.py` | 2 | Exact argv forwarding expectations. |
| `tests/test_vision_headless.py` | 1 | Deliberately nonexistent prompt-directory sentinel. |
| `tests/test_vision_integration.py` | 1 | Mock-consumed capture path. |

Other Bandit families remain outside this targeted task: B101 8517, B104 2, B105 9, B110 18, B112 12, B324 11, B404 14, B602 1, B603 18, and B607 4. They were not mass-suppressed or mechanically changed because each needs its own behavior-aware audit rather than being conflated with S108/PT018/S310.

## Verification

- Targeted Ruff scan: 0 findings; full `./venv/bin/ruff check .`: pass.
- `./venv/bin/mypy src/ --ignore-missing-imports`: 0 errors in 68 source files.
- Changed assertion/security batch: 534 passed.
- Test-only path batches: 347 passed; 107 passed and 2 live-ROM tests skipped; 86 passed and 1 live-ROM test skipped.
- `tests/test_integration.py` with a non-secret dummy API-key fixture: 29 passed.
- `tests/test_phase4_integration.py` and `tests/test_vision_integration.py`: direct collection is blocked in this worktree because the gitignored Pokémon ROM is absent; both failures occur before the changed assertions execute. The repository's configured full suite excludes those script-style direct runs and passed 4,457 tests with 15 expected skips.
- Python compilation check for all changed runtime/script modules: pass.
