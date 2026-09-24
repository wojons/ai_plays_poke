"""JEV-4: starter and battle assists must preserve JEV's decision."""

from __future__ import annotations

import inspect
from typing import Any

import pytest

import cron_runner
from src.core import jev_client


_STARTER_X = {6: "CHARMANDER", 8: "SQUIRTLE", 10: "BULBASAUR"}


class _StarterHarness:
    """Small Oak's Lab state machine for the starter-selection helper."""

    def __init__(self) -> None:
        self.x = 6
        self.screen = "menu"
        self.party = 0
        self.species: str | None = None
        self.pressed: list[str] = []

    def press_button(self, button: str, *, frames: int) -> None:
        del frames
        self.pressed.append(button)
        if self.screen == "menu":
            if button == "a":
                self.party = 1
                self.species = _STARTER_X[self.x]
                self.screen = "dialog"
            elif button == "b":
                self.screen = "overworld"
            return
        if self.screen != "overworld":
            return
        if button == "left":
            self.x -= 1
        elif button == "right":
            self.x += 1
        elif button == "a":
            self.screen = "menu"

    def fast_forward(self, frames: int) -> None:
        del frames

    def party_count(self) -> int:
        return self.party

    def first_party_species_hint(self) -> str | None:
        return self.species.title() if self.species else None

    def player_tile_x(self) -> int:
        return self.x

    def screen_type(self) -> str:
        return self.screen

    def read_menu_state(self) -> dict[str, Any]:
        return {"menu_id": 1, "active": True} if self.screen == "menu" else {}

    def read_dialog_text(self) -> str:
        return f"Do you want {_STARTER_X[self.x]}?"


def _pick_starter(
    monkeypatch: pytest.MonkeyPatch, choice: str
) -> tuple[str, list[str]]:
    harness = _StarterHarness()
    calls: list[dict[str, Any]] = []

    def fake_decide(state: str, **kwargs: Any) -> dict[str, Any]:
        calls.append({"state": state, **kwargs})
        return {
            "ok": True,
            "next_action": choice,
            "phase": "STARTER",
            "raw": {
                "next_action": {
                    "choice": choice,
                    "distribution": {
                        "CHARMANDER": 0.05,
                        "SQUIRTLE": 0.90 if choice == "SQUIRTLE" else 0.05,
                        "BULBASAUR": 0.90 if choice == "BULBASAUR" else 0.05,
                    },
                }
            },
            "escalate": False,
            "missing_class": "none",
        }

    monkeypatch.setattr(jev_client, "decide", fake_decide)
    decision_row: dict[str, Any] = {}
    count = cron_runner._select_starter_from_menu(
        harness,
        harness,
        decision_out=decision_row,
    )

    assert count == 1
    assert harness.species is not None
    assert len(calls) == 1
    questions = calls[0]["questions"]
    assert set(questions["next_action"]["criteria"]) == {
        "BULBASAUR",
        "CHARMANDER",
        "SQUIRTLE",
    }
    assert decision_row["phase"] == "STARTER"
    assert decision_row["starter_choice"] == choice
    assert decision_row["raw_distribution"]["next_action"]["choice"] == choice
    assert decision_row["jev_answered"] is True
    assert harness.first_party_species_hint() == harness.species.title()
    return harness.species, harness.pressed


def test_forcing_different_jev_choice_selects_different_starter_species(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    squirtle, squirtle_buttons = _pick_starter(monkeypatch, "SQUIRTLE")
    bulbasaur, bulbasaur_buttons = _pick_starter(monkeypatch, "BULBASAUR")

    assert squirtle == "SQUIRTLE"
    assert bulbasaur == "BULBASAUR"
    assert squirtle != bulbasaur
    assert squirtle_buttons != bulbasaur_buttons


def test_battle_recovery_executes_jev_action_and_records_distribution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = {
        "next_action": {
            "choice": "MOVE_3",
            "distribution": {"MOVE_1": 0.01, "MOVE_3": 0.94, "RUN": 0.05},
        },
        "phase": {"choice": "BATTLE", "distribution": {"BATTLE": 1.0}},
    }
    monkeypatch.setattr(
        jev_client,
        "decide",
        lambda *_args, **_kwargs: {
            "ok": True,
            "next_action": "MOVE_3",
            "phase": "BATTLE",
            "raw": raw,
            "escalate": False,
            "missing_class": "none",
        },
    )
    emitted: list[tuple[str, dict[str, Any]]] = []

    def fake_execute(_emu: Any, tool: str, arguments: dict[str, Any]) -> str:
        emitted.append((tool, arguments))
        return "Selected move 3."

    monkeypatch.setattr(cron_runner, "execute_tool_call", fake_execute)
    decision_row: dict[str, Any] = {}
    strategy, description = cron_runner._escalating_recovery(
        object(),
        recovery_level=4,
        last_direction="UP",
        last_saved_slot=3,
        game_state={
            "result": "battle",
            "battle_state": {
                "battle_type": "trainer",
                "player": {"moves": [{"slot": 1}, {"slot": 2}, {"slot": 3}]},
                "enemy": {"name": "Squirtle"},
            },
        },
        decision_out=decision_row,
    )

    assert strategy == "battle_jev_action"
    assert "select_move(3)" in description
    assert emitted == [("select_move", {"move_number": 3})]
    assert decision_row["phase"] == "BATTLE"
    assert decision_row["battle_action"] == "MOVE_3"
    assert decision_row["intent"] == "battle action MOVE_3"
    assert decision_row["raw_distribution"] == raw
    assert decision_row["jev_answered"] is True


def test_battle_recovery_has_no_select_move_one_signature() -> None:
    source = inspect.getsource(cron_runner._escalating_recovery)
    assert '{"move_number": 1}' not in source
