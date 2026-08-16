# ai-plays-poke — Diagnostics Trail (dogfood 2026-08-07)

How the system is actually built, the errors hit during a real-use run, and the right way to do things. Written from a real use session, not from the test suite.

## How it's built (two parallel worlds)

The repo contains **two gameplay stacks** that evolved separately:

1. **`src/game_loop.py`** — the "official" user-facing stack per README/AGENTS.md. Classic architecture: `GameLoop` → `GameAIManager` (OpenRouter) → per-tick vision screenshot analysis → `SaveManager` (SQLite `game_data.db` in save-dir) → battle heuristics. This is the older, spec-driven design (chapters 1–10, GOAP, HSM...). **The AI loop here is broken (see below).**
2. **`cron_runner.py`** — the fleet's actual E2E stack (what the foreman's E2E-001 fixture runs every 5–10 ticks). Much leaner: PyBoy emulator + `RAMReader` (direct Game Boy memory reads — instant, free) instead of vision; one LLM call per cycle (`openai/gpt-5.6-luna` via `OpenRouterClient`); a 4-dimensional stuck detector (same-direction, same-screen, same-tile, A-press loops) with an escalating recovery ladder; persistent `FrameCache` (screenshot-hash → UUID) to skip duplicate frames; checkpoint slots 0–4; JSONL event log. **This works.**

The two stacks share `src/core/emulator.py` (`Emulator` wrapper around PyBoy with `fast_forward`/`render=False` batching — that batching was the GAMEPLAY-LEAK-001 fix) but have separate decision code. The E2E runs that appear in board events ("luna_v16 80/80, trainer battle c79, RSS 110MB flat") are all cron_runner.

## Errors hit during the dogfood run (and the right way)

### 1. `❌ Vision analysis failed: unsupported format string passed to NoneType.__format__` — EVERY tick (DF-001, P0)

Chain: `GameLoop._analyze_game_state` → `ai_manager.analyze_screenshot(screenshot)` → real OpenRouter vision call (~3.5 s, paid) → response JSON `{"screen_type": "overworld", "player_hp": null, "enemy_hp": null, ...}` → `log_vision_analysis()` at `src/core/ai_client.py:115`:

```python
f"HP: {player_hp:.0f}%/{enemy_hp:.0f}%"   # player_hp is None → TypeError
```

→ except swallows it, returns fallback dict → game_loop prints `✅ Vision analysis: overworld, HP(100%, 100%)` from the *stub*, and the tick's AI result is discarded. Observed: 15/15 ticks failed, 0 AI decisions in 40 ticks, 3.2 s/tick, ~$0.013/tick wasted.

**Right way:** never format `:.0f` on values parsed from LLM JSON without coercion. The fleet's own stack never hits this because it doesn't use per-tick vision. The lesson generalizes: JSON from an LLM is untrusted — every numeric field needs a `None`-safe default before use. Also: the vision call itself is redundant on non-battle screens; the fleet's RAM reader already classifies the screen for free.

**Why the foreman missed it:** GAP-001's pass criteria was "`game_loop --max-ticks 10` exits 0 with no traceback" — and it does! The crash is swallowed inside `analyze_screenshot`; the run exits 0 having done literally nothing. Exit-code-only verification is the "false success" pattern (see DF-005). This is exactly why the dogfood loop runs the thing and reads the *behavior*, not the exit code.

### 2. `emulator_state.state.state` — double extension (DF-002)

`GameLoop.stop()` computes `save_path = save_dir / "emulator_state.state"` then calls `emulator.save_state(str(save_path))`. But `Emulator.save_state(slot)` (src/core/emulator.py:341) is slot-based: `path = Path("checkpoints") / f"{slot}.state"`. Passing an absolute path string as `slot` makes the join resolve to the absolute path, then appends `.state` → `emulator_state.state.state` in the save-dir. **Right way:** one save API, one contract (either path-based `save_state(path)` or slot-based; don't mix). Minor, but it breaks the documented output structure and any tooling that globs `*.state`.

### 3. Bad ROM path — exit code is correct (checked twice!)

First measurement (`... | tail; echo $?`) reported exit 0 for a missing ROM. Re-measured without a pipe: **exit 1** ✅. The `if __name__ == "__main__": sys.exit(main())` at the bottom of game_loop.py does the right thing. Lesson for future dogfood runs: never take `$?` from a pipeline.

### 4. Harmless noise

- `UserWarning: Using SDL2 binaries from pysdl2-dll 2.32.10` on every invocation (stderr). Cosmetic.
- `[WARN] Direction-locking detected: UP x3` every 1–2 cycles in cron_runner: the LLM controller proposes the same direction 3×; the recovery ladder rotates it. Working as designed (fleet's standing observation; recovery bounded at level 0 in short runs).
- `specs/AGENTS.md` is **DexDat content** (another project entirely — "This repository is NOT: code implementation", TRUST-POL-01, crypto/email platform). Someone copied it in. Agents reading it get actively wrong instructions (DF-004).

## Performance facts (measured, Aug 2026 box)

- Emulator tick (render=False): ~0.000 s/tick. Boot: ~0.02 s. Rendering one frame: ~0.000 s. **The emulator is never the bottleneck.**
- cron_runner cycle: 1.5–4.5 s — dominated by the single LLM call. 80 cycles ≈ 2.5 min wall, ~$1.10–1.40, RSS flat ~110 MB.
- game_loop.py tick with broken vision: ~3.2 s/tick (paid call + swallowed crash). README's "10000 ticks ~ 3 minutes at max speed" was true for pure emulation, not for the real AI path.

## Right-way summary for future agents

1. **To play/benchmark:** `python3 cron_runner.py --run-id X --cycles N` (see `skills/ai-plays-poke-usage/SKILL.md`).
2. **To verify a fix on the game_loop path:** run ≥ 40 ticks and require (a) zero `Vision analysis failed` lines, (b) `AI Decisions > 0` in the final stats, (c) per-tick time < 1 s. Exit code alone proves nothing.
3. **Never format LLM-JSON numerics with `:.0f`/`:.1f` unguarded.**
4. **Check both stacks** when touching gameplay: a change to `src/core/emulator.py` affects cron_runner; a change to `ai_client.py` affects game_loop.
5. Board is DuckDB parquet (`.coding-hermes/board/`) — tasks.parquet + events.parquet; append rows with pandas, keep dtypes (datetime64[us], int8 complexity, float64 attempts).

---

# 2026-08-16 follow-up — what changed, what didn't, and the mechanisms

Second dogfood run, 9 days after the first. Re-verified every DF/AP-GAP claim
with fresh real-use runs (20-cycle cron_runner E2E, 40-tick game_loop,
ram_map_server boot, three CLI --help probes). Full evidence:
`docs/dogfood/2026-08-16-integration.md`.

## What got fixed (verified, all real runs)

- **DF-001 crash → fixed.** 40 ticks of game_loop: zero `Vision analysis
  failed`, 40/40 real OpenRouter vision calls succeed (~$0.005 each). The
  None-HP format guard landed. Also GAP-001's exit crash and DF-002's
  `.state.state` double extension are gone (`emulator_state.state` + clean
  `session_1_export.json`).
- **AP-GAP-015/016/017 → fixed.** ptp_cli, debug_screen, memory_reader all
  answer `--help` with exit 0 instantly (no emulator boot).
- **cron_runner is now genuinely excellent**: 20/20 cycles, 9 unique
  coordinates, Pallet Town → Oak's Lab (map 0→40), 2 recovery events, and the
  **starter milestone** (`[STARTER-PICKED] party_count=1
  species_hint=Charmander` at cycle 18) — the GAMEPLAY-STARTER-001
  RAM-verified party-count branch works live.

## What the board claimed was fixed but L3 says otherwise (the point of this run)

### 1. AP-GAP-001 "verified working" did not reproduce (→ GAP-020, P1)

Mechanism, traced from source + run output:

- game_loop boots the ROM and ticks 60 frames/iteration. The Gen-1 Pokémon
  Blue title screen needs a START press to get to the copyright screen, then
  another to the main menu.
- The boot-progression hack (`game_loop.py:268-282`) presses START exactly
  once, at tick 16, only `if ai_decisions == 0 and not pending_commands` —
  and never verifies the screen changed. One START on the title screen is not
  enough; the vision classifier then sees "title screen" for the remaining
  ticks and its `recommended_action` ("press:A") is **logged but never queued
  as a command** (Commands Sent: 0, AI Decisions: 0).
- The foreman's T101 acceptance saw "4 AI decisions (menu navigation)" — so
  the boot sometimes gets further (run variance), which is exactly why
  exit-code/one-run acceptance is not enough. The correct pass criterion is
  screen-type progression + ≥1 button press, not "AI decisions > 0".

Lesson: a P0 task closed as "verified working" with a single criterion run is
the premature-completion pattern again. The L3 check (does a user get
gameplay?) was never performed.

### 2. Fabricated battle records (→ GAP-021, P1)

The 40-tick title-screen run wrote 2 `battles` rows with `status='victory'`
("unknown (dark silhouette)", "unidentified (sprite unclear)") and final
stats `Battles: 2, Wins: 2`. The battle detector fires on screen transitions
without requiring battle evidence (RAM screen type or a real sprite), and the
"victory" default is applied to unidentified opponents. Any benchmark built
on game_loop metrics is polluted by these phantom wins.

### 3. Telemetry lies about the AI mode (→ GAP-022, P2)

`game_loop.py:802` hardcodes `"model_name": "stub_ai"` ("Will be replaced
with real AI" — never replaced). Every session row says stub AI while real
vision calls run. DB consumers get wrong model attribution.

### 4. Docs/skill drift (→ GAP-023, P2)

README:193-196 and the usage SKILL.md still say game_loop's vision pipeline
is "under repair / broken (DF-001)". The crash IS fixed — the docs are now
stale in the opposite direction. The only place with accurate status was the
board; docs must track it.

### 5. Map viewer boots to name_entry (→ GAP-024, P2)

`ram_map_server.py` boots the emulator and serves a perfect JSON schema
(200/200/404, all fields), but the boot sequence landed at
`screen_type=name_entry` (Red's House 2F, map 38) — not overworld as
usability-tests.md claims — and there is no input endpoint (`do_GET` only),
so the viewer can never progress past pre-game. The name-entry screen is a
state the intro-skip can't handle, and the viewer has no way to type a name.

## The right way (updated)

1. **To play/benchmark:** `python3 cron_runner.py --run-id X --cycles N`
   (20 cycles ≈ 4 min, ~$0.16–0.30; JSONL events incl. starter milestone).
2. **To verify game_loop fixes:** fresh save-dir, 40 ticks, require
   `Commands Sent >= 1`, non-title vision responses, `Battles: 0, Wins: 0`
   on non-battle runs, and real `model_name` in the session row. Exit 0 and
   "no crash" prove nothing (see GAP-020/021/022).
3. **Boot progression on Gen 1:** title screen needs START → copyright →
   START → menu. Press once, verify via RAM/vision, press again. Never rely
   on a single unconditional press.
4. **Vision `recommended_action` must become a command** — logging the LLM's
   suggested button without executing it produces "AI analyzed but never
   played" runs.
5. **Battle records need battle evidence** — no sprite identified, no battle.
   A "victory" against "unknown (dark silhouette)" is data fabrication.
6. **Cost note:** game_loop vision is ~$0.005/tick and burns it even stuck on
   the title screen; cron_runner is ~$0.016/cycle with real progress.
