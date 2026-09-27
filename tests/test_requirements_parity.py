"""Parity test: requirements files must not drift from pyproject.toml.

Regression for REVIEW-2: pytest-benchmark/pytest-timeout were declared in
pyproject [project.optional-dependencies].dev but missing from
requirements-dev.txt, so `pip install -r requirements-dev.txt` yielded
'fixture benchmark not found' errors in tests/test_performance.py.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _parse_requirements(path: Path) -> set[str]:
    names = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        # Strip environment markers (e.g. "; python_version < '3.10'")
        req = line.split(";", 1)[0].strip()
        # Keep only the distribution name (drop version specifiers / extras)
        name = re.split(r"[<>=!~\[ ;]", req, 1)[0].strip()
        if name:
            names.add(name.lower())
    return names


def _dev_extras_from_pyproject() -> set[str]:
    toml_text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    try:
        import tomllib
    except ImportError:  # Python < 3.11
        import tomli as tomllib  # type: ignore[no-redef]
    data = tomllib.loads(toml_text)
    deps = data["project"]["optional-dependencies"]["dev"]
    names = set()
    for req in deps:
        name = re.split(r"[<>=!~\[ ;]", req, 1)[0].strip()
        if name:
            names.add(name.lower())
    return names


def test_dev_requirements_cover_pyproject_dev_extras():
    dev_extras = _dev_extras_from_pyproject()
    assert dev_extras, "pyproject dev extras must not be empty"
    req_dev = _parse_requirements(REPO_ROOT / "requirements-dev.txt")
    missing = dev_extras - req_dev
    assert not missing, (
        "packages declared in pyproject [project.optional-dependencies].dev "
        f"but missing from requirements-dev.txt: {sorted(missing)}"
    )


def test_requirements_files_exist():
    assert (REPO_ROOT / "requirements.txt").is_file()
    assert (REPO_ROOT / "requirements-dev.txt").is_file()


@pytest.mark.parametrize("package", ["pytest-benchmark", "pytest-timeout"])
def test_benchmark_tooling_present_in_dev_requirements(package: str):
    req_dev = _parse_requirements(REPO_ROOT / "requirements-dev.txt")
    assert package in req_dev
