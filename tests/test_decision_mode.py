"""Decision-mode switch: the pure-LLM benchmark must be real, not just a flag.

The load-bearing test is `test_llm_mode_never_calls_jev`: in "llm" mode the
fast tier must not be *invoked at all* (no budget, no latency, no influence),
not merely have its answer discarded. A regression there would silently
contaminate the LLM-core benchmark the project exists to measure.
"""

from __future__ import annotations

import pytest

import cron_runner


@pytest.fixture(autouse=True)
def _restore_mode():
    """Every test leaves the module-level mode exactly as it found it."""
    original = cron_runner.DECISION_MODE
    yield
    cron_runner.DECISION_MODE = original


# --------------------------------------------------------------- resolution
def test_default_mode_is_jev(monkeypatch):
    monkeypatch.delenv("AIPP_DECISION_MODE", raising=False)
    monkeypatch.delenv("CRON_DECISION_MODE", raising=False)
    assert cron_runner.resolve_decision_mode() == "jev"
    assert cron_runner.DEFAULT_DECISION_MODE == "jev"


def test_flag_selects_llm():
    assert cron_runner.resolve_decision_mode("llm") == "llm"


def test_flag_is_case_and_space_tolerant():
    assert cron_runner.resolve_decision_mode("  LLM  ") == "llm"


def test_env_selects_llm_when_no_flag(monkeypatch):
    monkeypatch.setenv("AIPP_DECISION_MODE", "llm")
    assert cron_runner.resolve_decision_mode() == "llm"


def test_flag_beats_env(monkeypatch):
    monkeypatch.setenv("AIPP_DECISION_MODE", "llm")
    assert cron_runner.resolve_decision_mode("jev") == "jev"


def test_garbage_falls_back_to_default(monkeypatch):
    monkeypatch.delenv("AIPP_DECISION_MODE", raising=False)
    monkeypatch.delenv("CRON_DECISION_MODE", raising=False)
    assert cron_runner.resolve_decision_mode("nonsense") == "jev"


def test_invalid_env_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("AIPP_DECISION_MODE", "totally-bogus")
    assert cron_runner.resolve_decision_mode() == "jev"


def test_secondary_env_var_works(monkeypatch):
    monkeypatch.delenv("AIPP_DECISION_MODE", raising=False)
    monkeypatch.setenv("CRON_DECISION_MODE", "llm")
    assert cron_runner.resolve_decision_mode() == "llm"


# ------------------------------------------------------- the load-bearing one
def test_llm_mode_never_calls_jev(monkeypatch):
    """In llm mode the fast tier is never invoked — not called and ignored."""
    calls: list[tuple] = []

    def _spy(*args, **kwargs):
        calls.append((args, kwargs))
        return {"intent": "jev should not have run", "plan": ["A"]}

    monkeypatch.setattr(cron_runner, "_jev_overworld_decision", _spy)
    cron_runner.DECISION_MODE = "llm"

    assert cron_runner._jev_or_none("state", goal="g") is None
    assert calls == [], "JEV was invoked during a pure-LLM benchmark run"


def test_jev_mode_passes_through(monkeypatch):
    sentinel = {"intent": "jev A", "plan": ["A"]}
    seen: list[tuple] = []

    def _spy(*args, **kwargs):
        seen.append((args, kwargs))
        return sentinel

    monkeypatch.setattr(cron_runner, "_jev_overworld_decision", _spy)
    cron_runner.DECISION_MODE = "jev"

    assert cron_runner._jev_or_none("state", goal="g") is sentinel
    assert seen, "JEV was not consulted in jev mode"


def test_jev_mode_result_is_not_mutated(monkeypatch):
    """Pass-through must not copy or alter the decision dict."""
    sentinel = {"intent": "jev LEFT", "plan": ["LEFT"], "escalated": True}
    monkeypatch.setattr(
        cron_runner, "_jev_overworld_decision", lambda *a, **k: sentinel
    )
    cron_runner.DECISION_MODE = "jev"
    out = cron_runner._jev_or_none()
    assert out is sentinel
    assert out == {"intent": "jev LEFT", "plan": ["LEFT"], "escalated": True}


# ------------------------------------------------------------------- parser
def test_parser_accepts_both_modes():
    parser = cron_runner._main_parser()
    assert parser.parse_args(["--decision-mode", "llm"]).decision_mode == "llm"
    assert parser.parse_args(["--decision-mode", "jev"]).decision_mode == "jev"


def test_parser_default_is_none_so_env_applies():
    """The flag defaults to None so env resolution can still win."""
    parser = cron_runner._main_parser()
    assert parser.parse_args([]).decision_mode is None


def test_parser_rejects_unknown_mode():
    parser = cron_runner._main_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--decision-mode", "nonsense"])
    # NOTE: this test previously used "hybrid" as its unknown value. "hybrid"
    # became a VALID alias when the System-One/System-Two modes were added
    # (SPEC_decision_modes.md), so the fixture had to move to a value that is
    # still genuinely unknown. The assertion is unchanged.


def test_parser_accepts_the_new_mode_names():
    parser = cron_runner._main_parser()
    for name in ("system1", "system2", "system1+system2", "hybrid"):
        assert parser.parse_args(["--decision-mode", name]).decision_mode == name


def test_modes_constant_keeps_the_historical_names():
    """The mode set grew ADDITIVELY: the two historical spellings must still be
    accepted, because every committed baseline and run log cites them."""
    modes = set(cron_runner.DECISION_MODES)
    assert {"jev", "llm"} <= modes, "a historical mode spelling was dropped"
    assert {"system1", "system2", "system1+system2"} <= modes
    # And each historical spelling still means what it always meant.
    assert cron_runner.decision_mode_family("jev") == cron_runner.MODE_HYBRID
    assert cron_runner.decision_mode_family("llm") == cron_runner.MODE_SYSTEM2
