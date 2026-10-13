# Dependency Review — 2026-10-12 Supervisor Scan (SUP-DEPS-20261012-AIP)

**Type:** Analysis only. No requirements files modified, nothing installed, no upgrades executed.
**Method:** live `pip list --outdated` on BOTH venvs (reproduces the supervisor delta) → classified against requirements.txt + requirements-dev.txt → compared against docs/dependency_review_20261010.md (SUP-DEPS-20261009-AIP baseline).
**Prior workers failed twice** (silent, no artifacts); this review was run INLINE per the row's foreman note.

## Delta vs the 2026-10-11 review (batch-4 surface)

| Metric | 10-09 scan (reviewed venv) | This scan (`.venv` py3.13) |
|---|---|---|
| Total outdated | 142 | **44** |
| Direct, outdated | 14 | 4 (black, pyboy, anthropic, websockets) |
| MAJOR-version bumps | 4 direct | 2 direct (anthropic, websockets) + 5 transitive |
| Advisories on DIRECT deps | 0 | 0 |

Batch 4 (6434692) removed the 4 vestigial pyproject deps (openai/streamlit/pandas/matplotlib) and pinned pyboy — that is the bulk of the shrink. No NEW direct exposure appeared since.

## venv/ (py3.11) is NO LONGER the project surface

The py3.11 `venv/` reports **108 outdated** — but pip-classified direct deps there number 3 and it carries unrelated tooling (litellm, twine, gymnasium, awscrt, h3-shim, gitreins editable, chimera-deliberation editable...). The previous review already scoped to the runtime surface; this scan confirms venv/ has drifted into a general-purpose environment. **Recommendation: stop auditing venv/ wholesale; audit `.venv/` (the tested venv, gitreins test_command) or rebuild venv/ from requirements. Filed as recommendation, not action.**

## Direct-dependency verdicts (`.venv` surface)

| Package | Current | Latest | Verdict |
|---|---|---|---|
| black | 26.10.0 | 26.10.1 | **update-now** (dev-only, patch bump) |
| pydantic | 2.14.0 | 2.14.1 | **update-now** (patch within 2.x) |
| pyboy | 2.7.0 | 2.8.1 | **hold** — still self-blocked by `>=1.0.0,<2.8.0` (tests/test_emulator_pyboy_logging.py pins monotonic log constants; 2.8.x renumbered). Unchanged since batch 4; needs its own verify-then-relax row. |
| anthropic | 0.122.0 | 1.13.0 | **update-with-testing** — MAJOR 1.0 boundary (httpx→httpx2, legacy completions removed). Project uses Messages client only (src/core/ai_client.py). Needs live LLM smoke. Carried over from 10-11 review with same verdict. |
| websockets | 16.1.1 | 17.2 | **update-with-testing** — legacy asyncio impl formally deprecated (removal ~2030); project runs server-side only (Starlette WS in dashboard). Needs dashboard boot + /ws smoke. |

## Transitive MAJOR bumps (all .venv, none direct)

cachebox 5→6, filelock 3→4, huggingface_hub 1→2, importlib_metadata 8→9, openai 2→3 (litellm-only consumer, caps its own range). None imported by project code directly; no security driver; **no action planned** — revisit only when a parent package forces it.

## Security

Direct deps: **0 known advisories**. The earlier `/tmp/sup-deps-scan.txt` findings (ecdsa PYSEC-2026-1325, python-jose CVE-2026-85394) are NOT INSTALLED in either project venv — they came from the py3.11 venv's tooling drift and are out of project scope.

## Planned upgrade order (execute in a future EXEC row, not here)

1. black + pydantic patch (mechanical) → full suite.
2. websockets 17.x → dashboard WS smoke → suite.
3. anthropic 1.x → live LLM-call smoke → suite.
4. pyboy: separate row to re-verify the logging-constant suite on 2.8.x, then relax the pin.
