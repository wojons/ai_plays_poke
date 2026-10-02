#!/usr/bin/env python3
"""Validate that all release-version surfaces agree."""

from __future__ import annotations

import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_SECTION_RE = re.compile(
    r"^\[project\]\s*$\n(?P<body>.*?)(?=^\[|\Z)", re.MULTILINE | re.DOTALL
)
VERSION_LINE_RE = re.compile(r'^version\s*=\s*["\']([^"\']+)["\']\s*$', re.MULTILINE)
CHANGELOG_SECTION_RE = re.compile(
    r"^## \[([^\]\n]+)\](?:\s+-\s+\d{4}-\d{2}-\d{2})?\s*$", re.MULTILINE
)


@dataclass(frozen=True)
class Check:
    """One release consistency result."""

    name: str
    passed: bool
    detail: str

    def render(self) -> str:
        """Render one clear, stable status line."""
        status = "PASS" if self.passed else "FAIL"
        return f"{status} {self.name}: {self.detail}"


@dataclass(frozen=True)
class ModuleVersion:
    """A Python module's declared or root-derived version."""

    value: str
    derived_from_root: bool


def _project_version(root: Path) -> str:
    text = (root / "pyproject.toml").read_text(encoding="utf-8")
    project_match = PROJECT_SECTION_RE.search(text)
    if project_match is None:
        raise ValueError("missing [project] section")
    version_match = VERSION_LINE_RE.search(project_match.group("body"))
    if version_match is None:
        raise ValueError("missing project version")
    return version_match.group(1)


def _changelog_sections(root: Path) -> list[str]:
    text = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    return CHANGELOG_SECTION_RE.findall(text)


def _module_version(
    path: Path, *, canonical: str, allow_root_derivation: bool
) -> ModuleVersion:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == "src":
            for imported in node.names:
                bound_name = imported.asname or imported.name
                if imported.name == "__version__" and bound_name == "__version__":
                    if not allow_root_derivation:
                        raise ValueError("root version cannot derive from itself")
                    return ModuleVersion(canonical, True)
        if isinstance(node, ast.Assign):
            if any(
                isinstance(target, ast.Name) and target.id == "__version__"
                for target in node.targets
            ):
                if isinstance(node.value, ast.Constant) and isinstance(
                    node.value.value, str
                ):
                    return ModuleVersion(node.value.value, False)
                raise ValueError("__version__ must be a string literal")
    raise ValueError("missing __version__")


def _metadata_check(root: Path) -> tuple[Check, str | None]:
    try:
        project_version = _project_version(root)
    except (OSError, ValueError) as exc:
        return Check("pyproject.toml/CHANGELOG.md", False, str(exc)), None

    try:
        released = [
            section
            for section in _changelog_sections(root)
            if section.casefold() != "unreleased"
        ]
    except OSError as exc:
        return Check("pyproject.toml/CHANGELOG.md", False, str(exc)), project_version

    if not released:
        return (
            Check(
                "pyproject.toml/CHANGELOG.md",
                False,
                "no released version found in CHANGELOG.md",
            ),
            project_version,
        )

    latest_release = released[0]
    if project_version != latest_release:
        return (
            Check(
                "pyproject.toml/CHANGELOG.md",
                False,
                f"project version {project_version} != latest release {latest_release}",
            ),
            project_version,
        )
    return (
        Check(
            "pyproject.toml/CHANGELOG.md",
            True,
            f"canonical version {project_version} matches latest release",
        ),
        project_version,
    )


def _python_version_check(
    root: Path, relative_path: str, canonical: str | None, *, allow_derived: bool
) -> Check:
    if canonical is None:
        return Check(relative_path, False, "canonical project version is unavailable")
    try:
        version = _module_version(
            root / relative_path,
            canonical=canonical,
            allow_root_derivation=allow_derived,
        )
    except (OSError, SyntaxError, ValueError) as exc:
        return Check(relative_path, False, str(exc))

    if version.value != canonical:
        return Check(
            relative_path,
            False,
            f"__version__ {version.value} != canonical version {canonical}",
        )
    if version.derived_from_root:
        detail = f"derives __version__ from src ({canonical})"
    else:
        detail = f"__version__ = {canonical}"
    return Check(relative_path, True, detail)


def _changelog_presence_check(root: Path) -> Check:
    try:
        sections = _changelog_sections(root)
    except OSError as exc:
        return Check("CHANGELOG.md", False, str(exc))
    if not sections:
        return Check("CHANGELOG.md", False, "no release or Unreleased sections found")
    return Check("CHANGELOG.md", True, f"found sections: {', '.join(sections)}")


def run_checks(root: Path) -> int:
    """Print all release checks and return a process-style status code."""
    metadata, canonical = _metadata_check(root)
    checks = [
        metadata,
        _python_version_check(root, "src/__init__.py", canonical, allow_derived=False),
        _python_version_check(
            root, "src/vision/__init__.py", canonical, allow_derived=True
        ),
        _python_version_check(
            root, "src/dashboard/__init__.py", canonical, allow_derived=True
        ),
        _changelog_presence_check(root),
    ]
    for check in checks:
        print(check.render())
    return 0 if all(check.passed for check in checks) else 1


def main() -> int:
    """Run checks against the repository containing this script."""
    return run_checks(Path(__file__).resolve().parents[1])


if __name__ == "__main__":
    sys.exit(main())
