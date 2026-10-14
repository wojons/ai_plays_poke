# Dependency Reconciliation — 2026-10-13 (SUP-DEPS-20261013-AIP-FOLLOWUP)

Surface: `.venv/` (CPython 3.13.13) — the authoritative test env (`test_command: ./.venv/bin/pytest`).
Method: `.venv/bin/python -m pip list --outdated --format=json`, `pip show` for Required-by/Requires,
declared-surface grep over `requirements.txt` / `requirements-dev.txt` / `pyproject.toml`,
static-import grep over `src/ tests/ scripts/ tools/ cron_runner.py`.

**Result: 22 entries measured → 4 upgraded → 18 remain.** Full pytest green before and after
(4492 passed / 14 skipped / exit 0). No `--force-reinstall`, no `--ignore-requires-python`,
no `uv sync`, no pin loosened.

## 0. Reconciliation table

Rows are in `pip list --outdated` order (alphabetical) — diff this table against the raw JSON to verify.
`ALREADY_REVIEWED` = the package itself was in SUP-DEPS-20261013-AIP (6e39400) or
SUP-DEPS-20261013-AIP-RESIDUAL (d7d7bba); the reason column says why it is still listed.

| # | Package | Installed → Latest | Classification | Reason / evidence |
|---|---|---|---|---|
| 1 | altair | 6.2.2 → 6.3.0 | ALREADY_REVIEWED | Orphan root: `Required-by:` empty, declared in no requirements file, 0 static imports. Residual doc §3 = not-applicable (the venv rebuild deletes it). No action. |
| 2 | anthropic | 0.122.0 → 1.13.0 | ALREADY_REVIEWED | DIRECT (`anthropic>=0.117.0`, so 1.13.0 is constraint-compatible) but MAJOR 0→1 of the HTTP client; single import site `src/core/ai_client.py:52` is a live-LLM fallback. Prior review held it for a live-call smoke — a green unit suite cannot prove the endpoint still answers. |
| 3 | boto3 | 1.43.112 → 1.43.113 | TRANSITIVE_PINNED | `Required-by: litellm` (undeclared orphan); pair-locked to botocore (`<1.44.0`); 0 imports. The package was reviewed — the *release* (1.43.113) appeared after the residual batch moved the pair to 1.43.112. |
| 4 | botocore | 1.43.112 → 1.43.113 | TRANSITIVE_PINNED | `Required-by: boto3, s3transfer`; must move in lockstep with boto3 (same version). 0 imports. |
| 5 | cachebox | 5.2.3 → 6.2.8 | ALREADY_REVIEWED | Only parent is deepdiff (orphan root); MAJOR 5→6; residual doc: delete with the rebuild, never upgrade. |
| 6 | contourpy | 1.3.3 → 1.4.0 | ALREADY_REVIEWED | Orphan root (no Required-by, matplotlib/streamlit era), 0 imports; residual §3 not-applicable. |
| 7 | filelock | 3.32.7 → 4.1.1 | TRANSITIVE_PINNED | litellm (orphan) caps `filelock<4.0`; also required by datasets / huggingface_hub / virtualenv. |
| 8 | fonttools | 4.63.0 → 4.66.1 | ALREADY_REVIEWED | Orphan root, no Required-by, 0 imports; residual §3 not-applicable. |
| 9 | fsspec | 2026.7.0 → 2026.9.0 | TRANSITIVE_PINNED | datasets (orphan) caps `fsspec<=2026.7.0`; huggingface_hub also requires it. |
| 10 | huggingface_hub | 1.33.0 → 2.2.0 | TRANSITIVE_PINNED | litellm (orphan) caps `huggingface-hub<2.0`; MAJOR 1→2. |
| 11 | importlib_metadata | 8.9.0 → 9.0.1 | TRANSITIVE_PINNED | litellm (orphan) caps `importlib-metadata<9.0`; also required by docstring-to-markdown. |
| 12 | litellm | 1.104.2 → 1.105.0 | ALREADY_REVIEWED | Undeclared orphan (`Required-by:` empty, absent from requirements/pyproject/uv.lock, 0 imports) **and the cap source** for items 3/4/7/10/11/14. Correct handling is removal in the venv rebuild, not an upgrade — do not bump the blocker. |
| 13 | narwhals | 2.24.0 → 2.27.1 | ALREADY_REVIEWED | Orphan chain via altair, 0 imports; residual §3 not-applicable. |
| 14 | openai | 2.54.0 → 3.29.0 | TRANSITIVE_PINNED | litellm (orphan) caps `openai<3.0.0`; MAJOR 2→3. |
| 15 | pre_commit | 4.6.2 → 4.7.0 | **DIRECT_UPGRADABLE → UPGRADED** | DIRECT dev dep (`requirements-dev.txt` + `pyproject [project.optional-dependencies].dev`); 0 static imports; minor inside 4.x. Not in either prior batch — genuinely new. |
| 16 | pyboy | 2.7.0 → 2.8.1 | INCOMPATIBLE | Our own pin `pyboy>=1.0.0,<2.8.0` (`requirements.txt:18`, `pyproject.toml:12`) excludes 2.8.1. 2.8.x renumbers the logging constants and bumps save-state STATE_VERSION to 29, breaking the 10 tracked `*.state` files incl. the md5-pinned boot states. Needs a state-migration row, not a bump. |
| 17 | pydantic | 2.13.4 → 2.14.1 | **DIRECT_UPGRADABLE → UPGRADED** | DIRECT; `requirements.txt` already declared `pydantic>=2.13.5`, so the installed 2.13.4 was **below our own floor**; 2.14.1 is a 2.x minor. Floor raised to `>=2.14.1` after the suite went green. |
| 18 | pydantic_core | 2.46.4 → 2.50.1 | **DIRECT_UPGRADABLE → UPGRADED** | Not declared itself, but it is the *exact pin* of the DIRECT dep pydantic — installing `pydantic==2.14.1` resolved `pydantic-core==2.50.1` in the same transaction (no force flag). Cannot move alone. |
| 19 | ruff | 0.15.22 → 0.17.0 | ALREADY_REVIEWED | Deliberate project pin: CI installs `ruff==0.15.22` (`.github/workflows/ci.yml:82`) and the hold is documented ("0.16.x churns 2000+ lint findings"). Bumping only the venv would desync the local lint gate from CI, and CI edits are out of scope. |
| 20 | starlette | 1.3.1 → 1.8.0 | TRANSITIVE_PINNED | Transitive under fastapi (`Required-by: fastapi`), 0 static imports. **Uncertainty documented:** fastapi 0.143.0 declares only `starlette>=0.46.0` — an OPEN upper bound, so this is *not* an upstream cap. Held by doctrine (runtime surface beneath every dashboard route, no live dashboard-boot proof), classified TRANSITIVE_PINNED per the brief's ambiguity rule. |
| 21 | uvicorn | 0.52.3 → 0.54.0 | **DIRECT_UPGRADABLE → UPGRADED** | DIRECT; `requirements.txt` declares `uvicorn>=0.54.0`, so 0.52.3 was **below our own floor** and 0.54.0 is exactly that floor. One import site (`src/dashboard/main.py:510`). No requirements edit needed — the declaration was already correct. |
| 22 | websockets | 16.1.1 → 17.2 | ALREADY_REVIEWED | DIRECT (declared `>=12.0` in both files, so no constraint conflict) but MAJOR 16→17 under the ASGI/WS layer with 0 static imports — the suite cannot prove the dashboard's WS handshake. Prior review held it for a live WS smoke. |

| Classification | Count |
|---|---|
| DIRECT_UPGRADABLE (all upgraded) | 4 |
| TRANSITIVE_PINNED | 8 |
| ALREADY_REVIEWED | 9 |
| INCOMPATIBLE | 1 |
| ENV_NOISE | 0 |
| **Total** | **22** |

## 1. Why 22 and not the supervisor's 20

The supervisor's `check-deps.py` reports a **count**, not an enumerated list, so the two are reconciled
by construction rather than assumed equal:

- The residual doc's own §3 enumerated **19** rows (8 hold + 1 hold(pin) + 5 blocked + 5 not-applicable),
  while its §1 header claimed "16 hold + 4 not-applicable = 20" and its intro said "remaining 18" — three
  different numbers in one document. The **enumerated** list (19) is the one that reconciles.
- Measured 22 = those 19 + **boto3/botocore** (patch pair moved to 1.43.112 on 2026-10-13; 1.43.113 was
  published afterwards) + **pre_commit** (4.7.0 published after that batch). Both deltas are new
  *releases* of already-reviewed packages, not unreviewed packages.

Hypothesis (c) from the brief — "shared-environment noise from the host venv leaking into the scan" —
is **refuted for this scan**: all 22 resolve inside `.venv/lib/python3.13/site-packages` via `pip show`
and the scan was run with the project interpreter. (The repo does contain a second, unrelated `./venv/`
at Python 3.11; it is not the scan target and contributed nothing.)

## 2. Upgrades applied (4 packages, one transaction, no collateral)

`uv pip install --python .venv/bin/python -r <4-pin file>` — targeted installs, **never `uv sync`**
(which prunes .venv extras; repo history).

| Package | From → To | Why it is safe |
|---|---|---|
| pre_commit | 4.6.2 → 4.7.0 | direct dev dep, 0 static imports, minor |
| uvicorn | 0.52.3 → 0.54.0 | direct, exactly our declared floor, 1 import site covered by `tests/test_dashboard.py` |
| pydantic | 2.13.4 → 2.14.1 | direct, 2.x minor, closes a floor violation |
| pydantic_core | 2.46.4 → 2.50.1 | pydantic's own exact pin, resolved (not forced) with pydantic |

Declared-floor edits (minimal, evidence-backed): `requirements.txt` `pydantic>=2.13.5 → >=2.14.1`;
`requirements-dev.txt` + `pyproject [project.optional-dependencies].dev` `pre-commit>=3.0 → >=4.7.0`
(name-level parity is asserted by `tests/test_requirements_parity.py`; specifiers are not).

## 3. Verification

- `pip list` diff before/after: **exactly** those four version changes, nothing else (155 dists).
- `pip check`: clean before and after.
- Floor audit over both requirements files: `declared-and-satisfied: 28`, `floor violations: 0`
  (before the batch, pydantic and uvicorn were installed *below* their own declared floors).
- `pip list --outdated --format=json`: **22 → 18** (pre_commit, pydantic, pydantic_core, uvicorn removed).
- `.venv/bin/python -m pytest tests/ -x -q --timeout=60` → **exit 0**, 4492 passed / 14 skipped
  (baseline at HEAD: same counts, exit 0). Runtime: 188.7s baseline → 206.3s post-bump (same host load band).
- `uv.lock` deliberately **not** regenerated: these were targeted installs; the lock/venv divergence is
  pre-existing and is a rebuild-source-of-truth decision, not this task's scope (same call as d7d7bba).

## 4. Honest gaps

- **Not upgraded on purpose:** the 8 TRANSITIVE_PINNED (upstream or orphan-parent caps — bumping would
  break the dep tree), 9 ALREADY_REVIEWED (majors needing live smokes, the ruff CI pin, orphan roots the
  rebuild deletes), 1 INCOMPATIBLE (pyboy, blocked by our own `<2.8.0` pin).
- **Blocked forever until the venv rebuild:** openai / filelock / huggingface_hub / importlib_metadata /
  boto3 / botocore are all capped by `litellm`, an undeclared orphan that is imported nowhere. Removing
  litellm (prior review §11 / the rebuild) collapses 4 major-version holds at once.
- **Not proven by tests:** websockets and starlette sit under the dashboard's runtime surface with zero
  static imports, so the green suite is not evidence for them; anthropic likewise needs a live call.
- **Live processes:** `aipp_mcp.py`, `game_bridge.py` and `aipp-console/server.py` run from this venv.
  Already-running processes keep their loaded modules; they pick up the four new versions on next restart.
- **Security:** no advisory scan was run (no scanner installed in .venv) — the prior review's gap stands.
