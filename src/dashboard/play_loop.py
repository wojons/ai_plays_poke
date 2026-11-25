"""Dashboard-owned play loop: the production caller of ``update_tick()``.

WHY THIS EXISTS (QA-CONSOLE-4)
    ``POST /control/start`` used to flip three fields on the in-memory session
    (``running``/``paused``/``start_time``) and answer ``{"status": "started"}``.
    Nothing advanced the emulator: ``DashboardSession.update_tick()`` — the only
    writer of ``tick_count`` / ``location`` / ``last_action_time`` — had no
    caller outside ``tests/test_dashboard.py``. A dogfood run therefore read
    ``running: true, tick_count: 0`` forever, with ``current_state: "idle"``,
    ``location: "Unknown"``, ``last_action_time: null`` and a 404 from
    ``/screenshots/latest``, while every unit test was green: the suite exercised
    a method no production path invoked (phantom coverage).

    This module is that missing path. A background thread owns one ``Emulator``
    and one ``RAMReader`` — the same components ``src/core/game_loop.py`` and
    ``cron_runner.py`` drive — ticks the emulator, derives the location from
    game RAM, saves screenshots through the session's ``ScreenshotManager`` and
    reports progress through ``DashboardSession.update_tick()``. Operator input
    queued through ``POST /control/command`` is executed here (this thread owns
    the emulator); with nothing queued the loop runs a deterministic
    exploration cycle. No LLM is involved, so a started session costs no API
    spend — decisions stay with the operator, or with ``cron_runner.py``.

HONESTY CONTRACT
    A loop that cannot run must never leave a session claiming to be running
    with zero ticks. Startup failures (missing ROM, unreadable boot state,
    emulator crash) are recorded on the session via ``record_loop_error()``,
    which flips ``running`` off and publishes ``last_error`` on ``GET /status``;
    ``/control/start`` refuses with 503 instead of answering ``started``.

CONFIGURATION (all optional, env vars)
    ``PTP_DASHBOARD_ROM``          ROM path (default: ``data/rom/<Blue SGB>.gb``)
    ``PTP_DASHBOARD_BOOT_STATE``   checkpoint path, or ``skip`` for intro bypass
    ``PTP_DASHBOARD_START_TIMEOUT`` seconds ``/control/start`` waits for tick 1
    ``PTP_DASHBOARD_STALL_TIMEOUT`` seconds without a tick before a running
                                   session is reported stalled (mid-run wedge
                                   bound; see ``DashboardSession``
                                   ``.check_tick_staleness``)
"""

from __future__ import annotations

import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_ROM = (
    REPO_ROOT / "data/rom/Pokemon - Blue Version (USA, Europe) (SGB Enhanced).gb"
)
# ``data/boot.state`` is the same known-good overworld checkpoint cron_runner.py
# boots from (DEFAULT_BOOT_STATE): starter picked, player standing in Pallet
# Town. Booting from it puts a fresh dashboard session straight into a state
# where the RAM map name is real, instead of A-mashing through the intro.
DEFAULT_BOOT_STATE = REPO_ROOT / "data/boot.state"

DEFAULT_FRAMES_PER_TICK = 8
DEFAULT_TICK_INTERVAL = 0.05
DEFAULT_SCREENSHOT_EVERY = 5
DEFAULT_PRESS_EVERY = 10

#: Direction cycle for the exploration policy. Deliberately deterministic: the
#: loop's job is observable progress, not a campaign, and a fixed cycle keeps
#: the behaviour reproducible in a test.
_BUTTON_CYCLE = ("down", "left", "up", "right")

# Buttons ``POST /control/command`` may name, spelled the way a player would.
VALID_BUTTONS = frozenset({"a", "b", "start", "select", "up", "down", "left", "right"})
# "press:up" / "button: A" / "tap b" are the same instruction as "up".
_COMMAND_PREFIXES = ("press:", "button:", "tap:", "press ", "button ", "tap ")


def parse_buttons(command: str) -> tuple[list[str], str | None]:
    """Turn an operator command into presses.

    Accepts a single button (``"up"``), a prefixed one (``"press:up"``) or a
    short sequence (``"up,up,a"`` / ``"down a"``). Returns ``(buttons, error)``
    where ``error`` names the first token that is not a button, so the loop can
    record a failure instead of raising through the thread.
    """
    text = (command or "").strip().lower()
    for prefix in _COMMAND_PREFIXES:
        if text.startswith(prefix):
            text = text[len(prefix) :].strip()
            break
    buttons: list[str] = []
    for token in (t for t in text.replace(",", " ").split() if t):
        if token not in VALID_BUTTONS:
            return buttons, f"unknown button {token!r} (valid: {sorted(VALID_BUTTONS)})"
        buttons.append(token)
    return buttons, None


class PlayLoopError(RuntimeError):
    """The play loop cannot start or has stopped for a reportable reason."""


class PlayLoop(Protocol):
    """What ``DashboardSession`` needs from a play loop (real or stub)."""

    def start(self) -> None: ...

    def stop(self) -> None: ...

    def pause(self) -> None: ...

    def resume(self) -> None: ...


class SessionSink(Protocol):
    """The session surface the loop writes progress through."""

    screenshot_manager: Any
    db: Any

    def update_tick(
        self, new_state: str | None = None, location: str | None = None
    ) -> None: ...

    def add_command(self, command: dict[str, Any]) -> None: ...

    def next_pending_command(self) -> dict[str, Any] | None: ...

    def record_loop_error(self, message: str) -> None: ...


def resolve_rom_path() -> Path:
    """ROM the dashboard plays: ``PTP_DASHBOARD_ROM`` or the repo's Blue ROM."""
    override = os.getenv("PTP_DASHBOARD_ROM")
    return Path(override).expanduser() if override else DEFAULT_ROM


def resolve_boot_state() -> Path | None:
    """Checkpoint to boot from, or ``None`` to A-mash through the intro.

    ``PTP_DASHBOARD_BOOT_STATE=skip`` disables checkpoint booting (the same
    spelling cron_runner.py uses); any other value is treated as a literal
    path. A configured-but-missing path falls back to the intro bypass rather
    than failing the start.
    """
    raw = os.getenv("PTP_DASHBOARD_BOOT_STATE")
    if raw is not None and raw.strip().lower() == "skip":
        return None
    candidate = Path(raw).expanduser() if raw else DEFAULT_BOOT_STATE
    return candidate if candidate.is_file() else None


class DashboardPlayLoop:
    """One emulator + RAM reader ticking in a thread, reporting to a session."""

    def __init__(
        self,
        session: SessionSink,
        *,
        rom_path: Path | None = None,
        boot_state: Path | None = None,
        frames_per_tick: int = DEFAULT_FRAMES_PER_TICK,
        tick_interval: float = DEFAULT_TICK_INTERVAL,
        screenshot_every: int = DEFAULT_SCREENSHOT_EVERY,
        press_every: int = DEFAULT_PRESS_EVERY,
    ) -> None:
        self.session = session
        self.rom_path = rom_path if rom_path is not None else resolve_rom_path()
        self.boot_state = boot_state if boot_state is not None else resolve_boot_state()
        self.frames_per_tick = max(1, frames_per_tick)
        self.tick_interval = max(0.0, tick_interval)
        self.screenshot_every = max(1, screenshot_every)
        self.press_every = max(1, press_every)

        self.error: str | None = None
        self._stop = threading.Event()
        self._paused = threading.Event()
        self._thread: threading.Thread | None = None
        self._press_index = 0

    # ── lifecycle ────────────────────────────────────────────────────

    @property
    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.is_alive:
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name=f"dashboard-play-loop-{getattr(self.session, 'session_id', 'session')}",
            daemon=True,
        )
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        thread = self._thread
        if (
            thread is not None
            and thread.is_alive()
            and thread is not threading.current_thread()
        ):
            thread.join(timeout)

    def pause(self) -> None:
        self._paused.set()

    def resume(self) -> None:
        self._paused.clear()

    # ── the loop ─────────────────────────────────────────────────────

    def _run(self) -> None:
        emulator: Any = None
        try:
            emulator, reader = self._boot()
            tick = 0
            while not self._stop.is_set():
                if self._paused.is_set():
                    self._stop.wait(0.1)
                    continue

                emulator.tick(frames=self.frames_per_tick)
                tick += 1
                location = self._read_location(reader)
                screen = reader.screen_type()

                # Operator input wins over the exploration cycle; checking every
                # tick is what makes the console feel like remote control
                # instead of a log of intentions.
                if not self._execute_pending(emulator):
                    if tick % self.press_every == 0:
                        self._press(emulator)
                if tick % self.screenshot_every == 0:
                    self._capture(emulator, tick, screen)

                # THE production call the defect was missing: only update_tick()
                # writes tick_count / location / last_action_time.
                self.session.update_tick(new_state=screen, location=location)

                if self.tick_interval:
                    time.sleep(self.tick_interval)
        except BaseException as exc:  # noqa: BLE001 - a dying loop must be visible
            self.error = f"{type(exc).__name__}: {exc}"
            self.session.record_loop_error(self.error)
        finally:
            if emulator is not None:
                try:
                    emulator.stop()
                except Exception as stop_exc:  # noqa: BLE001
                    print(
                        f"[dashboard] play loop: emulator stop failed: {stop_exc}",
                        file=sys.stderr,
                    )

    def _boot(self) -> tuple[Any, Any]:
        """Create the emulator + RAM reader and put the game in a real state."""
        if not self.rom_path.is_file():
            raise PlayLoopError(
                f"ROM not found: {self.rom_path} (set PTP_DASHBOARD_ROM to override)"
            )

        # Deferred like cron_runner.py's runtime imports: PyBoy/SDL cost is paid
        # by a started session, never by importing the dashboard.
        from src.core.emulator import Emulator
        from src.core.ram_reader import RAMReader

        emulator = Emulator(str(self.rom_path))
        if self.boot_state is not None:
            emulator.load_state(self.boot_state)
            emulator.wait(30)  # settle after the state restore
        else:
            emulator.bypass_title()
            emulator.skip_intro()
        return emulator, RAMReader(emulator, self.rom_path)

    @staticmethod
    def _read_location(reader: Any) -> str:
        """Location as the player would name it: map name plus tile coords."""
        return (
            f"{reader.current_map_name()} "
            f"({reader.player_tile_x()},{reader.player_tile_y()})"
        )

    def _press(self, emulator: Any) -> None:
        button = _BUTTON_CYCLE[self._press_index % len(_BUTTON_CYCLE)]
        self._press_index += 1
        emulator.press_button(button, frames=5)
        self.session.add_command(
            {
                "command": f"press:{button.upper()}",
                "reasoning": "dashboard play loop: deterministic exploration cycle",
                "confidence": 0.2,
                "success": True,
            }
        )

    def _execute_pending(self, emulator: Any) -> bool:
        """Run one queued operator command. ``True`` when input was applied."""
        pending = self.session.next_pending_command()
        if pending is None:
            return False

        raw = str(pending.get("command", ""))
        buttons, error = parse_buttons(raw)
        if error is None:
            for button in buttons:
                try:
                    emulator.press_button(button, frames=5)
                except ValueError as exc:  # emulator refused the button
                    error = str(exc)
                    break

        self.session.add_command(
            {
                "command": raw or "unknown",
                "reasoning": pending.get("reasoning", ""),
                "confidence": pending.get("confidence", 0.0),
                "success": error is None,
                "source": "operator",
                **({"error": error} if error else {}),
            }
        )
        return True

    def _capture(self, emulator: Any, tick: int, screen: str) -> None:
        screenshot = emulator.capture()
        path = self.session.screenshot_manager.save_screenshot(
            screenshot, f"tick_{tick}"
        )
        try:
            self.session.db.log_screenshot_event(
                {
                    "tick": tick,
                    "timestamp": datetime.now().isoformat(),
                    "path": str(path),
                    "game_state": {"screen_type": screen},
                }
            )
        except Exception as exc:  # noqa: BLE001 - observability, not gameplay
            # A logging failure must not stop the game. Surface it in the
            # server log instead of silently dropping it.
            print(
                f"[dashboard] play loop: screenshot log skipped: {exc}",
                file=sys.stderr,
            )
