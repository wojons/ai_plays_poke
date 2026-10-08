"""env/agent split increment 1 (CH-SPLIT): expose the emulator as an HTTP
environment service with a documented observe/act contract.

ADDITIVE ONLY — reuses ``src.core.emulator.Emulator`` and
``src.core.ram_reader.RAMReader`` as-is; cron_runner.py and src/core behavior
are untouched. Run from the repo root::

    uvicorn src.env_service:app --port 8765

Contract details: docs/api/env_service.md
"""

from __future__ import annotations

import base64
import io
import threading
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from PIL import Image
from pydantic import BaseModel, Field

from src.core.emulator import Emulator
from src.core.ram_reader import RAMReader

DEFAULT_ROM_PATH = "data/rom/Pokemon - Blue Version (USA, Europe) (SGB Enhanced).gb"
DEFAULT_BOOT_STATE = "data/boot.state"
DEFAULT_ACT_FRAMES = 8
MAX_ACT_FRAMES = 600
MAX_BUTTONS = 16

app = FastAPI(
    title="PTP-01X Environment Service",
    description="HTTP observe/act environment for Pokémon AI agents "
    "(CH-SPLIT increment 1).",
    version="0.1.0",
)

_lock = threading.Lock()
_emulator: Optional[Emulator] = None
_ram_reader: Optional[RAMReader] = None
_rom_path: str = ""
_boot_state: Optional[str] = None


# ── request / response models ────────────────────────────────────────────


class BootRequest(BaseModel):
    rom_path: str = Field(default=DEFAULT_ROM_PATH)
    boot_state: Optional[str] = Field(default=DEFAULT_BOOT_STATE)


class ActRequest(BaseModel):
    buttons: list[str] = Field(default_factory=list)
    frames: int = Field(default=DEFAULT_ACT_FRAMES, ge=1, le=MAX_ACT_FRAMES)


class Observation(BaseModel):
    """RAM-derived game state + last screenshot, base64-encoded PNG."""

    location: Optional[str] = None
    map_id: Optional[int] = None
    player_x: Optional[int] = None
    player_y: Optional[int] = None
    player_tile_x: Optional[int] = None
    player_tile_y: Optional[int] = None
    player_facing: Optional[str] = None
    screen_type: Optional[str] = None
    party_count: Optional[int] = None
    is_moving: Optional[bool] = None
    screenshot_base64: Optional[str] = None
    screenshot_format: str = "png"
    emulated_platform: str = "gb"


class ActResponse(BaseModel):
    pressed: list[str]
    frames: int
    observation: Observation


class HealthResponse(BaseModel):
    status: str
    booted: bool
    rom_path: Optional[str] = None
    boot_state: Optional[str] = None


# ── internals ────────────────────────────────────────────────────────────


def _require_emulator() -> tuple[Emulator, RAMReader]:
    if _emulator is None or _ram_reader is None:
        raise HTTPException(
            status_code=409,
            detail="Environment not booted. POST /env/boot first.",
        )
    return _emulator, _ram_reader


def _png_base64(emu: Emulator) -> str:
    frame = emu.capture()
    image = Image.fromarray(frame)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _safe_read(reader: RAMReader, attr: str) -> Any:
    try:
        return getattr(reader, attr)()
    except Exception:
        return None


def _build_observation() -> Observation:
    _, reader = _require_emulator()
    data: dict[str, Any] = {
        "location": _safe_read(reader, "current_map_name"),
        "map_id": _safe_read(reader, "current_map_id"),
        "player_x": _safe_read(reader, "player_x"),
        "player_y": _safe_read(reader, "player_y"),
        "player_tile_x": _safe_read(reader, "player_tile_x"),
        "player_tile_y": _safe_read(reader, "player_tile_y"),
        "player_facing": _safe_read(reader, "player_facing"),
        "screen_type": _safe_read(reader, "screen_type"),
        "party_count": _safe_read(reader, "party_count"),
        "is_moving": _safe_read(reader, "is_moving"),
    }
    data["screenshot_base64"] = _png_base64(_emulator)  # type: ignore[arg-type]
    return Observation(**data)


def _boot_locked(rom_path: str, boot_state: Optional[str]) -> None:
    global _emulator, _ram_reader, _rom_path, _boot_state
    _emulator = Emulator(rom_path)
    _ram_reader = RAMReader(_emulator, rom_path)
    _rom_path = rom_path
    _boot_state = boot_state
    if boot_state:
        _emulator.load_state(boot_state)
        _emulator.wait(30)  # settle after state restore (cron_runner parity)


# ── endpoints ────────────────────────────────────────────────────────────


@app.post("/env/boot", response_model=HealthResponse)
def boot(request: BootRequest) -> HealthResponse:
    """Boot a fresh PyBoy instance (optionally loading a boot checkpoint)."""
    with _lock:
        if _emulator is not None:
            raise HTTPException(
                status_code=409,
                detail="Environment already booted. POST /env/reset first.",
            )
        try:
            _boot_locked(request.rom_path, request.boot_state)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return HealthResponse(
            status="booted",
            booted=True,
            rom_path=_rom_path,
            boot_state=_boot_state,
        )


@app.get("/env/observe", response_model=Observation)
def observe() -> Observation:
    with _lock:
        return _build_observation()


@app.post("/env/act", response_model=ActResponse)
def act(request: ActRequest) -> ActResponse:
    if len(request.buttons) > MAX_BUTTONS:
        raise HTTPException(
            status_code=422,
            detail=f"Too many buttons in one act (max {MAX_BUTTONS}).",
        )
    with _lock:
        emu, _ = _require_emulator()
        for button in request.buttons:
            emu.press_button(button, frames=request.frames)
        if not request.buttons:
            emu.wait(request.frames)
        return ActResponse(
            pressed=request.buttons,
            frames=request.frames,
            observation=_build_observation(),
        )


@app.post("/env/reset", response_model=HealthResponse)
def reset() -> HealthResponse:
    """Reload the boot state in the live emulator instance."""
    with _lock:
        emu, _ = _require_emulator()
        if _boot_state:
            emu.load_state(_boot_state)
            emu.wait(30)  # settle after state restore (cron_runner parity)
        return HealthResponse(
            status="reset",
            booted=True,
            rom_path=_rom_path,
            boot_state=_boot_state,
        )


@app.get("/env/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok" if _emulator is not None else "idle",
        booted=_emulator is not None,
        rom_path=_rom_path or None,
        boot_state=_boot_state,
    )
