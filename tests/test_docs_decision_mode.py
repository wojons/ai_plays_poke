"""Docs must not advertise an implicit decision-mode default (DOC-029).

`cron_runner.py` has no implicit default: ``_main_parse_and_dry_run()`` exits 2
when neither ``--decision-mode`` nor ``AIPP_DECISION_MODE`` /
``CRON_DECISION_MODE`` names a mode (see ``tests/test_decision_mode.py::
test_missing_mode_refuses_to_start_with_choices``).  The prose docs drifted once
(README promised a "jev default" while the Quick Start command omitted the flag
and died rc=2).  These assertions pin the corrected surfaces so the claim cannot
rot back in silently.
"""

from __future__ import annotations

import re
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
README = BASE / "README.md"
ARCH = BASE / "docs" / "architecture.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_readme_quick_start_passes_a_decision_mode() -> None:
    """The copy-paste Quick Start command must name a mode, else rc=2."""
    text = _read(README)
    commands = [
        ln.strip()
        for ln in text.splitlines()
        if re.match(r"^\s*(?:[A-Za-z0-9_./-]*python3?)\s+cron_runner\.py", ln)
    ]
    assert commands, "README must show a runnable `python3 cron_runner.py ...` command"
    for cmd in commands:
        assert "--decision-mode" in cmd, (
            f"Quick Start command omits --decision-mode: {cmd!r}"
        )


def test_readme_does_not_promise_a_decision_mode_default() -> None:
    """No README line may claim a jev/system1+system2 decision-mode default."""
    text = _read(README)
    bad = [
        ln
        for ln in text.splitlines()
        if re.search(r"\b(jev|system1\+system2)\b[^.|]{0,40}\bdefault\b", ln, re.I)
        or re.search(r"\bdefault\b[^.|]{0,20}\bjev\b", ln, re.I)
    ]
    assert not bad, (
        "README advertises a decision-mode default that does not exist: " + repr(bad)
    )


def test_architecture_does_not_claim_cron_runner_defaults_to_jev() -> None:
    text = _read(ARCH)
    assert not re.search(r"defaults to JEV", text, re.I), (
        "docs/architecture.md still claims cron_runner.py defaults to JEV"
    )
