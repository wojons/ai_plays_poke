# Dogfood integration report — 2026-10-19 (dashboard + MCP surfaces, post-dependency-upgrade)

**Verdict: 🟡 PROMISING-BUT-ROUGH** — the gameplay path is healthy and *faster than ever* on
today's dependency bump (60 cycles in 27.9 s warm, 0.47 s/cycle vs 57.8 s on 2026-10-15), the two
2026-10-15 MCP fixes are re-proven live, and a fresh install on a clean bunker box still works
(26 s). What the run found instead is the layer *above* the fixes: the state projection lies about
the very menu the fixed tool now opens, and the dashboard's shipped UI cannot control any session
except `default` because its control calls put `session_id` in the body while the handlers read the
query string.

Run shape: HEAD `b730570` (the 2026-10-19 dependency upgrade `25516ea` is included), live bridge on
`127.0.0.1:8770`, scratch dashboard on `127.0.0.1:8947`, ephemeral bunker agent `df-aipp-1019` on
`bunker-mvp` (destroyed at the end of the run).

## 1. Headline use — autonomous gameplay (warm, 60 cycles)

```
.venv/bin/python cron_runner.py --run-id df1019a --cycles 60 --boot-state data/boot.state
real 27.92   # 0.47 s/cycle; first cycle 5.8 s (one 5203 ms LLM call), then 0.3 s/cycle
```

Run ladder (`cron_logs/run_df1019a.jsonl`): `decisions_total=60`, `jev_answered=58`,
`escalated=51`, `autonomy_ratio=0.9667`, **`jev_transport_failures=0`**, `teacher_escalations={1, improved:1}`,
`map_transitions_observed=1`, `distinct tiles=12`, `movement-progress=11/59 (19%)`,
`backtrack_rate=0.8136`, `nav-mem 2 hits / 0 fallbacks`.

Guard-event census in those 60 cycles: `noop_plan_guard` 45 · `memory_navigation_step_suppressed` 31 ·
`giveup_walk` 27 · `navigation_hold_guard` 11 · `memory_navigation_blocked` 7 · `recovery` 5 ·
`recovery_exhausted` 1.

**Read this as: JEV works in-game and costs nothing in failures, but the agent still re-walks the same
tiles** — a loud honesty ladder around a navigation loop that does not resolve. That is the pending
`ARM-1` owner decision, not a new defect; today's measurement is attached to `ARM-1` as an event
(id 591) rather than a new row.

## 2. MCP surface — both 2026-10-15 fixes re-proven, one new gap behind them

`tools/list` now advertises `game_press.frames` (`integer`, default 5, min 1, max 120) and the
handler forwards it (`scripts/aipp_mcp.py:115-123`, `:264-265`).

* **DF-AIPP-8 re-proof.** `scripts/play.py --frames 30 press START` really opens the START menu:
  `play_frames/df_before.png` vs `df_after_start.png` differ by **2885/23040 px (12.52 %)**, and `B`
  restores a **byte-identical** frame (`0/23040`, 0.00 %) — the change is the menu, not a sprite.
* **DF-AIPP-9 re-proof.** Omitting or renaming a required key now fails loudly:
  `error: missing required argument(s) for game_save: slot — required key(s) per the tool schema`
  (same for `game_load`, `game_delete_save`); no stray slot is written (`list_saves` still 7).
* **New DF-AIPP-10.** With the menu open, every observation still reports `SCREEN: overworld` —
  `RAMReader.screen_type()` (`src/core/ram_reader.py:1157-1185`) branches battle → name_entry →
  YES/NO box → dialog → unknown/title → overworld, and `_has_yes_no_menu()` (`:1202-1206`) only
  matches a two-item prompt (`wMaxMenuItem == 1`). A list menu falls through to overworld, so the
  projection handed to the decision model says "walkable" while the menu owns the input; presses
  return `state_changed: False` and the treadmill guards fire against a map that is not blocking.

The docs describe the tool surface honestly elsewhere (bridge protocol, security model, error
boundary), and `docs/api/mcp.md`'s table already documents the *pre-fix* default-slot behavior it
should now update — flagged inside DF-AIPP-12's surface rather than as its own row.

## 3. Dashboard surface (first real-use pass in the dogfood log)

Started as documented: `PTP_DASHBOARD_HOST=127.0.0.1 PTP_DASHBOARD_PORT=<scratch> PTP_API_KEY=<scratch> python3 -m src.dashboard.main`.

Works: `/health`, `/` (UI shell with `window.ENV` injected), `/api/docs` catalog, both WebSocket
streams (`/ws/metrics/{id}` at 1.0 s, `/ws/screenshots/{id}` at 0.5 s, 4–5 messages per 4 s each),
auth fail-closed (`/status` with no key or a wrong key → 401), `422` when `/screenshots/file` is
called without `path`, `404` for a missing file, and the whole command workflow
(`start → command → actions/recent → pause → resume → stop`).

**DF-AIPP-11 (P2):** the UI's control calls carry `session_id` in the POST **body**
(`static/index.html:619-670`) while the handlers declare it as a **query** scalar
(`main.py:325-373`). Every control therefore lands on `default`:
`POST /control/pause` with body `{"session_id":"df-dash"}` → `200 {"status":"paused","session_id":"default"}`
while `GET /status?session_id=df-dash` still reports `running:true, paused:false`.
`POST /control/start` with body `{"session_id":"dfui"}` → `{"status":"started","session_id":"default"}`,
and `dfui` is never created. The query form works (`POST /control/pause?session_id=df-dash`), so the
transport difference *is* the defect. A user cannot stop the session they started.

**DF-AIPP-12 (P3):** `docs/api/dashboard.md` names `session_id` only on `/control/start`; the other
seven routes that accept it (status, metrics, actions/recent, screenshots/latest, pause, resume,
stop) are documented without the parameter, so the documented start-then-read sequence reports the
idle `default` session and the next control call returns `400 {"error":"Session not running"}`.
This run hit exactly that as a user before reading the source; the tester-assumption half was
withdrawn, the docs half is filed.

Environment note (not a product defect): the documented default port 8000 on this host is held by an
unrelated `dexdat-api` container via `docker-proxy`, so the run used `PTP_DASHBOARD_PORT`. Always
attribute a port to *your* process (`ss -ltnp`) before trusting a probe — an unrelated service
answering on a "chosen" port reads like a product failure.

## 4. Install leg (fresh machine, ephemeral bunker)

`bunker spawn df-aipp-1019 --server bunker-mvp --ttl 1h`, then the documented path verbatim on a
clean box (Ubuntu 6.8, Python 3.12.3, no apt prereqs), script staged with `ssh 'cat > file'`:

| step | result |
|---|---|
| `git clone --depth 1 https://github.com/wojons/ai_plays_poke.git` | rc=0, **1 s**, commit `b730570` (no credential needed; public origin) |
| `python3 -m venv .venv` | rc=0, **4 s** |
| `.venv/bin/pip install -r requirements.txt` | rc=0, **20 s** (resolved Pillow 13.0.0, anthropic 1.15.0, fastapi 0.150.0, pyboy 2.7.0, websockets 17.3) |
| `.venv/bin/python cron_runner.py --dry-run` (documented smoke) | **rc=1, honest** — `ROM not found at data/rom/...` with the fix spelled out |
| documented MCP discovery probe (`initialize` + `tools/list`) | rc=0, protocol `2024-11-05`, `aipp-game 1.0.0` |

`install_seconds=26` total. Zero system dependencies. Agent destroyed afterwards
(`bunker destroy --server bunker-mvp df-aipp-1019`; home archived, SSH key removed).

Fresh-install resolution drift worth knowing: because `requirements.txt` carries lower bounds
(`pyboy>=1.0.0,<2.8.0`, `fastapi>=0.142.2`, …), a clean box today resolves versions newer than the
repo's own venv (fastapi 0.150.0 vs 0.146.0). The README block calls them "exact pins" while quoting
`>=` ranges — a wording nit noted in the run log, deliberately not filed as a row.

## 5. Performance (measured, no PERF row filed)

| operation | cold | warm |
|---|---|---|
| `cron_runner.py --dry-run` (new user's first command) | **1.10 s** (rc=0) | — |
| `cron_runner.py --cycles 60` (headline use) | first cycle **5.8 s** (5.2 s LLM) | **27.9 s total, 0.47 s/cycle** |
| MCP tool calls via stdio | `initialize`+`tools/list` ≈ 0.04 s | observe 0.004–0.005 s, press 0.011–0.015 s, save/delete 0.001–0.003 s, `game_reset` ≈ 0.84 s |
| dashboard REST routes | — | 0.0006–0.045 s (slowest: `POST /control/start` 1.18 s) |
| WebSocket cadence | — | metrics 1.0 s, screenshots/status 0.5 s (as documented) |
| fresh install on a clean box | **26 s** | — |

Nothing here is slow enough that a user would notice, so no PERF row was filed — that is the honest
result, not an omission. The one number that changed materially (0.47 s/cycle vs 0.96 s/cycle on
2026-10-15) is a regression check on the 2026-10-19 dependency upgrade passing, not a tuning target.

## 6. Reproduce the findings in ten minutes

```bash
# DF-AIPP-10 — the menu opens but the projection says overworld
.venv/bin/python scripts/play.py --frames 30 press START
.venv/bin/python scripts/play.py observe            # SCREEN: overworld (menu is drawn)
.venv/bin/python scripts/play.py frame before && .venv/bin/python scripts/play.py frame after_start
# compare the two PNGs: ~12.5 % of pixels differ, and a 30-frame B restores the first frame exactly

# DF-AIPP-11 — control calls that carry session_id in the body hit 'default'
curl -X POST -H "X-API-Key: $PTP_API_KEY" -H 'Content-Type: application/json' \
     -d '{"session_id":"probe"}' "http://127.0.0.1:$PTP_DASHBOARD_PORT/control/start"   # -> session_id: default
curl -H "X-API-Key: $PTP_API_KEY" "http://127.0.0.1:$PTP_DASHBOARD_PORT/sessions"
```

## 7. Lesson for the next agent in this repo

* The bridge is the source of truth for *input*; the projection is the source of truth for *what the
  model believes*. When the two disagree (menu open, projection says overworld) the model is wrong,
  and the fixed tool that made the disagreement reachable is not the culprit — the reader is.
* Every dashboard route takes `session_id` as a query parameter and defaults to `default`; pass it
  explicitly or you are reading and controlling a different session than the one you started.
* `cron_runner.py --dry-run` is a 1-second, zero-API-call preflight — run it before any live run and
  read the exit code directly, never through a pipe.
