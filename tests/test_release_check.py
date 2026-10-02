"""Tests for release metadata consistency checks."""

from pathlib import Path

from scripts import release_check


def _write_project(
    root: Path,
    *,
    project_version: str = "1.0.0",
    changelog: str = "## [Unreleased]\n\n## [1.0.0] - 2025-12-31\n",
    root_version: str = "1.0.0",
    vision_version: str = "from src import __version__\n",
    dashboard_version: str = "from src import __version__\n",
) -> None:
    (root / "src" / "vision").mkdir(parents=True)
    (root / "src" / "dashboard").mkdir(parents=True)
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "fixture"\nversion = "{project_version}"\n',
        encoding="utf-8",
    )
    (root / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
    (root / "src" / "__init__.py").write_text(
        f'__version__ = "{root_version}"\n', encoding="utf-8"
    )
    (root / "src" / "vision" / "__init__.py").write_text(
        vision_version, encoding="utf-8"
    )
    (root / "src" / "dashboard" / "__init__.py").write_text(
        dashboard_version, encoding="utf-8"
    )


def test_release_check_passes_for_consistent_dynamic_versions(
    tmp_path: Path, capsys
) -> None:
    _write_project(tmp_path)

    assert release_check.run_checks(tmp_path) == 0

    output = capsys.readouterr().out
    assert output.count("PASS ") == 5
    assert "canonical version 1.0.0 matches latest release" in output
    assert output.count("derives __version__ from src (1.0.0)") == 2


def test_release_check_fails_when_latest_release_differs(
    tmp_path: Path, capsys
) -> None:
    _write_project(tmp_path, project_version="1.1.0")

    assert release_check.run_checks(tmp_path) == 1

    output = capsys.readouterr().out
    assert "FAIL pyproject.toml/CHANGELOG.md" in output
    assert "project version 1.1.0 != latest release 1.0.0" in output


def test_release_check_fails_when_subpackage_version_differs(
    tmp_path: Path, capsys
) -> None:
    _write_project(tmp_path, dashboard_version='__version__ = "0.9.0"\n')

    assert release_check.run_checks(tmp_path) == 1

    output = capsys.readouterr().out
    assert "FAIL src/dashboard/__init__.py" in output
    assert "__version__ 0.9.0 != canonical version 1.0.0" in output


def test_release_check_fails_without_release_sections(tmp_path: Path, capsys) -> None:
    _write_project(tmp_path, changelog="# Changelog\n\nNo releases yet.\n")

    assert release_check.run_checks(tmp_path) == 1

    output = capsys.readouterr().out
    assert "FAIL CHANGELOG.md: no release or Unreleased sections found" in output
