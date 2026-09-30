# Verdict: LOAD-BRIDGE-1

**Task:** Bound aipp-bridge connection concurrency
**Evaluated:** 2026-09-30T12:02:51.814727
**Result:** ✗ FAIL

## Pipeline Stages

- ✗ **tier1**
  -   ✓ lint: ok (no output)
  ✗ secrets: Command timed out
  ✓ tests: ============================= test session starts ==============================
- ✓ **tier2**
  - COMPLETE
  ✓ Name and reproduce the request path causing the thread leak; replace the unbounded per-connection daemon thread model with bounded concurrency and clean shutdown; add a soak/watchdog verification showing the thread count remains bounded; document the incident and preserve loopback/token security.: All sub-requirements verified. (1) NAMED+REPRODUCED: docs/bridge-thread-incident-2026-09-30.md names the path (console GET /api/stream -> build_state() -> line-delimited {"cmd":"raw"} retry; 1018 R-state threads, loadavg 1015.9 peak) and tests/test_game_bridge.py::test_console_raw_retry_path_is_bounded_and_game_access_is_serialized reproduces it with 12 concurrent raw retries. (2) BOUNDED CONCURRENCY: scripts/game_bridge.py serve() (line 418) replaced per-connection daemon threads with a fixed worker set (DEFAULT_MAX_WORKERS=4, line 53) + bounded queue.Queue(maxsize=max_workers) (line 444); full queue answers {"ok":false,"error":"server busy"} (line 519). (3) CLEAN SHUTDOWN: SIGINT/SIGTERM handlers set stop_event; serve() drains queue, closes active connections, joins workers within SHUTDOWN_JOIN_TIMEOUT=5.0 (lines 530-552). (4) SOAK/WATCHDOG: scripts/verify_game_bridge_concurrency.py reads /proc/<pid>/status Threads and fails if > workers+1; ran `./.venv/bin/python scripts/verify_game_bridge_concurrency.py --duration 5 --workers 4 --concurrency 4` -> EXIT=0, 'PASS: requests=472 duration_s=5 max_child_threads=5 ceiling=5 workers=4 concurrency=4'. (5) TESTS: `./.venv/bin/python -m pytest tests/test_game_bridge.py -q` -> '3 passed in 1.31s'. (6) SECURITY PRESERVED: bind 127.0.0.1 only (line 482), secrets.compare_digest token gate (line 392), token file 0600 + min-length check in main, one-request-per-connection preserved (test asserts 1 response for 2 pipelined requests). (7) DOCUMENTED: incident doc plus board events.jsonl task_completed (commit 640476c).
The aipp-bridge thread leak is named, reproduced, fixed with bounded workers + clean shutdown, verified by a passing soak/watchdog and 3 passing tests, documented, and loopback/token security is preserved.

## Summary

Judge Result: LOAD-BRIDGE-1

Stage tier1: FAIL
    ✓ lint: ok (no output)
  ✗ secrets: Command timed out
  ✓ tests: ============================= test session starts ==============================

Stage tier2: PASS
  COMPLETE
  ✓ Name and reproduce the request path causing the thread leak; replace the unbounded per-connection daemon thread model with bounded concurrency and clean shutdown; add a soak/watchdog verification showing the thread count remains bounded; document the incident and preserve loopback/token security.: All sub-requirements verified. (1) NAMED+REPRODUCED: docs/bridge-thread-incident-2026-09-30.md names the path (console GET /api/stream -> build_state() -> line-delimited {"cmd":"raw"} retry; 1018 R-state threads, loadavg 1015.9 peak) and tests/test_game_bridge.py::test_console_raw_retry_path_is_bounded_and_game_access_is_serialized reproduces it with 12 concurrent raw retries. (2) BOUNDED CONCURRENCY: scripts/game_bridge.py serve() (line 418) replaced per-connection daemon threads with a fixed worker set (DEFAULT_MAX_WORKERS=4, line 53) + bounded queue.Queue(maxsize=max_workers) (line 444); full queue answers {"ok":false,"error":"server busy"} (line 519). (3) CLEAN SHUTDOWN: SIGINT/SIGTERM handlers set stop_event; serve() drains queue, closes active connections, joins workers within SHUTDOWN_JOIN_TIMEOUT=5.0 (lines 530-552). (4) SOAK/WATCHDOG: scripts/verify_game_bridge_concurrency.py reads /proc/<pid>/status Threads and fails if > workers+1; ran `./.venv/bin/python scripts/verify_game_bridge_concurrency.py --duration 5 --workers 4 --concurrency 4` -> EXIT=0, 'PASS: requests=472 duration_s=5 max_child_threads=5 ceiling=5 workers=4 concurrency=4'. (5) TESTS: `./.venv/bin/python -m pytest tests/test_game_bridge.py -q` -> '3 passed in 1.31s'. (6) SECURITY PRESERVED: bind 127.0.0.1 only (line 482), secrets.compare_digest token gate (line 392), token file 0600 + min-length check in main, one-request-per-connection preserved (test asserts 1 response for 2 pipelined requests). (7) DOCUMENTED: incident doc plus board events.jsonl task_completed (commit 640476c).
The aipp-bridge thread leak is named, reproduced, fixed with bounded workers + clean shutdown, verified by a passing soak/watchdog and 3 passing tests, documented, and loopback/token security is preserved.

Overall: FAIL ✗
