# Dashboard (src/dashboard/main.py)

PTP-01X Observability Dashboard — a FastAPI server for real-time monitoring and control of gameplay sessions: session status and metrics, screenshots, command history, and session control (start/pause/resume/stop).

> **Note:** `src/dashboard/run.py` (mentioned in AGENTS.md) does not exist. The server lives entirely in `src/dashboard/main.py`.

## Running

From the repo root, with the project venv activated:

```bash
source .venv/bin/activate
python3 -m src.dashboard.main
```

Running the file directly (`python3 src/dashboard/main.py`) also works — the uvicorn start-up lives under `if __name__ == "__main__":`. The module imports `src.db.database` / `src.core.screenshot_manager`, so run it from the repo root (or with `src` importable), not from inside `src/dashboard/`.

| Setting | Default | Purpose |
|---------|---------|---------|
| `PTP_DASHBOARD_PORT` | `8000` | Port uvicorn binds |
| `PTP_DASHBOARD_HOST` | `127.0.0.1` | Bind address (set `0.0.0.0` for LAN access) |
| `PTP_API_KEY` | unset | API key required by authenticated routes (see below) |

Once running:

- UI: `http://127.0.0.1:8000/` — serves `src/dashboard/static/index.html` with the runtime API key injected as `window.ENV` (the shipped HTML file carries no key)
- Endpoint catalog: `http://127.0.0.1:8000/api/docs` (JSON)
- Interactive OpenAPI docs: `http://127.0.0.1:8000/docs` (Swagger UI) and `/redoc` (FastAPI built-ins)

## Authentication

Every route marked 🔑 requires the `X-API-Key` header matching `PTP_API_KEY`. Auth is **fail-closed**: when `PTP_API_KEY` is unset, every authenticated request is rejected with 401 — there is no default key. Unauthenticated: `/` (the UI shell), `/health`, `/screenshots/file`, and the two WebSocket streams.

CORS is wide open (`allow_origins=["*"]` with `allow_credentials=True`), and `/screenshots/file` serves any filesystem path passed as its `path` query — treat the dashboard as a local/single-operator tool, not a public service.

## REST routes (14)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | — | Dashboard UI; `static/index.html` with `PTP_API_KEY` injected into `window.ENV` |
| GET | `/status` | 🔑 | Session status: running/paused, tick count, average tick rate, current state, location, elapsed seconds |
| GET | `/screenshots/latest` | 🔑 | Latest screenshot as JSON (`path`, `url`, `timestamp`) or, with `?format=base64`, a `data:image/png;base64` URI; 404 when none exist |
| GET | `/screenshots/file` | — | Raw screenshot file; required `path` query parameter; 404 when missing |
| GET | `/actions/recent` | 🔑 | Recent command history (`?limit=50`, last 1000 kept) with `total_count` |
| GET | `/metrics` | 🔑 | Performance metrics: ticks/s, total ticks/commands, commands per minute, success rate, avg confidence, `total_cost_estimate` (always 0 in current code), elapsed |
| POST | `/control/pause` | 🔑 | Pause a running session (400 if not running) |
| POST | `/control/resume` | 🔑 | Resume a paused session (400 if not running) |
| POST | `/control/stop` | 🔑 | Stop the session |
| POST | `/control/start` | 🔑 | Start a fresh session (`?session_id=default&save_dir=./game_saves`); stops and replaces an existing session with the same id |
| POST | `/control/command` | 🔑 | Queue a command; JSON body `{"command": "...", "reasoning": "...", "confidence": 0.9}` (400 when not running or paused) |
| GET | `/sessions` | 🔑 | List all live sessions with their status |
| GET | `/health` | — | Liveness probe: `{"status": "healthy", "timestamp": ...}` |
| GET | `/api/docs` | — | Machine-readable catalog of the endpoints above |

## WebSocket streams (2)

| Path | Cadence | Payload |
|------|---------|---------|
| `/ws/screenshots/{session_id}` | every 0.5 s | `{"type": "screenshot", "image": <base64 data URI>, "path", "timestamp", "tick", "state"}` when a newer frame exists, plus a `{"type": "status", "tick", "state", "paused", "tick_rate"}` message every interval |
| `/ws/metrics/{session_id}` | every 1.0 s | `{"type": "metrics", ...}` with the same fields as `GET /metrics` |

Both streams create the session on first connect if it does not exist yet.

## State model

Sessions are **in-memory** (`dashboard_sessions` dict): `POST /control/start` creates a `DashboardSession` that owns a `GameDatabase` (`<save_dir>/game_data.db`) and a `ScreenshotManager` (`<save_dir>/screenshots`). Restarting the server clears all sessions, command history (capped at 1000 entries), and tick-rate windows.

## See Also

- [API Documentation Index](index.md)
- [Emulator](emulator_interface.md) — PyBoy control
- [Database](database.md) — `GameDatabase` persistence
