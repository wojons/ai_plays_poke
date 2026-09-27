"""MEM-PROJ: retrieved world facts must reach the live JEV projection."""

from __future__ import annotations

from io import StringIO
from typing import Any

import pytest

import cron_runner
from src.core import duckbrain_client, state_projection


_OBSERVATION: dict[str, Any] = {
    "result": "overworld",
    "map_id": 0,
    "map_name": "Pallet Town",
    "player_x": 3,
    "player_y": 3,
    "player_tile_x": 6,
    "player_tile_y": 6,
    "adjacent": {"up": "wall", "down": "floor", "left": "grass", "right": "object"},
    "visible_exits": [],
}


def _successful_decision() -> dict[str, Any]:
    return {
        "ok": True,
        "next_action": "RIGHT",
        "phase": "EXPLORE",
        "raw": {
            "next_action": {"choice": "RIGHT", "distribution": {"RIGHT": 0.94}},
            "phase": {"choice": "EXPLORE", "distribution": {"EXPLORE": 1.0}},
        },
        "escalate": False,
        "escalate_reason": "jev_confident",
        "missing_class": "none",
    }


def _capture_projections(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    projections: list[str] = []

    def decide(projection: str, **_kwargs: Any) -> dict[str, Any]:
        projections.append(projection)
        return _successful_decision()

    monkeypatch.setattr(cron_runner.jev_client, "decide", decide)
    return projections


def test_retrieved_world_facts_reach_jev_projection(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    records = [
        {"key": "/world/map/0", "embedding_text": "Observed Pallet Town"},
        {
            "key": "/world/object/0/2_3",
            "embedding_text": "Pallet Town block (2,3) is grass",
        },
    ]

    def recall(**kwargs: Any) -> list[dict[str, Any]]:
        return records[:1] if kwargs.get("key") else records[1:]

    monkeypatch.setattr(duckbrain_client, "recall", recall)
    monkeypatch.setattr(duckbrain_client, "remember", lambda **_kwargs: "memory-id")
    facts = cron_runner._populate_world_memory(
        observation=_OBSERVATION,
        run_id="mem-proj-test",
        cycle=2,
        results=[],
        log_file=StringIO(),
        written_keys=set(),
    )

    projections = _capture_projections(monkeypatch)
    cron_runner._jev_overworld_decision(_OBSERVATION, world_facts=facts)

    assert facts == ["/world/map/0", "/world/object/0/2_3"]
    assert len(projections) == 1
    assert (
        "SUPPLIED FACTS:\n  - /world/map/0\n  - /world/object/0/2_3" in projections[0]
    )
    assert "[MEM-WORLD] 2 facts -> JEV projection" in capsys.readouterr().out


@pytest.mark.parametrize("world_facts", [None, []])
def test_empty_world_facts_preserve_projection_bytes(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    world_facts: list[str] | None,
) -> None:
    projections = _capture_projections(monkeypatch)
    cron_runner._jev_overworld_decision(_OBSERVATION, world_facts=world_facts)

    expected = state_projection.build(
        _OBSERVATION,
        mechanics=state_projection.DEFAULT_MECHANICS,
    )
    assert projections == [expected]
    assert "SUPPLIED FACTS" not in projections[0]
    assert "facts -> JEV projection" not in capsys.readouterr().out


def test_world_facts_respect_projection_caps(monkeypatch: pytest.MonkeyPatch) -> None:
    projections = _capture_projections(monkeypatch)
    long_fact = "fact-" + "x" * 400

    cron_runner._jev_overworld_decision(
        _OBSERVATION,
        world_facts=[long_fact] * 40,
    )

    assert len(projections) == 1
    assert len(projections[0]) == 6000
    assert "  - " + "fact-" + "x" * 232 + "..." in projections[0]
    assert long_fact not in projections[0]


def test_world_memory_retrieval_failure_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_recall(**_kwargs: Any) -> list[dict[str, Any]]:
        raise RuntimeError("DuckBrain unavailable")

    monkeypatch.setattr(duckbrain_client, "recall", fail_recall)
    monkeypatch.setattr(duckbrain_client, "remember", lambda **_kwargs: "memory-id")
    results: list[dict[str, Any]] = []

    facts = cron_runner._populate_world_memory(
        observation=_OBSERVATION,
        run_id="mem-proj-test",
        cycle=3,
        results=results,
        log_file=StringIO(),
        written_keys=set(),
    )

    assert facts == []
    assert any(row["event"] == "world_memory_retrieval_failed" for row in results)
