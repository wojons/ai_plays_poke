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


def test_long_run_doc_states_the_refusal_not_a_default() -> None:
    """docs/api/long_run.md must mirror scripts/long_run.py's exit-2 refusal."""
    text = _read(BASE / "docs" / "api" / "long_run.md")
    assert "refuses (exit 2)" in text, (
        "docs/api/long_run.md must state that the driver refuses without a mode"
    )


def test_long_run_refuses_without_a_mode(monkeypatch, capsys) -> None:
    """Behavioural pin for the claim above: no env, no flag -> exit 2."""
    import sys

    monkeypatch.syspath_prepend(str(BASE / "scripts"))
    for name in ("AIPP_DECISION_MODE", "CRON_DECISION_MODE"):
        monkeypatch.delenv(name, raising=False)
    import long_run

    import pytest

    with pytest.raises(SystemExit) as exc:
        long_run.resolve_decision_mode()
    assert exc.value.code == 2
    err = capsys.readouterr()
    assert "AIPP_DECISION_MODE" in (err.out + err.err)
    assert sys  # keep the import meaningful for readers


HISTORICAL_REPORTS = [
    "docs/dogfood/2026-10-27-integration.md",
    "docs/dogfood/diagnostics.md",
    "docs/dogfood/2026-08-26-integration.md",
    "docs/dogfood/2026-09-24-integration.md",
    "docs/dependency_review_20261010.md",
    "docs/dependency_review_20261013.md",
]


def test_historical_reports_are_annotated() -> None:
    """Dated reports keep their original commands, but must carry the caveat."""
    for rel in HISTORICAL_REPORTS:
        text = _read(BASE / rel)
        assert "Annotation (2026-11-21, DOC-029)" in text, (
            f"{rel} shows mode-less commands without the DOC-029 annotation"
        )
