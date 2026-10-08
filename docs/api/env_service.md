# Environment Service API (CH-SPLIT increment 1)

Status: Active (increment 1)
Date: 2026-10-07
Module: `src/env_service.py`
Example client: `examples/simple_agent_client.py`
Related: [emulator_interface.md](emulator_interface.md), [cron_runner.md](cron_runner.md)

The environment service exposes the PyBoy emulator and RAM reader as a local
HTTP service so an agent can drive the game purely through an observe/act
contract — no `cron_runner.py` import, no in-process emulator access. All
state lives in the service process (one emulator instance per service).
`cron_runner.py` and `src/core/*` behavior are untouched: the service
reuses `src.core.emulator.Emulator` and `src.core.ram_reader.RAMReader`
as-is.

## Running

From the repo root with the project venv activated:

```bash
source .venv/bin/activate   # or: source venv/bin/activate
uvicorn src.env_service:app --port 8765
```

The service is single-user and local by design (no auth); bind it to
`127.0.0.1` only.

## Contract

Base URL: `http://127.0.0.1:<port>`. All bodies are JSON.

### `GET /env/health`

Liveness + boot state. Always 200.

```json
{
  "status": "ok",            // "ok" when booted, "idle" before boot
  "booted": true,
  "rom_path": "data/rom/Pokemon - Blue Version (USA, Europe) (SGB Enhanced).gb",
  "boot_state": "data/boot.state"
}
```

### `POST /env/boot`

Boot a fresh emulator instance, optionally loading a `.state` checkpoint.

Request:

```json
{
  "rom_path": "data/rom/Pokemon - Blue Version (USA, Europe) (SGB Enhanced).gb",
  "boot_state": "data/boot.state"
}
```

Both fields optional (defaults are the Blue SGB ROM and `data/boot.state`;
pass `"boot_state": null` to boot from the title screen). Response is the
same shape as `/env/health` with `"status": "booted"`.

Errors:

| Code | When |
|------|------|
| 409  | Environment already booted. `POST /env/reset` to reload, or stop the service to reboot from scratch. |
| 400  | ROM or boot-state file not found (detail carries the path). |

### `GET /env/observe`

Current RAM-derived game state plus the last screenshot.

```json
{
  "location": "Pallet Town",
  "map_id": 40,
  "player_x": 37,
  "player_y": 5,
  "player_tile_x": 9,
  "player_tile_y": 7,
  "player_facing": "down",
  "screen_type": "overworld",
  "party_count": 1,
  "is_moving": false,
  "screenshot_base64": "iVBORw0KGgo...",
  "screenshot_format": "png",
  "emulated_platform": "gb"
}
```

- `screenshot_base64` is a base64-encoded PNG of the 144x160 RGB frame.
- Any RAM read that fails (e.g. mid-transition memory layout) comes back as
  `null` for that field instead of failing the request; the screenshot is
  always populated when booted.
- `location` is the map name resolved from the ROM map DB (may be `null`
  for maps missing from the DB).

Errors:

| Code | When |
|------|------|
| 409  | Environment not booted. |

### `POST /env/act`

Press buttons (sequentially, each held for `frames` emulator frames), then
return the new observation.

Request:

```json
{ "buttons": ["up", "a"], "frames": 8 }
```

- `buttons` defaults to `[]`; an empty list just advances `frames` (wait).
- `frames` defaults to 8, clamped to 1..600.
- Buttons are the Gen-1 joypad names accepted by
  `Emulator.press_button`: `up`, `down`, `left`, `right`, `a`, `b`,
  `start`, `select`.
- Per-request button cap: 16.

Response:

```json
{
  "pressed": ["up", "a"],
  "frames": 8,
  "observation": { ...same shape as /env/observe... }
}
```

Errors:

| Code | When |
|------|------|
| 409  | Environment not booted. |
| 422  | `frames` outside 1..600, more than 16 buttons, or malformed body. |

### `POST /env/reset`

Reload the boot checkpoint into the live emulator (restores the exact
boot-time position; no re-construction of the emulator instance).

Response: same shape as `/env/health` with `"status": "reset"`.

Errors:

| Code | When |
|------|------|
| 409  | Environment not booted. |
| 400  | Boot-state file missing (only possible if it was deleted after boot). |

## Error body shape

All non-2xx responses use FastAPI's default error envelope:

```json
{ "detail": "Environment already booted. POST /env/reset first." }
```

## Concurrency

All endpoints serialize on a single in-process lock — an `/env/act` blocks
`/env/observe` until the button sequence finishes. Clients should treat the
service as single-agent.

## Example

`examples/simple_agent_client.py` boots (if needed), then performs a
scripted 20-step walk (`up/left/down/right` x 5), printing the RAM-derived
location and tile per step — proving a non-`cron_runner` client can drive
the environment end-to-end:

```bash
uvicorn src.env_service:app --port 8765 &
python examples/simple_agent_client.py --base-url http://127.0.0.1:8765
```
