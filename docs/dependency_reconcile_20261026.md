# Dependency Reconciliation — 2026-10-26 (DEPS-005)

Follows the 2026-10-25 review (`docs/dependency_review_20261025.md`,
SUP-DEPS-20261022-AIP, c711d41) — which **updated the manifests and rebuilt a
venv in a throwaway worktree, but never reinstalled the main clone**. This row
is the consequence: the manifests demand floors the main clone's venv does not
satisfy, and nothing in the repo could see it.

**Surface:** `/home/kara/ai_plays_poke/venv` (CPython 3.11.15, 264 dists) — the
repo's only complete env and the interpreter CI uses (`.github/workflows/ci.yml`,
python 3.11). `./.venv` (CPython 3.13, 37 dists) is **held**, not reconciled:
see the held section below.

**Row premise vs reality.** The dispatch said "fastapi is installed at 0.139.2
while requirements.txt demands >=0.162.0". Measured pre-state was
**fastapi 0.143.0** — still below the floor, so the finding stands, but the
number in the row was stale. The scan (`pip list --outdated`) reported **128**
entries, which matches.

## What was actually drifted (production deps only)

`scripts/check-installed-deps.py` (added by this row) compares the *installed*
set against the declared floors. That is a different question from
`pip list --outdated`: an outdated scan lists 119 transitive packages that no
manifest pins and that are therefore irrelevant here, while a direct dependency
installed below its floor is drift that `--outdated` never labels as drift.

| Package | Installed | Required | Verdict |
|---|---|---|---|
| anthropic | 1.13.0 | `>=2.3.0` | drift — manifest bumped 10-25, clone never reinstalled |
| fastapi | 0.143.0 | `>=0.162.0` | drift — same cause |
| pydantic | 2.14.0 | `>=2.14.1` | drift — patch floor bumped 10-25 |
| pre-commit (dev) | 4.6.0 | `>=4.7.0` | drift — dev manifest floor, `requirements-dev.txt` |

Everything else in `requirements.txt` already satisfied its floor
(`pyboy 2.7.0`, `requests 2.34.2`, `numpy 2.4.6`, `Pillow 12.3.0`,
`python-dotenv 1.2.4`, `tqdm 4.70.1`, `PyYAML 6.0.3`,
`opencv-python-headless 5.0.0.93`, `uvicorn 0.54.0`, `websockets 17.2`,
`psutil 7.2.2`).

## Applied

```
./venv/bin/pip install -r requirements.txt        # 4 packages, 2 uninstalls
./venv/bin/pip install -r requirements-dev.txt    # pre-commit 4.6.0 -> 4.7.0
```

Resolved: `anthropic 1.13.0 → 2.3.0` (pulls `httpx2 2.13.1`, `httpcore2 2.13.1`
— the 2.x SDK moved its HTTP layer), `fastapi 0.143.0 → 0.162.0`,
`pydantic 2.14.0 → 2.14.1`, `pydantic_core 2.50.0 → 2.50.1`,
`pre-commit 4.6.0 → 4.7.0`. `pip freeze` diff before/after is exactly those
lines — no collateral churn.

Deliberately **not** bumped: `starlette 1.3.1` (fastapi 0.162.0 declares
`starlette>=0.46.0`; the installed one satisfies it) and `numpy 2.4.6`
(`>=1.26.4`). Reconciliation means "satisfies what we declared", not "is the
newest release": chasing latest is what `pip list --outdated` invites and what
this repo's earlier reviews spent rows refusing.

`pyboy` stayed at 2.7.0 while 2.8.1 is available — the `<2.8.0` pin in
`requirements.txt:18` held through the resolve (save-state STATE_VERSION 29
break; unchanged from the 10-19/10-25 reviews).

## Evidence

| Gate | Command | Result |
|---|---|---|
| prod floors | `./venv/bin/python scripts/check-installed-deps.py requirements.txt` | **14/14 OK, RC=0** |
| dev floors | `./venv/bin/python scripts/check-installed-deps.py requirements-dev.txt` | **14/14 OK, RC=0** |
| suite (pre-change baseline) | `./venv/bin/pytest -x --tb=short -q` | **4526 passed, 14 skipped** in 264.91s |
| suite (post-change) | `./venv/bin/pytest -x --tb=short -q` | **4526 passed, 14 skipped** in 257.09s — same count, RC=0 |
| typing | `./venv/bin/mypy src/ --ignore-missing-imports` (mypy 2.4.0) | Success: no issues in 69 source files |
| lint | `./venv/bin/ruff check .` (ruff 0.15.22) | All checks passed |
| outdated scan | `./venv/bin/pip list --outdated` | 128 → **124** (the four upgraded left the list) |

### anthropic 2.x against the real SDK (the row's load-bearing criterion)

`TestClaudeClientRealSDKCallShape` (tests/test_ai_client.py:1813) drives the
**installed** SDK against a loopback HTTP server and passes on 2.3.0. It is not
a vacuous import check, and that was proven rather than asserted — a standalone
witness (`/tmp` scratch, reproduced here) shows all three legs:

```
1. identity : anthropic dist=2.3.0  module=2.3.0
2. premise  : Messages.create params include temperature? False  (extra_body? True)
   RED arm   : temperature= without extra_body -> TypeError: Messages.create()
               got an unexpected keyword argument 'temperature'
3. wire     : POST /v1/messages body_keys=['max_tokens', 'messages', 'model', 'temperature']
   temperature_on_wire=0.25 max_tokens=32 reply='witness reply'
```

So on 2.3.0 the `extra_body={"temperature": ...}` forward in
`src/core/ai_client.py:483` is still **load-bearing** (removing it is a
`TypeError`, which is exactly what the regression test catches), and the
forwarded shape survives to the wire. No live egress was possible:
`.env` holds `OPENROUTER_API_KEY` / `DEEPSEEK_API_KEY` only, no
`ANTHROPIC_API_KEY` — same evidence bar the 10-19 and 10-25 reviews recorded.

## The 128 "outdated" packages, classified

`pip list --outdated` answers "behind latest", not "violates our declarations":

| Class | Count | Handling |
|---|---|---|
| direct prod, **below** floor | 0 (was 3) | fixed above |
| direct prod, floor already met | 3 | left: `pillow 12.3.0→13.0.0`, `websockets 17.2→17.3`, `pyboy 2.7.0→2.8.1` (blocked by the pin) |
| direct dev, below floor | 1 (was 1) | fixed above |
| direct dev, floor already met | 1 | left: `black 26.10.0→26.10.1` |
| transitive, unpinned by any manifest | 119 | left by design |

The 119 are resolved by whichever version satisfies the declaring parent's
range; bumping them individually is churn with no declared contract behind it
(the 10-14 review already burned a table on exactly this class).

## Gate repair (found while proving the gates)

The row's own acceptance gate — "full pytest suite passes" — turned out not to
be able to run in this clone:

- `.gitreins/config.yaml` `test_command` was `./.venv/bin/pytest`, and
  `.venv/bin/pytest` **does not exist** (`.venv` is a 37-dist runtime-only venv).
- `.gitreins/logs/` has 20 guard runs; **3** recorded
  `[SKIP] tests (full)  passed=true  exit_code=127  skip_reason=test runner
  './.venv/bin/pytest' not found` — and the commits landed anyway.
- `scripts/hooks/pre-commit` (GUARD-1) is supposed to reject exactly that, but
  its matcher was `grep -E '^  ~ '` against a log format gitreins no longer
  emits: it matched **0 of 20** logs, so the non-benign-skip check had never
  fired. The 11 logs that do show `[PASS] tests (full) exit_code=0` are from
  before `.venv` lost its dev tooling.

Fixes: `test_command` repointed to `./venv/bin/pytest -x --tb=short` (the env
that has pytest and matches CI's 3.11), and the wrapper now rejects any `[SKIP]`
line carrying a numeric `exit_code` (a check that tried to run and could not
execute) while leaving the benign `exit_code=n/a` family ("no staged files",
"no LSP tool on PATH") allowed. The wrapper's console-only `  ~ …` skip lines are
deliberately not matched: they carry no exit code, so matching them rejects
benign skips — a first revision of this fix did exactly that and rejected a good
commit on the permanent `no LSP tool on PATH` line.

Verified live on the commit carrying this document: the guard's tests cell ran
`./venv/bin/pytest` under `/home/kara/ai_plays_poke/venv/bin/python3`
(pytest 9.1.1), collected **4540 items** and returned `exit_code=0` — the first
guard run in this clone where the tests cell actually executed the suite instead
of skipping.

## Held (deliberate, with reasons)

- **`.venv/` (CPython 3.13) is not reconciled.** 4 production floors unmet —
  `pydantic 2.13.4` (`>=2.14.1`), `uvicorn 0.52.3` (`>=0.54.0`),
  `tqdm 4.70.0` (`>=4.70.1`), `python-dotenv 1.2.2` (`>=1.2.4`) — and it has no
  pytest/mypy/ruff at all. It is the interpreter of **live** workloads
  (`scripts/game_bridge.py` up 6d, two `scripts/aipp_mcp.py`, the console), so
  swapping packages under them is a maintenance-window operation, not something
  a dependency row does unilaterally. Reproduce its state with
  `./.venv/bin/python scripts/check-installed-deps.py requirements.txt` (RC=1,
  the four FAILs above). Needs its own row: either rebuild `.venv` from the
  manifests in a window and restart the daemons, or retire `.venv` entirely and
  move the daemons to `venv/`.
- **`pylsp` still skipped** (`[SKIP] lsp … no LSP tool on PATH`): the hook
  prepends `.venv/bin` to `PATH`, and `.venv` has no pylsp. Enabling the LSP
  cell is a gate-surface change with unverified findings — left as its own row
  rather than switched on inside a dependency commit.
- **No live LLM call** (no `ANTHROPIC_API_KEY`): the anthropic verdict rests on
  the real-SDK loopback witness above plus the 2.x changelog diff recorded in
  the 10-25 review.
- **No live dashboard/WebSocket smoke**: unchanged from 10-19; still open.

## Reproducing this row

```
./venv/bin/python scripts/check-installed-deps.py requirements.txt requirements-dev.txt
./venv/bin/pip list --outdated | wc -l
./venv/bin/pytest -x --tb=short -q
./venv/bin/mypy src/ --ignore-missing-imports
./venv/bin/ruff check .
```

API-version note (anthropic 2.x): the SDK default API version date moved to
2026-10-21; nothing in this repo pins or asserts it, and the loopback witness
above confirms the request shape is unchanged.
