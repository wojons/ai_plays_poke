"""Regression coverage for the wheel package mapping."""

from pathlib import Path
import tomllib


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_setuptools_packages_preserve_src_package() -> None:
    config = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    setuptools_config = config["tool"]["setuptools"]
    packages = setuptools_config["packages"]

    assert "src" in packages
    for package in packages:
        package_dir = REPO_ROOT.joinpath(*package.split("."))
        assert package_dir.is_dir(), f"declared package has no directory: {package}"
