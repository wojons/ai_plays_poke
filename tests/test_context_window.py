"""S3 rolling prior-turn context tests for the live controller request."""

import io
import json

import cron_runner


class _CapturingClient:
    def __init__(self, reply=None):
        self.calls = []
        self.reply = reply or {"plan": ["UP"], "intent": "continue"}

    def chat_completion(self, **kwargs):
        self.calls.append(kwargs)
        if callable(self.reply):
            payload = self.reply(kwargs)
        else:
            payload = self.reply
        return {"content": json.dumps(payload)}


def _record_turn(history, cycle, action):
    event = {
        "cycle": cycle,
        "screen": "overworld",
        "plan": [action],
        "intent": f"intent for cycle {cycle}",
    }
    cron_runner._record_recent_decision(
        history,
        event,
        outcome=f"executed {action}",
    )


def _user_prompt(client):
    request = client.calls[-1]
    assert request["messages"][1]["role"] == "user"
    return str(request["messages"][1]["content"])


def test_next_request_contains_prior_cycles_and_actions():
    history = []
    _record_turn(history, 1, "UP")
    _record_turn(history, 2, "RIGHT")
    _record_turn(history, 3, "A")
    client = _CapturingClient()

    cron_runner.controller_plan(
        client,
        {"map_name": "Pallet Town"},
        "A",
        "executed A",
        recent_decisions=history,
    )

    prompt = _user_prompt(client)
    assert "RECENT DECISIONS (prior turns):" in prompt
    assert "cycle 1 | screen=overworld | action=UP" in prompt
    assert "cycle 2 | screen=overworld | action=RIGHT" in prompt
    assert "cycle 3 | screen=overworld | action=A" in prompt
    assert "outcome=executed RIGHT" in prompt


def test_recent_decision_block_keeps_only_last_six_turns():
    history = []
    for cycle in range(1, cron_runner.RECENT_DECISION_LIMIT + 11):
        _record_turn(history, cycle, f"ACTION_{cycle}")
    client = _CapturingClient()

    cron_runner.controller_plan(
        client,
        {"map_name": "Pallet Town"},
        "",
        "",
        recent_decisions=history,
    )

    lines = [
        line
        for line in _user_prompt(client).splitlines()
        if line.startswith("- cycle ")
    ]
    expected_cycles = list(range(11, cron_runner.RECENT_DECISION_LIMIT + 11))
    assert len(history) == cron_runner.RECENT_DECISION_LIMIT
    assert lines == [
        (
            f"- cycle {cycle} | screen=overworld | action=ACTION_{cycle} | "
            f"intent=intent for cycle {cycle} | outcome=executed ACTION_{cycle}"
        )
        for cycle in expected_cycles
    ]


def test_model_can_answer_from_three_cycles_back_and_event_records_it():
    history = []
    for cycle, action in enumerate(("UP", "LEFT", "A", "DOWN"), start=1):
        _record_turn(history, cycle, action)

    def reply_from_prior_turn(kwargs):
        prompt = str(kwargs["messages"][1]["content"])
        assert "cycle 2 | screen=overworld | action=LEFT" in prompt
        return {
            "plan": ["LEFT"],
            "intent": "repeat the action from cycle 2",
        }

    client = _CapturingClient(reply_from_prior_turn)
    decision = cron_runner.controller_plan(
        client,
        {"map_name": "Pallet Town"},
        "DOWN",
        "executed DOWN",
        recent_decisions=history,
    )
    event = {
        "cycle": 5,
        "screen": "overworld",
        "plan": decision["plan"],
        "intent": decision["intent"],
    }
    turn = cron_runner._record_recent_decision(
        history,
        event,
        outcome="executed LEFT",
    )

    assert decision["plan"] == ["LEFT"]
    assert decision["intent"] == "repeat the action from cycle 2"
    assert turn == {
        "cycle": 5,
        "screen": "overworld",
        "action": "LEFT",
        "intent": "repeat the action from cycle 2",
        "outcome": "executed LEFT",
    }
    assert history[-1] == turn


def _run_live_teacher_escalation(monkeypatch, recent_decisions):
    initial_decision = {
        "ok": True,
        "next_action": "UP",
        "sufficient_state": 0.2,
        "missing_class": "map_topology",
        "action_confidence": 0.3,
        "ambiguity": 0.8,
        "escalate": True,
        "escalate_reason": "insufficient_state (0.20) missing=map_topology",
        "raw": {"next_action": {"UP": 0.3, "RIGHT": 0.2}},
    }
    monkeypatch.setattr(
        cron_runner.state_projection,
        "build",
        lambda *_args, **_kwargs: "MAP: Pallet Town\nPLAYER TILE: x=5, y=6",
    )
    monkeypatch.setattr(
        cron_runner.jev_client,
        "decide",
        lambda *_args, **_kwargs: dict(initial_decision),
    )
    monkeypatch.setattr(
        cron_runner.jev_client,
        "ask",
        lambda *_args, **_kwargs: {
            "ok": True,
            "next_action": "RIGHT",
            "sufficient_state": 0.8,
            "missing_class": "none",
            "cost_usd": 0.0001,
            "raw": {"next_action": {"RIGHT": 0.9}},
        },
    )
    client = _CapturingClient(
        {
            "missing_facts": ["which exit was already tried"],
            "fact_source": ["prior-turn context"],
            "instruction_patch": (
                "applies_when: choosing the next exit; avoid repeating a failed route"
            ),
            "one_shot_action": None,
            "confidence": 0.9,
        }
    )
    log_file = io.StringIO()
    results = []
    markers = []
    monkeypatch.setattr(
        cron_runner,
        "safe_print",
        lambda *args, **_kwargs: markers.append(" ".join(str(arg) for arg in args)),
    )

    decision = cron_runner._jev_overworld_decision(
        {"map_name": "Pallet Town"},
        recent_decisions=recent_decisions,
        teacher_api_client=client,
        teacher_model="test/teacher",
        teacher_log_file=log_file,
        teacher_cycle=9,
        teacher_results=results,
        escalated_classes=set(),
        handoff_policy=cron_runner.build_handoff_policy(handoff="any"),
        teacher_budget={"used": 0},
    )
    return decision, client, json.loads(log_file.getvalue()), results, markers


def test_live_teacher_prompt_and_logged_record_carry_prior_turns(monkeypatch):
    history = []
    _record_turn(history, 4, "UP")
    _record_turn(history, 5, "RIGHT")
    _record_turn(history, 6, "A")

    decision, client, logged_row, results, markers = _run_live_teacher_escalation(
        monkeypatch, history
    )

    prompt = _user_prompt(client)
    expected_block = cron_runner._recent_decisions_block(history)
    assert expected_block in prompt
    assert "cycle 4 | screen=overworld | action=UP" in prompt
    assert "cycle 5 | screen=overworld | action=RIGHT" in prompt
    assert "cycle 6 | screen=overworld | action=A" in prompt
    assert logged_row["request_prompt"] == prompt
    assert expected_block in logged_row["request_prompt"]
    assert results == [logged_row]
    assert markers == ["  [CTX] teacher request carried 3 prior turns"]
    assert decision["plan"] == ["RIGHT"]
    print("captured teacher request prior-turn block:")
    print(expected_block)
    print("logged request_prompt matches captured request: true")


def test_live_teacher_request_without_prior_turns_has_no_block_or_marker(monkeypatch):
    _decision, client, logged_row, results, markers = _run_live_teacher_escalation(
        monkeypatch, None
    )

    prompt = _user_prompt(client)
    assert "RECENT DECISIONS (prior turns):" not in prompt
    assert logged_row["request_prompt"] == prompt
    assert "RECENT DECISIONS (prior turns):" not in logged_row["request_prompt"]
    assert results == [logged_row]
    assert not any("[CTX]" in marker for marker in markers)
