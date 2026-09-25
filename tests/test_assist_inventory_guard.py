"""Regression tests for the deterministic assist inventory guard."""

from __future__ import annotations

import io
import json
import shutil
from pathlib import Path

from scripts.check_assist_inventory import run_guard


REPO_ROOT = Path(__file__).resolve().parents[1]
INVENTORY_PATH = REPO_ROOT / "config" / "assist_inventory.json"


def _copy_guard_inputs(tmp_path: Path) -> Path:
    """Copy only the production sources inspected by the guard."""
    root = tmp_path / "checkout"
    root.mkdir()
    shutil.copy2(REPO_ROOT / "cron_runner.py", root / "cron_runner.py")
    shutil.copytree(REPO_ROOT / "src", root / "src")
    inventory = root / "config" / "assist_inventory.json"
    inventory.parent.mkdir()
    shutil.copy2(INVENTORY_PATH, inventory)
    return root


def test_guard_passes_on_current_tree() -> None:
    output = io.StringIO()

    result = run_guard(REPO_ROOT, INVENTORY_PATH, output)

    assert result == 0
    assert "PASS: assist inventory matches" in output.getvalue()


def test_guard_fails_on_undeclared_press_button_site(tmp_path: Path) -> None:
    root = _copy_guard_inputs(tmp_path)
    cron_runner = root / "cron_runner.py"
    with cron_runner.open("a", encoding="utf-8") as stream:
        stream.write(
            '\n\ndef injected_assist(emu):\n    emu.press_button("select", frames=99)\n'
        )
    output = io.StringIO()

    result = run_guard(root, root / "config" / "assist_inventory.json", output)

    report = output.getvalue()
    assert result == 1
    assert "FAIL: assist inventory mismatch" in report
    assert "NEW" in report
    assert "injected_assist" in report
    assert "press_button('select', frames=99)" in report


def test_guard_fails_on_stale_declared_site(tmp_path: Path) -> None:
    root = _copy_guard_inputs(tmp_path)
    inventory_path = root / "config" / "assist_inventory.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    inventory["sites"].append(
        {
            "file": "cron_runner.py",
            "context": "removed_assist",
            "button": "select",
            "call": "press_button('select', frames=1)",
            "reason": "Regression fixture: this declaration has no source call.",
        }
    )
    inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
    output = io.StringIO()

    result = run_guard(root, inventory_path, output)

    report = output.getvalue()
    assert result == 1
    assert "FAIL: assist inventory mismatch" in report
    assert "STALE" in report
    assert "removed_assist" in report
