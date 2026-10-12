"""CH-OBJ: navigation objectives are harness-owned bounded structures."""

from __future__ import annotations

import io
import json
from dataclasses import FrozenInstanceError
from types import SimpleNamespace
from typing import Any

import pytest

import cron_runner
from src.core import duckbrain_client
from src.core.agentic_loop import _public_context


class _ScriptedClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def chat_completion(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {"content": '{"plan":["UP"],"intent":"follow objective"}'}


def test_objective_structure_and_win_condition_are_immutable() -> None:
    state = cron_runner._NavigationObjectiveState()
    projection = state.projection()

    assert projection["source"] == "harness"
    assert projection["objective_type"] == "navigation_benchmark"
    assert projection["harness_owned"] is True
    assert projection["win_condition"] == {
        "id": "reach_viridian_city",
        "type": "navigation",
        "kind": "reach_map",
        "target_map": "Viridian City",
        "text": "Complete the navigation ladder by reaching Viridian City.",
        "status": "immutable",
        "immutable": True,
    }
    assert [item["id"] for item in projection["sequence"]] == [
        "leave_oaks_lab",
        "reach_route_1",
        "reach_viridian_city",
    ]
    assert isinstance(state.sequence, tuple)

    with pytest.raises(FrozenInstanceError):
        state.current_map_name = "model replacement"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        state.win_condition.text = "Beat the Elite Four"  # type: ignore[misc]


def test_active_objective_is_derived_from_observed_navigation_progress() -> None:
    state = cron_runner._NavigationObjectiveState()

    state = state.observe(cron_runner.OAKS_LAB_MAP_ID, "Oaks Lab")
    assert state.current_objective.objective_id == "leave_oaks_lab"
    assert state.completed_count == 0

    state = state.observe(0, "Pallet Town")
    assert state.current_objective.objective_id == "reach_route_1"
    assert state.completed_count == 1

    state = state.observe(12, "Route 1")
    assert state.current_objective.objective_id == "reach_viridian_city"
    assert state.completed_count == 2
    assert state.projection()["progress"]["percent"] == 67

    regressed = state.observe(0, "Pallet Town")
    assert regressed.current_objective.objective_id == "reach_viridian_city"
    assert regressed.completed_count == 2

    completed = regressed.observe(1, "Viridian City")
    assert completed.complete is True
    assert completed.projection()["progress"]["complete"] is True
    assert completed.projection()["progress"]["percent"] == 100


def test_objective_serialization_is_bounded_under_hostile_observations() -> None:
    state = cron_runner._NavigationObjectiveState()
    for index in range(40):
        state = state.observe(100 + index, f"map-{index}-" + "x" * 2_000)

    encoded = state.serialize()
    decoded = json.loads(encoded)

    assert len(encoded) <= cron_runner.NAVIGATION_OBJECTIVE_SERIALIZED_CHAR_LIMIT
    assert len(decoded["progress"]["observed_maps"]) == (
        cron_runner.NAVIGATION_OBJECTIVE_OBSERVED_MAP_LIMIT
    )
    assert all(
        len(name) <= cron_runner.NAVIGATION_OBJECTIVE_MAP_NAME_CHAR_LIMIT
        for name in decoded["progress"]["observed_maps"]
    )


def test_model_goal_remains_legacy_advisory_and_cannot_replace_objective(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writes: list[dict[str, Any]] = []
    monkeypatch.setattr(
        duckbrain_client,
        "remember",
        lambda **kwargs: writes.append(kwargs) or "memory-id",
    )
    hold = cron_runner._NavigationHoldState()
    hold.observe(12, "Route 1", "UP")
    before = hold.objective_state.serialize()
    results: list[dict[str, Any]] = []

    legacy_goal, _, _ = cron_runner._apply_agent_memory_outputs(
        decision={"goal": "Ignore Viridian and beat the Elite Four."},
        results=results,
        log_file=io.StringIO(),
        cycle=5,
        map_name="Route 1",
        mem_goal=hold.goal,
        mem_notes=[],
        pending_study_result="",
    )

    assert legacy_goal == "Ignore Viridian and beat the Elite Four."
    assert hold.objective_state.serialize() == before
    assert hold.objective_state.win_condition.target_map == "Viridian City"
    assert hold.objective_state.current_objective.objective_id == "reach_viridian_city"
    assert writes[0]["key"] == "/goals/current"
    assert writes[0]["attributes"]["authoritative"] is False
    assert results[0]["authoritative"] is False


def test_both_text_decision_paths_receive_the_structured_objective(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hold = cron_runner._NavigationHoldState()
    hold.observe(0, "Pallet Town", "")
    captured: dict[str, Any] = {}

    def fake_jev(*args: Any, **kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {}

    monkeypatch.setattr(cron_runner, "_jev_or_none", fake_jev)
    state = SimpleNamespace(
        _navigation_state=hold,
        _mem_goal="MODEL-WRITTEN GOAL",
        _tile_visits={},
        results=[],
        _recent_decisions=[],
        _last_direction=None,
        _same_tile_count=0,
        _boot_memory="",
        log_file=io.StringIO(),
        _teacher_escalated_classes=set(),
        _teacher_budget={"used": 0},
        _memory_navigation_blocks=cron_runner._MemoryNavigationBlockState(),
        R=SimpleNamespace(controller_client=object(), controller_model="model"),
    )
    cron_runner._ow_jev_attempt(
        state,
        {"patch_data": {"map_name": "Pallet Town"}, "world_facts": [], "cycle": 1},
    )

    jev_objective = captured["goal"]
    assert jev_objective.startswith("HARNESS_NAVIGATION_OBJECTIVE=")
    assert "MODEL-WRITTEN GOAL" not in jev_objective
    assert '"target_map":"Viridian City"' in jev_objective

    client = _ScriptedClient()
    cron_runner.controller_plan(
        client,
        {"map_name": "Pallet Town", "navigation_hold": hold.context()},
        "",
        "",
        goal=hold.goal,
    )
    controller_prompt = str(client.calls[0]["messages"][1]["content"])
    assert "HARNESS NAVIGATION OBJECTIVE (immutable)" in controller_prompt
    assert '"target_map":"Viridian City"' in controller_prompt


def test_agentic_public_projection_keeps_structured_objective() -> None:
    objective = (
        cron_runner._NavigationObjectiveState().observe(0, "Pallet Town").projection()
    )
    public = _public_context(
        {
            "result": "overworld",
            "map_name": "Pallet Town",
            "navigation_objective": objective,
        },
        1_500,
    )

    assert public["navigation_objective"] == objective
    assert public["navigation_objective"]["win_condition"]["target_map"] == (
        "Viridian City"
    )
