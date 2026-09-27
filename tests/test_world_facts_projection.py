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
    "adjacent_walkability": {
        "up": "blocked",
        "down": "walkable",
        "left": "walkable",
        "right": "blocked",
    },
    "collision_grid": "#.#\n.O.\n...",
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
        {
            "key": "/world/map/0",
            "embedding_text": "Stale Pallet Town observation",
            "created_at": "2026-01-01T00:00:00+00:00",
        },
        {
            "key": "/world/map/0",
            "embedding_text": "Observed Pallet Town",
            "created_at": "2026-01-02T00:00:00+00:00",
            "attributes": {
                "map_name": "Pallet Town",
                "player_tile": {"x": 6, "y": 6},
                "adjacent_tiles": {
                    "up": "wall",
                    "down": "floor",
                    "left": "grass",
                    "right": "object",
                },
                "adjacent_walkability": {
                    "up": "blocked",
                    "down": "walkable",
                    "left": "walkable",
                    "right": "blocked",
                },
                "local_collision_grid": "#.#\n.O.\n...",
                "visible_exits": [],
            },
        },
        {
            "key": "/world/object/0/2_3",
            "embedding_text": "Pallet Town block (2,3) is grass",
        },
    ]

    def recall(**kwargs: Any) -> list[dict[str, Any]]:
        return records[:2] if kwargs.get("key") else records[2:]

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

    assert facts == [
        (
            "/world/map/0: Observed Pallet Town; tile=6,6; "
            "walkability=U:blocked,D:walkable,L:walkable,R:blocked; "
            "terrain=U:wall,D:floor,L:grass,R:object; "
            "local_collision=#.#/.O./...; exits=none"
        ),
        "/world/object/0/2_3: Pallet Town block (2,3) is grass",
    ]
    assert len(projections) == 1
    assert "SUPPLIED FACTS:" in projections[0]
    assert "walkability=U:blocked,D:walkable,L:walkable,R:blocked" in projections[0]
    assert "/world/object/0/2_3: Pallet Town block (2,3) is grass" in projections[0]
    assert "[MEM-WORLD] 2 facts -> JEV projection" in capsys.readouterr().out


def test_projection_distinguishes_walkability_from_terrain() -> None:
    projection = state_projection.build(_OBSERVATION)

    assert "TOPOLOGY (ROM collision truth for the next move):" in projection
    assert "UP=blocked DOWN=walkable LEFT=walkable RIGHT=blocked" in projection
    assert (
        "ADJACENT TERRAIN (appearance only; collision above is authoritative):"
        in projection
    )
    assert "UP=wall DOWN=floor LEFT=grass RIGHT=object" in projection
    assert (
        "LOCAL COLLISION MAP (O=player, .=walkable, #=blocked, ?=unknown):"
        in projection
    )
    assert "  #.#\n  .O.\n  ..." in projection


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


def test_complete_map_fact_stops_repeat_topology_escalation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deterministic ROM topology overrides a stale JEV self-reported gap."""
    calls = {"teacher": 0}

    def decide(projection: str, **_kwargs: Any) -> dict[str, Any]:
        assert "LOCAL COLLISION MAP" in projection
        decision = {
            "ok": True,
            "next_action": "DOWN",
            "phase": "EXPLORE",
            "sufficient_state": 0.2,
            "missing_class": "map_topology",
            "action_confidence": 0.3,
            "ambiguity": 0.6,
            "raw": {},
        }
        escalate, reason = cron_runner.jev_client.should_escalate(decision)
        return {**decision, "escalate": escalate, "escalate_reason": reason}

    def teacher(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        calls["teacher"] += 1
        return {"ok": False}

    monkeypatch.setattr(cron_runner.jev_client, "decide", decide)
    monkeypatch.setattr(cron_runner.jev_client, "escalate_and_reask", teacher)
    observation = dict(_OBSERVATION)
    fact = (
        "/world/map/0: Observed Pallet Town; tile=6,6; "
        "walkability=U:blocked,D:walkable,L:walkable,R:blocked; "
        "local_collision=#.#/.O./...; exits=none"
    )
    escalated_classes: set[str] = set()

    first = cron_runner._jev_overworld_decision(
        observation,
        world_facts=[fact],
        teacher_api_client=object(),
        teacher_model="test/teacher",
        escalated_classes=escalated_classes,
    )
    second = cron_runner._jev_overworld_decision(
        observation,
        world_facts=[fact],
        teacher_api_client=object(),
        teacher_model="test/teacher",
        escalated_classes=escalated_classes,
    )

    assert first["plan"] == ["DOWN"]
    assert second["plan"] == ["DOWN"]
    assert first["escalated"] is False
    assert second["escalated"] is False
    assert first["missing_class"] == "none"
    assert second["missing_class"] == "none"
    assert first["jev_escalate_reason"] == "map_topology_resolved_by_rom"
    assert second["jev_escalate_reason"] == "map_topology_resolved_by_rom"
    assert calls["teacher"] == 0


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
