"""HOLD-1: map transitions remain held across decision cycles."""

from __future__ import annotations

from io import StringIO
from types import SimpleNamespace
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


# ── DF-AIPP-17: a blocked forward direction must not replace the exit ──

# Map 37 (Red's House 1F) collision truth from the Blue SGB ROM used by
# data/boot.state — the same grid tests/test_memory_navigation_pin.py pins.
_MAP_37_COLLISION = (
    "########",
    "##.#....",
    "........",
    "........",
    "...##...",
    "...##...",
    "........",
    "........",
)


def _map_37_tile_observation(tile: tuple[int, int]) -> dict[str, Any]:
    """Spatial description for one map-37 tile, from real ROM collision truth."""
    tile_x, tile_y = tile
    rows: list[str] = []
    for y in range(tile_y - 2, tile_y + 3):
        cells: list[str] = []
        for x in range(tile_x - 2, tile_x + 3):
            if (x, y) == tile:
                cells.append("↑")
            elif 0 <= y < len(_MAP_37_COLLISION) and 0 <= x < len(_MAP_37_COLLISION[y]):
                cells.append(_MAP_37_COLLISION[y][x])
            else:
                cells.append("?")
        rows.append("".join(cells))
    offsets = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
    return {
        "result": "overworld",
        "map_id": 37,
        "map_name": "Red's House 1F",
        "player_tile_x": tile_x,
        "player_tile_y": tile_y,
        "adjacent": {"up": "wall", "down": "floor", "left": "floor", "right": "floor"},
        "adjacent_walkability": {
            direction.lower(): (
                "walkable"
                if _MAP_37_COLLISION[tile_y + dy][tile_x + dx] == "."
                else "blocked"
            )
            for direction, (dx, dy) in offsets.items()
        },
        "collision_grid": "\n".join(rows),
    }


def _reds_house_1f_hold() -> cron_runner._NavigationHoldState:
    """The held edge from run df1027a: Pallet Town -> Red's House 1F via UP."""
    state = cron_runner._NavigationHoldState()
    state.observe(0, "Pallet Town", "")
    state.observe(37, "Red's House 1F", "UP")
    assert state.blocked_return_direction == "DOWN"
    assert state.entry_direction == "UP"
    return state


def test_map_37_dead_end_tile_has_up_wall_and_down_door() -> None:
    """The dead-end premise: at (37,3,6) UP is a wall and DOWN is the exit."""
    observation = _map_37_tile_observation((3, 6))

    assert cron_runner._blocked_spatial_directions(observation) == {"up"}
    assert cron_runner._memory_walkability(observation)["down"] == "walkable"


def test_guard_declines_replacement_when_forward_direction_is_blocked() -> None:
    """DF-AIPP-17: DOWN is the only legal exit, so an UP wall cannot replace it."""
    state = _reds_house_1f_hold()
    collision = cron_runner._blocked_spatial_directions(
        _map_37_tile_observation((3, 6))
    )

    plan, event = cron_runner._guard_navigation_plan(
        ["DOWN", "DOWN"], state.context(), collision
    )

    assert plan == ["DOWN", "DOWN"]
    assert event is not None
    assert event["mechanism"] == "reverse_edge_guard"
    assert event["outcome"] == "declined"
    assert event["blocked_direction"] == "DOWN"
    assert event["replacement_direction"] == "UP"
    assert event["replacement_blocked"] is True
    assert event["collision_blocked_directions"] == ["UP"]
    assert event["original_plan"] == ["DOWN", "DOWN"]
    assert event["guarded_plan"] == ["DOWN", "DOWN"]
    assert "UP is collision-blocked" in event["reason"]


def test_guard_still_substitutes_when_forward_direction_is_open() -> None:
    """The shipped default is untouched wherever the completed edge is walkable."""
    state = _reds_house_1f_hold()

    plan, event = cron_runner._guard_navigation_plan(
        ["DOWN", "DOWN"], state.context(), set()
    )

    assert plan == ["UP", "UP"]
    assert event is not None
    assert event["outcome"] == "applied"
    assert event["replacement_blocked"] is False
    assert event["guarded_plan"] == ["UP", "UP"]


def test_guard_keeps_substitution_when_the_exit_is_also_blocked() -> None:
    """A blocked exit is not a legal exit: the guard keeps its reverse-edge veto."""
    state = _reds_house_1f_hold()

    plan, event = cron_runner._guard_navigation_plan(
        ["DOWN"], state.context(), {"UP", "DOWN"}
    )

    assert plan == ["UP"]
    assert event is not None
    assert event["outcome"] == "applied"
    assert event["collision_blocked_directions"] == ["DOWN", "UP"]


def test_final_plan_guard_keeps_the_door_exit_and_stays_truthful() -> None:
    """The main-loop guard must not re-substitute the wall the controller refused."""
    observation = _map_37_tile_observation((3, 6))
    state = _reds_house_1f_hold()
    runtime = SimpleNamespace(
        _memory_navigation_blocks=cron_runner._MemoryNavigationBlockState(
            current_tile=(37, 3, 6),
            blocked_directions={"UP"},
        ),
        results=[],
        log_file=StringIO(),
    )
    decision: dict[str, Any] = {}

    plan = cron_runner._ow_navigation_guard(
        runtime, 24, ["DOWN", "DOWN"], decision, state.context(), observation
    )
    executed = cron_runner._ow_memory_navigation_guard(
        runtime, 24, plan, state.context()
    )

    assert plan == ["DOWN", "DOWN"]
    assert executed == ["DOWN", "DOWN"]
    assert decision["_navigation_hold_applied"] is False
    row = runtime.results[0]
    assert row["event"] == "navigation_hold_guard"
    assert row["outcome"] == "declined"
    assert row["blocked_direction"] == "DOWN"
    assert row["executed_plan"] == ["DOWN", "DOWN"]


def test_controller_hold_uses_live_collision_truth() -> None:
    """The controller path declines the same substitution before the main loop."""
    client = _ScriptedClient('{"plan": ["DOWN"], "intent": "leave through the door"}')
    spatial = _map_37_tile_observation((3, 6))
    spatial["navigation_hold"] = _reds_house_1f_hold().context()

    decision = cron_runner.controller_plan(
        client, spatial, "UP", "entered Red's House 1F"
    )

    assert decision["plan"] == ["DOWN"]
    assert decision["navigation_hold_event"]["outcome"] == "declined"
    assert decision["navigation_hold_event"]["guarded_plan"] == ["DOWN"]
