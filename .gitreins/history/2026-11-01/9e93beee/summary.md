# Verdict: VIS-MODEL-1-R2

**Task:** VIS-MODEL-1 M3+M4 remediation: measured structure scorer, shared cell classes, measured score doc (judge 2c3fcafe FAIL fix-list)
**Evaluated:** 2026-11-01T13:55:31.798227
**Result:** ✗ FAIL

## Pipeline Stages

- ✗ **tier1**
  -   ✓ lint: scanners: nice=nice -n 10
  ~ secrets: Command timed out after 120s (step budget)
  ✓ tests: scanners: nice=nice -n 10
- ✗ **tier2**
  - INCOMPLETE

Cap exceeded: Iteration cap (100) reached (100.1 used). Increase max_iterations or split criteria.

## Summary

Judge Result: VIS-MODEL-1-R2

Stage tier1: FAIL
  WARNING: coverage is secrets+lint+tests — secrets did not run (skipped at runtime — secrets: timed out after 120s (step budget)); run `gitreins guard` for the full gate
    ✓ lint: scanners: nice=nice -n 10
  ~ secrets: Command timed out after 120s (step budget)
  ✓ tests: scanners: nice=nice -n 10

Stage tier2: FAIL
  INCOMPLETE

Cap exceeded: Iteration cap (100) reached (100.1 used). Increase max_iterations or split criteria.

Overall: FAIL ✗ [DEGRADED — skipped: tier1(secrets)=skipped at runtime — secrets: timed out after 120s (step budget)]
