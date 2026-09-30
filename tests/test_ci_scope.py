"""Keep CI's static-analysis scope aligned with the commit guard."""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"


def test_ci_mypy_covers_runtime_scripts() -> None:
    """Scripts checked by GitReins must also be checked before merge."""
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    assert "run: mypy src/ scripts/ --ignore-missing-imports" in workflow
