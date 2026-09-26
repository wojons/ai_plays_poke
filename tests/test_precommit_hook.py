import os
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
WRAPPER = REPO_ROOT / "scripts" / "hooks" / "pre-commit"


def _run(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def hook_repo(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _run("git", "init", "-q", cwd=repo)
    _run("git", "config", "user.name", "Guard Test", cwd=repo)
    _run("git", "config", "user.email", "guard@example.test", cwd=repo)

    tracked = repo / "tracked.txt"
    tracked.write_text("initial\n", encoding="utf-8")
    _run("git", "add", "tracked.txt", cwd=repo)
    _run("git", "commit", "-q", "-m", "initial", cwd=repo)

    gitreins_dir = repo / ".gitreins"
    gitreins_dir.mkdir()
    (gitreins_dir / "config.yaml").write_text("guards: {}\n", encoding="utf-8")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_gitreins = bin_dir / "gitreins"
    fake_gitreins.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' \"${FAKE_GITREINS_OUTPUT:-}\"\n"
        'exit "${FAKE_GITREINS_RC:-0}"\n',
        encoding="utf-8",
    )
    fake_gitreins.chmod(0o755)
    return repo, bin_dir


def _invoke_wrapper(
    repo: Path,
    bin_dir: Path,
    *,
    output: str = "Guard passed",
    rc: int = 0,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}{os.pathsep}{env['PATH']}",
            "FAKE_GITREINS_OUTPUT": output,
            "FAKE_GITREINS_RC": str(rc),
        }
    )
    return subprocess.run(
        ["bash", str(WRAPPER)],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _write_fresh_verdict(repo: Path) -> None:
    """Mimic what the real gitreins does on every guard invocation: persist a
    run log under .gitreins/logs/ (engine/guard_manager.py, persist_log=True
    default). The fake guard stub does not write one, so tests seed it."""
    logs = repo / ".gitreins" / "logs"
    logs.mkdir(exist_ok=True)
    (logs / "guard-test.log").write_text("ok\n", encoding="utf-8")


def test_wrapper_accepts_clean_guard_with_fresh_verdict(hook_repo):
    repo, bin_dir = hook_repo
    _write_fresh_verdict(repo)

    result = _invoke_wrapper(repo, bin_dir)

    assert result.returncode == 0
    assert "Guard passed" in result.stderr


def test_wrapper_rejects_fail_open_timeout(hook_repo):
    repo, bin_dir = hook_repo
    _write_fresh_verdict(repo)

    result = _invoke_wrapper(
        repo,
        bin_dir,
        output="Guard timed out. Remaining checks skipped — commit allowed to proceed.",
    )

    assert result.returncode == 1
    assert "guard TIMED OUT" in result.stderr


def test_wrapper_rejects_missing_fresh_verdict(hook_repo):
    repo, bin_dir = hook_repo

    result = _invoke_wrapper(repo, bin_dir)

    assert result.returncode == 1
    assert "no fresh guard verdict" in result.stderr


def test_wrapper_rejects_stale_verdict(hook_repo, monkeypatch):
    repo, bin_dir = hook_repo
    logs = repo / ".gitreins" / "logs"
    logs.mkdir()
    stale = logs / "guard-test.log"
    stale.write_text("ok\n", encoding="utf-8")
    old = 600  # seconds; wrapper rejects anything older than 5 minutes
    assert old > 300

    # Touch the mtime 10 minutes into the past.
    past = os.stat(stale).st_mtime - old
    os.utime(stale, (past, past))

    result = _invoke_wrapper(repo, bin_dir)

    assert result.returncode == 1
    assert "no fresh guard verdict" in result.stderr


def test_wrapper_preserves_guard_failure_exit_code(hook_repo):
    repo, bin_dir = hook_repo

    result = _invoke_wrapper(repo, bin_dir, output="Guard failed", rc=2)

    assert result.returncode == 2
    assert "Guard failed" in result.stderr


def test_wrapper_allows_repo_without_gitreins_config(hook_repo):
    repo, bin_dir = hook_repo
    (repo / ".gitreins" / "config.yaml").unlink()

    result = _invoke_wrapper(repo, bin_dir)

    assert result.returncode == 0


def test_wrapper_rejects_non_benign_skip(hook_repo):
    """A skip for a real reason (tool missing) must reject under allow_skips=false."""
    repo, bin_dir = hook_repo
    _write_fresh_verdict(repo)

    result = _invoke_wrapper(
        repo,
        bin_dir,
        output=(
            "Tier 1: DEGRADED PASS (skips: lsp=no LSP tool on PATH)  (test mode: full)\n"
            "  ✓ secrets — clean (gitleaks + builtin cross-check)\n"
            "  ~ lsp — skipped (no LSP tool on PATH (pylsp not installed))\n"
        ),
    )

    assert result.returncode == 1
    assert "non-benign" in result.stderr


def test_wrapper_allows_benign_no_staged_files_skip(hook_repo):
    """Bookkeeping-only commits (board JSONL, .gitreins history) legitimately
    run lint with an empty diff scope: the 'no staged files' skip is allowed."""
    repo, bin_dir = hook_repo
    _write_fresh_verdict(repo)

    result = _invoke_wrapper(
        repo,
        bin_dir,
        output=(
            "Tier 1: DEGRADED PASS (skips: lint=no staged files)  (test mode: full)\n"
            "  ✓ secrets — clean (gitleaks + builtin cross-check)\n"
            "  ~ lint — skipped (no staged files)\n"
            "  ✓ tests (full)\n"
        ),
    )

    assert result.returncode == 0


def test_tracked_wrapper_is_executable():
    assert os.access(WRAPPER, os.X_OK)
