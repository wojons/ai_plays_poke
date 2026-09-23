"""DF-AIPP-2: the run ladder must not count the same battle twice.

``_record_run_memory`` reads a run's ladder out of ``results``. Every battle
transition is recorded there in TWO shapes that describe the same moment:

* a top-level row — ``{"cycle": N, "event": "battle_start"}`` when the battle
  screen is entered and ``{"cycle": N, "event": "battle_end"}`` when it is left
  (cron_runner's battle start/end logging), and
* the nested ``battle_events`` list of the per-cycle state-window row of that
  same iteration (``entry["battle_events"]`` — the StateWindow transitions).

The recorder used to add the nested list lengths *plus* the top-level rows
(the latter only on rows that carried no nested list), so live run
``dgf_0923b`` reported ``ladder.battle_events`` 6 — 2 top-level rows and 4
nested events for a single battle. It now counts the top-level ``battle_*``
event rows only; nested lists contribute nothing.

Invariant pinned here: ``ladder.battle_events`` equals the number of top-level
``battle_*`` event rows in the same log (each battle_start and battle_end row
counts once), independently recomputed from the fixture in each test.
"""

from __future__ import annotations

from typing import Any

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


def _summary_attributes(writes: list[dict[str, Any]], run_id: str) -> dict[str, Any]:
    for write in writes:
        if write["key"] == f"/game/runs/{run_id}/summary":
            return write["attributes"]  # type: ignore[no-any-return]
    raise AssertionError(f"no /game/runs/{run_id}/summary write recorded")


def _top_level_battle_rows(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Independent oracle: the top-level battle transition rows of a log."""
    return [row for row in results if str(row.get("event", "")).startswith("battle_")]


def _nested_events_total(results: list[dict[str, Any]]) -> int:
    """The nested state-window events that must NOT reach the ladder."""
    return sum(
        len(row["battle_events"])
        for row in results
        if isinstance(row.get("battle_events"), list)
    )


def test_ladder_counts_top_level_rows_and_ignores_nested_lists(monkeypatch) -> None:
    """2 battle_start + 2 battle_end rows, 4 nested events -> ladder 4."""
    writes = _capture_writes(monkeypatch)
    results: list[dict[str, Any]] = [
        # Cycles 5/6/7: per-cycle rows nesting the same transitions (1+1+2=4).
        {
            "cycle": 5,
            "screen": "battle",
            "battle_events": [{"event": "battle_start"}],
        },
        {
            "cycle": 6,
            "screen": "battle",
            "battle_events": [{"event": "battle_start"}],
        },
        {
            "cycle": 7,
            "screen": "battle",
            "battle_events": [
                {"event": "battle_start"},
                {"event": "battle_end", "outcome": "won"},
            ],
        },
        # Top-level rows: two battles' worth of start+end transitions.
        {"cycle": 5, "event": "battle_start", "battle_type": "wild"},
        {"cycle": 7, "event": "battle_start", "battle_type": "trainer"},
        {"cycle": 6, "event": "battle_end", "next_screen": "dialog"},
        {"cycle": 7, "event": "battle_end", "next_screen": "overworld"},
    ]
    # Fixture guards: the nested lists really do total 4 (the double-count
    # fuel) and the log really does hold 4 top-level battle rows.
    assert _nested_events_total(results) == 4
    assert len(_top_level_battle_rows(results)) == 4

    cron_runner._record_run_memory(
        "df-aipp-2",
        results,
        extra={"log_path": "cron_logs/run_df_aipp_2.jsonl"},
    )

    attributes = _summary_attributes(writes, "df-aipp-2")
    ladder = attributes["ladder"]
    # 4 — not 8 (nested + top-level) and not 0.
    assert ladder["battle_events"] == 4
    assert ladder["battle_events"] == len(_top_level_battle_rows(results))
    assert attributes["battle_events"] == 4
    assert "battle_events" in ladder


def test_live_incident_shape_no_longer_reports_six(monkeypatch) -> None:
    """Run dgf_0923b's exact shape: one battle, 2 top-level rows, 4 nested."""
    writes = _capture_writes(monkeypatch)
    results: list[dict[str, Any]] = [
        {"cycle": 4, "screen": "battle", "battle_events": []},
        {
            "cycle": 5,
            "screen": "battle",
            "battle_events": [{"event": "battle_start"}],
        },
        {
            "cycle": 6,
            "screen": "battle",
            "battle_events": [{"event": "battle_start"}],
        },
        {
            "cycle": 7,
            "screen": "battle",
            "battle_events": [
                {"event": "battle_start"},
                {"event": "battle_end", "outcome": "won"},
            ],
        },
        {"cycle": 8, "screen": "battle", "battle_events": []},
        {"cycle": 5, "event": "battle_start", "battle_type": "trainer"},
        {"cycle": 7, "event": "battle_end", "next_screen": "overworld"},
    ]
    assert _nested_events_total(results) == 4
    assert len(_top_level_battle_rows(results)) == 2

    cron_runner._record_run_memory(
        "dgf-sim-b",
        results,
        extra={"log_path": "cron_logs/run_dgf_sim_b.jsonl"},
    )

    attributes = _summary_attributes(writes, "dgf-sim-b")
    assert attributes["ladder"]["battle_events"] == 2
    # The value the incident reported: both sources summed.
    assert _nested_events_total(results) + len(_top_level_battle_rows(results)) == 6


def test_nested_lists_alone_contribute_nothing(monkeypatch) -> None:
    """A log with only nested state-window lists reports 0, key still present."""
    writes = _capture_writes(monkeypatch)
    results: list[dict[str, Any]] = [
        {
            "cycle": 3,
            "screen": "battle",
            "battle_events": [
                {"event": "battle_start"},
                {"event": "battle_end", "outcome": "won"},
            ],
        },
    ]
    assert _nested_events_total(results) == 2

    cron_runner._record_run_memory("nested-only", results)

    attributes = _summary_attributes(writes, "nested-only")
    assert attributes["ladder"]["battle_events"] == 0
    assert attributes["battle_events"] == 0
