"""NAV-MEM: deterministic route writes and bounded decision-context injection."""

from __future__ import annotations

import json
from io import StringIO
from types import SimpleNamespace
from typing import Any

import pytest

import cron_runner
from src.core import duckbrain_client


def _observation(
    *,
    map_id: int = 0,
    map_name: str = "Pallet Town",
    tile: tuple[int, int] = (6, 6),
) -> dict[str, Any]:
    return {
        "result": "overworld",
        "map_id": map_id,
        "map_name": map_name,
        "player_tile_x": tile[0],
        "player_tile_y": tile[1],
        "player_x": tile[0],
        "player_y": tile[1],
        "adjacent": {
            "up": "floor",
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
        "visible_exits": [],
    }


def _install_store(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    records: dict[str, dict[str, Any]] = {}
    writes: list[dict[str, Any]] = []

    def remember(**kwargs: Any) -> str:
        record = {
            "id": f"memory-{len(writes) + 1}",
            "status": "active",
            "created_at": f"2026-01-01T00:00:{len(writes):02d}+00:00",
            **kwargs,
        }
        records[str(kwargs["key"])] = record
        writes.append(record)
        return str(record["id"])

    def recall(**kwargs: Any) -> list[dict[str, Any]]:
        key = kwargs.get("key")
        prefix = kwargs.get("key_prefix")
        limit = int(kwargs.get("limit", 10))
        return [
            record
            for record in records.values()
            if (key is None or record["key"] == key)
            and (prefix is None or str(record["key"]).startswith(prefix))
        ][:limit]

    monkeypatch.setattr(duckbrain_client, "remember", remember)
    monkeypatch.setattr(duckbrain_client, "recall", recall)
    return records, writes


def test_observed_transition_writes_proven_path_and_updates_source_map_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    records, writes = _install_store(monkeypatch)
    written_keys: set[str] = set()
    results: list[dict[str, Any]] = []
    log_file = StringIO()

    cron_runner._populate_world_memory(
        observation=_observation(),
        run_id="nav-mem-test",
        cycle=1,
        results=results,
        log_file=log_file,
        written_keys=written_keys,
    )
    transition = {
        "event": "navigation_transition",
        "from_map_id": 0,
        "from_map_name": "Pallet Town",
        "to_map_id": 1,
        "to_map_name": "Route 1",
        "crossing_direction": "UP",
        "departure_tile": {"x": 6, "y": 0},
        "route_tiles": [
            {"x": 6, "y": 6},
            {"x": 6, "y": 5},
            {"x": 6, "y": 0},
        ],
        "regression": False,
    }
    cron_runner._populate_world_memory(
        observation=_observation(map_id=1, map_name="Route 1", tile=(10, 17)),
        run_id="nav-mem-test",
        cycle=2,
        results=results,
        log_file=log_file,
        written_keys=written_keys,
        transition=transition,
    )

    path = records["/world/path/Pallet-Town->Route-1"]
    assert path["attributes"]["door_tile"] == {"x": 6, "y": 0}
    assert path["attributes"]["route_tiles"] == transition["route_tiles"]
    assert path["attributes"]["to_map"] == {"id": 1, "name": "Route 1"}

    source_map = records["/world/map/0"]
    assert source_map["attributes"]["exits"] == [
        {
            "tile": {"x": 6, "y": 0},
            "destination": {"id": 1, "name": "Route 1"},
            "crossing_direction": "UP",
        }
    ]
    source_map_writes = [write for write in writes if write["key"] == "/world/map/0"]
    assert len(source_map_writes) == 2
    assert any(
        row["event"] == "world_memory_write"
        and row["key"] == "/world/path/Pallet-Town->Route-1"
        for row in results
    )

    recalled = cron_runner._populate_world_memory(
        observation=_observation(),
        run_id="nav-mem-restart-test",
        cycle=3,
        results=results,
        log_file=log_file,
        written_keys=set(),
    )
    assert any(fact.startswith("/world/map/0:") for fact in recalled)
    assert any(
        fact.startswith("/world/path/Pallet-Town->Route-1:") for fact in recalled
    )
    assert records["/world/map/0"]["attributes"]["exits"][0]["destination"] == {
        "id": 1,
        "name": "Route 1",
    }


def test_no_path_or_exit_write_without_observed_transition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    records, writes = _install_store(monkeypatch)

    cron_runner._populate_world_memory(
        observation=_observation(),
        run_id="nav-mem-test",
        cycle=1,
        results=[],
        log_file=StringIO(),
        written_keys=set(),
        transition=None,
    )

    assert not any(key.startswith("/world/path/") for key in records)
    assert records["/world/map/0"]["attributes"]["exits"] == []
    assert all(
        write["domain"].startswith("world/map/")
        or write["domain"].startswith("world/object/")
        for write in writes
    )


def test_map_and_path_memory_are_bounded_injected_and_cited(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    facts = [
        "/world/map/0: Pallet Town exits north to Route 1",
        (
            "/world/path/Pallet-Town->Route-1: Proven route; "
            "door_tile=6,0; route_tiles=6,6|6,5|6,0"
        ),
        *[
            f"/world/object/0/{index}_0: filler-{index}-" + "x" * 300
            for index in range(20)
        ],
    ]
    projections: list[str] = []

    def decide(projection: str, **_kwargs: Any) -> dict[str, Any]:
        projections.append(projection)
        return {
            "ok": True,
            "next_action": "UP",
            "raw": {},
            "escalate": False,
            "escalate_reason": "jev_confident",
            "missing_class": "none",
        }

    monkeypatch.setattr(cron_runner.jev_client, "decide", decide)
    decision = cron_runner._jev_overworld_decision(
        _observation(),
        world_facts=facts,
    )

    assert "/world/map/0:" in projections[0]
    assert "/world/path/Pallet-Town->Route-1:" in projections[0]
    assert decision["world_memory_keys"][:2] == [
        "/world/map/0",
        "/world/path/Pallet-Town->Route-1",
    ]
    assert len(decision["world_memory_keys"]) == cron_runner.WORLD_MEMORY_TOP_K
    marker = capsys.readouterr().out
    assert "/world/map/0" in marker
    assert "/world/path/Pallet-Town->Route-1" in marker

    class _ControllerClient:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        def chat_completion(self, **kwargs: Any) -> dict[str, str]:
            self.calls.append(kwargs)
            return {"content": json.dumps({"plan": ["UP"], "intent": "route"})}

    client = _ControllerClient()
    cron_runner.controller_plan(
        client,  # type: ignore[arg-type]
        _observation(),
        "",
        "",
        world_facts=facts,
    )
    prompt = str(client.calls[0]["messages"][1]["content"])
    block = prompt.split("RELEVANT WORLD MEMORY", 1)[1].split(
        "Output a movement plan", 1
    )[0]
    assert "/world/map/0:" in block
    assert "/world/path/Pallet-Town->Route-1:" in block
    assert len(block) <= cron_runner.WORLD_MEMORY_BLOCK_CHARS + 200


# ── DF-AIPP-13-R4: bound nav-mem route replays across regression cycles ──
#
# Post-R3 residual runs replay a proven edge cycle after cycle: cross
# Pallet Town -> Route 1, regress back, cross again. Every leg walks
# already-visited tiles, so backtrack pins above 50% while no new ground is
# ever reached. The bound strikes BOTH directions of an edge on each
# regression crossing; after PATH_MEMORY_REGRESSION_STRIKES strikes the keys
# are skipped for PATH_MEMORY_REPLAY_COOLDOWN consults and the gap falls back
# to the live exploration policy. A first-visit crossing clears the debt.


def _pallet_route_record() -> dict[str, Any]:
    return {
        "id": "path-pallet-route1",
        "key": "/world/path/Pallet-Town->Route-1",
        "created_at": "2026-11-24T09:00:00+00:00",
        "status": "active",
        "attributes": {
            "fact_type": "path_transition",
            "from_map": {"id": 0, "name": "Pallet Town"},
            "to_map": {"id": 1, "name": "Route 1"},
            "crossing_direction": "UP",
            "door_tile": {"x": 6, "y": 0},
        },
    }


def _install_records(monkeypatch: pytest.MonkeyPatch, records: list[dict[str, Any]]) -> None:
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


PING_PONG_VISITED = ((0, "Pallet Town"), (1, "Route 1"))


def _regression_transition(
    *, from_id: int, from_name: str, to_id: int, to_name: str
) -> dict[str, Any]:
    return {
        "event": "navigation_transition",
        "from_map_id": from_id,
        "from_map_name": from_name,
        "to_map_id": to_id,
        "to_map_name": to_name,
        "crossing_direction": "DOWN" if from_id == 1 else "UP",
        "regression": True,
    }


def test_regression_cycle_bounds_route_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One regression round trip bounds both keys; the gap names them."""
    _install_records(monkeypatch, [_pallet_route_record()])
    observation = _observation(map_id=0, map_name="Pallet Town", tile=(6, 0))
    bound = cron_runner._PathMemoryReplayBound()

    # Before any regression the escape replay is available.
    route = cron_runner._memory_navigation_route(
        observation,
        visited_maps=PING_PONG_VISITED,
        replay_bound=bound,
    )
    assert route is not None
    assert route["key"] == "/world/path/Pallet-Town->Route-1"
    assert route["route_kind"] == cron_runner.DEAD_END_ESCAPE_ROUTE_KIND

    # Route 1 -> Pallet Town regression: first strike, no cooldown yet.
    events = bound.note_transition(
        _regression_transition(
            from_id=1, from_name="Route 1", to_id=0, to_name="Pallet Town"
        )
    )
    assert events == []

    # Pallet Town -> Route 1 regression: strike limit reached on BOTH keys.
    events = bound.note_transition(
        _regression_transition(
            from_id=0, from_name="Pallet Town", to_id=1, to_name="Route 1"
        )
    )
    assert sorted(event["route_key"] for event in events) == [
        "/world/path/Pallet-Town->Route-1",
        "/world/path/Route-1->Pallet-Town",
    ]
    assert all(
        event["cooldown_consults"] == cron_runner.PATH_MEMORY_REPLAY_COOLDOWN
        for event in events
    )

    # The bounded gap no longer replays the treadmill route.
    route = cron_runner._memory_navigation_route(
        observation,
        visited_maps=PING_PONG_VISITED,
        replay_bound=bound,
    )
    assert route is None
    decision = cron_runner._memory_navigation_decision(
        observation,
        visited_maps=PING_PONG_VISITED,
        replay_bound=bound,
    )
    assert decision["result"] == "miss"
    assert decision["reason"] == cron_runner.PATH_MEMORY_REPLAY_BOUNDED_REASON
    # Only the walked edge from THIS map is declined by this consult; the
    # reverse key binds the same way when the gap is consulted on Route 1.
    assert decision["bounded_route_keys"] == [
        "/world/path/Pallet-Town->Route-1",
    ]


def test_new_map_discovery_clears_route_replay_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A first-visit crossing pays the replay debt; the route returns."""
    _install_records(monkeypatch, [_pallet_route_record()])
    observation = _observation(map_id=0, map_name="Pallet Town", tile=(6, 0))
    bound = cron_runner._PathMemoryReplayBound()
    bound.note_transition(
        _regression_transition(
            from_id=1, from_name="Route 1", to_id=0, to_name="Pallet Town"
        )
    )
    bound.note_transition(
        _regression_transition(
            from_id=0, from_name="Pallet Town", to_id=1, to_name="Route 1"
        )
    )
    assert cron_runner._memory_navigation_route(
        observation, visited_maps=PING_PONG_VISITED, replay_bound=bound
    ) is None

    events = bound.note_transition(
        {
            "event": "navigation_transition",
            "from_map_id": 0,
            "from_map_name": "Pallet Town",
            "to_map_id": 34,
            "to_map_name": "Viridian City",
            "crossing_direction": "UP",
            "regression": False,
        }
    )
    assert len(events) == 1
    assert events[0]["event"] == cron_runner.PATH_MEMORY_REPLAY_CLEAR_EVENT
    assert sorted(events[0]["cleared_keys"]) == [
        "/world/path/Pallet-Town->Route-1",
        "/world/path/Route-1->Pallet-Town",
    ]
    route = cron_runner._memory_navigation_route(
        observation, visited_maps=PING_PONG_VISITED, replay_bound=bound
    )
    assert route is not None
    assert route["key"] == "/world/path/Pallet-Town->Route-1"


def test_forward_transition_does_not_bound_route_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Progress never strikes a route key; a fresh bound stays silent."""
    _install_records(monkeypatch, [_pallet_route_record()])
    observation = _observation(map_id=0, map_name="Pallet Town", tile=(6, 0))
    bound = cron_runner._PathMemoryReplayBound()

    assert bound.note_transition(
        {
            "event": "navigation_transition",
            "from_map_id": 0,
            "from_map_name": "Pallet Town",
            "to_map_id": 1,
            "to_map_name": "Route 1",
            "crossing_direction": "UP",
            "regression": False,
        }
    ) == []

    decision = cron_runner._memory_navigation_decision(
        observation,
        visited_maps=PING_PONG_VISITED,
        replay_bound=bound,
    )
    assert decision["result"] == "hit"
    assert decision["key"] == "/world/path/Pallet-Town->Route-1"


def test_replay_cooldown_decays_after_quiet_consults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The bound expires after its consult budget; strikes persist for re-arm."""
    _install_records(monkeypatch, [_pallet_route_record()])
    observation = _observation(map_id=0, map_name="Pallet Town", tile=(6, 0))
    bound = cron_runner._PathMemoryReplayBound()
    bound.note_transition(
        _regression_transition(
            from_id=1, from_name="Route 1", to_id=0, to_name="Pallet Town"
        )
    )
    bound.note_transition(
        _regression_transition(
            from_id=0, from_name="Pallet Town", to_id=1, to_name="Route 1"
        )
    )

    # One silent consult per cooldown unit: the last one lifts the bound.
    route: dict[str, Any] | None = None
    for _ in range(cron_runner.PATH_MEMORY_REPLAY_COOLDOWN):
        route = cron_runner._memory_navigation_route(
            observation, visited_maps=PING_PONG_VISITED, replay_bound=bound
        )
    assert route is not None
    assert route["key"] == "/world/path/Pallet-Town->Route-1"
    assert bound.strikes["/world/path/Pallet-Town->Route-1"] == 2

    # The next lone regression is tolerated (odd strike count); the one after
    # re-arms the cooldown.
    assert (
        bound.note_transition(
            _regression_transition(
                from_id=1, from_name="Route 1", to_id=0, to_name="Pallet Town"
            )
        )
        == []
    )
    events = bound.note_transition(
        _regression_transition(
            from_id=0, from_name="Pallet Town", to_id=1, to_name="Route 1"
        )
    )
    assert [event["strikes"] for event in events] == [4, 4]


def test_replay_bound_never_masks_a_plain_miss(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty bound keeps the historic miss reason byte-identical."""
    _install_records(monkeypatch, [])
    observation = _observation(map_id=0, map_name="Pallet Town", tile=(6, 0))
    decision = cron_runner._memory_navigation_decision(
        observation,
        visited_maps=PING_PONG_VISITED,
        replay_bound=cron_runner._PathMemoryReplayBound(),
    )
    assert decision["result"] == "miss"
    assert decision["reason"] == "no_proven_route_to_unvisited_map"
    assert "bounded_route_keys" not in decision


def test_cycle_transition_notes_strike_route_keys() -> None:
    """The cycle loop folds transitions into the bound and logs the rows."""
    state = SimpleNamespace(
        _path_replay_bound=cron_runner._PathMemoryReplayBound(),
        results=[],
        log_file=StringIO(),
    )
    cron_runner._ow_note_path_replay_bound(
        state,
        5,
        _regression_transition(
            from_id=1, from_name="Route 1", to_id=0, to_name="Pallet Town"
        ),
    )
    cron_runner._ow_note_path_replay_bound(
        state,
        6,
        _regression_transition(
            from_id=0, from_name="Pallet Town", to_id=1, to_name="Route 1"
        ),
    )
    assert [row["event"] for row in state.results] == [
        cron_runner.PATH_MEMORY_REPLAY_EVENT,
        cron_runner.PATH_MEMORY_REPLAY_EVENT,
    ]
    # Both rows come from the SECOND regression (strike limit 2 reached).
    assert [row["cycle"] for row in state.results] == [7, 7]
    logged = [json.loads(line) for line in state.log_file.getvalue().splitlines()]
    assert sorted(row["route_key"] for row in logged) == [
        "/world/path/Pallet-Town->Route-1",
        "/world/path/Route-1->Pallet-Town",
    ]
    # A cycle without a transition must not touch the bound.
    cron_runner._ow_note_path_replay_bound(state, 7, None)
    assert len(state.results) == 2


# ── sticky replay window: an in-flight route keeps navigating (DF-AIPP-13-R4)


def _gap_decision() -> dict[str, Any]:
    return {
        "ok": True,
        "next_action": "UP",
        "raw": {},
        "escalate": True,
        "escalate_reason": "missing_class=map_topology",
        "missing_class": "map_topology",
    }


def _nongap_decision(plan: str = "LEFT") -> dict[str, Any]:
    return {
        "ok": True,
        "next_action": plan,
        "raw": {},
        "escalate": False,
        "escalate_reason": "jev_confident",
        "missing_class": "none",
    }


def test_sticky_replay_overrides_nongap_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After a hit arms the window, non-gap cycles keep replaying the route."""
    _install_records(monkeypatch, [_pallet_route_record()])
    observation = _observation(map_id=0, map_name="Pallet Town", tile=(6, 0))
    bound = cron_runner._PathMemoryReplayBound()

    # Gap cycle: the route hit arms the sticky window.
    memory_navigation, memory_hit = cron_runner._jev_consult_memory_navigation(
        observation,
        _gap_decision(),
        visited_maps=PING_PONG_VISITED,
        replay_bound=bound,
    )
    assert memory_hit is not None
    assert bound.active_key == "/world/path/Pallet-Town->Route-1"

    # Next cycle JEV is confident (no gap): the arming spend + sticky gate
    # keep the replay navigating instead of handing control back mid-walk.
    memory_navigation, memory_hit = cron_runner._jev_consult_memory_navigation(
        observation,
        _nongap_decision(),
        visited_maps=PING_PONG_VISITED,
        replay_bound=bound,
    )
    assert memory_hit is not None
    assert memory_hit["key"] == "/world/path/Pallet-Town->Route-1"
    # One arming spend + one sticky spend of the budget.
    assert bound.active_consults == cron_runner.PATH_MEMORY_REPLAY_STICKY_CONSULTS - 2


def test_sticky_replay_released_on_map_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Crossing the edge converges the replay; the next run re-arms fresh."""
    _install_records(monkeypatch, [_pallet_route_record()])
    observation = _observation(map_id=0, map_name="Pallet Town", tile=(6, 0))
    bound = cron_runner._PathMemoryReplayBound()
    bound.note_transition(
        {
            "event": "navigation_transition",
            "from_map_id": 0,
            "from_map_name": "Pallet Town",
            "to_map_id": 1,
            "to_map_name": "Route 1",
            "crossing_direction": "UP",
            "regression": False,
        }
    )
    route_payload = {
        "key": "/world/path/Pallet-Town->Route-1",
        "route_kind": "unvisited",
    }
    bound.note_replay_arm(route_payload, observation)
    assert bound.sticky_consult_due(observation) is True

    # A transition releases the window even before the budget is spent.
    bound.note_transition(
        {
            "event": "navigation_transition",
            "from_map_id": 0,
            "from_map_name": "Pallet Town",
            "to_map_id": 1,
            "to_map_name": "Route 1",
            "crossing_direction": "UP",
            "regression": False,
        }
    )
    assert bound.active_key is None
    assert bound.sticky_consult_due(observation) is False


def test_sticky_replay_released_on_budget_expiry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A replay that never converges is lifetime-bounded in consults."""
    _install_records(monkeypatch, [_pallet_route_record()])
    observation = _observation(map_id=0, map_name="Pallet Town", tile=(6, 0))
    bound = cron_runner._PathMemoryReplayBound()
    bound.note_replay_arm(
        {"key": "/world/path/Pallet-Town->Route-1", "route_kind": "unvisited"},
        observation,
    )
    for _ in range(cron_runner.PATH_MEMORY_REPLAY_STICKY_CONSULTS):
        assert bound.sticky_consult_due(observation) is True
        bound.note_replay_consult()
    assert bound.sticky_consult_due(observation) is False


def test_sticky_replay_yields_to_a_bounded_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A bounded key cannot keep replaying: the sticky consult misses."""
    _install_records(monkeypatch, [_pallet_route_record()])
    observation = _observation(map_id=0, map_name="Pallet Town", tile=(6, 0))
    bound = cron_runner._PathMemoryReplayBound()
    for _ in range(cron_runner.PATH_MEMORY_REGRESSION_STRIKES):
        bound.note_transition(
            _regression_transition(
                from_id=0, from_name="Pallet Town", to_id=1, to_name="Route 1"
            )
        )
    bound.note_replay_arm(
        {"key": "/world/path/Pallet-Town->Route-1", "route_kind": "dead_end_escape"},
        observation,
    )
    memory_navigation, memory_hit = cron_runner._jev_consult_memory_navigation(
        observation,
        _nongap_decision(),
        visited_maps=PING_PONG_VISITED,
        replay_bound=bound,
    )
    assert memory_hit is None
    assert memory_navigation is not None
    assert memory_navigation["result"] == "miss"
    assert memory_navigation["reason"] == cron_runner.PATH_MEMORY_REPLAY_BOUNDED_REASON
    # The window is released: the next non-gap cycle is the model's answer.
    assert bound.active_key is None
    assert bound.sticky_consult_due(observation) is False


def test_sticky_replay_unkeyed_hit_does_not_arm() -> None:
    """A payload without a stable key cannot start a sticky window."""
    bound = cron_runner._PathMemoryReplayBound()
    bound.note_replay_arm({"route_kind": "unvisited"}, {"map_id": 0})
    assert bound.active_key is None
    assert bound.sticky_consult_due({"map_id": 0}) is False


# ── bound #2: ladder-first candidate order + no-transition replay strikes ──


def test_unvisited_route_prefers_objective_ladder_over_recency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A newer off-ladder record must not outrank the ladder destination."""
    newer = _pallet_route_record()
    # Off-ladder edge to Red's House 1F, recorded AFTER the Route 1 edge.
    house = {
        "id": "path-pallet-house",
        "key": "/world/path/Pallet-Town->Red-s-House-1F",
        "created_at": "2026-11-25T09:00:00+00:00",
        "status": "active",
        "attributes": {
            "fact_type": "path_transition",
            "from_map": {"id": 0, "name": "Pallet Town"},
            "to_map": {"id": 37, "name": "Red's House 1F"},
            "crossing_direction": "UP",
            "door_tile": {"x": 2, "y": 6},
        },
    }
    _install_records(monkeypatch, [newer, house])
    observation = _observation(map_id=0, map_name="Pallet Town", tile=(11, 1))
    route = cron_runner._memory_navigation_route(
        observation,
        visited_maps=((0, "Pallet Town"),),
        replay_bound=cron_runner._PathMemoryReplayBound(),
    )
    assert route is not None
    # Route 1 is ladder step 2; the fresher house edge is off-ladder.
    assert route["key"] == "/world/path/Pallet-Town->Route-1"


def test_repeated_replays_without_transition_bound_the_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A key replayed LIMIT times with no crossing cools down like a regression."""
    _install_records(monkeypatch, [_pallet_route_record()])
    # From the house door the escape replay is the same key each consult.
    observation = _observation(map_id=0, map_name="Pallet Town", tile=(6, 0))
    bound = cron_runner._PathMemoryReplayBound()
    for _ in range(cron_runner.PATH_MEMORY_REPLAY_NO_TRANSITION_LIMIT):
        route = cron_runner._memory_navigation_route(
            observation,
            visited_maps=PING_PONG_VISITED,
            replay_bound=bound,
        )
        assert route is not None, "replayed key must stay available until the limit"
    assert bound.replays_without_transition["/world/path/Pallet-Town->Route-1"] == (
        cron_runner.PATH_MEMORY_REPLAY_NO_TRANSITION_LIMIT
    )

    # The next consult skips the bounded key.
    route = cron_runner._memory_navigation_route(
        observation,
        visited_maps=PING_PONG_VISITED,
        replay_bound=bound,
    )
    assert route is None
    assert bound.last_suppressed_keys == ["/world/path/Pallet-Town->Route-1"]
    drained = bound.drain()
    assert len(drained) == 1
    assert drained[0]["event"] == cron_runner.PATH_MEMORY_REPLAY_EVENT
    assert drained[0]["reason"] == "no_transition_replays"
    assert drained[0]["strikes"] == cron_runner.PATH_MEMORY_REPLAY_NO_TRANSITION_LIMIT


def test_any_crossing_resets_no_transition_replay_counters() -> None:
    """A legit long walk that lands is never punished: crossing resets debt."""
    bound = cron_runner._PathMemoryReplayBound()
    for _ in range(cron_runner.PATH_MEMORY_REPLAY_NO_TRANSITION_LIMIT - 1):
        bound.note_route_hit("/world/path/Pallet-Town->Route-1")
    bound.note_transition(
        {
            "event": "navigation_transition",
            "from_map_id": 0,
            "from_map_name": "Pallet Town",
            "to_map_id": 34,
            "to_map_name": "Viridian City",
            "crossing_direction": "UP",
            "regression": False,
        }
    )
    assert bound.replays_without_transition == {}
    # Counting resumes from zero after the crossing.
    bound.note_route_hit("/world/path/Pallet-Town->Route-1")
    assert bound.replays_without_transition["/world/path/Pallet-Town->Route-1"] == 1
    assert bound.cooldowns == {}


def test_note_path_replay_bound_drains_consult_time_events() -> None:
    """Consult-time bounding events are logged even without a transition."""
    state = SimpleNamespace(
        _path_replay_bound=cron_runner._PathMemoryReplayBound(),
        results=[],
        log_file=StringIO(),
    )
    state._path_replay_bound.note_route_hit("/world/path/Pallet-Town->Route-1")
    cron_runner._ow_note_path_replay_bound(state, 5, None)
    assert state.results == []  # below the strike limit: no events yet
    for _ in range(cron_runner.PATH_MEMORY_REPLAY_NO_TRANSITION_LIMIT):
        state._path_replay_bound.note_route_hit("/world/path/Pallet-Town->Route-1")
    cron_runner._ow_note_path_replay_bound(state, 6, None)
    assert [row["event"] for row in state.results] == [
        cron_runner.PATH_MEMORY_REPLAY_EVENT
    ]
    assert state.results[0]["cycle"] == 7
    assert state.results[0]["reason"] == "no_transition_replays"

