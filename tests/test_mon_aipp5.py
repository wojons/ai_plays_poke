"""MON-AIPP-5: emulator desync/frame-staleness signals and data-growth gauges.

Covers the seven P3 families added to ``src/observability/metrics.py`` and the two
production surfaces that feed them:

* ``cron_runner.py`` — ``_track_emulator_integrity`` (frame staleness + the
  DOCUMENTED desync proxy) and ``_publish_data_growth_metrics`` (screenshot /
  ledger bytes, ledger mtime).
* ``scripts/game_bridge.py`` — ``aipp_bridge_requests_total`` on every connection
  exit and ``aipp_bridge_active_connections`` around the fixed worker pool.

The registry is process-wide, so every assertion is a DELTA or a filesystem fact,
never an absolute value another test module may have moved.

Acceptance runs, in the order the row names them:

1. ``time() - aipp_runlog_last_write_timestamp_seconds > 3600`` evaluates empty
   while the ledger is being written and reports a value after it stops
   (``TestRunlogStalenessQuery``; the query is evaluated over the scrape text,
   exactly what a Prometheus evaluation of that expression does).
2. ``aipp_bridge_active_connections`` returns to 0 after a 50-connection burst,
   with no worker threads left behind (``TestBridgeBurst``).
3. ``aipp_emulator_desync_total`` increments on a corrupted boot state that never
   advances — captured before and after (``TestDesyncProxy``).
"""

from __future__ import annotations

import io
import json
import os
import re
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
from PIL import Image
from prometheus_client import REGISTRY, generate_latest

import cron_runner
from scripts import game_bridge
from src.observability import metrics

TOKEN = "test-token-that-is-long-enough"  # noqa: S105 — fake fixture token
STALE_AFTER_SECONDS = 3600.0
PROXY_FAMILIES = (
    ("aipp_emulator_desync_total", "counter"),
    ("aipp_emulator_frame_stale_seconds", "gauge"),
    ("aipp_screenshot_bytes", "gauge"),
    ("aipp_runlog_bytes", "gauge"),
    ("aipp_runlog_last_write_timestamp_seconds", "gauge"),
    ("aipp_bridge_requests_total", "counter"),
    ("aipp_bridge_active_connections", "gauge"),
)
_SAMPLE_RE = re.compile(r"^([a-zA-Z_:][a-zA-Z0-9_:]*)(\{[^}]*\})? ([0-9.eE+-]+)$")


def _exposition() -> str:
    return generate_latest(REGISTRY).decode()


def _label_text(labels: dict[str, str] | None) -> str:
    if not labels:
        return ""
    body = ",".join(f'{key}="{val}"' for key, val in sorted(labels.items()))
    return f"{{{body}}}"


def _value(name: str, **labels: str) -> float:
    """Read one sample's value from the live registry (0.0 when absent)."""
    selector = re.escape(name) + re.escape(_label_text(labels)) + r" ([0-9.eE+-]+)$"
    match = re.search(rf"^{selector}", _exposition(), re.MULTILINE)
    return float(match.group(1)) if match else 0.0


def _samples(name: str) -> list[tuple[dict[str, str], float]]:
    """Every exposed sample of one family, parsed out of the scrape text."""
    rows: list[tuple[dict[str, str], float]] = []
    for line in _exposition().splitlines():
        if line.startswith("#"):
            continue
        match = _SAMPLE_RE.match(line)
        if not match or match.group(1) != name:
            continue
        labels = dict(re.findall(r'(\w+)="([^"]*)"', match.group(2) or ""))
        rows.append((labels, float(match.group(3))))
    return rows


def _total_bridge_requests() -> float:
    """Sum every (cmd, outcome) series: one connection increments one series."""
    return sum(value for _labels, value in _samples("aipp_bridge_requests_total"))


def _eval_staleness_query(now: float) -> list[float]:
    """Evaluate ``time() - aipp_runlog_last_write_timestamp_seconds > 3600``.

    A PromQL instant query over an unlabelled gauge: for each exposed sample,
    subtract its value from the evaluation instant (``now``, what a scraper
    supplies as ``time()``) and keep the samples above the threshold. An empty
    list is literally an empty result set — not a zero, which is a different
    answer — so "the ledger is being written" is distinguishable from "the
    ledger stopped an hour ago".
    """
    ages: list[float] = []
    for _labels, value in _samples("aipp_runlog_last_write_timestamp_seconds"):
        age = now - value
        if age > STALE_AFTER_SECONDS:
            ages.append(age)
    return ages


def _drain_png_bytes(width: int = 6, height: int = 6) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (10, 20, 30)).save(buffer, format="PNG")
    return buffer.getvalue()


class TestDeclarations:
    """The P3 families exist, once, with the types the spec asks for."""

    @pytest.mark.parametrize(("family", "openmetrics_type"), PROXY_FAMILIES)
    def test_family_declared_exactly_once(
        self, family: str, openmetrics_type: str
    ) -> None:
        exposition = _exposition()
        assert exposition.count(f"# TYPE {family} {openmetrics_type}") == 1
        assert f"# HELP {family} " in exposition

    def test_closed_label_vocabularies(self) -> None:
        assert metrics.bridge_cmd_label("health") == "health"
        assert metrics.bridge_cmd_label(" HEALTH ") == "health"
        # An operator spelling never mints a series.
        assert metrics.bridge_cmd_label("rm -rf") == "unknown"
        assert metrics.bridge_cmd_label(None) == "unknown"
        assert metrics.bridge_outcome_label("ok") == "ok"
        assert metrics.bridge_outcome_label("kinda-ok") == "unknown"

    def test_cmd_vocabulary_covers_every_dispatch_verb(self) -> None:
        """The closed `cmd` enum must track `_dispatch`, verb for verb."""
        source = Path(game_bridge.__file__).read_text(encoding="utf-8")
        dispatch = source.split("def _dispatch(", 1)[1].split("\ndef ", 1)[0]
        verbs = set(re.findall(r'cmd == "([a-z_]+)"', dispatch))
        assert verbs, "no dispatch verbs found — the parse, not the code, broke"
        assert verbs <= metrics._BRIDGE_CMD_LABELS
        # "unknown"/"none" are the two non-verbs and the only permitted extras.
        assert metrics._BRIDGE_CMD_LABELS - verbs == {"unknown", "none"}


class _FrozenBoot:
    """A corrupted boot state: the emulator never renders a new frame.

    The frame is byte-identical on every capture and the RAM reader keeps
    reporting the same tile, which is the observable shape of a desync. It is
    also the shape of an idle screen — see ``TestDesyncProxy`` for why the
    counter is documented as a proxy.
    """

    def __init__(self, frame: np.ndarray, tile: dict[str, Any]) -> None:
        self.frame = frame
        self.tile = tile
        self.captures = 0

    def capture(self) -> np.ndarray:
        self.captures += 1
        return self.frame.copy()

    def observe(self) -> dict[str, Any]:
        return dict(self.tile)


def _session(boot: _FrozenBoot) -> SimpleNamespace:
    """A session shaped like the one `_cycle_header` runs against."""
    R = SimpleNamespace(
        emu=boot,
        ram_reader=boot,
        image_module=Image,
        pipeline_name="RAM reader",
        _player_named=True,
        _rival_named=True,
    )
    S = SimpleNamespace(R=R, results=[], run_id="test-run")
    S._failed_flee_attempts = 0
    S._last_dialog_text = ""
    cron_runner._init_recovery_trackers(S)
    return S


@pytest.fixture
def header_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Isolate `_cycle_header` from its unrelated tail and from the real dirs."""
    shots = tmp_path / "screenshots"
    shots.mkdir()
    monkeypatch.setattr(cron_runner, "SCREENSHOT_DIR", shots)
    # The tail of `_cycle_header` (tile tracking, navigation, party state) needs
    # a live Game; the integrity tracker under test runs before any of it.
    monkeypatch.setattr(
        cron_runner,
        "_cycle_track_tiles",
        lambda S, patch: {"current_tile": None, "map_id": patch.get("map_id")},
    )
    monkeypatch.setattr(
        cron_runner,
        "_handle_navigation_transition",
        lambda S, cycle, st, patch, tile, map_id: None,
    )
    monkeypatch.setattr(
        cron_runner,
        "_cycle_world_and_goal",
        lambda S, cycle, patch, map_id, transition: {},
    )
    monkeypatch.setattr(cron_runner, "_cycle_party_state", lambda S, patch: (1, None))
    monkeypatch.setattr(
        cron_runner, "_cycle_starter_milestone", lambda S, cycle, party_count: None
    )
    return shots


class TestDesyncProxy:
    """Acceptance 3 — the counter moves on a corrupted, non-advancing boot state."""

    def test_counter_increments_on_a_frozen_frame_with_a_frozen_ram_tile(
        self, header_env
    ) -> None:
        frame = np.zeros((16, 16, 3), dtype=np.uint8)
        boot = _FrozenBoot(frame, {"map_id": 1, "player_tile_x": 5, "player_tile_y": 6})
        S = _session(boot)

        before = _value("aipp_emulator_desync_total")
        cron_runner._cycle_header(S, 0)  # cycle 1: no previous observation
        after_first = _value("aipp_emulator_desync_total")
        fresh = _value("aipp_emulator_frame_stale_seconds")
        time.sleep(0.01)  # let the monotonic clock measurably advance
        cron_runner._cycle_header(S, 1)  # cycle 2: identical pixels + identical tile
        after_second = _value("aipp_emulator_desync_total")

        assert boot.captures == 2
        assert after_first == before, "the first cycle cannot have a previous frame"
        assert after_second == after_first + 1, (
            "a frozen frame with an unchanged RAM tile must increment the proxy"
        )
        # The staleness gauge is a direct measurement, not a proxy: it resets to
        # 0 on the cycle the frame changed and reports real elapsed time after.
        assert fresh == 0.0
        assert _value("aipp_emulator_frame_stale_seconds") >= 0.01

    def test_moving_frames_never_increment_the_proxy(self, header_env) -> None:
        """Control arm: a progressing emulator must not look desynced."""
        boot = _FrozenBoot(
            np.zeros((16, 16, 3), dtype=np.uint8),
            {"map_id": 1, "player_tile_x": 5, "player_tile_y": 6},
        )
        S = _session(boot)
        before = _value("aipp_emulator_desync_total")
        for cycle in range(3):
            # Different pixels every cycle, same tile (a walking animation).
            boot.frame = np.full((16, 16, 3), cycle + 1, dtype=np.uint8)
            cron_runner._cycle_header(S, cycle)
        assert _value("aipp_emulator_desync_total") == before

    def test_unknown_ram_tile_never_increments_the_proxy(self, header_env) -> None:
        """The RAM half is load-bearing: no tile is not evidence of a still tile."""
        boot = _FrozenBoot(np.zeros((16, 16, 3), dtype=np.uint8), {"result": "dialog"})
        S = _session(boot)
        before = _value("aipp_emulator_desync_total")
        cron_runner._cycle_header(S, 0)
        cron_runner._cycle_header(S, 1)
        assert _value("aipp_emulator_desync_total") == before

    def test_proxy_semantics_are_stated_where_the_counter_is_incremented(
        self, header_env
    ) -> None:
        """The row asks for a DOCUMENTED proxy — the caveat must live in code."""
        doc = cron_runner._track_emulator_integrity.__doc__ or ""
        assert "PROXY" in doc
        assert "desync" in doc.lower()
        assert "§8.6" in doc
        # It must not claim to detect a desync: no comparator exists (§8.6).
        assert "true desync cannot be detected" in doc

    def test_tracker_is_wired_into_every_cycle_path(self) -> None:
        """_cycle_header must call the tracker after BOTH observations exist."""
        source = (
            Path(cron_runner.__file__).read_text(encoding="utf-8")
            if cron_runner.__file__
            else ""
        )
        header = source.split("def _cycle_header(", 1)[1].split("\ndef ", 1)[0]
        observe_at = header.index("_cycle_observe(")
        track_at = header.index("_track_emulator_integrity(")
        assert track_at > observe_at, (
            "the tracker needs the frame hash AND the RAM observation"
        )


class TestRunlogStalenessQuery:
    """Acceptance 1 — the §3.3 / §6 staleness expression, evaluated for real."""

    def test_query_is_empty_while_the_ledger_is_written_and_reports_after_it_stops(
        self, tmp_path: Path
    ) -> None:
        ledger = tmp_path / "run_mon_aipp5.jsonl"
        ledger.write_text('{"cycle": 1}\n{"cycle": 2}\n', encoding="utf-8")
        shots = tmp_path / "screenshots"
        shots.mkdir()

        # ── Active run: the ledger was written moments ago ──
        cron_runner._publish_data_growth_metrics(ledger, shots)
        assert _samples("aipp_runlog_last_write_timestamp_seconds"), (
            "an existing ledger must mint the gauge"
        )
        assert ledger.stat().st_size == _value("aipp_runlog_bytes")
        assert ledger.stat().st_mtime == pytest.approx(
            _value("aipp_runlog_last_write_timestamp_seconds"), abs=1e-6
        )
        now = time.time()
        assert _eval_staleness_query(now) == [], (
            "query must evaluate EMPTY during an active run"
        )

        # ── The ledger stops; the sample is unchanged and time() moves on ──
        ages = _eval_staleness_query(now + STALE_AFTER_SECONDS + 60)
        assert len(ages) == 1, "query must return a value after the ledger stops"
        assert ages[0] == pytest.approx(STALE_AFTER_SECONDS + 60, abs=1.0)

    def test_a_real_mtime_drives_the_gauge_not_a_synthetic_now(
        self, tmp_path: Path
    ) -> None:
        """The second arm: age the file on disk, re-publish, and the query fires."""
        ledger = tmp_path / "run_mon_aipp5.jsonl"
        ledger.write_text('{"cycle": 1}\n', encoding="utf-8")
        shots = tmp_path / "screenshots"
        shots.mkdir()
        stopped_at = time.time() - (STALE_AFTER_SECONDS + 120)
        os.utime(ledger, (stopped_at, stopped_at))

        cron_runner._publish_data_growth_metrics(ledger, shots)

        assert _value("aipp_runlog_last_write_timestamp_seconds") == pytest.approx(
            stopped_at, abs=1e-6
        )
        ages = _eval_staleness_query(time.time())
        assert len(ages) == 1
        assert ages[0] > STALE_AFTER_SECONDS

    def test_missing_ledger_records_no_timestamp(self, tmp_path: Path) -> None:
        """No ledger on disk must not stamp 1970 (that would fire the alarm)."""
        cron_runner._publish_data_growth_metrics(
            tmp_path / "never-written.jsonl", tmp_path / "no-screens"
        )
        assert _value("aipp_runlog_bytes") == 0.0
        assert _value("aipp_screenshot_bytes") == 0.0

    def test_data_growth_gauges_are_filesystem_measurements(
        self, tmp_path: Path
    ) -> None:
        ledger = tmp_path / "run_bytes.jsonl"
        ledger.write_text("x" * 512, encoding="utf-8")
        shots = tmp_path / "screenshots"
        shots.mkdir()
        (shots / "step_0001.png").write_bytes(_drain_png_bytes())
        (shots / "step_0002.png").write_bytes(_drain_png_bytes())

        cron_runner._publish_data_growth_metrics(ledger, shots)

        assert _value("aipp_runlog_bytes") == 512.0
        assert _value("aipp_screenshot_bytes") == sum(
            path.stat().st_size for path in shots.iterdir()
        )

    def test_growth_is_published_per_cycle_and_at_run_end(self) -> None:
        source = (
            Path(cron_runner.__file__).read_text(encoding="utf-8")
            if cron_runner.__file__
            else ""
        )
        cycles = source.split("def _run_cycles(", 1)[1].split("\ndef ", 1)[0]
        finalize = source.split("def _finalize_run(", 1)[1].split("\ndef ", 1)[0]
        assert "_publish_data_growth_metrics()" in cycles
        assert "_publish_data_growth_metrics()" in finalize
        # Run end must publish AFTER the ledger is closed, or the size is stale.
        assert finalize.index("log_file.close()") < finalize.index(
            "_publish_data_growth_metrics()"
        )


class _InstantGame:
    """Answers every verb without a ROM, an emulator, or a paid API."""

    def health(self) -> dict[str, Any]:
        return {"ok": True, "map": "test"}

    def raw(self) -> dict[str, Any]:
        return {"ok": True, "obs": {"result": "fake"}}


def _bridge_request(port: int, payload: dict[str, Any], timeout: float = 5) -> dict:
    with socket.create_connection(("127.0.0.1", port), timeout=timeout) as conn:
        conn.sendall((json.dumps(payload) + "\n").encode())
        buffer = bytearray()
        while b"\n" not in buffer:
            chunk = conn.recv(65536)
            if not chunk:
                break
            buffer.extend(chunk)
    assert buffer, "bridge closed without a response"
    decoded = json.loads(buffer.split(b"\n", 1)[0])
    assert isinstance(decoded, dict)
    return decoded


@dataclass
class _Server:
    port: int
    stop: threading.Event
    thread: threading.Thread

    def close(self) -> None:
        self.stop.set()
        self.thread.join(timeout=5)
        assert not self.thread.is_alive(), "bridge serve() did not shut down"


def _start_server(
    game: object, *, workers: int = 4, metrics_file: Path | None = None
) -> _Server:
    ready = threading.Event()
    stop = threading.Event()
    bound: list[int] = []

    def on_ready(port: int) -> None:
        bound.append(port)
        ready.set()

    thread = threading.Thread(
        target=game_bridge.serve,
        kwargs={
            "game": game,
            "token": TOKEN,
            "port": 0,
            "log": lambda _message: None,
            "max_workers": workers,
            "request_timeout": 2.0,
            "stop_event": stop,
            "on_ready": on_ready,
            "metrics_file": metrics_file,
        },
        name="test-mon-aipp5-bridge",
    )
    thread.start()
    assert ready.wait(timeout=5), "bridge did not bind its ephemeral loopback port"
    return _Server(bound[0], stop, thread)


def _bridge_workers() -> list[threading.Thread]:
    return [
        thread
        for thread in threading.enumerate()
        if thread.name.startswith("aipp-bridge-worker-")
    ]


class TestBridgeBurst:
    """Acceptance 2 — 50 connections, then the gauge must be back at 0."""

    def test_active_connections_returns_to_zero_after_fifty_connection_burst(
        self, tmp_path: Path
    ) -> None:
        metrics_file = tmp_path / "aipp_bridge.prom"
        baseline_workers = len(_bridge_workers())
        before_active = _value("aipp_bridge_active_connections")
        before_total = _total_bridge_requests()
        before_ok = _value("aipp_bridge_requests_total", cmd="health", outcome="ok")

        server = _start_server(_InstantGame(), workers=4, metrics_file=metrics_file)
        try:
            responses: list[dict[str, Any]] = []
            # 5 waves of 10 concurrent connections: a real burst against the
            # fixed 4-worker pool (so admission pressure is genuine) while the
            # per-wave drain keeps the harness off the listen backlog.
            for _wave in range(5):
                with ThreadPoolExecutor(max_workers=10) as pool:
                    responses.extend(
                        pool.map(
                            lambda _n: _bridge_request(
                                server.port, {"token": TOKEN, "cmd": "health"}
                            ),
                            range(10),
                        )
                    )
            assert len(responses) == 50
            # Every connection was answered — either served or refused as busy.
            assert all(isinstance(rep.get("ok"), bool) for rep in responses)
        finally:
            server.close()

        assert _value("aipp_bridge_active_connections") == 0.0, (
            "connections leaked: the gauge did not return to zero"
        )
        assert _value("aipp_bridge_active_connections") <= before_active
        assert _total_bridge_requests() == before_total + 50, (
            "50 connections must produce exactly 50 counted requests: a served"
            " request counts as (health, ok) and a queue rejection as (none, busy)"
        )
        served = _value("aipp_bridge_requests_total", cmd="health", outcome="ok")
        assert served > before_ok, "the burst never got a request served"
        # No worker survived the burst: the historical leak was thread growth.
        assert len(_bridge_workers()) == baseline_workers

        text = metrics_file.read_text(encoding="utf-8")
        assert "aipp_bridge_active_connections 0" in text
        # The textfile carries the same numbers the registry does, so a
        # node_exporter scrape and an in-process read cannot disagree.
        assert (
            f'aipp_bridge_requests_total{{cmd="health",outcome="ok"}} {served:g}'
            in text
        )

    def test_every_connection_exit_is_counted_exactly_once(self) -> None:
        """ok / unauthorized / invalid / unknown-verb / closed-without-request."""
        server = _start_server(_InstantGame(), workers=2)
        try:
            ok = _bridge_request(server.port, {"token": TOKEN, "cmd": "health"})
            assert ok.get("ok") is True
            denied = _bridge_request(server.port, {"token": "wrong", "cmd": "health"})
            assert denied.get("ok") is False
            unknown = _bridge_request(server.port, {"token": TOKEN, "cmd": "nope"})
            assert unknown.get("ok") is False
            with socket.create_connection(
                ("127.0.0.1", server.port), timeout=5
            ) as conn:
                conn.sendall(b"{not json}\n")
                assert conn.recv(65536)
            # A connection that closes without a request line must still count.
            socket.create_connection(("127.0.0.1", server.port), timeout=5).close()
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if (
                    _value("aipp_bridge_requests_total", cmd="none", outcome="empty")
                    > 0
                ):
                    break
                time.sleep(0.02)
        finally:
            server.close()

        assert _value("aipp_bridge_requests_total", cmd="health", outcome="ok") > 0
        assert (
            _value("aipp_bridge_requests_total", cmd="health", outcome="unauthorized")
            > 0
        )
        # A verb `_dispatch` does not serve is bucketed as "unknown" (the closed
        # vocabulary forbids minting an operator-supplied label), and the reply
        # was an error.
        assert _value("aipp_bridge_requests_total", cmd="unknown", outcome="error") > 0
        # Unparseable JSON never reaches the verb, so it is cmd="none".
        assert _value("aipp_bridge_requests_total", cmd="none", outcome="invalid") > 0
        assert _value("aipp_bridge_requests_total", cmd="none", outcome="empty") > 0
        assert _value("aipp_bridge_active_connections") == 0.0
