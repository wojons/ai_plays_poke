"""INT-CLI-DRYRUN-1 — the stdlib-only ``--dry-run`` fast path contract (GAP-032).

``cron_runner._dry_run_precheck`` (GAP-032) is documented to handle ``--dry-run``
at import time, BEFORE the heavy third-party imports, so a bare ``python3``
(no venv) can validate setup. DOGFOOD-PERF-001 (``db3f3efb``) deleted the
import-time call while deferring the heavy imports, and the
``src.observability.metrics`` import (prometheus_client) ended up ahead of
everything — so the module import itself died under a dependency-free
interpreter, and the in-main ``--dry-run`` branch sat behind the decision-mode
gate (exit 2 without ``--decision-mode``).

These tests pin the restored contract at the only level that can prove it:
the real module import order, in a subprocess.

1. A dependency-free interpreter (``<python> -S``: site-packages disabled, so
   prometheus_client/numpy/PIL are unimportable) runs
   ``cron_runner.py --dry-run --skip-key-check`` and exits 0 with the
   validation summary.
2. ``--dry-run`` needs neither the venv nor ``--decision-mode``: the precheck
   exits before the mode gate in ``_main_parse_and_dry_run``.
3. Real runs keep the mode gate: a non-dry-run invocation without a mode is
   still refused with exit 2.
4. The GAP-048 liveness path publishes probe results through a lazy shim so a
   bare-interpreter ``--dry-run`` (which runs before metrics are importable)
   never dies on the metrics call; real runs publish exactly as before.

Hermeticity: the subprocesses always pass ``--skip-key-check``, so the repo-root
``.env`` keys (loaded file-side by ``_load_dotenv_stdlib``) are never probed
over the network.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import cron_runner

CRON_RUNNER = Path(cron_runner.__file__).resolve()
REPO_ROOT = CRON_RUNNER.parent

# Keys _load_dotenv_stdlib copies from the repo-root .env into os.environ.
# Stripped from the inherited env AND never probed (--skip-key-check).
_KEY_ENV_VARS = ("OPENROUTER_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY")


def _offline_env() -> dict[str, str]:
    """Ambient env minus the probe keys and PYTHON* overrides."""
    return {
        k: v
        for k, v in os.environ.items()
        if k not in _KEY_ENV_VARS and not k.startswith(("PYTHON", "COVERAGE"))
    }


def _bare_env() -> dict[str, str]:
    """``env -i`` equivalent: no ambient keys, no PYTHON* vars at all."""
    return {"PATH": os.defpath, "HOME": os.environ.get("HOME", "")}


def _run_cron_runner(
    argv: list[str], *, bare: bool
) -> subprocess.CompletedProcess[str]:
    """Run cron_runner.py as a real CLI process.

    ``bare=True`` disables site-packages (``-S``), which is the in-test
    equivalent of ``env -i /usr/bin/python3 -S ...``: every third-party
    package becomes unimportable and only stdlib survives.
    """
    cmd = [sys.executable, *(["-S"] if bare else []), str(CRON_RUNNER), *argv]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=_bare_env() if bare else _offline_env(),
        cwd=str(REPO_ROOT),
        timeout=120,
    )


def _valid_setup_argv(tmp_path: Path) -> list[str]:
    """--dry-run args that validate regardless of the checkout's data/ dir."""
    rom = tmp_path / "rom.gb"
    rom.write_bytes(b"placeholder")  # presence is what validation checks
    return [
        "--dry-run",
        "--skip-key-check",
        "--rom",
        str(rom),
        "--boot-state",
        "skip",
    ]


class TestStdlibOnlyDryRunFastPath:
    """The restored GAP-032 contract, proven against the real import order."""

    def test_dependency_free_interpreter_runs_dry_run(self, tmp_path) -> None:
        """``<venv python> -S`` has NO third-party packages: precheck or die."""
        result = _run_cron_runner(_valid_setup_argv(tmp_path), bare=True)
        assert result.returncode == 0, (
            f"rc={result.returncode}\nstdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
        first_line = result.stdout.splitlines()[0]
        assert first_line.startswith("[DRY-RUN]"), first_line
        assert "setup validation" in first_line
        assert "ModuleNotFoundError" not in result.stderr

    def test_dry_run_does_not_require_decision_mode(self, tmp_path) -> None:
        """The precheck exits before the mode gate (venv interpreter)."""
        result = _run_cron_runner(_valid_setup_argv(tmp_path), bare=False)
        assert result.returncode == 0, (
            f"rc={result.returncode}\nstdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
        assert "[DRY-RUN]" in result.stdout
        assert "decision mode is required" not in result.stdout


class TestRealRunsKeepTheModeGate:
    def test_real_run_without_mode_is_still_refused(self) -> None:
        """Contract (a) keeps mode resolution ahead of real runs (exit 2)."""
        env = _offline_env()
        env.pop("AIPP_DECISION_MODE", None)
        env.pop("CRON_DECISION_MODE", None)
        result = subprocess.run(
            [sys.executable, str(CRON_RUNNER), "--skip-key-check"],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(REPO_ROOT),
            timeout=120,
        )
        assert result.returncode == 2, (
            f"rc={result.returncode}\nstdout:\n{result.stdout}"
        )
        assert "decision mode is required" in result.stdout
        assert "--decision-mode" in result.stdout


class TestCredentialMetricShim:
    """GAP-048 probe results reach the metrics registry lazily (MON-AIPP-4)."""

    def test_probe_results_publish_through_the_shim(self, monkeypatch) -> None:
        calls: list[tuple[str, bool]] = []
        monkeypatch.setattr(
            "src.observability.metrics.set_credential_valid",
            lambda name, live: calls.append((name, live)),
        )
        cron_runner._publish_credential_metric("OPENROUTER_API_KEY", False)
        assert calls == [("OPENROUTER_API_KEY", False)]

    def test_unimportable_metrics_never_break_liveness_probes(
        self, monkeypatch
    ) -> None:
        """A bare-interpreter --dry-run probes keys with no metrics module."""
        # ``sys.modules[name] = None`` makes the import raise ImportError —
        # the same failure a -S interpreter hits for prometheus_client.
        monkeypatch.setitem(sys.modules, "src.observability.metrics", None)
        cron_runner._publish_credential_metric("DEEPSEEK_API_KEY", True)
