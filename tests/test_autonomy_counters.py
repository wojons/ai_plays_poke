"""JEV-1 (PRD v3 AC-1): per-run autonomy counters over per-decision rows.

AC-1: "Given a completed run, when the run closes, then the run log contains
decisions_total, jev_answered, escalated and autonomy_ratio", with the
anti-gaming clause that the counters must be derived from per-decision rows —
a green-but-doing-nothing implementation reports ``decisions_total = 0`` and
fails the ratio assertion.

These tests drive the real ``controller_plan`` parse path with a scripted
client (no emulator, no network, no live LLM call) to build decision rows, mix
them with event/error rows, and push the population through the same
``_autonomy_counters`` / ``_format_summary`` / ``_write_autonomy_row`` code the
run closeout uses.
"""

from __future__ import annotations

import ast
import io
import json
from pathlib import Path
from typing import Any

import pytest

import cron_runner


class _ScriptedClient:
    """OpenRouterClient stand-in returning one canned raw response."""

    def __init__(self, content: str) -> None:
        self.content = content

    def chat_completion(self, **kwargs: Any) -> dict[str, Any]:
        return {"content": self.content}


def _decision(raw: str) -> dict[str, Any]:
    """Run the real controller prompt/parse path over one canned response."""
    return cron_runner.controller_plan(
        _ScriptedClient(raw),
        {"map_name": "Pallet Town"},
        "",
        "",
    )


# Rows that are NOT controller decisions: they carry no ``intent`` key and
# must move no counter (event rows, error rows, per-button execution rows).
_NON_DECISION_ROWS: list[dict[str, Any]] = [
    {"cycle": 5, "event": "memory_goal", "goal": "beat Brock"},
    {"cycle": 6, "event": "giveup_walk", "injected": ["A"]},
    {"cycle": 7, "event": "state_saved", "slot": 0},
    {"cycle": 8, "error": "boom"},
    {"cycle": 9, "screen": "battle", "action": "press_button({'button': 'a'})"},
]


def _decision_row(
    cycle: int,
    *,
    jev_answered: bool = False,
    escalated: bool = False,
    missing_class: str | None = None,
    intent: str = "press A",
) -> dict[str, Any]:
    """One main-loop decision row the way ``plan_entry`` writes it (JEV-1)."""
    return {
        "cycle": cycle,
        "screen": "overworld",
        "plan": ["A"],
        "intent": intent,
        "jev_answered": jev_answered,
        "escalated": escalated,
        "missing_class": missing_class,
    }


def _real_fallback_row(cycle: int) -> dict[str, Any]:
    """A real controller response with no intent field is still a decision."""
    decision = _decision('{"plan": ["START"]}')
    return _decision_row(cycle, intent=decision.get("intent", ""))


def _assigned_expr(name: str) -> ast.expr:
    """The value expression of the first ``<name> = ...`` in cron_runner.py.

    ``plan_entry`` and the ``_missing_class`` local are both built inline in
    ``main()`` (no seam to call), so the stamping guarantee is asserted
    against the source of truth itself rather than against a copy of the
    literal in this file.
    """
    source = Path(cron_runner.__file__).read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name
            for target in node.targets
        ):
            return node.value
    raise AssertionError(f"{name} assignment not found in cron_runner.py")


def _plan_entry_source() -> ast.Dict:
    value = _assigned_expr("plan_entry")
    assert isinstance(value, ast.Dict)
    return value


# ── decision-row schema ─────────────────────────────────────────────


def test_decision_row_carries_the_autonomy_fields() -> None:
    entry = _plan_entry_source()
    fields = {
        key.value: ast.unparse(value)
        for key, value in zip(entry.keys, entry.values)
        if isinstance(key, ast.Constant)
    }

    assert {"intent", "jev_answered", "escalated", "missing_class"} <= set(fields)
    # Sourced from the decision payload: JEV-2/JEV-4 make the counters
    # non-zero by putting these keys on the decision dict, not by editing the
    # row. ``missing_class`` is normalized to str|None through a local first.
    assert "decision.get('jev_answered'" in fields["jev_answered"]
    assert "decision.get('escalated'" in fields["escalated"]
    assert "_missing_class" in fields["missing_class"]
    assert "decision.get('missing_class'" in ast.unparse(
        _assigned_expr("_missing_class")
    )


# ── counters ────────────────────────────────────────────────────────


def test_counters_count_only_decision_rows() -> None:
    rows = [
        # real response (intent authored by the controller)
        _decision_row(1, jev_answered=True),
        # parse_fallback / parse_failure_fallback — still decisions
        {**_decision_row(2), "intent": "parse_fallback"},
        {**_decision_row(3), "intent": "parse_failure_fallback"},
        # real response with an empty intent string
        _real_fallback_row(4),
        *_NON_DECISION_ROWS,
    ]

    block = cron_runner._autonomy_counters(rows)

    assert block["decisions_total"] == 4
    assert block["jev_answered"] == 1
    assert block["escalated"] == 0
    assert block["autonomy_ratio"] == 0.25
    # Same population as the GAP-053 split, so the two summaries agree.
    real, fallback = cron_runner._classify_decision_intents(rows)
    assert (real, fallback) == (2, 2)
    assert block["decisions_total"] == real + fallback


def test_non_decision_rows_alone_yield_zero_decisions() -> None:
    block = cron_runner._autonomy_counters(list(_NON_DECISION_ROWS))

    assert block["decisions_total"] == 0
    assert block["jev_answered"] == 0
    assert block["escalated"] == 0
    # Anti-gaming: 0/0 is reported as None, never as a fabricated ratio.
    assert block["autonomy_ratio"] is None
    assert block["escalation_rate_by_missing_class"] == {}


def test_empty_results_yield_zero_decisions_and_no_ratio() -> None:
    block = cron_runner._autonomy_counters([])

    assert block["decisions_total"] == 0
    assert block["autonomy_ratio"] is None


def test_autonomy_ratio_equals_jev_answered_over_decisions_total() -> None:
    rows = [_decision_row(cycle, jev_answered=cycle <= 3) for cycle in range(1, 8)]
    rows.extend(_NON_DECISION_ROWS)

    block = cron_runner._autonomy_counters(rows)

    assert block["decisions_total"] == 7
    assert block["jev_answered"] == 3
    assert (
        block["autonomy_ratio"]
        == round(3 / 7, 4)
        == pytest.approx(block["jev_answered"] / block["decisions_total"], abs=1e-4)
    )


def test_escalation_rate_by_missing_class() -> None:
    rows = [
        _decision_row(1, escalated=True, missing_class="map_topology"),
        _decision_row(2, escalated=True, missing_class="map_topology"),
        _decision_row(3, escalated=True, missing_class="object_purpose"),
        _decision_row(4, escalated=True, missing_class=None),
        # A confident JEV answer is neither escalated nor counted as a class.
        _decision_row(5, jev_answered=True),
    ]

    block = cron_runner._autonomy_counters(rows)

    assert block["decisions_total"] == 5
    assert block["escalated"] == 4
    assert block["escalation_rate_by_missing_class"] == {
        "map_topology": 0.5,
        "object_purpose": 0.25,
        None: 0.25,
    }
    assert block["autonomy_ratio"] == 0.2


def test_escalated_row_with_non_string_missing_class_lands_in_the_none_bucket() -> None:
    row = _decision_row(1, escalated=True)
    row["missing_class"] = 123  # a malformed taxonomy token is not a class

    block = cron_runner._autonomy_counters([row])

    assert block["escalated"] == 1
    assert block["escalation_rate_by_missing_class"] == {None: 1.0}


# ── run-log row (AC-1's grep target) ────────────────────────────────


def test_write_autonomy_row_emits_one_json_line_with_the_ratio() -> None:
    rows = [
        _decision_row(1, jev_answered=True),
        _decision_row(2, escalated=True, missing_class="map_topology"),
        *_NON_DECISION_ROWS,
    ]
    block = cron_runner._autonomy_counters(rows)

    buffer = io.StringIO()
    row = cron_runner._write_autonomy_row(buffer, "jev1-run", block)
    text = buffer.getvalue()

    # `grep -c '"autonomy_ratio"' cron_logs/run_<id>.jsonl` >= 1
    assert text.count('"autonomy_ratio"') == 1
    assert text.endswith("\n") and text.count("\n") == 1

    parsed = json.loads(text)
    assert parsed == row
    assert parsed["event"] == cron_runner.AUTONOMY_LOG_EVENT
    assert parsed["run_id"] == "jev1-run"
    assert parsed["decisions_total"] == 2
    assert parsed["jev_answered"] == 1
    assert parsed["escalated"] == 1
    assert parsed["autonomy_ratio"] == 0.5
    assert parsed["escalation_rate_by_missing_class"] == {"map_topology": 1.0}


def test_written_autonomy_row_is_not_itself_a_decision_row() -> None:
    block = cron_runner._autonomy_counters([_decision_row(1, jev_answered=True)])
    buffer = io.StringIO()
    cron_runner._write_autonomy_row(buffer, "jev1-run", block)

    # Re-counting the emitted row cannot inflate the population it reports.
    recount = cron_runner._autonomy_counters([json.loads(buffer.getvalue())])

    assert recount["decisions_total"] == 0
    assert recount["autonomy_ratio"] is None


def test_autonomy_row_is_appended_after_the_run_rows() -> None:
    rows = [_decision_row(1, jev_answered=True)]
    buffer = io.StringIO()
    for entry in rows:
        buffer.write(json.dumps(entry, default=str) + "\n")

    cron_runner._write_autonomy_row(
        buffer, "jev1-run", cron_runner._autonomy_counters(rows)
    )

    lines = buffer.getvalue().splitlines()
    assert len(lines) == 2
    assert '"autonomy_ratio"' in lines[-1]
    assert "autonomy_ratio" not in lines[0]


# ── summary line ────────────────────────────────────────────────────


def test_summary_line_appends_autonomy_after_the_gap053_counters() -> None:
    rows = [
        _decision_row(cycle, jev_answered=cycle <= 3, escalated=cycle >= 6)
        for cycle in range(1, 8)
    ]
    block = cron_runner._autonomy_counters(rows)
    assert (block["jev_answered"], block["escalated"]) == (3, 2)

    line = cron_runner._format_summary(
        "jev1-run",
        20,
        {"overworld"},
        5,
        20,
        3,
        real_decisions=7,
        fallback_decisions=0,
        autonomy=block,
    )

    assert line.endswith(
        "| real_decisions=7 fallback_decisions=0 autonomy=3/7 (2 escalated)"
    )
    # The legacy prefix is untouched.
    assert line.startswith("[jev1-run] Done. 20 actions. Screens: {'overworld'} ")


def test_summary_line_prints_na_when_the_run_made_no_decisions() -> None:
    block = cron_runner._autonomy_counters(list(_NON_DECISION_ROWS))

    line = cron_runner._format_summary(
        "jev1-run", 5, {"overworld"}, 0, 5, 0, autonomy=block
    )

    assert "real_decisions=0 fallback_decisions=0" in line
    assert line.endswith("autonomy=n/a (0 decisions, 0 escalated)")
