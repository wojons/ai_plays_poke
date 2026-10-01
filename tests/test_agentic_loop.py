"""Deterministic acceptance tests for the bounded opt-in agentic loop."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any

import cron_runner
import pytest
from src.core.agentic_loop import (
    AgenticCaps,
    BoundedAgentContext,
    InMemoryAgentMemory,
    ModelResearchDelegate,
    run_agentic_cycle,
)


class _FakeClient:
    def __init__(self, replies: list[dict[str, Any]]) -> None:
        self.replies = list(replies)
        self.calls: list[dict[str, Any]] = []

    def send_tool_request(
        self, prompt: str, tools: list[dict[str, Any]], **kwargs: Any
    ) -> str:
        self.calls.append({"prompt": prompt, "tools": tools, **kwargs})
        return json.dumps(self.replies.pop(0))


class _FakeEmulator:
    def __init__(self, *, movement_changes_position: bool = True) -> None:
        self.x = 4
        self.y = 7
        self.movement_changes_position = movement_changes_position
        self.presses: list[str] = []

    def press_button(self, button: str, frames: int = 5) -> None:
        self.presses.append(button)
        if self.movement_changes_position and button == "right":
            self.x += 1

    def fast_forward(self, frames: int) -> None:
        return None


def _observe(emu: _FakeEmulator, text: str = "") -> Callable[[], dict[str, Any]]:
    return lambda: {
        "result": "overworld",
        "map_id": 1,
        "map_name": "Pallet Town",
        "player_tile_x": emu.x,
        "player_tile_y": emu.y,
        "text_content": [text] if text else [],
    }


def test_context_rolls_old_turns_into_a_capped_summary_with_text_facts() -> None:
    context = BoundedAgentContext(max_turns=2, summary_chars=150, block_chars=600)
    for cycle in range(1, 6):
        context.record(
            cycle=cycle,
            decision=f"decision-{cycle}",
            action=f"action-{cycle}",
            result=f"result-{cycle}",
            text_facts=[f"NPC said fact-{cycle}"],
        )

    block = context.render()
    evidence = context.evidence()

    assert [turn["cycle"] for turn in context.turns] == [4, 5]
    assert "EARLIER TURN SUMMARY" in block
    assert "cycle 3" in block
    assert "NPC said fact-3" in block
    assert "cycle 4" in block and "cycle 5" in block
    assert len(context.summary) <= 150
    assert len(block) <= 600
    assert evidence["window_turns"] == 2
    assert evidence["window_cap"] == 2
    assert evidence["context_chars"] == len(block)


def test_model_chosen_walk_is_executed_verified_and_stamped() -> None:
    client = _FakeClient(
        [
            {"name": "walk", "arguments": {"direction": "right", "tiles": 1}},
            {"plan": [], "intent": "movement already executed by tool"},
        ]
    )
    emulator = _FakeEmulator()
    context = BoundedAgentContext()

    result = run_agentic_cycle(
        client=client,
        emulator=emulator,
        observe=_observe(emulator),
        projection={"map_name": "Pallet Town", "result": "overworld"},
        context=context,
        memory=InMemoryAgentMemory(),
        delegate=None,
        model="fake/model",
        cycle=9,
        decision_mode="agentic",
        decision_mode_family="system2",
    )

    assert result.decision == {
        "plan": [],
        "intent": "movement already executed by tool",
        "raw_response": json.dumps(
            {"plan": [], "intent": "movement already executed by tool"}
        ),
        "agentic_tool_calls": 1,
    }
    assert emulator.presses == ["right"]
    assert len(result.events) == 1
    event = result.events[0]
    assert event["event"] == "agent_tool_call"
    assert event["tool_name"] == "walk"
    assert event["ok"] is True
    assert event["verified"] is True
    assert event["decision_mode"] == "agentic"
    assert event["decision_mode_family"] == "system2"
    assert event["agentic_tools_enabled"] is True
    assert {tool["function"]["name"] for tool in client.calls[0]["tools"]} >= {
        "walk",
        "interact",
        "read_dialogue",
        "recall",
        "delegate_research",
    }


def test_failed_tool_result_is_visible_to_model_and_never_becomes_blind_a() -> None:
    client = _FakeClient(
        [
            {"name": "walk", "arguments": {"direction": "right", "tiles": 1}},
            {"plan": [], "intent": "movement failed; wait for new evidence"},
        ]
    )
    emulator = _FakeEmulator(movement_changes_position=False)

    result = run_agentic_cycle(
        client=client,
        emulator=emulator,
        observe=_observe(emulator),
        projection={"map_name": "Pallet Town", "result": "overworld"},
        context=BoundedAgentContext(),
        memory=InMemoryAgentMemory(),
        delegate=None,
        model="fake/model",
        cycle=3,
        decision_mode="agentic",
        decision_mode_family="system2",
    )

    assert result.events[0]["ok"] is False
    assert "position did not change" in result.events[0]["result"]
    assert "position did not change" in client.calls[1]["prompt"]
    assert '"ok": false' in client.calls[1]["prompt"]
    assert result.decision["plan"] == []
    assert result.decision["intent"] != "parse_failure_fallback"


class _FakeDelegate:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def research(
        self, *, question: str, public_context: dict[str, Any], caps: Any
    ) -> dict[str, Any]:
        self.calls.append(
            {"question": question, "public_context": public_context, "caps": caps}
        )
        return {
            "finding": "Pokémon Center signs identify a healing location.",
            "sources": ["public game manual"],
            "confidence": 0.8,
            "cost_usd": 0.0004,
            "tool_calls": 1,
            "elapsed_s": 0.2,
        }


def test_delegation_is_capped_persisted_and_consumed_by_later_cycle() -> None:
    caps = AgenticCaps(
        max_tool_calls=2,
        delegate_wall_seconds=2.0,
        delegate_tool_calls=1,
        delegate_cost_usd=0.001,
        finding_chars=120,
        source_count=2,
    )
    context = BoundedAgentContext()
    memory = InMemoryAgentMemory()
    delegate = _FakeDelegate()
    emulator = _FakeEmulator()
    first_client = _FakeClient(
        [
            {
                "name": "delegate_research",
                "arguments": {"question": "How can I recognize a healing location?"},
            },
            {"plan": [], "intent": "store the research before moving"},
        ]
    )

    first = run_agentic_cycle(
        client=first_client,
        emulator=emulator,
        observe=_observe(emulator),
        projection={
            "map_name": "Pallet Town",
            "result": "overworld",
            "text_content": ["A sign is visible"],
            "private_token": "must-not-leak",
        },
        context=context,
        memory=memory,
        delegate=delegate,
        model="fake/model",
        cycle=4,
        decision_mode="agentic",
        decision_mode_family="system2",
        caps=caps,
    )

    event = first.events[0]
    assert event["delegation"] is True
    assert event["ok"] is True
    assert event["caps"] == {
        "wall_seconds": 2.0,
        "tool_calls": 1,
        "cost_usd": 0.001,
    }
    assert delegate.calls[0]["public_context"] == {
        "map_name": "Pallet Town",
        "screen": "overworld",
        "text": ["A sign is visible"],
    }
    assert len(memory.records) == 1
    assert memory.records[0]["finding"].startswith("Pokémon Center")

    later_client = _FakeClient([{"plan": ["UP"], "intent": "use delegated sign fact"}])
    later = run_agentic_cycle(
        client=later_client,
        emulator=emulator,
        observe=_observe(emulator),
        projection={"map_name": "Pallet Town", "result": "overworld"},
        context=context,
        memory=memory,
        delegate=delegate,
        model="fake/model",
        cycle=5,
        decision_mode="agentic",
        decision_mode_family="system2",
        caps=caps,
    )

    assert "Pokémon Center signs identify" in later_client.calls[0]["prompt"]
    assert later.decision["plan"] == ["UP"]
    assert later.context_evidence["delegated_findings"] == 1


def test_tool_cap_is_hard_and_mode_is_explicitly_opt_in() -> None:
    client = _FakeClient(
        [
            {"name": "read_dialogue", "arguments": {}},
            {"name": "read_dialogue", "arguments": {}},
            {"name": "read_dialogue", "arguments": {}},
        ]
    )
    emulator = _FakeEmulator()
    result = run_agentic_cycle(
        client=client,
        emulator=emulator,
        observe=_observe(emulator, "HELLO"),
        projection={"map_name": "Pallet Town", "result": "dialog"},
        context=BoundedAgentContext(),
        memory=InMemoryAgentMemory(),
        delegate=None,
        model="fake/model",
        cycle=1,
        decision_mode="agentic",
        decision_mode_family="system2",
        caps=AgenticCaps(max_tool_calls=2),
    )

    assert len(result.events) == 2
    assert len(client.calls) == 2
    assert result.decision["plan"] == []
    assert result.decision["intent"] == "agentic_tool_cap_reached"
    assert result.decision["agentic_tool_calls"] == 2

    parser = cron_runner._main_parser()
    assert parser.parse_args([]).decision_mode is None
    assert parser.parse_args(["--decision-mode", "agentic"]).decision_mode == "agentic"
    assert cron_runner.DEFAULT_DECISION_MODE == "jev"
    assert cron_runner.decision_mode_family("agentic") == cron_runner.MODE_SYSTEM2


def test_agentic_mode_routes_around_jev_without_changing_jev_default(
    monkeypatch,
) -> None:
    calls: list[object] = []
    monkeypatch.setattr(
        cron_runner,
        "_jev_overworld_decision",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    original = cron_runner.DECISION_MODE
    try:
        cron_runner.DECISION_MODE = "agentic"
        assert cron_runner._jev_or_none({"result": "overworld"}) is None
        assert calls == []
    finally:
        cron_runner.DECISION_MODE = original


def test_legacy_controller_request_carries_capped_running_summary() -> None:
    class _CompletionClient:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        def chat_completion(self, **kwargs: Any) -> dict[str, str]:
            self.calls.append(kwargs)
            return {"content": '{"plan": [], "intent": "summary consumed"}'}

    client = _CompletionClient()
    cron_runner.controller_plan(
        client,
        {"map_name": "Pallet Town"},
        "",
        "",
        running_summary="old-fact:" + "x" * 2_000,
    )

    prompt = str(client.calls[0]["messages"][1]["content"])
    summary = prompt.split("EARLIER TURN SUMMARY (capped):\n", 1)[1].split(
        "\n\nOutput a movement plan", 1
    )[0]
    assert summary.startswith("old-fact:")
    assert len(summary) == 1_200


def test_model_research_delegate_enforces_cost_ceiling_without_tools() -> None:
    class _ResearchClient:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        def chat_completion(self, **kwargs: Any) -> dict[str, str]:
            self.calls.append(kwargs)
            return {
                "content": json.dumps(
                    {
                        "finding": "Signs with P.C. mark healing buildings.",
                        "sources": ["public manual"],
                        "confidence": 0.7,
                    }
                )
            }

    client = _ResearchClient()
    delegate = ModelResearchDelegate(client, "openai/gpt-5.6-luna")
    caps = AgenticCaps(delegate_cost_usd=0.001, delegate_wall_seconds=1.0)
    result = delegate.research(
        question="How are healing buildings marked?",
        public_context={"screen": "overworld", "map_name": "Pallet Town"},
        caps=caps,
    )

    assert result["cost_usd"] <= caps.delegate_cost_usd
    assert result["tool_calls"] == 1
    assert len(client.calls) == 1
    assert client.calls[0]["max_tokens"] <= 240
    assert "tools" not in client.calls[0]


def test_model_research_delegate_returns_at_wall_clock_cap() -> None:
    class _SlowResearchClient:
        def chat_completion(self, **kwargs: Any) -> dict[str, str]:
            time.sleep(0.08)
            return {"content": '{"finding": "late"}'}

    delegate = ModelResearchDelegate(_SlowResearchClient(), "openai/gpt-5.6-luna")
    started = time.monotonic()
    with pytest.raises(TimeoutError, match="wall-clock cap"):
        delegate.research(
            question="What is this sign?",
            public_context={"screen": "overworld"},
            caps=AgenticCaps(delegate_wall_seconds=0.01),
        )
    assert time.monotonic() - started < 0.06
