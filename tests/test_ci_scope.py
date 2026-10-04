"""Keep CI's static-analysis scope aligned with the commit guard."""

import os
from pathlib import Path
import shlex
import subprocess
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"


def _ci_mypy_command() -> str:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    _, type_check_and_rest = workflow.split(
        "      - name: Type check (mypy)\n", maxsplit=1
    )
    type_check_block = type_check_and_rest.split("\n      - name:", maxsplit=1)[0]
    run_prefix = "        run: "
    run_commands = [
        line.removeprefix(run_prefix)
        for line in type_check_block.splitlines()
        if line.startswith(run_prefix)
    ]

    assert len(run_commands) == 1
    return run_commands[0]


@pytest.mark.timeout(120)
def test_ci_mypy_covers_runtime_scripts_without_duplicate_modules() -> None:
    """Run CI's exact mypy command against both repository source roots."""
    command = _ci_mypy_command()
    environment = os.environ.copy()
    environment["PATH"] = (
        f"{Path(sys.executable).parent}{os.pathsep}{environment.get('PATH', '')}"
    )

    completed = subprocess.run(
        shlex.split(command),
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, (
        f"CI mypy command failed with exit {completed.returncode}: {command}\n"
        f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
    )
    assert shlex.split(command) == [
        "mypy",
        "--explicit-package-bases",
        "src/",
        "scripts/",
        "--ignore-missing-imports",
    ]


def test_ci_uses_a_glibc_compatible_act_container() -> None:
    """The act image must load the interpreter installed by setup-python."""
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    assert "    container: catthehacker/ubuntu:act-latest" in workflow
    assert "        shell: bash" in workflow
