"""Regression tests for GAMEPLAY-ESCAPE-001 battle escape/recovery loops."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from cron_runner import _escalating_recovery
from src.core.global_context import GlobalContext
from src.core.ram_reader import (
    ADDR_CURRENT_MENU_ITEM,
    ADDR_IS_IN_BATTLE,
    ADDR_MAX_MENU_ITEM,
    ADDR_TOP_MENU_ITEM_X,
    ADDR_TOP_MENU_ITEM_Y,
)
from src.core.state_window import StateWindow
from src.core.tools import (
    MAX_FAILED_FLEE_ATTEMPTS,
    decide_battle_tool_call,
    execute_tool_call,
)


class BattleMenuStub:
    """Small Gen 1 battle-menu state machine backed by the real RAM addresses."""

    def __init__(
        self,
        *,
        battle_code: int = 1,
        mode: str = "main",
        escape_succeeds: bool = True,
    ) -> None:
        self.battle_code = battle_code
        self.mode = mode
        self.escape_succeeds = escape_succeeds
        self.cursor = [0, 0]
        self.pressed: list[str] = []
        self.waited: list[int] = []
        self.forwarded: list[int] = []
        self.load_state = MagicMock()

    def read_u8(self, address: int) -> int:
        if address == ADDR_IS_IN_BATTLE:
            return self.battle_code
        if self.mode == "main":
            if address == ADDR_TOP_MENU_ITEM_Y:
                return 14
            if address == ADDR_TOP_MENU_ITEM_X:
                return 9 if self.cursor[1] == 0 else 15
            if address == ADDR_CURRENT_MENU_ITEM:
                return self.cursor[0]
            if address == ADDR_MAX_MENU_ITEM:
                return 1
        if self.mode == "moves":
            if address == ADDR_TOP_MENU_ITEM_Y:
                return 12
            if address == ADDR_TOP_MENU_ITEM_X:
                return 5
            if address == ADDR_CURRENT_MENU_ITEM:
                return 0
            if address == ADDR_MAX_MENU_ITEM:
                return 3
        return 0

    def press_button(self, button: str, frames: int = 5) -> None:
        del frames
        self.pressed.append(button)
        if self.battle_code not in (1, 2):
            return

        if button == "b":
            if self.mode != "main":
                self.mode = "main"
                self.cursor = [0, 0]
            return

        if self.mode == "main":
            if button == "up":
                self.cursor[0] = 0
            elif button == "down":
                self.cursor[0] = 1
            elif button == "left":
                self.cursor[1] = 0
            elif button == "right":
                self.cursor[1] = 1
            elif button == "a":
                if self.cursor == [1, 1]:
                    if self.battle_code == 1 and self.escape_succeeds:
                        self.battle_code = 0
                        self.mode = "ended"
                    else:
                        self.mode = "text"
                elif self.cursor == [0, 0]:
                    self.mode = "moves"
            return

        if self.mode == "moves" and button == "a":
            self.mode = "text"

    def wait(self, frames: int) -> None:
        self.waited.append(frames)

    def fast_forward(self, frames: int) -> None:
        self.forwarded.append(frames)


@pytest.fixture
def wild_battle_vision() -> dict[str, object]:
    return {
        "screen_type": "battle",
        "result": "battle",
        "battle_state": {
            "battle_type": "wild",
            "player": {
                "name": "Squirtle",
                "level": 5,
                "hp_pct": 80,
                "hp": 16,
                "max_hp": 20,
                "type": "Water",
                "moves": [{"name": "Tackle", "pp": 35, "slot": 1}],
            },
            "enemy": {
                "name": "Rattata",
                "level": 3,
                "hp_pct": 100,
                "hp": 12,
                "max_hp": 12,
                "type": "Normal",
            },
        },
    }


class TestRunFromBattle:
    def test_wild_battle_at_fight_menu_clears_battle_flag(self) -> None:
        emu = BattleMenuStub(battle_code=1, mode="main")

        result = execute_tool_call(emu, "run_from_battle", {})

        assert result == "Escaped from wild battle."
        assert emu.battle_code == 0
        assert emu.pressed[-5:] == ["up", "left", "right", "down", "a"]

    def test_move_submenu_is_cancelled_and_reanchored_before_run(self) -> None:
        emu = BattleMenuStub(battle_code=1, mode="moves")

        result = execute_tool_call(emu, "run_from_battle", {})

        assert result == "Escaped from wild battle."
        assert emu.battle_code == 0
        assert "b" in emu.pressed
        assert emu.pressed[-5:] == ["up", "left", "right", "down", "a"]

    def test_trainer_battle_returns_error_without_tapping(self) -> None:
        emu = BattleMenuStub(battle_code=2, mode="main")

        result = execute_tool_call(emu, "run_from_battle", {})

        assert result.startswith("Error:")
        assert "trainer battle" in result
        assert emu.pressed == []
        assert emu.battle_code == 2

    def test_failed_wild_escape_reports_battle_still_active(self) -> None:
        emu = BattleMenuStub(
            battle_code=1,
            mode="main",
            escape_succeeds=False,
        )

        result = execute_tool_call(emu, "run_from_battle", {})

        assert "failed" in result.lower()
        assert emu.battle_code == 1


class TestFleeAttemptPolicy:
    def test_first_three_failed_attempts_allow_run(self) -> None:
        requested = {"name": "run_from_battle", "arguments": {}}

        for failures in range(MAX_FAILED_FLEE_ATTEMPTS):
            assert decide_battle_tool_call(requested, failures) == requested

    def test_after_three_failures_switches_to_move_one(self) -> None:
        requested = {"name": "run_from_battle", "arguments": {}}

        actual = decide_battle_tool_call(requested, MAX_FAILED_FLEE_ATTEMPTS)

        assert actual == {"name": "select_move", "arguments": {"move_number": 1}}

    def test_non_flee_action_is_never_rewritten(self) -> None:
        requested = {"name": "switch_pokemon", "arguments": {"slot": 2}}

        assert decide_battle_tool_call(requested, 99) == requested


class TestStateWindowBattleLoop:
    def test_successful_flee_stops_static_state_window_after_one_call(
        self,
        wild_battle_vision: dict[str, object],
    ) -> None:
        emu = BattleMenuStub(battle_code=1, mode="main")
        response = json.dumps({"name": "run_from_battle", "arguments": {}})
        with patch("src.core.state_window.OpenRouterClient") as client_cls:
            client = MagicMock()
            client.send_tool_request.return_value = response
            client_cls.return_value = client
            window = StateWindow(
                "battle",
                GlobalContext(),
                emu,
                wild_battle_vision,
                max_steps=12,
                use_ram_prompts=True,
            )

        result = window.run()

        assert result["outcome"] == "battle_ended"
        assert client.send_tool_request.call_count == 1
        assert [h["tool_call"]["name"] for h in window._history] == [
            "run_from_battle"
        ]

    def test_fourth_failed_flee_is_replaced_by_move(
        self,
        wild_battle_vision: dict[str, object],
    ) -> None:
        emu = BattleMenuStub(
            battle_code=1,
            mode="main",
            escape_succeeds=False,
        )
        response = json.dumps({"name": "run_from_battle", "arguments": {}})
        with patch("src.core.state_window.OpenRouterClient") as client_cls:
            client = MagicMock()
            client.send_tool_request.return_value = response
            client_cls.return_value = client
            window = StateWindow(
                "battle",
                GlobalContext(),
                emu,
                wild_battle_vision,
                max_steps=4,
                use_ram_prompts=True,
            )

        result = window.run()

        assert [h["tool_call"]["name"] for h in window._history] == [
            "run_from_battle",
            "run_from_battle",
            "run_from_battle",
            "select_move",
        ]
        assert result["_failed_flee_attempts"] == MAX_FAILED_FLEE_ATTEMPTS


class TestBattleAwareRecovery:
    @pytest.mark.parametrize("level", range(5))
    def test_every_recovery_level_uses_battle_action(self, level: int) -> None:
        emu = BattleMenuStub(battle_code=2, mode="main")
        game_state = {
            "result": "battle",
            "battle_state": {"battle_type": "trainer"},
        }

        strategy, description = _escalating_recovery(
            emu,
            recovery_level=level,
            last_direction="UP",
            last_saved_slot=3,
            game_state=game_state,
        )

        assert strategy == "battle_select_move"
        assert "select_move(1)" in description
        assert "start" not in emu.pressed
        assert emu.pressed.count("a") == 2
        emu.load_state.assert_not_called()
