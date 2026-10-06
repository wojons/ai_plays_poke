"""PERF-3: recalled world facts must never serve stale "unknown" walkability.

Memory records are written once and replayed for the rest of the run, so a
record written while a tile was unresolved used to render
``walkability=U:unknown,...`` into the JEV projection forever, next to the live
ROM collision truth for the same tile. These tests pin the two contracts that
fix that: stale unknowns never reach the projection, and live ROM truth for the
current tile always leads the supplied facts.
"""

from __future__ import annotations

from io import StringIO
from typing import Any

import pytest

import cron_runner
from src.core import duckbrain_client

_DIRECTIONS = ("up", "down", "left", "right")


def _observation(**overrides: Any) -> dict[str, Any]:
    """A Pallet Town overworld read whose ROM collision truth is complete."""
    obs: dict[str, Any] = {
        "result": "overworld",
        "map_id": 0,
        "map_name": "Pallet Town",
        "map_dimensions": "10×9",
        "map_tileset": 0,
        "player_x": 3,
        "player_y": 3,
        "player_tile_x": 5,
        "player_tile_y": 6,
        "adjacent": {
            "up": "unknown",
            "down": "unknown",
            "left": "grass",
            "right": "grass",
        },
        "adjacent_walkability": {
            "up": "walkable",
            "down": "walkable",
            "left": "walkable",
            "right": "walkable",
        },
        "collision_grid": ".####\n##.##\n..O..\n.....\n.....",
        "visible_exits": [],
    }
    obs.update(overrides)
    return obs


def _map_record(
    *,
    tile: tuple[int, int],
    walkability: dict[str, str],
    collision_grid: str = "?####\n##.##\n..O..\n.....\n.....",
) -> dict[str, Any]:
    """A recalled /world/map/0 record, as DuckBrain serves it back."""
    return {
        "key": "/world/map/0",
        "embedding_text": f"Observed Pallet Town (map 0) at tile ({tile[0]},{tile[1]})",
        "attributes": {
            "fact_type": "map_observation",
            "map_id": 0,
            "map_name": "Pallet Town",
            "player_tile": {"x": tile[0], "y": tile[1]},
            "adjacent_tiles": {
                "up": "unknown",
                "down": "unknown",
                "left": "grass",
                "right": "grass",
            },
            "adjacent_walkability": dict(walkability),
            "local_collision_grid": collision_grid,
            "visible_exits": [],
        },
    }


def _install_memory_store(
    monkeypatch: pytest.MonkeyPatch,
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Serve ``records`` from recall(); collect writes instead of sending them."""
    written: list[dict[str, Any]] = []

    def recall(**_kwargs: Any) -> list[dict[str, Any]]:
        return list(records)

    def remember(**kwargs: Any) -> str:
        written.append(kwargs)
        return f"memory-{len(written)}"

    monkeypatch.setattr(duckbrain_client, "recall", recall)
    monkeypatch.setattr(duckbrain_client, "remember", remember)
    return written


def _capture_projections(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    projections: list[str] = []

    def decide(projection: str, **_kwargs: Any) -> dict[str, Any]:
        projections.append(projection)
        return {
            "ok": True,
            "next_action": "DOWN",
            "phase": "EXPLORE",
            "raw": {},
            "escalate": False,
            "escalate_reason": "jev_confident",
            "missing_class": "none",
        }

    monkeypatch.setattr(cron_runner.jev_client, "decide", decide)
    return projections


# ── (a) stale unknowns never contradict or suppress fresh ROM truth ──────────


def test_unknown_walkability_never_contradicts_fresh_rom_truth() -> None:
    """A same-tile record's stale unknowns are replaced, not mixed in."""
    record = _map_record(
        tile=(5, 6),
        walkability={
            "up": "unknown",
            "down": "unknown",
            "left": "unknown",
            "right": "unknown",
        },
    )

    text = cron_runner._world_fact_text(
        record,
        fresh_walkability={
            "up": "blocked",
            "down": "walkable",
            "left": "walkable",
            "right": "blocked",
        },
        fresh_tile=(5, 6),
        fresh_collision_grid=".####\n##.##\n..O..\n.....\n.....",
    )

    assert "walkability=U:blocked,D:walkable,L:walkable,R:blocked" in text
    assert "unknown" not in text
    # The same tile's stale grid (with a "?" cell) is replaced by the live read.
    assert "local_collision=.####/##.##/..O../...../....." in text


def test_same_tile_fresh_truth_outranks_stored_known_values() -> None:
    """Live ROM truth wins over a snapshot for the same tile, per direction."""
    record = _map_record(
        tile=(5, 6),
        walkability={
            "up": "blocked",
            "down": "blocked",
            "left": "unknown",
            "right": "walkable",
        },
    )

    text = cron_runner._world_fact_text(
        record,
        fresh_walkability={
            "up": "walkable",
            "down": "walkable",
            "left": "walkable",
            "right": "walkable",
        },
        fresh_tile=(5, 6),
        fresh_collision_grid=".####\n##.##\n..O..\n.....\n.....",
    )

    assert "walkability=U:walkable,D:walkable,L:walkable,R:walkable" in text
    assert "unknown" not in text


def test_stale_record_for_another_tile_drops_unknowns_without_borrowing_fresh() -> None:
    """A different tile keeps its own truth: fresh values are never misattributed."""
    record = _map_record(
        tile=(1, 1),
        walkability={
            "up": "unknown",
            "down": "blocked",
            "left": "unknown",
            "right": "walkable",
        },
    )

    text = cron_runner._world_fact_text(
        record,
        fresh_walkability={
            "up": "walkable",
            "down": "walkable",
            "left": "walkable",
            "right": "walkable",
        },
        fresh_tile=(5, 6),
        fresh_collision_grid=".####\n##.##\n..O..\n.....\n.....",
    )

    assert "walkability=D:blocked,R:walkable" in text
    assert "U:walkable" not in text
    assert "L:walkable" not in text
    assert "local_collision=.####" not in text


# ── (b) no ":unknown" walkability entries when fresh values are provided ──────


@pytest.mark.parametrize("unknown_direction", _DIRECTIONS)
def test_world_fact_text_has_no_unknown_walkability_with_fresh_values(
    unknown_direction: str,
) -> None:
    walkability = {direction: "blocked" for direction in _DIRECTIONS}
    walkability[unknown_direction] = "unknown"
    record = _map_record(tile=(5, 6), walkability=walkability)

    text = cron_runner._world_fact_text(
        record,
        fresh_walkability={
            "up": "blocked",
            "down": "walkable",
            "left": "walkable",
            "right": "blocked",
        },
        fresh_tile=(5, 6),
        fresh_collision_grid=".####\n##.##\n..O..\n.....\n.....",
    )

    assert "walkability=U:blocked,D:walkable,L:walkable,R:blocked" in text
    assert ":unknown" not in text
    assert "unknown" not in text


def test_unknown_walkability_is_never_rendered_without_fresh_values() -> None:
    """Stale unknowns are dropped even when no live read is supplied."""
    record = _map_record(
        tile=(1, 1),
        walkability={
            "up": "unknown",
            "down": "unknown",
            "left": "walkable",
            "right": "unknown",
        },
    )

    text = cron_runner._world_fact_text(record)

    assert "walkability=L:walkable" in text
    assert "unknown" not in text


def test_walkability_free_record_renders_no_walkability_field() -> None:
    """All-unknown memory contributes no walkability claim at all."""
    record = _map_record(
        tile=(1, 1),
        walkability={direction: "unknown" for direction in _DIRECTIONS},
    )

    text = cron_runner._world_fact_text(record)

    assert "walkability=" not in text
    assert "terrain=L:grass,R:grass" in text


# ── live ROM truth for the CURRENT map leads the supplied facts ──────────────


def test_fresh_map_first_cycle_supplies_live_rom_topology(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Retrieval runs before writes, so a new map has no recalled record yet."""
    _install_memory_store(monkeypatch, records=[])
    observation = _observation(map_id=37, map_name="Red's House 1F")
    results: list[dict[str, Any]] = []

    facts = cron_runner._populate_world_memory(
        observation=observation,
        run_id="perf3-test",
        cycle=2,
        results=results,
        log_file=StringIO(),
        written_keys=set(),
    )

    assert facts == [
        (
            "/world/map/37: live ROM collision truth (this cycle); tile=5,6; "
            "walkability=U:walkable,D:walkable,L:walkable,R:walkable"
        )
    ]
    refresh = [
        row for row in results if row["event"] == "world_memory_topology_refresh"
    ]
    assert len(refresh) == 1
    assert refresh[0]["map_id"] == 37
    assert refresh[0]["walkability"] == {
        "up": "walkable",
        "down": "walkable",
        "left": "walkable",
        "right": "walkable",
    }
    # The PERF-2 safety net now has ROM evidence on the very first cycle.
    assert cron_runner._map_topology_resolved(observation, facts) is True


def test_fresh_topology_is_withheld_when_the_rom_read_is_incomplete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A partial read must not masquerade as fresh truth."""
    _install_memory_store(monkeypatch, records=[])
    observation = _observation(
        collision_grid=".####\n##?##\n..O..\n.....\n.....",
    )
    results: list[dict[str, Any]] = []

    facts = cron_runner._populate_world_memory(
        observation=observation,
        run_id="perf3-test",
        cycle=2,
        results=results,
        log_file=StringIO(),
        written_keys=set(),
    )

    assert facts == []
    assert not [
        row for row in results if row["event"] == "world_memory_topology_refresh"
    ]
    assert cron_runner._map_topology_resolved(observation, facts) is False


def test_projection_carries_one_unambiguous_walkability_truth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stale unknown facts and live truth never appear side by side."""
    stale = _map_record(
        tile=(1, 1),
        walkability={
            "up": "unknown",
            "down": "unknown",
            "left": "unknown",
            "right": "unknown",
        },
    )
    _install_memory_store(monkeypatch, records=[stale])
    observation = _observation()
    facts = cron_runner._populate_world_memory(
        observation=observation,
        run_id="perf3-test",
        cycle=3,
        results=[],
        log_file=StringIO(),
        written_keys=set(),
    )

    projections = _capture_projections(monkeypatch)
    cron_runner._jev_overworld_decision(observation, world_facts=facts)

    assert len(projections) == 1
    projection = projections[0]
    assert "SUPPLIED FACTS:" in projection
    assert "walkability=U:unknown" not in projection
    assert "walkability=U:walkable,D:walkable,L:walkable,R:walkable" in projection
    # The stale record still contributes its resolved terrain, without a
    # walkability claim it cannot support.
    assert "/world/map/0: Observed Pallet Town (map 0) at tile (1,1)" in projection
    assert "terrain=L:grass,R:grass" in projection


def test_live_rom_topology_clears_a_jev_reported_gap_without_the_teacher(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End to end through the PERF-2 gate: escalated JEV answer, no teacher."""
    stale = _map_record(
        tile=(1, 1),
        walkability={direction: "unknown" for direction in _DIRECTIONS},
    )
    _install_memory_store(monkeypatch, records=[stale])
    observation = _observation()
    facts = cron_runner._populate_world_memory(
        observation=observation,
        run_id="perf3-test",
        cycle=3,
        results=[],
        log_file=StringIO(),
        written_keys=set(),
    )

    teacher_calls = {"count": 0}

    def decide(projection: str, **_kwargs: Any) -> dict[str, Any]:
        _ = projection
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
        teacher_calls["count"] += 1
        return {"ok": False}

    monkeypatch.setattr(cron_runner.jev_client, "decide", decide)
    monkeypatch.setattr(cron_runner.jev_client, "escalate_and_reask", teacher)

    decision = cron_runner._jev_overworld_decision(
        observation,
        world_facts=facts,
        teacher_api_client=object(),
        teacher_model="test/teacher",
        escalated_classes=set(),
    )

    assert decision["escalated"] is False
    assert decision["missing_class"] == "none"
    assert decision["jev_escalate_reason"] == "map_topology_resolved_by_rom"
    assert teacher_calls["count"] == 0


# ── PERF-3 follow-up: derive, invalidate, and target missing facts ────────────


def test_world_writer_uses_collision_grid_not_vision_walkability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The persisted walkability comes from RAM collision cells only."""
    written = _install_memory_store(monkeypatch, records=[])
    observation = _observation(
        # Deliberately contradictory vision-like labels. These must never be
        # persisted as movement truth.
        adjacent_walkability={
            "up": "blocked",
            "down": "walkable",
            "left": "blocked",
            "right": "walkable",
        },
        collision_grid="#####\n##.##\n#.O##\n#####\n#####",
    )

    facts = cron_runner._populate_world_memory(
        observation=observation,
        run_id="perf3-writer-test",
        cycle=1,
        results=[],
        log_file=StringIO(),
        written_keys=set(),
    )

    assert written[0]["attributes"]["adjacent_walkability"] == {
        "up": "walkable",
        "down": "blocked",
        "left": "walkable",
        "right": "blocked",
    }
    assert facts[0].endswith("walkability=U:walkable,D:blocked,L:walkable,R:blocked")


def test_retrieval_rederives_unknown_walkability_from_collision_grid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A cached all-unknown record is repaired from the live collision grid."""
    stale = _map_record(
        tile=(5, 6),
        walkability={direction: "unknown" for direction in _DIRECTIONS},
    )
    _install_memory_store(monkeypatch, records=[stale])
    observation = _observation(
        adjacent_walkability={direction: "unknown" for direction in _DIRECTIONS},
        collision_grid="#####\n##.##\n#.O##\n#####\n#####",
    )

    facts = cron_runner._populate_world_memory(
        observation=observation,
        run_id="perf3-retrieval-test",
        cycle=2,
        results=[],
        log_file=StringIO(),
        written_keys=set(),
    )

    assert any(
        "walkability=U:walkable,D:blocked,L:walkable,R:blocked" in fact
        for fact in facts
    )
    assert all(":unknown" not in fact for fact in facts)


def test_teacher_missing_facts_become_next_cycle_world_targets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Teacher gaps bind to exact world keys and are recalled on the next cycle."""
    pre_decision = {
        "ok": True,
        "next_action": "RIGHT",
        "sufficient_state": 0.18,
        "missing_class": "map_topology",
        "escalate": True,
        "escalate_reason": "insufficient_state (0.18) missing=map_topology",
        "raw": {},
    }
    monkeypatch.setattr(
        cron_runner.jev_client, "decide", lambda *_args, **_kwargs: pre_decision
    )
    monkeypatch.setattr(
        cron_runner.jev_client,
        "escalate_and_reask",
        lambda *_args, **_kwargs: {
            "ok": True,
            "patch": {
                "missing_facts": ["the walkable exit below the player"],
                "instruction_patch": "prefer the resolved exit",
            },
            "post_ask": {
                "ok": True,
                "next_action": "DOWN",
                "missing_class": "none",
                "raw": {},
            },
        },
    )

    # Empty path-memory store for the pre-teacher NAV-MEM consult: a live
    # local DuckBrain with real /world/path/* records would answer the
    # navigation gap before the teacher runs, making this test env-dependent.
    monkeypatch.setattr(duckbrain_client, "recall", lambda **_kwargs: [])

    decision = cron_runner._jev_overworld_decision(
        _observation(),
        teacher_api_client=object(),
        teacher_model="test/teacher",
        escalated_classes=set(),
    )
    assert decision["teacher_missing_facts"] == ["the walkable exit below the player"]
    assert decision["teacher_memory_targets"] == [
        "/world/map/0",
        "/world/object/0/3_4",
    ]

    recall_calls: list[dict[str, Any]] = []

    def recall(**kwargs: Any) -> list[dict[str, Any]]:
        recall_calls.append(kwargs)
        if kwargs.get("key") == "/world/object/0/3_4":
            return [
                {
                    "key": "/world/object/0/3_4",
                    "embedding_text": "Pallet Town block (3,4) is a walkable exit",
                }
            ]
        return []

    monkeypatch.setattr(duckbrain_client, "recall", recall)
    monkeypatch.setattr(duckbrain_client, "remember", lambda **_kwargs: "memory-id")
    results: list[dict[str, Any]] = []
    facts = cron_runner._populate_world_memory(
        observation=_observation(),
        run_id="perf3-target-test",
        cycle=2,
        results=results,
        log_file=StringIO(),
        written_keys=set(),
        retrieval_targets=decision["teacher_memory_targets"],
    )

    assert any(call.get("key") == "/world/object/0/3_4" for call in recall_calls)
    assert any("/world/object/0/3_4:" in fact for fact in facts)
    consumed = [
        row
        for row in results
        if row["event"] == "world_memory_teacher_targets_consumed"
    ]
    assert consumed == [
        {
            "cycle": 2,
            "event": "world_memory_teacher_targets_consumed",
            "namespace": cron_runner.WORLD_MEMORY_NAMESPACE,
            "targets": ["/world/map/0", "/world/object/0/3_4"],
            "matched_keys": ["/world/object/0/3_4"],
        }
    ]
