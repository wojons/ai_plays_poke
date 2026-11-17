"""Keep CI's static-analysis scope aligned with the commit guard."""

import os
from pathlib import Path
import shlex
import shutil
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

    completed = subprocess.run(  # noqa: S603 — repo-defined mypy command, test harness
        shlex.split(command),
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        shell=False,
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

    assert "    container: ghcr.io/snooptheone/act-ubuntu-custom:latest" in workflow
    assert "        shell: bash" in workflow


def test_src_package_initializers_exist() -> None:
    """src/ and src/vision/ must have tracked __init__.py files."""
    src_init = REPO_ROOT / "src" / "__init__.py"
    vision_init = REPO_ROOT / "src" / "vision" / "__init__.py"

    assert src_init.is_file(), f"missing package initializer: {src_init}"
    assert vision_init.is_file(), f"missing package initializer: {vision_init}"


def test_vision_initializer_exports_five_symbols() -> None:
    """src/vision/__init__.py must export the five vision symbols used by ai_client."""
    vision_init = REPO_ROOT / "src" / "vision" / "__init__.py"
    content = vision_init.read_text(encoding="utf-8")

    expected = {
        "VisionPipeline",
        "OCREngine",
        "SpriteRecognizer",
        "BattleAnalyzer",
        "LocationDetector",
    }
    for symbol in expected:
        assert symbol in content, f"vision initializer missing export: {symbol}"


def _load_ruff_config() -> dict:
    """The [tool.ruff] table from pyproject.toml."""
    toml_text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    try:
        import tomllib
    except ImportError:  # Python < 3.11
        import tomli as tomllib  # type: ignore[no-redef]
    return tomllib.loads(toml_text)["tool"]["ruff"]


def _ruff_executable() -> str | None:
    """Resolve ruff the way CI does: next to the running interpreter, then PATH."""
    lookup_path = (
        f"{Path(sys.executable).parent}{os.pathsep}{os.environ.get('PATH', '')}"
    )
    return shutil.which("ruff", path=lookup_path)


def test_ruff_does_not_honour_gitignore() -> None:
    """QA-AI-PLAYS-POKE-029: ruff must enumerate the index, not .gitignore.

    ruff applies .gitignore during file discovery and does NOT exempt paths git
    already tracks, so `.gitignore` line 152 `_*.py` hid 9 tracked files (every
    package `__init__.py` plus src/ptp_cli/__main__.py) and the explicit
    `web_viewer.py` entry hid a 10th. `ruff check src/ tests/` therefore read 192 of
    the 201 tracked files under those roots and still printed "All checks passed!".
    `respect-gitignore = false` is what closes the hole; the coverage test below
    proves the effect on the real file set.
    """
    assert _load_ruff_config().get("respect-gitignore") is False, (
        "[tool.ruff] must keep `respect-gitignore = false`: with ruff's default "
        "(true) every tracked file matched by .gitignore is silently skipped, so "
        "the lint gate can pass without ever reading it"
    )


@pytest.mark.timeout(60)
def test_ruff_lints_every_tracked_python_file() -> None:
    """Every `git ls-files '*.py'` path must appear in `ruff check --show-files .`."""
    ruff = _ruff_executable()
    if ruff is None:
        pytest.skip("ruff not installed (the dev extra pins ruff==0.15.22)")
    git = shutil.which("git")
    if git is None:
        pytest.skip("git not available to enumerate tracked files")

    tracked = subprocess.run(  # noqa: S603 — repo tooling invoked without a shell
        [git, "ls-files", "*.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert tracked.returncode == 0, f"git ls-files failed: {tracked.stderr}"
    tracked_files = {
        line.strip() for line in tracked.stdout.splitlines() if line.strip()
    }
    assert tracked_files, "git ls-files '*.py' returned no files"

    shown = subprocess.run(  # noqa: S603 — repo tooling invoked without a shell
        [ruff, "check", "--show-files", "."],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert shown.returncode == 0, f"ruff check --show-files failed: {shown.stderr}"

    linted: set[str] = set()
    for line in shown.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            linted.add(Path(line).resolve().relative_to(REPO_ROOT).as_posix())
        except ValueError:  # reported outside the repo root; keep it verbatim
            linted.add(line)

    skipped = sorted(tracked_files - linted)
    assert not skipped, (
        "ruff does not lint these tracked files - they are in the git index but "
        "invisible to `ruff check src/ tests/`: " + ", ".join(skipped)
    )
    # The exact files .gitignore used to hide must be reported by name.
    for hidden in ("src/__init__.py", "src/ptp_cli/__main__.py", "web_viewer.py"):
        assert hidden in linted, f"{hidden} is tracked but ruff does not lint it"


def test_ensure_package_inits_script_runs_successfully() -> None:
    """The CI guard script must exit 0 when initializers are already present."""
    script = REPO_ROOT / "scripts" / "ensure_package_inits.py"
    assert script.is_file()

    completed = subprocess.run(  # noqa: S603 — repo-defined guard script
        [sys.executable, str(script)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, (
        f"ensure_package_inits.py failed with exit {completed.returncode}: "
        f"{completed.stdout}\n{completed.stderr}"
    )
    assert "Package initializers present." in completed.stdout
