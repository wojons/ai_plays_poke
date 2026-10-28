"""Parity test: requirements files must not drift from pyproject.toml.

Regression for REVIEW-2: pytest-benchmark/pytest-timeout were declared in
pyproject [project.optional-dependencies].dev but missing from
requirements-dev.txt, so `pip install -r requirements-dev.txt` yielded
'fixture benchmark not found' errors in tests/test_performance.py.

Regression for INT-CI-2: the CI workflow installed pytest BARE while the dev
requirements bound it, so CI resolved pytest 9.2.0 and every benchmark test
died in fixture setup with "AttributeError: 'Function' object has no attribute
'_nodeid'" (pytest-benchmark 5.3.0 reads the private Function._nodeid, which
pytest 9.2 removed). The pins below must agree and must exclude 9.2+.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"

# pytest 9.2.0 removed the private Function._nodeid attribute that
# pytest-benchmark 5.3.0 (the latest release) reads in BenchmarkFixture.__init__.
# Any environment resolving pytest >= this breaks every benchmark test.
BENCHMARK_BREAKING_PYTEST = (9, 2)


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


def _requirement_spec(text: str, name: str) -> str | None:
    """Version specifier for ``name`` in a requirements file, e.g. '>=8.1,<9.2'."""
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        m = re.match(rf"{re.escape(name)}\s*([<>=!~].*)$", line)
        if m:
            return m.group(1).strip()
    return None


def _ci_pytest_install_spec(ci_text: str) -> str | None:
    """The pytest version spec CI installs with, or None when installed bare."""
    for line in ci_text.splitlines():
        if "pip install" not in line:
            continue
        m = re.search(r'"pytest([<>=!~][^"]*)"', line)
        if m:
            return m.group(1)
        if re.search(r"(?:^|\s)pytest(?=\s|$)", line):
            return None
    return None


def _upper_bound(spec: str) -> tuple[int, ...] | None:
    m = re.search(r"<(\d+(?:\.\d+)*)", spec)
    if not m:
        return None
    return tuple(int(part) for part in m.group(1).split("."))


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


def test_ci_pytest_pin_excludes_benchmark_breaking_version():
    """INT-CI-2: CI must not install a pytest that breaks pytest-benchmark."""
    spec = _ci_pytest_install_spec(CI_WORKFLOW.read_text(encoding="utf-8"))
    assert spec is not None, (
        "ci.yml must pin pytest with an explicit version bound. Installing it "
        "bare lets pip resolve a release that breaks pytest-benchmark's "
        "BenchmarkFixture (INT-CI-2)."
    )
    bound = _upper_bound(spec)
    assert bound is not None, f"ci.yml pytest spec {spec!r} needs an upper bound"
    # `<9.2` is the correct bound (it excludes 9.2.0 itself), so an upper bound
    # equal to the breaking version is allowed; only a HIGHER bound is unsafe.
    assert bound <= BENCHMARK_BREAKING_PYTEST, (
        f"ci.yml pins pytest{spec}, which admits pytest "
        f">= {'.'.join(map(str, BENCHMARK_BREAKING_PYTEST))}; that release removed "
        "Function._nodeid and breaks pytest-benchmark 5.3.0 (INT-CI-2)"
    )


def test_ci_pytest_pin_matches_dev_requirements():
    """The bound CI enforces and the bound devs install must not drift."""
    ci_spec = _ci_pytest_install_spec(CI_WORKFLOW.read_text(encoding="utf-8"))
    dev_spec = _requirement_spec(
        (REPO_ROOT / "requirements-dev.txt").read_text(encoding="utf-8"), "pytest"
    )
    assert ci_spec is not None and dev_spec is not None, (
        "both ci.yml and requirements-dev.txt must bound pytest"
    )
    assert _upper_bound(ci_spec) == _upper_bound(dev_spec), (
        f"pytest upper bounds drift: ci.yml {ci_spec!r} vs "
        f"requirements-dev.txt {dev_spec!r}"
    )
