"""Deterministic acceptance tests for the bounded opt-in agentic loop."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from io import StringIO
from pathlib import Path
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
        _ = frames
        self.presses.append(button)
        if self.movement_changes_position and button == "right":
            self.x += 1

    def fast_forward(self, frames: int) -> None:
        _ = frames
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
    assert "cycle 4" in block
    assert "cycle 5" in block
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
    schemas = {
        tool["function"]["name"]: tool["function"]["parameters"]
        for tool in client.calls[0]["tools"]
    }
    assert set(schemas) == {
        "walk",
        "interact",
        "read_dialog",
        "remember",
        "recall",
        "delegate_research",
        "set_goal",
        "check_goal",
    }
    assert schemas["interact"]["required"] == ["target"]
    assert schemas["delegate_research"]["required"] == ["question", "budget"]
    assert event["agentic_tool_calls"] == 1


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


def test_model_can_remember_then_recall_labeled_facts() -> None:
    client = _FakeClient(
        [
            {
                "name": "remember",
                "arguments": {
                    "key": "/world/object/1/4_7",
                    "domain": "world/object",
                    "facts": {"identity": "mailbox", "interaction": "none"},
                    "applies_when": {"map_id": 1},
                },
            },
            {
                "name": "recall",
                "arguments": {"key": "/world/object/1/4_7"},
            },
            {"plan": [], "intent": "memory verified"},
        ]
    )
    memory = InMemoryAgentMemory()

    result = run_agentic_cycle(
        client=client,
        emulator=_FakeEmulator(),
        observe=lambda: {},
        projection={"map_id": 1, "result": "overworld"},
        context=BoundedAgentContext(),
        memory=memory,
        delegate=None,
        model="fake/model",
        cycle=6,
        decision_mode="llm",
        decision_mode_family="system2",
        caps=AgenticCaps(max_tool_calls=3),
        run_id="tools-1-test",
    )

    assert [event["tool_name"] for event in result.events] == ["remember", "recall"]
    assert all(event["ok"] and event["verified"] for event in result.events)
    assert result.events[1]["result"].startswith("Recalled 1 record(s)")
    assert memory.records[0]["key"] == "/world/object/1/4_7"
    assert memory.records[0]["facts"]["identity"] == "mailbox"


def test_model_can_set_and_check_run_goal() -> None:
    client = _FakeClient(
        [
            {
                "name": "set_goal",
                "arguments": {"text": "Reach Route 1", "reason": "Explore north"},
            },
            {"name": "check_goal", "arguments": {}},
            {"plan": [], "intent": "goal confirmed"},
        ]
    )
    context = BoundedAgentContext()
    memory = InMemoryAgentMemory()

    result = run_agentic_cycle(
        client=client,
        emulator=_FakeEmulator(),
        observe=lambda: {},
        projection={"map_id": 1, "result": "overworld"},
        context=context,
        memory=memory,
        delegate=None,
        model="fake/model",
        cycle=7,
        decision_mode="agentic",
        decision_mode_family="system2",
        caps=AgenticCaps(max_tool_calls=3),
        run_id="run-abc",
    )

    assert [event["tool_name"] for event in result.events] == ["set_goal", "check_goal"]
    assert result.events[1]["result"] == (
        'Current goal: {"text": "Reach Route 1", "reason": "Explore north"}'
    )
    assert memory.records[0]["key"] == "/run/run-abc/goal"
    assert context.current_goal == {
        "text": "Reach Route 1",
        "reason": "Explore north",
    }


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
                "arguments": {
                    "question": "How can I recognize a healing location?",
                    "budget": {
                        "wall_seconds": 2.0,
                        "tool_calls": 1,
                        "cost_usd": 0.001,
                    },
                },
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
            {"name": "read_dialog", "arguments": {}},
            {"name": "read_dialog", "arguments": {}},
            {"name": "read_dialog", "arguments": {}},
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


def test_model_tool_surface_follows_system_two_family_without_touching_jev() -> None:
    assert cron_runner._model_tools_enabled("agentic") is True
    assert cron_runner._model_tools_enabled("llm") is True
    assert cron_runner._model_tools_enabled("system2") is True
    assert cron_runner._model_tools_enabled("jev") is False
    assert cron_runner._model_tools_enabled("system1+system2") is False
    assert cron_runner._model_tools_enabled("system1") is False
    help_text = " ".join(cron_runner._main_parser().format_help().split())
    assert "verified model-tool surface" in help_text
    assert "JEV/hybrid never enables this surface" in help_text


@pytest.mark.parametrize(
    ("mode", "family", "pipeline", "tool_calls", "tools_enabled"),
    [
        ("jev", "system1+system2", "jev", 0, False),
        ("llm", "system2", "agentic_tools", 1, True),
    ],
)
def test_run_summary_matches_decision_tool_surface_stamps(
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    family: str,
    pipeline: str,
    tool_calls: int,
    tools_enabled: bool,
) -> None:
    monkeypatch.setattr(cron_runner, "DECISION_MODE", mode)
    row = {
        "intent": "benchmark decision",
        "pipeline": pipeline,
        "decision_mode": mode,
        "decision_mode_family": family,
        "agentic_tools_enabled": tools_enabled,
        "agentic_tool_calls": tool_calls,
        "jev_answered": mode == "jev",
    }
    autonomy = cron_runner._autonomy_counters([row])
    buffer = StringIO()
    summary = cron_runner._write_autonomy_row(buffer, "bench-par", autonomy)

    assert summary["decision_mode"] == row["decision_mode"]
    assert summary["decision_mode_family"] == row["decision_mode_family"]
    assert summary["agentic_tools_enabled"] is row["agentic_tools_enabled"]
    assert summary["agentic_tool_calls"] == row["agentic_tool_calls"]
    assert summary["pipeline"] == row["pipeline"]
    assert summary["pipeline_counts"] == {pipeline: 1}
    assert json.loads(buffer.getvalue()) == summary


def test_scripted_smoke_writes_model_chosen_tool_result_row(tmp_path: Path) -> None:
    from scripts.smoke_agentic_tools import run_smoke

    output = tmp_path / "run_tools1_smoke.jsonl"
    rows = run_smoke(output)

    logged = [json.loads(line) for line in output.read_text().splitlines()]
    assert logged == rows
    assert logged[0]["event"] == "agent_tool_call"
    assert logged[0]["decision_mode"] == "llm"
    assert logged[0]["decision_mode_family"] == "system2"
    assert logged[0]["agentic_tools_enabled"] is True
    assert logged[0]["agentic_tool_calls"] >= 1
    assert logged[0]["tool_name"] == "walk"
    assert logged[0]["ok"] is True
    assert logged[0]["verified"] is True
    assert "Walked right 1 tile" in logged[0]["result"]


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
            _ = kwargs
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
