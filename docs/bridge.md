# Live-Play Game Bridge (`scripts/game_bridge.py`)

The bridge lets a human or agent play the live game cycle by cycle and inspect
exactly what the decision model sees. It boots one emulator, keeps it alive, and
serves the bounded text projection built from a live RAM snapshot — the same
`RAMReader.observe()` → `state_projection.build()` output the game loop feeds the
model, not a paraphrase. Client tool: `scripts/play.py`.

## Security model

- Off by default: nothing autostarts the bridge.
- Binds `127.0.0.1` only (loopback, never `0.0.0.0`).
- Refuses to boot without a token file.
- Refuses a token file that is group/world-readable (requires mode `0600`).
- Refuses tokens shorter than 24 characters.
- Every request must carry the token, compared with `secrets.compare_digest`.

A session with no token simply cannot talk to it. Enable per session; revoke by
killing the process and deleting the token.

## What it serves

Newline-terminated JSON requests over a TCP socket (default port `8770`,
loopback). Every request carries a `"token"` field and a `"cmd"` field:

| `cmd` | Arguments | Effect |
|---|---|---|
| `health` | — | Bridge/ROM/boot status, pause state, goal |
| `observe` | — | Full observation + state projection (what the decision model receives) |
| `press` | `buttons` (list), `frames` (default 5), `settle` (default true) | Press buttons for N frames and settle |
| `step` | `n` (default 30) | Advance N frames without pressing (rejected while paused) |
| `save` | `slot` (default `slot1`) | Save emulator state to a slot |
| `load` | `slot` (default `slot1`) | Load emulator state from a slot |
| `frame` | `label` (default `now`) | Capture a PNG frame |
| `raw` | — | Raw RAM reader observation (no projection) |
| `pause` / `resume` | — | Pause/resume emulation |
| `list_saves` | — | List saved slots |
| `delete_save` | `slot` | Delete a saved slot |
| `reset` | — | Reset the emulator |
| `goal` | `text` | Set/read the current session goal |

Unknown commands return `{"ok": false, "error": "unknown cmd ..."}`.

### Server flags

```
python3 scripts/game_bridge.py --token-file TOKEN_FILE [--port N]
                               [--max-workers N] [--request-timeout SECONDS]
                               [--boot-state PATH] [--log PATH]
```

- `--token-file` (required): file holding the per-session token; must exist and be `0600`
- `--port`: TCP port (default `8770`)
- `--max-workers`: fixed worker-thread ceiling (default 4; pending queue has the same bound)
- `--request-timeout`: seconds allowed to receive one newline-terminated request (default 30)
- `--boot-state`: `.state` checkpoint to boot from
- `--log`: log path override

### Client (`scripts/play.py`)

```
python3 scripts/play.py [--frames N] CMD [args ...]
```

Commands: `observe, press, step, frame, save, load, goal, health, pause,
resume, list_saves, delete_save, reset`. The token is read from
`$AIPP_BRIDGE_TOKEN_FILE` (default `~/.hermes/aipp_bridge/session.token`); the
port from `$AIPP_BRIDGE_PORT` (default `8770`). `--frames` controls how long a
button is held (5 = one deliberate tap; the title screen needs ~30).

## Enable

```bash
mkdir -p ~/.hermes/aipp_bridge
chmod 700 ~/.hermes/aipp_bridge
python3 -c "import secrets; print(secrets.token_urlsafe(32))" \
    > ~/.hermes/aipp_bridge/session.token
chmod 600 ~/.hermes/aipp_bridge/session.token

# start the bridge (foreground; kill the process to stop)
python3 scripts/game_bridge.py --token-file ~/.hermes/aipp_bridge/session.token

# in another shell: verify it is up
python3 scripts/play.py health
```

`scripts/play.py` picks up the default token path automatically; override with
`AIPP_BRIDGE_TOKEN_FILE` / `AIPP_BRIDGE_PORT` when running more than one bridge.

## Revoke

```bash
# kill the bridge process (Ctrl-C if foreground, or:)
pkill -f scripts/game_bridge.py
rm ~/.hermes/aipp_bridge/session.token
```

Deleting the token means any new bridge cannot be started with it and any
client still holding it can no longer connect once the process is gone.

## Concurrency

The bridge serialises one request at a time against a single emulator under a
lock, with a bounded worker pool and pending queue. The incident analysis in
[bridge-thread-incident-2026-09-30.md](bridge-thread-incident-2026-09-30.md)
covers what went wrong before those bounds existed. To verify current
concurrency behaviour on your machine, run
`scripts/verify_game_bridge_concurrency.py`.

## Troubleshooting

- Check `health` first: it reports ROM, boot state, pause state and goal.
- Read the thread/concurrency incident write-up before debugging hangs:
  [docs/bridge-thread-incident-2026-09-30.md](bridge-thread-incident-2026-09-30.md).
- Run `scripts/verify_game_bridge_concurrency.py` to confirm the lock/queue
  bounds behave as documented on this host.
