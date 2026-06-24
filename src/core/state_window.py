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
import re
from pathlib import Path
from typing import Any

import yaml

from src.core.ai_client import OpenRouterClient
from src.core.global_context import GlobalContext
from src.core.tools import TOOL_SCHEMA, execute_tool_call
import subprocess, json, os

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
    ) -> None:
        self.state_type = state_type
        self.global_ctx = global_ctx
        self.emulator = emulator
        self.vision = vision
        self.generation = generation
        self.thinking_model = thinking_model
        self.max_steps = max_steps

        self.client = OpenRouterClient()
        self._step_count = 0
        self._history: list[dict[str, Any]] = []

        # Load state workflow
        self._workflow = _load_state_workflow(state_type, generation)

    # ── Public API ────────────────────────────────────────────────────

    def run(self) -> dict[str, Any]:
        """Run the focused state loop until resolved or max_steps reached.

        Returns a result dict with 'outcome' and relevant data.
        """
        for _ in range(self.max_steps):
            self._step_count += 1

            # Build the focused prompt
            prompt = self._build_prompt()

            # Get action from thinking model
            response = self.client.send_tool_request(
                prompt=prompt,
                tools=TOOL_SCHEMA + _DUCKBRAIN_TOOLS + [_QUERY_GLOBAL_TOOL],
                model=self.thinking_model,
                max_tokens=150,
                temperature=0.3,
            )

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

            # Check for state transition
            outcome = self._check_outcome()
            if outcome:
                return outcome

        # Max steps reached without resolution
        return {"outcome": "max_steps", "steps": self._step_count}

    # ── Prompt building ─────────────────────────────────────────────

    def _build_prompt(self) -> str:
        """Assemble the focused state window prompt."""
        parts: list[str] = []

        # 1. Compacted global context (system role)
        parts.append("GLOBAL STATE:\n" + self.global_ctx.compact())

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
        text_lines = self.vision.get("text_lines", [])
        if text_lines:
            parts.append(f"  Text: {text_lines}")
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
            "\nOUTPUT: Call a tool. If you need info from global state "
            "that isn't shown above, use query_global."
        )

        return "\n".join(parts)

    # ── Global query handler ─────────────────────────────────────────

    def _answer_global_query(self, question: str) -> str:
        """Answer a query against global context."""
        compacted = self.global_ctx.compact()
        # For now, just return the full compacted context.
        # Future: use an LLM to extract the specific answer.
        return compacted

    # ── Outcome detection ────────────────────────────────────────────

    def _check_outcome(self) -> dict[str, Any] | None:
        """Check if the state has been resolved based on recent history.

        Override in subclasses or use the vision model to detect.
        """
        # TODO: use vision + LLM to detect state transitions
        # For now, state transitions are handled by the parent DecisionLoop
        return None
