"""Regression tests for the loopback game bridge concurrency boundary.

The production incident grew through the console's GET /api/stream path:
console build_state() -> game_state() -> line-delimited {"cmd": "raw"} bridge
requests. Once a Game call stopped completing, retry connections each created a
new daemon thread. These tests use a blocking fake Game to reproduce that
admission pattern without a ROM, emulator, live game, or paid API.
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from scripts import game_bridge


TOKEN = "test-token-that-is-long-enough"
WORKER_POLL_INTERVAL = 0.02
WORKER_ADMISSION_TIMEOUT = 2.0
# Admission + busy observation together must stay inside the fake Game's 3s
# release window, otherwise the first raw call times out on its own.
BUSY_OBSERVATION_TIMEOUT = 0.8
WORKER_EXIT_TIMEOUT = 2.0


@dataclass
class BlockingGame:
    """A fake Game whose raw request holds the serialized Game boundary."""

    release: threading.Event = field(default_factory=threading.Event)
    entered: threading.Event = field(default_factory=threading.Event)
    lock: threading.Lock = field(default_factory=threading.Lock)
    active: int = 0
    max_active: int = 0
    calls: int = 0
    paused: bool = False

    def raw(self) -> dict[str, Any]:
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            self.calls += 1
            self.entered.set()
        try:
            if not self.release.wait(timeout=3):
                raise TimeoutError("test did not release fake raw request")
            time.sleep(0.01)
            return {"ok": True, "obs": {"result": "fake"}, "call": self.calls}
        finally:
            with self.lock:
                self.active -= 1


@dataclass
class ServerHandle:
    port: int
    stop: threading.Event
    thread: threading.Thread

    def close(self) -> None:
        self.stop.set()
        self.thread.join(timeout=3)
        assert not self.thread.is_alive(), "bridge serve() did not shut down cleanly"


def start_server(game: object, *, workers: int = 3) -> ServerHandle:
    ready = threading.Event()
    stop = threading.Event()
    bound_port: list[int] = []

    def on_ready(port: int) -> None:
        bound_port.append(port)
        ready.set()

    thread = threading.Thread(
        target=game_bridge.serve,
        kwargs={
            "game": game,
            "token": TOKEN,
            "port": 0,
            "log": lambda _message: None,
            "max_workers": workers,
            "request_timeout": 1.0,
            "stop_event": stop,
            "on_ready": on_ready,
        },
        name="test-game-bridge-server",
    )
    thread.start()
    assert ready.wait(timeout=2), "bridge did not bind its ephemeral loopback port"
    return ServerHandle(bound_port[0], stop, thread)


def request(port: int, payload: dict[str, Any], timeout: float = 3) -> dict[str, Any]:
    with socket.create_connection(("127.0.0.1", port), timeout=timeout) as conn:
        conn.sendall((json.dumps(payload) + "\n").encode())
        response = b""
        while b"\n" not in response:
            chunk = conn.recv(65536)
            if not chunk:
                break
            response += chunk
    assert response, "bridge closed without a response"
    decoded = json.loads(response.split(b"\n", 1)[0])
    assert isinstance(decoded, dict)
    return decoded


def bridge_worker_threads() -> list[threading.Thread]:
    return [
        thread
        for thread in threading.enumerate()
        if thread.name.startswith("aipp-bridge-worker-")
    ]


def test_console_raw_retry_path_is_bounded_and_game_access_is_serialized() -> None:
    """Many concurrent raw retries cannot create more than the fixed worker set."""
    game = BlockingGame()
    server = start_server(game, workers=3)
    clients: list[threading.Thread] = []
    responses: list[dict[str, Any]] = []
    response_lock = threading.Lock()

    def call_raw() -> None:
        response = request(server.port, {"token": TOKEN, "cmd": "raw"})
        with response_lock:
            responses.append(response)

    try:
        for index in range(12):
            client = threading.Thread(target=call_raw, name=f"raw-retry-{index}")
            client.start()
            clients.append(client)

        assert game.entered.wait(timeout=2), "no raw request reached the fake Game"
        # Wait until the fixed worker set is fully admitted instead of guessing
        # with a fixed sleep: poll the live thread list for the 3 workers, and
        # hold the bounded invariant (never more than 3) across every sample.
        deadline = time.monotonic() + WORKER_ADMISSION_TIMEOUT
        while True:
            worker_threads = bridge_worker_threads()
            assert len(worker_threads) <= 3, (
                "bridge admitted more than its fixed worker set"
            )
            if len(worker_threads) == 3:
                break
            assert time.monotonic() < deadline, (
                "bridge worker set was not fully admitted in time"
            )
            time.sleep(WORKER_POLL_INTERVAL)

        # Only release once a "server busy" rejection has actually been
        # observed: releasing right after admission lets the burst drain
        # through 3 workers + pending queue before the queue ever fills, so
        # the rejection invariant is decided by this event, not by timing.
        def first_response_is_busy() -> bool:
            with response_lock:
                return any(
                    response.get("error") == "server busy" for response in responses
                )

        busy_deadline = time.monotonic() + BUSY_OBSERVATION_TIMEOUT
        while not first_response_is_busy():
            assert game.max_active == 1
            assert len(bridge_worker_threads()) <= 3
            assert time.monotonic() < busy_deadline, (
                "burst of 12 never produced a 'server busy' rejection"
            )
            time.sleep(WORKER_POLL_INTERVAL)
        assert game.max_active == 1

        game.release.set()
        for client in clients:
            client.join(timeout=3)
            assert not client.is_alive(), "raw request did not finish"

        assert len(responses) == len(clients)
        assert all(isinstance(response.get("ok"), bool) for response in responses)
        assert any(response.get("ok") is True for response in responses)
        assert any(response.get("error") == "server busy" for response in responses)
        assert game.max_active == 1
    finally:
        game.release.set()
        server.close()

    # Worker threads exit through a 0.1s pending-poll loop, so give them a
    # bounded drain window instead of sampling enumerate() exactly once.
    exit_deadline = time.monotonic() + WORKER_EXIT_TIMEOUT
    while bridge_worker_threads():
        assert time.monotonic() < exit_deadline, (
            "bridge worker threads did not exit after server close"
        )
        time.sleep(WORKER_POLL_INTERVAL)


def test_token_authentication_and_one_request_per_connection_are_preserved() -> None:
    game = BlockingGame()
    game.release.set()
    server = start_server(game, workers=2)
    try:
        denied = request(server.port, {"token": "wrong", "cmd": "raw"})
        assert denied == {"ok": False, "error": "unauthorized"}
        assert game.calls == 0

        with socket.create_connection(("127.0.0.1", server.port), timeout=2) as conn:
            first = json.dumps({"token": TOKEN, "cmd": "raw"})
            second = json.dumps({"token": TOKEN, "cmd": "raw"})
            conn.sendall((first + "\n" + second + "\n").encode())
            wire = b""
            while True:
                chunk = conn.recv(65536)
                if not chunk:
                    break
                wire += chunk

        lines = [line for line in wire.splitlines() if line]
        assert len(lines) == 1
        assert json.loads(lines[0])["ok"] is True
        assert game.calls == 1
    finally:
        server.close()


def test_soak_watchdog_uses_fake_game_and_enforces_process_thread_ceiling() -> None:
    repo = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [
            sys.executable,
            str(repo / "scripts" / "verify_game_bridge_concurrency.py"),
            "--duration",
            "0.4",
            "--workers",
            "2",
            "--concurrency",
            "2",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "PASS:" in completed.stdout
    assert "max_child_threads=3 ceiling=3" in completed.stdout
