"""JEV-403 regression coverage for loud transport degradation and preflight."""

from __future__ import annotations

import ast
import io
import json
import sys
import urllib.error
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

import cron_runner
from scripts import long_run
from src.core import jev_client


@pytest.fixture(autouse=True)
def _restore_cron_globals() -> Any:
    original_mode = cron_runner.DECISION_MODE
    original_log_dir = cron_runner.LOG_DIR
    yield
    cron_runner.DECISION_MODE = original_mode
    cron_runner.LOG_DIR = original_log_dir


class _Response:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode()


class _StopAtEmulator(RuntimeError):
    pass


def _decision_row(
    cycle: int,
    *,
    jev_ok: bool,
    escalated: bool = False,
    error: str | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "cycle": cycle,
        "intent": "controller fallback" if not jev_ok else "jev RIGHT",
        "jev_answered": jev_ok,
        "jev_ok": jev_ok,
        "escalated": escalated,
    }
    if error is not None:
        row["jev_error"] = error
    return row


def _summary(autonomy: dict[str, Any]) -> str:
    return cron_runner._format_summary(
        "jev403",
        5,
        {"overworld"},
        0,
        5,
        2,
        autonomy=autonomy,
    )


class TestDecisionRowTransportStamping:
    def test_failed_overworld_attempt_keeps_transport_error_for_fallback_row(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        error = "OR_JEV: HTTP 403 RBAC: access denied"
        monkeypatch.setattr(
            jev_client,
            "decide",
            lambda *_args, **_kwargs: {
                "ok": False,
                "error": error,
                "escalate": True,
                "escalate_reason": f"transport: {error}",
            },
        )

        attempt = cron_runner._jev_overworld_decision(
            {
                "result": "overworld",
                "map_name": "Pallet Town",
                "player_tile_x": 10,
                "player_tile_y": 10,
                "adjacent": {},
            }
        )
        fields = cron_runner._jev_outcome_fields(attempt)

        assert attempt["ok"] is False
        assert fields == {"jev_ok": False, "jev_error": error}

    def test_starter_failure_stamps_jev_ok_and_truncated_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        error = "OR_JEV: HTTP 403 " + "x" * 240
        monkeypatch.setattr(
            jev_client,
            "decide",
            lambda *_args, **_kwargs: {"ok": False, "error": error},
        )
        reader = MagicMock()
        reader.party_count.return_value = 0
        reader.read_dialog_text.return_value = "Do you want CHARMANDER?"
        row: dict[str, Any] = {}

        cron_runner._select_starter_from_menu(MagicMock(), reader, decision_out=row)

        assert row["jev_ok"] is False
        assert row["jev_error"] == error[:200]
        assert len(row["jev_error"]) == 200

    def test_every_jev_answered_row_writer_expands_transport_fields(self) -> None:
        source = Path(cron_runner.__file__).read_text(encoding="utf-8")
        writers: list[ast.Dict] = []
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, ast.Dict):
                continue
            literal_keys = {
                key.value
                for key in node.keys
                if isinstance(key, ast.Constant) and isinstance(key.value, str)
            }
            if {
                "jev_answered",
                "raw_distribution",
            } <= literal_keys and "ok" not in literal_keys:
                writers.append(node)

        assert len(writers) == 3
        for writer in writers:
            expansions = [
                ast.unparse(value)
                for key, value in zip(writer.keys, writer.values)
                if key is None
            ]
            assert any(
                "_jev_outcome_fields" in expansion or expansion == "_jev_outcome"
                for expansion in expansions
            )


class TestRunDegradation:
    def test_majority_transport_failures_emit_event_and_loud_tail(self) -> None:
        rows = [
            _decision_row(
                cycle,
                jev_ok=cycle > 3,
                error=("OR_JEV: HTTP 403 denied" if cycle <= 3 else None),
            )
            for cycle in range(1, 6)
        ]

        autonomy = cron_runner._autonomy_counters(rows)
        buffer = io.StringIO()
        autonomy_row = cron_runner._write_autonomy_row(buffer, "jev403", autonomy)
        degradation_row = cron_runner._write_degradation_row(buffer, "jev403", autonomy)

        assert autonomy_row["jev_transport_failures"] == 3
        assert autonomy_row["jev_transport_failure_rate"] == 0.6
        assert degradation_row is not None
        assert degradation_row["event"] == "run_degradation"
        assert degradation_row["failures"] == 3
        assert degradation_row["jev_errors"] == ["OR_JEV: HTTP 403 denied"]
        assert degradation_row["errors"] == ["OR_JEV: HTTP 403 denied"]
        assert "DEGRADED" in _summary(autonomy)
        assert [
            json.loads(line)["event"] for line in buffer.getvalue().splitlines()
        ] == [
            "run_autonomy",
            "run_degradation",
        ]

    def test_healthy_escalated_rows_do_not_false_alarm(self) -> None:
        rows = [
            _decision_row(cycle, jev_ok=True, escalated=cycle % 2 == 0)
            for cycle in range(1, 7)
        ]

        autonomy = cron_runner._autonomy_counters(rows)
        buffer = io.StringIO()
        degradation_row = cron_runner._write_degradation_row(
            buffer, "healthy", autonomy
        )

        assert autonomy["jev_transport_failures"] == 0
        assert autonomy["jev_transport_failure_rate"] == 0.0
        assert autonomy["degraded"] is False
        assert degradation_row is None
        assert buffer.getvalue() == ""
        assert "DEGRADED" not in _summary(autonomy)


class TestLongRunSummary:
    @staticmethod
    def _write(path: Path, rows: list[dict[str, Any]]) -> None:
        path.write_text("".join(json.dumps(row) + "\n" for row in rows))

    def test_poisoned_episode_is_degraded_and_errors_non_empty(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "poisoned.jsonl"
        self._write(
            path,
            [
                _decision_row(
                    cycle,
                    jev_ok=cycle > 3,
                    error=("OR_JEV: HTTP 403 denied" if cycle <= 3 else None),
                )
                for cycle in range(1, 6)
            ],
        )

        summary = long_run.summarise(path)

        assert summary["jev_transport_failures"] == 3
        assert summary["jev_error_rows"] == 3
        assert summary["jev_failure_rate"] == 0.6
        assert summary["degraded"] is True
        assert any(error.startswith("JEV DEGRADED: 3/5") for error in summary["errors"])

    def test_healthy_episode_has_no_synthetic_degradation_error(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "healthy.jsonl"
        self._write(
            path,
            [
                _decision_row(cycle, jev_ok=True, escalated=cycle % 2 == 0)
                for cycle in range(1, 7)
            ],
        )

        summary = long_run.summarise(path)

        assert summary["jev_transport_failures"] == 0
        assert summary["jev_failure_rate"] == 0.0
        assert summary["degraded"] is False
        assert not any("JEV DEGRADED" in error for error in summary["errors"])


class TestJevPreflightClassification:
    @pytest.fixture(autouse=True)
    def _one_named_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            jev_client, "load_keys", lambda: [("OR_JEV", "not-a-real-key")]
        )

    def test_403_is_auth_failure_and_names_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def forbidden(*_args: object, **_kwargs: object) -> object:
            raise urllib.error.HTTPError(
                jev_client.ENDPOINT,
                403,
                "Forbidden",
                None,
                io.BytesIO(b'{"error":{"message":"RBAC: access denied"}}'),
            )

        monkeypatch.setattr("urllib.request.urlopen", forbidden)

        result = jev_client.preflight(timeout=15)

        assert result["status"] == "auth_failure"
        assert result["key_name"] == "OR_JEV"
        assert "HTTP 403" in result["error"]

    def test_timeout_is_transient(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def timeout(*_args: object, **_kwargs: object) -> object:
            raise TimeoutError("timed out")

        monkeypatch.setattr("urllib.request.urlopen", timeout)

        result = jev_client.preflight(timeout=15)

        assert result["status"] == "transient"
        assert result["key_name"] == "OR_JEV"
        assert "timed out" in result["error"]

    def test_ok_is_pass(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "urllib.request.urlopen",
            lambda *_args, **_kwargs: _Response(
                {"answers": {"preflight": {"choice": "READY"}}}
            ),
        )

        result = jev_client.preflight(timeout=15)

        assert result == {"status": "pass", "ok": True, "key_name": "OR_JEV"}


class TestMainPreflightGate:
    def _stop_before_boot(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        argv: list[str],
        result: dict[str, Any],
    ) -> tuple[list[int], Path]:
        calls: list[int] = []
        for name in cron_runner.DECISION_MODE_ENV_VARS:
            monkeypatch.delenv(name, raising=False)

        def preflight(*, timeout: int) -> dict[str, Any]:
            calls.append(timeout)
            return result

        def stop_emulator(_rom: str) -> object:
            raise _StopAtEmulator

        monkeypatch.chdir(tmp_path)
        log_dir = tmp_path / "logs"
        monkeypatch.setattr(cron_runner, "LOG_DIR", log_dir)
        monkeypatch.setattr(jev_client, "preflight", preflight)
        monkeypatch.setattr(cron_runner, "Emulator", stop_emulator)
        monkeypatch.setattr(sys, "argv", ["cron_runner.py", "--run-id", "gate", *argv])
        with pytest.raises(_StopAtEmulator):
            cron_runner.main()
        return calls, log_dir / "run_gate.jsonl"

    @pytest.mark.parametrize(
        "argv,expected_calls,expected_status",
        [
            pytest.param([], [15], "pass", id="default-jev"),
            pytest.param(["--decision-mode", "jev"], [15], "pass", id="jev"),
            pytest.param(["--decision-mode", "llm"], [], "skipped", id="llm"),
            pytest.param(
                ["--decision-mode", "jev", "--skip-preflight"],
                [],
                "skipped",
                id="opt-out",
            ),
        ],
    )
    def test_main_gate_runs_only_when_jev_will_be_used(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        argv: list[str],
        expected_calls: list[int],
        expected_status: str,
    ) -> None:
        calls, log_path = self._stop_before_boot(
            monkeypatch,
            tmp_path,
            argv,
            {"status": "pass", "ok": True, "key_name": "OR_JEV"},
        )

        assert calls == expected_calls
        event = json.loads(log_path.read_text())
        assert event["event"] == "preflight"
        assert event["status"] == expected_status

    def test_transient_preflight_warns_and_continues_to_boot(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        calls, log_path = self._stop_before_boot(
            monkeypatch,
            tmp_path,
            ["--decision-mode", "jev"],
            {
                "status": "transient",
                "ok": False,
                "key_name": "OR_JEV",
                "error": "OR_JEV: timed out",
            },
        )

        assert calls == [15]
        event = json.loads(log_path.read_text())
        assert event["event"] == "preflight_warning"
        assert event["status"] == "transient"
        assert "continuing" in capsys.readouterr().out

    def test_auth_failure_exits_nonzero_before_emulator_boot(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        booted = False

        def emulator(_rom: str) -> object:
            nonlocal booted
            booted = True
            return object()

        monkeypatch.chdir(tmp_path)
        log_dir = tmp_path / "logs"
        monkeypatch.setattr(cron_runner, "LOG_DIR", log_dir)
        monkeypatch.setattr(
            jev_client,
            "preflight",
            lambda *, timeout: {
                "status": "auth_failure",
                "ok": False,
                "key_name": "OR_JEV",
                "error": "OR_JEV: HTTP 403 RBAC: access denied",
            },
        )
        monkeypatch.setattr(cron_runner, "Emulator", emulator)
        monkeypatch.setattr(
            sys,
            "argv",
            ["cron_runner.py", "--run-id", "auth-loss", "--decision-mode", "jev"],
        )

        with pytest.raises(SystemExit) as exc:
            cron_runner.main()

        assert exc.value.code != 0
        assert booted is False
        assert "OR_JEV" in capsys.readouterr().out
        event = json.loads((log_dir / "run_auth-loss.jsonl").read_text())
        assert event["status"] == "auth_failure"
        assert event["key_name"] == "OR_JEV"
