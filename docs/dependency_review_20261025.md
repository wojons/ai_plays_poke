# Dependency Review — 2026-10-25 (SUP-DEPS-20261022-AIP)

Continues the 2026-10-13 → 2026-10-19 chain (`dependency_review_20261013.md`,
`dependency_residual_20261013.md`, `dependency_reconcile_20261014.md`,
`dependency_reconcile_20261015.md`, `dependency_review_20261019.md`) and the
2026-10-20 fastapi bump (`SUP-DEPS-20261020-AIP`, commit 0eea256).

**Surface:** a fresh worktree venv built from the upgraded manifests
(`uv venv --seed --python 3.13 .venv` + `uv pip install -r requirements.txt
-r requirements-dev.txt`), Python 3.13.13. This differs from the 10-19 method:
that review upgraded the drifted main-clone venv in place; this review rebuilds
from manifests, which is the only state a fresh clone can reproduce.

**Scan provenance (important):** the dispatch row quoted "35 outdated, 6 major
drifts" from `scripts/check-deps.py` run 2026-10-22 against
`/home/kara/ai_plays_poke/.venv` — the main clone's venv, which still carries
pre-batch-4 residue (see below). Two of the six "majors" (openai, pandas) and
both undeclared packages (cachebox, huggingface_hub) exist only in that venv;
they were removed from the manifests in SUP-DEPS batch 4 (2026-10-11, commit
36c58de) with zero importers, and the 10-19 review already classified them
held-orphan. A fresh clone never installs them.

## Verdict per named package (the row's six majors)

| Package | Row claimed | Verdict | Reason |
|---|---|---|---|
| anthropic | 1.15.0 → 2.1.0 | **upgraded 1.15.0 → 2.3.0** (latest; row snapshot 2.1.0 superseded by 2.2.0/2.3.0 on 10-23) | DIRECT dep (`requirements.txt`), imported at `src/core/ai_client.py:52` (lazy, try/except). Usage surface is `Anthropic(api_key=...)` + `messages.create(..., extra_body={"temperature": ...})`. The 2.0.0 changelog (2026-10-21) lists exactly one breaking change: default API version bumped to 2026-10-21; 2.1.0–2.3.0 add Admin-API surfaces. No removals touching `messages.create()`. The `extra_body` forward (from the 10-19 fix, guarded by `TestClaudeClientRealSDKCallShape`, a real-SDK loopback test) is valid on 0.x/1.x/2.x. RED-proof: that test fails with `TypeError: ... unexpected keyword argument 'temperature'` when the `extra_body` forward is reverted — the 1.x break regression test is already in the suite and stays the guard. |
| fastapi | 0.152.0 → 0.160.0 | **upgraded 0.152.0 → 0.162.0** (latest; row snapshot 0.160.0 superseded by 0.161.x/0.162.0 on 10-22/23) | DIRECT dep (requirements.txt, requirements-dev.txt, pyproject main+dev). Consumers: `src/dashboard/main.py`, `src/env_service.py`, `web_viewer.py` + TestClient in two test files. Breaking changes 0.153→0.162 checked: **0.155.0** removed deprecated `**extra` kwargs from `Query/Header/Cookie/Body/Form/File` — repo grep has 0 uses (only `Header(None)`, `Query(...)`); **0.160.0** changed parameter-model `extra` semantics (sibling-field application) — repo sets no custom `extra=` configs; 0.161.x are bugfixes. |
| cachebox | 5.2.3 → 6.2.8 | **held (orphan)** — absent after rebuild | Never declared in any manifest at any point in git history (`git log -S cachebox` on the manifest files: empty), zero imports repo-wide. In the main-clone venv only as residue under the orphan `deepdiff` (itself orphaned since batch 4). `pip list --outdated` can no longer list it in a manifest-clean venv because it is not installed. |
| huggingface_hub | 1.33.0 → 2.2.0 | **held (orphan)** — absent after rebuild | Same class as cachebox: never declared (git `-S` empty), zero imports. Main-clone residue only. (10-19 note stands: its old-venv 1→2 bump was additionally capped by orphan `litellm`.) |
| openai | 2.54.0 → 3.36.1 | **held (not installed; was orphan)** | Declared 2025-2026-early but removed in batch 4 with evidence: imported NOWHERE (`openai` appears only as OpenRouter model-name strings like `"openai/gpt-5.6-luna"`). 10-19: 0 imports, sole old-venv parent the orphan `litellm` which caps `openai<3.0`. LLM calls go through OpenRouter via `requests` (`src/core/ai_client.py`), not the openai SDK. |
| pandas | 3.0.6 → 3.1.0 | **held (not installed; was orphan)** | Removed in batch 4 with the same evidence class: zero imports. Old-venv residue only. |

The four holds are honest `none:<reason>`-style outcomes, recorded here and in
the manifests' history rather than fabricated as "current": a venv built from
the tracked manifests does not contain these packages, so they cannot appear in
an outdated scan. Acceptance criterion 1 is satisfied by *absence* (the grep
prints 0), which the criterion itself defines as success.

## Consequential change: requires-python ">=3.10" → ">=3.11"

Regenerating `uv.lock` was impossible under the declared `>=3.10`:
`pre-commit==4.7.0` (dev extra, floor-bumped 2026-10-11) requires Python≥3.11,
so uv refuses to solve (`No solution found ... pre-commit==4.7.0 cannot be
used` for the `python_full_version == '3.10.*'` split). The old lock predates
that floor bump (it still contains openai/pandas/matplotlib/streamlit-era
packages and no fastapi at all) and was therefore stale beyond any targeted
refresh. Every runtime environment in use already requires ≥3.11 (CI
`.github/workflows/ci.yml:70` python 3.11; project venv 3.13), so the floor
bump matches reality. README "Python 3.10+" updated to 3.11+ accordingly.

## Lock regeneration

`uv lock` (RC=0) from the upgraded pyproject: **74 packages** resolved (was 106
in the stale lock — the streamlit/openai/pandas/matplotlib dead subtree gone),
`anthropic 2.3.0`, `fastapi 0.162.0`, `pyboy 2.7.0` (pin `>=1.0.0,<2.8.0`
respected), no openai/pandas/cachebox/huggingface_hub entries. AC-2 therefore
reports `uv.lock` + `requirements.txt` as the two changed dependency surfaces.

## Manifest changes

- `requirements.txt`: `anthropic>=1.15.0` → `>=2.3.0` (comment extended with
  the 2.x verdict); `fastapi>=0.152.0` → `>=0.162.0` (comment carries the two
  breaking-change checks).
- `requirements-dev.txt`: `fastapi>=0.152.0` → `>=0.162.0`.
- `pyproject.toml`: same two bumps (main + dev extra for fastapi);
  `requires-python = ">=3.11"` with inline rationale.
- `uv.lock`: regenerated (74 packages, see above).
- `README.md`: System Requirements 3.10+ → 3.11+; Dependencies block re-quoted
  from the requirement files (README-31 convention: the block must match).

## Application method

Fresh venv from manifests (not targeted installs): `uv venv --seed --python 3.13
.venv`, then `uv pip install --python .venv/bin/python -r requirements.txt -r
requirements-dev.txt`. Rationale: the drifted main-clone venv cannot be the
acceptance surface (its extra packages are exactly what this row is about), and
manifest-build is what a fresh clone reproduces. No `uv sync` was run (nothing
to prune; the venv is manifest-built).

## Side effect of the rebuild worth naming

The fresh resolve moved `websockets` 16.1.1 → 17.3 and `starlette` 1.3.1 →
1.10.0 (transitives of the open-upper dashboard pins). The 10-19 review held
in-place bumps of these pending a live WS smoke row — that concern applies to
the *drifted* venv; a manifest-built venv gets the newest satisfying versions
by construction, and the tracked dashboard test suite (including bind-failure
and boot-banner tests) is the in-CI witness for the server layer. The
live-WS-smoke row request from 10-19 remains open and still applies.

## Honest gaps

- No live LLM call was made (no `ANTHROPIC_API_KEY` here); the anthropic 2.x
  verdict rests on the changelog diff (single breaking change = default API
  version date) plus the real-SDK loopback test, same evidence bar as 10-19.
- No live dashboard/WebSocket smoke (unchanged from 10-19; still its own row).
- The row's witness suggestion (headless emulator run) was not run: no ROM in
  this worktree and the row's own acceptance criteria (outdated scan, manifest
  diff, `pytest -x -q`) define the required gates instead.
- pyboy stays pinned `>=1.0.0,<2.8.0` (save-state format break; needs a state
  migration row, per requirements.txt and the 10-19 review).
