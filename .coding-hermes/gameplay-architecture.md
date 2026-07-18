# Gameplay Architecture: RAM-Reader-Driven Controller Pipeline

> **Status:** Design document — guides implementation of PROMPT-COMPACT, HSM-WIRE, STUCK-RECOVER, BATTLE-AGENT, and subsequent tasks.
> **Date:** 2026-07-18
> **Author:** Foreman (deepseek-v4-flash / coding-hermes-foreman)

---

## Executive Summary

The current system boots, reads RAM perfectly, and classifies screens correctly — but the gameplay controller does not produce reliable autonomous play. The root cause is architectural: **three separate flow paths** (RAM-reader overworld controller, vision-based cartographer, StateWindow LLM loops) operate independently with no unified state machine, no controller memory window, and ad-hoc recovery. This document defines a unified architecture where:

1. The **HSM** (69 states, 105 tests, existing) becomes the single source of truth for game state
2. The **RAM reader** provides instant, hallucination-free state observations  
3. The **controller** operates on compact RAM-derived prompts (~50 tokens vs ~500)
4. **Recovery** is a first-class state within the HSM, not ad-hoc variable tracking
5. **DuckBrain** injects cross-session memory into every decision

---

## 1. Data Flow Architecture

```
┌────────────────────────────────────────────────────────────────────────┐
│                         cron_runner.py main()                          │
│                                                                        │
│  ┌──────────────┐    ┌──────────────────┐    ┌────────────────────┐   │
│  │  Emulator     │───▶│   RAMReader       │───▶│   observe() output │   │
│  │  (pygba/mGBA) │    │  .observe()       │    │   {                │   │
│  └──────────────┘    └──────────────────┘    │     result: str,    │   │
│                                              │     coords: (x,y),  │   │
│  ┌──────────────┐    ┌──────────────────┐    │     adjacent: {},   │   │
│  │  HSM          │◀───│   StateRouter     │    │     map_id: int,   │   │
│  │  69 states    │    │  (new)            │    │     battle: {},    │   │
│  │  105 tests    │    │  maps observe()   │    │     text: [],     │   │
│  └──────────────┘    │  → HSM state       │    │     menu: []      │   │
│                      │  → prompt template  │    │   }               │   │
│                      └───────┬────────────┘    └────────────────────┘   │
│                              │                                          │
│                              ▼                                          │
│              ┌──────────────────────────────┐                           │
│              │   Controller (per-state)      │                           │
│              │   - overworld: DeepSeek V4    │                           │
│              │   - battle: DeepSeek V4       │                           │
│              │   - dialog: skip (auto-A)     │                           │
│              │   - name_entry: programmatic  │                           │
│              │   - menu: DeepSeek V4         │                           │
│              └──────────────┬───────────────┘                           │
│                             │ button plan                                │
│                             ▼                                          │
│              ┌──────────────────────────────┐                           │
│              │   PlanExecutor + Recovery     │                          │
│              │   (direction blacklist,       │                          │
│              │    spatial filter, RLE cap,   │                          │
│              │    checkpoint rollback)       │                          │
│              └──────────────────────────────┘                           │
│                                                                        │
│  ┌──────────────┐    ┌──────────────────┐                              │
│  │  DuckBrain    │◀───│   Foreman writes  │                             │
│  │  namespace    │    │   /play_sessions/ │                             │
│  │  /project/    │    │   arch decisions  │                             │
│  │  ai_plays_    │    └──────────────────┘                              │
│  │  poke/        │                                                      │
│  └──────────────┘                                                      │
└────────────────────────────────────────────────────────────────────────┘
```

## 2. State Data Flow to Controller

### 2.1 RAM Reader Output (instant, <1ms, zero tokens)

The RAM reader (`src/core/ram_reader.py`) reads 60+ WRAM addresses from the emulator. Its `observe()` method produces:

```json
{
  "result": "overworld",                    // Screen classification
  "coords": {"x": 3, "y": 4},              // Player tile position
  "map_id": 0,                              // Current map ID
  "player_facing": "down",                  // Direction player faces
  "adjacent": {"up": "floor", "down": "grass", "left": "wall", "right": "floor"},
  "map_name": "Pallet Town",                // From map header
  "text_content": [],                        // Dialog text buffer
  "menu_items": [],                          // Menu cursor items
  "battle": {                                // Only when wIsInBattle != 0
    "is_battle": true,
    "player_hp": 85,
    "player_max_hp": 85,
    "enemy_name": "Rattata",
    "enemy_hp": "?",
    "enemy_max_hp": 30,
    "player_moves": [{"name": "Tackle", "pp": 35, "max_pp": 35}, ...]
  },
  "text_box_active": false,
  "menu_cursor_position": 0
}
```

### 2.2 Compact Prompt for Controller (~50 tokens vs ~500)

The RAM reader gives us **structured, deterministic data** — no hallucination, no vision latency, no token waste. The controller prompt compresses to:

```
You are at (3,4) on Pallet Town. Adjacent: up=floor, down=grass, left=wall, right=floor. Facing down.
GOAL: leave bedroom, reach rival battle
Recent: pressed DOWN → moved to (3,4), pressed DOWN → moved to (3,5)
Last action: moved to (3,5). Result: moved.
What direction?
```

This is ~50 tokens — 10× cheaper and faster than the cartographer's spatial description (~500 tokens).

### 2.3 Controller Output

The controller outputs a **movement plan** as JSON:

```json
{"plan": ["DOWN", "DOWN", "LEFT"], "intent": "walk to stairs"}
```

For battle:

```json
{"action": "FIGHT", "move": 1, "intent": "attack with Tackle"}
```

For menu:

```json
{"action": "SELECT", "item": 3, "intent": "use Potion on Pikachu"}
```

For dialog (auto-A):

```
No output needed — non-interactive dialogs are handled automatically.
```

---

## 3. Unified State Machine Integration (HSM as Single Source of Truth)

### 3.1 Current State (Problem)

Three separate screen classification mechanisms:

| Mechanism | Location | Type | Used For |
|-----------|----------|------|----------|
| RAM reader `observe().result` | `cron_runner.py` | RAM-based | Routing to overworld vs StateWindow |
| HSM 69 states | `state_machine.py` | Code-based | Not wired at all (ignored!) |
| StateWindow `screen_type` | `state_window.py` | Vision-based | Internal state window routing |

**These three disagree.** The RAM reader says "overworld," the HSM is in "BOOT.INITIALIZE" (never moved), and StateWindow redetects from vision.

### 3.2 Target Architecture

```
observe() ──▶ StateRouter ──▶ HSM.transition() ──▶ Controller
                │                                     │
                │ Creates StateWindow if needed        │
                │ (dialog, battle, menu)               │
                │ Otherwise: overworld controller       │
```

**StateRouter** (new module, `src/core/state_router.py`) maps RAM reader output to HSM transitions:

```python
class StateRouter:
    def __init__(self, emulator, ram_reader, hsm, ctx):
        self.emulator = emulator
        self.ram_reader = ram_reader
        self.hsm = hsm
        self.ctx = ctx
    
    def route(self) -> RouteResult:
        """Given RAM observation, determine game state and return controller params."""
        obs = self.ram_reader.observe()
        screen_type = obs["result"]
        
        # Map screen_type to HSM state
        screen_to_hsm = {
            "overworld": "OVERWORLD.IDLE",
            "battle": "BATTLE.BATTLE_MENU",
            "menu": "MENU.MAIN_MENU",
            "dialog": "DIALOG.TEXT_DISPLAY",
            "name_entry": "BOOT.CHARACTER_NAMING",
            "title": "TITLE.WAITING_FOR_START",
        }
        target_state = screen_to_hsm.get(screen_type, "OVERWORLD.IDLE")
        self.hsm.transition_to(target_state, reason=f"RAM observed {screen_type}")
        
        # Select prompt template based on HSM state
        if screen_type == "overworld":
            return RouteResult(
                controller="overworld_controller",
                prompt_template="gen1/overworld_ram.yaml",
                interactive=True,
            )
        elif screen_type == "battle":
            return RouteResult(
                controller="battle_controller",
                prompt_template="gen1/battle_ram.yaml",
                interactive=True,
            )
        elif screen_type in ("dialog", "title", "cutscene"):
            # Non-interactive — auto-A press, no LLM
            return RouteResult(
                controller="auto_a",
                prompt_template=None,
                interactive=False,
            )
        elif screen_type == "name_entry":
            return RouteResult(
                controller="programmatic_name_entry",
                prompt_template=None,
                interactive=True,
            )
        elif screen_type in ("menu", "yes_no"):
            return RouteResult(
                controller="menu_controller",
                prompt_template="gen1/menu_ram.yaml",
                interactive=True,
            )
        else:
            return RouteResult(
                controller="fallback",
                prompt_template="gen1/fallback.yaml",
                interactive=True,
            )
```

### 3.3 Prompt Template Selection by HSM State

The HSM's current state dictates which prompt template to load:

| HSM State | Prompt Template | Controller Model | Token Budget |
|-----------|----------------|------------------|-------------|
| `OVERWORLD.IDLE` | `gen1/overworld_ram.yaml` | DeepSeek V4 Flash | 200 total |
| `OVERWORLD.WALKING` | `gen1/overworld_ram.yaml` | DeepSeek V4 Flash | 200 total |
| `BATTLE.BATTLE_MENU` | `gen1/battle_ram.yaml` | DeepSeek V4 Flash | 300 total |
| `BATTLE.MOVE_SELECTION` | `gen1/battle_ram.yaml` | DeepSeek V4 Flash | 200 total |
| `DIALOG.TEXT_DISPLAY` | (auto-A, no LLM) | None | 0 |
| `DIALOG.CHOICE_MENU` | `gen1/dialog_choice.yaml` | DeepSeek V4 Flash | 150 total |
| `MENU.MAIN_MENU` | `gen1/menu_ram.yaml` | DeepSeek V4 Flash | 200 total |
| `MENU.POKEMON_MENU` | `gen1/pokemon_menu.yaml` | DeepSeek V4 Flash | 200 total |
| `BOOT.CHARACTER_NAMING` | (programmatic) | None | 0 |
| `EMERGENCY.SOFTLOCK_DETECTED` | `gen1/emergency.yaml` | DeepSeek V4 Flash | 300 total |
| `EMERGENCY.ERROR_RECOVERY` | `gen1/emergency.yaml` | DeepSeek V4 Flash | 300 total |

### 3.4 Removing Duplicate Screen Classification

The `StateWindow.__init__` currently takes `vision: dict` and infers screen type from it. Under the new architecture:

- **StateWindow receives the HSM state directly**, not raw vision output
- The `_build_prompt` method no longer needs screen-type detection logic — it loads the prompt template that matches the HSM state
- `_check_outcome()` can call `ram_reader.observe()` instead of a vision model to detect state transitions

Removal scope in `state_window.py`:
- `screen_type` / `screen_subtype` inference from vision dict → deleted
- `_is_interactive()` → simplified to check HSM state type
- `_check_outcome()` → use RAM reader instead of vision_client

---

## 4. Controller Memory Window

### 4.1 Current (Broken)

The controller has no memory between cycles. It presses DOWN 5+ times because it doesn't know it already pressed DOWN. Recovery is reactive (detect locking → load checkpoint) instead of preventative (see last action failed → don't repeat).

### 4.2 Target: Sliding Window of Last 5 Actions

A small sliding window in `GlobalContext` tracks the last 5 actions + outcomes:

```python
# In GlobalContext
self.action_history: list[dict] = []  # max 5 entries

def record_action(self, button: str, result: str, position: tuple[int, int]):
    """Record a single button press and its outcome."""
    self.action_history.append({
        "button": button,
        "result": result,  # "moved", "blocked", "interacted", "dialog_advanced"
        "position": position,
        "timestamp": time.time(),
    })
    if len(self.action_history) > 5:
        self.action_history.pop(0)

def compact_actions(self) -> str:
    """Return compact action history string."""
    if not self.action_history:
        return ""
    lines = ["Recent actions:"]
    for a in self.action_history[-5:]:
        lines.append(f"  {a['button']} → {a['result']}")
    return "\n".join(lines)
```

### 4.3 Prompt Injection

The controller prompt includes:

```
You are at (3,4) on Pallet Town. Adjacent: up=floor, down=grass, left=wall, right=floor. Facing down.
GOAL: leave bedroom.
Recent: pressed DOWN → moved to (3,5), pressed DOWN → blocked by wall, pressed LEFT → moved to (3,4)
⚠️ 3 consecutive DOWN presses failed. That direction is blocked.
What direction?
```

This directly prevents the direction-locking failure mode.

---

## 5. Recovery Architecture

### 5.1 Recovery as an HSM State (Not Ad-Hoc Variables)

Currently three independent tracking variables exist:

| Variable | Purpose | Recovery Action |
|----------|---------|-----------------|
| `_same_dir_count` | Direction locking | Checkpoint rollback |
| `_void_cycles` | Void state | Menu redraw |
| `_stuck_cycles` | Same screen stuck | Breakout B press |

**Problem:** These don't compose. A void state with direction-locking triggers two separate recovery paths. Escalation is ad-hoc.

**Target:** Recovery state within HSM:

```
OVERWORLD.IDLE
    → OVERWORLD.WALKING (player moves)
    → EMERGENCY.SOFTLOCK_DETECTED (no state change for N cycles)
        → EMERGENCY.ERROR_RECOVERY (try alternate direction)
            → OVERWORLD.IDLE (recovery worked)
            → EMERGENCY.ERROR_RECOVERY (try START+B+B)  
                → OVERWORLD.IDLE (recovery worked)
                → EMERGENCY.ERROR_RECOVERY (load checkpoint)
                    → OVERWORLD.IDLE (recovery worked)
                    → EMERGENCY.EMERGENCY_SHUTDOWN (max retries exhausted)
```

### 5.2 Escalation Ladder

| Level | Trigger | Action | HSM State |
|-------|---------|--------|-----------|
| 1 | 3 consecutive same-direction | Log warning | OVERWORLD.IDLE (no state change) |
| 2 | 5 consecutive same-direction + no position change | Alternate direction (rotation) | OVERWORLD.IDLE |
| 3 | 3+ alternate directions attempted | START+B+B (close menu, force redraw) | EMERGENCY.SOFTLOCK_DETECTED |
| 4 | START+B+B didn't fix it | Load checkpoint | EMERGENCY.ERROR_RECOVERY |
| 5 | Checkpoint load failed 3x | Soft reset (START+SELECT+A+B) | EMERGENCY.ERROR_RECOVERY |
| 6 | All recovery exhausted | Halt ticks, log "GAME OVER" | EMERGENCY.EMERGENCY_SHUTDOWN |

### 5.3 Recovery Counter Reset

Recovery counters reset when:
- Player position changes (successful movement, any direction)
- Screen type changes (dialog→overworld, overworld→battle, etc.)
- Any HSM state transition occurs (natural state change)

### 5.4 Void Detection

Detected via RAM reader: if `_walk_counter` stays 0 and map tiles show all `?` for 3+ cycles.

```python
def _detect_void(obs: dict) -> bool:
    """Check if the player is in a glitched/void map."""
    return (
        obs.get("walk_counter", 1) == 0  # Not walking
        and obs.get("result") == "overworld"  # "overworld" but nothing changes
    )
```

### 5.5 Battle Stuck Detection

Detected via RAM reader: if `wIsInBattle` is non-zero but no HP changes in 10+ frames, the battle AI may be in an infinite loop. Trigger: force switch to START → RUN → A sequence.

---

## 6. DuckBrain Context Integration

### 6.1 Before Each Controller Decision

The controller prompt includes DuckBrain context:

```python
def _get_duckbrain_context(ram_reader, map_id: int) -> str:
    """Load past decisions for current map."""
    results = duckbrain_recall(
        query=f"/discoveries/map_{map_id}/"
    )
    if not results:
        return ""
    return f"MAP KNOWLEDGE: {results[:200]}"
```

**Injected into prompt:**
```
You are at (3,4) on Pallet Town.
MAP KNOWLEDGE: Right side near lab has a wall. Walk LEFT to exit house.
Recent: pressed LEFT → moved to (3,3)
What direction?
```

### 6.2 After Each Run

After each cron tick, the foreman writes to DuckBrain:

```
/project/ai_plays_poke/decisions/map_0/2026-07-18
  {success_rate: 0.8, stuck_directions: ["down", "right"], discoveries: [...]}

/project/ai_plays_poke/performance/latest_run
  {cycles: 200, overworld_pct: 0.45, dialog_pct: 0.30, battle_pct: 0.10, ...}
```

### 6.3 Goals Injected from DuckBrain

The `GlobalContext.add_goal()` system maps to DuckBrain:

```python
# On reaching overworld:
duckbrain_recall("/goals/generated/") → ["leave bedroom", "reach rival battle"]
```

---

## 7. Implementation Phases

### Phase A: HSM Wiring (HSM-WIRE)
**Files:** `src/core/state_router.py` (new), `cron_runner.py`, `src/core/state_window.py`
- Create `StateRouter` that maps RAM reader output → HSM state → prompt template
- Wire HSM into cron_runner main loop
- Remove duplicate screen classification from state_window.py
- Verify 105 HSM tests + existing state_window tests pass

### Phase B: Compact Prompts (PROMPT-COMPACT)
**Files:** `configs/prompts/gen1/overworld_ram.yaml` (new), `src/core/state_window.py`
- Create `overworld_ram.yaml` using RAM data instead of spatial descriptions
- Update `StateWindow._build_prompt` to detect USE_RAM_READER and use compact prompts
- Target: overworld prompt < 100 tokens

### Phase C: Memory Window (CONTROLLER-CONTEXT)
**Files:** `src/core/global_context.py`, `cron_runner.py`
- Add action history sliding window (max 5)
- Inject into controller prompts
- Track outcomes (moved, blocked, interacted)

### Phase D: Unified Recovery (STUCK-RECOVER)
**Files:** `cron_runner.py`, `src/core/state_machine.py`
- Add EMERGENCY states to HSM
- Route recovery through HSM state machine
- Keep existing escalation ladder

### Phase E: Battle Agent (BATTLE-AGENT)
**Files:** `configs/prompts/gen1/battle_ram.yaml` (new), `cron_runner.py`
- Create battle prompt using RAM reader battle data
- Wire FIGHT/MOVE/BAG/PKMN/RUN into controller logic

### Phase F: DuckBrain Persistence (DUCKBRAIN-CONTEXT)
**Files:** `cron_runner.py`
- Add pre-decision DuckBrain recall
- Add post-run DuckBrain remember
- Wire into foreman's Step 10 write path

---

## 8. Token Budget

| Component | Current (tokens) | Target (tokens) | Savings |
|-----------|-----------------|-----------------|---------|
| System prompt | 400 | 400 | — |
| Spatial description | 500 | 50 | 10× |
| Action history | 0 | 100 | (new) |
| DuckBrain context | 0 | 200 | (new) |
| **Total controller** | ~900 | ~750 | ~17% |
| StateWindow (dialog) | ~500 | ~300 | ~40% |
| StateWindow (name entry) | ~800 | ~200 (programmatic) | ~75% |

---

## 9. Key Architectural Decisions

| Decision | Rationale | Rejected Alternatives |
|----------|-----------|----------------------|
| RAM reader as single source of truth | Instant, deterministic, no hallucinations | Vision cartographer (1-60s latency, $/call, hallucinates walls) |
| HSM owned by StateRouter | Single transition authority; all recovery goes through HSM | Ad-hoc recovery variables (don't compose, missable) |
| Controller outputs plans, not single buttons | Fewer LLM calls (1 call per 3-12 actions vs per action) | Single button per cycle (6× cost, more stub decisions) |
| Non-interactive dialog = no LLM | Saves 50-80% of dialog cycles | Sending every text box to LLM (costly, no value) |
| Action history in GlobalContext | Crosses StateWindow boundaries (battle→overworld) | Local variable in cron_runner (lost on StateWindow call) |

---

## 10. Success Criteria

1. **Intro bypass**: < 15 checks to reach overworld (currently ~12, target <15)
2. **Overworld navigation**: 80%+ of actions result in position change (not blocked)
3. **Battle handling**: Controller detects battle via RAM and outputs valid FIGHT/RUN within 3 cycles
4. **Recovery**: Escalating recovery works without manual intervention
5. **Performance**: < 50 controller tokens per decision (was ~500)
6. **Cost**: 70% reduction in API costs from cartographer elimination
7. **Tests**: All 3000+ existing tests pass, no regression
