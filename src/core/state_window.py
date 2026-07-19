"""
State Window — focused sub-agent for a specific game state type.

Each state window gets:
- A compacted view of the global context
- A state-specific mermaid workflow (loaded from configs/states/)
- Emulator tool definitions
- A query_global tool to ask for missing global details

The state window runs a focused decision loop until the state
is resolved (e.g., name entered, dialog advanced, battle won).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from src.core.ai_client import OpenRouterClient
from src.core.global_context import GlobalContext
from src.core.state_machine import (
    HierarchicalStateMachine,
    create_hierarchical_state_machine,
)
from src.core.tools import TOOL_SCHEMA, execute_tool_call
import subprocess
import os
import logging

logger = logging.getLogger(__name__)

# ── DuckBrain CLI wrapper ──────────────────────────────────────────────────

_DUCKBRAIN_CLI = os.path.expanduser("~/duckbrain/bin/duckbrain.js")

def _duckbrain_remember(key: str, fact: str, namespace: str = "pokemon-global") -> str:
    """Store a discovery via DuckBrain CLI."""
    result = subprocess.run(
        ["node", _DUCKBRAIN_CLI, "remember", key,
         "--domain=concept",
         f"--attr={json.dumps({'source': 'agent', 'fact': fact})}",
         f"--namespace={namespace}"],
        capture_output=True, text=True, timeout=10,
        cwd=os.path.expanduser("~/duckbrain"),
    )
    return result.stdout.strip() or result.stderr.strip()

def _duckbrain_recall(query: str, namespace: str = "pokemon-global") -> str:
    """Query memories via DuckBrain CLI."""
    result = subprocess.run(
        ["node", _DUCKBRAIN_CLI, "recall",
         f"--prefix={query}",
         f"--namespace={namespace}"],
        capture_output=True, text=True, timeout=10,
        cwd=os.path.expanduser("~/duckbrain"),
    )
    return result.stdout.strip() or "nothing found"

# ── DuckBrain tools (added to every state window) ──────────────────────────

_DUCKBRAIN_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "remember",
            "description": (
                "Store a discovery or important fact for future runs. "
                "Use this when you learn something about the game — "
                "type advantages, item locations, NPC behaviors, strategies. "
                "This persists across game sessions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "Hierarchical key, e.g. /discoveries/types or /goals/current",
                    },
                    "fact": {
                        "type": "string",
                        "description": "The discovery or fact to remember.",
                    },
                },
                "required": ["key", "fact"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recall",
            "description": (
                "Recall past discoveries. Use before making decisions — "
                "check if you've learned something relevant."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Key prefix to search, e.g. /discoveries/ or /goals/",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_goal",
            "description": (
                "Set a goal for yourself. Goals guide your exploration. "
                "Examples: 'leave the bedroom', 'find Professor Oak', "
                "'catch a wild Pokémon', 'reach the next town'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "goal": {
                        "type": "string",
                        "description": "The goal to pursue.",
                    },
                },
                "required": ["goal"],
            },
        },
    },
]

# ── Query global tool (added to every state window) ───────────────────────

_QUERY_GLOBAL_TOOL = {
    "type": "function",
    "function": {
        "name": "query_global",
        "description": (
            "Ask the global context a question. Use when you need details "
            "that weren't provided in your compacted context — e.g. 'What "
            "is my current objective?', 'What Pokémon are in my party?', "
            "'Did I already beat this trainer?'"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The question to ask global context.",
                },
            },
            "required": ["question"],
        },
    },
}

# ── State workflow loading ───────────────────────────────────────────────

_STATES_DIR = Path("configs/states")


def _load_state_workflow(state_type: str, generation: str = "gen1") -> str:
    """Load the mermaid workflow for a state type."""
    # Try gen-specific first, then generic
    for path in (
        _STATES_DIR / generation / f"{state_type}.yaml",
        _STATES_DIR / f"{state_type}.yaml",
    ):
        if path.exists():
            with open(path, "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
            return data.get("workflow", "") if isinstance(data, dict) else ""
    return ""


# ── State window runner ──────────────────────────────────────────────────


class StateWindow:
    """Focused decision loop for a single game state type.

    Usage::

        ctx = GlobalContext(...)
        win = StateWindow(state_type="name_entry", global_ctx=ctx,
                          emulator=emu, vision=vision_output)
        result = win.run()
        # result = {"outcome": "name_selected", "name": "ASH"}
    """

    def __init__(
        self,
        state_type: str,
        global_ctx: GlobalContext,
        emulator: Any,
        vision: dict[str, Any],
        *,
        generation: str = "gen1",
        thinking_model: str = "deepseek-v4-flash",
        max_steps: int = 15,
        hint_level: int = 0,
        vision_client: Any = None,
        use_ram_prompts: bool = False,
        hsm: HierarchicalStateMachine | None = None,
    ) -> None:
        self.state_type = state_type
        self.global_ctx = global_ctx
        self.emulator = emulator
        self.vision = vision
        self.generation = generation
        self.thinking_model = thinking_model
        self.max_steps = max_steps
        self.hint_level = hint_level
        self.vision_client = vision_client
        self.use_ram_prompts = use_ram_prompts

        self.client = OpenRouterClient()
        self._step_count = 0
        self._history: list[dict[str, Any]] = []
        self._raw_responses: list[str] = []  # raw LLM text per step

        # ── HSM integration ───────────────────────────────────────────
        if hsm is not None:
            self.hsm = hsm
        else:
            self.hsm = create_hierarchical_state_machine()

        # Register transition callback for DuckBrain logging
        self.hsm.register_transition_callback(self._log_hsm_transition)

        # Map initial vision data to HSM state
        initial_hsm_state = self._map_vision_to_hsm_state()
        if initial_hsm_state and initial_hsm_state != self.hsm.get_current_state_name():
            # Only attempt if it's a valid transition; otherwise just note the mismatch
            if self.hsm.can_transition(self.hsm.get_current_state_name(), initial_hsm_state):
                self.hsm.transition_to(initial_hsm_state, reason="StateWindow init")
            else:
                logger.debug(
                    "Init: cannot transition %s → %s (invalid path). "
                    "HSM stays at %s; vision maps to %s.",
                    self.hsm.get_current_state_name(),
                    initial_hsm_state,
                    self.hsm.get_current_state_name(),
                    initial_hsm_state,
                )

        # ── Battle tracking ──────────────────────────────────────────
        self._in_battle = (self.state_type == "battle")
        self._battle_events: list[dict[str, Any]] = []
        if self._in_battle:
            self._battle_events.append({
                "event": "battle_start",
                "screen_type": self.vision.get("screen_type", ""),
            })

        # Save initial HSM state for outcome detection
        self._initial_hsm_state = self.hsm.get_current_state_name()

        # Load state workflow
        self._workflow = _load_state_workflow(state_type, generation)

        # Load core + hint system prompt
        from src.core.prompt_loader import load_system_prompt
        self._system_prompt = load_system_prompt(hint_level=hint_level)

    # ── Public API ────────────────────────────────────────────────────

    def run(self) -> dict[str, Any]:
        """Run the focused state loop until resolved or max_steps reached.

        Returns a result dict with 'outcome' and relevant data.
        """
        _auto_a_count = 0  # consecutive auto-A presses (safety cap)
        _MAX_AUTO_A = 20   # fall back to AI deliberation after this many

        for _ in range(self.max_steps):
            self._step_count += 1

            # ── Fast-forward shortcut for non-interactive dialog ─────
            if self.state_type == "dialog" and not self._is_interactive():
                if _auto_a_count < _MAX_AUTO_A:
                    self.emulator.press_button("a", frames=30)
                    self.emulator.wait(10)   # let game register
                    self.emulator.fast_forward(120)
                    self._history.append({
                        "step": self._step_count,
                        "tool_call": {"name": "press_button", "arguments": {"button": "a", "duration": 30, "fast_forward": 120}},
                        "action": "auto_a",
                        "auto": True,
                    })
                    _auto_a_count += 1
                    continue
                else:
                    # Safety cap: fall back to AI deliberation
                    pass
            elif self.state_type == "name_entry":
                self.emulator.press_button("a", frames=30)
                self.emulator.wait(10)
                self.emulator.fast_forward(120)
                self._history.append({"step":self._step_count,"tool_call":{"name":"press_button","arguments":{"button":"a","duration":30,"fast_forward":120}},"action":"name_entry_a_mash"})
                _auto_a_count += 1
                continue

                # ── Programmatic name entry keyboard navigation ────
                # DeepSeek ignores keyboard_grid instructions, so we
                # compute the correct button press here directly.
                kg = self.vision.get("keyboard_grid", {})
                if kg:
                    rows = kg.get("rows", [])
                    cursor = kg.get("current_cursor", {"row": 0, "col": 0})
                    cr, cc = cursor.get("row", 0), cursor.get("col", 0)
                    name_field = self.vision.get("name_field", "")
                    target_name = "ASH"

                    # Determine what to do
                    if name_field and len(name_field) >= len(target_name):
                        # All letters typed — navigate to END
                        button, dur = "down", 10
                    elif name_field:
                        # Find next letter
                        next_letter = target_name[len(name_field)]
                        tr, tc = -1, -1
                        for ri, row in enumerate(rows):
                            for ci, letter in enumerate(row):
                                if letter.upper() == next_letter.upper():
                                    tr, tc = ri, ci
                                    break
                            if tr >= 0:
                                break
                        if tr >= 0:
                            if tr == cr and tc == cc:
                                button, dur = "a", 30
                            elif tr > cr:
                                button, dur = "down", 10
                            elif tr < cr:
                                button, dur = "up", 10
                            elif tc > cc:
                                button, dur = "right", 10
                            elif tc < cc:
                                button, dur = "left", 10
                            else:
                                button, dur = "a", 30
                        else:
                            button, dur = "down", 10
                    else:
                        # Nothing typed yet — cursor should be on A, press it
                        button, dur = "a", 30

                    self.emulator.press_button(button, frames=dur)
                    self.emulator.wait(10)
                    self._history.append({
                        "step": self._step_count,
                        "tool_call": {"name": "press_button", "arguments": {"button": button, "duration": dur}},
                        "action": f"name_entry_auto_{button}",
                    })
                    continue
                # No keyboard_grid — fall through to LLM
            else:
                _auto_a_count = 0  # reset on interactive or non-dialog states

            # Build the focused prompt
            prompt = self._build_prompt()

            # Get action from thinking model
            response = self.client.send_tool_request(
                prompt=prompt,
                tools=TOOL_SCHEMA + _DUCKBRAIN_TOOLS + [_QUERY_GLOBAL_TOOL],
                model=self.thinking_model,
                max_tokens=2000,
                temperature=0.3,
            )

            self._raw_responses.append(response or "")

            # Parse tool call
            from src.core.tools import parse_tool_call

            tool_call = parse_tool_call(response) if response else None
            if tool_call is None:
                tool_call = {
                    "name": "press_button",
                    "arguments": {"button": "a", "duration": 5},
                }
            # Normalize arguments to dict
            if isinstance(tool_call.get("arguments"), str):
                try:
                    tool_call["arguments"] = json.loads(tool_call["arguments"])
                except (json.JSONDecodeError, TypeError):
                    tool_call["arguments"] = {"raw": tool_call["arguments"]}

            # Handle query_global calls
            if tool_call["name"] == "query_global":
                question = tool_call.get("arguments", {}).get("question", "")
                answer = self._answer_global_query(question)
                self._history.append({"role": "query_global", "question": question, "answer": answer})
                continue  # re-loop with answer in history

            # Handle DuckBrain calls (no emulator action)
            if tool_call["name"] == "remember":
                key = tool_call.get("arguments", {}).get("key", "/discoveries/unknown")
                fact = tool_call.get("arguments", {}).get("fact", "")
                rid = _duckbrain_remember(key=key, fact=fact)
                self._history.append({"role": "remember", "key": key, "id": rid})
                continue

            if tool_call["name"] == "recall":
                query = tool_call.get("arguments", {}).get("query", "/")
                results = _duckbrain_recall(query=query)
                self._history.append({"role": "recall", "query": query, "results": results[:200]})
                continue

            if tool_call["name"] == "set_goal":
                goal = tool_call.get("arguments", {}).get("goal", "")
                self.global_ctx.add_goal(goal)
                self._history.append({"role": "set_goal", "goal": goal})
                continue

            # Execute on emulator
            action_result = execute_tool_call(
                self.emulator,
                tool_name=tool_call["name"],
                arguments=tool_call.get("arguments", {}),
            )

            self._history.append({
                "step": self._step_count,
                "tool_call": tool_call,
                "action": action_result,
            })

            # ── Battle animation wait ──────────────────────────────
            # After executing a battle action (FIGHT, move select),
            # wait for the attack/HP-drain animation before re-reading.
            if self.state_type == "battle":
                self.emulator.wait(60)
                self.emulator.fast_forward(180)

            # ── HSM state update ──────────────────────────────────
            new_hsm_state = self._map_vision_to_hsm_state()
            if new_hsm_state and new_hsm_state != self.hsm.get_current_state_name():
                self.hsm.transition_to(new_hsm_state, reason=f"Step {self._step_count}")

            # Check for state transition
            outcome = self._check_outcome()
            if outcome:
                # ── Battle end logging ──────────────────────────
                if self._in_battle:
                    self._battle_events.append({
                        "event": "battle_end",
                        "outcome": outcome.get("outcome", "unknown"),
                        "to_type": outcome.get("to_type", "unknown"),
                    })
                # ── Include battle events in result ──────────────
                outcome["_battle_events"] = self._battle_events
                return outcome

        # Max steps reached without resolution
        result: dict[str, Any] = {"outcome": "max_steps", "steps": self._step_count,
                          "_battle_events": self._battle_events}
        return result

    # ── Prompt building ─────────────────────────────────────────────

    def _build_prompt(self) -> str:
        """Assemble the focused state window prompt."""
        parts: list[str] = []

        # ── RAM reader compact prompt path ──────────────────────────
        # Routes to battle-specific prompt when in battle, otherwise the
        # overworld compact prompt (which still requires player_x to be
        # present in vision data).
        if self.use_ram_prompts:
            screen = self.vision.get("result", self.vision.get("screen_type", ""))
            if screen == "battle" or self.vision.get("battle_state"):
                return self._build_battle_prompt()
            if "player_x" in self.vision:
                return self._build_ram_prompt()

        # 0. Core system prompt + hints (from core.yaml + hint layers)
        if self._system_prompt:
            parts.append(self._system_prompt)

        # 1. Compacted global context (system role)
        parts.append("\nGLOBAL STATE:\n" + self.global_ctx.compact())

        # 1b. HSM state
        hsm_name = self.hsm.get_current_state_name()
        available = self.hsm.get_available_transitions()
        parts.append(f"\nHSM STATE: {hsm_name}")
        if available:
            parts.append(f"  Valid next states: {', '.join(sorted(available))}")

        # 2. State workflow
        if self._workflow:
            parts.append("\nCURRENT TASK:\n" + self._workflow)

        # 3. Observation from vision
        parts.append("\nobservation:")
        parts.append(f"  Screen: {self.vision.get('screen_type', '?')}")
        if self.vision.get("screen_subtype"):
            parts.append(f"  Subtype: {self.vision['screen_subtype']}")
        if self.vision.get("name_field"):
            parts.append(f"  Name field: {self.vision['name_field']}")

        # Keyboard grid — critical for name_entry navigation
        kg = self.vision.get("keyboard_grid", {})
        if kg:
            cursor = kg.get("current_cursor", {"row": 0, "col": 0})
            cr, cc = cursor.get("row", 0), cursor.get("col", 0)
            rows = kg.get("rows", [])
            name_field = self.vision.get("name_field", "")
            
            # Figure out what letter the cursor is on
            cursor_letter = "?"
            if rows and cr < len(rows) and cc < len(rows[cr]):
                cursor_letter = rows[cr][cc]
            
            parts.append("\n  ⌨️ NAME ENTRY KEYBOARD — TYPE ONE LETTER AT A TIME:")
            parts.append(f"  CURSOR IS ON LETTER: '{cursor_letter}' at row={cr}, col={cc}")
            parts.append(f"  ALREADY TYPED: '{name_field}'")
            
            # Determine target name and next action
            target_name = "ASH"  # default
            if name_field and len(name_field) > 0:
                typed_count = len(name_field)
                if typed_count < len(target_name):
                    next_letter = target_name[typed_count]
                    # Find next_letter in the grid
                    tr, tc = -1, -1
                    for ri, row in enumerate(rows):
                        for ci, letter in enumerate(row):
                            if letter.upper() == next_letter.upper():
                                tr, tc = ri, ci
                                break
                        if tr >= 0:
                            break
                    if tr >= 0:
                        dr = tr - cr  # delta rows (negative = UP, positive = DOWN)
                        dc = tc - cc  # delta cols (negative = LEFT, positive = RIGHT)
                        dirs = []
                        if dr < 0:
                            dirs.append(f"press UP {abs(dr)} time(s)")
                        elif dr > 0:
                            dirs.append(f"press DOWN {dr} time(s)")
                        if dc < 0:
                            dirs.append(f"press LEFT {abs(dc)} time(s)")
                        elif dc > 0:
                            dirs.append(f"press RIGHT {dc} time(s)")
                        parts.append(f"  NEXT LETTER TO TYPE: '{next_letter}' at row={tr}, col={tc}")
                        if not dirs:
                            parts.append(f"  ⚡ CURSOR IS ON '{next_letter}' — press A NOW to type it!")
                        else:
                            parts.append(f"  TO REACH '{next_letter}': {' then '.join(dirs)}")
                            parts.append("  After reaching it, press A to type the letter.")
                    else:
                        parts.append(f"  NEXT LETTER '{next_letter}' not found — navigate to END")
                else:
                    parts.append("  ✓ ALL LETTERS TYPED! Navigate to END: press DOWN past all rows to bottom row, then RIGHT to END, then A.")
            else:
                # Nothing typed yet — first letter of target
                tr, tc = -1, -1
                first_letter = target_name[0]
                for ri, row in enumerate(rows):
                    for ci, letter in enumerate(row):
                        if letter.upper() == first_letter.upper():
                            tr, tc = ri, ci
                            break
                    if tr >= 0:
                        break
                if tr >= 0:
                    dr = tr - cr
                    dc = tc - cc
                    needed = []
                    if dr < 0:
                        needed.append(f"UP {abs(dr)}")
                    elif dr > 0:
                        needed.append(f"DOWN {dr}")
                    if dc < 0:
                        needed.append(f"LEFT {abs(dc)}")
                    elif dc > 0:
                        needed.append(f"RIGHT {dc}")
                    parts.append(f"  TARGET NAME: '{target_name}' — first letter is '{first_letter}' at row={tr}, col={cc}")
                    if not needed:
                        parts.append(f"  ⚡ CURSOR IS ON '{first_letter}' — press A NOW!")
                    else:
                        parts.append(f"  MOVE TO '{first_letter}': {' then '.join(needed)} — then press A.")
            
            if rows:
                parts.append("  Grid reference:")
                for ri, row in enumerate(rows):
                    parts.append(f"    Row {ri}: {row}")
            parts.append(f"  Bottom row: {kg.get('bottom_row', [])}")

        # Text content — the agent reads this to make decisions
        from src.core.prompt_loader import get_text_content
        content = get_text_content(self.vision)
        if content:
            parts.append("\n  SCREEN TEXT (read this — it tells you what to do):")
            for line in content:
                parts.append(f"    > {line}")

        menu_items = self.vision.get("menu_items", [])
        if menu_items:
            parts.append(f"  Menu: {menu_items}")
        adj = self.vision.get("adjacent_tiles", {})
        if adj:
            parts.append(f"  Surroundings: up={adj.get('up','?')} down={adj.get('down','?')} left={adj.get('left','?')} right={adj.get('right','?')}")

        # 4. Step counter
        parts.append(f"\nStep {self._step_count} of {self.max_steps} in this state.")

        # 5. History (last 3 actions)
        if self._history:
            parts.append("\nRecent actions in this state:")
            for h in self._history[-3:]:
                role = h.get("role", "")
                if role == "recall":
                    parts.append(f"  Recalled: {h.get('query','')} → {h.get('results','')}")
                elif role == "remember":
                    parts.append(f"  Remembered: {h.get('key','')}")
                elif role == "set_goal":
                    parts.append(f"  Set goal: {h.get('goal','')}")
                elif role == "query_global":
                    parts.append(f"  Asked global: {h.get('question','')}")
                else:
                    parts.append(f"  Step {h.get('step','?')}: {h.get('action','?')}")

        # 6. Output instruction
        parts.append(
            "\nOUTPUT: Call a tool. Use DuckBrain to remember things or set goals. "
            "If you need info from global state that isn't shown above, use query_global."
        )

        return "\n".join(parts)

    def _build_ram_prompt(self) -> str:
        """Build a compact prompt from RAM reader data (< 100 tokens for overworld).

        Uses configs/prompts/gen1/overworld_ram.yaml for the overworld template,
        configs/prompts/gen1/battle_ram.yaml for battle screens.
        Other screen types fall through to the standard prompt builder.
        """
        st = self.vision.get("result", self.vision.get("screen_type", ""))
        if st == "battle":
            return self._build_battle_prompt()
        if st != "overworld":
            # Fall back to standard build for non-overworld states
            return self._build_ram_fallback()

        # Load compact overworld template
        tmpl_path = Path("configs/prompts/gen1/overworld_ram.yaml")
        tmpl = ""
        if tmpl_path.exists():
            data = yaml.safe_load(tmpl_path.read_text())
            tmpl = data.get("ram_overworld", "") if isinstance(data, dict) else ""

        if not tmpl:
            return self._build_ram_fallback()

        # Fill template with ram_reader fields
        adj = self.vision.get("adjacent", {})
        try:
            prompt = tmpl.format(
                map_name=self.vision.get("map_name", "Unknown"),
                map_dims=self.vision.get("map_dimensions", "?"),
                player_x=self.vision.get("player_x", "?"),
                player_y=self.vision.get("player_y", "?"),
                facing=self.vision.get("player_facing", "?"),
                adj_up=adj.get("up", "?"),
                adj_down=adj.get("down", "?"),
                adj_left=adj.get("left", "?"),
                adj_right=adj.get("right", "?"),
                minimap=self.vision.get("overworld_grid", ""),
                suggested_action=self.vision.get("suggested_action", "explore"),
            )
        except (KeyError, ValueError, AttributeError):
            return self._build_ram_fallback()

        return prompt

    def _build_battle_prompt(self) -> str:
        """Build a compact battle prompt from RAM reader battle data.

        Uses configs/prompts/gen1/battle_ram.yaml as template.
        Falls back to the render_battle() text if template not available.
        The final prompt always ends with an explicit "call this tool"
        instruction so the controller LLM uses the battle tools instead
        of trying to compose raw button sequences.
        """
        # Try the battle RAM template first
        tmpl_path = Path("configs/prompts/gen1/battle_ram.yaml")
        tmpl = ""
        if tmpl_path.exists():
            data = yaml.safe_load(tmpl_path.read_text())
            tmpl = data.get("ram_battle", "") if isinstance(data, dict) else ""

        # Get battle state from vision dict (populated by ram_reader.observe())
        battle_state = self.vision.get("battle_state", {})
        if battle_state:
            p = battle_state.get("player", {})
            e = battle_state.get("enemy", {})
            battle_type = battle_state.get("battle_type", "Wild")

            # Build moves list using ONLY fields that read_battle_state()
            # actually exposes (name, pp, slot). pp_max / power live in
            # the move database, not the per-battle RAM read.
            moves_parts = []
            for i, move in enumerate(p.get("moves", [])):
                slot = move.get("slot", i + 1)
                moves_parts.append(
                    f"  {slot}. {move.get('name', '?')} (PP:{move.get('pp', 0)})"
                )
            moves_str = "\n".join(moves_parts) if moves_parts else "  (no moves)"

            if tmpl:
                try:
                    return tmpl.format(
                        battle_type=battle_type,
                        enemy_name=e.get("name", "Unknown"),
                        player_name=p.get("name", "Pokémon"),
                        player_level=p.get("level", "?"),
                        player_hp_pct=p.get("hp_pct", "?"),
                        player_hp=p.get("hp", "?"),
                        player_max_hp=p.get("max_hp", "?"),
                        player_type=p.get("type", "Unknown"),
                        enemy_level=e.get("level", "?"),
                        enemy_hp_pct=e.get("hp_pct", "?"),
                        enemy_hp=e.get("hp", "?"),
                        enemy_max_hp=e.get("max_hp", "?"),
                        enemy_type=e.get("type", "Unknown"),
                        moves_list=moves_str,
                    )
                except (KeyError, ValueError, AttributeError):
                    pass

        # Fallback: use the render field from ram_reader
        render = self.vision.get("render", "")
        if render:
            return (
                render
                + "\n→ Call select_move(N) for move N (1-4), run_from_battle() "
                "to flee, use_battle_item(name) to bag, or switch_pokemon(N) "
                "to swap."
            )

        # Last resort: standard RAM fallback
        return self._build_ram_fallback()

    def _build_ram_fallback(self) -> str:
        """Fallback: use the 'render' field from ram_reader as the prompt."""
        render = self.vision.get("render", "")
        if render:
            return render
        # Last resort: use standard builder
        parts: list[str] = []
        if self._system_prompt:
            parts.append(self._system_prompt)
        parts.append(f"Screen: {self.vision.get('result', '?')}")
        return "\n".join(parts)

    # ── Global query handler ─────────────────────────────────────────

    def _answer_global_query(self, question: str) -> str:
        """Answer a query against global context."""
        compacted = self.global_ctx.compact()
        # For now, just return the full compacted context.
        # Future: use an LLM to extract the specific answer.
        return compacted

    # ── Outcome detection ────────────────────────────────────────────

    def _map_vision_to_hsm_state(self) -> str | None:
        """Map vision/RAM-reader observation data to an HSM state name.

        Uses RAM reader data first (deterministic), falls back to
        vision screen_type/screen_subtype (vision-based classification).

        Returns the HSM state name (e.g. ``OVERWORLD.IDLE``), or None
        if the observation data cannot be mapped.
        """
        # ── RAM reader path (deterministic, preferred) ────────────────
        result = self.vision.get("result", "")
        battle_data = self.vision.get("battle", {})
        menu_items = self.vision.get("menu_items", [])
        text = self.vision.get("text_content", self.vision.get("text_lines", []))

        # Battle detection via RAM reader
        if result == "battle" or battle_data.get("is_battle"):
            return "BATTLE.BATTLE_MENU"

        # Menu detection via RAM reader
        if result == "menu" or (menu_items and result != "overworld"):
            # If menu items contain battle commands, we're in battle menu
            if any(item in ["FIGHT", "BAG", "PKMN", "RUN"] for item in menu_items):
                return "BATTLE.BATTLE_MENU"
            return "MENU.MAIN_MENU"

        # Dialog/text detection
        if result == "dialog" or (text and not menu_items and result not in ("battle", "menu")):
            return "DIALOG.TEXT_DISPLAY"

        # Overworld detection
        if result == "overworld" or "player_x" in self.vision:
            return "OVERWORLD.IDLE"

        # ── Vision-based fallback ─────────────────────────────────────
        st = self.vision.get("screen_type", "")
        _subtype = self.vision.get("screen_subtype", "")

        if st == "battle":
            return "BATTLE.BATTLE_MENU"
        if st == "menu":
            return "MENU.MAIN_MENU"
        if st in ("dialog", "text"):
            return "DIALOG.TEXT_DISPLAY"
        if st in ("overworld", "navigation"):
            return "OVERWORLD.IDLE"
        if st == "title":
            return "TITLE.WAITING_FOR_START"
        if st == "name_entry":
            return "BOOT.CHARACTER_NAMING"

        # Can't map
        return None

    def _log_hsm_transition(
        self, from_state: Any, to_state: Any
    ) -> None:
        """Callback: log HSM state transitions to DuckBrain.

        Registered with ``hsm.register_transition_callback()``.
        """
        try:
            from_name = from_state.name if from_state else "None"
            to_name = to_state.name if to_state else "None"
            entry = (
                f"HSM transition: {from_name} → {to_name} "
                f"(tick={self.hsm._tick})"
            )
            _duckbrain_remember(
                key=f"/play_sessions/transitions/{from_name}",
                fact=entry,
                namespace="pokemon-global",
            )
        except Exception:
            # DuckBrain is best-effort — never crash the game loop
            pass

    @staticmethod
    def _hsm_type_to_state_type(state_type: str) -> str:
        """Map a state_window ``state_type`` string to HSM StateType name (lowercase)."""
        mapping = {
            "battle": "battle",
            "menu": "menu",
            "dialog": "dialog",
            "text": "dialog",
            "overworld": "overworld",
            "navigation": "overworld",
            "title": "title",
            "name_entry": "boot",
        }
        return mapping.get(state_type, state_type)

    def _is_interactive(self) -> bool:
        """Check if the current dialog requires AI deliberation.

        Returns True when the vision output indicates the player needs
        to make a choice (menu, Yes/No prompt, name entry, etc.).

        Returns False for pure narration text boxes that just need
        an A press to advance — these can be fast-forwarded.
        """
        if self.vision.get("menu_items"):
            return True
        if self.vision.get("dialog_prompt"):
            return True
        if self.vision.get("screen_subtype") in ("keyboard", "yes_no"):
            return True
        if self.vision.get("name_field"):
            return True
        return False

    def _check_outcome(self) -> dict[str, Any] | None:
        """Check if the state has been resolved.

        Primary: checks if the HSM transitioned away from the initial state
        captured during ``__init__``.
        Fallback: uses vision_client to re-analyze screen when available.

        Returns an outcome dict if the state transitioned, or None.
        """
        # ── Primary: HSM-based state change detection ────────────────
        current_hsm = self.hsm.get_current_state_name()
        if current_hsm != self._initial_hsm_state:
            hsm_cur = self.hsm.get_current_state()
            return {
                "outcome": "state_transition",
                "from_type": self.state_type,
                "to_type": hsm_cur.state_type.name.lower() if hsm_cur else "unknown",
                "hsm_state": current_hsm,
            }

        # ── Fallback: vision-based re-classification ──────────────────
        if self.vision_client is None:
            return None

        init_screen_type = self.vision.get("screen_type", "")
        if not init_screen_type:
            return None

        try:
            screenshot = self.emulator.capture()
        except Exception:
            return None

        try:
            new_vision = self.vision_client.analyze(screenshot, game=self.generation)
        except Exception:
            return None

        new_screen_type = new_vision.get("screen_type", "")
        if new_screen_type and new_screen_type != init_screen_type:
            return {
                "outcome": "state_transition",
                "from_type": init_screen_type,
                "to_type": new_screen_type,
                "new_vision": new_vision,
            }

        # Same screen type — also check subtype changes for menu transitions
        init_subtype = self.vision.get("screen_subtype")
        new_subtype = new_vision.get("screen_subtype")
        if new_subtype and init_subtype and new_subtype != init_subtype:
            return {
                "outcome": "state_transition",
                "from_type": f"{init_screen_type}/{init_subtype}",
                "to_type": f"{new_screen_type}/{new_subtype}",
                "new_vision": new_vision,
            }

        return None
