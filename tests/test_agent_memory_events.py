"""Regression tests for DF-AIPP-1: agent memory events must reach ``results``.

The note/goal/study handlers used to write their event dicts ONLY to the run
log file, while ``_record_run_memory`` counts events out of ``results``. So the
run ladder reported ``memory_events`` 0 for every run and
``/game/runs/<id>/lessons`` was never written — even for live runs that emitted
notes and goals.

These tests simulate a run cycle the way ``main()`` drives it (through
``_apply_agent_memory_outputs``), then assert on the recorder's summary shape.
"""

from __future__ import annotations

import json
from typing import Any, TextIO

import cron_runner
from src.core import duckbrain_client


def _capture_writes(monkeypatch) -> list[dict[str, Any]]:
    writes: list[dict[str, Any]] = []
    monkeypatch.setattr(
        duckbrain_client,
        "remember",
        lambda **kwargs: writes.append(kwargs) or "memory-id",
    )
    monkeypatch.setattr(duckbrain_client, "get", lambda **kwargs: None)
    return writes


def _writes_by_key(writes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {write["key"]: write for write in writes}


def _log_rows(log_file: TextIO) -> list[dict[str, Any]]:
    log_file.flush()
    log_file.seek(0)
    rows = [line for line in log_file.read().splitlines() if line.strip()]
    log_file.seek(0, 2)  # back to append position for further cycles
    return [json.loads(line) for line in rows]


def test_run_cycle_memory_events_land_in_results_and_log(tmp_path) -> None:
    """Every logged note/goal/study event also lands in ``results``."""
    results: list[dict[str, Any]] = []
    log_path = tmp_path / "run_sim.jsonl"

    with log_path.open("w+", encoding="utf-8") as log_file:
        goal, notes, pending = cron_runner._apply_agent_memory_outputs(
            decision={"note": "Oak said to head north.", "goal": "Reach Route 1."},
            results=results,
            log_file=log_file,
            cycle=7,
            map_name="Pallet Town",
            mem_goal="",
            mem_notes=[],
            pending_study_result="",
        )
        assert goal == "Reach Route 1."
        assert notes[0] == "[Pallet Town] Oak said to head north."
        assert pending == ""

        logged = _log_rows(log_file)

    assert [row["event"] for row in results] == ["memory_note", "memory_goal"]
    # The log and the in-memory results must describe the same run events.
    assert logged == results
    assert results[0]["cycle"] == 7
    assert results[0]["map"] == "Pallet Town"
    assert results[1]["goal"] == "Reach Route 1."


def test_study_event_lands_in_results(monkeypatch, tmp_path) -> None:
    """A study lookup is a run event too (the ladder counts memory_study)."""
    _capture_writes(monkeypatch)
    results: list[dict[str, Any]] = []
    log_path = tmp_path / "run_study.jsonl"

    with log_path.open("w+", encoding="utf-8") as log_file:
        _, _, pending = cron_runner._apply_agent_memory_outputs(
            decision={"study": "/notes/overworld-3"},
            results=results,
            log_file=log_file,
            cycle=3,
            map_name="Route 1",
            mem_goal="",
            mem_notes=[],
            pending_study_result="",
        )
        logged = _log_rows(log_file)

    assert "nothing at /notes/overworld-3" in pending
    assert [row["event"] for row in results] == ["memory_study"]
    assert results[0]["key"] == "/notes/overworld-3"
    assert logged == results


def test_failed_memory_write_records_no_event(monkeypatch, tmp_path) -> None:
    """A failed DuckBrain write still records no event — unchanged by the fix.

    The goal string is still adopted in memory (pre-existing behaviour: the
    assignment happens before the write), but nothing enters ``results`` and no
    log line is written, so the ladder cannot over-count failed writes.
    """

    def fail_remember(**kwargs) -> str:
        raise OSError("duckbrain offline")

    monkeypatch.setattr(duckbrain_client, "remember", fail_remember)
    monkeypatch.setattr(duckbrain_client, "get", lambda **kwargs: None)
    results: list[dict[str, Any]] = []
    log_path = tmp_path / "run_fail.jsonl"

    with log_path.open("w+", encoding="utf-8") as log_file:
        goal, notes, _ = cron_runner._apply_agent_memory_outputs(
            decision={"note": "should not land", "goal": "nor this"},
            results=results,
            log_file=log_file,
            cycle=1,
            map_name="Pallet Town",
            mem_goal="",
            mem_notes=[],
            pending_study_result="",
        )
        logged = _log_rows(log_file)

    assert results == []
    assert logged == []
    assert goal == "nor this"  # in-memory update, not a recorded event
    assert notes == []


def test_simulated_run_memory_events_reach_ladder_and_lessons(
    monkeypatch, tmp_path
) -> None:
    """DF-AIPP-1: a run emitting note+goal reports memory_events > 0 + lessons."""
    writes = _capture_writes(monkeypatch)
    # Second and later study lookups resolve to a real remembered record.
    monkeypatch.setattr(
        duckbrain_client,
        "get",
        lambda **kwargs: {
            "key": kwargs["key"],
            "attributes": {"fact": "Route 1 is north."},
        },
    )
    results: list[dict[str, Any]] = []
    log_path = tmp_path / "run_dgf_sim.jsonl"

    with log_path.open("w+", encoding="utf-8") as log_file:
        goal, notes, pending = cron_runner._apply_agent_memory_outputs(
            decision={
                "note": "Oak said to head north.",
                "goal": "Reach Route 1.",
                "study": "/notes/oak-lab",
            },
            results=results,
            log_file=log_file,
            cycle=12,
            map_name="Pallet Town",
            mem_goal="",
            mem_notes=[],
            pending_study_result="",
        )

    assert "Route 1 is north." in pending
    assert goal == "Reach Route 1."
    assert notes == ["[Pallet Town] Oak said to head north."]

    cron_runner._record_run_memory(
        "dgf-sim", results, extra={"log_path": str(log_path)}
    )

    by_key = _writes_by_key(writes)
    summary = by_key["/game/runs/dgf-sim/summary"]
    ladder = summary["attributes"]["ladder"]
    assert ladder["memory_events"] == 3
    assert ladder["memory_events"] > 0
    assert ladder["battle_events"] == 0  # DF-AIPP-2's counter is untouched
    assert summary["attributes"]["events"]["memory_note"] == 1
    assert summary["attributes"]["events"]["memory_goal"] == 1
    assert summary["attributes"]["events"]["memory_study"] == 1

    lessons = by_key["/game/runs/dgf-sim/lessons"]
    assert lessons["domain"] == "game/runs"
    assert lessons["namespace"] == "pokemon-global"
    assert lessons["attributes"] == {
        "notes": ["Oak said to head north."],
        "goals": ["Reach Route 1."],
    }

    index = by_key["/game/runs/index"]
    assert index["attributes"]["runs"][0]["ladder"]["memory_events"] == 3
