"""DF-JEV-3: battle rows expose the real StateWindow action and JEV payload."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

import cron_runner
from src.core import jev_client
from src.core.global_context import GlobalContext
from src.core.state_window import StateWindow


def test_normal_battle_routes_jev_action_through_state_window_and_stamps_row(
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
    battle_tool_call = cron_runner._jev_battle_tool_call(observation, game_state)
    emulator = MagicMock()

    with (
        patch("src.core.state_window.OpenRouterClient") as client_cls,
        patch(
            "src.core.state_window.execute_tool_call", return_value="selected move 3"
        ) as execute,
        patch("src.core.state_window.battle_status", return_value="wild"),
    ):
        window = StateWindow(
            "battle",
            GlobalContext(),
            emulator,
            game_state,
            max_steps=5,
            battle_tool_call=battle_tool_call,
        )
        window._check_outcome = MagicMock(return_value=None)
        result = window.run()

    row = {
        "cycle": 5,
        "screen": "battle",
        "action": "select_move({'move_number': 3})",
    }
    cron_runner._stamp_battle_observability(
        row,
        state_type="battle",
        history=window._history,
        jev_decision=observation,
    )

    assert len(calls) == 1
    assert calls[0][1] == {"in_battle": True, "act_phase": True}
    execute.assert_called_once_with(
        emulator,
        tool_name="select_move",
        arguments={"move_number": 3},
    )
    client_cls.return_value.send_tool_request.assert_not_called()
    assert result["steps"] == 1
    assert row["phase"] == "BATTLE"
    assert row["battle_action"] == "MOVE_3"
    assert row["raw_distribution"] == raw


def test_jev_unavailable_keeps_existing_state_window_fallback() -> None:
    game_state = {
        "result": "battle",
        "battle_state": {"player": {"moves": [{"slot": 1}]}},
    }
    unavailable = {"ok": False, "error": "JEV unavailable"}

    assert cron_runner._jev_battle_tool_call(None, game_state) is None
    assert cron_runner._jev_battle_tool_call(unavailable, game_state) is None

    emulator = MagicMock()
    query = '{"name":"query_global","arguments":{"question":"best move?"}}'
    with (
        patch("src.core.state_window.OpenRouterClient") as client_cls,
        patch(
            "src.core.state_window.execute_tool_call", return_value="selected move 1"
        ) as execute,
    ):
        client_cls.return_value.send_tool_request.return_value = query
        window = StateWindow(
            "battle",
            GlobalContext(),
            emulator,
            game_state,
            max_steps=3,
            battle_tool_call=cron_runner._jev_battle_tool_call(unavailable, game_state),
        )
        window._check_outcome = MagicMock(return_value=None)
        window.run()

    assert client_cls.return_value.send_tool_request.call_count == 3
    execute.assert_called_once_with(
        emulator,
        tool_name="select_move",
        arguments={"move_number": 1},
    )


def test_public_battle_vocabulary_matches_jev_questions() -> None:
    criteria = jev_client._questions(in_battle=True)["next_action"]["criteria"]

    assert set(criteria) == jev_client.BATTLE_ACTIONS


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
