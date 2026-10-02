# Verdict: REV-2

**Task:** Runtime dependency manifest drift: pyproject.toml omits runtime deps
**Evaluated:** 2026-10-02T10:28:17.821178
**Result:** ✗ FAIL

## Pipeline Stages

- ✗ **tier1**
  -   ✓ lint: ok (no output)
  ✓ secrets: secrets: harness state excluded from gitleaks scope (.gitreins/**)
  ✗ tests: Command timed out
- ✓ **tier2**
  - COMPLETE
  ✓ pyproject.toml [project].dependencies includes requests, numpy, Pillow, opencv-python-headless, psutil, fastapi, uvicorn, websockets with version bounds matching requirements.txt; pip install -e . in a fresh venv resolves without missing modules: pyproject.toml lines 11-28 [project].dependencies contains all 8 required packages with bounds EXACTLY matching requirements.txt (verified programmatically, all MATCH=True): requests>=2.31.0, numpy>=1.24.0, Pillow>=10.0.0, opencv-python-headless>=4.8.0, psutil>=5.9.0, fastapi>=0.104.0, uvicorn>=0.24.0, websockets>=12.0. Fresh venv test: `python3 -m venv /tmp/rev2venv && /tmp/rev2venv/bin/pip install -e .` exited 0 with 'Successfully installed ... Pillow-12.3.0 ... fastapi-0.142.2 ... numpy-2.4.6 ... opencv-python-headless-5.0.0.93 ... psutil-7.2.2 ... requests-2.34.2 ... uvicorn-0.54.0 ... websockets-16.1.1 ... ptp-01x-pokemon-ai-0.1.0'. Import check in that venv returned ALL_IMPORTS_OK (requests, numpy, PIL, cv2, psutil, fastapi, uvicorn, websockets all import). tests/test_requirements_parity.py: 4 passed in 0.03s; full suite `./.venv/bin/pytest -x --tb=short` showed 0 FAILED/ERROR. [resolution 0.34; pyproject.toml]
pyproject.toml declares all 8 runtime deps with version bounds identical to requirements.txt, and pip install -e . in a fresh venv resolves and imports every module successfully.

## Summary

Judge Result: REV-2

Stage tier1: FAIL
    ✓ lint: ok (no output)
  ✓ secrets: secrets: harness state excluded from gitleaks scope (.gitreins/**)
  ✗ tests: Command timed out

Stage tier2: PASS
  COMPLETE
  ✓ pyproject.toml [project].dependencies includes requests, numpy, Pillow, opencv-python-headless, psutil, fastapi, uvicorn, websockets with version bounds matching requirements.txt; pip install -e . in a fresh venv resolves without missing modules: pyproject.toml lines 11-28 [project].dependencies contains all 8 required packages with bounds EXACTLY matching requirements.txt (verified programmatically, all MATCH=True): requests>=2.31.0, numpy>=1.24.0, Pillow>=10.0.0, opencv-python-headless>=4.8.0, psutil>=5.9.0, fastapi>=0.104.0, uvicorn>=0.24.0, websockets>=12.0. Fresh venv test: `python3 -m venv /tmp/rev2venv && /tmp/rev2venv/bin/pip install -e .` exited 0 with 'Successfully installed ... Pillow-12.3.0 ... fastapi-0.142.2 ... numpy-2.4.6 ... opencv-python-headless-5.0.0.93 ... psutil-7.2.2 ... requests-2.34.2 ... uvicorn-0.54.0 ... websockets-16.1.1 ... ptp-01x-pokemon-ai-0.1.0'. Import check in that venv returned ALL_IMPORTS_OK (requests, numpy, PIL, cv2, psutil, fastapi, uvicorn, websockets all import). tests/test_requirements_parity.py: 4 passed in 0.03s; full suite `./.venv/bin/pytest -x --tb=short` showed 0 FAILED/ERROR. [resolution 0.34; pyproject.toml]
pyproject.toml declares all 8 runtime deps with version bounds identical to requirements.txt, and pip install -e . in a fresh venv resolves and imports every module successfully.

Overall: FAIL ✗
