# cron_runner

Cron-friendly Pokémon AI runner — the README's sole recommended entry point for real autonomous gameplay.

## Overview

`cron_runner.py` is an end-to-end runner that boots the emulator, bypasses the intro, and plays Pokémon Blue autonomously. It reads game state directly from emulator RAM (instant, free) and spends LLM calls only on game decisions:

1. **Observe** game state — RAM reader (default) OR Gemma 12B vision cartographer.
2. **Overworld** — the controller model (`openai/gpt-5.6-luna` via OpenRouter) reads spatial data and outputs a button plan.
3. **Execute** the plan with direction-locking detection and checkpoint rollback.
4. **Non-overworld** (battle, dialog, menu, name entry) — the existing StateWindow flow with `deepseek-v4-flash`.

Unlike the legacy `src/game_loop.py` (whose vision pipeline is under repair — AP-GAP-001), `cron_runner.py` performs no paid vision calls per tick in its default RAM-reader mode.

## Usage

```bash
# From the repo root, with the project venv activated
python3 cron_runner.py --run-id demo1 --cycles 80
```

```bash
# Validate setup without booting the emulator or spending LLM calls
python3 cron_runner.py --dry-run
```

`--dry-run` prints a pipeline config summary (ROM path, boot-state path, cycles, run-id, model/provider config, API-key presence) and exits 0. It never boots the emulator and never makes an LLM/API call. Because the check runs before the heavy third-party imports, it also works under bare `python3` (no venv, no numpy/PIL). It exits 1 if the ROM is missing (a real run would crash at boot); a missing or explicitly bad boot-state path is reported as a warning with the intro-bypass fallback, matching runtime behavior.

```text
usage: cron_runner.py [-h] [--run-id RUN_ID] [--cycles CYCLES]
                      [--boot-state BOOT_STATE] [--dry-run]

Cron-friendly Pokemon AI runner with RAM reader / cartographer → controller
pipeline. Flow: 1. Observe game state (RAM reader OR Gemma 12B cartographer)
2. If overworld: controller (openai/gpt-5.6-luna via OpenRouter) reads spatial data → button
plan 3. Execute plan with direction-locking detection, checkpoint rollback 4.
Non-overworld: existing StateWindow flow

options:
  -h, --help            show this help message and exit
  --run-id RUN_ID
  --cycles CYCLES
  --boot-state BOOT_STATE
                        Path to a known-good .state checkpoint to boot from
                        instead of the intro bypass (default: data/boot.state
                        when present; 'skip' forces the legacy intro bypass).
  --dry-run             Validate setup (ROM + boot-state paths, config
                        summary) and exit 0 — no emulator boot, no LLM/API
                        calls (GAP-032).
```

## CLI Flags

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `-h, --help` | — | — | Show usage and exit |
| `--run-id RUN_ID` | `str` | auto-generated `%Y%m%d_%H%M%S` timestamp | Label for this run. Sets the log path `cron_logs/run_<run-id>.jsonl` and the screenshot directory `screenshots/run_<run-id>/`. Reusing an id overwrites the previous log. |
| `--cycles CYCLES` | `int` | `200` | Number of AI decision cycles to run. Clamped to a minimum of 1 (`CYCLES = max(1, args.cycles)`). |
| `--boot-state BOOT_STATE` | `str` | `data/boot.state` if present | Path to a known-good `.state` checkpoint to boot from instead of the intro bypass. `skip` forces the legacy intro bypass (title-screen A-mash). If the path does not exist, the runner falls back to the intro bypass with a warning. |
| `--dry-run` | `flag` | `false` | Validate setup and print a config summary (ROM path, boot-state path, cycles, run-id, model/provider config, API-key presence), then exit 0 — no emulator boot, no LLM/API calls. Runs before the heavy third-party imports, so it also works under bare `python3`. Exits 1 if the ROM is missing; a missing boot-state path is a warning (intro-bypass fallback), not an error. |

Runtime behavior is configured by module-level constants (not flags): `ROM` (default `data/rom/Pokemon - Blue Version (USA, Europe) (SGB Enhanced).gb`), `DEFAULT_BOOT_STATE` (default `data/boot.state`), `USE_RAM_READER` (True = RAM reader, False = Gemma 12B cartographer), `HINT_LEVEL` (prompt hint depth, default 4 = navigation), `CART_STEPS` (controller actions per overworld cycle, default 6), and the checkpoint/recovery thresholds listed below.

## Pipeline Stages

### 0. Boot — known-good checkpoint (default) or intro bypass

**Checkpoint boot (default):** when `data/boot.state` exists, the emulator loads it and skips the intro entirely. The shipped checkpoint is a deterministic PyBoy state saved from a verified run: the player stands in Oak's Lab (map 0x28, tile ~(4,4)) with the starter already picked (party = 1) and no dialog open. Loading is deterministic for the pinned PyBoy version (verified: two loads produce byte-identical frames and RAM).

**Intro bypass (fallback / `--boot-state skip`):** deterministic boot sequence — wait for title, `START`, then A-mash through the intro with a phase state machine (title → dialog → name_entry → overworld). Name entry escalates to programmatic typing (`submit_name()`, ASH/GARY) after 3 stuck cycles; a detected old save file restarts with NEW GAME. A checkpoint is saved to slot 0 at the bedroom, then the runner walks to Pallet Town. This path can land in a degenerate wall-facing overworld state that direction-locks on the first cycles — the checkpoint boot exists to avoid it.

**First cycles:** cycle 1 observes the overworld via RAM and sends spatial state to the controller. `[CACHE-HIT]` frame references appear when the same frame repeats (standing still, walking animation loop) — normal. `[WARN] Direction-locking detected: <dir> x3` fires when a single plan contains 3+ consecutive same-direction presses (a straight walk triggers it even while moving); it is only a warning — recovery escalates at 4+ consecutive same-direction presses across cycles without progress.

**Summary metrics:** the final line reports `lock-rate: N/CYCLES cycles with direction-lock warnings (P%)` — the fraction of cycles containing ≥1 direction-lock warning — plus `distinct tiles: N` — unique (map, x, y) RAM tiles observed. Healthy overworld runs stay well under 50% lock-rate and visit multiple tiles.

### 1. Observe — RAM reader (default) or cartographer

- **RAM reader** (`USE_RAM_READER = True`, default): instant, free reads of map id, player tile coordinates, party count, menu state, battle state, and dialog rendering. No frame hashing needed.
- **Cartographer** (`USE_RAM_READER = False`): `google/gemma-3-12b-it` vision model (temperature 0.1, max_tokens 2048) classifies the screenshot against `reference/bedroom_overworld.png` and returns spatial JSON (adjacent tiles, visible exits, player facing, suggested action). Identical frames are skipped via an md5 frame hash that reuses the cached observation.

### 2. Overworld — controller plan

The controller (`openai/gpt-5.6-luna` via OpenRouter, temperature 0.3, max_tokens 300, thinking disabled) receives a compact spatial summary (map name, player tile, facing, adjacent tiles, visible exits, screen text, suggested action) plus memory context (goal, notes, last dialog, study result) and outputs a JSON movement plan: `{"plan": ["UP","DOWN","A",...], "intent": "..."}` — max `CART_STEPS` (6) actions.

Before execution the plan passes through three deterministic filters:

- **Blacklist rotation** — directions that caused a checkpoint recovery are chain-rotated 90°; if all four are blacklisted the action becomes `A`.
- **Spatial pre-filter** — directions whose adjacent tile is `wall` or `object` are stripped (Pallet Town's north map-edge exit is preserved).
- **Run-length cap** — max 3 consecutive same-direction moves, then `A`.

### 3. Execute — with stuck detection and recovery

Each plan action is pressed (`PRESS_FRAMES` = 5) with a settle fast-forward (`STEP_FORWARD` = 15). Five independent stuck detectors feed an escalating recovery ladder (see [Checkpoint & Rollback](#checkpoint--rollback)):

| Detector | Threshold | Meaning |
|----------|-----------|---------|
| Direction-locked | 4 consecutive same-direction presses | Blocked path — the direction is likely a wall |
| Screen-locked | 5 cycles on same screen type (non-overworld) | Dialog/menu loop |
| Tile-locked | 8 cycles on same RAM (map, x, y) tile | No movement despite walking |
| Void-locked | 3 cycles with >95% unknown adjacent tiles | Cartographer blind / bad observation |
| A-press-locked | 3 consecutive A presses without direction change | Stuck interacting |

### 4. Non-overworld — StateWindow flow

Battle, dialog, menu, and name_entry screens go through the existing `StateWindow` flow with `deepseek-v4-flash` as the thinking model (`max_steps=1` for battle and name_entry, `STATE_STEPS` = 12 otherwise). Battle entries execute one action per fresh RAM read; dialog text is carried over to the next overworld decision. A deterministic branch selects the first starter in Oak's Lab (RAM-reader mode) without any LLM call.

### Agent memory (DuckBrain)

The controller maintains its own knowledge, persisted to DuckBrain (namespace `pokemon-global`): optional `note` / `goal` / `study` fields in its JSON response are executed by the runner — notes are stored under `/notes/overworld-<cycle>`, the goal under `/goals/current` (and re-loaded at startup), and study keys are fetched and injected into the next cycle's prompt.

## Outputs

- `cron_logs/run_<id>.jsonl` — one JSON object per line (see schema below).
- `screenshots/run_<id>/step_NNNN.png` — 160×144 RGB frame per cycle (`BATTLE_NNNN.png` on rival battles).

## JSONL Log Schema (`cron_logs/run_<id>.jsonl`)

One JSON object per line, written incrementally (the log doubles as a live feed for web viewers). Entry types are distinguished by `event` (for event rows) or `screen` (for per-cycle decision rows).

### Per-cycle decision rows

**Overworld (controller path):**

| Field | Type | Description |
|-------|------|-------------|
| `cycle` | `int` | 1-based cycle number |
| `screen` | `str` | `"overworld"` |
| `pipeline` | `str` | `"RAM reader"` or `"cartographer"` |
| `plan` | `list[str]` | Executed button plan (uppercase) |
| `intent` | `str` | Controller's stated intent |
| `controller_raw` | `str` | Raw controller JSON response |
| `frame_cache` | `str` | `"hit"` (image tokens skipped, UUID ref sent) or `"miss"` |
| `frame_uuid` | `str \| null` | FrameCache UUID reference on a hit |
| `cartographer_raw` | `str` | Raw observation payload (RAM reader: `{"source": "ram_reader", "result": "overworld"}`) |
| `map_id` / `map_name` | `int` / `str` | Current map |
| `player_x` / `player_y` | `int` | Screen-space player coordinates |
| `player_tile_x` / `player_tile_y` | `int` | Map tile coordinates |

```json
{"cycle": 1, "screen": "overworld", "pipeline": "RAM reader", "plan": ["DOWN", "DOWN", "RIGHT"], "intent": "Move away from the house door toward the route.", "controller_raw": "{\"plan\":[\"DOWN\",\"DOWN\",\"RIGHT\"],\"intent\":\"...\"}", "frame_cache": "hit", "frame_uuid": "88f6ea8100b0", "cartographer_raw": "{\"source\": \"ram_reader\", \"result\": \"overworld\"}", "map_id": 0, "map_name": "Pallet Town", "player_x": 2, "player_y": 3, "player_tile_x": 5, "player_tile_y": 6}
```

**Non-overworld (StateWindow path — battle, dialog, menu, title, etc.):**

| Field | Type | Description |
|-------|------|-------------|
| `cycle` | `int` | 1-based cycle number |
| `screen` | `str` | Observed screen type (`battle`, `dialog`, `menu`, `title`, ...) |
| `state` | `str` | StateWindow state type (e.g. `name_entry` for keyboard subtype) |
| `action` | `str` | Last tool call, e.g. `press_button({'button': 'a', 'duration': 30})`, or `"?"` |
| `elapsed_s` | `float` | Seconds spent on the cycle |
| `cartographer_raw` | `str` | Raw observation payload |
| `state_window_raw` | `str` | Raw StateWindow model responses (newline-separated) |
| `battle_events` | `list` | Battle sub-events from StateWindow (empty for non-battle) |
| `failed_flee_attempts` | `int` | Running count of failed flee attempts (fed into next battle prompt) |

**Name entry bypass:**

| Field | Type | Description |
|-------|------|-------------|
| `cycle` / `screen` | `int` / `str` | Cycle number / `"name_entry"` |
| `action` | `str` | `"name_bypass"` |
| `elapsed_s` | `float` | Seconds spent on the cycle |
| `cartographer_raw` | `str` | Raw observation payload |

### Event rows

| Event | Fields |
|-------|--------|
| `starter_selection` | `cycle`, `screen`, `event`, `action` (`confirm_first_starter_then_decline_nickname`), `map_id`, `party_count_before`, `party_count_after`, `player_tile_x`, `player_tile_y` |
| `starter_picked` | `cycle`, `event`, `party_count` (1), `species_hint` |
| `battle_start` | `cycle`, `event`, `battle_type` (`wild` / `trainer`, ...) |
| `battle_end` | `cycle`, `event`, `next_screen` |
| `RIVAL_BATTLE_REACHED` | `cycle`, `event` (milestone marker) |
| `state_saved` | `cycle`, `event`, `slot` (0-4) |
| `recovery` | `cycle`, `event`, `level` (0-4 ladder rung), `strategy`, `reason`, `attempt`, `description` |
| `recovery_exhausted` | `cycle`, `event`, `reason`, `attempts` (written when the runner gives up) |
| `memory_note` | `cycle`, `event`, `map`, `note` |
| `memory_goal` | `cycle`, `event`, `goal` |
| `memory_study` | `cycle`, `event`, `key`, `result` |
| `error` | `cycle`, `error` (full traceback text) |

```json
{"cycle": 3, "event": "recovery", "level": 0, "strategy": "alternate_direction", "reason": "direction-locked (RIGHT x4)", "attempt": 1, "description": "rotated from RIGHT → DOWN"}
{"cycle": 10, "event": "state_saved", "slot": 0}
{"cycle": 31, "event": "battle_start", "battle_type": "trainer"}
```

## Checkpoint & Rollback

**Checkpointing:** emulator state is saved every `CHECKPOINT_INTERVAL` (10) cycles into `CHECKPOINT_SLOTS` (5) rotating slots (0-4); slot 0 holds the post-intro bedroom save. Each save emits a `state_saved` event with the slot number.

**Recovery ladder** — when a stuck detector fires, the runner escalates through these rungs (`_recovery_level`), capped at `MAX_RECOVERY_ATTEMPTS` (5):

| Level | Strategy | Action |
|-------|----------|--------|
| 0 | `alternate_direction` | Rotate 90° from the last direction |
| 1 | `menu_redraw` | START → B → B (force screen refresh) |
| 2 | `step_back` | Press the opposite of the last direction |
| 3 | `load_checkpoint` | Restore the last saved slot; the blocked direction is added to the blacklist |
| 4 | `a_mash` | 20 rapid A presses, then B (dialog/menu escape) |

Special cases:

- **Battles bypass the generic ladder entirely** — loading a checkpoint would erase the encounter and START/B/A-mash are not legal turns. Instead a normalized `select_move(1)` action is re-issued from the live battle state.
- **Dialogs use a fast path** — a dialog box is not stuck; 12× A presses advance the text (`dialog_advance` strategy) instead of the menu_redraw rung.
- After `MAX_RECOVERY_ATTEMPTS` (5) escalations the runner logs `recovery_exhausted` and stops recovering (`_gave_up`).

## Cost Notes

- **RAM-reader mode is free per tick** — state observation comes from RAM, so only decision cycles spend LLM tokens. A measured 80/80-cycle E2E run cost ≈ **$0.60 for 43 LLM calls** (README provenance).
- **Overworld cycles** call the controller `openai/gpt-5.6-luna` via OpenRouter (vision model, double-discount pricing; temp 0.3, max_tokens 300).
- **FrameCache dedup** cuts image-token spend: every screenshot is md5-hashed against a disk-backed LRU cache (`data/frame_cache.json`, max 1000 entries, survives restarts). First sighting sends the image (~2500 image tokens); any repeat sighting (standing still, same dialog, battle idle) sends a short text UUID reference instead — same visual info at ~zero image tokens. Logged as `frame_cache: hit|miss` per cycle.
- **Non-overworld cycles** run StateWindow with `deepseek-v4-flash` (text-only, cheap). When `DEEPSEEK_API_KEY` is set, DeepSeek models are routed to `api.deepseek.com` directly instead of OpenRouter.
- **Cartographer mode** (only when `USE_RAM_READER = False`) adds a `google/gemma-3-12b-it` vision call per changed frame — this is why RAM-reader mode is the default.
- Fleet cost accounting uses the wrapper at `~/bin/bash.014/call` for OpenRouter call logging/billing.

## Environment

| Variable | Required | Purpose |
|----------|----------|---------|
| `OPENROUTER_API_KEY` | Yes (or `OPENAI_API_KEY`) | Controller (Luna), cartographer, and StateWindow OpenRouter calls |
| `DEEPSEEK_API_KEY` | Optional | Routes DeepSeek models (`deepseek-v4-flash`) to `api.deepseek.com` for lower cost |
| `OPENAI_API_KEY` | Fallback | Used only if `OPENROUTER_API_KEY` is unset (OpenRouter rejects `sk-` OpenAI keys — `OPENROUTER_API_KEY` is preferred) |

Copy `.env.example` to `.env` and fill in the key; the runner loads it at startup.

## See Also

- [API Documentation Index](index.md)
- [README Quick Start (working path)](../../README.md#quick-start-working-path)
- [StateWindow](game_state.md) — non-overworld decision flow
- [Emulator](emulator_interface.md) — PyBoy control (`press_button`, `fast_forward`, `save_state`/`load_state`)
