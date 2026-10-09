"""Regression coverage for collision-blocked memory-navigation position pins."""

from __future__ import annotations

from io import StringIO
from types import SimpleNamespace
from typing import Any

import pytest

import cron_runner
from src.core import duckbrain_client

_ROUTE_KEY = "/world/path/Red-s-House-1F->Red-s-House-2F"


def _observation(
    *,
    tile: tuple[int, int] = (2, 7),
    up_tile: str = "floor",
) -> dict[str, Any]:
    return {
        "result": "overworld",
        "map_id": 37,
        "map_name": "Red's House 1F",
        "player_tile_x": tile[0],
        "player_tile_y": tile[1],
        "adjacent": {
            "up": up_tile,
            "down": "floor",
            "left": "floor",
            "right": "floor",
        },
        "adjacent_walkability": {
            "up": "walkable",
            "down": "walkable",
            "left": "walkable",
            "right": "walkable",
        },
        "collision_grid": ".....\n.....\n..O..\n.....\n.....",
    }


@pytest.fixture
def proven_route(monkeypatch: pytest.MonkeyPatch) -> None:
    record = {
        "key": _ROUTE_KEY,
        "created_at": "2026-10-09T19:26:56+00:00",
        "attributes": {
            "crossing_direction": "RIGHT",
            "door_tile": {"x": 6, "y": 1},
            "arrival_tile": {"x": 7, "y": 1},
        },
    }
    monkeypatch.setattr(duckbrain_client, "recall", lambda **_kwargs: [record])


def test_repeated_blocked_memory_step_replans_after_threshold(
    proven_route: None,
) -> None:
    """dg1009b: three failed UP attempts at 37:2,7 must make route try RIGHT."""
    observation = _observation()
    state = cron_runner._MemoryNavigationBlockState()
    plans: list[list[str]] = []

    for _ in range(cron_runner.NAV_MEMORY_BLOCK_LIMIT + 1):
        decision = cron_runner._memory_navigation_decision(
            observation,
            block_state=state,
        )
        assert decision["result"] == "hit"
        plans.append(decision["plan"])
        state.note_attempt(observation, decision, decision["plan"])

    assert (
        plans[: cron_runner.NAV_MEMORY_BLOCK_LIMIT]
        == [["UP"]] * cron_runner.NAV_MEMORY_BLOCK_LIMIT
    )
    assert plans[-1] == ["RIGHT"]
    assert state.blocked_directions == {"UP"}
    assert decision["replanned_from_blocked"] == ["UP"]


def test_unblocked_memory_route_keeps_existing_step(proven_route: None) -> None:
    state = cron_runner._MemoryNavigationBlockState()

    decision = cron_runner._memory_navigation_decision(
        _observation(),
        block_state=state,
    )

    assert decision["result"] == "hit"
    assert decision["plan"] == ["UP"]
    assert "replanned_from_blocked" not in decision
    assert state.blocked_directions == set()


def test_spatial_collision_suppresses_direction_until_tile_changes(
    proven_route: None,
) -> None:
    state = cron_runner._MemoryNavigationBlockState()
    blocked_tile = _observation(up_tile="wall")

    first = cron_runner._memory_navigation_decision(
        blocked_tile,
        block_state=state,
    )
    same_tile_fresh_spatial = cron_runner._memory_navigation_decision(
        _observation(),
        block_state=state,
    )
    moved_tile = cron_runner._memory_navigation_decision(
        _observation(tile=(3, 7)),
        block_state=state,
    )

    assert first["plan"] == ["RIGHT"]
    assert first["replanned_from_blocked"] == ["UP"]
    assert same_tile_fresh_spatial["plan"] == ["RIGHT"]
    assert moved_tile["plan"] == ["UP"]
    assert state.blocked_directions == set()


def test_teacher_collision_patch_suppresses_memory_step(proven_route: None) -> None:
    observation = _observation()
    state = cron_runner._MemoryNavigationBlockState()

    events = state.remember_teacher_patch(
        observation,
        {
            "patch": {
                "instruction_patch": (
                    "use ROM collision truth and treat UP as blocked at the current tile"
                )
            }
        },
    )
    decision = cron_runner._memory_navigation_decision(
        observation,
        block_state=state,
    )

    assert [event["reason"] for event in events] == ["teacher_collision_patch"]
    assert decision["plan"] == ["RIGHT"]
    assert decision["replanned_from_blocked"] == ["UP"]


def test_final_plan_guard_cannot_reintroduce_suppressed_step() -> None:
    state = cron_runner._MemoryNavigationBlockState(
        current_tile=(37, 2, 7),
        blocked_directions={"UP"},
    )
    runtime = SimpleNamespace(
        _memory_navigation_blocks=state,
        results=[],
        log_file=StringIO(),
    )

    guarded = cron_runner._ow_memory_navigation_guard(
        runtime,
        7,
        ["UP", "A"],
        {"active": True, "blocked_return_direction": "DOWN"},
    )

    assert guarded == ["RIGHT", "A"]
    assert runtime.results == [
        {
            "cycle": 8,
            "event": "memory_navigation_step_suppressed",
            "tile": (37, 2, 7),
            "blocked_directions": ["UP"],
            "forbidden_directions": ["DOWN", "UP"],
            "original_plan": ["UP", "A"],
            "guarded_plan": ["RIGHT", "A"],
        }
    ]
