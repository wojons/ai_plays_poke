"""Purity gates for the pure-LLM benchmark (BENCH-1): system2 never asks JEV.

Load-bearing contract: in ``llm``/``system2`` mode the fast tier is NEVER
consulted — not on the overworld path (already enforced by ``_jev_or_none``),
and not on the two remaining direct ``jev_client.decide`` call sites, battle
recovery and starter selection. A leak there stamps ``jev_answered=True`` into
a benchmark-labelled run and silently measures a contaminated arm.

Controls prove the same sites still consult JEV in ``jev`` (hybrid) mode —
the fix must gate the mode, not delete the tier.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import cron_runner


@pytest.fixture(autouse=True)
def _restore_mode():
    """Every test leaves the module-level mode exactly as it found it."""
    original = cron_runner.DECISION_MODE
    yield
    cron_runner.DECISION_MODE = original


def _battle_state() -> dict:
    """A game state ``_is_battle_game_state`` recognises as an active battle."""
    return {
        "screen_type": "battle",
        "battle_state": {
            "enemy": {"hp": 10, "max_hp": 20},
            "party": [{"moves": ["TACKLE"], "pp": [35]}],
        },
    }


def test_llm_mode_battle_recovery_never_calls_jev(monkeypatch):
    """BENCH-1 gate: battle recovery must not consult the fast tier in llm mode."""

    def _spy(*args, **kwargs):
        raise AssertionError("jev_client.decide was called in pure-LLM mode")

    monkeypatch.setattr(cron_runner.jev_client, "decide", _spy)
    cron_runner.DECISION_MODE = "llm"

    decision_out: dict = {}
    strategy, _desc = cron_runner._escalating_recovery(
        MagicMock(),
        0,
        "UP",
        None,
        game_state=_battle_state(),
        decision_out=decision_out,
    )
    assert decision_out.get("jev_answered") is False
    assert decision_out.get("jev_blocked_reason"), (
        "a blocked fast-tier ask must carry a reason, not a bare null"
    )
    # The turn still resolves: the RAM fallback decides it (fail-closed, not a hang).
    assert strategy


def test_jev_mode_battle_recovery_still_consults_jev(monkeypatch):
    """Control: hybrid mode keeps the existing battle JEV ask (M6 back-compat)."""
    sentinel = {"ok": True, "next_action": "MOVE_1", "raw": {"MOVE_1": 0.9}}
    seen: list[tuple] = []

    def _spy(*args, **kwargs):
        seen.append((args, kwargs))
        return dict(sentinel)

    monkeypatch.setattr(cron_runner.jev_client, "decide", _spy)
    monkeypatch.setattr(
        cron_runner, "execute_tool_call", lambda *a, **k: "pressed move 1"
    )
    cron_runner.DECISION_MODE = "jev"

    decision_out: dict = {}
    cron_runner._escalating_recovery(
        MagicMock(),
        0,
        "UP",
        None,
        game_state=_battle_state(),
        decision_out=decision_out,
    )
    assert seen, "hybrid mode must still consult JEV for battles"
    assert decision_out.get("jev_answered") is True
    assert decision_out.get("jev_blocked_reason") is None


def test_llm_mode_starter_selection_never_calls_jev(monkeypatch):
    """BENCH-1 gate: starter selection must not consult the fast tier in llm mode."""

    def _spy(*args, **kwargs):
        raise AssertionError("jev_client.decide was called in pure-LLM mode")

    monkeypatch.setattr(cron_runner.jev_client, "decide", _spy)
    cron_runner.DECISION_MODE = "llm"

    ram_reader = MagicMock()
    ram_reader.party_count.return_value = 0
    ram_reader.read_dialog_text.return_value = "CHARMANDER"
    ram_reader.screen_type.return_value = "overworld"

    decision_out: dict = {}
    cron_runner._select_starter_from_menu(
        MagicMock(), ram_reader, decision_out=decision_out
    )
    assert decision_out.get("jev_answered") is False
    assert decision_out.get("jev_blocked_reason"), (
        "a blocked fast-tier ask must carry a reason, not a bare null"
    )


def test_jev_mode_starter_selection_still_consults_jev(monkeypatch):
    """Control: hybrid mode keeps the existing starter JEV ask."""
    sentinel = {"ok": True, "next_action": "CHARMANDER", "raw": {"CHARMANDER": 0.9}}
    seen: list[tuple] = []

    def _spy(*args, **kwargs):
        seen.append((args, kwargs))
        return dict(sentinel)

    monkeypatch.setattr(cron_runner.jev_client, "decide", _spy)
    cron_runner.DECISION_MODE = "jev"

    ram_reader = MagicMock()
    ram_reader.party_count.return_value = 0
    ram_reader.read_dialog_text.return_value = "CHARMANDER"
    ram_reader.screen_type.return_value = "overworld"

    decision_out: dict = {}
    cron_runner._select_starter_from_menu(
        MagicMock(), ram_reader, decision_out=decision_out
    )
    assert seen, "hybrid mode must still consult JEV for the starter choice"
    assert decision_out.get("jev_answered") is True
    assert decision_out.get("jev_blocked_reason") is None


def test_purity_predicate_matches_mode_family():
    """One predicate gates every direct fast-tier call site."""
    cron_runner.DECISION_MODE = "llm"
    assert cron_runner._llm_mode_fast_tier_blocked() is True
    cron_runner.DECISION_MODE = "system2"
    assert cron_runner._llm_mode_fast_tier_blocked() is True
    cron_runner.DECISION_MODE = "jev"
    assert cron_runner._llm_mode_fast_tier_blocked() is False
    cron_runner.DECISION_MODE = "system1"
    assert cron_runner._llm_mode_fast_tier_blocked() is False
    cron_runner.DECISION_MODE = "system1+system2"
    assert cron_runner._llm_mode_fast_tier_blocked() is False
