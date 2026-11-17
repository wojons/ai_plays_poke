"""ARM-2-R1: long_run must never pick a decision mode in silence.

ARM-2 made the decision-mode arm (jev | llm | hybrid | ...) selectable and its
acceptance criterion 4 forbade a hardcoded DEFAULT_DECISION_MODE fallback arm.
scripts/long_run.py still had one: `resolve_decision_mode()` returned "jev"
whenever neither AIPP_DECISION_MODE nor CRON_DECISION_MODE was set, so a
scheduled long run that forgot the variable silently ran the arm that measured
0/5 at leaving Pallet Town — and an unrecognised spelling was forwarded to
cron_runner, which degrades it on the far side of the subprocess boundary.

The contract under test:

* neither variable set, no flag  -> refuse (SystemExit, message names both)
* --allow-default-mode           -> "jev" + a loud warning naming the arm
* AIPP_DECISION_MODE=hybrid      -> "hybrid" and the child argv says so
* unrecognised spelling          -> refuse, message lists the accepted set
* the accepted set is cron_runner's, exactly (no private spelling drift)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO))

import cron_runner  # noqa: E402
import long_run  # noqa: E402

LONG_RUN = str(REPO / "scripts" / "long_run.py")
MODE_VARS = ("AIPP_DECISION_MODE", "CRON_DECISION_MODE")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """No ambient mode env leaks into resolution assertions."""
    for name in MODE_VARS:
        monkeypatch.delenv(name, raising=False)


def _cli(*args: str, **env_overrides: str) -> subprocess.CompletedProcess[str]:
    """Run the real driver with a mode-free env; never launches the game."""
    env = {k: v for k, v in os.environ.items() if k not in MODE_VARS}
    env.update(env_overrides)
    return subprocess.run(
        [sys.executable, LONG_RUN, *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO),
        timeout=180,
    )


# ── the accepted set is cron_runner's, not a private invention ──────────────


def test_accepted_set_mirrors_cron_runner_exactly():
    assert set(long_run.DECISION_MODES) == set(cron_runner.DECISION_MODES)
    assert tuple(long_run.DECISION_MODE_ENV_VARS) == tuple(
        cron_runner.DECISION_MODE_ENV_VARS
    )


# ── (a) no env, no flag: refuse, naming the variables ──────────────────────


def test_missing_mode_refuses_and_names_both_variables(capsys):
    with pytest.raises(SystemExit) as exc:
        long_run.resolve_decision_mode()
    assert exc.value.code != 0
    err = capsys.readouterr().err
    assert "AIPP_DECISION_MODE" in err
    assert "CRON_DECISION_MODE" in err
    assert "--allow-default-mode" in err


def test_blank_mode_env_counts_as_unset(monkeypatch):
    monkeypatch.setenv("AIPP_DECISION_MODE", "   ")
    monkeypatch.setenv("CRON_DECISION_MODE", "")
    with pytest.raises(SystemExit):
        long_run.resolve_decision_mode()


# ── (b) --allow-default-mode is the only path to the legacy arm ────────────


def test_allow_default_mode_returns_jev_and_warns_loudly(capsys):
    assert long_run.resolve_decision_mode(allow_default=True) == "jev"
    err = capsys.readouterr().err
    assert "[WARNING]" in err
    assert "jev" in err


def test_allow_default_mode_does_not_override_a_set_mode(monkeypatch):
    monkeypatch.setenv("AIPP_DECISION_MODE", "hybrid")
    assert long_run.resolve_decision_mode(allow_default=True) == "hybrid"


# ── (c) a named mode is honoured end to end, into the child argv ───────────


@pytest.mark.parametrize("mode", ["jev", "llm", "hybrid"])
def test_named_modes_are_honoured(monkeypatch, mode):
    monkeypatch.setenv("AIPP_DECISION_MODE", mode)
    assert long_run.resolve_decision_mode() == mode


def test_hybrid_reaches_the_child_argv(monkeypatch):
    monkeypatch.setenv("AIPP_DECISION_MODE", "hybrid")
    mode = long_run.resolve_decision_mode()
    argv = long_run.episode_argv("run_arm2r1_ep001", str(long_run.BOOT), mode)
    assert argv[argv.index("--decision-mode") + 1] == "hybrid"


def test_cron_env_is_used_when_aipp_is_unset(monkeypatch):
    monkeypatch.setenv("CRON_DECISION_MODE", "hybrid")
    assert long_run.resolve_decision_mode() == "hybrid"


# ── (d) an unrecognised spelling is rejected, not forwarded ────────────────


def test_unrecognised_spelling_refuses_and_lists_accepted_values(monkeypatch, capsys):
    monkeypatch.setenv("AIPP_DECISION_MODE", "hybrid-v2")
    with pytest.raises(SystemExit) as exc:
        long_run.resolve_decision_mode()
    assert exc.value.code != 0
    err = capsys.readouterr().err
    assert "hybrid-v2" in err
    for mode in long_run.DECISION_MODES:
        assert mode in err


def test_unrecognised_cron_spelling_refuses_too(monkeypatch):
    monkeypatch.setenv("CRON_DECISION_MODE", "LLM+jev")
    with pytest.raises(SystemExit):
        long_run.resolve_decision_mode()


# ── the same contract, through the real CLI (no game launched) ─────────────


def test_cli_help_works_without_a_mode():
    proc = _cli("--help")
    assert proc.returncode == 0, proc.stderr
    assert "--allow-default-mode" in proc.stdout
    assert "AIPP_DECISION_MODE" in proc.stdout


def test_cli_run_path_refuses_without_a_mode():
    # --dry-run stops before any game/episode work, but it goes through the
    # real argparse -> resolve_decision_mode path that a scheduled run takes.
    proc = _cli("--dry-run")
    assert proc.returncode != 0
    assert "AIPP_DECISION_MODE" in proc.stderr
    assert "CRON_DECISION_MODE" in proc.stderr


def test_cli_dry_run_materialises_hybrid_argv():
    proc = _cli("--dry-run", AIPP_DECISION_MODE="hybrid")
    assert proc.returncode == 0, proc.stderr
    plan = json.loads(proc.stdout)
    assert plan["decision_mode"] == "hybrid"
    argv = plan["episode_argv"]
    assert argv[argv.index("--decision-mode") + 1] == "hybrid"
    assert "cron_runner.py" in argv


def test_cli_dry_run_rejects_unrecognised_mode():
    proc = _cli("--dry-run", AIPP_DECISION_MODE="bogus")
    assert proc.returncode != 0
    assert "bogus" in proc.stderr
    for mode in long_run.DECISION_MODES:
        assert mode in proc.stderr


def test_cli_dry_run_allow_default_mode_warns_and_uses_jev():
    proc = _cli("--dry-run", "--allow-default-mode")
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["decision_mode"] == "jev"
    assert "[WARNING]" in proc.stderr
