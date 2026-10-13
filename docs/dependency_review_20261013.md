# Dependency Review — 2026-10-13 Supervisor Scan (SUP-DEPS-20261013-AIP)

**Type:** Analysis only. **No package was installed, upgraded, or removed.** `requirements.txt`,
`requirements-dev.txt`, `pyproject.toml` and `uv.lock` are unchanged by this task.

**Reviewed surface:** `.venv/` (Python 3.13.13) — the runtime venv the project actually tests
with. `.gitreins/config.yaml` sets `test_command: ./.venv/bin/pytest -x --tb=short`, so `.venv`
is the authoritative environment. The py3.11 `venv/` is out of scope (see §8).

**Method (all commands run against the repo, no state changed):**

| Step | Command | Result |
|---|---|---|
| Supervisor scan | `python3 ~/.hermes/skills/coding-hermes-supervisor/scripts/check-deps.py /home/kara/ai_plays_poke` | `Python: OUTDATED (44)` |
| Independent reproduction | `.venv/bin/pip list --outdated --format=json` | **44** entries (matches) |
| Parentage | `.venv/bin/pip show` (`Required-by`) for all 44 | see §4 |
| Cap analysis | `importlib.metadata.requires()` on every installed parent | see §6 |
| Code surface | `grep -rnE` for `import` / `from` lines of each package under `src tests scripts tools cron_runner.py` | see §4 |
| Cross-venv delta | `venv/bin/pip list --outdated` (py3.11) | 108 entries |

**References:**
- `docs/dependency_review_20261012.md` — SUP-DEPS-20261012-AIP (the immediately prior review)
- `docs/dependency_review_20261010.md` — SUP-DEPS-20261009-AIP baseline / batch-4 record

---

## 1. Headline

The **set of 44 is unchanged from yesterday's scan**, and **no previously-identified package moved
further**. What this review adds over 2026-10-12 is (a) the full itemisation — yesterday's document
enumerated only 10 of the 44 — and (b) the *structural* finding: **most of the 44 are not project
dependencies at all.**

The `.venv` holds **155 installed distributions**, of which **31 are undeclared top-level
installs** (nothing installed requires them, and nothing in `requirements*.txt` / `pyproject.toml`
declares them). Those orphans — `litellm`, `datasets`, `deepdiff`, `ruff`, `protobuf`,
`gitpython`, and the matplotlib/streamlit/Flask leftovers — drag in the majority of the outdated
list. **`litellm` alone caps four of the seven major-version bumps at versions the project could
otherwise take.**

The highest-value action is therefore **not** 44 pin bumps. It is to **rebuild `.venv` from
`requirements.txt` + `requirements-dev.txt` (or `uv sync` against `uv.lock`)**, which removes the
orphan surface and with it roughly half this list — and which *unblocks* the four litellm-capped
majors in one deterministic step. That rebuild is **recommended here, not executed** (§11).

---

## 2. How the "44" was obtained — and a defect in the scan's own output

`check-deps.py` reports the count correctly but **cannot show you the whole list**:

- `check-deps.py:153` caps the Python listing at `out[:25]` — a header line plus **24 entries**.
  The 2026-10-13 run printed `OUTDATED (44)` followed by exactly 24 rows (through `litellm`), then
  moved on. Anything reading the scan output sees 24 of 44.
- `check-deps.py` also ignores `argv` entirely: passing the project path does not scope it; it
  sweeps all 15 projects in its map. The ai_plays_poke section was extracted from the full sweep.

The full 44 in this document were reproduced independently with
`.venv/bin/pip list --outdated --format=json` (44 entries, identical set). The **count** in the
supervisor output is trustworthy; its **listing** is truncated. Filed as an observation for the
supervisor, not as a project change.

---

## 3. Direct vs transitive — surface summary

Classification rule: **direct** = declared in `requirements.txt`, `requirements-dev.txt` or
`pyproject.toml`; **transitive** = present only because something else pulls it in.

| Class | Count |
|---|---|
| Direct (declared) | **10** |
| Transitive (declared-parent chain) | 12 |
| Transitive (deferred/blocked by a cap) | 5 |
| Transitive (orphan root — undeclared, nothing requires it) | 17 |
| **Total** | **44** |

**17 of 44 are undeclared orphans.** Their "current → latest" gap is real, but upgrading them
individually is maintenance on packages the project never asked for.

### 3.1 The undeclared surface (31 roots, of which 17 appear in the 44)

`pip show` shows `Required-by:` empty for all of these, and `grep -c litellm uv.lock
pyproject.toml requirements.txt requirements-dev.txt` returns **0 for every file**. Selected
roots, with what they explain:

| Orphan root | Version | Drags in (from the 44) |
|---|---|---|
| `litellm` | 1.104.2 | boto3, botocore, openai, huggingface_hub, fsspec, importlib_metadata, jiter, click, filelock, protobuf |
| `datasets` | 5.1.0 | fsspec, huggingface_hub, filelock (and pandas/pyarrow, not in the 44) |
| `deepdiff` | 9.1.0 | cachebox |
| `altair` / `gitpython` / `pydeck` / `watchdog` / `werkzeug` / `blinker` / `itsdangerous` | — | altair, narwhals, contourpy, fonttools, kiwisolver (matplotlib/streamlit/Flask era) |
| `ruff` | 0.15.22 | itself (a lint tool, not a library dependency) |
| `protobuf`, `tenacity`, `pyparsing`, `httptools` | — | themselves |

Also present and undeclared: `cbor2`, `cryptography`, `cycler`, `h2`, `httpx2`, `pyasn1`,
`pyjwt`, `pymongo`, `python-multipart`, `toml` — not in the 44, listed for completeness.

Removing the 31 orphan roots removes their subtrees; that is the mechanism by which a rebuild
reshapes this list.

---

## 4. Full inventory — all 44 outdated distributions

`Parent` = what `pip show … Required-by` reports. `Code?` = number of files under
`src/ tests/ scripts/ tools/ cron_runner.py` with a static `import`/`from` of the package.

### 4.1 Direct dependencies (10)

| # | Package | Current | Latest | Class | Change | Code? | Risk |
|---|---|---|---|---|---|---|---|
| 1 | `anthropic` | 0.122.0 | **1.13.0** | direct (requirements.txt) | **MAJOR 0→1** | 1 | **HIGH** — HTTP-client generation move |
| 2 | `black` | 26.10.0 | 26.10.1 | direct (requirements-dev.txt) | patch | 0 (tool) | low |
| 3 | `numpy` | 2.5.2 | 2.5.4 | direct (requirements.txt) | patch (2.5.x) | 44 | low |
| 4 | `pre_commit` | 4.6.2 | 4.7.0 | direct (requirements-dev.txt) | minor | 0 (tool) | low |
| 5 | `pyboy` | 2.7.0 | **2.8.1** | direct, **pinned `<2.8.0`** | **MAJOR, self-blocked** | 10 | **HIGH** |
| 6 | `pydantic` | 2.13.4 | 2.14.1 | direct (requirements.txt) | minor | 1 | medium (coupled, §6) |
| 7 | `python-dotenv` | 1.2.2 | 1.2.4 | direct (requirements.txt) | patch | 0 | low — **below declared floor** |
| 8 | `tqdm` | 4.70.0 | 4.70.1 | direct (requirements.txt) | patch | 0 | low — **below declared floor** |
| 9 | `uvicorn` | 0.52.3 | 0.54.0 | direct (requirements.txt) | minor (0.x) | 1 | low-med — **below declared floor** |
| 10 | `websockets` | 16.1.1 | **17.2** | direct (requirements.txt) | **MAJOR 16→17** | 0 | **HIGH** |

### 4.2 Transitive (34)

| # | Package | Current | Latest | Class | Parent (Required-by) | Change | Code? | Risk |
|---|---|---|---|---|---|---|---|---|
| 11 | `altair` | 6.2.2 | 6.3.0 | transitive (orphan root) | *orphan root* (none) | minor | 0 | low |
| 12 | `anyio` | 4.14.2 | 4.15.1 | transitive | anthropic, httpx, httpx2, openai, starlette | minor | 0 | low |
| 13 | `ast_serialize` | 0.12.1 | 0.13.0 | transitive | mypy *(direct dev)* | 0.x minor | 0 | low |
| 14 | `boto3` | 1.43.111 | 1.43.112 | transitive | litellm *(orphan)* | patch | 0 | low |
| 15 | `botocore` | 1.43.111 | 1.43.112 | transitive | boto3, s3transfer | patch | 0 | low |
| 16 | `cachebox` | 5.2.3 | **6.2.8** | transitive | deepdiff *(orphan)* | **MAJOR 5→6** | 0 | medium |
| 17 | `charset-normalizer` | 3.5.1 | 3.5.2 | transitive | requests *(direct)* | patch | 0 | low |
| 18 | `click` | 8.4.2 | 8.5.0 | transitive | black, huggingface_hub, litellm, uvicorn | minor | 0 | low |
| 19 | `contourpy` | 1.3.3 | 1.4.0 | transitive (orphan root) | *orphan root* (none) | minor | 0 | low |
| 20 | `coverage` | 7.16.1 | 7.16.2 | transitive | pytest-cov *(direct dev)* | patch | 0 | low |
| 21 | `filelock` | 3.32.7 | **4.1.1** | transitive | datasets, huggingface_hub, litellm, python-discovery, virtualenv | **MAJOR 3→4** | 0 | **BLOCKED** (§6) |
| 22 | `fonttools` | 4.63.0 | 4.66.1 | transitive (orphan root) | *orphan root* (none) | minor | 0 | low |
| 23 | `fsspec` | 2026.7.0 | 2026.9.0 | transitive | datasets, huggingface_hub | calendar minor | 0 | **BLOCKED** (§6) |
| 24 | `httptools` | 0.8.0 | 0.9.0 | transitive (orphan root) | *orphan root* (none; `uvicorn[standard]` extra only) | 0.x minor | 0 | low |
| 25 | `huggingface_hub` | 1.33.0 | **2.2.0** | transitive | datasets, litellm, tokenizers | **MAJOR 1→2** | 0 | **BLOCKED** (§6) |
| 26 | `identify` | 2.6.19 | 2.6.20 | transitive | pre_commit *(direct dev)* | patch | 0 | low |
| 27 | `idna` | 3.18 | 3.20 | transitive | anyio, httpx, httpx2, requests, yarl | minor | 0 | low |
| 28 | `importlib_metadata` | 8.9.0 | **9.0.1** | transitive | docstring-to-markdown, litellm | **MAJOR 8→9** | 0 | **BLOCKED** (§6) |
| 29 | `jedi` | 0.20.0 | 0.20.1 | transitive | python-lsp-server *(direct dev)* | patch | 0 | low |
| 30 | `jiter` | 0.16.0 | 0.17.0 | transitive | anthropic, openai | 0.x minor | 0 | low |
| 31 | `kiwisolver` | 1.5.0 | 1.5.1 | transitive (orphan root) | *orphan root* (none) | patch | 0 | low |
| 32 | `litellm` | 1.104.2 | 1.105.0 | transitive (orphan root) | *orphan root* (none) — **undeclared everywhere** | minor | 0 | **HIGH** — it is the blocker |
| 33 | `narwhals` | 2.24.0 | 2.27.1 | transitive | altair *(orphan chain)* | minor | 0 | low |
| 34 | `nodeenv` | 1.10.0 | 1.11.0 | transitive | pre_commit *(direct dev)* | minor | 0 | low |
| 35 | `openai` | 2.54.0 | **3.29.0** | transitive | litellm *(orphan)* | **MAJOR 2→3** | 0 | **BLOCKED** (§6) |
| 36 | `protobuf` | 7.35.1 | 7.36.2 | transitive (orphan root) | *orphan root* (none) | minor | 0 | low |
| 37 | `pydantic_core` | 2.46.4 | 2.50.1 | transitive | pydantic *(direct)* — **exact pin** | coupled | 0 | medium (§6) |
| 38 | `pyparsing` | 3.3.2 | 3.3.3 | transitive (orphan root) | *orphan root* (none) | patch | 0 | low |
| 39 | `ruff` | 0.15.22 | 0.17.0 | transitive (orphan root) | *orphan root* (none) | 0.x minor | 0 (tool) | medium — lint-gate rule churn |
| 40 | `starlette` | 1.3.1 | 1.7.0 | transitive | fastapi *(direct)* | minor | 0 | low-med |
| 41 | `tenacity` | 9.1.4 | 9.2.1 | transitive (orphan root) | *orphan root* (none) | minor | 0 | low |
| 42 | `truststore` | 0.10.4 | 0.10.5 | transitive | httpcore2, httpx2 | patch | 0 | low |
| 43 | `urllib3` | 2.7.0 | 2.8.0 | transitive | botocore, requests | minor | 0 | low |
| 44 | `virtualenv` | 21.14.6 | 21.14.7 | transitive | pre_commit *(direct dev)* | patch | 0 | low |

Every code-surface probe (`websockets`, `tqdm`, `litellm`, `openai`, `starlette`, `altair`,
`protobuf`, `tenacity`, `pyparsing`, `httptools`, `cachebox`, `huggingface_hub`,
`importlib_metadata`, `jedi`, `boto3`, `botocore`, `contourpy`, `fonttools`, `kiwisolver`) returned
**0 files**. Only `anthropic` (1), `pydantic` (1), `uvicorn` (1), `fastapi` (4), `requests` (2),
`numpy` (44), `pyboy` (10) are imported directly.

---

## 5. Major-version risks (explicit)

**Seven semver-major boundaries** are present in the scan:

| Package | Boundary | Why it is risky here |
|---|---|---|
| `anthropic` | **0.122.0 → 1.13.0** | First stable major; the client moved its HTTP stack (the venv already carries `httpx2` 2.13.1 / `httpcore2` 2.13.1 alongside `httpx` 0.28.1, and `anthropic 0.122.0` requires `httpx<1,>=0.25.0`). Imported by `src/` (1 file) and driven against a live LLM endpoint — needs a live call smoke, not just a unit run. |
| `websockets` | **16.1.1 → 17.2** | Major for a package the ASGI server stack sits on; no static import (reachable only through the dashboard's server side), so a green unit suite proves nothing. Needs a dashboard boot + WS handshake smoke. |
| `openai` | **2.54.0 → 3.29.0** | Pulled only by `litellm`, and **capped** by it (see §6). Not imported by project code. |
| `filelock` | **3.32.7 → 4.1.1** | Pulled by `datasets`/`huggingface_hub`/`litellm`/`virtualenv`; **capped by litellm `<4.0`**. |
| `huggingface_hub` | **1.33.0 → 2.2.0** | Pulled by `datasets`/`litellm`/`tokenizers`; **capped by litellm `<2.0`**. |
| `importlib_metadata` | **8.9.0 → 9.0.1** | Pulled by `docstring-to-markdown` and `litellm`; **capped by litellm `<9.0`**. |
| `cachebox` | **5.2.3 → 6.2.8** | Pulled by `deepdiff` only — both are orphans, so this disappears with a rebuild rather than being upgraded. |

**One additional major is present but self-blocked:** `pyboy 2.7.0 → 2.8.1` is refused by the
project's own pin `pyboy>=1.0.0,<2.8.0` in *both* `requirements.txt` and `pyproject.toml`. The pin
carries a detailed rationale comment (non-monotonic logging constants + save-state `STATE_VERSION`
29 with no migration → all 10 tracked `*.state` files, `data/boot.state`, the md5-pinned
`data/baselines/base-1_boot.state` and `play_states/pallet_outside_house_20260929.state` fail to
load). **Unblocking this is a state-migration task, not a pin bump.**

### 5.1 Elevated-risk non-majors

| Package | Move | Why flagged |
|---|---|---|
| `ruff` | 0.15.22 → 0.17.0 | 0.x lines are breaking-by-convention; a two-minor jump changes lint rules and can turn a green `ruff` gate red without any code change. |
| `starlette` | 1.3.1 → 1.7.0 | Four minors under `fastapi` (which only floors it at `>=0.46.0`, no cap) — sits under every dashboard route. |
| `uvicorn` | 0.52.3 → 0.54.0 | 0.x minor; also the item that currently violates its own declared floor. |
| `protobuf` | 7.35.1 → 7.36.2 | Minor, but protobuf minors can change generated-code assumptions; harmless here only because nothing imports it. |

---

## 6. Breaking pairs and hard caps (verified from installed metadata)

### 6.1 The pydantic ↔ pydantic_core exact pin (must move together)

```
pydantic 2.13.4  requires  pydantic-core==2.46.4      # EXACT pin, not a range
installed pydantic_core: 2.46.4
```

`pydantic_core 2.46.4 → 2.50.1` **cannot be done alone** — bumping `pydantic_core` in isolation
breaks the `pydantic==2.46.4` requirement. Conversely, upgrading `pydantic` to 2.14.1 pulls
`pydantic-core 2.50.1` with it. **Treat #6 and #37 as one atomic change.** Both `uv.lock` and the
installed set agree on the current pair (2.13.4 / 2.46.4).

### 6.2 litellm is capping four majors

`litellm 1.104.2` declares (verified via `importlib.metadata.requires`):

```
openai>=2.20.0,<3.0.0          -> blocks openai 3.29.0
filelock>=3.16.1,<4.0          -> blocks filelock 4.1.1
importlib-metadata>=8.0.0,<9.0 -> blocks importlib_metadata 9.0.1
huggingface-hub>=0.34.0,<2.0   -> blocks huggingface_hub 2.2.0
```

**All four blocked majors trace to a single undeclared package.** `litellm` has **0 hits** in
`uv.lock`, `pyproject.toml`, `requirements.txt`, `requirements-dev.txt`, and **0 imports** in the
repo's code. It is a leftover install, and it is the sole reason those four cannot move.

Note the asymmetry this creates between the two dependency surfaces: **`uv.lock` already resolves
`openai = "3.1.0"`** — because litellm is not part of the uv surface — while the pip-installed
`.venv` is held at 2.54.0 *by* litellm. The lock file and the installed environment disagree about
which openai is correct, and the disagreement is entirely an artifact of the orphan.

### 6.3 The datasets fsspec ceiling

`datasets 5.1.0` declares `fsspec[http]<=2026.7.0,>=2023.1.0` → **blocks `fsspec 2026.9.0`**
(currently 2026.7.0, i.e. exactly at the ceiling). `datasets` is also an orphan; the ceiling
disappears with it.

### 6.4 Pair constraints that are satisfied (no blocker)

| Pair | Constraint | Latest | Verdict |
|---|---|---|---|
| boto3 → botocore | `<1.44.0,>=1.43.111` | 1.43.112 | allowed |
| s3transfer → botocore | `<2.0a0,>=1.37.4` | 1.43.112 | allowed |
| requests → charset-normalizer / idna / urllib3 | `<4,>=2` / `<4,>=2.5` / `<3,>=1.26` | 3.5.2 / 3.20 / 2.8.0 | allowed |
| fastapi → starlette | `>=0.46.0` (no cap) | 1.7.0 | allowed |
| starlette → anyio | `<5,>=3.6.2` | 4.15.1 | allowed |
| mypy → ast-serialize | `<1.0.0,>=0.11.2` | 0.13.0 | allowed |
| pytest-cov → coverage | `>=7.10.6` | 7.16.2 | allowed |
| python-lsp-server → jedi | `<0.21.0,>=0.17.2` | 0.20.1 | allowed |
| huggingface-hub → click | `<9.0.0,>=8.4.2` | 8.5.0 | allowed |
| pre-commit → identify / nodeenv / virtualenv | `>=1.0.0` / `>=0.11.1` / `>=20.10.0` | 2.6.20 / 1.11.0 / 21.14.7 | allowed |

---

## 7. Delta vs the 2026-10-12 review (SUP-DEPS-20261012-AIP)

Yesterday's document stated the same total (44) and the same surface (`.venv`, py3.13). It
itemised **10** of the 44 (5 direct + 5 transitive majors). Direct comparison of every item it
named:

| Item named on 10-12 | 10-12 recorded | 10-13 scan | Moved further? |
|---|---|---|---|
| `black` | 26.10.0 → 26.10.1 | 26.10.0 → 26.10.1 | **no** |
| `pyboy` | 2.7.0 → 2.8.1 | 2.7.0 → 2.8.1 | **no** |
| `anthropic` | 0.122.0 → 1.13.0 | 0.122.0 → 1.13.0 | **no** |
| `websockets` | 16.1.1 → 17.2 | 16.1.1 → 17.2 | **no** |
| `pydantic` | 2.14.0 → 2.14.1 | **2.13.4** → 2.14.1 | **recorded current version differs — see note** |
| `cachebox` | 5 → 6 | 5.2.3 → 6.2.8 | installed unchanged |
| `filelock` | 3 → 4 | 3.32.7 → 4.1.1 | installed unchanged |
| `huggingface_hub` | 1 → 2 | 1.33.0 → 2.2.0 | installed unchanged |
| `importlib_metadata` | 8 → 9 | 8.9.0 → 9.0.1 | installed unchanged |
| `openai` | 2 → 3 | 2.54.0 → 3.29.0 | installed unchanged |

**Result: 9 of 10 stable; nothing moved further in the day between scans.**

> **Note on `pydantic`:** the 10-12 review's table records the installed version as `2.14.0`.
> Today's `.venv`, `uv.lock` **and** `pip show` all report **2.13.4**. `requirements.txt` declares
> the floor `pydantic>=2.13.5` — which 2.13.4 also violates. Either the 10-12 figure was a
> transcription error or the venv was re-pinned between scans; the **target (2.14.1) is unchanged**
> either way, and this review records the measured value. Flagged rather than silently reconciled.

**What the two prior reviews did not cover that this one does:** the 34 transitive entries, the
undeclared-orphan surface (§3.1), the litellm cap chain (§6.2), and the requirements-floor drift
(§8).

---

## 8. Requirements-floor drift — `.venv` is older than what the repo declares

Four direct dependencies are installed **below the floor declared in `requirements.txt`**:

| Package | `requirements.txt` floor | Installed in `.venv` | Status |
|---|---|---|---|
| `pydantic` | `>=2.13.5` | 2.13.4 | **violates** |
| `python-dotenv` | `>=1.2.4` | 1.2.2 | **violates** |
| `tqdm` | `>=4.70.1` | 4.70.0 | **violates** |
| `uvicorn` | `>=0.54.0` | 0.52.3 | **violates** |

`uv.lock` agrees with the venv, not the requirements file (`uvicorn = "0.52.3"`,
`python-dotenv = "1.2.2"`, `tqdm = "4.70.0"`, `pydantic = "2.13.4"`). So **three artifacts disagree
with each other**: the declared floor says one thing, the lock says another, the venv matches the
lock.

This also means these four are **not real "upgrades"** — they are the repo catching up to what it
already declares. `pip install -r requirements.txt` would move them without any decision being
taken. They are ranked first in the plan for that reason.

### 8.1 The py3.11 `venv/` (out of scope, confirmed drifted)

`venv/` (Python 3.11.15) reports **108 outdated** — identical to the figure in yesterday's review,
so it has not diverged further in a day. It carries unrelated fleet tooling (`awscrt`, `astroid`,
`gitreins`/`chimera-deliberation` editables, `argcomplete`, `attrs`, …). Yesterday's recommendation
stands and is re-affirmed: **stop auditing `venv/` wholesale** — it is a general-purpose
environment, not the project runtime. Either rebuild it from `requirements.txt` or delete it.
`venv/` is **not** the tested surface; `.venv/` is (`test_command: ./.venv/bin/pytest`).

---

## 9. Plan — safe to upgrade now

These are safe on evidence: the package is **not imported anywhere in the repo**, its move is a
**patch or a minor inside the same major**, and **no installed parent caps it** below the latest
version. A single full-suite run after the batch is sufficient (and required by the repo's own
gate).

**Tier A — do these; mechanical, zero code surface (19 items)**

| Package | From → To | Basis |
|---|---|---|
| `python-dotenv` | 1.2.2 → 1.2.4 | patch; **closes a declared-floor violation** |
| `tqdm` | 4.70.0 → 4.70.1 | patch; **closes a declared-floor violation** |
| `black` | 26.10.0 → 26.10.1 | patch, dev tool, 0 imports |
| `coverage` | 7.16.1 → 7.16.2 | patch, dev tool, 0 imports |
| `identify` | 2.6.19 → 2.6.20 | patch, dev tool, 0 imports |
| `virtualenv` | 21.14.6 → 21.14.7 | patch, dev tool, 0 imports |
| `jedi` | 0.20.0 → 0.20.1 | patch, dev tool, 0 imports |
| `kiwisolver` | 1.5.0 → 1.5.1 | patch, 0 imports |
| `pyparsing` | 3.3.2 → 3.3.3 | patch, 0 imports |
| `charset-normalizer` | 3.5.1 → 3.5.2 | patch, 0 imports, parent allows `<4` |
| `boto3` + `botocore` | 1.43.111 → 1.43.112 | patched **pair** — move together; boto3 caps botocore `<1.44.0` |
| `truststore` | 0.10.4 → 0.10.5 | patch, 0 imports |
| `protobuf` | 7.35.1 → 7.36.2 | minor, 0 imports |
| `tenacity` | 9.1.4 → 9.2.1 | minor, 0 imports |
| `idna` | 3.18 → 3.20 | minor, 0 imports, parents allow `<4` |
| `urllib3` | 2.7.0 → 2.8.0 | minor, 0 imports, botocore excludes only `==2.2.0` |
| `click` | 8.4.2 → 8.5.0 | minor, 0 imports, huggingface-hub caps `<9.0.0` |
| `anyio` | 4.14.2 → 4.15.1 | minor, 0 imports, starlette caps `<5` |
| `nodeenv` | 1.10.0 → 1.11.0 | minor, dev tool, 0 imports |

**Tier A2 — 0.x minors with no code surface (3 items)** — safe on the same evidence, flagged only
because 0.x lines are breaking-by-convention:

| Package | From → To | Basis |
|---|---|---|
| `ast_serialize` | 0.12.1 → 0.13.0 | mypy caps `<1.0.0`; 0 imports |
| `jiter` | 0.16.0 → 0.17.0 | openai/anthropic cap `<1`; 0 imports |
| `httptools` | 0.8.0 → 0.9.0 | reachable only via `uvicorn[standard]`; 0 imports |

**Tier A3 — only if the rebuild in §11 is *not* taken (4 items)** — orphan-chain minors, 0 imports:

`fonttools 4.63.0 → 4.66.1`, `contourpy 1.3.3 → 1.4.0`, `altair 6.2.2 → 6.3.0`,
`narwhals 2.24.0 → 2.27.1`. These are low-risk, but upgrading them is polishing the orphan
surface the rebuild would delete. **Prefer the rebuild.**

**Tier B — safe, but they touch the imported runtime surface: run the suite afterwards (4 items)**

| Package | From → To | Why it still belongs in "now" |
|---|---|---|
| `numpy` | 2.5.2 → 2.5.4 | patch **inside 2.5.x** — no ABI/API boundary; imported by 44 files, so the suite is the gate |
| `pydantic` **+** `pydantic_core` | 2.13.4 → 2.14.1 **and** 2.46.4 → 2.50.1 | one atomic change (§6.1); minor; **closes a declared-floor violation**; imported by 1 file |
| `uvicorn` | 0.52.3 → 0.54.0 | **closes a declared-floor violation**; imported by 1 file; needs the dashboard to boot |
| `starlette` | 1.3.1 → 1.7.0 | fastapi imposes no cap; no direct import; verify the dashboard routes still mount |

---

## 10. Plan — deferred (with the reason for each)

**Deferred — major boundary; each needs its own verify-then-upgrade row, not this review**

| Package | From → To | Reason to defer |
|---|---|---|
| `anthropic` | 0.122.0 → **1.13.0** | MAJOR 0→1 across the HTTP-client generation boundary. `src/` imports it and drives a **live LLM endpoint** — requires a live-call smoke against the real API, not just a unit suite. Carried unchanged from 10-11 and 10-12 with the same verdict; still deserves its own row. |
| `websockets` | 16.1.1 → **17.2** | MAJOR 16→17 under the ASGI server stack; **0 static imports**, so a green unit suite is not evidence. Needs a dashboard boot + WS handshake smoke. Unchanged across three reviews. |
| `pyboy` | 2.7.0 → **2.8.1** | **Self-blocked by the project pin** `pyboy>=1.0.0,<2.8.0` (requirements.txt *and* pyproject.toml). The block is substantive: non-monotonic logging constants plus save-state `STATE_VERSION` 29 with no migration path — 10 tracked `*.state` files, the md5-pinned `data/boot.state` and `base-1_boot.state`, and the live bridge's boot state all fail to load. **Needs a state-migration row (re-derive + re-pin with evidence), not a pin bump.** |
| `cachebox` | 5.2.3 → **6.2.8** | MAJOR 5→6, pulled only by `deepdiff` — both orphans. **Do not upgrade; delete with the rebuild** (§11). |
| `ruff` | 0.15.22 → 0.17.0 | 0.x two-minor jump; rule-set churn can red a lint gate with no code change. Needs a deliberate gate-recalibration row if the project wants it — and note `ruff` is itself an undeclared tool install. |

**Deferred — hard-blocked by an installed cap (5 items; no upgrade is possible without removing the blocker)**

| Package | Target | Blocking constraint |
|---|---|---|
| `openai` | 3.29.0 | `litellm` requires `openai>=2.20.0,<3.0.0` |
| `filelock` | 4.1.1 | `litellm` requires `filelock>=3.16.1,<4.0` |
| `huggingface_hub` | 2.2.0 | `litellm` requires `huggingface-hub>=0.34.0,<2.0` |
| `importlib_metadata` | 9.0.1 | `litellm` requires `importlib-metadata>=8.0.0,<9.0` |
| `fsspec` | 2026.9.0 | `datasets` requires `fsspec[http]<=2026.7.0` |

**Four of these five are blocked by `litellm` — an undeclared orphan.** None of them is imported by
project code. Removing `litellm` from the venv removes the block; they should then be re-evaluated
on their own merits (and two of them — `openai` 3.x, `huggingface_hub` 2.x — are still majors and
would need their own rows).

**Deferred — no action planned (1 item)**

| Package | Reason |
|---|---|
| `litellm` 1.104.2 → 1.105.0 | Its own upgrade is a minor, but the correct handling is removal, not upgrade (§11). Do not bump the very package that is capping four others. |

---

## 11. Recommendation — fix the surface, not 44 pins

**The evidence points at one structural action rather than a long upgrade campaign.**

1. **Rebuild `.venv` from the declared surface** (`pip install -r requirements.txt -r
   requirements-dev.txt`, or `uv sync` against `uv.lock`). The venv holds **155 distributions**
   against a declared surface of roughly two dozen. The rebuild removes the **31 undeclared top-level
   installs** and their subtrees.
2. **This reshapes the list rather than shrinking it by a fixed number.** Packages that are *only*
   reachable through an orphan stop being installed at all — `litellm` and its whole subtree
   (`boto3`, `botocore`, `openai`, `huggingface_hub`, `fsspec`, `importlib_metadata`, `jiter`,
   `protobuf`, `click`, `filelock`), plus `cachebox`, `deepdiff`, `datasets`, `ruff`, `altair`,
   `narwhals`, `contourpy`, `fonttools`, `kiwisolver`, `tenacity`, `pyparsing`, `httptools`,
   `truststore` (`httpx2`/`httpcore2`), `gitpython`, and the Flask/Mongo leftovers. **No reboot of
   individual pins is needed for items the project never depended on.**
3. **The rebuild must be done as its own task, not as part of this review** — it changes the
   runtime of a project mid-benchmark, and it must be followed by the full suite plus a real
   `cron_runner.py --dry-run`. Recorded here as a **recommendation**, filed as its own row.
4. **Then, and separately, execute the Tier A/B upgrades in §9** — starting with the four
   declared-floor violations (§8), which are corrections rather than decisions.
5. **`venv/` (py3.11, 108 outdated):** rebuild from requirements or delete. Do not audit it.
   Re-affirmed from 10-12.
6. **`uv.lock` vs installed drift** worth one row of its own: `uv.lock` currently resolves
   `openai 3.1.0` and `numpy 2.2.6` while `.venv` holds `2.54.0` and `2.5.2`. Whatever rebuild is
   chosen, decide **one** source of truth (requirements files *or* the lock) — today the three
   artifacts disagree (§8).

**Explicitly not done here:** nothing was installed, uninstalled, upgraded, or re-pinned; no lock
or requirements edit; no code change.

---

## 12. Security

**No advisory claim is made in this review.** The 2026-10-12 review asserted "0 known advisories on
direct deps"; that claim was **not re-verified here** because **no advisory scanner is installed in
`.venv`** (`pip list | grep -iE "audit|safety"` → nothing) and this task must not install one. This
is a gap, not a clean bill of health — the two reviews' security statements are not comparable.

Worth recording for whoever picks up the rebuild: the 10-12 review traced its earlier
`ecdsa` / `python-jose` findings to the **py3.11 `venv/` tooling drift**, and confirmed neither is
installed in the project venv. That conclusion is consistent with today's `venv/` still carrying
unrelated fleet tooling (§8.1).

---

## 13. No-change statement

This document is the only artifact of SUP-DEPS-20261013-AIP.

- `requirements.txt`, `requirements-dev.txt`, `pyproject.toml`, `uv.lock` — **unmodified**
- `.venv/`, `venv/` — **unmodified** (read-only inspection: `pip list`, `pip show`,
  `importlib.metadata`)
- No `pip install`, no `uv sync`, no `pip uninstall`
- No source, test, or configuration change

All numbers in this document come from the commands recorded in the Method table and were
reproduced independently of the supervisor script; its own listing is truncated at 24 rows (§2)
and was not relied on for the inventory.
