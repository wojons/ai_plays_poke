# Dependency Reconciliation — 2026-10-15 (SUP-DEPS-20261015-AIP-FOLLOWUP)

Follow-up to `dependency_reconcile_20261014.md` (SUP-DEPS-20261014-AIP-FOLLOWUP, d8efb95),
which itself continued the 2026-10-13 chain (`dependency_review_20261013.md` 6e39400,
`dependency_residual_20261013.md` d7d7bba, batch `b83e7db`).

**Surface:** `.venv/` (Python 3.13.13) — the authoritative test env (`test_command` runs
`./.venv/bin/pytest`). `venv/` (Python 3.11) is a stale duplicate, not authoritative; both
venvs are real directories (no symlink involved, nothing deleted or modified outside the
classification work).

Scan: `.venv/bin/pip list --outdated` → **22 entries today** (prior review scanned 21;
the delta is `pluggy 1.6.0 → 1.7.0`, newly listed since d8efb95, and `fastapi` moving
0.143.1 → 0.143.2 latest).

**Method:** targeted installs only (`uv pip install --python .venv/bin/python <pkg>==<ver>`,
no `uv sync`, no force flags, no pin changes); `pip check` after the batch; `ruff check .`;
`mypy src/ --ignore-missing-imports`; focused smoke; full suite left to the foreman. Every
verdict re-verified against current installed state (dist-info METADATA caps re-read
today), not copied from the prior doc.

## Result

**2 upgraded, 9 held, 9 orphan-chain, 2 N/A (pin) = 22.** Post-batch scan: 20 remaining
(22 − 2 upgraded).

## Reconciliation table

All 22 entries in `pip list --outdated` order. Classification rules per the prior reviews:
orphan = undeclared in `requirements*.txt` / `pyproject.toml` / `uv.lock` root deps and
`Required-by:` resolves only to orphans; orphan-chain = transitive of an orphan.

| # | Package | Installed → Latest | Verdict | Reason (re-verified 2026-10-15) |
|---|---|---|---|---|
| 1 | altair | 6.2.2 → 6.3.0 | orphan-chain | Orphan root (`Required-by:` empty; absent from all manifests; 0 static imports — streamlit-era leftover). Rebuild removes it. |
| 2 | anthropic | 0.122.0 → 1.15.0 | held | MAJOR 0→1. DIRECT dep (`requirements.txt:22` `anthropic>=0.117.0`, `pyproject.toml:17` `anthropic>=0.3.0`) so the constraint permits the jump, BUT it is imported by `src/core/ai_client.py:52` and drives a live LLM endpoint — a green unit suite cannot prove the endpoint answers. Hold stands per prior doctrine; needs a dedicated live-call smoke row. Latest drifted 1.14.0→1.15.0 since the prior doc. |
| 3 | boto3 | 1.43.112 → 1.43.114 | orphan-chain | Sole parent litellm (undeclared orphan, `Required-by:` empty); 0 project imports; pair-locked to botocore. |
| 4 | botocore | 1.43.112 → 1.43.114 | orphan-chain | Same chain as boto3 (Required-by boto3/s3transfer only); 0 imports. |
| 5 | cachebox | 5.2.3 → 6.2.8 | orphan-chain | Only parent deepdiff (orphan); MAJOR 5→6; delete-with-rebuild doctrine, never upgrade. |
| 6 | contourpy | 1.3.3 → 1.4.0 | orphan-chain | Orphan root (0 Required-by; matplotlib-era; present in `uv.lock` only as a resolved transitive of a since-dropped dep); 0 imports. |
| 7 | fastapi | 0.143.1 → 0.143.2 | **upgraded** | DIRECT (`requirements.txt:36` `fastapi>=0.142.2`); pure patch; verified from 0.143.2's wheel METADATA: `starlette>=0.46.0` (open upper bound; installed 1.3.1 satisfies), `pydantic>=2.9.0` (2.14.0 satisfies). `pip check` clean post-install. |
| 8 | filelock | 3.32.7 → 4.2.0 | held | MAJOR 3→4; litellm (orphan) caps `filelock>=3.16.1,<4.0` (re-read from installed dist-info METADATA today). Note: the prior doc's venv reported 3.31.1; the authoritative `.venv` holds 3.32.7 — same verdict. Unblocks via venv rebuild. |
| 9 | fonttools | 4.63.0 → 4.67.0 | orphan-chain | Orphan root, 0 imports. |
| 10 | fsspec | 2026.7.0 → 2026.9.0 | held | litellm (orphan) caps `fsspec[http]<=2026.7.0`; installed version sits exactly at the orphan's ceiling; ceiling disappears with the rebuild. |
| 11 | GitPython | 3.2.0 → 3.2.1 | orphan-chain | `Required-by:` empty; undeclared in all manifests (requirements.txt documents it as streamlit's dropped subtree); 0 static imports. |
| 12 | huggingface_hub | 1.33.0 → 2.2.0 | held | MAJOR 1→2; litellm (orphan) caps `huggingface-hub<2.0`. |
| 13 | importlib_metadata | 8.9.0 → 9.0.1 | held | MAJOR 8→9; litellm (orphan) caps `importlib-metadata<9.0`. |
| 14 | litellm | 1.104.2 → 1.105.1 | orphan-chain | The cap source itself: undeclared orphan (0 hits in every manifest, 0 imports) whose metadata caps openai/filelock/huggingface_hub/importlib_metadata/fsspec below latest. Removal in the venv rebuild is the correct handling — do not upgrade the blocker. |
| 15 | narwhals | 2.24.0 → 2.27.1 | orphan-chain | Transitive of altair (orphan chain), 0 imports. |
| 16 | openai | 2.54.0 → 3.31.0 | held | MAJOR 2→3; litellm (orphan) caps `openai>=2.20.0,<3.0.0`. Not imported by project code (OpenRouter model-name strings only, per requirements.txt:43-44 comment). |
| 17 | pluggy | 1.6.0 → 1.7.0 | **upgraded** | NEW today (not in d8efb95's 21). Transitive of declared dev deps: pytest 9.1.1 (`pluggy<2,>=1.5`), pytest-cov (`pluggy>=1.2`), python-lsp-server (`pluggy>=1.0.0`) — 1.7.0 inside every range; minor 1.x bump; 0 direct project imports. |
| 18 | pyboy | 2.7.0 → 2.8.1 | N/A | Self-blocked by the project's own pin `pyboy>=1.0.0,<2.8.0` (requirements.txt:18, state-VERSION-29 + logging-constant renumber documented in the pin comment). Needs a state-migration row, not a bump. |
| 19 | pymongo | 4.18.3 → 4.19.0 | orphan-chain | Orphan root (`Required-by:` empty, absent from all manifests, 0 imports). NEW vs prior doc's table. |
| 20 | ruff | 0.15.22 → 0.17.1 | N/A | Intentionally pinned: CI installs `ruff==0.15.22` (`.github/workflows/ci.yml:82`); bumping the venv alone would desync local lint from CI. |
| 21 | starlette | 1.3.1 → 1.8.0 | held | Transitive under fastapi; fastapi (incl. today's 0.143.2, verified from its wheel METADATA) declares only `starlette>=0.46.0` — an OPEN upper bound, so this is doctrine-held, not cap-held: five minors under every dashboard route with no live dashboard-boot/WS proof; deserves its own verify row. |
| 22 | websockets | 16.1.1 → 17.2 | held | MAJOR 16→17 (DIRECT, `websockets>=12.0` so constraint-compatible) under the ASGI/WS layer with 0 static imports — the suite cannot prove the dashboard's WS handshake; needs a live WS smoke row. |

| Verdict | Count |
|---|---|
| upgraded | 2 |
| held | 9 |
| orphan-chain | 9 |
| N/A (pin) | 2 |
| **Total** | **22** |

## Scan-count note (22 today vs 21 at d8efb95)

Same env (`.venv`), one day later: `pluggy 1.7.0` appeared as newly-listed-outdated (pytest
ecosystem release), and `fastapi` latest moved 0.143.1 → 0.143.2 (d8efb95 already upgraded to
0.143.1). Net +1 row. The `venv/` (Python 3.11) duplicate scan lists a different superset
(includes editable installs like chimera-deliberation/gitreins that leak into that old env);
it was used only as cross-check evidence and is NOT the classification surface.

## Upgrades applied (one transaction, no collateral)

`uv pip install --python .venv/bin/python fastapi==0.143.2 pluggy==1.7.0` →
`Uninstalled 2 / Installed 2`, exactly those two packages; `.venv/bin/pip check`:
**No broken requirements found.**

## Honest gap statement

- All 22 entries carry an explained verdict (no unexplained nulls).
- Not done deliberately: the five litellm-capped majors + fsspec stay blocked until the venv
  rebuild (standing recommendation, still not executed); anthropic/websockets majors and
  starlette still need dedicated live-smoke verify rows; pyboy needs a state-migration row.
- `uv.lock` not regenerated (targeted installs only); lock-vs-venv divergence is pre-existing
  and a rebuild-source-of-truth decision, out of scope here.
- No advisory/security scan run (no scanner in `.venv`; prior review §12 gap stands).
- The stale `venv/` (Python 3.11) duplicate was left untouched; folding it away belongs to the
  venv-rebuild row.

## Verification

- `.venv/bin/pip check` after batch: clean.
- `.venv/bin/ruff check .`: All checks passed!
- `.venv/bin/mypy src/ --ignore-missing-imports`: Success: no issues found in 69 source files.
- Focused smoke: `pytest tests/ -x -q -k "game_bridge or ai_client or dashboard" --timeout=600`
  — result recorded in the commit message.
