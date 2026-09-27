"""BOOT-1 regression tests: long_run's default boot state and stamped arm.

The driver's default boot must be the MEASURED baseline (Pallet Town, map 0 —
the state CTRL-WIN/DIST-1/BASE-1 numbers came from), not data/boot.state
(Oak's Lab, map 40). The decision-mode arm must be stamped explicitly into the
cron_runner argv, not left to an ambient env var inside the child.
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).parent.parent))

import long_run  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """No ambient boot/mode env leaks into resolution assertions."""
    monkeypatch.delenv("LONG_RUN_BOOT_STATE", raising=False)
    monkeypatch.delenv("AIPP_DECISION_MODE", raising=False)
    monkeypatch.delenv("CRON_DECISION_MODE", raising=False)


# ── (a) default boot path + the measured Pallet Town baseline ───────────────


def test_default_boot_path_is_base1_baseline():
    assert long_run.BOOT.name == "base-1_boot.state"
    assert str(long_run.BOOT).endswith(
        os.path.join("data", "baselines", "base-1_boot.state")
    )


def test_default_boot_resolves_to_pallet_town_map_0():
    # The state file itself IS the measured baseline — its md5 is asserted
    # below; the full emulator probe is the ROM-gated integration test.
    import hashlib

    assert (
        hashlib.md5(long_run.BOOT.read_bytes()).hexdigest()
        == "81e4ec4e8d1b62002bc78f619c5fc79c"
    )


@pytest.mark.integration
@pytest.mark.skipif(
    not Path(long_run.ROM).exists(), reason="ROM is a user-supplied file"
)
def test_default_boot_probes_pallet_town_map_0_live():
    """Full emulator probe — needs the ROM; skipped on ROM-less worktrees."""
    verdict = long_run.probe_state(long_run.BOOT)
    assert verdict["ok"], verdict
    assert verdict["map_id"] == 0
    assert verdict["map_name"] == "Pallet Town"


def test_resolve_boot_state_default(monkeypatch):
    assert long_run.resolve_boot_state() == long_run.BOOT


def test_resolve_boot_state_env_override_beats_default(monkeypatch, tmp_path):
    override = tmp_path / "custom.state"
    override.write_bytes(b"x")
    monkeypatch.setenv("LONG_RUN_BOOT_STATE", str(override))
    assert long_run.resolve_boot_state() == override


def test_resolve_boot_state_empty_env_falls_back(monkeypatch):
    monkeypatch.setenv("LONG_RUN_BOOT_STATE", "")
    assert long_run.resolve_boot_state() == long_run.BOOT


# ── (b) decision-mode resolution mirrors cron_runner precedence ─────────────


def test_mode_default_jev():
    assert long_run.resolve_decision_mode() == "jev"


def test_mode_aipp_beats_cron_env(monkeypatch):
    monkeypatch.setenv("AIPP_DECISION_MODE", "llm")
    monkeypatch.setenv("CRON_DECISION_MODE", "jev")
    assert long_run.resolve_decision_mode() == "llm"


def test_mode_cron_env_used_when_no_aipp(monkeypatch):
    monkeypatch.setenv("CRON_DECISION_MODE", "system1")
    assert long_run.resolve_decision_mode() == "system1"


def test_mode_is_normalised_like_cron_runner(monkeypatch):
    monkeypatch.setenv("AIPP_DECISION_MODE", "  LLM  ")
    assert long_run.resolve_decision_mode() == "llm"


def test_mode_module_constant_matches_resolution(monkeypatch):
    import importlib

    monkeypatch.setenv("AIPP_DECISION_MODE", "llm")
    reloaded = importlib.reload(long_run)
    assert reloaded.DECISION_MODE == "llm"
    monkeypatch.delenv("AIPP_DECISION_MODE", raising=False)
    importlib.reload(long_run)
    assert long_run.DECISION_MODE == "jev"


# ── (c) composed cron_runner argv carries the explicit arm ──────────────────


def test_episode_argv_stamps_decision_mode():
    argv = long_run.episode_argv("run_x_ep001", "/tmp/boot.state", "llm")
    assert "cron_runner.py" in argv
    assert ["--boot-state", "/tmp/boot.state"] == argv[
        argv.index("--boot-state") : argv.index("--boot-state") + 2
    ]
    i = argv.index("--decision-mode")
    assert argv[i + 1] == "llm"


def test_episode_argv_stamps_env_resolved_mode(monkeypatch):
    monkeypatch.setenv("AIPP_DECISION_MODE", "llm")
    mode = long_run.resolve_decision_mode()
    argv = long_run.episode_argv("run_x_ep001", str(long_run.BOOT), mode)
    assert argv[argv.index("--decision-mode") + 1] == "llm"


def test_episode_argv_default_mode_is_jev():
    argv = long_run.episode_argv("run_x_ep001", str(long_run.BOOT), "jev")
    assert argv[argv.index("--decision-mode") + 1] == "jev"
