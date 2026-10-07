"""Scripted TOOLS-1 smoke run with no emulator ROM or API calls."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.core.agentic_loop import (  # noqa: E402
    BoundedAgentContext,
    InMemoryAgentMemory,
    run_agentic_cycle,
)


class _ScriptedClient:
    """Return one model-chosen tool call, then a final plan."""

    def __init__(self) -> None:
        self._replies = [
            {"name": "walk", "arguments": {"direction": "right", "tiles": 1}},
            {"plan": [], "intent": "scripted tool movement completed"},
        ]

    def send_tool_request(
        self, prompt: str, tools: list[dict[str, Any]], **kwargs: Any
    ) -> str:
        _ = prompt, tools, kwargs
        return json.dumps(self._replies.pop(0))


class _ScriptedEmulator:
    def __init__(self) -> None:
        self.x = 4
        self.y = 7

    def press_button(self, button: str, frames: int = 5) -> None:
        _ = frames
        if button == "right":
            self.x += 1

    def fast_forward(self, frames: int) -> None:
        _ = frames


def run_smoke(output: Path) -> list[dict[str, Any]]:
    """Run the real bounded tool loop against deterministic scripted fixtures."""
    emulator = _ScriptedEmulator()

    def observe() -> dict[str, Any]:
        return {
            "result": "overworld",
            "map_id": 1,
            "map_name": "Pallet Town",
            "player_tile_x": emulator.x,
            "player_tile_y": emulator.y,
        }

    result = run_agentic_cycle(
        client=_ScriptedClient(),
        emulator=emulator,
        observe=observe,
        projection=observe(),
        context=BoundedAgentContext(),
        memory=InMemoryAgentMemory(),
        delegate=None,
        model="scripted/tools-1",
        cycle=1,
        decision_mode="llm",
        decision_mode_family="system2",
        run_id="tools1-smoke",
    )
    rows = [
        *result.events,
        {
            "cycle": 1,
            "event": "decision",
            "pipeline": "agentic_tools",
            "decision_mode": "llm",
            "decision_mode_family": "system2",
            "agentic_tools_enabled": True,
            "agentic_tool_calls": len(result.events),
            "plan": result.decision["plan"],
            "intent": result.decision["intent"],
        },
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("".join(json.dumps(row, default=str) + "\n" for row in rows))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("cron_logs/run_tools1_smoke.jsonl"),
    )
    args = parser.parse_args()
    rows = run_smoke(args.output)
    print(json.dumps(rows[0], ensure_ascii=False))
    print(f"wrote {len(rows)} rows to {args.output}")


if __name__ == "__main__":
    main()
