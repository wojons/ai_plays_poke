"""Focused tests for MEM-1's end-of-run DuckBrain recorder."""

from __future__ import annotations

from typing import Any

import cron_runner
from src.core import duckbrain_client


def _writes_by_key(writes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {write["key"]: write for write in writes}


def test_record_run_memory_writes_summary_lessons_and_bounded_index(
    monkeypatch,
) -> None:
    writes: list[dict[str, Any]] = []
    previous_runs = [
        {"run_id": f"old-{index}", "ts": f"2026-09-{index + 1:02d}", "cycles": index}
        for index in range(12)
    ]

    monkeypatch.setattr(
        duckbrain_client,
        "remember",
        lambda **kwargs: writes.append(kwargs) or "memory-id",
    )
    monkeypatch.setattr(
        duckbrain_client,
        "get",
        lambda **kwargs: {"attributes": {"runs": previous_runs}},
    )

    results = [
        {
            "event": "memory_note",
            "note": "Oak said to head north.",
            "screen": "dialog",
            "map_name": "Pallet Town",
        },
        {
            "event": "memory_goal",
            "goal": "Reach Route 1.",
            "screen": "overworld",
            "map_name": "Pallet Town",
            "action": "move(up)",
        },
        {
            "screen": "battle",
            "map_name": "Route 1",
            "action": "press(a)",
            "battle_events": [
                {"event": "battle_start"},
                {"event": "battle_end", "outcome": "won"},
            ],
        },
        # The same battle's top-level transition rows (DF-AIPP-2): the recorder
        # counts THESE and skips the nested list above, never both (which would
        # make this fixture report battle_events 4 instead of 2).
        {"cycle": 3, "event": "battle_start", "battle_type": "wild"},
        {"cycle": 4, "event": "battle_end", "next_screen": "overworld"},
        {
            "event": "starter_picked",
            "screen": "overworld",
            "map_name": "Viridian City",
        },
    ]

    cron_runner._record_run_memory(
        "mem1-run",
        results,
        extra={"log_path": "cron_logs/run_mem1-run.jsonl", "distinct_tiles": 7},
    )

    by_key = _writes_by_key(writes)
    summary = by_key["/game/runs/mem1-run/summary"]
    assert summary["domain"] == "game/runs"
    assert summary["namespace"] == "pokemon-global"
    assert summary["attributes"]["events"] == {
        "memory_note": 1,
        "memory_goal": 1,
        "starter_picked": 1,
        "battle_start": 1,
        "battle_end": 1,
    }
    assert summary["attributes"]["screens"] == {
        "dialog": 1,
        "overworld": 2,
        "battle": 1,
    }
    assert summary["attributes"]["n_actions"] == 2
    assert summary["attributes"]["distinct_maps"] == [
        "Pallet Town",
        "Route 1",
        "Viridian City",
    ]
    assert summary["attributes"]["battle_events"] == 2
    assert summary["attributes"]["cycles"] == len(results)
    assert summary["attributes"]["log_path"] == "cron_logs/run_mem1-run.jsonl"
    assert summary["attributes"]["distinct_tiles"] == 7
    assert summary["attributes"]["ladder"] == {
        "memory_events": 2,
        "battle_events": 2,
        "map_progress": "Viridian City",
        "starter_picked": True,
    }

    lessons = by_key["/game/runs/mem1-run/lessons"]
    assert lessons["attributes"] == {
        "notes": ["Oak said to head north."],
        "goals": ["Reach Route 1."],
    }

    index = by_key["/game/runs/index"]
    assert index["domain"] == "game/runs"
    assert len(index["attributes"]["runs"]) == 10
    assert index["attributes"]["runs"][0]["run_id"] == "mem1-run"
    assert index["attributes"]["runs"][0]["cycles"] == len(results)
    assert index["attributes"]["runs"][0]["ladder"] == summary["attributes"]["ladder"]
    assert index["attributes"]["runs"][1:] == previous_runs[:9]


def test_record_run_memory_skips_empty_lessons(monkeypatch) -> None:
    writes: list[dict[str, Any]] = []
    monkeypatch.setattr(
        duckbrain_client,
        "remember",
        lambda **kwargs: writes.append(kwargs) or "memory-id",
    )
    monkeypatch.setattr(duckbrain_client, "get", lambda **kwargs: None)

    cron_runner._record_run_memory("no-lessons", [{"screen": "overworld"}])

    keys = {write["key"] for write in writes}
    assert "/game/runs/no-lessons/summary" in keys
    assert "/game/runs/no-lessons/lessons" not in keys
    assert "/game/runs/index" in keys


def test_record_run_memory_writes_readable_ram_truth(monkeypatch) -> None:
    writes: list[dict[str, Any]] = []
    monkeypatch.setattr(
        duckbrain_client,
        "remember",
        lambda **kwargs: writes.append(kwargs) or "memory-id",
    )
    monkeypatch.setattr(duckbrain_client, "get", lambda **kwargs: None)

    class FakeRAMReader:
        def party_count(self) -> int:
            return 2

        def first_party_species_hint(self) -> str:
            return "Squirtle"

        def read_items(self) -> list[dict[str, Any]]:
            return [{"name": "Potion", "count": 3}]

        def current_map_id(self) -> int:
            return 1

        def current_map_name(self) -> str:
            return "Viridian City"

        def player_tile_x(self) -> int:
            return 8

        def player_tile_y(self) -> int:
            return 12

    cron_runner._record_run_memory("ram-truth", [], ram_reader=FakeRAMReader())

    by_key = _writes_by_key(writes)
    assert by_key["/game/save/party"]["attributes"] == {
        "party_count": 2,
        "species_hint": "Squirtle",
    }
    assert by_key["/game/save/items"]["attributes"] == {
        "items": [{"name": "Potion", "count": 3}]
    }
    assert by_key["/game/save/location"]["attributes"] == {
        "map_id": 1,
        "map_name": "Viridian City",
        "pos": {"x": 8, "y": 12},
    }


def test_record_run_memory_swallows_duckbrain_failure(monkeypatch, capsys) -> None:
    def fail_remember(**kwargs) -> str:
        raise OSError("duckbrain offline")

    monkeypatch.setattr(duckbrain_client, "remember", fail_remember)
    monkeypatch.setattr(duckbrain_client, "get", lambda **kwargs: None)

    assert cron_runner._record_run_memory("survives", []) is None
    assert "[MEM] recorder failed: duckbrain offline" in capsys.readouterr().out
