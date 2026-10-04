"""NAV-MEM: deterministic route writes and bounded decision-context injection."""

from __future__ import annotations

import json
from io import StringIO
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
