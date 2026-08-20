# Verdict: GAP-030

**Task:** GAP-030: pytest/pytest-xdist/pytest-cov absent from requirements.txt
**Evaluated:** 2026-08-20T16:31:05.072016
**Result:** ✗ FAIL

## Pipeline Stages

- ✗ **tier1**
  -   ✓ lint: 
  ✗ secrets: [90m11:26AM[0m [32mINF[0m [1mscanned ~175138875 bytes (175.14 MB) in 8.36s[0m
[90m11:26AM[0m
  ✓ tests: ============================= test session starts ==============================
platform linux -- P
- ✓ **tier2**
  - COMPLETE
  ✓ A fresh clone following README and AGENTS setup, installing requirements.txt plus the documented dev install, can run pytest tests with -q --co collecting 3937 tests with zero errors, including -n auto (xdist) and --cov=src support. requirements-dev.txt gains pytest, pytest-xdist, pytest-cov; README and AGENTS instruct devs to install requirements-dev.txt for testing.: requirements-dev.txt (commit 99bc907) contains pytest>=7.0, pytest-cov>=4.0, pytest-xdist>=3.0. README.md:330 fresh-clone note and README.md:588 instruct `pip install -r requirements-dev.txt`; AGENTS.md:16 instructs `pip install -r requirements-dev.txt` for dev. Verified `.venv/bin/pytest tests/ -q --co` = '3937 tests collected in 5.13s' with zero errors; `-n auto` = 3937 collected in 4.34s; `--cov=src` = coverage report + 3937 collected in 8.88s. End-to-end run `-n auto --cov=src` on subset = 311 passed; test_schemas.py = 45 passed. pytest 9.1.1, pytest-cov 7.1.0, pytest-xdist 3.8.0 installed in both .venv and venv.
GAP-030 fully satisfied: requirements-dev.txt gains pytest/pytest-xdist/pytest-cov, README and AGENTS instruct devs to install requirements-dev.txt, and pytest -q --co collects 3937 tests with zero errors including -n auto and --cov=src support.

## Summary

Judge Result: GAP-030

Stage tier1: FAIL
    ✓ lint: 
  ✗ secrets: [90m11:26AM[0m [32mINF[0m [1mscanned ~175138875 bytes (175.14 MB) in 8.36s[0m
[90m11:26AM[0m
  ✓ tests: ============================= test session starts ==============================
platform linux -- P

Stage tier2: PASS
  COMPLETE
  ✓ A fresh clone following README and AGENTS setup, installing requirements.txt plus the documented dev install, can run pytest tests with -q --co collecting 3937 tests with zero errors, including -n auto (xdist) and --cov=src support. requirements-dev.txt gains pytest, pytest-xdist, pytest-cov; README and AGENTS instruct devs to install requirements-dev.txt for testing.: requirements-dev.txt (commit 99bc907) contains pytest>=7.0, pytest-cov>=4.0, pytest-xdist>=3.0. README.md:330 fresh-clone note and README.md:588 instruct `pip install -r requirements-dev.txt`; AGENTS.md:16 instructs `pip install -r requirements-dev.txt` for dev. Verified `.venv/bin/pytest tests/ -q --co` = '3937 tests collected in 5.13s' with zero errors; `-n auto` = 3937 collected in 4.34s; `--cov=src` = coverage report + 3937 collected in 8.88s. End-to-end run `-n auto --cov=src` on subset = 311 passed; test_schemas.py = 45 passed. pytest 9.1.1, pytest-cov 7.1.0, pytest-xdist 3.8.0 installed in both .venv and venv.
GAP-030 fully satisfied: requirements-dev.txt gains pytest/pytest-xdist/pytest-cov, README and AGENTS instruct devs to install requirements-dev.txt, and pytest -q --co collects 3937 tests with zero errors including -n auto and --cov=src support.

Overall: FAIL ✗
