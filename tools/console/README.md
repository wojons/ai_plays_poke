# Console QA tools

These tools test the local operator console served at `http://127.0.0.1:8899`. The
console lives in `~/aipp-console` and normally runs as the `aipp-console.service`
systemd user unit. The runner follows the existing tools' API and port; the separate
FastAPI dashboard in `src/dashboard/main.py` is not the console they exercise.

## Unattended runner

From the repository root:

```bash
make qa-console
```

The target selects `venv/bin/python`, then `.venv/bin/python`, then `python3`. The
runner:

1. checks `GET /api/health` and starts `aipp-console.service` if the console is down;
2. runs `test_controls.py` and fails if any of its read endpoints is not HTTP 200;
3. drives both boolean values through `/api/live` and `/api/auto`, verifies each value
   in both the response and `/api/state`, and restores the original values;
4. runs `test_pass.py`; and
5. exits non-zero for every non-movement failure.

Movement buttons are deliberately not tested unattended. The runner blocks every
`/api/press` request before it reaches the console, skips the movement assertions and
their save-state restore, and prints a `SKIP` line for each exclusion. Pressing a
movement button changes the live game state and requires an approved interactive run.

To verify the wiring and movement blocker without contacting the console:

```bash
make qa-console-dry-run
```

## QA lane / cron invocation

The QA lane should run the same target from the canonical checkout:

```bash
cd /home/kara/ai_plays_poke && make qa-console
```

For cron, prevent overlapping live passes and preserve the runner's exit status:

```cron
17 * * * * cd /home/kara/ai_plays_poke && flock -n /tmp/aipp-console-qa.lock make qa-console >> /home/kara/aipp-console/data/qa.log 2>&1
```

A failed endpoint, ignored toggle value, tool crash, or failed panel check makes the
command exit non-zero, so the QA lane/cron can alert instead of recording a false pass.

## Tool inventory

- `test_controls.py` — enumerates and exercises the console controls, including
  malformed input. It already avoids movement endpoints.
- `test_pass.py` — full live console pass. Run it through `run_qa.py` for unattended
  use so movement calls cannot reach the game.
- `test_auto_vision.py` — proves the vision panel refreshes on its own; it moves the
  game and is therefore interactive-only.
- `bench_vision_accuracy.py` — scores a vision model against the reader grid, cell by
  cell.
- `bench_equipped.py` — compares grid reading and people identification by model.
- `vision_10x9.md` — the prompt that measured best.

The individual tools can still be run with the project venv when an approved
interactive investigation needs them:

```bash
/home/kara/ai_plays_poke/venv/bin/python tools/console/test_controls.py
```
