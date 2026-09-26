"""Focused tests for deterministic world-memory population and retrieval."""

from __future__ import annotations

import json
from io import StringIO
from typing import Any

import cron_runner
from src.core import duckbrain_client


def _observation() -> dict[str, Any]:
    return {
        "result": "overworld",
        "map_id": 0,
        "map_name": "Pallet Town",
        "map_dimensions": "10×9",
        "map_tileset": 0,
        "player_x": 3,
        "player_y": 3,
        "player_tile_x": 6,
        "player_tile_y": 6,
        "adjacent": {
            "up": "unknown",
            "down": "floor",
            "left": "grass",
            "right": "object",
        },
        "visible_exits": [],
    }


def _install_memory_store(monkeypatch) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}

    def remember(**kwargs: Any) -> str:
        record = {"id": f"memory-{len(records) + 1}", "status": "active", **kwargs}
        records[kwargs["key"]] = record
        return str(record["id"])

    def recall(**kwargs: Any) -> list[dict[str, Any]]:
        key = kwargs.get("key")
        prefix = kwargs.get("key_prefix")
        limit = int(kwargs.get("limit", 10))
        matches = [
            record
            for record in records.values()
            if (key is None or record["key"] == key)
            and (prefix is None or record["key"].startswith(prefix))
        ]
        return matches[:limit]

    monkeypatch.setattr(duckbrain_client, "remember", remember)
    monkeypatch.setattr(duckbrain_client, "recall", recall)
    return records


def test_world_memory_writes_structured_map_and_object_facts(monkeypatch) -> None:
    records = _install_memory_store(monkeypatch)
    results: list[dict[str, Any]] = []
    log_file = StringIO()

    cron_runner._populate_world_memory(
        observation=_observation(),
        run_id="mem-pop-test",
        cycle=1,
        results=results,
        log_file=log_file,
        written_keys=set(),
    )

    map_record = records["/world/map/0"]
    object_record = records["/world/object/0/2_3"]
    for record in (map_record, object_record):
        assert record["key"].startswith("/world/")
        assert record["domain"] == record["key"].removeprefix("/")
        assert isinstance(record["attributes"], dict)
        assert record["embedding_text"]
        assert record["confidence"] == 1.0
        assert record["evidence"] == {
            "run_id": "mem-pop-test",
            "cycle": 1,
            "map": {"id": 0, "name": "Pallet Town"},
            "tile": {"x": 6, "y": 6},
        }

    assert map_record["attributes"]["fact_type"] == "map_observation"
    assert map_record["attributes"]["adjacent_tiles"]["left"] == "grass"
    assert object_record["attributes"] == {
        "fact_type": "tile_observation",
        "map_id": 0,
        "map_name": "Pallet Town",
        "position": {"x": 2, "y": 3, "coordinate_space": "map_block"},
        "tile_type": "grass",
        "relative_direction": "left",
    }
    assert "/world/object/0/4_3" in records
    assert not any(key.endswith("3_2") for key in records)
    assert not any(key.endswith("3_4") for key in records)
    assert [row["event"] for row in results].count("world_memory_write") == 3
    assert [json.loads(line) for line in log_file.getvalue().splitlines()] == results


def test_next_cycle_retrieves_fact_before_attempting_new_writes(monkeypatch) -> None:
    records = _install_memory_store(monkeypatch)
    results: list[dict[str, Any]] = []
    log_file = StringIO()
    written_keys: set[str] = set()

    cron_runner._populate_world_memory(
        observation=_observation(),
        run_id="mem-pop-test",
        cycle=1,
        results=results,
        log_file=log_file,
        written_keys=written_keys,
    )
    first_cycle_write_count = len(records)
    cron_runner._populate_world_memory(
        observation=_observation(),
        run_id="mem-pop-test",
        cycle=2,
        results=results,
        log_file=log_file,
        written_keys=written_keys,
    )

    retrievals = [row for row in results if row["event"] == "world_memory_retrieval"]
    assert len(retrievals) == 1
    assert retrievals[0]["cycle"] == 2
    assert retrievals[0]["map_id"] == 0
    assert retrievals[0]["keys"][0] == "/world/map/0"
    assert set(retrievals[0]["keys"]) >= {
        "/world/map/0",
        "/world/object/0/2_3",
    }
    assert retrievals[0]["records"][0]["evidence"]["cycle"] == 1
    assert len(records) == first_cycle_write_count

    logged = [json.loads(line) for line in log_file.getvalue().splitlines()]
    assert logged == results
    assert logged.index(retrievals[0]) > max(
        index
        for index, row in enumerate(logged)
        if row["event"] == "world_memory_write" and row["cycle"] == 1
    )


def test_world_memory_skips_observation_without_typed_location(monkeypatch) -> None:
    records = _install_memory_store(monkeypatch)
    results: list[dict[str, Any]] = []

    cron_runner._populate_world_memory(
        observation={"map_id": "0", "player_tile_x": None, "player_tile_y": 6},
        run_id="mem-pop-test",
        cycle=1,
        results=results,
        log_file=StringIO(),
        written_keys=set(),
    )

    assert records == {}
    assert results == []
