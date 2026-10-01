"""Focused tests for the E2E-002 80-cycle L2 acceptance instrument."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import evaluate_e2e_l2 as e2e  # noqa: E402


def _manifest(run_id: str = "e2e002_20261001_010203_ab12") -> dict:
    return {
        "schema_version": 1,
        "instrument": "E2E-002",
        "mode": e2e.MODE,
        "run_id": run_id,
        "cycles": 80,
        "boot_state": "data/boot.state",
        "fresh_run_id": True,
        "command": [
            "python",
            "cron_runner.py",
            "--run-id",
            run_id,
            "--boot-state",
            "data/boot.state",
            "--cycles",
            "80",
        ],
        "key_preflight": {
            "passed": True,
            "skipped": False,
            "live_key_names": ["OPENROUTER_API_KEY"],
        },
        "memory_cap_bytes": e2e.MEMORY_CAP_BYTES,
        "memory_cap_enforced": True,
        "peak_rss_kb": 512_000,
        "process_exit_code": 0,
        "runner_api_failure_count": 0,
    }


def _rows(run_id: str = "e2e002_20261001_010203_ab12") -> list[dict]:
    return [
        {"run_id": run_id, "event": "preflight", "status": "pass", "ok": True},
        {"cycle": 1, "screen": "overworld", "map_id": 40, "map_name": "Oak's Lab"},
        {"cycle": 2, "event": "memory_note", "note": "Oak said to head north."},
        {"cycle": 3, "event": "starter_picked", "species_hint": "Charmander"},
        {"cycle": 20, "event": "battle_start", "battle_type": "trainer"},
        {
            "cycle": 20,
            "screen": "battle",
            "battle_events": [{"event": "battle_start", "source": "battle-checkpoint"}],
        },
        {"cycle": 24, "event": "battle_end", "next_screen": "overworld"},
        {"cycle": 25, "screen": "overworld", "map_id": 11, "map_name": "Route 1"},
        {"cycle": 80, "screen": "overworld", "map_id": 11, "map_name": "Route 1"},
    ]


def _duckbrain_summary(run_id: str = "e2e002_20261001_010203_ab12") -> dict:
    return {
        "key": f"/game/runs/{run_id}/summary",
        "attributes": {
            "events": {"memory_note": 1, "starter_picked": 1, "battle_start": 1, "battle_end": 1},
            "ladder": {"memory_events": 1, "battle_events": 2, "map_progress": "Route 1"},
        },
    }


def _artifacts(tmp_path: Path) -> tuple[Path, Path]:
    review = tmp_path / "review.html"
    replay = tmp_path / "replay.mp4"
    review.write_text("<html>review</html>", encoding="utf-8")
    replay.write_bytes(b"synthetic replay")
    return review, replay


def _previous_pass(run_id: str = "e2e002_20260930_235959_cd34") -> dict:
    return {
        "instrument": "E2E-002",
        "mode": e2e.MODE,
        "run_id": run_id,
        "single_run_pass": True,
        "checks": {"key_liveness": {"passed": True}},
    }


def _evaluate(tmp_path: Path, **overrides) -> dict:
    review, replay = _artifacts(tmp_path)
    args = {
        "manifest": _manifest(),
        "rows": _rows(),
        "duckbrain_summary": _duckbrain_summary(),
        "review_path": review,
        "replay_path": replay,
        "previous_results": [_previous_pass()],
    }
    args.update(overrides)
    return e2e.evaluate_evidence(**args)


def test_positive_evidence_requires_two_distinct_passes_for_l2(tmp_path: Path) -> None:
    result = _evaluate(tmp_path)

    assert result["single_run_pass"] is True
    assert result["gate_pass"] is True
    assert result["score"]["level"] == "L2"
    assert result["score"]["value"] == 2
    assert result["independent_passing_run_ids"] == [
        "e2e002_20260930_235959_cd34",
        "e2e002_20261001_010203_ab12",
    ]
    assert result["checks"]["organic_battle_pair"]["observed_pairs"] == 1
    assert result["checks"]["api_failures"]["observed"] == 0
    assert result["checks"]["peak_rss"]["observed_mb"] == pytest.approx(500.0)
    assert result["checks"]["memory_both_surfaces"]["event_types"] == ["memory_note"]


def test_first_full_pass_is_l1_candidate_not_l2_claim(tmp_path: Path) -> None:
    result = _evaluate(tmp_path, previous_results=[])

    assert result["single_run_pass"] is True
    assert result["gate_pass"] is False
    assert result["score"]["level"] == "L1"
    assert result["score"]["levels"]["L2"]["passed"] is False
    assert result["score"]["levels"]["L2"]["reason"] == "requires two distinct passing run ids; observed 1"


@pytest.mark.parametrize(
    ("case", "mutate", "failed_check"),
    [
        (
            "jsonl memory missing",
            lambda m, r, d, review, replay: r.__setitem__(
                slice(None), [row for row in r if row.get("event") != "memory_note"]
            ),
            "memory_both_surfaces",
        ),
        (
            "duckbrain memory missing",
            lambda m, r, d, review, replay: d["attributes"].__setitem__("events", {}),
            "memory_both_surfaces",
        ),
        (
            "only checkpoint battle artifacts",
            lambda m, r, d, review, replay: r.__setitem__(
                slice(None),
                [row for row in r if row.get("event") not in {"battle_start", "battle_end"}],
            ),
            "organic_battle_pair",
        ),
        (
            "post battle route missing",
            lambda m, r, d, review, replay: [
                row.__setitem__("map_id", 40) for row in r if row.get("map_id") == 11
            ],
            "map_40_to_11_post_battle",
        ),
        (
            "api failure",
            lambda m, r, d, review, replay: r.append(
                {"cycle": 50, "jev_ok": False, "jev_error": "transport failed"}
            ),
            "api_failures",
        ),
        (
            "replay missing",
            lambda m, r, d, review, replay: replay.unlink(),
            "review_and_replay",
        ),
    ],
)
def test_required_evidence_fails_closed(
    tmp_path: Path, case: str, mutate, failed_check: str
) -> None:
    manifest = _manifest()
    rows = _rows()
    summary = _duckbrain_summary()
    review, replay = _artifacts(tmp_path)
    mutate(manifest, rows, summary, review, replay)

    result = e2e.evaluate_evidence(
        manifest=manifest,
        rows=rows,
        duckbrain_summary=summary,
        review_path=review,
        replay_path=replay,
        previous_results=[_previous_pass()],
    )

    assert result["single_run_pass"] is False, case
    assert result["gate_pass"] is False, case
    assert result["checks"][failed_check]["passed"] is False, case
    assert result["score"]["level"] != "L2", case


def test_dead_key_and_twenty_cycle_runs_never_count(tmp_path: Path) -> None:
    manifest = _manifest()
    manifest["cycles"] = 20
    manifest["key_preflight"] = {
        "passed": False,
        "skipped": False,
        "live_key_names": [],
    }

    result = _evaluate(tmp_path, manifest=manifest)

    assert result["checks"]["instrument_shape"]["passed"] is False
    assert result["checks"]["key_liveness"]["passed"] is False
    assert result["single_run_pass"] is False
    assert result["score"]["level"] == "L0"
    assert result["smoke_only"] is True


def test_duplicate_run_id_cannot_supply_second_pass(tmp_path: Path) -> None:
    current_id = _manifest()["run_id"]
    result = _evaluate(tmp_path, previous_results=[_previous_pass(current_id)])

    assert result["single_run_pass"] is True
    assert result["gate_pass"] is False
    assert result["independent_passing_run_ids"] == [current_id]


def test_peak_rss_is_kb_converted_to_mb_and_cap_is_fail_closed(tmp_path: Path) -> None:
    manifest = _manifest()
    manifest["peak_rss_kb"] = 4 * 1024 * 1024 + 1

    result = _evaluate(tmp_path, manifest=manifest)

    assert result["checks"]["peak_rss"]["observed_mb"] == pytest.approx(4096.0009765625)
    assert result["checks"]["peak_rss"]["passed"] is False
    assert result["single_run_pass"] is False


def test_publish_ladder_score_merges_existing_summary_attributes(monkeypatch) -> None:
    writes: list[dict] = []
    monkeypatch.setattr(
        e2e.duckbrain_client,
        "remember",
        lambda **kwargs: writes.append(kwargs) or "memory-id",
    )
    existing = _duckbrain_summary()
    result = {
        "run_id": _manifest()["run_id"],
        "mode": e2e.MODE,
        "score": {"level": "L2", "value": 2, "levels": {}},
        "single_run_pass": True,
        "gate_pass": True,
        "independent_passing_run_ids": ["run-a", _manifest()["run_id"]],
        "checks": {"api_failures": {"passed": True, "observed": 0}},
    }

    e2e.publish_ladder_score(result, existing)

    assert len(writes) == 1
    write = writes[0]
    assert write["key"] == f"/game/runs/{_manifest()['run_id']}/summary"
    assert write["attributes"]["events"] == existing["attributes"]["events"]
    assert write["attributes"]["e2e_acceptance"]["mode"] == e2e.MODE
    assert write["attributes"]["e2e_acceptance"]["ladder_score"] == "L2"
