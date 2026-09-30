# Bridge thread leak — 2026-09-30 (LOAD-BRIDGE-1)

## What happened

`aipp-bridge.service` (`scripts/game_bridge.py`, owning the emulator on
`127.0.0.1:8770`) grew to **1018 threads, all in `R` state**, while its CPU share
was 304%. Host `loadavg` climbed linearly from a 5–25 baseline to a **1015.9**
peak over 73 minutes (2026-09-29 21:49 → 23:02Z, ~13 threads/min), and
**nothing alerted**: `forkbomb-reaper` logged `killed_total=0` in every sample
for the whole hour, because it models shell busy-waits and fork storms, not
thread spins inside a long-lived service.

Measured load1_after series from `~/.hermes/logs/forkbomb-reaper.jsonl`:

| time (local) | load1_after |
|---|---|
| all of 09-29 baseline | 5–25 |
| 21:49 | 36 |
| 22:10 | 176 |
| 22:24 | 399 |
| 22:31 | 514 |
| 22:42 | 686 |
| 22:49 | 807 |
| 23:02:13 | **1015.9 (peak)** |

`/proc/loadavg` 1-minute load equalled the `R`-thread count (1015.9 vs 1018), and
only 2 other processes on the box were runnable — this was one PID spinning.

The process exited at 23:02:57 with **no crash line** in `/tmp/aipp_bridge.log`,
no OOM in `journalctl`, and 39 GB RAM free; systemd `Restart=always` respawned it
into a 16-thread instance.

## The leak path

`serve()` was `accept()` → `threading.Thread(target=handle, daemon=True).start()`
— **one unbounded daemon thread per accepted connection**, never joined, no pool,
no cap. Nothing limited how many connections could exist at once, so every
connection that arrived while a `Game` call was still running added a permanent
thread.

The traffic that fed it is the console: `aipp-console/server.py` `_stream()`
(`GET /api/stream`) calls `build_state()` → `game_state()` → a line-delimited
`{"cmd": "raw"}` request **on every SSE tick**, and `bridge()` retries up to 3
times before reporting `bridge unreachable`. One slow `Game` call therefore turns
into a retry multiplier from every open tab, which is exactly the shape that
produces a linear ~13 threads/min ramp.

## The fix

In `scripts/game_bridge.py`:

- `serve()` now owns a **fixed worker set** (`--max-workers`, default 4) and a
  bounded pending queue of the same size; the accept loop only enqueues, and a
  full queue answers `{"ok": false, "error": "server busy"}` and closes. No
  connection can create a thread.
- Every `Game` operation is **serialized behind one lock** in `handle()`.
  PyBoy + `RAMReader` + the bridge's cross-cycle state are a single mutable unit
  and are not safe to enter concurrently; socket parsing stays parallel, game
  access does not.
- Clean shutdown: `SIGINT`/`SIGTERM` set a stop event, `serve()` drains the
  queue, shuts down active sockets, and joins the workers within
  `SHUTDOWN_JOIN_TIMEOUT`.
- Request hardening kept/added: per-request socket timeout (30 s), 1 MiB request
  ceiling, JSON-object check, and the unchanged token `compare_digest` gate.

Preserved on purpose: loopback-only bind, token required on every request, and
one request per connection.

## How to verify

Fast, ROM-free, no paid API:

```bash
.venv/bin/python -m pytest tests/test_game_bridge.py -q
.venv/bin/python scripts/verify_game_bridge_concurrency.py --duration 30 --workers 4 --concurrency 4
```

`verify_game_bridge_concurrency.py` spawns a controlled fake `Game` on an
ephemeral loopback port, hammers it with concurrent authenticated requests, and
reads `/proc/<pid>/status` every batch: it fails loudly if any response is
non-JSON, non-`ok`, comes from the wrong responder, shows overlapping `Game`
access, or if the child thread count exceeds `workers + 1`. It also fails if the
child cannot shut down cleanly. Exit is non-zero with the reason on stderr.

Sample PASS line:

```
PASS: requests=292 duration_s=3 max_child_threads=5 ceiling=5 workers=4 concurrency=4
```

## Not exercised, deliberately

- No `press`/`step`/`save`/`reset` driving of a live game: those change game
  state and need explicit approval. The soak uses `health` against a fake Game;
  the regression tests use a blocking fake `raw` so they never touch a ROM.
- The live unit on port 8770 was not restarted by this change. Rollout is
  `systemctl --user restart aipp-bridge.service`.

## Still open (filed, not fixed here)

The host-level half of the finding — a watchdog that asserts no single PID
exceeds a thread ceiling and **restarts the unit**, so this class alerts instead
of silently burning the box — is a systemd/host concern outside this repo's
change surface. The measurement and the reaper-blindness evidence are captured
above; the follow-up row is filed on the board.
