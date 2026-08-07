# ai-plays-poke — Real-Use Integration Report (2026-08-07)

Dogfood run by the coding-hermes cron. Two entry points exist. **Only one works for real gameplay.**

## TL;DR

| Entry point | Documented? | Works? | AI decisions? |
|---|---|---|---|
| `src/game_loop.py` (README/AGENTS.md) | ✅ everywhere | ⚠️ runs, but AI pipeline crashes every tick | ❌ 0 |
| `cron_runner.py` (E2E runner) | ❌ nowhere (one line in SKILL.md) | ✅ 10/10 cycles | ✅ 13 actions |

**Use `cron_runner.py` for real gameplay.** `src/game_loop.py` is the official-looking but broken path (DF-001).

## Setup (one-time)

```bash
cd /home/kara/ai_plays_poke
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill OPENROUTER_API_KEY (and optionally DEEPSEEK_API_KEY)
# ROM: data/rom/Pokemon - Blue Version (USA, Europe) (SGB Enhanced).gb (already present)
```

Note: `.venv` already exists in this repo with everything installed. `venv/` also exists (older). Use `.venv`.

## The working path — autonomous E2E runner

```bash
python3 cron_runner.py --run-id my_first_run --cycles 80
```

- `--run-id` labels all artifacts; `--cycles` = number of AI decision cycles (fleet runs 80; 10 ≈ $0.15, 80 ≈ $0.60–1.20).
- Model: `openai/gpt-5.6-luna` via OpenRouter (key from `.env`). State reading: RAM reader (free, instant) — no vision API calls per tick.
- Outputs:
  - `cron_logs/run_<run-id>.jsonl` — one JSON line per cycle: `screen`, `plan` (button sequence), `intent` (LLM rationale), `player_x/y`, `map_name`, plus `event` rows (`recovery`, `state_saved`) — see schema below.
  - `screenshots/run_<run-id>/step_000N.png` — 160×144 RGB frames.
  - `data/frame_cache.json` — persistent screenshot-hash cache (survives runs).
  - `data/emergency_snapshots/` — emulator states on trouble.
  - stdout: per-cycle `[N/80] screen | pipeline | seconds`, `📡 API: <model> | <ms> | $<cost>`, `[WARN] Direction-locking`, `[RECOVER] Level 0: ...`, `[CKPT] Saved state to slot N`.
- Exit code 0 on success. Clean Ctrl+C-safe behavior.

### JSONL schema (verified 2026-08-07)

```json
{"cycle": 1, "screen": "overworld", "pipeline": "RAM reader",
 "plan": ["DOWN", "RIGHT", "RIGHT", "UP"], "intent": "Move away from the house door...",
 "controller_raw": "{...}", "frame_cache": "hit", "frame_uuid": "88f6ea8100b0",
 "cartographer_raw": "{\"source\": \"ram_reader\", \"result\": \"overworld\"}",
 "map_id": 0, "map_name": "Pallet Town", "player_x": 2, "player_y": 3,
 "player_tile_x": 5, "player_tile_y": 6}
```

Event rows (non-cycle): `{"cycle": 3, "event": "recovery", "level": 0, "strategy": "alternate_direction", "reason": "direction-locked (RIGHT x4)", "attempt": 1}` and `{"event": "state_saved", "slot": 0}`.

### What a healthy run looks like (dogfood 10-cycle run)

```
[1/10] overworld | RAM reader x6 | 3.9s   ← each cycle = 1 LLM call, ~1.5–4.5s
[WARN] Direction-locking detected: RIGHT x3   ← LLM repeats a direction; recovery rotates it
[RECOVER] Level 0: alternate_direction — rotated from RIGHT → DOWN
[10/10] overworld | RAM reader x6 | 2.6s
[dogfood_20260807_0015] Done. 13 actions. Screens: {'?', 'overworld'}
EXIT=0
```

Player actually moves (verified: (2,3) → (7,1), Pallet Town) with coherent intents ("Move north toward Route 1 and trigger Professor Oak...").

## The broken path — `src/game_loop.py` (DF-001, P0)

```bash
python3 src/game_loop.py --rom "data/rom/Pokemon - Blue Version (USA, Europe) (SGB Enhanced).gb" \
  --max-ticks 1000 --save-dir runs/test_001
```

What happens today (verified 15/15 ticks, 40-tick run):

1. Every tick: `GameLoop._analyze_game_state()` → `GameAIManager.analyze_screenshot()` → **real paid OpenRouter vision call (~3.5 s, ~$0.013)**.
2. Vision JSON returns `"player_hp": null` on non-battle screens → `log_vision_analysis()` (src/core/ai_client.py:115) formats `f"HP: {player_hp:.0f}%"` → **TypeError: unsupported format string passed to NoneType.__format__**.
3. `analyze_screenshot`'s except returns a fallback dict; game_loop falls back to stub state.
4. Result: `❌ Vision analysis failed: ...` printed every tick, **0 AI decisions ever**, ~3.2 s/tick (README claims "10000 ticks ~ 3 minutes at max speed" — at this rate it's ~9 h and ~$130 of thrown-away API calls).

Fix direction (task DF-001): coerce `None` HP to a default before formatting (`player_hp or 0`), add regression test with a null-HP vision payload, and/or skip the vision call when the previous screen type is known non-battle.

Also on this path (minor):
- Save file is `emulator_state.state.state` (double extension, DF-002) — `Emulator.save_state()` appends `.state` to whatever it's given.
- `--multi-instance` is a stub that raises `NotImplementedError` (documented in README as optional; don't use).

## Cost & resource expectations

- cron_runner: ~$0.013–0.018 per cycle (luna), 80 cycles ≈ $1.10–1.40, ~2.5 min wall. RSS flat ~110 MB (LEAK-001 fixed). Videos via `make_run_video.py` (fleet adds video + srt).
- game_loop.py today: ~$0.013/tick wasted on failing vision calls — do not run long sessions until DF-001 lands.

## Pitfalls

1. **Don't judge the project by `src/game_loop.py`** — the fleet's real benchmark is `cron_runner.py`.
2. The `UserWarning: Using SDL2 binaries from pysdl2-dll` on stderr is harmless.
3. Don't delete `data/frame_cache.json` — it's the persistent cache; safe to keep across runs.
4. `specs/AGENTS.md` is stray DexDat content (DF-004) — ignore it; use the root `AGENTS.md`.
5. API keys live in `.env` (`OPENROUTER_API_KEY`, `DEEPSEEK_API_KEY`). Never commit `.env`.
