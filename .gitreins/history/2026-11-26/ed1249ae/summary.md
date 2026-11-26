# Verdict: RELEASE-009-R1

**Task:** Test coverage for portable AIPP_* runtime-path resolvers
**Evaluated:** 2026-11-26T00:50:39.604916
**Result:** ✗ FAIL (DEGRADED — skipped checks)

## Pipeline Stages

- ✓ **tier1**
  -   ✓ lint: scanners: nice=nice -n 10
  ✓ secrets: secrets: scanners=gitleaks+builtin cross-check
  ✓ tests: scanners: nice=nice -n 10
- ✗ **tier2**
  - INCOMPLETE
  ✗ Coverage FAILED — ungraded: pytest tests/test_path_resolvers.py passes covering every AIPP_* resolver default and override; grep -rn 'AIPP_CANONICAL_ENV|AIPP_CONSOLE_HOME|AIPP_HANDBOOK_RENDER|AIPP_REPO|AIPP_PYTHON' tests/ returns > 0 hits; a guard test fails when an absolute /home path literal is reintroduced; full suite green.
Evaluator error: LLM call failed: LLM request failed after 3 attempts (provider=openai model=deepseek-flash url=https://api.deepseek.com/chat/completions key=<GITREINS_LLM_API_KEY>) — last error: HTTPSConnectionPool(host='api.deepseek.com', port=443): Max retries exceeded with url: /chat/completions (Caused by NameResolutionError("HTTPSConnection(host='api.deepseek.com', port=443): Failed to resolve 'api.deepseek.com' ([Errno -3] Temporary failure in name resolution)"))

## Summary

Stage tier1: PASS
    ✓ lint: scanners: nice=nice -n 10
  ✓ secrets: secrets: scanners=gitleaks+builtin cross-check
  ✓ tests: scanners: nice=nice -n 10

Stage tier2: FAIL
  INCOMPLETE
  ✗ Coverage FAILED — ungraded: pytest tests/test_path_resolvers.py passes covering every AIPP_* resolver default and override; grep -rn 'AIPP_CANONICAL_ENV|AIPP_CONSOLE_HOME|AIPP_HANDBOOK_RENDER|AIPP_REPO|AIPP_PYTHON' tests/ returns > 0 hits; a guard test fails when an absolute /home path literal is reintroduced; full suite green.
Evaluator error: LLM call failed: LLM request failed after 3 attempts (provider=openai model=deepseek-flash url=https://api.deepseek.com/chat/completions key=<GITREINS_LLM_API_KEY>) — last error: HTTPSConnectionPool(host='api.deepseek.com', port=443): Max retries exceeded with url: /chat/completions (Caused by NameResolutionError("HTTPSConnection(host='api.deepseek.com', port=443): Failed to resolve 'api.deepseek.com' ([Errno -3] Temporary failure in name resolution)"))

Overall: FAIL ✗
