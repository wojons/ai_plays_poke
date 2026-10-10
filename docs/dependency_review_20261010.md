# Dependency Review — 2026-10-09 Supervisor Scan (SUP-DEPS-20261009-AIP)

**Type:** Analysis only. No requirements files were modified, nothing was installed, no bulk upgrade was executed.
**Scope:** Python 3.11 runtime venv (`venv/`, pip 26.1.2) — the environment the supervisor scan measured. The Py3.13 test venv (`.venv/`) exists separately (see "Environment note" at the end).
**Method:** `pip list --outdated --format=json` (142 pkgs, reproduced live, matches the supervisor scan exactly) → classified against `requirements.txt` + `requirements-dev.txt` + `pyproject.toml [project]` → advisories from OSV/PyPI via `pip-audit` over the frozen environment (69 unique advisories across 19 packages) → resolver dry-runs (`pip install --dry-run`) for every risky direct bump → grep-level usage checks in `src/`, `tests/`, `cron_runner.py`.

## Summary

| Metric | Count |
|---|---|
| Total outdated packages | **142** |
| — Direct dependencies, outdated | **14** |
| — Transitive dependencies, outdated | **128** |
| Direct dependencies total (union of all three files) | 29 |
| Direct dependencies currently up to date | 15 |
| Known security advisories (unique, all transitive) | 69 across 19 packages |
| Advisories touching any DIRECT dependency | **0** |

**Classification drift found (needs a follow-up row, not fixed here):** `pyproject.toml [project].dependencies` declares 4 packages that `requirements.txt` omits — `openai`, `streamlit`, `pandas`, `matplotlib`. The project is installed editable, so those 4 ARE direct deps in practice (pip shows them as `Required-by: ptp-01x-pokemon-ai`). Additionally `requirements-dev.txt` declares floors (black 26.10.0, mypy 2.4.0, flake8 7.4.1) that the installed versions sit BELOW — the next plain `pip install -r requirements-dev.txt` silently jumps all three. The existing parity test (`tests/test_requirements_parity.py`) covers only dev extras, so the runtime drift is unguarded.

## Direct-dependency table (every outdated direct requirement)

Verdicts: **update-now** (mechanical, dev-only, or in-range), **update-with-testing** (needs a named verification gate), **hold** (blocked).

| Package | Current | Latest | Which file | Constraint / security note | Action |
|---|---|---|---|---|---|
| pyboy | 2.7.0 | 2.8.1 | requirements.txt (+pyproject) | **Self-blocked:** repo pins `>=1.0.0,<2.8.0` because 2.8.0 renumbered logging constants NON-monotonically (INFO=4 > CRITICAL=3), inverting the boot-path log suppression that `tests/test_emulator_pyboy_logging.py` (2 tests) pins. Unblocking requires re-verifying that suite against the new ordering, then relaxing the pin. | **hold** |
| anthropic | 0.117.0 | 1.13.0 | requirements.txt | **MAJOR (1.0 boundary):** SDK swaps httpx→httpx2, raises Python floor to 3.10 (fine here: 3.11/3.13), removes the legacy Text Completions API, changes raw-response methods. Project only uses the Messages client (`src/core/ai_client.py:52` lazy-imports `Anthropic`), no completions usage. Dry-run: resolves clean, pulls `httpx2 2.13.1` + `httpcore2 2.13.1`. Needs a live LLM-call smoke. | **update-with-testing** |
| pydantic | 2.13.5 | 2.14.0 | requirements.txt | Minor within 2.x (adds Py3.15 support, lazy imports, TypeForm; no breaking changes per release notes). Dry-run: clean; pulls `pydantic_core 2.50.0`, `typing_extensions 4.16.0`, `typing-inspection 0.4.4` (all available). Widest transitive pull of the runtime set → run the full suite. | **update-with-testing** |
| fastapi | 0.142.2 | 0.143.0 | requirements.txt + requirements-dev.txt + pyproject | Minor bump; Python 3.13 supported. Dry-run: clean. Serves the observability dashboard; needs a dashboard boot + `/ws/screenshots` smoke. | **update-with-testing** |
| websockets | 16.1.1 | 17.2 | requirements.txt + pyproject | 17.x promotes the new asyncio implementation and formally deprecates the legacy one (removal ~2030) — behavior change surface for long-lived sockets. Project only runs the SERVER side (Starlette `@app.websocket` in `src/dashboard/main.py:400`); the `websockets` package provides uvicorn's WS protocol impl. Dry-run: clean. | **update-with-testing** |
| black | 26.5.1 | 26.10.0 | requirements-dev.txt | Formatting tool only. Installed 26.5.1 is **below the declared floor 26.10.0** — the env is already drift-pinned; upgrading aligns env with file. Verify `black --check` stays idempotent (no reformat churn). | **update-now** |
| mypy | 2.3.0 | 2.4.0 | requirements-dev.txt | Type checker. Installed 2.3.0 is **below the declared floor 2.4.0**. Project baseline is 0 mypy errors — the count must stay 0 after bump (new checks can add findings). | **update-with-testing** |
| flake8 | 7.3.0 | 7.4.1 | requirements-dev.txt | Linter. Installed 7.3.0 is **below the declared floor 7.4.1**. Gate: `flake8 src/ tests/` clean. | **update-now** |
| pytest-benchmark | 5.2.3 | 5.3.0 | requirements-dev.txt | Dev-only benchmark harness; floor `>=4.0` already satisfied. Benchmarks are calibration-affected — compare before/after on one benchmark file. | **update-now** |
| python-lsp-server | 1.14.0 | 1.15.0 | requirements-dev.txt | Dev tooling — pylsp is wired into the gitreins guard (`guards.lsp: true`, pylsp). Bump and confirm the guard's lsp step still reports clean. | **update-with-testing** |
| openai | 2.46.0 | 3.28.0 | pyproject only (missing from requirements.txt) | **MAJOR (3.0 boundary)** — but `import openai` appears NOWHERE in `src/`, `tests/`, or `cron_runner.py`; the only consumer is the transitively-installed `litellm` (chimera-deliberation tooling), which caps its own compat range. This is a vestigial direct dep. Recommend: either remove from pyproject (drift fix) or bump only alongside litellm. | **hold** |
| streamlit | 1.59.2 | 1.65.0 | pyproject only | Zero `import streamlit` in the repo (the old `src/dashboard/run.py` entry point referenced in AGENTS.md no longer exists; dashboard is FastAPI now). Vestigial dep — but it drags GitPython/altair/pyarrow. Recommend removal, not upgrade. | **hold** |
| pandas | 3.0.3 | 3.0.6 | pyproject only | Zero imports anywhere in the repo. Pulled by nothing else (only `datasets`/`streamlit` would use it). Vestigial — recommend removal. | **hold** |
| matplotlib | 3.11.1 | 3.11.2 | pyproject only | Zero imports anywhere in the repo. Vestigial — recommend removal. | **hold** |

**Direct dependencies that are current (no action, listed for completeness):** requests 2.34.2, numpy, Pillow, python-dotenv, tqdm, PyYAML, opencv-python-headless, uvicorn, psutil, pytest, pytest-cov, pytest-xdist, pytest-timeout, requests-mock, pre-commit — all at or above their declared floors with no pending update in this scan.

## Security concerns

**No direct dependency carries a known advisory.** All 69 unique advisories (OSV/PyPI, audited 2026-10-09) live in transitive packages. 19 packages affected; every one has a released fix. Ranked by advisory count:

| Package (installed) | Advisories | Fixed in | Pulled in by | Note |
|---|---|---|---|---|
| gitpython 3.1.52 | 21 (incl. CVE-2026-76217..76222, CVE-2026-73619..73625, CVE-2026-87817/87819) | 3.1.60 | streamlit | Biggest single exposure; sits under the vestigial streamlit dep |
| PyJWT 2.13.0 | 14 (incl. CVE-2026-101917..101927, CVE-2026-102265..102275) | 2.14.0 (one needs 2.15.0) | mcp ← gitreins | Fleet tooling chain, not runtime |
| pymongo 4.16.0 | 4 (CVE-2026-88029, 96747..96749) | 4.18.2 | (no parent — env residue) | |
| virtualenv 21.6.1 | 4 (CVE-2026-102925..102938) | 21.7.13 | pre_commit | |
| pyasn1 0.6.2 | 4 (CVE-2026-30922, 59884..59886) | 0.6.4 | rsa | |
| aiohttp 3.14.1 | 3 (CVE-2026-69243, CVE-2026-69244, CVE-2026-59881) | 3.14.2/3.14.3 | litellm | Latest is 3.14.4 — take it |
| urllib3 2.7.0 | 3 (CVE-2026-97687..97689) | 2.8.0 | requests, botocore, twine, id | |
| httpx2 2.7.0 | 5 (CVE-2026-84378..84382) | 2.10.0–2.12.0 | anthropic (after 1.x bump) | Also blocks the anthropic 1.x path |
| httpcore2 2.7.0 | 1 (CVE-2026-84381) | 2.10.0 | (httpx2 stack) | |
| cryptography 49.0.0 | 1 (CVE-2026-69247) | 50.0.0 | localstack-core, SecretStorage | |
| litellm 1.93.0 | 1 (CVE-2026-84377) | 1.93.2 | chimera-deliberation | **In-range patch** — `litellm>=1.93.2` needs no consumer change |
| multidict 6.7.1 | 1 (CVE-2026-104874) | 6.9.1 | aiohttp, yarl | |
| pip 26.1.2 | 1 (CVE-2026-13346) | 26.2 | (self) | |
| h2 4.3.0 | 1 (CVE-2026-71554) | 4.4.1 | (httpx2 stack) | |
| hpack 4.1.0 | 1 (CVE-2026-59980) | 4.2.0 | h2 | |
| cbor2 5.8.0 | 1 (CVE-2026-26209) | 5.9.0 | (no parent) | |
| datasets 5.0.0 | 1 (CVE-2026-66007) | 5.0.1 | (no parent) | |
| deepdiff 8.6.1 | 1 (CVE-2026-33155) | 8.6.2 | (no parent) | |
| werkzeug 3.1.6 | 1 (CVE-2026-102598) | 3.1.9 | pytest_httpserver | Test-only |

**Exposure framing:** the runtime attack surface of the game AI itself is small (outbound `requests` to the LLM API + a locally-bound dashboard), so most of these sit in dev/CI/fleet-tooling paths rather than the production runtime. They are still cheap to clear — all fixes are routine version bumps already inside or compatible with the consumers' declared ranges. The one to prioritize beyond hygiene is the aiohttp/httpx2 stack (network-facing parsers) and urllib3 (under `requests`, which IS the runtime HTTP client).

## Transitive highlights (top 10 notable of 128)

| Package | Current → Latest | Why it matters |
|---|---|---|
| aiohttp | 3.14.1 → 3.14.4 | 3 CVEs (request-parsing/DoS class); sole consumer litellm; fix is a patch-level bump |
| starlette | 1.3.1 → 1.7.0 | Minor-major jump under fastapi AND mcp AND sse-starlette AND streamlit — widest shared consumer set; bump with fastapi, not alone |
| cryptography | 49.0.0 → 50.0.2 | 1 CVE + major-version jump; C-extension wheels exist for 3.11/3.13 |
| urllib3 | 2.7.0 → 2.8.0 | 3 CVEs; sits directly under runtime `requests` |
| GitPython | 3.1.52 → 3.2.0 | 21 advisories; under streamlit (vestigial) — removing streamlit removes the whole subtree |
| PyJWT | 2.13.0 → 2.15.1 | 14 advisories; under mcp (gitreins tooling) |
| mcp | 1.28.1 → 2.3.0 | Major bump; only consumer is gitreins — coordinate with the fleet's gitreins pipx copy, do NOT bump blind in this venv |
| openai | 2.46.0 → 3.28.0 | Major; litellm pins its own openai compat range — bump only with litellm |
| litellm | 1.93.0 → 1.104.2 | CVE fix needs only 1.93.2 (in-range); the full jump pulls openai/aiohttp/tokenizers along — take the patch first |
| pyarrow | 25.0.0 → 26.0.0 | Heavy C-extension wheel under streamlit/datasets; version-locked with pandas in practice |

(Second tier, routine: certifi 2026.6.17→2026.7.22, anyio 4.14.2→4.15.1, protobuf 7.34→7.36, coverage 7.13→7.16, ruff 0.15→0.17, isort 8→9 (major, dev-only), playwright 1.61→1.63, huggingface_hub 1.24→2.2 (major, under datasets).)

## Recommended batch plan (NOT executed)

Apply to `venv/` (3.11 runtime) and mirror to `.venv/` (3.13 gate) so both environments stay in parity; run `./.venv/bin/pytest -x --tb=short` (the guard's test command) as the gate for each batch. Verify with `pip check` after every batch.

1. **Batch 0 — env hygiene (no repo change):** `pip install -U pip setuptools wheel virtualenv` (clears pip CVE-2026-13346 + 4 virtualenv advisories).
2. **Batch 1 — security transitives (no repo change, one commit-free apply):** `aiohttp>=3.14.4 urllib3>=2.8.0 cryptography>=50.0.2 gitpython>=3.1.60 pyjwt>=2.15.0 pymongo>=4.18.2 pyasn1>=0.6.4 h2>=4.4.1 hpack>=4.2.0 cbor2>=5.9.0 datasets>=5.0.1 deepdiff>=8.6.2 werkzeug>=3.1.9 multidict>=6.9.1 httpx2 httpcore2 litellm>=1.93.2`. Gate: pip check + full suite + `python -c "from src.core import ai_client"` import smoke.
3. **Batch 2 — safe direct + tooling:** `black==26.10.0 mypy==2.4.0 flake8==7.4.1 pytest-benchmark==5.3.0 python-lsp-server==1.15.0 pydantic==2.14.0` (aligns env with the dev floors already declared). Gate: full suite; assert mypy error count stays at the 0 baseline; `black --check src/ tests/` idempotent; gitreins guard lsp step clean.
4. **Batch 3 — runtime direct with live smokes:** `anthropic==1.13.0` (pulls httpx2 stack; then run one real Messages call through `src/core/ai_client.py`), `fastapi==0.143.0` + dashboard boot + `/ws/screenshots` websocket smoke, `websockets==17.2` + `uvicorn` bump together with it.
5. **Batch 4 — hold-list (separate tasks, not this batch plan):** pyboy 2.8.x (task: re-verify `tests/test_emulator_pyboy_logging.py` under non-monotonic constants, then relax the `<2.8.0` pin); openai/streamlit/pandas/matplotlib (task: decide remove-vs-keep in pyproject — the drift fix, which also shrinks the GitPython exposure); mcp 2.x (coordinate with fleet gitreins).
6. **Deliberately excluded:** the 128-transitive bulk bump as one operation. Anything not in batches 0–3 rides its parent's bump or waits for the next review.

## Environment note

The scan ran against `venv/` (Python 3.11.15). The repo's guard/test venv is `.venv/` (Python 3.13.13, no pip binary — uv-managed). Version skew between the two venvs is expected to exist but was NOT audited here; the batch plan above mirrors upgrades into both and gates on the 3.13 suite, which is what the pre-commit guard actually runs.
