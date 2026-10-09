"""Regression coverage for collision-blocked memory-navigation position pins."""

from __future__ import annotations

from io import StringIO
from types import SimpleNamespace
from typing import Any

import pytest

import cron_runner
from src.core import duckbrain_client

_ROUTE_KEY = "/world/path/Red-s-House-1F->Red-s-House-2F"

# Map 37 collision truth from the Blue SGB ROM used by data/boot.state. The
# first 5x5 observation produced from it is byte-for-byte the grid recorded in
# cron_logs/run_dfarm12_verify_1611.jsonl at cycle 5.
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
_STEP_DELTA = {
    "UP": (0, -1),
    "DOWN": (0, 1),
    "LEFT": (-1, 0),
    "RIGHT": (1, 0),
}


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


def _map_37_observation(tile: tuple[int, int]) -> dict[str, Any]:
    """Build the real 5x5 RAM collision window around one map-37 tile."""
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

    observation = _observation(tile=tile)
    observation["collision_grid"] = "\n".join(rows)
    observation["adjacent_walkability"] = {
        direction.lower(): (
            "walkable"
            if _MAP_37_COLLISION[tile_y + dy][tile_x + dx] == "."
            else "blocked"
        )
        for direction, (dx, dy) in _STEP_DELTA.items()
    }
    return observation


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
    blocked_tile["adjacent_walkability"]["up"] = "blocked"
    blocked_tile["collision_grid"] = ".....\n..#..\n..O..\n.....\n....."

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


def test_collision_grid_path_replans_around_blocked_direct_step() -> None:
    """A blocked shortest-axis step must cause a route search, not suppression."""
    result = cron_runner._memory_route_plan(
        (2, 2),
        (2, 0),
        "RIGHT",
        {
            "up": "blocked",
            "down": "walkable",
            "left": "walkable",
            "right": "walkable",
        },
        ".....\n..#..\n..↑..\n.....\n.....",
    )

    assert result == (["LEFT"], "collision_grid_path")


def test_precise_collision_grid_overrides_coarse_object_label(
    proven_route: None,
) -> None:
    """The map-block object label must not veto a walkable world-tile step."""
    observation = _map_37_observation((6, 3))
    observation["adjacent"]["up"] = "object"
    state = cron_runner._MemoryNavigationBlockState()

    decision = cron_runner._memory_navigation_decision(
        observation,
        block_state=state,
    )

    assert (
        cron_runner._walkability_from_collision_grid(observation["collision_grid"])[
            "up"
        ]
        == "walkable"
    )
    assert state.blocked_directions == set()
    assert decision["result"] == "hit"
    assert decision["plan"] == ["UP"]
    assert decision["mechanism"] == "collision_grid_path"


def test_map_37_collision_route_reaches_exit_tile(
    proven_route: None,
) -> None:
    """Replanning each real 5x5 window reaches (6,1) without crossing a wall."""
    tile = (5, 5)
    state = cron_runner._MemoryNavigationBlockState()
    visited = [tile]

    assert _map_37_observation(tile)["collision_grid"] == (
        ".....\n##...\n##↑..\n.....\n....."
    )
    for _ in range(8):
        if tile == (6, 1):
            break
        observation = _map_37_observation(tile)
        decision = cron_runner._memory_navigation_decision(
            observation,
            block_state=state,
        )
        assert decision["result"] == "hit"
        assert decision["mechanism"] == "collision_grid_path"
        step = decision["plan"][0]
        dx, dy = _STEP_DELTA[step]
        tile = (tile[0] + dx, tile[1] + dy)
        assert _MAP_37_COLLISION[tile[1]][tile[0]] == "."
        visited.append(tile)

    assert tile == (6, 1)
    assert visited == [(5, 5), (5, 4), (5, 3), (5, 2), (5, 1), (6, 1)]

    crossing = cron_runner._memory_navigation_decision(
        _map_37_observation(tile),
        block_state=state,
    )
    assert crossing["plan"] == ["RIGHT"]
    assert crossing["mechanism"] == "proven_crossing"
