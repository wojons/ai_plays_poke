#!/usr/bin/env python3
"""Bounded concurrency soak/watchdog for scripts/game_bridge.py.

This starts a controlled fake Game on an ephemeral loopback port. It never opens a
ROM, advances frames, presses a button, or calls a paid API. Concurrent authenticated
health requests must all return valid success objects while /proc reports no more
than one server thread plus the configured fixed bridge workers.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import multiprocessing
import socket
import sys
import time
from pathlib import Path
from typing import Any, cast

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from scripts import game_bridge  # noqa: E402

TOKEN = "load-bridge-verification-token"


class FakeGame:
    """Read-only Game stand-in that also detects overlapping dispatch."""

    paused = False

    def __init__(self, delay: float) -> None:
        self.delay = delay
        self.active = 0
        self.max_active = 0
        self.calls = 0

    def health(self) -> dict[str, Any]:
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        self.calls += 1
        try:
            time.sleep(self.delay)
            return {
                "ok": True,
                "service": "controlled-fake-game",
                "max_game_concurrency": self.max_active,
                "call": self.calls,
            }
        finally:
            self.active -= 1


def _child_server(
    ready: Any,
    stop: Any,
    workers: int,
    request_timeout: float,
    delay: float,
) -> None:
    game = FakeGame(delay)
    game_bridge.serve(
        cast(Any, game),
        TOKEN,
        0,
        lambda _message: None,
        max_workers=workers,
        request_timeout=request_timeout,
        stop_event=stop,
        on_ready=ready.send,
    )


def _thread_count(pid: int) -> int:
    status = Path(f"/proc/{pid}/status")
    if not status.exists():
        raise RuntimeError(f"bridge child {pid} exited before watchdog sample")
    for line in status.read_text(encoding="utf-8").splitlines():
        if line.startswith("Threads:"):
            return int(line.split(":", 1)[1].strip())
    raise RuntimeError(f"Threads field missing from {status}")


def _request(port: int, sequence: int, timeout: float) -> dict[str, Any]:
    payload = {"token": TOKEN, "cmd": "health", "sequence": sequence}
    with socket.create_connection(("127.0.0.1", port), timeout=timeout) as conn:
        conn.sendall((json.dumps(payload) + "\n").encode())
        wire = b""
        while b"\n" not in wire:
            chunk = conn.recv(65536)
            if not chunk:
                break
            wire += chunk
    if not wire:
        raise RuntimeError(f"request {sequence}: empty response")
    try:
        response = json.loads(wire.split(b"\n", 1)[0])
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError(
            f"request {sequence}: invalid JSON response: {error}"
        ) from error
    if not isinstance(response, dict):
        raise RuntimeError(f"request {sequence}: non-object response {response!r}")
    if response.get("ok") is not True:
        raise RuntimeError(f"request {sequence}: non-success response {response!r}")
    if response.get("service") != "controlled-fake-game":
        raise RuntimeError(f"request {sequence}: wrong responder {response!r}")
    if response.get("max_game_concurrency") != 1:
        raise RuntimeError(f"request {sequence}: Game access overlapped {response!r}")
    return response


def run_soak(
    *,
    duration: float,
    workers: int,
    concurrency: int,
    request_timeout: float,
    game_delay: float,
) -> tuple[int, int]:
    if duration <= 0:
        raise ValueError("duration must be positive")
    if workers < 1:
        raise ValueError("workers must be at least 1")
    if concurrency < 1 or concurrency > workers:
        raise ValueError("concurrency must be between 1 and workers")

    context = multiprocessing.get_context("spawn")
    parent_ready, child_ready = context.Pipe(duplex=False)
    stop = context.Event()
    child = context.Process(
        target=_child_server,
        args=(child_ready, stop, workers, request_timeout, game_delay),
        name="game-bridge-soak-server",
    )
    child.start()
    child_ready.close()
    requests = 0
    max_threads = 0
    ceiling = workers + 1  # one serve loop plus the fixed worker set

    try:
        if not parent_ready.poll(5):
            raise RuntimeError("controlled bridge did not publish its ephemeral port")
        port = int(parent_ready.recv())
        if child.pid is None:
            raise RuntimeError("controlled bridge child has no pid")
        pid = child.pid
        deadline = time.monotonic() + duration
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as clients:
            while time.monotonic() < deadline:
                futures = [
                    clients.submit(_request, port, requests + index, request_timeout)
                    for index in range(concurrency)
                ]
                for future in futures:
                    future.result()
                requests += len(futures)
                observed = _thread_count(pid)
                max_threads = max(max_threads, observed)
                if observed > ceiling:
                    raise RuntimeError(
                        f"thread ceiling breached: observed={observed} ceiling={ceiling} "
                        f"pid={child.pid}"
                    )
    finally:
        stop.set()
        child.join(timeout=game_bridge.SHUTDOWN_JOIN_TIMEOUT + 2)
        if child.is_alive():
            child.terminate()
            child.join(timeout=2)
            raise RuntimeError(
                "controlled bridge failed clean shutdown; child was terminated"
            )
        parent_ready.close()

    if child.exitcode != 0:
        raise RuntimeError(f"controlled bridge exited with status {child.exitcode}")
    if requests == 0:
        raise RuntimeError("soak completed without sending a request")
    return requests, max_threads


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=float, default=30.0)
    parser.add_argument("--workers", type=int, default=game_bridge.DEFAULT_MAX_WORKERS)
    parser.add_argument(
        "--concurrency", type=int, default=game_bridge.DEFAULT_MAX_WORKERS
    )
    parser.add_argument("--request-timeout", type=float, default=3.0)
    parser.add_argument("--game-delay", type=float, default=0.01)
    args = parser.parse_args()

    try:
        requests, max_threads = run_soak(
            duration=args.duration,
            workers=args.workers,
            concurrency=args.concurrency,
            request_timeout=args.request_timeout,
            game_delay=args.game_delay,
        )
    except Exception as error:  # noqa: BLE001 - CLI must fail loudly with the cause
        print(f"FAIL: {type(error).__name__}: {error}", file=sys.stderr)
        return 1

    ceiling = args.workers + 1
    print(
        f"PASS: requests={requests} duration_s={args.duration:g} "
        f"max_child_threads={max_threads} ceiling={ceiling} "
        f"workers={args.workers} concurrency={args.concurrency}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
