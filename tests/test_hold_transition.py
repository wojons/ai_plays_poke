"""HOLD-1: map transitions remain held across decision cycles."""

from __future__ import annotations

from typing import Any

import cron_runner


class _ScriptedClient:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[dict[str, Any]] = []

    def chat_completion(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {"content": self.content}


def test_controller_refuses_reverse_edge_from_navigation_context() -> None:
    """The pre-HOLD controller returned DOWN unchanged and re-entered Pallet."""
    client = _ScriptedClient('{"plan": ["DOWN", "DOWN"], "intent": "go back south"}')
    spatial = {
        "map_id": 12,
        "map_name": "Route 1",
        "player_tile_x": 10,
        "player_tile_y": 35,
        "navigation_hold": {
            "active": True,
            "current_map_id": 12,
            "current_map_name": "Route 1",
            "previous_map_id": 0,
            "previous_map_name": "Pallet Town",
            "entry_direction": "UP",
            "blocked_return_direction": "DOWN",
            "visited_maps": ["Pallet Town", "Route 1"],
            "goal": "Advance through Route 1 without returning to Pallet Town.",
        },
    }

    decision = cron_runner.controller_plan(client, spatial, "UP", "entered Route 1")

    assert decision["plan"] == ["UP", "UP"]
    assert decision["navigation_hold_event"]["mechanism"] == "reverse_edge_guard"
    assert decision["navigation_hold_event"]["blocked_direction"] == "DOWN"
    prompt = str(client.calls[0]["messages"][1]["content"])
    assert "NAVIGATION HOLD: transition Pallet Town -> Route 1 is complete" in prompt
    assert "never press DOWN" in prompt


def test_map_edge_memory_persists_goal_and_guard_across_cycles() -> None:
    state = cron_runner._NavigationHoldState()

    assert state.observe(0, "Pallet Town", "") is None
    transition = state.observe(12, "Route 1", "UP")

    assert transition is not None
    assert transition["event"] == "navigation_transition"
    assert transition["mechanism"] == "visited_map_edge_memory"
    assert transition["regression"] is False
    assert transition["blocked_return_direction"] == "DOWN"
    assert transition["visited_maps"] == ["Pallet Town", "Route 1"]
    assert "do not return to Pallet Town" in transition["persistent_goal"]

    first, first_event = cron_runner._guard_navigation_plan(
        ["DOWN", "LEFT"], state.context()
    )
    second, second_event = cron_runner._guard_navigation_plan(
        ["RIGHT", "DOWN"], state.context()
    )

    assert first == ["UP", "LEFT"]
    assert second == ["RIGHT", "UP"]
    assert first_event is not None
    assert second_event is not None
    assert first_event["reason"] == (
        "DOWN reverses the completed transition from Pallet Town to Route 1"
    )
    assert second_event["persistent_goal"] == state.goal


def test_forward_and_lateral_actions_are_unchanged() -> None:
    state = cron_runner._NavigationHoldState()
    state.observe(0, "Pallet Town", "")
    state.observe(12, "Route 1", "UP")

    plan, event = cron_runner._guard_navigation_plan(
        ["UP", "LEFT", "RIGHT", "A"], state.context()
    )

    assert plan == ["UP", "LEFT", "RIGHT", "A"]
    assert event is None


def test_reentering_visited_map_is_logged_as_regression_not_new_progress() -> None:
    state = cron_runner._NavigationHoldState()
    state.observe(0, "Pallet Town", "")
    state.observe(12, "Route 1", "UP")

    regression = state.observe(0, "Pallet Town", "DOWN")

    assert regression is not None
    assert regression["regression"] is True
    assert regression["visited_maps"] == ["Pallet Town", "Route 1"]
    assert "Return to Route 1" in regression["persistent_goal"]
    assert state.context()["active"] is False


class _FakeEmulator:
    def __init__(self) -> None:
        self.pressed: list[tuple[str, int]] = []
        self.forwarded: list[int] = []

    def press_button(self, button: str, *, frames: int) -> None:
        self.pressed.append((button, frames))

    def fast_forward(self, frames: int) -> None:
        self.forwarded.append(frames)


def test_recovery_cannot_step_back_through_held_edge() -> None:
    emu = _FakeEmulator()
    evidence: dict[str, Any] = {}

    strategy, description = cron_runner._escalating_recovery(
        emu,
        2,
        "UP",
        None,
        decision_out=evidence,
        forbidden_directions={"DOWN"},
    )

    assert strategy == "navigation_hold_recovery"
    assert "refused reverse-edge DOWN" in description
    assert emu.pressed == [("left", 60)]
    assert evidence["navigation_hold_recovery"] == {
        "mechanism": "reverse_edge_guard",
        "blocked_direction": "DOWN",
        "replacement_direction": "LEFT",
    }


def test_main_loop_wires_transition_memory_and_final_plan_guard() -> None:
    source = open(cron_runner.__file__, encoding="utf-8").read()

    observe_at = source.index("_navigation_state.observe(")
    decision_at = source.index("_jev_attempt = _jev_or_none(", observe_at)
    final_guard_at = source.index("plan, _final_hold_event = _guard_navigation_plan(")
    execute_at = source.index("# ── Execute the plan", final_guard_at)

    assert observe_at < decision_at
    assert final_guard_at < execute_at
    assert '"event": "navigation_hold_guard"' in source[final_guard_at:execute_at]
