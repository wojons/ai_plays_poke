"""GAP-053: the final summary must separate real AI decisions from
parse_fallback blind A-presses.

The 2026-09-09b run made 0/20 successful LLM calls yet printed
``Done. 23 actions.`` — those 23 "actions" were ``parse_fallback`` plan
``["A"]`` presses, not controller decisions. These tests drive the real
``controller_plan`` response path with a scripted client (no emulator, no
network) and then feed the returned decisions through the same
classification and summary aggregation the main loop uses.
"""

from __future__ import annotations

from typing import Any

import pytest

import cron_runner
from src.core import duckbrain_client


class _ScriptedClient:
    """OpenRouterClient stand-in returning one canned raw response."""

    def __init__(self, content: str) -> None:
        self.content = content
        self.calls = 0

    def chat_completion(self, **kwargs: Any) -> dict[str, Any]:
        self.calls += 1
        return {"content": self.content}


def _decision(raw: str) -> dict[str, Any]:
    """Run the real controller prompt/parse path over one canned response."""
    client = _ScriptedClient(raw)
    decision = cron_runner.controller_plan(
        client,
        {"map_name": "Pallet Town"},
        "",
        "",
    )
    assert client.calls == 1, "controller_plan made no LLM call"
    return decision


def _plan_row(decision: dict[str, Any], cycle: int = 1) -> dict[str, Any]:
    """Mirror the main loop's plan-entry row (cron_runner.py plan_entry)."""
    return {
        "cycle": cycle,
        "screen": "overworld",
        "plan": decision.get("plan", ["A"]),
        "intent": decision.get("intent", ""),
        "controller_raw": decision.get("raw_response", ""),
    }


# ── intent classification ───────────────────────────────────────────


def test_unreadable_response_marks_parse_fallback() -> None:
    # Valid JSON, but the model returned no plan/button → the runner
    # blind-presses A and the intent must say so.
    decision = _decision('{"thought": "I am not sure what to do"}')

    assert decision["plan"] == ["A"]
    assert decision["intent"] == "parse_fallback"
    assert "_parse_error" not in decision


def test_unparseable_response_marks_parse_failure_fallback() -> None:
    decision = _decision("the model rambled and never emitted JSON")

    assert decision["plan"] == ["A"]
    assert decision["intent"] == "parse_failure_fallback"


def test_real_controller_response_keeps_its_own_intent() -> None:
    decision = _decision('{"plan": ["UP", "A"], "intent": "walk north to Route 1"}')

    assert decision["plan"] == ["UP", "A"]
    assert decision["intent"] == "walk north to Route 1"
    assert decision["intent"] not in cron_runner.FALLBACK_INTENTS


def test_classify_splits_real_from_fallback_decisions() -> None:
    fallback = _decision('{"thought": "no plan"}')
    failure = _decision("not json")
    real = _decision('{"plan": ["DOWN"], "intent": "leave the house"}')
    # A real response with no intent field is still a real decision.
    empty_intent = _decision('{"plan": ["START"]}')

    rows = [
        _plan_row(fallback, 1),
        _plan_row(real, 2),
        _plan_row(failure, 3),
        _plan_row(empty_intent, 4),
        # Non-decision rows carry no intent key and must not be counted.
        {"cycle": 5, "event": "memory_goal", "goal": "beat Brock"},
        {"cycle": 6, "error": "boom"},
    ]

    assert cron_runner._classify_decision_intents(rows) == (2, 2)


def test_dead_key_run_counts_every_press_as_fallback() -> None:
    # 0 successful LLM calls: the exact 2026-09-09b failure shape.
    rows = [
        _plan_row(_decision('{"thought": "no plan"}'), cycle) for cycle in range(1, 24)
    ]

    real, fallback = cron_runner._classify_decision_intents(rows)

    assert real == 0
    assert fallback == 23
    assert len(rows) == 23  # total actions is unchanged, just disambiguated


# ── summary line ────────────────────────────────────────────────────


def test_summary_line_appends_decision_counts_and_keeps_legacy_shape() -> None:
    line = cron_runner._format_summary(
        "dgf_0923b",
        20,
        {"overworld"},
        5,
        20,
        3,
        real_decisions=14,
        fallback_decisions=6,
    )

    # Legacy shape preserved byte-for-byte up to the appended fields.
    assert line.startswith(
        "[dgf_0923b] Done. 20 actions. Screens: {'overworld'} "
        "| lock-rate: 5/20 cycles with direction-lock warnings (25%) "
        "| distinct tiles: 3 "
    )
    assert line.endswith("| real_decisions=14 fallback_decisions=6")


def test_dead_key_run_summary_prints_zero_real_decisions() -> None:
    rows = [
        _plan_row(_decision('{"thought": "still no plan"}'), cycle)
        for cycle in range(1, 24)
    ]
    real, fallback = cron_runner._classify_decision_intents(rows)

    line = cron_runner._format_summary(
        "2026-09-09b",
        len(rows),
        {"overworld"},
        0,
        len(rows),
        0,
        real_decisions=real,
        fallback_decisions=fallback,
    )

    assert "real_decisions=0" in line
    assert "fallback_decisions=23" in line
    # The misleading legacy prefix is still there for log parsers.
    assert "Done. 23 actions." in line


def test_summary_defaults_to_zero_when_counts_not_supplied() -> None:
    # Older callers/tests keep the 6-arg form; the new fields default.
    line = cron_runner._format_summary("run1", 20, {"overworld"}, 5, 20, 3)

    assert "Done. 20 actions." in line
    assert "real_decisions=0 fallback_decisions=0" in line


# ── JSONL summary row (DuckBrain) ───────────────────────────────────


def test_record_run_memory_summary_attributes_carry_decision_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writes: list[dict[str, Any]] = []
    monkeypatch.setattr(
        duckbrain_client,
        "remember",
        lambda **kwargs: writes.append(kwargs) or "memory-id",
    )
    monkeypatch.setattr(
        duckbrain_client,
        "get",
        lambda **kwargs: {"attributes": {"runs": []}},
    )

    results = [
        _plan_row(_decision('{"plan": ["UP"], "intent": "walk north"}'), 1),
        _plan_row(_decision('{"thought": "no plan"}'), 2),
        _plan_row(_decision("not json"), 3),
        {"cycle": 4, "event": "memory_note", "note": "Oak talks a lot."},
    ]

    cron_runner._record_run_memory("gap053-run", results)

    summary = {w["key"]: w for w in writes}["/game/runs/gap053-run/summary"]
    attributes = summary["attributes"]
    assert attributes["real_decisions"] == 1
    assert attributes["fallback_decisions"] == 2
    assert attributes["n_actions"] == sum(bool(row.get("action")) for row in results)
