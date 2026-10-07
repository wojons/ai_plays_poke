"""DELEG-1 scripted S5 delegation acceptance smoke — no ROM, no API.

Mirrors scripts/smoke_agentic_tools.py and the unit-test pattern in
tests/test_agentic_loop.py: a scripted client emits one model-chosen
``delegate_research`` call, a scripted delegate returns a canned finding, the
finding is persisted to memory, and a LATER cycle's prompt (same process, same
memory/context objects) carries it — the SPEC_agentic_memory_loop.md §5
acceptance, visible in the emitted JSON log rather than asserted in-process.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.core.agentic_loop import (  # noqa: E402
    AgenticCaps,
    BoundedAgentContext,
    InMemoryAgentMemory,
    run_agentic_cycle,
)

QUESTION = "Why is the Viridian City gym locked?"
FINDING = "Pokémon Red: Viridian City gym is locked until badges X"


class _ScriptedClient:
    """Cycle 1: emit the delegate_research call then a final plan."""

    def __init__(self) -> None:
        self._replies: list[dict[str, Any]] = [
            {
                "name": "delegate_research",
                "arguments": {
                    "question": QUESTION,
                    "budget": {
                        "wall_seconds": 2.0,
                        "tool_calls": 1,
                        "cost_usd": 0.001,
                    },
                },
            },
            {"plan": ["UP"], "intent": "store the finding before heading north"},
        ]
        self.calls: list[dict[str, Any]] = []

    def send_tool_request(
        self, prompt: str, tools: list[dict[str, Any]], **kwargs: Any
    ) -> str:
        self.calls.append({"prompt": prompt, "tools": tools, **kwargs})
        return json.dumps(self._replies.pop(0))


class _LaterClient:
    """Cycle 2: record the received prompt, return a final plan."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def send_tool_request(
        self, prompt: str, tools: list[dict[str, Any]], **kwargs: Any
    ) -> str:
        self.calls.append({"prompt": prompt, "tools": tools, **kwargs})
        return json.dumps({"plan": ["UP"], "intent": "using delegated finding"})


class _ScriptedDelegate:
    """Canned research worker — the finding the model 'asked' for."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def research(
        self, *, question: str, public_context: dict[str, Any], caps: Any
    ) -> dict[str, Any]:
        self.calls.append(
            {"question": question, "public_context": public_context, "caps": caps}
        )
        return {
            "finding": FINDING,
            "sources": ["public game manual"],
            "confidence": 0.9,
            "cost_usd": 0.0004,
            "tool_calls": 1,
            "elapsed_s": 0.2,
        }


def _observe(emu: "_ScriptedEmulator") -> dict[str, Any]:
    return {
        "result": "overworld",
        "map_id": 1,
        "map_name": "Pallet Town",
        "player_tile_x": emu.x,
        "player_tile_y": emu.y,
    }


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


def _expected_key(question: str) -> str:
    digest = hashlib.sha256(question.encode()).hexdigest()[:16]
    return f"/world/research/{digest}"


def run_smoke(output: Path) -> list[dict[str, Any]]:
    """Two cycles, same memory + context objects, deterministic fixtures."""
    emulator = _ScriptedEmulator()
    context = BoundedAgentContext()
    memory = InMemoryAgentMemory()
    delegate = _ScriptedDelegate()
    caps = AgenticCaps(
        max_tool_calls=2,
        delegate_wall_seconds=2.0,
        delegate_tool_calls=1,
        delegate_cost_usd=0.001,
        finding_chars=120,
        source_count=2,
    )

    rows: list[dict[str, Any]] = []

    # ── Cycle 1: model-chosen delegate_research + persistence ──
    first_client = _ScriptedClient()
    first = run_agentic_cycle(
        client=first_client,
        emulator=emulator,
        observe=lambda: _observe(emulator),
        projection={
            "map_name": "Pallet Town",
            "result": "overworld",
            "text_content": ["A sign is visible"],
        },
        context=context,
        memory=memory,
        delegate=delegate,
        model="scripted/deleg1",
        cycle=4,
        decision_mode="agentic",
        decision_mode_family="system2",
        caps=caps,
        run_id="deleg1-smoke",
    )

    delegate_events = [
        e for e in first.events if e.get("tool_name") == "delegate_research"
    ]
    assert len(delegate_events) == 1, (
        f"expected 1 delegate event, got {delegate_events}"
    )
    delegate_event = delegate_events[0]
    assert delegate_event["ok"] is True and delegate_event["verified"] is True
    assert delegate_event["delegation"] is True

    recalled = memory.recall(key=_expected_key(QUESTION))
    assert recalled, "finding was not persisted under /world/research/<digest>"
    record = recalled[0]

    rows.append(
        {
            "step": "cycle1_delegate_call",
            "cycle": 4,
            "event": delegate_event,
            "evidence": {
                "tool_name": delegate_event["tool_name"],
                "ok": delegate_event["ok"],
                "caps": delegate_event["caps"],
                "result": delegate_event["result"],
            },
        }
    )
    rows.append(
        {
            "step": "cycle1_memory_persisted",
            "cycle": 4,
            "event": "memory_recall_by_key",
            "evidence": {"key": record["key"], "record": record},
        }
    )

    # ── Cycle 2 (later cycle, same memory object): context carries it ──
    later_client = _LaterClient()
    later = run_agentic_cycle(
        client=later_client,
        emulator=emulator,
        observe=lambda: _observe(emulator),
        projection={"map_name": "Pallet Town", "result": "overworld"},
        context=context,
        memory=memory,
        delegate=delegate,
        model="scripted/deleg1",
        cycle=5,
        decision_mode="agentic",
        decision_mode_family="system2",
        caps=caps,
        run_id="deleg1-smoke",
    )

    prompt = later_client.calls[0]["prompt"]
    evidence = dict(later.context_evidence)
    assert evidence["delegated_findings"] >= 1, evidence
    assert FINDING in prompt, "finding text missing from later-cycle prompt"

    rows.append(
        {
            "step": "cycle2_later_context",
            "cycle": 5,
            "event": "context_evidence",
            "evidence": {
                **evidence,
                "finding_in_prompt": FINDING in prompt,
                "prompt_chars": len(prompt),
            },
        }
    )
    rows.append(
        {
            "step": "cycle2_decision",
            "cycle": 5,
            "event": "decision",
            "evidence": {
                "plan": later.decision["plan"],
                "intent": later.decision["intent"],
                "pipeline": "agentic_tools",
            },
        }
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "".join(json.dumps(row, default=str, ensure_ascii=False) + "\n" for row in rows)
    )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("/tmp/run_deleg1_smoke.jsonl"),
    )
    args = parser.parse_args()
    rows = run_smoke(args.output)
    for row in rows:
        print(json.dumps(row, default=str, ensure_ascii=False))
    print(f"wrote {len(rows)} rows to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
