# Dependency Review — 2026-10-19 (SUP-DEPS-20261019-AIP)

Continues the 2026-10-13 → 2026-10-15 chain (`dependency_review_20261013.md`,
`dependency_residual_20261013.md`, `dependency_reconcile_20261014.md`,
`dependency_reconcile_20261015.md`).

**Surface:** `.venv/` (Python 3.13.13) — the authoritative test env
(`.gitreins/config.yaml` `test_command: ./.venv/bin/pytest -x --tb=short`).
`venv/` (Python 3.11) is the stale duplicate and was not touched.

**Scan:** `.venv/bin/pip list --outdated` → **30 entries** (21 at the 2026-10-15 scan;
the delta is newly-listed-outdated releases plus the packages that scan upgraded since).

**Baseline measured before any change:** `pytest tests/ -q` → **4503 passed,
14 skipped** in 183s (4517 collected). The dispatch brief quoted "~4514 tests
passing"; the measured figure is 4503 passing + 14 skipped. Recorded rather than
echoed — the numbers below are measured, not quoted.

**Method:** targeted installs only (`uv pip install --python .venv/bin/python
<pkg>==<ver>`); no `uv sync`, no force flags, no `pip install -U`. `pip check`
after every batch, full suite after every batch, then `ruff` + both mypy scopes
(the brief's `src/` scope and CI's `src/ scripts/` scope). Every verdict was
re-verified against current installed metadata (`pip show`, dist-info `METADATA`,
PyPI JSON) rather than copied from the prior docs.

## Result

**9 upgraded, 17 held, 2 N/A (pin), 2 satisfied-not-bumped = 30.**
Post-change scan: **21 remaining** (30 − 9 upgraded).

## Reconciliation table

Classification rules carried forward: `orphan` = undeclared in
`requirements*.txt` / `pyproject.toml` with `Required-by:` empty and zero static
imports; `orphan-chain` = transitive of such a package. Hand-upgrading orphans is
pointless churn — a venv rebuild removes them.

| # | Package | Installed → Latest | Verdict | Reason (re-verified 2026-10-19) |
|---|---|---|---|---|
| 1 | altair | 6.2.2 → 6.3.0 | held (orphan) | `Required-by:` empty, absent from all manifests, 0 imports — streamlit-era leftover (requirements.txt:46 documents the drop). |
| 2 | anthropic | 0.122.0 → 1.15.0 | **upgraded** | DIRECT (`requirements.txt:25`) and imported (`src/core/ai_client.py:52`). MAJOR 0→1: sampling params removed from `messages.create()`, HTTP layer moved to `httpx2`. Breaking change handled in code + guarded by a new real-SDK loopback test (see below). |
| 3 | ast_serialize | 0.13.0 → 0.13.1 | **upgraded** | Transitive of DECLARED dev dep mypy 2.4.0 (`ast-serialize<1.0.0,>=0.11.2`). Patch. |
| 4 | boto3 | 1.43.112 → 1.43.114 | held (orphan-chain) | Sole parent litellm (orphan); 0 imports; pair-locked to botocore. |
| 5 | botocore | 1.43.112 → 1.43.114 | held (orphan-chain) | Same chain (parents boto3/s3transfer only). |
| 6 | cachebox | 5.2.3 → 6.2.8 | held (orphan) | Only parent deepdiff (orphan, `Required-by:` empty); MAJOR 5→6; delete-with-rebuild doctrine. |
| 7 | certifi | 2026.7.22 → 2026.10.18 | **upgraded** | Transitive of DIRECT dep requests 2.34.2 (`certifi>=2023.5.7`, open upper) and httpx. CalVer date bump. |
| 8 | contourpy | 1.3.3 → 1.4.0 | held (orphan) | `Required-by:` empty, 0 imports — matplotlib-era leftover. |
| 9 | distlib | 0.4.3 → 0.4.4 | **upgraded** | Transitive of virtualenv → pre_commit 4.7.0 (DECLARED, `requirements-dev.txt:15`). |
| 10 | fastapi | 0.143.2 → 0.146.0 | **upgraded** | DIRECT (`requirements.txt:38`). 0.x minor series with two upstream BREAKING changes — both checked against this codebase: 0.145.0 removed `openapi_prefix` + `**extra` from `FastAPI()` (0 hits repo-wide), 0.146.0 deprecated `root_path` (0 hits). `starlette>=0.46.0` still open-upper, so the starlette pin was not forced. |
| 11 | filelock | 3.32.7 → 4.2.4 | held (cap) | MAJOR 3→4, capped by litellm 1.104.2 (`filelock>=3.16.1,<4.0`). Unblocks only via venv rebuild. |
| 12 | fonttools | 4.63.0 → 4.67.0 | held (orphan) | `Required-by:` empty, 0 imports. |
| 13 | fsspec | 2026.7.0 → 2026.9.0 | held (cap) | Capped by datasets 5.1.0 (`fsspec[http]<=2026.7.0,>=2023.1.0`); installed sits exactly at the orphan's ceiling. (Prior doc attributed this cap to litellm — it does not cap fsspec; corrected here.) |
| 14 | GitPython | 3.2.0 → 3.2.1 | held (orphan) | `Required-by:` empty, absent from manifests, 0 imports. |
| 15 | httpcore2 | 2.13.1 → 2.14.0 | satisfied | Now transitive of anthropic 1.15.0 via httpx2 (`httpx2>=2.0.0,<3`); 2.13.1 satisfies. Bump blocked in-session by the package-name security scanner (`httpx2` ≈ `httpx` typosquat heuristic) and unnecessary. |
| 16 | httpx2 | 2.13.1 → 2.14.0 | satisfied | Same as httpcore2. No longer an orphan: `Required-by: anthropic`. |
| 17 | huggingface_hub | 1.33.0 → 2.2.0 | held (cap) | MAJOR 1→2, capped by litellm (`huggingface-hub>=0.34.0,<2.0`). |
| 18 | importlib_metadata | 8.9.0 → 9.0.1 | held (cap) | MAJOR 8→9, capped by litellm (`importlib-metadata>=8.0.0,<9.0`). |
| 19 | litellm | 1.104.2 → 1.106.0 | held (orphan) | The cap source itself: undeclared, 0 imports, `Required-by:` empty. Verified from PyPI that **1.106.0 declares the identical caps** (`openai<3.0`, `filelock<4.0`, `importlib-metadata<9.0`, `huggingface-hub<2.0`), so upgrading it would unblock nothing. Removal at rebuild is the fix. |
| 20 | narwhals | 2.24.0 → 2.27.1 | held (orphan-chain) | Transitive of altair (orphan). |
| 21 | openai | 2.54.0 → 3.35.1 | held (cap) | MAJOR 2→3 AND orphan (parent litellm only, `openai>=2.20.0,<3.0.0`, 0 imports). Not bumped by the project (OpenRouter model-name strings only). |
| 22 | pillow | 12.3.0 → 13.0.0 | **upgraded** | DIRECT (`requirements.txt:29`) and imported in 33 files. MAJOR reviewed from the 13.0.0 release notes: removals are `Image._show`, `ImageCms…product_name`, `ExifTags.IFD.Makernote`, `get_child_images` on `Image`, I-mode PNG clipping, small-ICO saving, `fromarray(mode=)` type-changing — none used here (the four `fromarray(..., mode="RGB")` calls pass a matching dtype). Ships a large CVE batch. Floor left at `>=10.4.0` on purpose: Pillow 13 requires Python ≥3.11 while the project declares ≥3.10. |
| 23 | platformdirs | 4.13.0 → 4.13.5 | **upgraded** | Transitive of virtualenv (`platformdirs<5,>=4.4`). |
| 24 | pyboy | 2.7.0 → 2.8.1 | N/A (pin) | Self-blocked by the project pin `pyboy>=1.0.0,<2.8.0` (requirements.txt:18): 2.8.0 renumbered logging constants non-monotonically AND bumped the save-state format to STATE_VERSION 29 with no migration, breaking all 10 tracked `*.state` files. Needs a state-migration row, not a bump. **The dispatch brief listed pyboy as a "safe minor" upgrade — that is wrong and is not applied.** |
| 25 | pymongo | 4.18.3 → 4.19.0 | held (orphan) | `Required-by:` empty, absent from manifests, 0 imports. |
| 26 | python-discovery | 1.6.2 → 1.6.4 | **upgraded** | Transitive of virtualenv (`python-discovery>=1.6.1`). |
| 27 | ruff | 0.15.22 → 0.17.1 | N/A (pin) | CI installs `ruff==0.15.22` (`.github/workflows/ci.yml:82`); bumping the venv alone desyncs local lint from CI. |
| 28 | starlette | 1.3.1 → 1.9.0 | held (doctrine) | Not cap-held — fastapi 0.146.0 still declares `starlette>=0.46.0` (open upper), verified after the upgrade: installed starlette stayed 1.3.1. Five minors under every dashboard route with no live dashboard-boot/WS proof; needs its own live-verify row. |
| 29 | virtualenv | 21.14.7 → 21.14.11 | **upgraded** | Transitive of DECLARED dev dep pre_commit 4.7.0 (`virtualenv>=20.10.0`). Runtime-relevant: the pre-commit guard builds envs with it. |
| 30 | websockets | 16.1.1 → 17.2 | N/A (pin) | DIRECT declaration but MAJOR 16→17 on the ASGI/WS layer; 0 static imports, so the suite cannot prove the dashboard's WS handshake. Needs a live WS smoke row. |

| Verdict | Count |
|---|---|
| upgraded | 9 |
| held — cap-blocked | 5 |
| held — orphan / orphan-chain | 10 |
| held — doctrine (starlette) | 1 |
| N/A (pin: pyboy, ruff, websockets) | 3 |
| satisfied, not bumped (httpx2, httpcore2) | 2 |
| **Total** | **30** |

## Upgrades applied

Installed in four batches, `pip check` clean after each, full suite after each:

`uv pip install --python .venv/bin/python ast-serialize==0.13.1 certifi==2026.10.18
virtualenv==21.14.11 distlib==0.4.4 platformdirs==4.13.5 python-discovery==1.6.4
fastapi==0.146.0 pillow==13.0.0 anthropic==1.15.0`

No collateral: `/tmp/deps-changes.txt` shows exactly the 9 version lines and
nothing else (no packages added or removed).

## Code changes

1. `src/core/ai_client.py` — `ClaudeClient.chat_completion`: `temperature=temperature`
   → `extra_body={"temperature": temperature}`. anthropic ≥1.0 removed the sampling
   parameters from `messages.create()`, so the old call raises `TypeError`; `extra_body`
   is forwarded to the API as-is, so models that still honour `temperature` keep the
   old behaviour. The change is also valid on 0.x.

2. `tests/test_ai_client.py` — new `TestClaudeClientRealSDKCallShape`. The existing
   `ClaudeClient` tests mock the whole SDK class, so they cannot see an SDK-signature
   break. The new test starts a stdlib HTTP server on `127.0.0.1:0`, points the REAL
   installed SDK at it with `ANTHROPIC_BASE_URL`, calls `ClaudeClient.chat_completion`,
   and asserts the parsed fields **and** that `temperature` still reaches the wire.
   No network egress; the port is ephemeral; the server is shut down in `finally`.

   **RED proof:** with `src/core/ai_client.py` reverted to `temperature=temperature`
   (SDK 1.15.0 installed) the test fails with the production error verbatim —
   `TypeError: Messages.create() got an unexpected keyword argument 'temperature'`.
   Restored → passes. The same command was also driven standalone against the real SDK
   (`/tmp/probe_anthropic.py`): pre-fix `PROBE_FAIL TypeError …`, post-fix
   `request_body = {max_tokens, messages, model, temperature}` → `PROBE_OK`.

3. Manifest floors (no exact pins existed; floors bumped for the two upgraded direct deps):
   - `requirements.txt`: `anthropic>=0.117.0` → `>=1.15.0`, `fastapi>=0.142.2` → `>=0.146.0`
   - `requirements-dev.txt`: `fastapi>=0.104.0` → `>=0.146.0`
   - `pyproject.toml`: `anthropic>=0.3.0` → `>=1.15.0`; `fastapi>=0.104.0` → `>=0.146.0`
     (both `[project].dependencies` and the `dev` extra)
   - `Pillow` floor deliberately NOT bumped (see #22). `pyboy`, `ruff`, `websockets`
     pins untouched.

## Verification

| Gate | Command | Result |
|---|---|---|
| Baseline (pre-change) | `.venv/bin/pytest tests/ -x -q` | 4503 passed, 14 skipped (183s) |
| Batch A (6 pkgs) | same | 4503 passed, 14 skipped (178s) |
| Batch B (fastapi) | same | 4503 passed, 14 skipped (205s) |
| Batch C (pillow) | `pytest tests/test_vision.py test_vision_client.py test_ocr.py test_screenshot_manager.py test_screenshots.py test_perf_frame_gate.py` then full | 225 passed, 5 skipped (focused); 4503 passed, 14 skipped (full, 240s) |
| Batch D (anthropic + test) | `pytest tests/test_ai_client.py` then full | 242 passed (focused); **4504 passed, 14 skipped (477s)** |
| Dependency consistency | `.venv/bin/pip check` | `No broken requirements found.` (after every batch) |
| Lint (CI command) | `.venv/bin/ruff check src/ tests/` | `All checks passed!` |
| Type check (brief) | `.venv/bin/mypy src/ --ignore-missing-imports` | `Success: no issues found in 69 source files` |
| Type check (CI command) | `.venv/bin/mypy --explicit-package-bases src/ scripts/ --ignore-missing-imports` | `Success: no issues found in 90 source files` |
| Import/API smoke | fastapi `FastAPI().openapi()` on 0.146.0 | schema generated, starlette still 1.3.1 |

The final full-suite run took 477s vs 183s at baseline: host load average was 32–37
during that run (shared fleet box), and the pass/skip counts are identical, so this is
contention, not a regression. Evidence: `/tmp/deps-before.txt`, `/tmp/deps-after.txt`,
`/tmp/deps-changes.txt`, `/tmp/baseline-tests.log`, `/tmp/batchA-tests.log`,
`/tmp/batchB-tests.log`, `/tmp/batchC-tests.log`, `/tmp/final-tests.log`.

## Honest gaps

- **No live LLM call was made** (no `ANTHROPIC_API_KEY` in this environment). The
  anthropic upgrade is proven against the real SDK over loopback, not against
  `api.anthropic.com`. Note the `ClaudeClient` default models are years-old IDs
  (`claude-3-sonnet-20240307`, `claude-3-haiku-20240307`), so that path is not
  production-live regardless of SDK version — a separate issue, not a dependency one.
- **Five majors stay blocked by an orphan** (litellm caps `openai<3`, `filelock<4`,
  `importlib-metadata<9`, `huggingface-hub<2`) plus `fsspec` (datasets cap). All six
  unblock by deleting `litellm`/`datasets`/`tokenizers`/`boto3`/`botocore` in the
  long-pending venv rebuild — removing packages was out of scope here.
- **`httpx2`/`httpcore2` were not bumped**: the session's package-name security scanner
  refuses `httpx2` as a suspected typosquat of `httpx` (it is the legitimate
  Pydantic-maintained fork anthropic 1.x now uses). 2.13.1 satisfies `>=2.0.0,<3`.
- **starlette + websockets still need live-verify rows**; pyboy still needs a
  state-migration row.
- No advisory/security scan run (no scanner in the venv; the prior review's gap stands).
- `uv.lock` not regenerated (targeted installs only); lock-vs-venv divergence is
  pre-existing and a rebuild decision.
