# Dashboard (src/dashboard/main.py)

PTP-01X Observability Dashboard — a FastAPI server for real-time monitoring and control of gameplay sessions: session status and metrics, screenshots, command history, and session control (start/pause/resume/stop).

> **Note:** the legacy Streamlit entry point `src/dashboard/run.py` no longer exists. The server lives entirely in `src/dashboard/main.py`.

## Running

From the repo root, with the project venv activated:

```bash
source .venv/bin/activate
python3 -m src.dashboard.main
```

Running the file directly (`python3 src/dashboard/main.py`) also works — the uvicorn start-up lives under `if __name__ == "__main__":`. The module imports `src.db.database` / `src.core.screenshot_manager`, so run it from the repo root (or with `src` importable), not from inside `src/dashboard/`.

|| Setting | Default | Purpose |
|---------|---------|---------|
| `PTP_DASHBOARD_PORT` | `8000` | Port uvicorn binds |
| `PTP_DASHBOARD_HOST` | `127.0.0.1` | Bind address (set `0.0.0.0` for LAN access) |
| `PTP_API_KEY` | unset | API key required by authenticated routes (see below) |
| `PTP_DASHBOARD_ROM` | `data/rom/Pokemon - Blue Version (USA, Europe) (SGB Enhanced).gb` | ROM a started session plays (see Play loop) |
| `PTP_DASHBOARD_BOOT_STATE` | `data/boot.state` | Checkpoint a started session boots from; `skip` forces the intro bypass |
| `PTP_DASHBOARD_START_TIMEOUT` | `20` | Seconds `POST /control/start` waits for the loop's first tick before refusing |
| `PTP_DASHBOARD_STALL_TIMEOUT` | `30` | Seconds a running session may go without a new tick before a status read reports it stalled (`running: false`, `current_state: "error"`, `last_error` naming the stall) — the mid-run wedge bound; pauses are exempt |

If the configured address is already occupied, startup fails with a non-zero exit and
reports the bind error (for example, `Errno 98` / `address already in use`). The
`Starting PTP-01X Dashboard` success banner is not printed in this case. Set
`PTP_DASHBOARD_PORT` to an available port to start the dashboard, for example:
`PTP_DASHBOARD_PORT=8001 python3 -m src.dashboard.main`.

Once running:

- UI: `http://127.0.0.1:8000/` — serves `src/dashboard/static/index.html` with the runtime API key injected as `window.ENV` (the shipped HTML file carries no key)
- Endpoint catalog: `http://127.0.0.1:8000/api/docs` (JSON)
- Interactive OpenAPI docs: `http://127.0.0.1:8000/docs` (Swagger UI) and `/redoc` (FastAPI built-ins)

## Authentication

Every route marked 🔑 requires the `X-API-Key` header matching `PTP_API_KEY`. Auth is **fail-closed**: when `PTP_API_KEY` is unset, every authenticated request is rejected with 401 — there is no default key. Unauthenticated: `/` (the UI shell), `/health`, `/screenshots/file`, and the two WebSocket streams.

A keyless server says so on the page. `/` is unauthenticated, so the UI still loads, but every data panel and control button behind it would 401 silently; to make that visible the served page carries a banner (`id="env-warning"`) naming the missing `PTP_API_KEY` and the restart command. The banner is injected only when the key is empty/blank — a configured server renders the page with no banner at all — and it does not change the auth model: authenticated routes still 401 until `PTP_API_KEY` is set on the server and the process is restarted.

CORS is wide open (`allow_origins=["*"]` with `allow_credentials=True`), and `/screenshots/file` serves any filesystem path passed as its `path` query — treat the dashboard as a local/single-operator tool, not a public service.

## REST routes (14)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | — | Dashboard UI; `static/index.html` with `PTP_API_KEY` injected into `window.ENV` |
| GET | `/status` | 🔑 | Session status: running/paused, tick count, average tick rate, current state, location, elapsed seconds, and `last_error` (the play loop's failure message, `null` when healthy); accepts `?session_id=<id>` (default: `default`) |
| GET | `/screenshots/latest` | 🔑 | Latest screenshot as JSON (`path`, `url`, `timestamp`) or, with `?format=base64`, a `data:image/png;base64` URI; accepts `?session_id=<id>` (default: `default`); 404 when none exist |
| GET | `/screenshots/file` | — | Raw screenshot file; required `path` query parameter; 404 when missing |
| GET | `/actions/recent` | 🔑 | Recent command history (`?limit=50` or `?session_id=<id>&limit=50`); accepts `?session_id=<id>` (default: `default`); last 1000 kept with `total_count` |
| GET | `/metrics` | 🔑 | Performance metrics: ticks/s, total ticks/commands, commands per minute, success rate, avg confidence, `total_cost_estimate` (always 0 in current code), elapsed; accepts `?session_id=<id>` (default: `default`) |
| POST | `/control/pause` | 🔑 | Pause a running session (400 if not running); accepts `?session_id=<id>` (default: `default`) |
| POST | `/control/resume` | 🔑 | Resume a paused session (400 if not running); accepts `?session_id=<id>` (default: `default`) |
| POST | `/control/stop` | 🔑 | Stop the session; accepts `?session_id=<id>` (default: `default`) |
| POST | `/control/start` | 🔑 | Start a session with its own play loop (`?session_id=default&save_dir=./game_saves`; replaces an existing session with the same id). Answers 200 with `tick_count >= 1` once the loop publishes its first tick, or 503 with the failure reason — never `started` for a session that cannot tick |
| POST | `/control/command` | 🔑 | Queue a command; JSON body `{"command": "...", "reasoning": "...", "confidence": 0.9}` (400 when not running or paused) |
| GET | `/sessions` | 🔑 | List all live sessions with their status |
| GET | `/health` | — | Liveness probe: `{"status": "healthy", "timestamp": ...}` |
| GET | `/api/docs` | — | Machine-readable catalog of the endpoints above |

## WebSocket streams (2)

|| Path | Cadence | Payload |
|------|---------|---------|
| `/ws/screenshots/{session_id}` | every 0.5 s | `{"type": "screenshot", "image": <base64 data URI>, "path", "timestamp", "tick", "state"}` when a newer frame exists, plus a `{"type": "status", "tick", "state", "paused", "tick_rate"}` message every interval |
| `/ws/metrics/{session_id}` | every 1.0 s | `{"type": "metrics", ...}` with the same fields as `GET /metrics` |

Both streams create the session on first connect if it does not exist yet.

## State model

Sessions are **in-memory** (`dashboard_sessions` dict). Read routes and WebSocket connections lazily create a `DashboardSession` with a `GameDatabase` (`<save_dir>/game_data.db`) and `ScreenshotManager` (`<save_dir>/screenshots`). A started session also owns a live play loop (see below), so `tick_count`, `location`, `last_action_time` and the screenshots all come from real emulator progress. Restarting the server clears in-memory session state, command history (capped at 1000 entries), and tick-rate windows, and stops any running play loop.

Read routes default to the `default` session; include `?session_id=<your_id>` to select another session.

## Play loop

`DashboardSession.start()` (`src/dashboard/main.py`) starts a **session-owned background thread** (`src/dashboard/play_loop.py`, `DashboardPlayLoop`); it no longer just flips flags. The loop:

1. boots PyBoy on the ROM (`PTP_DASHBOARD_ROM`, else `data/rom/<pokemon blue>.gb`) from the checkpoint (`PTP_DASHBOARD_BOOT_STATE`, else `data/boot.state`; `skip` forces the intro bypass),
2. ticks the emulator, reads the RAM-derived state and location, and executes queued `/control/command` input (`emulator.press_button` per queued command; with nothing queued, a deterministic down/left/up/right exploration cycle — no LLM is involved and a started session costs no API spend),
3. publishes every iteration through `DashboardSession.update_tick(state, location)` — the single writer of `tick_count` / `location` / `last_action_time`,
4. saves a PNG every 5 ticks through `ScreenshotManager`, which is what `/screenshots/latest` and `/ws/screenshots/{session_id}` serve.

Honesty contract: `POST /control/start` waits up to `PTP_DASHBOARD_START_TIMEOUT` seconds (default 20) for the first tick. A loop that cannot boot (missing ROM, PyBoy error, provider failure) or that never ticks stops the session and the route answers **503** with `{"status": "failed", "session_id": ..., "error": "<reason>"}`; `GET /status` then reports `running: false`, `tick_count: 0`, `current_state: "error"` and the same message in `last_error`. The console never reports `running: true` with endless zero ticks and no error. The same contract covers a **mid-run wedge**: a PyBoy hang inside `emulator.tick()` raises nothing, so a wedged loop just stops publishing. A running session that publishes no tick for `PTP_DASHBOARD_STALL_TIMEOUT` seconds (default 30; paused sessions are exempt) is flipped by the next status read to `running: false`, `current_state: "error"` and a `last_error` naming the stall — no restart required. `POST /control/pause` / `resume` gate the loop's tick execution, `POST /control/stop` joins the loop thread and closes the emulator.

`cron_runner.py` is a separate driver for long campaigns; it shares the components (`Emulator`, `GameAIManager`) but not these dashboard sessions.

## See Also

- [API Documentation Index](index.md)
- [Emulator](emulator_interface.md) — PyBoy control
- [Database](database.md) — `GameDatabase` persistence
