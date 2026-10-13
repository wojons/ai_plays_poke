# ptp_cli (src/ptp_cli/)

The PTP-01X command-line flag surface: a single argparse parser (`CLIFlagParser` in `src/ptp_cli/flags.py`) covering tick-rate control, screenshot capture, command buffering, run limits, snapshot/save-state management, experiment orchestration, and system flags. Running the package parses and validates the arguments, then prints the resolved configuration.

> **Note:** the parser is the CLI *contract* (the flag names/limits downstream code is specified against) — it is not yet wired into the gameplay pipeline. See [Wiring status](#wiring-status).

## Modules

| Path | Role |
|------|------|
| `src/ptp_cli/__main__.py` | `python -m src.ptp_cli` entry point — mirrors the `if __name__ == "__main__"` block in `flags.py` |
| `src/ptp_cli/flags.py` | `CLIFlagParser` (argparse groups), the `FullConfig` / per-group dataclasses, and `create_config_from_args()` |

Both entry paths behave identically: `--help`/`-h` prints parser help and exits 0; otherwise the args are parsed + validated and the resulting config is printed.

## Running

From the repo root, with the project venv activated:

```bash
source .venv/bin/activate
python -m src.ptp_cli --help
```

```bash
# Parse + validate a configuration and print it (the ROM path must exist)
python -m src.ptp_cli --rom "data/rom/Pokemon - Blue Version (USA, Europe) (SGB Enhanced).gb" --save-dir ./game_saves --max-ticks 5000
```

```bash
# Equivalent invocation used in the dogfood/integration record
PYTHONPATH=src .venv/bin/python -m src.ptp_cli --help
```

`--help` exits 0 with the full usage block plus the grouped flag descriptions and the examples epilog. A ROM path that does not exist is reported as `ERROR: ROM file not found: <path>`, followed by the full help text, and exits 1.

> The epilog examples in `flags.py` name `python src/game_loop.py …` (the legacy loop path, whose vision pipeline is under repair). The real invocations to use are the `python -m src.ptp_cli …` forms above — see [cron_runner](cron_runner.md) for actual autonomous gameplay.

## Flags

`--rom` is required and `--save-dir` defaults to `./game_saves`; everything else is optional. "Default: unlimited" means the limit flag defaults to `None` (no cap). All names/defaults/help text below are transcribed from `flags.py` and match `--help` output.

### Required options

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--rom` | str | — (**required**) | Path to Pokemon ROM file (.gb or .gbc) |
| `--save-dir` | str | `./game_saves` | Directory for saves, database, and screenshots |

### Tick Rate Control

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--tick-rate-base` | int | `10` | Base tick rate for overworld exploration (ticks/second); must be 1–60 |
| `--tick-rate-battle` | int | `2` | Tick rate during battle sequences (ticks/second); must be 1–30 |
| `--tick-rate-timeout` | int | `30` | Maximum seconds without state change before timeout; must be ≥ 5 |
| `--tick-rate-adaptive` | flag | `False` | Auto-adjust rate based on decision latency |
| `--tick-rate-budget` | `{hourly,daily,run}` | `None` | Cost budget mode |
| `--tick-rate-budget-limit` | float | `None` | Maximum budget in dollars per period (required with `--tick-rate-budget`) |

### Screenshot Control

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--screenshot-interval` | int | `100` | Base screenshot interval in ticks; must be ≥ 1 |
| `--screenshot-battle-turn` | int | `1` | Screenshots captured per battle turn |
| `--screenshot-on-error` | int | `1` | Screenshots captured per error tick |
| `--screenshot-on-change` | flag | `False` | Capture screenshot on any state transition |
| `--screenshot-quality` | int `[0-100]` | `85` | JPEG quality 0–100 |
| `--screenshot-max-storage` | float | `50.0` | Maximum storage in GB for screenshots; must be positive |
| `--screenshot-async` | flag | `False` | Enable non-blocking (async) screenshot capture |
| `--screenshot-compress` | flag | `False` | Compress old screenshots to save storage |

### Command Buffer Control

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--command-buffer-size` | int | `10` | Maximum number of queued commands; must be ≥ 1 |
| `--command-timeout` | int | `5` | Maximum seconds a command can wait in buffer; must be ≥ 1 |
| `--command-validate` | flag | `False` | Validate commands against current game state before execution |
| `--command-rollback-history` | int | `100` | Number of commands stored for potential rollback; must be ≥ 0 |
| `--command-interrupt-battle` | flag | `True` | Clear command buffer when random battle starts |
| `--command-stale-threshold` | int | `2` | Seconds before command is considered stale; must be ≥ 0 |

### Run Limits

Stopping conditions; `--on-limit` decides what happens when one is hit.

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--max-time` | int | unlimited | Maximum real time in seconds; must be positive |
| `--max-ticks` | int | unlimited | Maximum game ticks to execute; must be positive |
| `--max-cost` | float | unlimited | Maximum cost in USD; must be positive |
| `--max-pokemon-caught` | int | unlimited | Stop after catching N Pokemon; must be positive |
| `--max-badges` | int | unlimited | Stop after earning N badges (0–16) |
| `--max-level` | int | unlimited | Stop when Pokemon reaches level N (1–100) |
| `--on-limit` | `{save-and-exit,save-only,abort}` | `save-and-exit` | Action when a limit is reached |
| `--limit-grace-period` | int | `30` | Seconds to finish current decision before stopping; must be ≥ 0 |

### Snapshot Management

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--snapshot-memory` | int | `10` | Number of RAM snapshots for instant restore; must be ≥ 0 |
| `--snapshot-disk` | int | `1000` | Interval in ticks for disk snapshots; must be ≥ 100 |
| `--snapshot-on-event` | str | `""` | Event triggers for snapshots: `catch,battle,badge,death` (comma-separated) |
| `--snapshot-max-disk` | float | `20.0` | Maximum storage in GB for snapshots; must be positive |
| `--snapshot-compress` | flag | `False` | Compress disk snapshots to save storage |
| `--snapshot-validate` | flag | `False` | Validate snapshots can be restored after saving |
| `--rollback-on-error` | flag | `False` | Automatically rollback to last good snapshot on error |
| `--rollback-grace` | int | `3` | Maximum rollback depth; must be ≥ 0 |
| `--snapshot-share` | flag | `False` | Allow sharing snapshots via network |
| `--snapshot-name` | str | `None` | Name for creating a named snapshot |

### Save State Control

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--save-interval-ticks` | int | `1000` | Snapshot interval in ticks; must be ≥ 100 |
| `--save-max-snapshots` | int | `10` | Maximum number of snapshots to keep; must be ≥ 1 |
| `--save-on-event` | str | `""` | Event triggers: `battle,level_up,badge,catch,location_change` (comma-separated) |
| `--emergency-snapshot-count` | int | `3` | Number of emergency snapshots to preserve on crash; must be ≥ 1 |
| `--save-state-validate` | flag | `False` | Validate save states can be restored after saving |
| `--save-state-compress` | flag | `False` | Compress old save states to save storage |

### Experiment Orchestration

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--experiment-name` | str | `default` | Experiment identifier for grouping results |
| `--parallel-workers` | int | `1` | Maximum concurrent game instances; must be ≥ 1 |
| `--sequential-retry` | int | `3` | Number of retries on failure; must be ≥ 0 |
| `--parallel-memory-limit` | float | `8.0` | Per-worker memory limit in GB; must be positive |
| `--parallel-api-rate-limit` | int | `100` | Maximum API calls per minute across all workers; must be ≥ 1 |
| `--aggregate-stats` | flag | `False` | Calculate mean and standard deviation for parallel runs |
| `--fail-mode` | `{continue,fast-fail,retry}` | `continue` | Behavior on failure |
| `--checkpoint-frequency` | int | `10000` | Save checkpoint after N sequential runs; must be ≥ 0 |
| `--resume-from` | str | `None` | Resume experiment from checkpoint directory |
| `--experiment-config` | str | `None` | Load experiment settings from YAML config file |
| `--export-results` | flag | `False` | Export aggregated results after experiment completes |
| `--results-format` | `{json,csv,parquet}` | `json` | Output format for exported results |

### System Flags

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `-v`, `--verbose` | flag | `False` | Enable verbose output |
| `-q`, `--quiet` | flag | `False` | Suppress all output except errors |
| `--log-file` | str | `None` | Write logs to specified file |
| `--config-file` | str | `None` | Load additional configuration from YAML file |
| `--random-seed` | int | `None` | Random seed for reproducibility |

## Validation

`CLIFlagParser.parse_and_validate()` parses the args and runs `validate_config()`, which returns a list of error strings. `create_config_from_args()` prints each error prefixed with `ERROR:`, prints the full help text, and exits 1 when the list is non-empty; otherwise it returns the `FullConfig`.

Checks performed (all in `flags.py`):

- `--rom` is set and the path exists (`ROM file not found: <path>`).
- Per-group bounds, as noted in the Type/Description columns above (e.g. `tick-rate-base must be <= 60`, `max-badges must be 0-16`, `invalid snapshot-on-event: <value>`).
- `--tick-rate-budget` requires `--tick-rate-budget-limit`.
- `--verbose` and `--quiet` cannot be combined.
- When `--parallel-workers > 1` and `--resume-from` is given, the resume directory must exist.

All of the above are hard failures: any one of them makes the executable print `ERROR: …`, dump the help text, and exit 1. `--tick-rate-adaptive` combined with `--tick-rate-base > 30` is itself an error (`adaptive mode works best with tick-rate-base <= 30`), not just a warning.

## Wiring status

`src/ptp_cli` is a wired **package** (importable, `__main__` entry point, exercised by `tests/ptp_cli/test_flags.py`) but the parsed `FullConfig` is not yet consumed by the game loop: the only other reference in `src/` is the integration-point list in the `src/core/save_manager.py` module docstring. Today the executable's observable behavior is: print help (exit 0) or print the validated configuration (exit 0) / report errors + help (exit 1). It boots no emulator and makes no API calls.

## Tests

```bash
.venv/bin/python -m pytest tests/ptp_cli/ -v
```

## See Also

- [API Documentation Index](index.md)
- [cron_runner](cron_runner.md) — the recommended entry point for actual autonomous gameplay
- [Dashboard](dashboard.md) — observability dashboard server
- `specs/ptp_01x_cli_control_infrastructure.md` — the spec the flag surface implements
