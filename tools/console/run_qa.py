#!/usr/bin/env python3
# Console URL is a fixed loopback HTTP endpoint and every open has a bounded timeout.
# ruff: noqa: S310

"""Run the existing console QA tools without issuing game movement commands."""

from __future__ import annotations

import argparse
import json
import runpy
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import ExitStack
from pathlib import Path
from types import TracebackType
from typing import Any, Callable
from unittest.mock import patch

CONSOLE_URL = "http://127.0.0.1:8899"
HEALTH_PATH = "/api/health"
SERVICE = "aipp-console.service"
ROOT = Path(__file__).resolve().parents[2]
TOOLS = Path(__file__).resolve().parent
MOVEMENT_RESULTS = {
    "operator press moves the game",
    "press appears in the operator event log",
    "game restored from the save after the movement test",
}


class _BlockedMovementResponse:
    """A successful inert response used only for intercepted movement requests."""

    status = 200

    def __enter__(self) -> _BlockedMovementResponse:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    def read(self, amount: int = -1) -> bytes:
        del amount
        return b'{"ok": true, "skipped": "movement changes game state"}'


Urlopen = Callable[..., Any]
Run = Callable[..., subprocess.CompletedProcess[Any]]


def _request_json(
    path: str,
    body: dict[str, Any] | None = None,
    timeout: int = 30,
) -> tuple[int, dict[str, Any]]:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        CONSOLE_URL + path,
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(  # nosec B310
            request, timeout=timeout
        ) as response:
            payload = json.loads(response.read())
            return response.status, payload if isinstance(payload, dict) else {}
    except urllib.error.HTTPError as error:
        return error.code, {}
    except (OSError, TimeoutError, json.JSONDecodeError):
        return 0, {}


def _healthy() -> bool:
    status, payload = _request_json(HEALTH_PATH, timeout=5)
    return status == 200 and payload.get("ok") is True


def _ensure_console() -> tuple[bool, str]:
    """Start the systemd user service when its health endpoint is down."""
    if _healthy():
        return True, "console already healthy"

    print(f"START: {SERVICE} (health endpoint was down)", flush=True)
    started = subprocess.run(
        ["systemctl", "--user", "start", SERVICE],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if started.returncode != 0:
        detail = (started.stderr or started.stdout).strip()
        return False, f"could not start {SERVICE}: {detail}"

    for _ in range(30):
        if _healthy():
            return True, f"started {SERVICE}"
        time.sleep(1)
    return False, f"{SERVICE} did not become healthy within 30 seconds"


def _movement_safe_urlopen(original: Urlopen) -> Urlopen:
    def open_without_movement(
        request: str | urllib.request.Request,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        url = (
            request.full_url if isinstance(request, urllib.request.Request) else request
        )
        if urllib.parse.urlsplit(url).path == "/api/press":
            print(
                "SKIP: movement button request blocked; unattended QA must not change game state",
                flush=True,
            )
            return _BlockedMovementResponse()
        return original(request, *args, **kwargs)

    return open_without_movement


def _movement_safe_run(original: Run) -> Run:
    def run_without_restore(
        *args: Any, **kwargs: Any
    ) -> subprocess.CompletedProcess[Any]:
        command = args[0] if args else kwargs.get("args")
        if (
            isinstance(command, (list, tuple))
            and any(str(part).endswith("scripts/play.py") for part in command)
            and "load" in command
        ):
            print(
                "SKIP: save-state restore blocked because no movement was performed",
                flush=True,
            )
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        return original(*args, **kwargs)

    return run_without_restore


def _run_tool(path: Path, block_movement: bool = False) -> dict[str, Any]:
    print(f"\nRUN: {path.relative_to(ROOT)}", flush=True)
    if not block_movement:
        return runpy.run_path(str(path), run_name="__main__")

    print(
        "SKIP: movement-button checks and their save-state restore are excluded from unattended QA",
        flush=True,
    )
    with ExitStack() as stack:
        safe_urlopen = _movement_safe_urlopen(urllib.request.urlopen)
        safe_run = _movement_safe_run(subprocess.run)
        stack.enter_context(patch("urllib.request.urlopen", safe_urlopen))
        stack.enter_context(patch("subprocess.run", safe_run))
        return runpy.run_path(str(path), run_name="__main__")


def _validate_control_results(namespace: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    call = namespace.get("call")
    checks = namespace.get("CHECKS")
    if not callable(call) or not isinstance(checks, list):
        return ["test_controls.py did not expose its CHECKS/call contract"]

    for method, path, body in checks:
        status, _elapsed, _head = call(path, body, method)
        if status != 200:
            failures.append(f"{method} {path} returned HTTP {status}, expected 200")
    return failures


def _toggle_round_trips() -> list[str]:
    """Prove both boolean inputs are accepted, observed, and restored."""
    failures: list[str] = []
    status, baseline = _request_json("/api/state")
    if status != 200:
        return [f"GET /api/state returned HTTP {status} before toggle checks"]

    toggles = (
        ("/api/live", "live"),
        ("/api/auto", "auto_vision"),
    )
    originals: dict[str, bool] = {}
    for _path, state_key in toggles:
        value = (baseline.get(state_key) or {}).get("on")
        if not isinstance(value, bool):
            failures.append(f"state.{state_key}.on is not a boolean")
            continue
        originals[state_key] = value

    try:
        for path, state_key in toggles:
            if state_key not in originals:
                continue
            for desired in (False, True):
                post_status, response = _request_json(path, {"on": desired})
                observed_status, observed = _request_json("/api/state")
                echoed = (response.get(state_key) or {}).get("on")
                read_back = (observed.get(state_key) or {}).get("on")
                if post_status != 200:
                    failures.append(f"POST {path} returned HTTP {post_status}")
                if observed_status != 200:
                    failures.append(
                        f"GET /api/state returned HTTP {observed_status} after POST {path}"
                    )
                if echoed is not desired or read_back is not desired:
                    failures.append(
                        f"POST {path} ignored on={desired}: echo={echoed!r}, state={read_back!r}"
                    )
    finally:
        for path, state_key in toggles:
            if state_key not in originals:
                continue
            restore_status, _response = _request_json(
                path, {"on": originals[state_key]}
            )
            if restore_status != 200:
                failures.append(
                    f"POST {path} returned HTTP {restore_status} while restoring baseline"
                )

    return failures


def _validate_pass_results(namespace: dict[str, Any]) -> list[str]:
    results = namespace.get("RESULTS")
    if not isinstance(results, list):
        return ["test_pass.py did not expose its RESULTS contract"]

    failures: list[str] = []
    result_names = {row[0] for row in results if isinstance(row, tuple) and row}
    missing = MOVEMENT_RESULTS - result_names
    if missing:
        failures.append(f"movement-result contract changed; missing {sorted(missing)}")

    for name, result, detail in results:
        if name in MOVEMENT_RESULTS:
            print(f"SKIP | {name}  [movement changes game state]", flush=True)
        elif result != "PASS":
            failures.append(f"{name}: {detail or result}")
    return failures


def _dry_run() -> int:
    def must_not_open(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        raise AssertionError("movement request escaped the blocker")

    safe_open = _movement_safe_urlopen(must_not_open)
    with safe_open(
        urllib.request.Request(CONSOLE_URL + "/api/press", data=b"{}")
    ) as response:
        if response.status != 200:
            print("FAIL: movement blocker did not return its inert response")
            return 1

    print(f"DRY RUN: health-check {CONSOLE_URL}{HEALTH_PATH}")
    print(f"DRY RUN: start {SERVICE} only when health is down")
    print("DRY RUN: run tools/console/test_controls.py")
    print("DRY RUN: verify every read endpoint and both values of every safe toggle")
    print("DRY RUN: run tools/console/test_pass.py with /api/press blocked")
    print("PASS: unattended movement skip path is active")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="prove the movement blocker and print the run without contacting the console",
    )
    args = parser.parse_args()
    if args.dry_run:
        return _dry_run()

    healthy, detail = _ensure_console()
    print(("PASS" if healthy else "FAIL") + f": {detail}", flush=True)
    if not healthy:
        return 1

    failures: list[str] = []
    try:
        controls = _run_tool(TOOLS / "test_controls.py")
        failures.extend(_validate_control_results(controls))
    except Exception as error:  # noqa: BLE001
        failures.append(f"test_controls.py crashed: {type(error).__name__}: {error}")

    failures.extend(_toggle_round_trips())

    try:
        full_pass = _run_tool(TOOLS / "test_pass.py", block_movement=True)
        failures.extend(_validate_pass_results(full_pass))
    except Exception as error:  # noqa: BLE001
        failures.append(f"test_pass.py crashed: {type(error).__name__}: {error}")

    print("\n=== unattended console QA summary ===")
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        print(f"RESULT: FAIL ({len(failures)} failure(s))")
        return 1
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
