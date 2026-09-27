# Verdict: REVIEW-1

**Task:** Dashboard credential hardening (P0)
**Evaluated:** 2026-09-27T20:03:17.390571
**Result:** ✓ PASS

## Pipeline Stages

- ✓ **tier1**
  -   ✓ lint: ok (no output)
  ✓ secrets: secrets: harness state excluded from gitleaks scope (.gitreins/**)
  ✓ tests: ============================= test session starts ==============================
- ✓ **tier2**
  - COMPLETE
  ✓ API_KEY has no default and auth fails closed when PTP_API_KEY unset; PTP_DASHBOARD_HOST defaults to 127.0.0.1; key never printed to stdout; string ptp-secret-key absent from source; dashboard tests pass: All five sub-claims verified. (1) No default: src/dashboard/main.py:37 `API_KEY = os.getenv("PTP_API_KEY")` — commit 692cddd diff confirms the old `os.getenv("PTP_API_KEY", "ptp-secret-key-12345")` was removed. (2) Fail closed: main.py:66-71 `verify_api_key` -> `if not API_KEY or x_api_key != API_KEY: raise HTTPException(status_code=401, ...)`; tests/test_dashboard.py:64-124 (TestFailClosedAuth) assert 401 for the old default key, a missing header, and an empty header when API_KEY is None, plus 200 with a configured key. (3) Host default: main.py:512 `host = os.getenv("PTP_DASHBOARD_HOST", "127.0.0.1")`; `grep -n 0.0.0.0 src/dashboard/main.py src/dashboard/static/index.html` returns no match (exit 1). (4) Key not printed: main.py:514-515 print only host/port and the docs URL; the `print(f"API Key: {API_KEY}")` line was deleted in 692cddd, and tests/test_dashboard.py:104-124 (test_startup_does_not_print_the_api_key) runs the __main__ block via runpy and asserts `"API Key" not in out` and `TEST_API_KEY not in out`. (5) Literal absent: repo-wide grep for `ptp-secret-key` (excluding .git/.venv/.coding-hermes/.gitreins) matches only tests/test_dashboard.py:77, which assembles it as `"ptp" + "-secret-key-12345"` so the exact string never appears; src/dashboard/static/index.html:430 uses `(window.ENV && window.ENV.PTP_API_KEY) || ''` with serve-time injection via render_index_html (main.py:43-59). Tests run fresh: `./.venv/bin/pytest tests/test_dashboard.py -q -p no:cacheprovider` -> "63 passed in 0.54s" (exit 0); full suite `./.venv/bin/pytest tests/ -q --tb=line -k "not benchmark" -p no:cacheprovider` -> "4276 passed, 14 skipped, 5 deselected in 237.59s" (exit 0). Only caveat: a stale untracked build artifact src/dashboard/__pycache__/main.cpython-311.pyc still contains the old literals, but it is not source and is not tracked.
Dashboard credential hardening is fully implemented and verified: no default API key, fail-closed auth, 127.0.0.1 bind default, no key on stdout, no ptp-secret-key literal in source, and 63 dashboard tests plus the full 4276-test suite pass.

## Summary

Judge Result: REVIEW-1

Stage tier1: PASS
    ✓ lint: ok (no output)
  ✓ secrets: secrets: harness state excluded from gitleaks scope (.gitreins/**)
  ✓ tests: ============================= test session starts ==============================

Stage tier2: PASS
  COMPLETE
  ✓ API_KEY has no default and auth fails closed when PTP_API_KEY unset; PTP_DASHBOARD_HOST defaults to 127.0.0.1; key never printed to stdout; string ptp-secret-key absent from source; dashboard tests pass: All five sub-claims verified. (1) No default: src/dashboard/main.py:37 `API_KEY = os.getenv("PTP_API_KEY")` — commit 692cddd diff confirms the old `os.getenv("PTP_API_KEY", "ptp-secret-key-12345")` was removed. (2) Fail closed: main.py:66-71 `verify_api_key` -> `if not API_KEY or x_api_key != API_KEY: raise HTTPException(status_code=401, ...)`; tests/test_dashboard.py:64-124 (TestFailClosedAuth) assert 401 for the old default key, a missing header, and an empty header when API_KEY is None, plus 200 with a configured key. (3) Host default: main.py:512 `host = os.getenv("PTP_DASHBOARD_HOST", "127.0.0.1")`; `grep -n 0.0.0.0 src/dashboard/main.py src/dashboard/static/index.html` returns no match (exit 1). (4) Key not printed: main.py:514-515 print only host/port and the docs URL; the `print(f"API Key: {API_KEY}")` line was deleted in 692cddd, and tests/test_dashboard.py:104-124 (test_startup_does_not_print_the_api_key) runs the __main__ block via runpy and asserts `"API Key" not in out` and `TEST_API_KEY not in out`. (5) Literal absent: repo-wide grep for `ptp-secret-key` (excluding .git/.venv/.coding-hermes/.gitreins) matches only tests/test_dashboard.py:77, which assembles it as `"ptp" + "-secret-key-12345"` so the exact string never appears; src/dashboard/static/index.html:430 uses `(window.ENV && window.ENV.PTP_API_KEY) || ''` with serve-time injection via render_index_html (main.py:43-59). Tests run fresh: `./.venv/bin/pytest tests/test_dashboard.py -q -p no:cacheprovider` -> "63 passed in 0.54s" (exit 0); full suite `./.venv/bin/pytest tests/ -q --tb=line -k "not benchmark" -p no:cacheprovider` -> "4276 passed, 14 skipped, 5 deselected in 237.59s" (exit 0). Only caveat: a stale untracked build artifact src/dashboard/__pycache__/main.cpython-311.pyc still contains the old literals, but it is not source and is not tracked.
Dashboard credential hardening is fully implemented and verified: no default API key, fail-closed auth, 127.0.0.1 bind default, no key on stdout, no ptp-secret-key literal in source, and 63 dashboard tests plus the full 4276-test suite pass.

Overall: PASS ✓
