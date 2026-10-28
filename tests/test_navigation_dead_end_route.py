"""DF-AIPP-17: the planner must route out of a dead-end map.

Red's House 1F (map 37) is a dead end once its only unvisited edge (to Red's
House 2F, map 38) becomes a visited edge: every remaining exit leads back
through Pallet Town, which the objective ladder requires anyway (Pallet Town is
the only way to Route 1). Before this fix the planner planned to nobody, the
hold guard rewrote the controller's DOWN, and the run alternated between
(37,3,6) and (37,3,7) for the rest of the tick.
"""

from __future__ import annotations

from io import StringIO
from typing import Any

import pytest

import cron_runner
from src.core import duckbrain_client

PATH = "/world/path/"


def _observation(
    *,
    map_id: int,
    map_name: str,
    tile: tuple[int, int],
    walkability: dict[str, str] | None = None,
    collision_grid: str | None = None,
) -> dict[str, Any]:
    return {
        "result": "overworld",
        "map_id": map_id,
        "map_name": map_name,
        "player_tile_x": tile[0],
        "player_tile_y": tile[1],
        "player_x": tile[0],
        "player_y": tile[1],
        "adjacent": {"up": "floor", "down": "floor", "left": "floor", "right": "floor"},
        "adjacent_walkability": walkability
        or {
            "up": "walkable",
            "down": "walkable",
            "left": "walkable",
            "right": "walkable",
        },
        "collision_grid": collision_grid
        if collision_grid is not None
        else ".....\n.....\n..↑..\n.....\n.....",
        "visible_exits": [],
    }


def _record(
    key: str,
    *,
    created_at: str,
    attributes: dict[str, Any],
) -> dict[str, Any]:
    return {
        "id": key,
        "key": key,
        "created_at": created_at,
        "status": "active",
        "attributes": attributes,
    }


def _install_records(
    monkeypatch: pytest.MonkeyPatch, records: list[dict[str, Any]]
) -> None:
    def recall(**kwargs: Any) -> list[dict[str, Any]]:
        key = kwargs.get("key")
        prefix = kwargs.get("key_prefix")
        limit = int(kwargs.get("limit", 10))
        return [
            record
            for record in records
            if (key is None or record["key"] == key)
            and (prefix is None or str(record["key"]).startswith(prefix))
        ][:limit]

    monkeypatch.setattr(duckbrain_client, "recall", recall)


def _house_records(*, arrival_tile: dict[str, int] | None) -> list[dict[str, Any]]:
    """1F -> 2F (a proven edge) and Pallet Town -> 1F (the edge the run came by)."""
    inbound: dict[str, Any] = {
        "fact_type": "path_transition",
        "from_map": {"id": 0, "name": "Pallet Town"},
        "to_map": {"id": 37, "name": "Red's House 1F"},
        "crossing_direction": "UP",
        "door_tile": {"x": 5, "y": 6},
    }
    if arrival_tile is not None:
        inbound["arrival_tile"] = arrival_tile
    return [
        _record(
            f"{PATH}Red-s-House-1F->Red-s-House-2F",
            created_at="2026-10-27T09:00:00+00:00",
            attributes={
                "fact_type": "path_transition",
                "from_map": {"id": 37, "name": "Red's House 1F"},
                "to_map": {"id": 38, "name": "Red's House 2F"},
                "crossing_direction": "UP",
                "door_tile": {"x": 7, "y": 2},
                "arrival_tile": {"x": 7, "y": 1},
            },
        ),
        _record(
            f"{PATH}Pallet-Town->Red-s-House-1F",
            created_at="2026-10-27T09:05:00+00:00",
            attributes=inbound,
        ),
    ]


HOUSE_VISITED = ((0, "Pallet Town"), (38, "Red's House 2F"))


def test_dead_end_map_escapes_to_objective_gateway(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """At the arrival mat, the escape replays the reverse of the edge in."""
    _install_records(monkeypatch, _house_records(arrival_tile={"x": 2, "y": 7}))
    route = cron_runner._memory_navigation_route(
        _observation(
            map_id=37,
            map_name="Red's House 1F",
            tile=(2, 7),
            # The 1F door mat classifies as "void"/unknown, never "blocked".
            walkability={
                "up": "walkable",
                "down": "unknown",
                "left": "walkable",
                "right": "walkable",
            },
            collision_grid="...##\n.....\n..↑..\n?????\n?????",
        ),
        visited_maps=HOUSE_VISITED,
    )

    assert route is not None
    assert route["route_kind"] == cron_runner.DEAD_END_ESCAPE_ROUTE_KIND
    assert route["derivation"] == "reverse_of_proven_edge"
    assert route["to_map"] == "Pallet-Town"
    assert route["to_map_id"] == 0
    assert route["destination_visited"] is True
    assert route["objective_gateway"] is True
    assert route["gateway_objective_rank"] == 1
    assert route["door_tile"] == {"x": 2, "y": 7}
    assert route["plan"] == ["DOWN"]
    assert route["reason"] == "no_executable_route_to_unvisited_map"


def test_dead_end_escape_walks_toward_the_door_tile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Away from the mat the escape is a real route step, not a lateral wiggle."""
    _install_records(monkeypatch, _house_records(arrival_tile={"x": 2, "y": 7}))
    route = cron_runner._memory_navigation_route(
        _observation(map_id=37, map_name="Red's House 1F", tile=(3, 7)),
        visited_maps=HOUSE_VISITED,
    )

    assert route is not None
    assert route["route_kind"] == cron_runner.DEAD_END_ESCAPE_ROUTE_KIND
    assert route["plan"] == ["LEFT"]
    assert route["mechanism"] == "collision_grid_path"


def test_unvisited_destination_outranks_dead_end_escape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """New ground still wins: the escape only exists for dead ends."""
    _install_records(monkeypatch, _house_records(arrival_tile={"x": 2, "y": 7}))
    route = cron_runner._memory_navigation_route(
        _observation(map_id=37, map_name="Red's House 1F", tile=(7, 2)),
        visited_maps=((0, "Pallet Town"),),
    )

    assert route is not None
    assert route["route_kind"] == "unvisited"
    assert route["destination_visited"] is False
    assert route["to_map"] == "Red-s-House-2F"
    assert route["objective_gateway"] is False


def test_escape_refuses_non_ladder_destination(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pallet Town must not plan itself back into the house it just left."""
    _install_records(
        monkeypatch,
        [
            _record(
                f"{PATH}Pallet-Town->Red-s-House-1F",
                created_at="2026-10-27T09:00:00+00:00",
                attributes={
                    "fact_type": "path_transition",
                    "from_map": {"id": 0, "name": "Pallet Town"},
                    "to_map": {"id": 37, "name": "Red's House 1F"},
                    "crossing_direction": "UP",
                    "door_tile": {"x": 5, "y": 6},
                    "arrival_tile": {"x": 5, "y": 5},
                },
            ),
            _record(
                f"{PATH}Red-s-House-1F->Pallet-Town",
                created_at="2026-10-27T09:10:00+00:00",
                attributes={
                    "fact_type": "path_transition",
                    "from_map": {"id": 37, "name": "Red's House 1F"},
                    "to_map": {"id": 0, "name": "Pallet Town"},
                    "crossing_direction": "DOWN",
                    "door_tile": {"x": 2, "y": 7},
                    "arrival_tile": {"x": 5, "y": 6},
                },
            ),
        ],
    )
    decision = cron_runner._memory_navigation_decision(
        _observation(map_id=0, map_name="Pallet Town", tile=(5, 6)),
        visited_maps=((0, "Pallet Town"), (37, "Red's House 1F")),
    )

    assert decision["result"] == "miss"
    assert decision["reason"] == "no_proven_route_to_unvisited_map"


def test_reverse_escape_skipped_without_arrival_tile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A record with no landing tile cannot yield a reverse route."""
    _install_records(monkeypatch, _house_records(arrival_tile=None))
    decision = cron_runner._memory_navigation_decision(
        _observation(map_id=37, map_name="Red's House 1F", tile=(2, 7)),
        visited_maps=HOUSE_VISITED,
    )

    assert decision["result"] == "miss"
    assert decision["reason"] == "no_proven_route_to_unvisited_map"


def _hold_context() -> dict[str, Any]:
    return {
        "active": True,
        "current_map_id": 37,
        "current_map_name": "Red's House 1F",
        "previous_map_id": 0,
        "previous_map_name": "Pallet Town",
        "entry_direction": "UP",
        "blocked_return_direction": "DOWN",
        "visited_maps": ["Pallet Town", "Red's House 1F", "Red's House 2F"],
        "goal": "Advance through Red's House 1F toward the next new map.",
    }


def test_hold_guard_skips_substitution_for_planner_escape() -> None:
    """The guard must not turn the authored exit press back into the wall."""
    escape = {
        "key": f"{PATH}Pallet-Town->Red-s-House-1F",
        "to_map": "Pallet-Town",
        "door_tile": {"x": 2, "y": 7},
    }
    plan, event = cron_runner._guard_navigation_plan(
        ["DOWN"], _hold_context(), {"UP"}, escape
    )

    assert plan == ["DOWN"]
    assert event is not None
    assert event["outcome"] == "skipped"
    assert event["guarded_plan"] == ["DOWN"]
    assert event["escape_destination"] == "Pallet-Town"
    assert event["memory_route_key"] == escape["key"]


def test_hold_guard_still_replaces_without_an_escape_route() -> None:
    """Negative arm: the original held-edge substitution stays intact."""
    plan, event = cron_runner._guard_navigation_plan(["DOWN"], _hold_context(), set())

    assert plan == ["UP"]
    assert event is not None
    assert event["outcome"] == "applied"


def test_escape_plan_survives_the_full_hold_filter() -> None:
    """HOLD-1 end to end: the escape press reaches the emulator unchanged."""
    escape = {
        "key": f"{PATH}Pallet-Town->Red-s-House-1F",
        "to_map": "Pallet-Town",
        "door_tile": {"x": 2, "y": 7},
    }
    state = type(
        "State",
        (),
        {
            "_memory_navigation_blocks": cron_runner._MemoryNavigationBlockState(),
            "results": [],
            "log_file": StringIO(),
        },
    )()
    decision = {
        "plan": ["DOWN"],
        "memory_navigation": {
            "result": "hit",
            "route_kind": cron_runner.DEAD_END_ESCAPE_ROUTE_KIND,
            **escape,
        },
    }

    plan = cron_runner._ow_navigation_guard(
        state, 0, ["DOWN"], decision, _hold_context(), None
    )

    assert plan == ["DOWN"]
    assert state.results[-1]["event"] == "navigation_hold_guard"
    assert state.results[-1]["outcome"] == "skipped"
    assert decision["_navigation_hold_applied"] is False


def test_path_memory_write_prefers_settled_arrival_tile() -> None:
    """The stale transition-cycle tile must not become the reverse door."""
    transition = {
        "from_map_id": 0,
        "from_map_name": "Pallet Town",
        "to_map_id": 37,
        "to_map_name": "Red's House 1F",
        "crossing_direction": "UP",
        "departure_tile": {"x": 5, "y": 6},
        "arrival_tile": {"x": 2, "y": 7},
    }
    write = cron_runner._path_memory_write(
        transition,
        observation=_observation(map_id=37, map_name="Red's House 1F", tile=(5, 5)),
        evidence={"run_id": "test"},
        confidence=1.0,
    )

    assert write is not None
    assert write["attributes"]["arrival_tile"] == {"x": 2, "y": 7}


def test_path_memory_write_falls_back_to_observation_tile() -> None:
    """Negative arm: without a settled tile the observation is still used."""
    transition = {
        "from_map_id": 0,
        "from_map_name": "Pallet Town",
        "to_map_id": 37,
        "to_map_name": "Red's House 1F",
        "crossing_direction": "UP",
        "departure_tile": {"x": 5, "y": 6},
    }
    write = cron_runner._path_memory_write(
        transition,
        observation=_observation(map_id=37, map_name="Red's House 1F", tile=(5, 5)),
        evidence={"run_id": "test"},
        confidence=1.0,
    )

    assert write is not None
    assert write["attributes"]["arrival_tile"] == {"x": 5, "y": 5}


def test_settle_arrival_tile_waits_for_the_warp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The landing tile is read after the destination coords are written.

    The warp fade repeats the stale source tile for several reads, so a helper
    that returns on the first agreeing pair reports (5,5) — the bug this
    function exists to fix.
    """
    reads = [
        {
            "map_id": 37,
            "player_tile_x": 5,
            "player_tile_y": 5,
        },  # map flipped, still stale
        {"map_id": 37, "player_tile_x": 5, "player_tile_y": 5},  # fade, stale again
        {"map_id": 37, "player_tile_x": 5, "player_tile_y": 5},  # fade, stale again
        {"map_id": 37, "player_tile_x": 2, "player_tile_y": 7},  # warp applied
        {"map_id": 37, "player_tile_x": 2, "player_tile_y": 7},  # stable
    ]

    class _Reader:
        def __init__(self) -> None:
            self.calls = 0

        def observe(self) -> dict[str, Any]:
            observation = reads[min(self.calls, len(reads) - 1)]
            self.calls += 1
            return dict(observation)

    class _Emu:
        def wait(self, frames: int) -> None:
            assert frames == cron_runner.ARRIVAL_TILE_SETTLE_FRAMES

    reader = _Reader()
    state = type(
        "State", (), {"R": type("Run", (), {"ram_reader": reader, "emu": _Emu()})()}
    )()
    monkeypatch.setattr(cron_runner, "USE_RAM_READER", True)

    assert cron_runner._settle_arrival_tile(state, 37) == (2, 7)
    assert reader.calls == cron_runner.ARRIVAL_TILE_SETTLE_READS


def test_settle_arrival_tile_ignores_source_map_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A read that still reports the source map is not a landing tile."""
    reads = [
        {"map_id": 0, "player_tile_x": 5, "player_tile_y": 6},
        {"map_id": 0, "player_tile_x": 5, "player_tile_y": 5},
    ]

    class _Reader:
        def __init__(self) -> None:
            self.calls = 0

        def observe(self) -> dict[str, Any]:
            observation = reads[min(self.calls, len(reads) - 1)]
            self.calls += 1
            return dict(observation)

    class _Emu:
        def wait(self, frames: int) -> None:
            del frames

    state = type(
        "State", (), {"R": type("Run", (), {"ram_reader": _Reader(), "emu": _Emu()})()}
    )()
    monkeypatch.setattr(cron_runner, "USE_RAM_READER", True)

    assert cron_runner._settle_arrival_tile(state, 37) is None


class _StepReader:
    """RAM reader whose tile advances one entry per emulator button press."""

    def __init__(self, tiles: list[tuple[int, int, int]]) -> None:
        self._tiles = tiles
        self.press = 0

    def current_map_id(self) -> int:
        return self._tiles[self.press][0]

    def player_tile_x(self) -> int:
        return self._tiles[self.press][1]

    def player_tile_y(self) -> int:
        return self._tiles[self.press][2]

    def is_moving(self) -> bool:
        return False


class _StepEmu:
    def __init__(self, reader: _StepReader) -> None:
        self._reader = reader

    def press_button(self, button: str, frames: int = 5) -> None:
        del button, frames
        self._reader.press = min(self._reader.press + 1, len(self._reader._tiles) - 1)

    def fast_forward(self, frames: int) -> None:
        del frames


def _execution_state(reader: _StepReader) -> Any:
    return type(
        "State",
        (),
        {
            "R": type("Run", (), {"ram_reader": reader, "emu": _StepEmu(reader)})(),
            "_same_dir": None,
            "_same_dir_count": 0,
            "_a_press_count": 0,
            "_last_direction": None,
            "_last_action_button": None,
        },
    )()


def test_corridor_walk_is_not_a_direction_lock() -> None:
    """Five productive LEFT presses down a corridor never read as locked."""
    reader = _StepReader(
        [(37, 7, 7), (37, 6, 7), (37, 5, 7), (37, 4, 7), (37, 3, 7), (37, 2, 7)]
    )
    state = _execution_state(reader)

    cron_runner._ow_execute_plan(state, ["LEFT"] * 5)

    assert state._same_dir == "LEFT"
    assert state._same_dir_count == 0


def test_pressing_into_a_wall_still_locks() -> None:
    """Negative arm: no movement, same direction, still counts toward recovery."""
    reader = _StepReader([(37, 3, 7)])
    state = _execution_state(reader)

    cron_runner._ow_execute_plan(state, ["LEFT"] * cron_runner.MAX_STUCK_SAME_DIR)

    assert state._same_dir == "LEFT"
    assert state._same_dir_count == cron_runner.MAX_STUCK_SAME_DIR


def test_summary_counts_escapes_apart_from_new_ground_hits() -> None:
    """An escape is a hit, but the run summary must not report it as progress."""
    escape_row = {
        "memory_navigation": {
            "result": "hit",
            "key": f"{PATH}Pallet-Town->Red-s-House-1F",
            "route_kind": cron_runner.DEAD_END_ESCAPE_ROUTE_KIND,
        }
    }
    unvisited_row = {
        "memory_navigation": {
            "result": "hit",
            "key": f"{PATH}Red-s-House-1F->Red-s-House-2F",
            "route_kind": "unvisited",
        }
    }

    hits, fallbacks, escapes = cron_runner._count_memory_navigation(escape_row, 0, 0, 0)
    assert (hits, fallbacks, escapes) == (1, 0, 1)

    hits, fallbacks, escapes = cron_runner._count_memory_navigation(
        unvisited_row, hits, fallbacks, escapes
    )
    assert (hits, fallbacks, escapes) == (2, 0, 1)
