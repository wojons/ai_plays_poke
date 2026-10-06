# DEPS-AIPP-001 — Safe grouped upgrades of direct dependencies

## Summary

| Metric | Value |
|---|---|
| Outdated packages (project venv) | 46 |
| Direct deps among outdated | 15 |
| Upgraded (non-major, non-risky) | 6 |
| Deferred direct deps | 9 |
| Transitive deps (left to resolver) | 31 |
| `pip check` | PASS (all compatible) |
| `pytest tests/ -x -q` | 4410 passed, 14 skipped (green) |

## Environment note (important)

The 2026-10-06 supervisor scan reported ~137 rows from `pip list --outdated`, but that
list was read from the **system** pip (`/usr/bin/pip`, Python 3.11), not the project
venv. The project venv at `.venv` is **uv-managed** (Python 3.13, `uv.lock` present) and
has no `pip` binary inside it. Running `uv pip list --outdated --python .venv/bin/python`
shows the true venv state: **46** outdated packages. All work below was done against the
venv via `uv pip`, and `uv pip check` is the `pip check` equivalent.

## Upgrades performed (6 direct deps, grouped)

### Group 1 — runtime, patch-level
| Package | From | To | Bump |
|---|---|---|---|
| python-dotenv | 1.2.2 | 1.2.4 | patch |
| tqdm | 4.70.0 | 4.70.1 | patch |

### Group 2 — runtime, minor
| Package | From | To | Bump |
|---|---|---|---|
| uvicorn | 0.52.3 | 0.54.0 | minor |

### Group 3 — dev tooling
| Package | From | To | Bump |
|---|---|---|---|
| flake8 | 7.4.0 | 7.4.1 | patch |
| mypy | 2.3.1 | 2.4.0 | minor |
| black | 26.5.1 | 26.10.0 | minor (CalVer) |

Transitive packages moved by the resolver as a side effect (not hand-pinned):
`click` 8.4.2→8.5.0, `ast-serialize` 0.11.2→0.12.1, `librt` 0.15.0→0.16.0,
`platformdirs` 4.11.12→4.12.3, `pyflakes` 4.0.0→4.0.2.

## Deferred (skipped) — direct deps

| Package | Current | Latest | Decision | Reason |
|---|---|---|---|---|
| numpy | 2.5.2 | 2.5.3 | skip | flagged risky in task brief (core numeric infra) |
| pydantic | 2.13.4 | 2.13.5 | skip | flagged risky in task brief (core validation infra) |
| fastapi | 0.141.1 | 0.142.2 | skip | flagged risky in task brief; 0.x minor is breaking |
| anthropic | 0.122.0 | 1.11.0 | skip | major bump (0.x → 1.x) |
| websockets | 16.1.1 | 17.2 | skip | major bump (16 → 17) |
| openai | 3.1.0 | 3.24.0 | skip | declared only in pyproject.toml; not in requirements.txt |
| streamlit | 1.61.1 | 1.65.0 | skip | declared only in pyproject.toml; not in requirements.txt |
| pandas | 3.0.5 | 3.0.6 | skip | declared only in pyproject.toml; not in requirements.txt |
| matplotlib | 3.11.1 | 3.11.2 | skip | declared only in pyproject.toml; not in requirements.txt |

Notes:

- **risky (named in brief):** numpy / pydantic / fastapi / Pillow were pre-flagged as
  risky. Pillow is not outdated (12.3.0 == latest), so no Pillow row. The remaining three
  are deferred even though their bumps are patch-level, per the brief's safety directive.
- **major:** anthropic and websockets have real major bumps — out of scope by rule.
- **pyproject-only:** openai, streamlit, pandas, matplotlib are declared only in
  `pyproject.toml` `[project].dependencies`, not in `requirements.txt`. Upgrading them
  would require editing `pyproject.toml`, which is out of scope (deliverable manifests are
  `requirements.txt` / `requirements-dev.txt`).

## Transitive / undeclared (not hand-upgraded)

31 packages (e.g. altair, anyio, coverage, starlette, urllib3, ruff, pyarrow, protobuf,
virtualenv, zipp, ...) are transitive or undeclared. Per rule 2 these are left to the
resolver and were not bulk-upgraded by hand.

## Verification

- `uv pip check --python .venv/bin/python` → **"All installed packages are compatible"**
  (checked after each group and at the end).
- `python -m pytest tests/ -x -q` → **4410 passed, 14 skipped** in ~235s (baseline was
  4410 passed, 14 skipped in ~199s — identical, green).

## Files changed

- `requirements.txt` — bumped floors: python-dotenv>=1.2.4, tqdm>=4.70.1, uvicorn>=0.54.0
- `requirements-dev.txt` — bumped floors: black>=26.10.0, mypy>=2.4.0, flake8>=7.4.1
- `deps-report.md` — this report
