"""S3 rolling prior-turn context tests for the live controller request."""

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
