"""Regression tests for the PYSEC temporary-file and URL hardening."""

from __future__ import annotations

import json
import stat
import tempfile
from pathlib import Path

import pytest

from scripts import game_bridge, jev_projection_probe, smoke_deleg_research
from scripts.backfill_runs import BackfillError, DuckBrainClient


@pytest.mark.parametrize(
    "base_url",
    ["file:///tmp/duckbrain", "ftp://example.test", "localhost:3000", ""],
)
def test_duckbrain_client_rejects_non_http_urls(base_url: str) -> None:
    with pytest.raises(BackfillError, match="must use http:// or https://"):
        DuckBrainClient(base_url, "pokemon-global", "test-token")


@pytest.mark.parametrize("base_url", ["http://127.0.0.1:3000", "https://example.test/"])
def test_duckbrain_client_accepts_http_urls(base_url: str) -> None:
    client = DuckBrainClient(base_url, "pokemon-global", "test-token")

    assert client.base_url == base_url.rstrip("/")


def test_probe_result_uses_distinct_owner_only_temp_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))

    first = jev_projection_probe._write_probe_result("probe", {"run": 1})
    second = jev_projection_probe._write_probe_result("probe", {"run": 2})

    assert first != second
    assert first.parent == tmp_path
    assert json.loads(first.read_text(encoding="utf-8")) == {"run": 1}
    assert stat.S_IMODE(first.stat().st_mode) == 0o600


def test_default_diagnostic_paths_are_randomized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))

    first_log = Path(game_bridge._new_log_path())
    second_log = Path(game_bridge._new_log_path())
    first_smoke = smoke_deleg_research._default_output_path()
    second_smoke = smoke_deleg_research._default_output_path()

    assert first_log != second_log
    assert first_log.parent == tmp_path
    assert stat.S_IMODE(first_log.stat().st_mode) == 0o600
    assert first_smoke != second_smoke
    assert first_smoke.parent.parent == tmp_path
    assert first_smoke.name == "run.jsonl"
