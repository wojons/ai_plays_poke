"""JEV-2 (PRD v3 stage 7 / AC-6): teacher state repair and JEV re-ask."""

from __future__ import annotations

import io
import json
from copy import deepcopy
from typing import Any

import pytest

import cron_runner
from src.core import jev_client, teacher_client


_TYPED_PATCH: dict[str, Any] = {
    "ok": True,
    "missing_facts": ["the walkable exit below the player"],
    "fact_source": ["RAM minimap"],
    "instruction_patch": "prefer a visible walkable exit over repeated interaction",
    "applies_when": "map topology is present and the last interaction failed",
    "one_shot_action": None,
    "confidence": 0.7,
    "latency_s": 0.2,
    "cost_usd": 0.0002,
}


def _pre_decision() -> dict[str, Any]:
    return {
        "ok": True,
        "sufficient_state": 0.22,
        "missing_class": "map_topology",
        "escalate": True,
        "escalate_reason": "insufficient_state (0.22) missing=map_topology",
    }


class _TeacherClient:
    def __init__(
        self, content: str | None = None, error: Exception | None = None
    ) -> None:
        self.content = content
        self.error = error

    def chat_completion(self, **_kwargs: Any) -> dict[str, Any]:
        if self.error is not None:
            raise self.error
        return {
            "content": self.content,
            "usage": {"cost": 0.0002},
        }


class _ScriptedTeacherClient:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def chat_completion(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return self.responses.pop(0)


def _teacher_json(**overrides: Any) -> str:
    payload = {
        key: value
        for key, value in _TYPED_PATCH.items()
        if key
        in {
            "missing_facts",
            "fact_source",
            "instruction_patch",
            "applies_when",
            "one_shot_action",
            "confidence",
        }
    }
    payload.update(overrides)
    return json.dumps(payload)


def _patch_teacher(monkeypatch: Any, patch: dict[str, Any]) -> None:
    monkeypatch.setattr(
        teacher_client,
        "request_patch",
        lambda **_kwargs: deepcopy(patch),
    )


def test_ac6_teacher_patch_reasks_jev_and_records_improvement(monkeypatch: Any) -> None:
    calls: list[dict[str, Any]] = []

    def fake_ask(state: str, **kwargs: Any) -> dict[str, Any]:
        calls.append({"state": state, **kwargs})
        return {
            "ok": True,
            "sufficient_state": 0.60,
            "missing_class": "none",
            "latency_s": 0.3,
            "cost_usd": 0.0001,
        }

    monkeypatch.setattr(jev_client, "ask", fake_ask)
    log_file = io.StringIO()
    results: list[dict[str, Any]] = []

    record = jev_client.escalate_and_reask(
        _pre_decision(),
        projection="MAP: Pallet Town",
        memory="/game/runs/index: reached Oak's Lab",
        recent_events=[{"cycle": 4, "action": "A", "result": "no change"}],
        milestones=[],
        teacher_model="test/teacher",
        client=_TeacherClient(
            f"<ildocthetag>private reasoning</ildocthetag>{_teacher_json()}|end_of_turn|"
        ),
        log_file=log_file,
        cycle=4,
        results=results,
    )

    assert record["ok"] is True
    assert record["improved"] is True
    assert record["pre_ask"]["sufficient_state"] == 0.22
    assert record["pre_ask"]["missing_class"] == "map_topology"
    assert record["patch"]["instruction_patch"] == _TYPED_PATCH["instruction_patch"]
    assert record["post_ask"]["sufficient_state"] == 0.60
    assert record["post_ask"]["missing_class"] == "none"
    assert len(calls) == 1
    assert len(results) == 1
    assert results[0]["event"] == "teacher_escalation"
    assert json.loads(log_file.getvalue()) == results[0]
    assert (
        "Additional instruction (from a previous escalation"
        in calls[0]["questions"]["next_action"]["instructions"]
    )


def test_equal_or_worse_reask_is_not_improved(monkeypatch: Any) -> None:
    _patch_teacher(monkeypatch, _TYPED_PATCH)
    monkeypatch.setattr(
        jev_client,
        "ask",
        lambda *_args, **_kwargs: {
            "ok": True,
            "sufficient_state": 0.20,
            "missing_class": "map_topology",
        },
    )

    record = jev_client.escalate_and_reask(
        _pre_decision(),
        projection="state",
        memory=None,
        teacher_model="test/teacher",
        client=object(),
    )

    assert record["ok"] is True
    assert record["improved"] is False
    assert record["post_ask"]["sufficient_state"] == 0.20


@pytest.mark.parametrize(
    ("client", "error_text"),
    [
        (_TeacherClient(content="reasoning without JSON"), "no JSON"),
        (_TeacherClient(error=RuntimeError("teacher offline")), "teacher offline"),
    ],
)
def test_teacher_failure_is_fail_closed_and_does_not_reask(
    monkeypatch: Any, client: _TeacherClient, error_text: str
) -> None:
    def unexpected_ask(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("JEV must not be re-asked after an invalid teacher patch")

    monkeypatch.setattr(jev_client, "ask", unexpected_ask)
    record = jev_client.escalate_and_reask(
        _pre_decision(),
        projection="state",
        memory=None,
        teacher_model="test/teacher",
        client=client,
    )

    assert record["ok"] is False
    assert record["improved"] is False
    assert record["patch"]["ok"] is False
    assert error_text in record["error"]
    assert record["post_ask"] is None


def test_apply_patch_changes_only_next_action_instructions() -> None:
    base = jev_client._questions(in_battle=False)
    before = deepcopy(base)

    patched = jev_client.apply_patch(base, _TYPED_PATCH)

    assert patched is not base
    assert patched["next_action"]["criteria"] == before["next_action"]["criteria"]
    assert patched["next_action"]["type"] == before["next_action"]["type"]
    assert patched["next_action"]["instructions"].startswith(
        before["next_action"]["instructions"]
    )
    assert _TYPED_PATCH["instruction_patch"] in patched["next_action"]["instructions"]
    assert _TYPED_PATCH["applies_when"] in patched["next_action"]["instructions"]
    for name in set(before) - {"next_action"}:
        assert patched[name] == before[name]
        assert json.dumps(patched[name], sort_keys=True) == json.dumps(
            before[name], sort_keys=True
        )
    assert base == before


def test_one_shot_action_is_recorded_but_cannot_make_repair_improved(
    monkeypatch: Any,
) -> None:
    one_shot = {**_TYPED_PATCH, "one_shot_action": "DOWN"}
    _patch_teacher(monkeypatch, one_shot)
    monkeypatch.setattr(
        jev_client,
        "ask",
        lambda *_args, **_kwargs: {
            "ok": True,
            "sufficient_state": 0.60,
            "missing_class": "map_topology",
        },
    )

    record = jev_client.escalate_and_reask(
        _pre_decision(),
        projection="state",
        memory=None,
        teacher_model="test/teacher",
        client=object(),
    )

    assert record["patch"]["one_shot_action"] == "DOWN"
    assert record["improved"] is False


def test_escalation_writer_emits_grepable_triple() -> None:
    record = {
        "ok": True,
        "pre_ask": {
            "sufficient_state": 0.22,
            "missing_class": "map_topology",
            "escalate_reason": "insufficient state",
        },
        "patch": deepcopy(_TYPED_PATCH),
        "post_ask": {"sufficient_state": 0.60, "missing_class": "none"},
        "improved": True,
        "latency_s": 0.5,
        "cost_usd": 0.0003,
    }
    buffer = io.StringIO()

    row = teacher_client.write_escalation_row(buffer, cycle=7, record=record)

    text = buffer.getvalue()
    assert text.count('"event": "teacher_escalation"') == 1
    assert text.endswith("\n") and text.count("\n") == 1
    parsed = json.loads(text)
    assert parsed == row
    assert {"pre_ask", "patch", "post_ask"} <= parsed.keys()
    assert parsed["pre_ask"]["sufficient_state"] == 0.22
    assert parsed["post_ask"]["sufficient_state"] == 0.60


def test_absent_memory_is_rendered_as_not_captured() -> None:
    prompt = teacher_client.build_teacher_prompt(
        distributions=_pre_decision(),
        missing_class="map_topology",
        projection="MAP: Pallet Town",
        recent_events=[],
        milestones=[],
        memory=None,
    )

    memory_block = prompt.split("MEMORY (DuckBrain):", 1)[1].split(
        "CURRENT PROJECTION", 1
    )[0]
    assert "(not captured)" in memory_block
    assert "\n0\n" not in memory_block


def test_teacher_event_rows_do_not_change_autonomy_decision_population() -> None:
    results = [
        {
            "cycle": 1,
            "intent": "walk south",
            "jev_answered": True,
            "escalated": False,
        },
        {
            "cycle": 2,
            "event": "teacher_escalation",
            "pre_ask": {"sufficient_state": 0.22},
            "patch": deepcopy(_TYPED_PATCH),
            "post_ask": {"sufficient_state": 0.60},
            "improved": True,
        },
    ]

    counters = cron_runner._autonomy_counters(results)
    teacher = cron_runner.teacher_escalation_records(results)

    assert counters["decisions_total"] == 1
    assert counters["jev_answered"] == 1
    assert counters["escalated"] == 0
    assert teacher == {"count": 1, "improved": 1}

    buffer = io.StringIO()
    cron_runner._write_autonomy_row(buffer, "jev2-run", counters, teacher)
    assert buffer.getvalue().count('"autonomy_ratio"') == 1
    assert json.loads(buffer.getvalue())["teacher_escalations"] == teacher

    summary = cron_runner._format_summary(
        "jev2-run",
        2,
        {"overworld"},
        0,
        2,
        1,
        real_decisions=1,
        autonomy=counters,
        teacher=teacher,
    )
    assert summary.endswith("teacher=1 escalations (1 improved)")


def test_reasoning_budget_exhaustion_retries_once_and_names_failure() -> None:
    client = _ScriptedTeacherClient(
        [
            {
                "content": "",
                "finish_reason": "length",
                "usage": {
                    "completion_tokens": 16,
                    "completion_tokens_details": {"reasoning_tokens": 16},
                },
            },
            {
                "content": "",
                "finish_reason": "length",
                "usage": {
                    "completion_tokens": 32,
                    "completion_tokens_details": {"reasoning_tokens": 32},
                },
            },
        ]
    )

    patch = teacher_client.request_patch(
        distributions=_pre_decision(),
        missing_class="map_topology",
        projection="MAP: Pallet Town",
        teacher_model="test/reasoning-teacher",
        client=client,
        max_tokens=16,
    )

    assert patch["ok"] is False
    assert (
        patch["error"]
        == "teacher token budget exhausted by reasoning tokens (finish_reason=length)"
    )
    assert [call["max_tokens"] for call in client.calls] == [16, 32]


def test_provider_reasoning_field_and_inline_reasoning_normalize_patch() -> None:
    client = _ScriptedTeacherClient(
        [
            {
                "choices": [
                    {
                        "message": {
                            "reasoning_content": "provider-side private reasoning",
                            "content": (
                                "<think>inline private reasoning</think>"
                                f"{_teacher_json()}|end_of_turn|"
                            ),
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"cost": 0.0002},
            }
        ]
    )

    patch = teacher_client.request_patch(
        distributions=_pre_decision(),
        missing_class="map_topology",
        projection="MAP: Pallet Town",
        teacher_model="test/reasoning-teacher",
        client=client,
        max_tokens=32,
    )

    assert patch["ok"] is True
    assert patch["instruction_patch"] == _TYPED_PATCH["instruction_patch"]
    assert patch["applies_when"] == _TYPED_PATCH["applies_when"]


def test_teacher_call_disables_thinking_and_sends_budget() -> None:
    client = _ScriptedTeacherClient(
        [
            {
                "choices": [
                    {
                        "message": {"content": f"{_teacher_json()}|end_of_turn|"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"cost": 0.0002},
            }
        ]
    )

    teacher_client.request_patch(
        distributions=_pre_decision(),
        missing_class="map_topology",
        projection="MAP: Pallet Town",
        teacher_model="test/reasoning-teacher",
        client=client,
        max_tokens=32,
    )

    # Reasoning models bill thinking against max_tokens: the teacher call
    # must disable thinking (docs/dogfood/diagnostics.md) and pass its budget.
    call = client.calls[0]
    assert call["thinking"] == {"type": "disabled"}
    assert call["max_tokens"] == 32


def test_overworld_escalation_reasks_with_distribution_and_is_bounded(
    monkeypatch: Any,
) -> None:
    distribution = {
        "next_action": {"choice": "RIGHT", "distribution": {"RIGHT": 0.51}},
        "missing_class": {
            "choice": "map_topology",
            "distribution": {"map_topology": 0.88},
        },
    }
    pre_decision = {
        **_pre_decision(),
        "next_action": "RIGHT",
        "raw": distribution,
    }
    monkeypatch.setattr(jev_client, "decide", lambda *_args, **_kwargs: pre_decision)

    patch_calls: list[dict[str, Any]] = []

    def fake_request_patch(**kwargs: Any) -> dict[str, Any]:
        patch_calls.append(kwargs)
        return {**deepcopy(_TYPED_PATCH), "one_shot_action": "DOWN"}

    reask_calls: list[dict[str, Any]] = []

    def fake_ask(state: str, **kwargs: Any) -> dict[str, Any]:
        reask_calls.append({"state": state, **kwargs})
        return {
            "ok": True,
            "next_action": "LEFT",
            "sufficient_state": 0.91,
            "missing_class": "none",
            "raw": {"next_action": {"choice": "LEFT", "distribution": {"LEFT": 0.91}}},
        }

    monkeypatch.setattr(teacher_client, "request_patch", fake_request_patch)
    monkeypatch.setattr(jev_client, "ask", fake_ask)
    log_file = io.StringIO()
    results: list[dict[str, Any]] = []
    escalated_classes: set[str] = set()
    kwargs = {
        "goal": "leave Oaks Lab",
        "recent_events": [{"cycle": 3, "action": "UP", "result": "no change"}],
        "last_action": "UP",
        "last_action_changed_state": False,
        "teacher_api_client": object(),
        "teacher_model": "test/reasoning-teacher",
        "teacher_memory": "/game/runs/index: reached Oak's Lab",
        "teacher_log_file": log_file,
        "teacher_cycle": 4,
        "teacher_results": results,
        "escalated_classes": escalated_classes,
    }

    first = cron_runner._jev_overworld_decision({}, **kwargs)
    second = cron_runner._jev_overworld_decision({}, **kwargs)

    assert first["plan"] == ["DOWN"]
    assert first["intent"] == "teacher one-shot DOWN"
    assert second["plan"] == ["RIGHT"]
    assert len(patch_calls) == 1
    assert patch_calls[0]["distributions"] == pre_decision
    assert patch_calls[0]["memory"] == "/game/runs/index: reached Oak's Lab"
    assert len(reask_calls) == 1
    assert (
        _TYPED_PATCH["instruction_patch"]
        in (reask_calls[0]["questions"]["next_action"]["instructions"])
    )
    assert escalated_classes == {"map_topology"}
    assert len(results) == 1
    assert results[0]["event"] == "teacher_escalation"
    assert json.loads(log_file.getvalue())["patch"]["one_shot_action"] == "DOWN"


def test_overworld_teacher_failure_degrades_to_normal_jev_decision(
    monkeypatch: Any,
) -> None:
    decision = {**_pre_decision(), "next_action": "RIGHT", "raw": {}}
    monkeypatch.setattr(jev_client, "decide", lambda *_args, **_kwargs: decision)
    monkeypatch.setattr(
        teacher_client,
        "request_patch",
        lambda **_kwargs: teacher_client.StatePatch.failed("teacher offline").to_dict(),
    )
    monkeypatch.setattr(
        jev_client,
        "ask",
        lambda *_args, **_kwargs: pytest.fail(
            "failed teacher patch must not re-ask JEV"
        ),
    )
    log_file = io.StringIO()
    results: list[dict[str, Any]] = []
    escalated_classes: set[str] = set()

    result = cron_runner._jev_overworld_decision(
        {},
        teacher_api_client=object(),
        teacher_model="test/reasoning-teacher",
        teacher_log_file=log_file,
        teacher_cycle=5,
        teacher_results=results,
        escalated_classes=escalated_classes,
    )

    assert result["plan"] == ["RIGHT"]
    assert result["intent"] == "jev RIGHT"
    assert escalated_classes == {"map_topology"}
    assert len(results) == 1
    assert results[0]["ok"] is False
    assert results[0]["error"] == "teacher offline"
