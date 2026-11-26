# Verdict: RELEASE-009-R1

**Task:** Test coverage for portable AIPP_* runtime-path resolvers
**Evaluated:** 2026-11-26T00:13:57.724045
**Result:** ✗ FAIL (DEGRADED — skipped checks)

## Pipeline Stages

- ✓ **tier1**
  -   ✓ lint: scanners: nice=nice -n 10
  ✓ secrets: secrets: scanners=gitleaks+builtin cross-check
  ✓ tests: scanners: nice=nice -n 10
- ✗ **tier2**
  - INCOMPLETE
  ✗ Coverage FAILED — ungraded: pytest tests/test_path_resolvers.py passes covering every AIPP_* resolver default and override; grep -rn 'AIPP_CANONICAL_ENV|AIPP_CONSOLE_HOME|AIPP_HANDBOOK_RENDER|AIPP_REPO|AIPP_PYTHON' tests/ returns > 0 hits; a guard test fails when an absolute /home path literal is reintroduced; full suite green.
Evaluator error: LLM call failed: LLM request failed after 3 attempts (provider=openai model=glm-5.3-flash url=https://api.z.ai/api/coding/paas/v4/chat/completions key=<GITREINS_LLM_API_KEY>) — last error: 429 Client Error: Too Many Requests for url: https://api.z.ai/api/coding/paas/v4/chat/completions

## Summary

Stage tier1: PASS
    ✓ lint: scanners: nice=nice -n 10
  ✓ secrets: secrets: scanners=gitleaks+builtin cross-check
  ✓ tests: scanners: nice=nice -n 10

Stage tier2: FAIL
  INCOMPLETE
  ✗ Coverage FAILED — ungraded: pytest tests/test_path_resolvers.py passes covering every AIPP_* resolver default and override; grep -rn 'AIPP_CANONICAL_ENV|AIPP_CONSOLE_HOME|AIPP_HANDBOOK_RENDER|AIPP_REPO|AIPP_PYTHON' tests/ returns > 0 hits; a guard test fails when an absolute /home path literal is reintroduced; full suite green.
Evaluator error: LLM call failed: LLM request failed after 3 attempts (provider=openai model=glm-5.3-flash url=https://api.z.ai/api/coding/paas/v4/chat/completions key=<GITREINS_LLM_API_KEY>) — last error: 429 Client Error: Too Many Requests for url: https://api.z.ai/api/coding/paas/v4/chat/completions

Overall: FAIL ✗
