"""DF-JEV-3: battle rows expose the real StateWindow action and JEV payload."""

from __future__ import annotations

from typing import Any

import pytest

import cron_runner
from src.core import jev_client


def test_real_battle_path_stamps_executed_action_and_jev_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = {
        "next_action": {
            "choice": "MOVE_3",
            "distribution": {"MOVE_1": 0.05, "MOVE_3": 0.95},
        },
        "phase": {"choice": "BATTLE", "distribution": {"BATTLE": 1.0}},
    }
    calls: list[tuple[str, dict[str, Any]]] = []

    def fake_decide(state: str, **kwargs: Any) -> dict[str, Any]:
        calls.append((state, kwargs))
        return {
            "ok": True,
            "next_action": "MOVE_3",
            "raw": raw,
            "escalate": False,
        }

    monkeypatch.setattr(cron_runner, "DECISION_MODE", cron_runner.MODE_SYSTEM1)
    monkeypatch.setattr(jev_client, "decide", fake_decide)
    game_state = {
        "result": "battle",
        "battle_state": {"player": {"moves": [{"slot": 1}, {"slot": 3}]}},
    }
    observation = cron_runner._observe_battle_decision(game_state)
    row = {"cycle": 5, "screen": "battle", "action": "select_move({'move_number': 3})"}

    cron_runner._stamp_battle_observability(
        row,
        state_type="battle",
        history=[
            {
                "tool_call": {
                    "name": "select_move",
                    "arguments": {"move_number": 3},
                }
            }
        ],
        jev_decision=observation,
    )

    assert len(calls) == 1
    assert calls[0][1] == {"in_battle": True, "act_phase": True}
    assert row["phase"] == "BATTLE"
    assert row["battle_action"] == "MOVE_3"
    assert row["raw_distribution"] == raw


def test_non_battle_shaped_jev_answer_stamps_effective_fallback_without_fabrication() -> (
    None
):
    row = {"cycle": 6, "screen": "battle", "action": "select_move({'move_number': 1})"}

    cron_runner._stamp_battle_observability(
        row,
        state_type="battle",
        history=[
            {
                "tool_call": {
                    "name": "select_move",
                    "arguments": {"move_number": 1},
                },
                "forced": True,
            }
        ],
        jev_decision={"ok": True, "next_action": "A", "raw": None},
    )

    assert row["battle_action"] == "MOVE_1"
    assert row["raw_distribution"] is None


def test_non_battle_decision_row_is_unchanged() -> None:
    row = {
        "cycle": 7,
        "screen": "overworld",
        "plan": ["UP"],
        "raw_distribution": {"existing": "overworld payload"},
    }
    original = dict(row)

    cron_runner._stamp_battle_observability(
        row,
        state_type="overworld",
        history=[
            {
                "tool_call": {
                    "name": "select_move",
                    "arguments": {"move_number": 4},
                }
            }
        ],
        jev_decision={"raw": {"battle": "must not leak"}},
    )

    assert row == original
