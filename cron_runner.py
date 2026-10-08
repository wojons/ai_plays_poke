#!/usr/bin/env python3
"""Cron-friendly Pokemon AI runner with RAM reader / cartographer → controller pipeline.

Flow:
  1. Observe game state (RAM reader OR Gemma 12B cartographer)
  2. If overworld: controller (openai/gpt-5.6-luna via OpenRouter) reads spatial data → button plan
  3. Execute plan with direction-locking detection, checkpoint rollback
  4. Non-overworld: existing StateWindow flow
"""

from __future__ import annotations

import builtins as _builtins

_original_print = _builtins.print


def safe_print(*args, **kwargs):
    """Print that survives broken stdout (piped background processes)."""
    try:
        _original_print(*args, **kwargs)
    except (BrokenPipeError, OSError):
        pass


import argparse
from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TextIO, cast
import sys
import os
import time
import json
import re
import traceback
import base64
import io
import hashlib
import threading
from pathlib import Path
from datetime import datetime, timezone

# ── Config constants (early) ─────────────────────────────────────────
# Defined before the heavy third-party imports (yaml/numpy/PIL/src.*) so
# the --dry-run precheck below can validate setup under bare python3 too.
ROM = "data/rom/Pokemon - Blue Version (USA, Europe) (SGB Enhanced).gb"
DEFAULT_BOOT_STATE = Path("data/boot.state")  # known-good overworld checkpoint
BOOT_STATE_ROM_TITLE = (
    "POKEMON BLUE"  # data/boot.state was saved from the Blue SGB ROM (GAP-037)
)
CYCLES = (
    20  # shared default with .coding-hermes/cron.sh (GAP-041); --cycles N overrides
)
USE_RAM_READER = True  # True = RAM-based state reader (instant, free), False = Gemma 12B cartographer

# ── Controller model (GAP-052) ──────────────────────────────────────
# The controller model is selectable: --controller-model beats
# CRON_CONTROLLER_MODEL beats POKE_CONTROLLER_MODEL (the GAP-049
# minimal env hook) beats DEFAULT_CONTROLLER_MODEL. The default is the
# original hardcoded string, so an invocation that passes neither flag
# nor env sends a byte-identical request to the client. Any '*deepseek*'
# model routes direct to api.deepseek.com via DEEPSEEK_API_KEY
# (src/core/ai_client.py) — the working escape hatch when OpenRouter is
# out of credit.
DEFAULT_CONTROLLER_MODEL = "openai/gpt-5.6-luna"
CONTROLLER_MODEL_ENV_VARS = ("CRON_CONTROLLER_MODEL", "POKE_CONTROLLER_MODEL")
CONTROLLER_MAX_TOKENS = 300  # controller completion budget
CONTROLLER_RETRY_TOKEN_BUMP = 100  # GAP-052(c): extra budget on the single parse retry


def _controller_model_override(
    flag_value: str | None = None,
) -> tuple[str, str] | None:
    """Return ``(model, source)`` for an explicit controller-model choice.

    ``None`` when neither the flag nor an env var supplies one (blank
    values count as unset, so ``--controller-model ""`` or an empty env
    var falls through instead of sending an empty model name).
    """
    if flag_value is not None and flag_value.strip():
        return flag_value.strip(), "flag --controller-model"
    for name in CONTROLLER_MODEL_ENV_VARS:
        value = os.environ.get(name)
        if value is not None and value.strip():
            return value.strip(), f"env {name}"
    return None


def resolve_controller_model(flag_value: str | None = None) -> str:
    """Resolve the controller model: flag > env > ``DEFAULT_CONTROLLER_MODEL``.

    Defined before the heavy imports so the --dry-run precheck can report
    the model the run would actually use (GAP-052).
    """
    override = _controller_model_override(flag_value)
    return override[0] if override is not None else DEFAULT_CONTROLLER_MODEL


# ── Decision mode: System One, System Two, or both ──────────────────
# The three families are first-class and selectable. The historical spellings
# keep their exact meaning, because every committed baseline, artifact and run
# log cites them ("jev" IS the hybrid; "llm" IS System Two alone).
#
#   "system1"          — the fast System-One tier decides EVERY eligible cycle
#                        and never hands back. This is the mode that measures
#                        the fast tier unaided, which is currently unknown.
#   "system2" (= "llm")— the controller decides EVERY cycle and JEV is never
#                        consulted (not even called). The pure-LLM benchmark.
#   "system1+system2"  — the fast tier decides and hands back to the reasoning
#      (= "jev")        teacher when a trigger fires AND the policy allows it.
#
# The handoff policy (--handoff ...) selects WHICH trigger families may hand
# back. "off" is exactly system1 — one mechanism, not two.
#
# Resolved flag > env > default, and stamped into every decision row so a run's
# mode AND its policy are recoverable from its log alone.
DEFAULT_DECISION_MODE = "jev"  # historical spelling; canonicalises to system1+system2
DECISION_MODE_ENV_VARS = ("AIPP_DECISION_MODE", "CRON_DECISION_MODE")

MODE_SYSTEM1 = "system1"
MODE_SYSTEM2 = "system2"
MODE_HYBRID = "system1+system2"

# Every accepted spelling -> the single canonical family it means.
DECISION_MODE_ALIASES: dict[str, str] = {
    "system1": MODE_SYSTEM1,
    "system2": MODE_SYSTEM2,
    MODE_HYBRID: MODE_HYBRID,
    "hybrid": MODE_HYBRID,
    "jev": MODE_HYBRID,  # historical: fast tier WITH the teacher on call
    "llm": MODE_SYSTEM2,  # historical pure-LLM spelling; now uses verified tools
    # Explicit spelling for the same bounded System-Two model→tool loop. Both
    # spellings remain distinct in decision rows for benchmark clarity.
    "agentic": MODE_SYSTEM2,
}
DECISION_MODES = tuple(DECISION_MODE_ALIASES)


def normalize_decision_mode(value: str | None) -> str | None:
    """Canonical SPELLING for a mode value, or ``None`` when unrecognised.

    Normalises case and whitespace only. It deliberately does NOT rewrite a
    legacy spelling into its family: the spelling is what gets stamped into
    every decision row, and it must stay byte-identical to the run logs already
    on disk (acceptance M6).
    """
    if not isinstance(value, str):
        return None
    text = value.strip().lower()
    return text if text in DECISION_MODE_ALIASES else None


def decision_mode_family(mode: str | None) -> str:
    """The System-One/System-Two family a mode spelling means.

    This is the value the branching reads; :func:`resolve_decision_mode` returns
    the spelling. Keeping the two separate is what lets the new names exist
    WITHOUT changing the stamped value of the old ones.
    """
    normalised = normalize_decision_mode(mode)
    return DECISION_MODE_ALIASES.get(normalised or "", MODE_HYBRID)


def current_mode_family() -> str:
    """The family of the module's CURRENT mode spelling.

    Branching calls this rather than reading a cached family, so assigning
    ``DECISION_MODE`` is sufficient to change behaviour. A second module-level
    family variable would be a footgun: two values that must be kept in sync,
    with a silent wrong branch whenever they drift.
    """
    return decision_mode_family(DECISION_MODE)


def _model_tools_enabled(mode: str | None) -> bool:
    """Whether this mode uses the verified model-tool surface.

    Both historical ``llm`` and explicit ``agentic`` are System-Two modes, as
    is the canonical ``system2`` spelling. JEV/hybrid remains byte-for-byte on
    its existing path with no tools.
    """
    return decision_mode_family(mode) == MODE_SYSTEM2


def resolve_decision_mode(flag_value: str | None = None) -> str:
    """Resolve the decision mode SPELLING: flag > env > ``DEFAULT_DECISION_MODE``.

    Returns the spelling as given, so ``--decision-mode jev`` still stamps
    ``decision_mode="jev"`` exactly as every existing run log does. Use
    :func:`decision_mode_family` for the branchable family.
    """
    candidates = [flag_value, *(os.environ.get(n) for n in DECISION_MODE_ENV_VARS)]
    for candidate in candidates:
        normalised = normalize_decision_mode(candidate)
        if normalised is not None:
            return normalised
    return normalize_decision_mode(DEFAULT_DECISION_MODE) or DEFAULT_DECISION_MODE


# ── Handoff policy: WHICH triggers may hand back to System Two ───────
# These three trigger families are exactly the ones
# ``jev_client.should_escalate()`` already fires. The policy selects among
# them; it never invents a trigger.
HANDOFF_FAILURE = "failure"
HANDOFF_GAP = "gap"
HANDOFF_CONFIDENCE = "confidence"
HANDOFF_ALL_FAMILIES = (HANDOFF_FAILURE, HANDOFF_GAP, HANDOFF_CONFIDENCE)
HANDOFF_CHOICES = ("off", "any", "failure", "gap", "confidence")

DEFAULT_HANDOFF = "any"
DEFAULT_HANDOFF_CONFIDENCE = 0.50  # mirrors jev_client.ESCALATE_THRESHOLD
DEFAULT_HANDOFF_AMBIGUITY = 0.40  # mirrors jev_client.AMBIGUITY_GATE
HANDOFF_ENV_VARS = ("AIPP_HANDOFF", "CRON_HANDOFF")


def classify_handoff_trigger(reason: str | None) -> str:
    """Map a ``should_escalate()`` reason string to its trigger family.

    The reason prefixes are the contract from ``jev_client.should_escalate()``.
    A reason this does not recognise classifies as "other" and is reported —
    it is never silently treated as "no trigger fired".
    """
    if not isinstance(reason, str) or not reason.strip():
        return "none"
    text = reason.strip().lower()
    if text.startswith("transport"):
        return "transport"
    if text.startswith("failure"):
        return HANDOFF_FAILURE
    if text.startswith("insufficient_state") or text.startswith("missing_class"):
        return HANDOFF_GAP
    if text.startswith("low_confidence"):
        return HANDOFF_CONFIDENCE
    return "other"


def resolve_handoff_families(value: str | None) -> frozenset[str]:
    """Parse a ``--handoff`` value into the trigger families allowed to fire."""
    raw = value
    if not isinstance(raw, str) or not raw.strip():
        raw = next(
            (os.environ.get(n) for n in HANDOFF_ENV_VARS if os.environ.get(n)), None
        )
    if not isinstance(raw, str) or not raw.strip():
        raw = DEFAULT_HANDOFF
    text = raw.strip().lower()
    if text == "off":
        return frozenset()
    if text in ("any", "all"):
        return frozenset(HANDOFF_ALL_FAMILIES)
    wanted = {p.strip() for p in text.replace("+", ",").split(",") if p.strip()}
    if wanted & {"all", "any"}:
        return frozenset(HANDOFF_ALL_FAMILIES)
    return frozenset(wanted & set(HANDOFF_ALL_FAMILIES))


def build_handoff_policy(
    *,
    handoff: str | None = None,
    confidence: float | None = None,
    ambiguity: float | None = None,
    classes: str | None = None,
    teacher_max: int | None = None,
) -> dict[str, Any]:
    """The effective handoff policy for a run, stamped into its log.

    Defaults deliberately mirror the thresholds already in code
    (``0.50`` / ``0.40``): changing a default would invalidate every committed
    baseline, so the policy starts as a no-op on the existing behaviour.
    """
    families = resolve_handoff_families(handoff)
    allow: frozenset[str] | None = None
    if isinstance(classes, str) and classes.strip():
        allow = frozenset(
            p.strip() for p in classes.replace(";", ",").split(",") if p.strip()
        )
    return {
        "families": sorted(families),
        "classes": sorted(allow) if allow else None,
        "confidence": (
            float(confidence) if confidence is not None else DEFAULT_HANDOFF_CONFIDENCE
        ),
        "ambiguity": (
            float(ambiguity) if ambiguity is not None else DEFAULT_HANDOFF_AMBIGUITY
        ),
        "teacher_max_per_episode": int(teacher_max) if teacher_max else None,
    }


def handoff_allowed(
    policy: dict[str, Any], trigger: str, missing_class: str | None
) -> tuple[bool, str]:
    """May this trigger hand back under this policy? Returns (allowed, why)."""
    if trigger == "transport":
        # Availability, not policy: an unanswered fast tier must degrade to the
        # controller or the cycle cannot proceed. This check comes FIRST —
        # ahead of the empty-families test — because --handoff off must not be
        # able to wedge a run by suppressing the failover that keeps it moving.
        return True, "transport failover (not policy-gated)"
    families = set(policy.get("families") or ())
    if not families:
        return False, "handoff off (system1)"
    if trigger not in families:
        return False, f"trigger {trigger!r} not in {sorted(families)}"
    allow = policy.get("classes")
    if allow and missing_class and missing_class not in allow:
        return False, f"missing_class {missing_class!r} not in {sorted(allow)}"
    return True, "allowed"


# Module-level so the run loop and the row writers can stamp it; main()
# re-resolves from the flags once the argument parser has run.
DECISION_MODE = resolve_decision_mode()
HANDOFF_POLICY = build_handoff_policy()


# ── --dry-run precheck (GAP-032) ────────────────────────────────────
# Lightweight argparse pass that runs BEFORE yaml/numpy/PIL/src.* are
# imported, so `--dry-run` validates setup without booting the emulator
# or spending LLM calls — even under bare python3 (stdlib only).
#
# GAP-048: presence is not liveness. An expired OPENROUTER_API_KEY used
# to print "OPENROUTER_API_KEY=set" and exit 0, then 401 on every real
# call. The precheck now probes each CONFIGURED key over stdlib urllib
# (still no third-party import) and exits non-zero with the provider's
# verbatim error when a key is dead; --skip-key-check restores the old
# presence-only, offline behavior.


def _load_dotenv_stdlib(env_path: Path | None = None) -> None:
    """Minimal stdlib .env loader (mirrors src/core/ai_client.py's fallback).

    Lets --dry-run report API-key presence from the real setup without
    importing python-dotenv or any project package.
    """
    path = env_path if env_path is not None else Path(".env")
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("\"'")
        if key and value and not os.environ.get(key):
            os.environ[key] = value


def _read_rom_header_title(rom_path: str) -> str | None:
    """Return the Gen-1 ROM header title (offset 0x134, 16 bytes, null-stripped).

    Returns ``None`` when the file is unreadable or too short to hold a
    header — callers treat that as "unknown, don't warn".
    """
    try:
        with open(rom_path, "rb") as f:
            f.seek(0x134)
            raw = f.read(16)
    except OSError:
        return None
    if len(raw) < 16:
        return None
    return raw.split(b"\x00", 1)[0].decode("ascii", errors="replace")


def _warn_boot_state_rom_mismatch(
    run_id: str,
    boot_path: Path | None,
    rom_path: str | None = None,
) -> None:
    """Warn when a boot checkpoint saved from the Blue ROM is loaded into a non-Blue ROM.

    data/boot.state is a PyBoy savestate captured from the Blue SGB ROM
    (starter already picked). PyBoy's ``load_state`` restores memory
    blindly — it never validates that the savestate matches the loaded
    cartridge — so booting a Blue checkpoint into e.g. pokemon_red.gb
    yields garbage RAM with zero errors. GAP-037: surface that here, in
    both the real boot path and the --dry-run pre-flight. No-op when the
    checkpoint is skipped (``boot_path is None``), the ROM title is
    unreadable, or the ROM is Blue (matching ``BOOT_STATE_ROM_TITLE``).
    """
    if boot_path is None:
        return
    rom = rom_path if rom_path is not None else ROM
    title = _read_rom_header_title(rom)
    if title is None or title == BOOT_STATE_ROM_TITLE:
        return
    safe_print(
        f"[{run_id}] WARNING: {boot_path} was saved from the Blue ROM "
        f"({BOOT_STATE_ROM_TITLE}) but --rom is {title} — loading a mismatched "
        f"checkpoint yields garbage state; use --boot-state skip for non-Blue ROMs"
    )


# ── API-key liveness probes (GAP-048) ───────────────────────────────
# Pre-GAP-048 the dry-run reported key PRESENCE only, so an expired key
# still printed "OPENROUTER_API_KEY=set" and exited 0 — the user then
# burned a dead 20-cycle run on 401s. These probes stay in the
# import-light path (stdlib urllib, imported lazily inside the probe):
# HTTP 200 = live, anything else = dead, surfacing the provider's own
# error text verbatim (e.g. "API key expired").

_PROBE_TIMEOUT_SECONDS = 10.0

# Only keys with a cheap, read-only status endpoint are probed. Keys that
# are unset are never probed, so a key-less setup behaves as before.
_KEY_PROBE_URLS: dict[str, str] = {
    "OPENROUTER_API_KEY": "https://openrouter.ai/api/v1/key",
    "DEEPSEEK_API_KEY": "https://api.deepseek.com/models",
}


def _extract_provider_error(body: str, status: int) -> str:
    """Return the provider's verbatim error message from a non-200 response.

    OpenRouter answers 401 with ``{"error": {"message": "API key expired"}}``.
    Falls back to a bare ``message`` field, then the raw body, then the status
    code — never invents text, so the user sees exactly what the provider said.
    """
    try:
        payload: Any = json.loads(body)
    except (ValueError, TypeError):
        payload = None
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            if isinstance(message, str) and message.strip():
                return message.strip()
        if isinstance(error, str) and error.strip():
            return error.strip()
        message = payload.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
    text = body.strip()
    if text:
        return text[:300]
    return f"HTTP {status}"


def _probe_api_key(
    _name: str,
    url: str,
    key: str,
    timeout: float = _PROBE_TIMEOUT_SECONDS,
) -> tuple[bool, str]:
    """Probe one configured provider key; return ``(live, message)`` (GAP-048).

    GETs ``url`` with ``Bearer <key>`` and treats HTTP 200 as live. A non-200
    response returns the provider's verbatim error; a network failure (DNS, no
    route, timeout) returns the urllib error text. Either way the key value
    itself is never printed. Stdlib ``urllib`` only — no new dependency.
    """
    import urllib.error
    import urllib.request

    request = urllib.request.Request(  # noqa: S310 -- URL is from fixed HTTPS map.
        url, headers={"Authorization": f"Bearer {key}"}, method="GET"
    )
    try:
        # Only fixed provider endpoints reach this bounded request.
        with urllib.request.urlopen(  # noqa: S310  # nosec B310
            request, timeout=timeout
        ) as response:
            status = int(getattr(response, "status", 200))
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        try:
            raw = exc.read().decode("utf-8", errors="replace")
        except Exception:  # pragma: no cover - unreadable error body
            raw = ""
        return False, _extract_provider_error(raw, exc.code)
    except Exception as exc:  # URLError (DNS/route/TLS) or a socket timeout
        return False, str(exc) or exc.__class__.__name__
    if status == 200:
        return True, ""
    return False, _extract_provider_error(body, status)


def _check_configured_keys(skip: bool) -> list[tuple[str, str]]:
    """Probe every CONFIGURED key and report the dead ones (GAP-048).

    Returns ``[(key_name, verbatim_error), ...]`` for dead keys — empty when
    every configured key is live, none is configured (no probes at all), or
    the probes were skipped for offline validation.
    """
    if skip:
        safe_print("  Key liveness:   skipped (--skip-key-check)")
        return []
    configured = [name for name in _KEY_PROBE_URLS if os.environ.get(name)]
    if not configured:
        safe_print("  Key liveness:   no configured keys to probe")
        return []
    dead: list[tuple[str, str]] = []
    for name in configured:
        live, message = _probe_api_key(name, _KEY_PROBE_URLS[name], os.environ[name])
        if live:
            safe_print(f"  Key liveness:   {name} live")
        else:
            safe_print(f"  Key liveness:   {name} DEAD — {message}")
            dead.append((name, message))
    return dead


def _dry_run_summary(
    run_id_arg: str | None,
    cycles: int,
    boot_state_arg: str | None,
    rom_arg: str | None = None,
    *,
    skip_key_check: bool = False,
    controller_model: str | None = None,
) -> int:
    """Validate ROM/boot-state paths and print the pipeline config summary.

    Shared by the early precheck (import time, before heavy imports) and
    main() (defensive — the precheck normally exits first). Returns 0 when the
    setup validates; 1 when the ROM is missing (a real run would crash at boot)
    or any CONFIGURED API key fails its liveness probe (GAP-048). Never boots
    the emulator and never spends an LLM completion; the only network I/O is
    the key-liveness GET, which ``skip_key_check`` turns off entirely.

    ``controller_model`` is the raw ``--controller-model`` value (GAP-052); the
    reported model is the resolved one, and the line stays byte-identical to
    the pre-GAP-052 text when neither flag nor env supplies an override.
    """
    _load_dotenv_stdlib()
    rom = rom_arg if rom_arg is not None else ROM  # resolved ROM (GAP-033 --rom)
    rom_ok = Path(rom).is_file()
    if boot_state_arg is None:
        boot_path = DEFAULT_BOOT_STATE
    elif boot_state_arg.lower() == "skip":
        boot_path = None
    else:
        boot_path = Path(boot_state_arg)
    safe_print(
        "[DRY-RUN] cron_runner.py — setup validation "
        "(no emulator boot, no LLM completions)"
    )
    safe_print(f"  ROM path:       {rom}  [{'OK' if rom_ok else 'MISSING'}]")
    if boot_path is None:
        safe_print("  Boot state:     skip (legacy intro bypass)")
    else:
        boot_ok = boot_path.is_file()
        fallback = (
            "will boot from checkpoint"
            if boot_ok
            else "missing — will fall back to intro bypass"
        )
        safe_print(
            f"  Boot state:     {boot_path}  "
            f"[{'OK' if boot_ok else 'MISSING — fallback'}] ({fallback})"
        )
    _warn_boot_state_rom_mismatch(
        run_id_arg or time.strftime("%Y%m%d_%H%M%S"), boot_path, rom
    )
    safe_print(f"  Cycles:         {cycles}")
    safe_print(f"  Run ID:         {run_id_arg or time.strftime('%Y%m%d_%H%M%S')}")
    safe_print(
        f"  Pipeline:       {'RAM reader' if USE_RAM_READER else 'cartographer'} "
        f"(USE_RAM_READER={USE_RAM_READER!r})"
    )
    # GAP-052: report the controller model the run would actually use. The
    # no-override form is byte-identical to the pre-GAP-052 line.
    _ctrl_override = _controller_model_override(controller_model)
    _ctrl_model = resolve_controller_model(controller_model)
    if _ctrl_override is None:
        _ctrl_seg = f"controller={_ctrl_model} (OpenRouter)"
    else:
        _ctrl_seg = (
            f"controller={_ctrl_override[0]} ({_ctrl_override[1]}; "
            "*deepseek* models route direct to api.deepseek.com)"
        )
    safe_print(
        f"  Model/provider: {_ctrl_seg} · "
        "state_window=deepseek-v4-flash (api.deepseek.com when DEEPSEEK_API_KEY "
        "set, else OpenRouter) · cartographer=google/gemma-3-12b-it (only when "
        "USE_RAM_READER=False)"
    )
    key_states = " · ".join(
        f"{k}={'set' if os.environ.get(k) else 'not set'}"
        for k in ("OPENROUTER_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY")
    )
    safe_print(f"  API keys:       {key_states}")
    dead_keys = _check_configured_keys(skip_key_check)
    errors: list[str] = []
    if not rom_ok:
        errors.append(
            f"ROM not found at {rom} — a real run would crash at boot. "
            f"Fix: you must own the game; place your own dump at {rom}."
        )
    errors.extend(f"{name} is dead — {message}" for name, message in dead_keys)
    for message in errors:
        safe_print(f"[DRY-RUN] ERROR: {message}")
    if errors:
        return 1
    safe_print("[DRY-RUN] Validation OK — exiting 0.")
    return 0


def _dry_run_precheck(argv: list[str] | None = None) -> None:
    """Handle --dry-run at import time, before heavy third-party imports.

    Lightweight argparse pass that only knows the flags --dry-run needs.
    Exits 0 (or 1 on a missing ROM / dead configured API key) when
    --dry-run is present; otherwise returns and normal execution proceeds.
    Malformed values are left for the real parser in main() to report.
    """
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-key-check", action="store_true")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--cycles", type=int, default=CYCLES)
    parser.add_argument("--boot-state", default=None)
    parser.add_argument("--rom", default=None)
    parser.add_argument("--controller-model", default=None)
    try:
        args, _ = parser.parse_known_args(argv)
    except SystemExit:
        return
    if not args.dry_run:
        return
    sys.exit(
        _dry_run_summary(
            args.run_id,
            args.cycles,
            args.boot_state,
            args.rom,
            skip_key_check=args.skip_key_check,
            controller_model=args.controller_model,
        )
    )


if TYPE_CHECKING:
    import numpy as np
    from PIL import Image

    from src.core.agentic_loop import BoundedAgentContext
    from src.core.ai_client import OpenRouterClient
    from src.core.ram_reader import RAMReader


# ── Suppress emulator SGB warnings ──────────────────────────────────
# mGBA core prints "GB: Unimplemented SGB command: 0F" to stderr when
# running SGB-enhanced ROMs. These are harmless noise in cron runs.
class _SGBSuppress:
    """Context manager that filters SGB warnings from stderr.

    GAMEPLAY-LEAK-001 fix: the original implementation (a) wrote non-SGB
    lines back through the ``sys.stderr`` file object, whose fd was
    already dup2'd to this class's own pipe — so filtered lines re-entered
    the pipe and looped forever, growing an unbounded ``_buf`` at
    70-100 MB/s; and (b) split lines at 4096-byte read boundaries, so
    truncated ``Unimplemented SGB`` lines bypassed the filter and fed the
    loop. Now: writes go to the dup'd original stderr fd (no loop),
    partial lines are carried across reads (no bypass), and ``_buf`` is a
    bounded debug tail.
    """

    _MAX_BUF_LINES = 200

    def __init__(self) -> None:
        # These get set in __enter__
        self._real_stderr = sys.stderr
        self._real_stderr_fd = -1
        self._pipe_r = -1
        self._pipe_w = -1
        self._thread: threading.Thread | None = None
        self._buf: list[str] = []

    def __enter__(self) -> "_SGBSuppress":
        self._pipe_r, self._pipe_w = os.pipe()
        self._real_stderr_fd = os.dup(2)
        os.dup2(self._pipe_w, 2)
        os.close(self._pipe_w)
        self._buf = []

        def _filter() -> None:
            pending = ""  # incomplete line carried across read boundaries
            while True:
                data = os.read(self._pipe_r, 4096)
                if not data:
                    break
                pending += data.decode(errors="replace")
                lines = pending.split("\n")
                pending = lines.pop()  # last element is an incomplete tail
                for line in lines:
                    if not line or "Unimplemented SGB" in line:
                        continue  # drop SGB noise (even truncated fragments)
                    if len(self._buf) < self._MAX_BUF_LINES:
                        self._buf.append(line)
                    # Write to the dup'd ORIGINAL stderr fd, never fd 2
                    # (fd 2 is this class's own pipe — writing there would
                    # feed the feedback loop).
                    try:
                        os.write(
                            self._real_stderr_fd,
                            line.encode(errors="replace") + b"\n",
                        )
                    except OSError:
                        pass

        self._thread = threading.Thread(target=_filter, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *args: object) -> None:
        os.dup2(self._real_stderr_fd, 2)
        os.close(self._real_stderr_fd)
        if self._pipe_r:
            os.close(self._pipe_r)
        # thread is daemon — will exit on its own


sys.path.insert(0, str(Path(__file__).parent))
# ruff: noqa: E402 — sys.path must be modified before project imports
from src.core import jev_client
from src.core import state_projection
from src.core.prompt_loader import load_system_prompt
from src.core.tools import execute_tool_call

# Repository-owned, schema-versioned teacher promotions. Missing files load as
# an empty set, preserving the pre-JEV-3 decision path in unseeded checkouts.
DEFAULT_JEV_SCENARIO_PATH = (
    Path(__file__).resolve().parent / "config" / "jev_promoted_patches.json"
)

# ── Config ──────────────────────────────────────────────────────────
# ROM / DEFAULT_BOOT_STATE / CYCLES / USE_RAM_READER are defined at the
# top of the file (before the heavy imports) so the --dry-run precheck
# (GAP-032) can validate setup under bare python3.
STATE_STEPS = 12
USE_VISION_CLIENT = (
    False  # True = debug mode (cheap classifier), False = Gemma 12B cartographer
)
HINT_LEVEL = 4  # 0=benchmark, 1=mechanics, 2=genre, 3=starter, 4=navigation
FAST_FORWARD_FRAMES = 600  # ~10s game time, ~50ms wall time
CART_STEPS = 6  # controller steps per overworld cycle (reduced from 12 — short moves, more cartographer feedback)
PRESS_FRAMES = 5  # one deliberate D-pad/button press (roughly one tile)
# Fixed settle for non-direction buttons. Directional movement uses the bounded,
# RAM-stabilized settle below: live Blue-ROM probes measured floor/grass commits
# at 17 frames total, a turn at 19, and a two-tile ledge hop at 36.
STEP_FORWARD = 15
STEP_SETTLE_MAX_FRAMES = 40  # post-press bound; 45 frames total with PRESS_FRAMES
STEP_SETTLE_STABLE_FRAMES = 4  # exceeds the ledge hop's 2-frame midpoint pause
LOG_DIR = Path("cron_logs")
LOG_DIR.mkdir(exist_ok=True)
run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
log_path = LOG_DIR / f"run_{run_id}.jsonl"
SCREENSHOT_DIR = Path("screenshots") / f"run_{run_id}"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

# ── Checkpointing ───────────────────────────────────────────────────
CHECKPOINT_INTERVAL = 10  # save state every N cycles
CHECKPOINT_SLOTS = 5  # rotating slots 0-4
MAX_SAME_DIRECTION = 5  # blocked-direction threshold before rollback (legacy)

# ── Recovery (STUCK-RECOVER) ──────────────────────────────────────
MAX_RECOVERY_ATTEMPTS = 5  # total recovery escalations before giving up
MAX_SAME_SCREEN_CYCLES = 5  # same screen for N cycles → stuck
MAX_SAME_TILE_CYCLES = 8  # same RAM tile across any screen types → stuck
MAX_VOID_CYCLES = 3  # >95% unknown-tile cycles → void
MAX_STUCK_SAME_DIR = 4  # same direction N times → direction-locked
MAX_SAME_FRAME_CYCLES = (
    8  # pixel-identical screen N cycles → frame-locked (catches dialog loops)
)
# Post-exhaustion movement injection: never passively A-mash after giving up
_GIVEUP_SEQUENCE = ("UP", "LEFT", "DOWN", "RIGHT", "START", "B")
OAKS_LAB_MAP_ID = 40
STARTER_ACTION_FRAMES = 20
STARTER_ADVANCE_FRAMES = 120
# Opposite direction map for step-back recovery
_OPPOSITE_DIR = {"UP": "DOWN", "DOWN": "UP", "LEFT": "RIGHT", "RIGHT": "LEFT"}
# Direction rotation map for alternate-direction recovery (90° clockwise)
_DIR_ROTATION = {"UP": "RIGHT", "RIGHT": "DOWN", "DOWN": "LEFT", "LEFT": "UP"}

# ── Visual-reference cartographer assets (loaded only for real vision runs) ──
CARTOGRAPHER_SYSTEM = ""
CARTOGRAPHER_TEMPLATE = ""
REFERENCE_IMAGE_B64 = ""


def _load_cartographer_assets() -> None:
    """Load the optional vision prompt and reference image after preflight."""
    global CARTOGRAPHER_SYSTEM, CARTOGRAPHER_TEMPLATE, REFERENCE_IMAGE_B64

    import yaml
    from PIL import Image

    carto_cfg = yaml.safe_load(
        Path("configs/prompts/gen1/cartographer.yaml").read_text()
    )
    CARTOGRAPHER_SYSTEM = carto_cfg["system"]
    CARTOGRAPHER_TEMPLATE = carto_cfg["user_template"]

    reference_image = Image.open("reference/bedroom_overworld.png")
    reference_buffer = io.BytesIO()
    reference_image.save(reference_buffer, format="PNG")
    REFERENCE_IMAGE_B64 = base64.b64encode(reference_buffer.getvalue()).decode()


# ── Helpers ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class _RecoveryTrackers:
    same_dir: str | None
    same_dir_count: int
    same_screen_count: int
    same_tile_count: int
    void_cycles: int
    a_press_count: int


@dataclass
class _NavigationHoldState:
    """Run-local map memory that prevents an achieved transition from regressing.

    A map transition is an edge with a direction.  Once the player crosses a
    previously-unseen edge, the reverse direction remains guarded for every
    later cycle on the destination map.  The state also owns the persistent
    navigation goal injected into both decision paths.
    """

    current_map_id: int | None = None
    current_map_name: str = ""
    previous_map_id: int | None = None
    previous_map_name: str = ""
    entry_direction: str = ""
    blocked_return_direction: str = ""
    goal: str = ""
    visited_maps: tuple[tuple[int, str], ...] = ()

    def observe(
        self,
        map_id: int,
        map_name: str,
        last_direction: str,
    ) -> dict[str, Any] | None:
        """Remember one map observation and return a transition log row if changed."""
        if map_id < 0:
            return None
        normalized_name = map_name or f"Map_{map_id:02X}"
        if self.current_map_id is None:
            self.current_map_id = map_id
            self.current_map_name = normalized_name
            self.visited_maps = ((map_id, normalized_name),)
            return None
        if map_id == self.current_map_id:
            self.current_map_name = normalized_name
            return None

        source_id = self.current_map_id
        source_name = self.current_map_name
        direction = last_direction.upper()
        if direction not in _OPPOSITE_DIR:
            direction = ""
        already_visited = any(seen_id == map_id for seen_id, _ in self.visited_maps)

        self.previous_map_id = source_id
        self.previous_map_name = source_name
        self.current_map_id = map_id
        self.current_map_name = normalized_name
        if not already_visited:
            self.visited_maps = (*self.visited_maps, (map_id, normalized_name))
            self.entry_direction = direction
            self.blocked_return_direction = _OPPOSITE_DIR.get(direction, "")
            self.goal = (
                f"Advance through {normalized_name} toward the next new map; "
                f"do not return to {source_name}. The {source_name} edge is already completed."
            )
        else:
            # The observation itself proves a regression already happened. Do
            # not turn that old map into the new held destination; keep the goal
            # pointed at the map from which progress was lost.
            self.entry_direction = ""
            self.blocked_return_direction = ""
            self.goal = f"Return to {source_name}; entering {normalized_name} again was a regression."

        return {
            "event": "navigation_transition",
            "from_map_id": source_id,
            "from_map_name": source_name,
            "to_map_id": map_id,
            "to_map_name": normalized_name,
            "crossing_direction": direction or None,
            "blocked_return_direction": self.blocked_return_direction or None,
            "regression": already_visited,
            "persistent_goal": self.goal,
            "visited_maps": [name for _, name in self.visited_maps],
            "mechanism": "visited_map_edge_memory",
        }

    def context(self) -> dict[str, Any]:
        """Return the bounded decision/log projection of the held edge."""
        return {
            "active": bool(self.blocked_return_direction),
            "current_map_id": self.current_map_id,
            "current_map_name": self.current_map_name,
            "previous_map_id": self.previous_map_id,
            "previous_map_name": self.previous_map_name,
            "entry_direction": self.entry_direction,
            "blocked_return_direction": self.blocked_return_direction,
            "visited_maps": [name for _, name in self.visited_maps],
            "goal": self.goal,
        }


def _guard_navigation_plan(
    plan: list[str], navigation: dict[str, Any] | None
) -> tuple[list[str], dict[str, Any] | None]:
    """Replace actions that would traverse the held map edge in reverse."""
    original = [str(button).upper() for button in plan]
    if not isinstance(navigation, dict) or not navigation.get("active"):
        return original, None
    blocked = str(navigation.get("blocked_return_direction") or "").upper()
    forward = str(navigation.get("entry_direction") or "").upper()
    if blocked not in _OPPOSITE_DIR or forward not in _OPPOSITE_DIR:
        return original, None

    guarded = [forward if button == blocked else button for button in original]
    if guarded == original:
        return original, None
    event = {
        "mechanism": "reverse_edge_guard",
        "reason": (
            f"{blocked} reverses the completed transition from "
            f"{navigation.get('previous_map_name')} to {navigation.get('current_map_name')}"
        ),
        "from_map_id": navigation.get("previous_map_id"),
        "from_map_name": navigation.get("previous_map_name"),
        "to_map_id": navigation.get("current_map_id"),
        "to_map_name": navigation.get("current_map_name"),
        "blocked_direction": blocked,
        "replacement_direction": forward,
        "original_plan": original,
        "guarded_plan": guarded,
        "persistent_goal": navigation.get("goal"),
        "visited_maps": list(navigation.get("visited_maps") or []),
    }
    return guarded, event


def _apply_navigation_hold_to_decision(
    decision: dict[str, Any], spatial_desc: dict[str, Any]
) -> dict[str, Any]:
    """Apply the spatially-projected hold to one controller decision."""
    raw_plan = decision.get("plan")
    if not isinstance(raw_plan, list):
        return decision
    guarded, event = _guard_navigation_plan(
        raw_plan,
        spatial_desc.get("navigation_hold"),
    )
    if event is None:
        return decision
    return {**decision, "plan": guarded, "navigation_hold_event": event}


def _reset_recovery_trackers(
    recovery_reason: str,
    *,
    same_dir: str | None,
    same_dir_count: int,
    same_screen_count: int,
    same_tile_count: int,
    void_cycles: int,
    a_press_count: int,
) -> _RecoveryTrackers:
    """Clear the tracker that fired, including A presses after any recovery."""
    _ = a_press_count
    if "direction-locked" in recovery_reason:
        same_dir = None
        same_dir_count = 0
    elif "screen-locked" in recovery_reason:
        same_screen_count = 0
    elif "tile-locked" in recovery_reason:
        same_tile_count = 0
    elif "void-locked" in recovery_reason:
        void_cycles = 0

    return _RecoveryTrackers(
        same_dir=same_dir,
        same_dir_count=same_dir_count,
        same_screen_count=same_screen_count,
        same_tile_count=same_tile_count,
        void_cycles=void_cycles,
        a_press_count=0,
    )


def _track_same_tile(
    current_tile: tuple[int, int, int] | None,
    last_tile: tuple[int, int, int] | None,
    same_tile_count: int,
) -> tuple[tuple[int, int, int] | None, int]:
    """Track a RAM map/tile tuple without considering the screen type."""
    if current_tile is None:
        return None, 0
    if current_tile == last_tile:
        return current_tile, same_tile_count + 1
    return current_tile, 1


def _movement_progress_delta(
    current_tile: tuple[int, int, int] | None,
    last_tile: tuple[int, int, int] | None,
) -> tuple[int, int]:
    """Return changed/observable counts for one consecutive cycle pair.

    A decision or button press is not movement. Only two consecutive valid RAM
    tile observations create a comparable cycle, and only a changed map/tile
    tuple counts as movement progress.
    """
    if current_tile is None or last_tile is None:
        return 0, 0
    return (int(current_tile != last_tile), 1)


def _read_player_tile(ram_reader: RAMReader) -> tuple[int, int, int] | None:
    """Return one valid RAM map/tile sample, or ``None`` if it is incomplete."""
    try:
        map_id = ram_reader.current_map_id()
        tile_x = ram_reader.player_tile_x()
        tile_y = ram_reader.player_tile_y()
    except AttributeError:
        # Lightweight test/replay readers predate the movement-RAM surface.
        return None
    if not all(isinstance(value, int) for value in (map_id, tile_x, tile_y)):
        return None
    return map_id, tile_x, tile_y


def _settle_directional_step(
    emu: Any,
    ram_reader: RAMReader,
    *,
    max_frames: int = STEP_SETTLE_MAX_FRAMES,
    stable_frames: int = STEP_SETTLE_STABLE_FRAMES,
) -> tuple[int, int, int] | None:
    """Advance until a directional move has a stable, non-moving RAM tile.

    Gen I ledge hops are two linked tile movements. At the measured midpoint,
    ``wWalkCounter`` is zero for two frames and the coordinates name the ledge
    tile, even though the hop has not committed. Requiring a longer stable run
    prevents that transient tile from becoming movement/recovery ground truth.
    The loop is bounded so malformed RAM cannot stall the runner.
    """
    stable_tile: tuple[int, int, int] | None = None
    stable_count = 0
    last_tile: tuple[int, int, int] | None = None

    frame_limit = max(0, max_frames)
    for elapsed_frames in range(1, frame_limit + 1):
        emu.fast_forward(1)
        current_tile = _read_player_tile(ram_reader)
        if current_tile is None:
            # Preserve the historical fixed settle for readers that cannot
            # expose movement RAM, without exceeding the caller's bound.
            fallback_frames = min(frame_limit, STEP_FORWARD) - elapsed_frames
            if fallback_frames > 0:
                emu.fast_forward(fallback_frames)
            return None
        last_tile = current_tile or last_tile
        if current_tile is not None and not ram_reader.is_moving():
            if current_tile == stable_tile:
                stable_count += 1
            else:
                stable_tile = current_tile
                stable_count = 1
            if stable_count >= max(1, stable_frames):
                return current_tile
        else:
            stable_tile = None
            stable_count = 0

    return last_tile


def _tile_lock_reason(tile: tuple[int, int, int] | None, same_tile_count: int) -> str:
    """Return the recovery reason for a tile streak at the configured limit."""
    if tile is None or same_tile_count < MAX_SAME_TILE_CYCLES:
        return ""
    map_id, tile_x, tile_y = tile
    return f"tile-locked (map {map_id} @ ({tile_x},{tile_y}) x{same_tile_count} cycles)"


def _should_select_starter(
    *,
    map_id: int,
    party_count: int,
    screen_type: str,
    menu_state: dict[str, Any],
) -> bool:
    """Return whether Oak's empty-party menu needs a JEV starter decision."""
    menu_detected = int(menu_state.get("menu_id", 0)) > 0 or screen_type in (
        "menu",
        "list_menu",
    )
    return map_id == OAKS_LAB_MAP_ID and party_count == 0 and menu_detected


def _approach_first_starter(
    emu: Any,
    ram_reader: RAMReader,
    *,
    max_dialog_advances: int = 12,
) -> bool:
    """Leave Oak's tile loop and interact with the nearest starter ball."""
    # A just-triggered interaction can still look like overworld for a few
    # frames; settle before deciding whether movement is controllable.
    emu.fast_forward(STARTER_ADVANCE_FRAMES)
    screen_type = ram_reader.screen_type()
    if screen_type != "overworld":
        for _ in range(max_dialog_advances):
            emu.press_button("a", frames=STARTER_ACTION_FRAMES)
            emu.fast_forward(STARTER_ADVANCE_FRAMES)
            screen_type = ram_reader.screen_type()
            if screen_type == "overworld":
                break
    if screen_type != "overworld":
        return False

    tile_x = ram_reader.player_tile_x()
    tile_y = ram_reader.player_tile_y()
    moves: list[str] = []
    moves.extend(["down"] * max(0, 4 - tile_y))
    moves.extend(["up"] * max(0, tile_y - 4))
    moves.extend(["right"] * max(0, 6 - tile_x))
    moves.extend(["left"] * max(0, tile_x - 6))
    if len(moves) > 12:
        return False

    for button in moves:
        emu.press_button(button, frames=PRESS_FRAMES)
        _settle_directional_step(emu, ram_reader)
    emu.press_button("up", frames=PRESS_FRAMES)
    _settle_directional_step(emu, ram_reader)
    emu.press_button("a", frames=STARTER_ACTION_FRAMES)
    emu.fast_forward(STARTER_ADVANCE_FRAMES)

    # Do not return control to the generic controller during transient overworld
    # frames: an A-heavy plan can race straight through the YES/NO prompt.
    # Advance only until the starter choice is visibly active, then let the JEV
    # species branch decide whether to confirm this ball or move to another.
    for _ in range(max_dialog_advances):
        current_screen = ram_reader.screen_type()
        current_menu = ram_reader.read_menu_state()
        if (
            current_screen in ("menu", "list_menu")
            or int(current_menu.get("menu_id", 0)) > 0
        ):
            return True
        emu.press_button("a", frames=STARTER_ACTION_FRAMES)
        emu.fast_forward(STARTER_ADVANCE_FRAMES)
    return False


STARTER_BALL_X = {
    "CHARMANDER": 6,
    "SQUIRTLE": 8,
    "BULBASAUR": 10,
}


def _starter_species_from_dialog(text: str) -> str | None:
    """Return the starter named by Oak's live confirmation dialog."""
    upper = text.upper()
    return next((species for species in STARTER_BALL_X if species in upper), None)


def _select_starter_from_menu(
    emu: Any,
    ram_reader: RAMReader,
    *,
    max_advances: int = 16,
    decline_presses: int = 8,
    decision_out: dict[str, Any] | None = None,
) -> int:
    """Choose Oak's starter through JEV, then decline the nickname prompt.

    The active YES/NO dialog supplies the currently faced species from RAM. JEV
    chooses among all three species; button presses only transport that choice.
    On a missing/invalid JEV answer this fails closed without accepting a ball.
    """
    party_count = ram_reader.party_count()
    dialog_text = ram_reader.read_dialog_text()
    visible_species = _starter_species_from_dialog(dialog_text)
    llm_blocked = _llm_mode_fast_tier_blocked()
    decision, valid_choice = _ask_jev_starter_choice(
        dialog_text,
        visible_species,
        llm_blocked=llm_blocked,
    )
    if decision_out is not None:
        _record_starter_decision_outcome(
            decision_out,
            visible_species,
            valid_choice,
            decision,
            llm_blocked=llm_blocked,
        )
    if valid_choice is None or not decision.get("ok"):
        return party_count

    if valid_choice != visible_species:
        if not _travel_to_starter_ball(
            emu,
            ram_reader,
            visible_species,
            valid_choice,
            max_advances=max_advances,
        ):
            return party_count

    return _confirm_starter_and_decline_nickname(
        emu,
        ram_reader,
        initial_party_count=party_count,
        max_advances=max_advances,
        decline_presses=decline_presses,
    )


def _ask_jev_starter_choice(
    dialog_text: str,
    visible_species: str | None,
    *,
    llm_blocked: bool,
) -> tuple[dict[str, Any], str | None]:
    """Ask JEV which starter ball to pick; return (decision, valid_choice).

    BENCH-1: in the pure-LLM benchmark mode the fast tier is never
    consulted — the gate below fails closed (no ball is accepted, the
    caller's own fallback flow decides).
    """
    questions = jev_client.starter_questions(visible_species=visible_species)
    state = json.dumps(
        {
            "phase": "STARTER",
            "visible_species": visible_species,
            "dialog": dialog_text,
            "choices": list(STARTER_BALL_X),
        },
        sort_keys=True,
    )
    if llm_blocked:
        decision: dict[str, Any] = {"ok": False, "error": "llm benchmark mode"}
    else:
        decision = jev_client.decide(
            state,
            act_phase=True,
            questions=questions,
        )
    raw_choice = decision.get("next_action")
    choice = raw_choice.upper() if isinstance(raw_choice, str) else None
    valid_choice = choice if choice in STARTER_BALL_X else None
    return decision, valid_choice


def _record_starter_decision_outcome(
    decision_out: dict[str, Any],
    visible_species: str | None,
    valid_choice: str | None,
    decision: dict[str, Any],
    *,
    llm_blocked: bool,
) -> None:
    """Mirror the JEV starter ask into ``decision_out`` using transport evidence."""
    # Same transport-evidence convention as the battle gate: a blocked ask
    # stamps ``jev_ok=None`` (no attempt), never a transport failure.
    _jev_outcome = {"jev_ok": None} if llm_blocked else _jev_outcome_fields(decision)
    decision_out.update(
        {
            "phase": "STARTER",
            "starter_choice": valid_choice,
            "visible_species": visible_species,
            "raw_distribution": decision.get("raw"),
            "jev_answered": bool(
                not llm_blocked and decision.get("ok") and valid_choice
            ),
            "escalated": bool(decision.get("escalate", False)),
            "missing_class": decision.get("missing_class"),
            "jev_blocked_reason": (
                f"decision_mode={DECISION_MODE} (fast tier not consulted)"
                if llm_blocked
                else None
            ),
            **_jev_outcome,
        }
    )


def _return_to_floor(emu: Any, ram_reader: RAMReader, max_advances: int) -> bool:
    """Decline the visible ball and walk back to the floor; True once there."""
    emu.press_button("b", frames=STARTER_ACTION_FRAMES)
    emu.fast_forward(STARTER_ADVANCE_FRAMES)
    for _ in range(max_advances):
        if ram_reader.screen_type() == "overworld":
            return True
        emu.press_button("b", frames=STARTER_ACTION_FRAMES)
        emu.fast_forward(STARTER_ADVANCE_FRAMES)
    return False


def _walk_to_ball_x(emu: Any, ram_reader: RAMReader, target_x: int) -> None:
    """Move horizontally to a starter ball column (Oak's balls: x=6/8/10)."""
    current_x = ram_reader.player_tile_x()
    direction = "right" if target_x > current_x else "left"
    for _ in range(abs(target_x - current_x)):
        emu.press_button(direction, frames=PRESS_FRAMES)
        _settle_directional_step(emu, ram_reader)


def _open_starter_dialog(emu: Any, ram_reader: RAMReader, max_advances: int) -> bool:
    """Walk up and confirm until the starter YES/NO dialog opens; else False."""
    emu.press_button("up", frames=PRESS_FRAMES)
    _settle_directional_step(emu, ram_reader)
    emu.press_button("a", frames=STARTER_ACTION_FRAMES)
    emu.fast_forward(STARTER_ADVANCE_FRAMES)
    for _ in range(max_advances):
        current_screen = ram_reader.screen_type()
        current_menu = ram_reader.read_menu_state()
        if (
            current_screen in ("menu", "list_menu")
            or int(current_menu.get("menu_id", 0)) > 0
        ):
            return True
        emu.press_button("a", frames=STARTER_ACTION_FRAMES)
        emu.fast_forward(STARTER_ADVANCE_FRAMES)
    return False


def _travel_to_starter_ball(
    emu: Any,
    ram_reader: RAMReader,
    visible_species: str | None,
    valid_choice: str,
    *,
    max_advances: int,
) -> bool:
    """Decline the visible ball and walk to the selected one, verifying by dialog.

    Oak's three balls sit at x=6/8/10 on the same row. Returns True only when
    the dialog ground truth confirms the movement landed on ``valid_choice``.
    """
    if not _return_to_floor(emu, ram_reader, max_advances):
        return False
    _walk_to_ball_x(emu, ram_reader, STARTER_BALL_X[valid_choice])
    if not _open_starter_dialog(emu, ram_reader, max_advances):
        return False
    # The dialog is the ground truth: never confirm if movement landed on
    # a different ball than the species JEV selected.
    selected_species = _starter_species_from_dialog(ram_reader.read_dialog_text())
    if selected_species is not None and selected_species != valid_choice:
        emu.press_button("b", frames=STARTER_ACTION_FRAMES)
        emu.fast_forward(STARTER_ADVANCE_FRAMES)
        return False
    return True


def _confirm_starter_and_decline_nickname(
    emu: Any,
    ram_reader: RAMReader,
    *,
    initial_party_count: int,
    max_advances: int,
    decline_presses: int,
) -> int:
    """Confirm the starter, then B-spam through the default-YES nickname prompt."""
    party_count = initial_party_count
    emu.press_button("a", frames=STARTER_ACTION_FRAMES)
    emu.fast_forward(STARTER_ADVANCE_FRAMES)

    for _ in range(max_advances):
        party_count = ram_reader.party_count()
        if party_count > 0:
            break
        emu.press_button("a", frames=STARTER_ACTION_FRAMES)
        emu.fast_forward(STARTER_ADVANCE_FRAMES)

    if party_count > 0:
        # Verified live against Pokémon Blue: B advances the remaining text and
        # resolves the default-YES nickname prompt as NO without name entry.
        for _ in range(decline_presses):
            emu.press_button("b", frames=STARTER_ACTION_FRAMES)
            emu.fast_forward(STARTER_ADVANCE_FRAMES)
    return party_count


def _starter_picked_event(
    previous_party_count: int,
    current_party_count: int,
    species_hint: str | None,
) -> dict[str, Any] | None:
    """Build the one-time milestone for the starter 0→1 party transition."""
    if previous_party_count != 0 or current_party_count != 1:
        return None
    return {
        "event": "starter_picked",
        "party_count": 1,
        "species_hint": species_hint,
    }


def _starter_milestone_for_cycle(
    *,
    previous_party_count: int,
    current_party_count: int,
    species_hint: str | None,
    baseline_starter_name: str | None,
    milestone_emitted: bool,
) -> tuple[dict[str, Any] | None, bool]:
    """One-shot starter milestone for one decision-loop cycle.

    Fires at most once per run, from either path:

    1. In-run 0→1 party transition (fresh boot: JEV-routed starter branch
       or controller-driven dialog advance) — the classic ``starter_picked`` event.
    2. Post-pick boot baseline: runs loading a known-good checkpoint
       (``data/boot.state`` was saved after the starter was received) start
       with ``party_count == 1``, so no 0→1 transition is ever observable and
       the strict transition check would stay silent forever even though the
       party visibly holds a starter (GAMEPLAY-STARTER-002). The milestone
       then fires from the baseline party's starter species instead, tagged
       with ``"source": "boot_baseline"``.

    Returns ``(event, milestone_emitted)`` — pass the previous cycle's
    ``milestone_emitted`` back in to keep the event one-shot across cycles.
    """
    if milestone_emitted:
        return None, True
    event = _starter_picked_event(
        previous_party_count, current_party_count, species_hint
    )
    if event is not None:
        return event, True
    if baseline_starter_name is not None and previous_party_count > 0:
        return (
            {
                "event": "starter_picked",
                "party_count": 1,
                "species_hint": baseline_starter_name,
                "source": "boot_baseline",
            },
            True,
        )
    return None, False


def _blocked_spatial_directions(spatial_desc: dict[str, Any]) -> set[str]:
    """Return blocked directions, preserving known map-edge exits."""
    adjacent = spatial_desc.get("adjacent", {})
    blocked = {
        direction
        for direction, tile_type in adjacent.items()
        if tile_type in ("wall", "object")
    }

    # Route 1 is a map-edge warp, so the coarse 2×2 block classifier sees
    # its north-edge tile as a wall. At the center opening, UP is the exit.
    if spatial_desc.get("map_name") == "Pallet Town":
        tile_x = int(spatial_desc.get("player_tile_x", -1))
        tile_y = int(spatial_desc.get("player_tile_y", 99))
        if 8 <= tile_x <= 12 and tile_y <= 2:
            blocked.discard("up")

    return blocked


def screenshot_to_base64(screenshot: np.ndarray) -> str:
    """Convert numpy RGB screenshot to base64 data URL."""
    from PIL import Image

    img = Image.fromarray(screenshot)
    # Scale 3x with nearest-neighbor (pixel-perfect) so the vision model
    # can distinguish wall edges from floor seams at 144x160 native res.
    img = img.resize((img.width * 3, img.height * 3), Image.Resampling.NEAREST)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def _cycle_frame_hash(screenshot: np.ndarray) -> str:
    """Hash one captured frame for every same-frame consumer in the cycle."""
    return hashlib.md5(screenshot.tobytes()).hexdigest()


def _save_cycle_screenshot(
    image: Image.Image,
    *,
    cycle: int,
    frame_hash: str,
    last_saved_frame_hash: str,
    screenshot_dir: Path,
) -> str:
    """Save a numbered progress frame only when its pixels changed."""
    if frame_hash == last_saved_frame_hash:
        return last_saved_frame_hash
    image.save(screenshot_dir / f"step_{cycle:04d}.png")
    return frame_hash


def _is_battle_game_state(game_state: dict[str, Any] | None) -> bool:
    """Return whether an observed game-state dict represents an active battle."""
    if not game_state:
        return False
    screen = game_state.get(
        "result", game_state.get("screen_type", game_state.get("screen", ""))
    )
    return screen == "battle" or bool(game_state.get("battle_state"))


BATTLE_ACTIONS = jev_client.BATTLE_ACTIONS


def _battle_fallback_action(game_state: dict[str, Any]) -> str | None:
    """Choose an observed usable move when JEV cannot return a valid action."""
    battle = game_state.get("battle_state")
    if not isinstance(battle, dict):
        return None
    player = battle.get("player")
    if not isinstance(player, dict):
        return None
    moves = player.get("moves")
    if not isinstance(moves, list):
        return None
    usable = [
        move
        for move in moves
        if isinstance(move, dict)
        and isinstance(move.get("slot"), int)
        and 1 <= move["slot"] <= 4
        and int(move.get("pp", 1)) > 0
    ]
    if not usable:
        return None
    # Prefer remaining PP; on a tie, preserve the later slot so recovery does
    # not silently recreate the old always-move-1 behavior.
    chosen = max(usable, key=lambda move: (int(move.get("pp", 1)), move["slot"]))
    return f"MOVE_{chosen['slot']}"


def _battle_tool_call(
    action: str, game_state: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    """Translate one JEV battle vocabulary choice into emulator transport."""
    if action.startswith("MOVE_"):
        return "select_move", {"move_number": int(action.removeprefix("MOVE_"))}
    if action == "RUN":
        return "run_from_battle", {}
    if action == "SWITCH":
        return "switch_pokemon", {"slot": 2}

    battle = game_state.get("battle_state")
    inventory = battle.get("inventory") if isinstance(battle, dict) else None
    item_name = "Potion"
    if isinstance(inventory, list):
        first_item = next((item for item in inventory if isinstance(item, str)), None)
        if first_item is not None:
            item_name = first_item
    return "use_battle_item", {"item_name": item_name}


def _battle_action_description(tool_name: str, arguments: dict[str, Any]) -> str:
    """Render the executed transport without hiding the selected vocabulary."""
    if tool_name == "select_move":
        return f"select_move({arguments['move_number']})"
    if tool_name == "switch_pokemon":
        return f"switch_pokemon({arguments['slot']})"
    if tool_name == "use_battle_item":
        return f"use_battle_item({arguments['item_name']})"
    return "run_from_battle()"


def _observe_battle_decision(game_state: dict[str, Any]) -> dict[str, Any] | None:
    """Ask JEV for the next normal battle action and its raw evidence."""
    if current_mode_family() == MODE_SYSTEM2:
        return None
    try:
        decision = jev_client.decide(
            json.dumps(game_state, default=str, sort_keys=True),
            in_battle=True,
            act_phase=True,
        )
    except Exception as exc:  # noqa: BLE001 - observability must not stop the battle
        safe_print(f"  [JEV] battle observation failed: {exc!r}")
        return None
    return decision if isinstance(decision, dict) else None


def _jev_battle_action(decision: dict[str, Any] | None) -> str | None:
    """Return a valid action from a successful JEV battle decision."""
    if not isinstance(decision, dict) or not decision.get("ok"):
        return None
    raw_action = decision.get("next_action")
    action = raw_action.upper() if isinstance(raw_action, str) else None
    return action if action in BATTLE_ACTIONS else None


def _jev_battle_tool_call(
    decision: dict[str, Any] | None, game_state: dict[str, Any]
) -> dict[str, Any] | None:
    """Translate an available JEV battle choice for StateWindow execution."""
    action = _jev_battle_action(decision)
    if action is None:
        return None
    tool_name, arguments = _battle_tool_call(action, game_state)
    return {"name": tool_name, "arguments": arguments}


def _executed_battle_action(history: list[dict[str, Any]]) -> str | None:
    """Return the effective vocabulary action from StateWindow's executed history."""
    for item in reversed(history):
        tool_call = item.get("tool_call")
        if not isinstance(tool_call, dict):
            continue
        tool_name = tool_call.get("name")
        raw_arguments = tool_call.get("arguments")
        arguments = raw_arguments if isinstance(raw_arguments, dict) else {}
        if tool_name == "select_move":
            move_number = arguments.get("move_number")
            return (
                f"MOVE_{move_number}" if isinstance(move_number, int) else "SELECT_MOVE"
            )
        if tool_name == "run_from_battle":
            return "RUN"
        if tool_name == "switch_pokemon":
            slot = arguments.get("slot")
            return f"SWITCH_{slot}" if isinstance(slot, int) else "SWITCH"
        if tool_name == "use_battle_item":
            return "ITEM"
        if isinstance(tool_name, str) and tool_name:
            return tool_name.upper()
    return None


def _stamp_battle_observability(
    entry: dict[str, Any],
    *,
    state_type: str,
    history: list[dict[str, Any]],
    jev_decision: dict[str, Any] | None,
) -> None:
    """Add battle-only telemetry to the real StateWindow decision row."""
    if state_type != "battle":
        return
    entry.update(
        {
            "phase": "BATTLE",
            "battle_action": _jev_battle_action(jev_decision)
            or _executed_battle_action(history),
            "raw_distribution": (
                jev_decision.get("raw") if isinstance(jev_decision, dict) else None
            ),
        }
    )


# ── JEV overworld tier (DF-JEV-1, PRD v3 stages 5-6) ────────────────────────
# The overworld action vocabulary is the non-battle question set's criteria
# (jev_client._questions): buttons, not battle moves. An answer outside this
# set is a JEV miss, and a miss falls back to the reasoning controller — the
# loop never invents a press out of an unreadable answer.
OVERWORLD_ACTIONS: frozenset[str] = frozenset(jev_client.BUTTONS)

# JEV's "do nothing this cycle" answer. It maps to an EMPTY plan because
# translating it into any button press would invent one.
OVERWORLD_WAIT = "WAIT"

# The decision-row pipeline name for a plan JEV authored (PRD v3 AC-1 rows).
JEV_PIPELINE = "jev"


def _jev_outcome_fields(decision: dict[str, Any]) -> dict[str, Any]:
    """Return the additive transport fields stamped on every JEV decision row."""
    ok = bool(decision.get("ok"))
    fields: dict[str, Any] = {"jev_ok": ok}
    if not ok:
        fields["jev_error"] = str(decision.get("error"))[:200]
    return fields


def _map_topology_resolved(obs: dict[str, Any], world_facts: list[str] | None) -> bool:
    """Whether current ROM evidence closes a recalled map-topology gap."""
    map_id = obs.get("map_id")
    if not isinstance(map_id, int) or not world_facts:
        return False
    map_prefix = f"/world/map/{map_id}:"
    if not any(fact.startswith(map_prefix) for fact in world_facts):
        return False

    walkability = obs.get("adjacent_walkability")
    if not isinstance(walkability, dict):
        return False
    required = {"up", "down", "left", "right"}
    if set(walkability) < required or any(
        walkability[direction] not in {"walkable", "blocked"} for direction in required
    ):
        return False

    collision_grid = obs.get("collision_grid")
    return (
        isinstance(collision_grid, str)
        and bool(collision_grid.strip())
        and "?" not in collision_grid
    )


def _teacher_world_memory_targets(
    patch: dict[str, Any], observation: dict[str, Any]
) -> tuple[list[str], list[str]]:
    """Bind a teacher's missing facts to exact current-map memory keys.

    The map record is always the primary target. Directional gaps additionally
    target the adjacent object key so a record beyond the normal prefix limit is
    fetched explicitly on the next cycle. Invalid/untyped patch entries produce
    no targets rather than broadening retrieval.
    """
    raw_missing = patch.get("missing_facts")
    if not isinstance(raw_missing, list):
        return [], []
    missing_facts = [
        fact.strip() for fact in raw_missing if isinstance(fact, str) and fact.strip()
    ]
    map_id = observation.get("map_id")
    if not missing_facts or not isinstance(map_id, int) or map_id < 0:
        return missing_facts, []

    targets = [f"/world/map/{map_id}"]
    player_x = observation.get("player_x")
    player_y = observation.get("player_y")
    if isinstance(player_x, int) and isinstance(player_y, int):
        aliases = {
            "up": {"up", "above", "north"},
            "down": {"down", "below", "south"},
            "left": {"left", "west"},
            "right": {"right", "east"},
        }
        for fact in missing_facts:
            words = set(re.findall(r"[a-z]+", fact.lower()))
            for direction, direction_aliases in aliases.items():
                if words.isdisjoint(direction_aliases):
                    continue
                dx, dy = _WORLD_TILE_OFFSETS[direction]
                target = f"/world/object/{map_id}/{player_x + dx}_{player_y + dy}"
                if target not in targets:
                    targets.append(target)
    return missing_facts, targets


# ── S6 NAV-MEM: memory-driven navigation ────────────────────────────────────
# A map transition observed by the loop is a PROVEN edge: pressing
# ``crossing_direction`` in ``from_map`` moved the player to ``to_map``. S6
# stores that edge as ``/world/path/<from>-><to>`` (see ``_path_memory_write``)
# and, before a navigation gap spends a teacher (LLM) call, replays it from
# memory instead of re-deriving the same world fact every episode.
#
# The store is read through ``duckbrain_client.recall`` rather than in-process
# state, so a route recorded by an earlier run is usable after a restart.
PATH_MEMORY_PREFIX = "/world/path/"
PATH_MEMORY_RECALL_LIMIT = 16
WORLD_MEMORY_TOP_K = 8
WORLD_MEMORY_BLOCK_CHARS = 2_000
WORLD_MEMORY_FACT_CHARS = 240
# The decision-pipeline stamped on a row whose plan came from path memory.
MEMORY_NAV_PIPELINE = "memory_nav"
# The one JEV missing-information class whose decisions are navigation. Only a
# gap JEV classified this way may be resolved from ``world/path/*``; every other
# hand-off keeps the existing teacher path untouched.
NAVIGATION_MISSING_CLASSES: frozenset[str] = frozenset({"map_topology"})
_WALK_DIRECTIONS: frozenset[str] = frozenset({"UP", "DOWN", "LEFT", "RIGHT"})


def _map_slug(map_name: str | None, map_id: int) -> str:
    """Canonical map token used in ``/world/path/<from>-><to>`` keys.

    Names are slugged so a memory key is stable and human-citable
    (``Pallet Town`` -> ``Pallet-Town``); a map with no usable name falls back
    to the same ``Map_XX`` spelling the rest of the harness uses for its id.
    """
    name = (map_name or "").strip()
    if name:
        slug = re.sub(r"[^0-9A-Za-z]+", "-", name).strip("-")
        if slug:
            return slug
    return f"Map-{map_id:02X}"


def _path_memory_key(from_slug: str, to_slug: str) -> str:
    """The exact memory key for one proven map edge."""
    return f"{PATH_MEMORY_PREFIX}{from_slug}->{to_slug}"


def _parse_path_memory_key(key: Any) -> tuple[str, str] | None:
    """Split a ``/world/path/<from>-><to>`` key, or None when it is not one."""
    if not isinstance(key, str) or not key.startswith(PATH_MEMORY_PREFIX):
        return None
    rest = key[len(PATH_MEMORY_PREFIX) :]
    from_slug, separator, to_slug = rest.partition("->")
    if not separator or not from_slug or not to_slug:
        return None
    return from_slug, to_slug


def _world_memory_key(fact: Any) -> str | None:
    """Extract the stable cited key from one rendered ``/world/*`` fact."""
    if not isinstance(fact, str):
        return None
    key = fact.partition(":")[0].strip()
    return key if key.startswith("/world/") else None


def _bounded_world_facts(facts: list[str] | None) -> list[str]:
    """Apply S3's top-K and character ceilings to decision-memory facts."""
    bounded: list[str] = []
    used = 0
    for raw in facts or []:
        if len(bounded) >= WORLD_MEMORY_TOP_K:
            break
        fact = " ".join(str(raw).split())
        if not fact:
            continue
        if len(fact) > WORLD_MEMORY_FACT_CHARS:
            fact = fact[: WORLD_MEMORY_FACT_CHARS - 3] + "..."
        remaining = WORLD_MEMORY_BLOCK_CHARS - used
        if remaining <= 0:
            break
        if len(fact) > remaining:
            if remaining < 4:
                break
            fact = fact[: remaining - 3] + "..."
        bounded.append(fact)
        used += len(fact)
    return bounded


def _world_memory_block(facts: list[str] | None) -> str:
    """Render the bounded relevant-memory block for the reasoning controller."""
    bounded = _bounded_world_facts(facts)
    if not bounded:
        return ""
    return "RELEVANT WORLD MEMORY (top 8, cited keys):\n" + "\n".join(
        f"- {fact}" for fact in bounded
    )


def _observation_map_slug(observation: dict[str, Any]) -> str | None:
    """The current map's path-key token, or None when the map is unreadable."""
    map_id = observation.get("map_id")
    if not isinstance(map_id, int) or map_id < 0:
        return None
    return _map_slug(str(observation.get("map_name") or ""), map_id)


def _tile_from_point(value: Any) -> tuple[int, int] | None:
    """Read a stored ``{"x": int, "y": int}`` point, when it is typed."""
    if not isinstance(value, dict):
        return None
    x, y = value.get("x"), value.get("y")
    if isinstance(x, int) and isinstance(y, int):
        return (x, y)
    return None


def _observation_tile(observation: dict[str, Any]) -> tuple[int, int] | None:
    """The tile the player stands on, when both coordinates are typed ints."""
    x = observation.get("player_tile_x")
    y = observation.get("player_tile_y")
    if isinstance(x, int) and isinstance(y, int):
        return (x, y)
    return None


def _memory_walkability(observation: dict[str, Any]) -> dict[str, str]:
    """ROM-resolved adjacent walkability for the tile the player stands on.

    The live collision grid is applied last: it is this cycle's RAM read, while
    ``adjacent_walkability`` may carry vision-derived labels.
    """
    resolved = _known_walkability(observation.get("adjacent_walkability"))
    resolved.update(_walkability_from_collision_grid(observation.get("collision_grid")))
    return resolved


def _step_toward(
    current: tuple[int, int],
    door: tuple[int, int],
    walkability: dict[str, str],
) -> str | None:
    """One legal button press that shortens the walk to ``door``.

    The larger remaining delta is tried first, so a wide room is crossed on its
    long axis. A direction is only chosen when the ROM resolved it as walkable:
    an unresolved or blocked cell is never pressed, so memory cannot invent a
    move the collision grid contradicts.
    """
    deltas = {
        ("RIGHT" if door[0] > current[0] else "LEFT"): abs(door[0] - current[0]),
        ("DOWN" if door[1] > current[1] else "UP"): abs(door[1] - current[1]),
    }
    for direction, delta in sorted(deltas.items(), key=lambda item: -item[1]):
        if delta <= 0:
            continue
        if walkability.get(direction.lower()) == "walkable":
            return direction
    return None


def _memory_route_plan(
    current: tuple[int, int] | None,
    door: tuple[int, int] | None,
    direction: str,
    walkability: dict[str, str],
) -> tuple[list[str], str] | None:
    """The button plan that replays a proven edge from the current tile.

    On the recorded door tile the proven crossing direction is replayed; away
    from it, one ROM-legal step toward the door is taken. Returns None when
    neither is legal, so the caller keeps its existing decision path instead of
    inventing a press.
    """
    if door is not None and current is not None and current != door:
        step = _step_toward(current, door, walkability)
        if step is None:
            return None
        return [step], "step_to_door"
    if direction not in _WALK_DIRECTIONS:
        return None
    if walkability.get(direction.lower()) == "blocked":
        return None
    return [direction], "proven_crossing"


def _memory_navigation_route(
    observation: dict[str, Any],
    *,
    visited_maps: tuple[tuple[int, str], ...] | None = None,
) -> dict[str, Any] | None:
    """Return a proven route toward a NOT-YET-VISITED map, or None.

    Reads the store (never in-process state). A destination the run has already
    visited is not a route toward new ground, and a route whose next step the
    ROM contradicts is refused here so the caller keeps its existing path.
    """
    from_slug = _observation_map_slug(observation)
    if from_slug is None:
        return None
    from src.core import duckbrain_client as _dbc

    records = _dbc.recall(
        key_prefix=f"{PATH_MEMORY_PREFIX}{from_slug}->",
        namespace=WORLD_MEMORY_NAMESPACE,
        limit=PATH_MEMORY_RECALL_LIMIT,
    )
    visited_slugs = _memory_visited_slugs(from_slug, visited_maps)

    current_tile = _observation_tile(observation)
    walkability = _memory_walkability(observation)
    candidates = _memory_route_candidates(records, visited_slugs)
    if not candidates:
        return None

    # The newest record wins: a later crossing is the more recent proof.
    _, record, direction, door = max(candidates, key=lambda item: item[0])
    plan_result = _memory_route_plan(current_tile, door, direction, walkability)
    if plan_result is None:
        return None
    plan, mechanism = plan_result
    return _memory_route_payload(record, direction, door, plan, mechanism)


def _memory_visited_slugs(
    from_slug: str,
    visited_maps: tuple[tuple[int, str], ...] | None,
) -> set[str]:
    """Collect map slugs already visited this run, seeded with the current map."""
    visited_slugs = {from_slug}
    for visited_id, visited_name in visited_maps or ():
        if isinstance(visited_id, int) and visited_id >= 0:
            visited_slugs.add(_map_slug(str(visited_name or ""), visited_id))
    return visited_slugs


def _memory_route_candidates(
    records: list[dict[str, Any]],
    visited_slugs: set[str],
) -> list[tuple[str, dict[str, Any], str, tuple[int, int] | None]]:
    """Turn stored path-memory records into sortable route candidates."""
    candidates: list[tuple[str, dict[str, Any], str, tuple[int, int] | None]] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        parsed = _parse_path_memory_key(record.get("key"))
        if parsed is None or parsed[1] in visited_slugs:
            continue
        attributes = record.get("attributes")
        if not isinstance(attributes, dict):
            attributes = {}
        candidates.append(
            (
                str(record.get("created_at") or ""),
                record,
                str(attributes.get("crossing_direction") or "").upper(),
                _tile_from_point(attributes.get("door_tile")),
            )
        )
    return candidates


def _memory_route_payload(
    record: dict[str, Any],
    direction: str,
    door: tuple[int, int] | None,
    plan: Any,
    mechanism: Any,
) -> dict[str, Any] | None:
    """Build the navigation-route payload from the winning memory record."""
    parsed = _parse_path_memory_key(record.get("key"))
    if parsed is None:
        return None
    attributes = record.get("attributes")
    if not isinstance(attributes, dict):
        attributes = {}
    return {
        "key": record.get("key"),
        "from_map": parsed[0],
        "to_map": parsed[1],
        "crossing_direction": direction or None,
        "door_tile": ({"x": door[0], "y": door[1]} if door is not None else None),
        "arrival_tile": attributes.get("arrival_tile"),
        "plan": plan,
        "mechanism": mechanism,
    }


def _memory_navigation_decision(
    observation: dict[str, Any],
    *,
    visited_maps: tuple[tuple[int, str], ...] | None = None,
) -> dict[str, Any]:
    """Resolve a navigation gap from ``world/path/*`` memory.

    Always returns a recordable outcome: a hit carries the cited key and the
    plan; a miss/error carries why, so the run summary can separate "no proven
    route exists" from "the store could not be read".
    """
    base: dict[str, Any] = {
        "source": "world/path",
        "from_map": _observation_map_slug(observation),
    }
    if base["from_map"] is None:
        return {**base, "result": "miss", "reason": "current_map_unknown"}
    try:
        route = _memory_navigation_route(observation, visited_maps=visited_maps)
    except Exception as exc:  # noqa: BLE001 - memory must not stop gameplay
        safe_print(f"  [NAV-MEM] path memory read failed: {exc!r}")
        return {**base, "result": "error", "reason": type(exc).__name__}
    if route is None:
        return {
            **base,
            "result": "miss",
            "reason": "no_proven_route_to_unvisited_map",
        }
    return {**base, **route, "result": "hit"}


def _is_navigation_gap(decision: dict[str, Any]) -> bool:
    """Whether this JEV answer is asking how to move through the map.

    The RAW reported class is read first: ``_map_topology_resolved`` may already
    have demoted an effective gap to ``missing_class="none"`` once the live ROM
    closed it, but the decision is still a navigation one, and a proven route
    still outranks re-deriving the same fact from the projection.
    """
    if not decision.get("ok"):
        return False
    if decision.get("reported_missing_class") in NAVIGATION_MISSING_CLASSES:
        return True
    missing = decision.get("missing_class")
    if isinstance(missing, str) and missing in NAVIGATION_MISSING_CLASSES:
        return True
    reason = decision.get("escalate_reason")
    return isinstance(reason, str) and "map_topology" in reason.lower()


def _path_memory_write(
    transition: dict[str, Any],
    *,
    observation: dict[str, Any],
    evidence: dict[str, Any],
    confidence: float,
) -> dict[str, Any] | None:
    """Render one observed map transition as a ``/world/path/*`` memory write."""
    from_id = transition.get("from_map_id")
    to_id = transition.get("to_map_id")
    if not isinstance(from_id, int) or not isinstance(to_id, int):
        return None
    if from_id < 0 or to_id < 0:
        return None
    from_name = str(transition.get("from_map_name") or "")
    to_name = str(transition.get("to_map_name") or "")
    from_slug = _map_slug(from_name, from_id)
    to_slug = _map_slug(to_name, to_id)
    domain = f"world/path/{from_slug}->{to_slug}"
    direction = str(transition.get("crossing_direction") or "").upper()
    door = _tile_from_point(transition.get("departure_tile"))
    arrival = _observation_tile(observation)
    route_tiles: list[dict[str, int]] = []
    raw_route = transition.get("route_tiles")
    if isinstance(raw_route, list):
        for raw_tile in raw_route:
            tile = _tile_from_point(raw_tile)
            rendered_tile = {"x": tile[0], "y": tile[1]} if tile is not None else None
            if rendered_tile is not None and rendered_tile not in route_tiles:
                route_tiles.append(rendered_tile)
    if door is not None:
        rendered_door = {"x": door[0], "y": door[1]}
        if rendered_door not in route_tiles:
            route_tiles.append(rendered_door)

    attributes: dict[str, Any] = {
        "fact_type": "path_transition",
        "from_map": {"id": from_id, "name": from_name},
        "to_map": {"id": to_id, "name": to_name},
        "crossing_direction": direction or None,
        "route_tiles": route_tiles,
        "regression": bool(transition.get("regression")),
    }
    if door is not None:
        attributes["door_tile"] = {"x": door[0], "y": door[1]}
    if arrival is not None:
        attributes["arrival_tile"] = {"x": arrival[0], "y": arrival[1]}

    rendered = (
        f"Proven route: from {from_name or from_slug}, press {direction} "
        f"to reach {to_name or to_slug}"
        if direction
        else f"Proven route: {from_name or from_slug} connects to {to_name or to_slug}"
    )
    return {
        "key": f"/{domain}",
        "domain": domain,
        "attributes": attributes,
        "embedding_text": rendered,
        "labels": ["world", domain],
        "confidence": confidence,
        "evidence": evidence,
        "applies_when": {"from_map_id": from_id},
    }


def _transition_map_exit_write(
    transition: dict[str, Any],
    *,
    existing: dict[str, Any] | None,
    evidence: dict[str, Any],
    confidence: float,
) -> dict[str, Any] | None:
    """Merge a newly proven exit into the source map's durable map record."""
    from_id = transition.get("from_map_id")
    to_id = transition.get("to_map_id")
    door = _tile_from_point(transition.get("departure_tile"))
    if not isinstance(from_id, int) or not isinstance(to_id, int) or door is None:
        return None
    if from_id < 0 or to_id < 0:
        return None
    from_name = str(transition.get("from_map_name") or f"Map_{from_id:02X}")
    to_name = str(transition.get("to_map_name") or f"Map_{to_id:02X}")
    direction = str(transition.get("crossing_direction") or "").upper() or None
    attributes: dict[str, Any] = {}
    if isinstance(existing, dict) and isinstance(existing.get("attributes"), dict):
        attributes.update(existing["attributes"])
    attributes.update(
        {
            "fact_type": "map_observation",
            "map_id": from_id,
            "map_name": from_name,
        }
    )
    raw_exits = attributes.get("exits")
    exits = (
        [dict(item) for item in raw_exits if isinstance(item, dict)]
        if isinstance(raw_exits, list)
        else []
    )
    new_exit = {
        "tile": {"x": door[0], "y": door[1]},
        "destination": {"id": to_id, "name": to_name},
        "crossing_direction": direction,
    }
    if new_exit in exits:
        return None
    exits.append(new_exit)
    attributes["exits"] = exits

    raw_tiles_visited = attributes.get("tiles_visited")
    tiles_visited = (
        [dict(item) for item in raw_tiles_visited if isinstance(item, dict)]
        if isinstance(raw_tiles_visited, list)
        else []
    )
    raw_route = transition.get("route_tiles")
    for raw_tile in raw_route if isinstance(raw_route, list) else []:
        tile = _tile_from_point(raw_tile)
        rendered = {"x": tile[0], "y": tile[1]} if tile is not None else None
        if rendered is not None and rendered not in tiles_visited:
            tiles_visited.append(rendered)
    door_point = {"x": door[0], "y": door[1]}
    if door_point not in tiles_visited:
        tiles_visited.append(door_point)
    attributes["tiles_visited"] = tiles_visited

    source_evidence = {
        **evidence,
        "map": {"id": from_id, "name": from_name},
        "tile": door_point,
    }
    domain = f"world/map/{from_id}"
    return {
        "key": f"/{domain}",
        "domain": domain,
        "attributes": attributes,
        "embedding_text": (
            f"Observed {from_name} exit at ({door[0]},{door[1]}) to {to_name}"
        ),
        "labels": ["world", domain],
        "confidence": confidence,
        "evidence": source_evidence,
    }


def _jev_overworld_decision(
    obs: dict[str, Any],
    *,
    goal: str = "",
    visited: dict[tuple[int, int], int] | None = None,
    recent_events: list[dict[str, Any]] | None = None,
    recent_decisions: list[dict[str, Any]] | None = None,
    world_facts: list[str] | None = None,
    last_action: str = "",
    last_action_changed_state: bool | None = None,
    teacher_api_client: Any = None,
    teacher_model: str | None = None,
    teacher_memory: str | None = None,
    teacher_log_file: TextIO | None = None,
    teacher_cycle: int | None = None,
    teacher_results: list[dict[str, Any]] | None = None,
    escalated_classes: set[str] | None = None,
    handoff_policy: dict[str, Any] | None = None,
    teacher_budget: dict[str, int] | None = None,
    scenario_path: str | Path | None = None,
    visited_maps: tuple[tuple[int, str], ...] | None = None,
) -> dict[str, Any]:
    """Ask the JEV tier for this overworld cycle's plan (PRD v3 stages 5-6).

    The bounded RAM projection is built the way ``scripts/jev_projection_probe.py``
    builds it — the same ``state_projection.build()`` call over the live
    ``observe()`` dict, with the same cross-cycle material (goal, per-tile repeat
    counts, recent events, last action) and the same mechanics rules — so the
    game loop consumes the exact contract the probe proved.

    Fail-closed contract: when JEV errors or its ``next_action`` is outside the
    overworld vocabulary, the return carries only the unusable JEV attempt so
    the caller falls back to ``controller_plan()`` while preserving transport
    evidence; no press is ever invented. On a hit, the dict carries the
    ``plan``/``intent`` the loop executes plus the JEV proof fields
    the per-decision rows stamp: ``jev_answered``, ``escalated``,
    ``missing_class`` and ``raw_distribution`` (the full answer distribution).
    """
    err, decision, projection, world_memory_keys = _jev_build_projection_decision(
        obs,
        goal=goal,
        visited=visited,
        recent_events=recent_events,
        last_action=last_action,
        last_action_changed_state=last_action_changed_state,
        world_facts=world_facts,
        scenario_path=scenario_path,
    )
    if err is not None:
        return cast(dict[str, Any], err)

    assert decision is not None
    initial_decision = decision
    teacher_one_shot: str | None = None
    teacher_missing_facts: list[str] = []
    teacher_memory_targets: list[str] = []
    memory_navigation, memory_hit = _jev_consult_memory_navigation(
        obs,
        decision,
        visited_maps=visited_maps,
    )
    missing_class = decision.get("missing_class")
    escalation_class = (
        missing_class if isinstance(missing_class, str) and missing_class else "unknown"
    )
    handoff_trigger, policy, handoff_ok, handoff_why = _jev_handoff_gate(
        decision,
        handoff_policy=handoff_policy,
        teacher_budget=teacher_budget,
        escalation_class=escalation_class,
    )
    can_call_teacher = (
        bool(decision.get("escalate"))
        and handoff_ok
        and teacher_api_client is not None
        and bool(teacher_model)
        and escalated_classes is not None
        and escalation_class not in escalated_classes
        # S6 NAV-MEM: a proven route already answered this navigation gap, so
        # the teacher (LLM) is never called for it.
        and memory_hit is None
    )
    if can_call_teacher:
        (
            decision,
            _teacher_record,
            teacher_one_shot,
            teacher_missing_facts,
            teacher_memory_targets,
        ) = _jev_teacher_escalation(
            decision,
            projection=projection,
            obs=obs,
            teacher_memory=teacher_memory,
            recent_events=recent_events,
            recent_decisions=recent_decisions,
            last_action_changed_state=last_action_changed_state,
            teacher_log_file=teacher_log_file,
            teacher_cycle=teacher_cycle,
            teacher_results=teacher_results,
            teacher_model=teacher_model,
            teacher_api_client=teacher_api_client,
            escalated_classes=escalated_classes,
            teacher_budget=teacher_budget,
        )

    escalate = bool(initial_decision.get("escalate", False))
    # A policy-blocked trigger is NOT an escalation: no teacher was called, so
    # the row must not claim one. This is what makes system1 (handoff off)
    # measurable — `escalated` means "handed back", not "wanted to".
    if escalate and not handoff_ok:
        escalate = False
    reason = initial_decision.get("escalate_reason")
    plan, intent, jev_answered, escalate, decision = _jev_resolve_action_plan(
        decision,
        initial_decision,
        teacher_one_shot=teacher_one_shot,
        memory_hit=memory_hit,
        escalate=escalate,
    )
    if plan is None:
        # Return the JEV attempt, not an empty sentinel: the caller still
        # takes the controller fallback, but can stamp whether this was a
        # transport failure or a healthy response with no usable action.
        return decision
    return _jev_decision_row(
        decision,
        initial_decision,
        plan=plan,
        intent=intent,
        jev_answered=jev_answered,
        escalate=escalate,
        reason=reason,
        projection=projection,
        handoff_trigger=handoff_trigger,
        handoff_ok=handoff_ok,
        handoff_why=handoff_why,
        policy=policy,
        teacher_missing_facts=teacher_missing_facts,
        teacher_memory_targets=teacher_memory_targets,
        memory_navigation=memory_navigation,
        world_memory_keys=world_memory_keys,
    )


def _jev_build_projection_decision(
    obs: dict[str, Any],
    *,
    goal: str,
    visited: dict[tuple[int, int], int] | None,
    recent_events: list[dict[str, Any]] | None,
    last_action: str,
    last_action_changed_state: bool | None,
    world_facts: list[str] | None,
    scenario_path: str | Path | None,
) -> tuple[Any, dict[str, Any] | None, str, list[str]]:
    """Build the bounded projection and ask JEV; fail closed on any raise.

    Returns ``(error, decision, projection, world_memory_keys)`` — ``error`` is
    the fail-closed row when the tier raised, and the remaining values are
    ``None``/empty in that case. Callers must treat ``decision`` as non-None
    after the error check (JEV's contract: any raising tier is replaced by the
    fail-closed row, never left unwritten).
    """
    world_memory_keys: list[str] = []
    try:
        bounded_world_facts = _bounded_world_facts(world_facts)
        world_memory_keys = [
            key for fact in bounded_world_facts if (key := _world_memory_key(fact))
        ]
        if bounded_world_facts:
            safe_print(
                f"  [MEM-WORLD] {len(bounded_world_facts)} facts -> JEV projection: "
                + ", ".join(world_memory_keys)
            )
        projection = state_projection.build(
            obs,
            goal=goal,
            visited=visited,
            recent_events=recent_events,
            last_action=last_action,
            last_action_changed_state=last_action_changed_state,
            mechanics=state_projection.DEFAULT_MECHANICS,
            extra_facts=bounded_world_facts or None,
        )
        decision = jev_client.decide(
            projection,
            last_action_failed=last_action_changed_state is False,
            scenario_path=scenario_path,
        )
        _reconcile_map_topology_gap(decision, obs, world_facts)
        return None, decision, projection, world_memory_keys
    except Exception as exc:  # noqa: BLE001 - fail closed, but never silently
        # A raising tier must not kill the cycle AND must not hide itself: the
        # run keeps playing through the controller, and the transport outcome
        # is carried into the fallback decision row for run-level degradation.
        safe_print(f"  [JEV] overworld decision failed: {exc!r} - falling back")
        return (
            cast(dict[str, Any], {"ok": False, "error": f"{type(exc).__name__}: {exc}"}),
            None,
            "",
            [],
        )


def _reconcile_map_topology_gap(
    decision: dict[str, Any],
    obs: dict[str, Any],
    world_facts: list[str] | None,
) -> None:
    """Downgrade a self-reported map_topology gap the ROM data disproves.

    JEV repeatedly self-reported this gap after the projection carried
    both the recalled map and exact ROM collision truth. Preserve the
    raw answer but reconcile the effective gate with deterministic data.
    """
    reason = decision.get("escalate_reason")
    topology_gap = (
        isinstance(reason, str)
        and (
            reason.startswith("insufficient_state")
            or reason.startswith("missing_class=map_topology")
        )
        and decision.get("missing_class") == "map_topology"
    )
    if topology_gap and _map_topology_resolved(obs, world_facts):
        decision["reported_missing_class"] = "map_topology"
        decision["missing_class"] = "none"
        decision["escalate"] = False
        decision["escalate_reason"] = "map_topology_resolved_by_rom"


def _jev_consult_memory_navigation(
    obs: dict[str, Any],
    decision: dict[str, Any],
    *,
    visited_maps: tuple[tuple[int, str], ...] | None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Consult proven path-memory routes for a navigation gap (S6 NAV-MEM).

    Only a navigation gap reads ``world/path/*``; a hit replaces the teacher
    call entirely and stamps the cited memory key on the row. A miss leaves
    the existing hand-off byte-identical, so an empty store cannot change a
    run's behaviour.
    """
    memory_navigation: dict[str, Any] | None = None
    memory_hit: dict[str, Any] | None = None
    if not _is_navigation_gap(decision):
        return memory_navigation, memory_hit
    memory_navigation = _memory_navigation_decision(obs, visited_maps=visited_maps)
    if memory_navigation.get("result") == "hit":
        memory_hit = memory_navigation
        safe_print(
            f"  [NAV-MEM] {memory_hit['key']} "
            f"({memory_hit['mechanism']}) -> {memory_hit['plan']} | no LLM call"
        )
    else:
        safe_print(
            f"  [NAV-MEM] no proven route ({memory_navigation.get('reason')}) "
            "- keeping the existing path"
        )
    return memory_navigation, memory_hit


def _jev_handoff_gate(
    decision: dict[str, Any],
    *,
    handoff_policy: dict[str, Any] | None,
    teacher_budget: dict[str, int] | None,
    escalation_class: str,
) -> tuple[str, dict[str, Any], bool, str | None]:
    """Classify the trigger and check the run's handoff policy + teacher budget.

    The trigger families are the ones jev_client.should_escalate() already
    fires; the policy only selects among them.
    """
    handoff_trigger = classify_handoff_trigger(decision.get("escalate_reason"))
    policy = handoff_policy if isinstance(handoff_policy, dict) else HANDOFF_POLICY
    handoff_ok, handoff_why = handoff_allowed(policy, handoff_trigger, escalation_class)
    if handoff_ok and teacher_budget is not None:
        cap = policy.get("teacher_max_per_episode")
        if isinstance(cap, int) and cap > 0 and teacher_budget.get("used", 0) >= cap:
            handoff_ok = False
            handoff_why = (
                f"teacher budget exhausted ({teacher_budget.get('used', 0)}/{cap})"
            )
    return handoff_trigger, policy, handoff_ok, handoff_why


def _jev_teacher_escalation(
    decision: dict[str, Any],
    *,
    projection: str,
    obs: dict[str, Any],
    teacher_memory: str | None,
    recent_events: list[dict[str, Any]] | None,
    recent_decisions: list[dict[str, Any]] | None,
    last_action_changed_state: bool | None,
    teacher_log_file: TextIO | None,
    teacher_cycle: int | None,
    teacher_results: list[dict[str, Any]] | None,
    teacher_model: str | None,
    teacher_api_client: Any,
    escalated_classes: set[str] | None,
    teacher_budget: dict[str, int] | None,
) -> tuple[
    dict[str, Any],
    dict[str, Any] | None,
    str | None,
    list[str],
    list[str],
]:
    """Escalate to the teacher LLM and fold its patch back into the decision.

    Consumes the per-class allowance before the API boundary so a failed or
    raising teacher cannot be retried on every subsequent game cycle, and
    counts the budget at the same boundary (a call that fails still spent it).
    """
    teacher_record: dict[str, Any] | None = None
    teacher_one_shot: str | None = None
    teacher_missing_facts: list[str] = []
    teacher_memory_targets: list[str] = []
    # The predicate above narrows this for readers; the assertion also makes
    # the Optional contract explicit to static analyzers.
    assert escalated_classes is not None
    escalated_classes.add(escalation_class_of(decision))
    if teacher_budget is not None:
        teacher_budget["used"] = teacher_budget.get("used", 0) + 1
    prior_turn_count = len(
        (recent_decisions or [])[-jev_client.RECENT_DECISION_LIMIT :]
    )
    if prior_turn_count:
        safe_print(f"  [CTX] teacher request carried {prior_turn_count} prior turns")
    try:
        teacher_record = jev_client.escalate_and_reask(
            decision,
            projection=projection,
            memory=teacher_memory,
            recent_events=recent_events,
            recent_decisions=recent_decisions,
            milestones=[],
            teacher_model=teacher_model,
            client=teacher_api_client,
            last_action_failed=last_action_changed_state is False,
            log_file=teacher_log_file,
            cycle=teacher_cycle,
            results=teacher_results,
        )
    except Exception as exc:  # noqa: BLE001 - fail closed to normal decision
        safe_print(f"  [TEACHER] escalation failed: {exc!r} - using normal decision")
    if teacher_record and teacher_record.get("ok"):
        decision, teacher_one_shot, teacher_missing_facts, teacher_memory_targets = (
            _apply_teacher_patch(decision, teacher_record, obs)
        )
    return decision, teacher_record, teacher_one_shot, teacher_missing_facts, teacher_memory_targets


def escalation_class_of(decision: dict[str, Any]) -> str:
    """Return the escalation class for a decision that is about to escalate."""
    missing_class = decision.get("missing_class")
    return (
        missing_class if isinstance(missing_class, str) and missing_class else "unknown"
    )


def _apply_teacher_patch(
    decision: dict[str, Any],
    teacher_record: dict[str, Any],
    obs: dict[str, Any],
) -> tuple[dict[str, Any], str | None, list[str], list[str]]:
    """Fold a successful teacher patch (one-shot + post-ask) into the decision."""
    teacher_one_shot: str | None = None
    teacher_missing_facts: list[str] = []
    teacher_memory_targets: list[str] = []
    patch = teacher_record.get("patch")
    post_ask = teacher_record.get("post_ask")
    if isinstance(patch, dict):
        teacher_missing_facts, teacher_memory_targets = (
            _teacher_world_memory_targets(patch, obs)
        )
        raw_one_shot = patch.get("one_shot_action")
        if isinstance(raw_one_shot, str):
            normalized_one_shot = raw_one_shot.upper()
            if normalized_one_shot in OVERWORLD_ACTIONS:
                teacher_one_shot = normalized_one_shot
    if isinstance(post_ask, dict) and post_ask.get("ok"):
        decision = post_ask
    return decision, teacher_one_shot, teacher_missing_facts, teacher_memory_targets


def _jev_resolve_action_plan(
    decision: dict[str, Any],
    initial_decision: dict[str, Any],
    *,
    teacher_one_shot: str | None,
    memory_hit: dict[str, Any] | None,
    escalate: bool,
) -> tuple[list[str] | None, str, bool, bool, dict[str, Any]]:
    """Turn the JEV/teacher/memory answer into an executable plan.

    Returns ``(plan, intent, jev_answered, escalate, decision)``. ``plan`` is
    ``None`` when no usable action exists — the caller then returns the
    (possibly degraded) decision so the controller fallback can stamp it.
    S6 NAV-MEM: a memory-resolved navigation gap neither handed back to the
    teacher nor carries a JEV-authored plan, so the row reports
    ``escalated=False`` / ``jev_answered=False`` and cites the path-memory key.
    """
    jev_answered = True
    if memory_hit is not None:
        return list(memory_hit["plan"]), f"memory-nav {memory_hit['key']}", False, False, decision
    raw_action = teacher_one_shot or decision.get("next_action")
    action = raw_action.upper() if isinstance(raw_action, str) else None
    if not decision.get("ok") or action not in OVERWORLD_ACTIONS:
        # A failed escalation degrades to the original JEV decision. If that
        # is unusable too, the caller takes its existing controller fallback.
        decision = initial_decision
        raw_action = decision.get("next_action")
        action = raw_action.upper() if isinstance(raw_action, str) else None
    if not decision.get("ok") or action not in OVERWORLD_ACTIONS:
        return None, "", jev_answered, escalate, decision
    if teacher_one_shot is not None:
        return [teacher_one_shot], f"teacher one-shot {teacher_one_shot}", jev_answered, escalate, decision
    if action == OVERWORLD_WAIT:
        return [], "jev WAIT (no press)", jev_answered, escalate, decision
    return [action], f"jev {action}", jev_answered, escalate, decision


def _jev_decision_row(
    decision: dict[str, Any],
    initial_decision: dict[str, Any],
    *,
    plan: list[str],
    intent: str,
    jev_answered: bool,
    escalate: bool,
    reason: Any,
    projection: str,
    handoff_trigger: str,
    handoff_ok: bool,
    handoff_why: str | None,
    policy: dict[str, Any],
    teacher_missing_facts: list[str],
    teacher_memory_targets: list[str],
    memory_navigation: dict[str, Any] | None,
    world_memory_keys: list[str],
) -> dict[str, Any]:
    """Assemble the per-cycle JEV decision row (the loop's contract)."""
    return {
        "ok": bool(decision.get("ok")),
        "plan": plan,
        "intent": intent,
        "jev_answered": jev_answered,
        "escalated": escalate,
        "missing_class": initial_decision.get("missing_class"),
        "reported_missing_class": initial_decision.get("reported_missing_class"),
        # Preserve the first JEV answer in raw_distribution. When a promoted
        # scenario re-asks JEV, the effective answer is a separate field.
        "raw_distribution": decision.get("raw"),
        "scenario_post_distribution": decision.get("scenario_post_raw"),
        "scenario_patch_id": decision.get("scenario_patch_id"),
        "scenario_patch_evidence": decision.get("scenario_patch_evidence"),
        "scenario_patch_applied": bool(decision.get("scenario_patch_applied", False)),
        "jev_escalate_reason": reason if isinstance(reason, str) else None,
        "jev_projection_chars": len(projection),
        # Handoff provenance: which trigger fired, whether the run's policy let
        # it hand back, and why not when it did not. Stamped on every row so a
        # mode and its policy are recoverable from the log alone.
        "handoff_trigger": handoff_trigger,
        "handoff_allowed": handoff_ok,
        "handoff_blocked_reason": None if handoff_ok else handoff_why,
        "handoff_policy_families": sorted(policy.get("families") or ()),
        # A successful teacher patch becomes a one-cycle retrieval request.
        # The main loop holds these exact /world/* keys until the next cycle.
        "teacher_missing_facts": teacher_missing_facts,
        "teacher_memory_targets": teacher_memory_targets,
        # S6 NAV-MEM: the path-memory outcome of this decision — a hit (and the
        # cited key), or a miss/error with the reason. Counted run-wide into
        # `memory_navigation_hits` / `memory_navigation_fallbacks`.
        "memory_navigation": memory_navigation,
        # Exact citations for the bounded facts that reached this request.
        "world_memory_keys": world_memory_keys,
    }


def _llm_mode_fast_tier_blocked() -> bool:
    """Whether the pure-LLM benchmark mode is active (fast tier must not ask).

    One predicate for EVERY direct fast-tier call site: ``_jev_or_none`` gates
    the overworld path, and battle recovery / starter selection call this
    directly. In ``system2`` (``llm``) a benchmark run must spend no JEV
    budget anywhere — a leak at any site stamps ``jev_answered=True`` into a
    benchmark-labelled log and silently contaminates the arm being measured.
    """
    return current_mode_family() == MODE_SYSTEM2


def _jev_or_none(*args: Any, **kwargs: Any) -> dict[str, Any] | None:
    """Return a fast-tier decision, or None in the pure-LLM benchmark mode.

    In ``system2`` (the historical "llm") the fast tier is not merely ignored —
    it is never called, so a benchmark run spends no JEV budget and every
    decision in its log is the controller's own. In ``system1`` and
    ``system1+system2`` this is a transparent pass-through; the difference
    between those two is the handoff policy, applied inside.
    """
    if _llm_mode_fast_tier_blocked():
        return None
    return _jev_overworld_decision(*args, **kwargs)


def _escalating_recovery(
    emu,
    recovery_level: int,
    last_direction: str,
    last_saved_slot: int | None,
    game_state: dict[str, Any] | None = None,
    decision_out: dict[str, Any] | None = None,
    forbidden_directions: set[str] | None = None,
) -> tuple[str, str]:
    """Execute escalating recovery action. Returns (strategy_name, description).

    Ladder:
      Level 0 — Alternate direction: rotate 90° from last direction
      Level 1 — Menu redraw: START, B, B (force screen refresh)
      Level 2 — Step back: press opposite of last direction
      Level 3 — Load checkpoint: restore last saved state
      Level 4 — A-mash + B: rapid A presses (dialog stuck) then B to close

    If no last_direction or no checkpoint available, skips to next level.
    Recovery level wraps at 4 (always does A-mash on max).

    Battles bypass every generic rung. Loading a checkpoint can erase the
    encounter, START/B/direction recovery is not a legal turn, and blind A-mash
    can choose an unintended move. Ask JEV against the live battle state and
    translate its battle vocabulary choice into the corresponding tool call —
    except in the pure-LLM benchmark mode, where the fast tier is never
    consulted (BENCH-1: the benchmark arm must not be contaminated) and the
    RAM fallback below decides the battle fail-closed.
    """
    if _is_battle_game_state(game_state):
        assert game_state is not None
        return _battle_recovery_action(
            emu, game_state, decision_out=decision_out
        )

    # Clamp level
    level = min(recovery_level, 4)

    if level == 0 and last_direction in _DIR_ROTATION:
        alt = _DIR_ROTATION[last_direction]
        emu.press_button(alt.lower(), frames=60)
        emu.fast_forward(120)
        return ("alternate_direction", f"rotated from {last_direction} → {alt}")

    if level == 1:
        return _menu_redraw_recovery(emu)

    if level == 2 and last_direction in _OPPOSITE_DIR:
        return _step_back_recovery(
            emu,
            last_direction,
            decision_out=decision_out,
            forbidden_directions=forbidden_directions,
        )

    if level == 3 and last_saved_slot is not None:
        return _load_checkpoint_recovery(emu, last_saved_slot)

    if level >= 4 or (level >= 2 and last_direction not in _OPPOSITE_DIR):
        return _a_mash_recovery(emu)

    # Fallback: try next level
    return _escalating_recovery(
        emu,
        recovery_level + 1,
        last_direction,
        last_saved_slot,
        game_state=game_state,
        decision_out=decision_out,
        forbidden_directions=forbidden_directions,
    )


def _battle_recovery_action(
    emu,
    game_state: dict[str, Any],
    *,
    decision_out: dict[str, Any] | None,
) -> tuple[str, str]:
    """Run the battle recovery rung: JEV decides, translated into a tool call.

    Battles bypass every generic rung. Loading a checkpoint can erase the
    encounter, START/B/direction recovery is not a legal turn, and blind A-mash
    can choose an unintended move. Ask JEV against the live battle state and
    translate its battle vocabulary choice into the corresponding tool call —
    except in the pure-LLM benchmark mode, where the fast tier is never
    consulted (BENCH-1: the benchmark arm must not be contaminated) and the
    RAM fallback below decides the battle fail-closed.
    """
    llm_blocked = _llm_mode_fast_tier_blocked()
    if llm_blocked:
        decision: dict[str, Any] = {"ok": False, "error": "llm benchmark mode"}
    else:
        decision = jev_client.decide(
            json.dumps(game_state, default=str, sort_keys=True),
            in_battle=True,
            act_phase=True,
        )
    raw_action = decision.get("next_action")
    action = raw_action.upper() if isinstance(raw_action, str) else None
    jev_action = action if action in BATTLE_ACTIONS else None
    battle_action = jev_action or _battle_fallback_action(game_state)
    # Transport evidence follows the overworld convention: a blocked ask
    # stamps ``jev_ok=None`` (no attempt was made), NOT ``False`` — a
    # False would count as a JEV transport failure and could trip the
    # degradation gate on a mode that never touches the tier.
    _jev_outcome = {"jev_ok": None} if llm_blocked else _jev_outcome_fields(decision)
    if decision_out is not None:
        decision_out.update(
            {
                "phase": "BATTLE",
                "battle_action": battle_action,
                "intent": (
                    f"battle action {battle_action}"
                    if battle_action is not None
                    else None
                ),
                "raw_distribution": decision.get("raw"),
                "jev_answered": bool(
                    not llm_blocked and decision.get("ok") and jev_action
                ),
                "escalated": bool(decision.get("escalate", False)),
                "missing_class": decision.get("missing_class"),
                "jev_blocked_reason": (
                    f"decision_mode={DECISION_MODE} (fast tier not consulted)"
                    if llm_blocked
                    else None
                ),
                **_jev_outcome,
            }
        )
    if battle_action is None:
        return (
            "battle_jev_unavailable",
            "JEV returned no valid battle action and RAM exposed no usable move",
        )
    tool_name, arguments = _battle_tool_call(battle_action, game_state)
    result = execute_tool_call(emu, tool_name, arguments)
    action_description = _battle_action_description(tool_name, arguments)
    source = "JEV" if jev_action is not None else "RAM fallback"
    return (
        "battle_jev_action",
        f"{action_description} chosen by {source} — {result}",
    )


def _menu_redraw_recovery(emu) -> tuple[str, str]:
    """Level 1: open menu, close it — forces screen re-render."""
    emu.press_button("start", frames=30)
    emu.wait(60)
    emu.press_button("b", frames=10)
    emu.wait(30)
    emu.press_button("b", frames=10)
    emu.wait(30)
    return ("menu_redraw", "START → B → B (force screen redraw)")


def _step_back_recovery(
    emu,
    last_direction: str,
    *,
    decision_out: dict[str, Any] | None,
    forbidden_directions: set[str] | None,
) -> tuple[str, str]:
    """Level 2: press opposite of last direction, honouring forbidden edges."""
    opp = _OPPOSITE_DIR[last_direction]
    forbidden = {direction.upper() for direction in (forbidden_directions or set())}
    if opp in forbidden:
        replacement = _DIR_ROTATION[opp]
        for _ in range(4):
            if replacement not in forbidden:
                break
            replacement = _DIR_ROTATION[replacement]
        if replacement in forbidden:
            return (
                "navigation_hold_recovery_skipped",
                f"refused {opp}; every recovery direction is forbidden",
            )
        emu.press_button(replacement.lower(), frames=60)
        emu.fast_forward(120)
        if decision_out is not None:
            decision_out["navigation_hold_recovery"] = {
                "mechanism": "reverse_edge_guard",
                "blocked_direction": opp,
                "replacement_direction": replacement,
            }
        return (
            "navigation_hold_recovery",
            f"refused reverse-edge {opp}; pressed {replacement} instead",
        )
    emu.press_button(opp.lower(), frames=60)
    emu.fast_forward(120)
    return ("step_back", f"pressed {opp} (opposite of {last_direction})")


def _load_checkpoint_recovery(emu, last_saved_slot: int) -> tuple[str, str]:
    """Level 3: restore the last saved state."""
    try:
        emu.load_state(last_saved_slot)
        return ("load_checkpoint", f"loaded slot {last_saved_slot}")
    except Exception as exc:
        return ("load_checkpoint_failed", f"slot {last_saved_slot}: {exc}")


def _a_mash_recovery(emu) -> tuple[str, str]:
    """Level 4: 20 rapid A presses (dialog stuck) then B to close menus."""
    for _ in range(20):
        emu.press_button("a", frames=3)
        emu.fast_forward(1)
    emu.wait(30)
    emu.press_button("b", frames=30)
    emu.wait(30)
    return ("a_mash", "20× A + B (dialog/menu escape)")


def _extract_vision_usage(response: Any) -> dict[str, Any] | None:
    """Normalize a chat_completion response's usage block (PERCEPT-1).

    Delegates to ``VisionClient._normalize_usage`` so the vision path and
    the decision-loop path report the identical shape. Imported lazily so
    CLI parsing and preflight stay light.
    """
    from src.core.vision import VisionClient

    if not isinstance(response, dict):
        return None
    return VisionClient._normalize_usage(response.get("usage"))


def _sum_vision_usage(
    left: dict[str, Any] | None, right: dict[str, Any] | None
) -> dict[str, Any] | None:
    """Sum two normalized vision-usage blocks (PERCEPT-1).

    Used when one logical decision took several API calls (the controller
    retry). ``None`` operands are treated as zero; the cost sums when both
    sides price the call, stays ``None`` when neither does, and falls back
    to the one priced side otherwise. Image tokens sum only over the sides
    that reported them.
    """
    if left is None:
        return right
    if right is None:
        return left

    def _optional_sum(a: Any, b: Any) -> Any:
        if a is None and b is None:
            return None
        if a is None:
            return b
        if b is None:
            return a
        return a + b

    return {
        "prompt_tokens": int(left.get("prompt_tokens") or 0)
        + int(right.get("prompt_tokens") or 0),
        "completion_tokens": int(left.get("completion_tokens") or 0)
        + int(right.get("completion_tokens") or 0),
        "total_tokens": int(left.get("total_tokens") or 0)
        + int(right.get("total_tokens") or 0),
        "image_tokens": _optional_sum(
            left.get("image_tokens"), right.get("image_tokens")
        ),
        "cost_usd": _optional_sum(left.get("cost_usd"), right.get("cost_usd")),
    }


def _rollup_vision_usage(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate per-decision vision usage across a run (PERCEPT-1).

    Reads ``vision_usage`` on decision rows (controller/JEV plans) and
    ``_cartographer_usage`` on rows carrying the cartographer's spatial
    dict. Returns a flat dict suitable for the final summary line and the
    log's evidence row; every ``None``-valued field keeps its ``None`` so
    the report can distinguish "provider did not price this" from 0.
    """
    totals: dict[str, Any] = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "image_tokens": None,
        "cost_usd": None,
        "calls": 0,
    }
    for row in results:
        usages: list[dict[str, Any]] = []
        vision = row.get("vision_usage")
        if isinstance(vision, dict):
            usages.append(vision)
        carto = row.get("_cartographer_usage")
        if isinstance(carto, dict):
            usages.append(carto)
        for usage in usages:
            totals["calls"] += 1
            totals["prompt_tokens"] += int(usage.get("prompt_tokens") or 0)
            totals["completion_tokens"] += int(usage.get("completion_tokens") or 0)
            totals["total_tokens"] += int(usage.get("total_tokens") or 0)
            if usage.get("image_tokens") is not None:
                current_image = totals["image_tokens"]
                add_image = int(usage["image_tokens"])
                totals["image_tokens"] = (
                    add_image
                    if current_image is None
                    else int(current_image) + add_image
                )
            if usage.get("cost_usd") is not None:
                current_cost = totals["cost_usd"]
                add_cost = float(usage["cost_usd"])
                totals["cost_usd"] = (
                    add_cost if current_cost is None else float(current_cost) + add_cost
                )
    return totals


def cartographer_analyze(
    client: OpenRouterClient,
    screenshot: np.ndarray,
) -> tuple[dict[str, Any], str]:
    """Send reference image + live screenshot to Gemma 12B.

    Returns (parsed spatial JSON, raw_text). No WorldState dependency —
    the vision model looks at the game directly and describes what it sees.

    The parsed dict carries ``_cartographer_usage`` (PERCEPT-1): the
    provider's token counts and cost for THIS call, or ``None`` when the
    provider supplied no usage block. Consumers that never read the key
    are unaffected.
    """
    img_b64 = screenshot_to_base64(screenshot)

    response = client.chat_completion(
        model="google/gemma-3-12b-it",
        messages=[
            {"role": "system", "content": CARTOGRAPHER_SYSTEM},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": CARTOGRAPHER_TEMPLATE},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{REFERENCE_IMAGE_B64}"
                        },
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{img_b64}"},
                    },
                ],
            },
        ],
        temperature=0.1,
        max_tokens=2048,
    )

    text = response.get("content", "")
    spatial = _extract_spatial_json(text)
    # PERCEPT-1: carry the provider's usage block out with the spatial data
    # instead of dropping it — the run summary needs vision tokens/cost.
    spatial["_cartographer_usage"] = _extract_vision_usage(response)
    return spatial, text


def _extract_spatial_json(text: str) -> dict[str, Any]:
    """Extract spatial observation JSON from model response.

    Handles markdown fences, leading/trailing text, and partial JSON.
    Much simpler than the old OBS_PATCH parser — just finds the JSON object.
    """
    text = text.strip()

    # Strip ``` fences
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:] if len(lines) > 1 else lines
        if lines and lines[-1].strip() in ("```", "```json", "```yaml"):
            lines = lines[:-1]
        text = "\n".join(lines)

    # Try whole-string JSON first
    try:
        return cast(dict[str, Any], json.loads(text))
    except (json.JSONDecodeError, ValueError):
        pass

    # Try finding JSON object with regex
    import re

    m = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if m:
        try:
            return cast(dict[str, Any], json.loads(m.group()))
        except (json.JSONDecodeError, ValueError):
            pass

    # Try YAML fallback. Import lazily so CLI parsing and preflight stay light.
    try:
        import yaml

        data = yaml.safe_load(text)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    return {"result": "unknown", "_parse_error": text[:500]}


# ── Controller response parsing (GAP-052) ───────────────────────────
# DeepSeek-family models emit their reasoning INLINE in the content string
# ("<think>...</think>" blocks, bare "</think>", "|end_of_thought|" markers,
# stray fragments after the closing brace), so json.loads() on the raw
# content failed and every cycle degraded to a blind A-press. Strip the
# noise, then take the first BALANCED JSON object — the old r"\{[^}]+\}"
# regex truncated at the first "}" and missed nested objects entirely.
_THINK_BLOCK_RE = re.compile(r"<think\b[^>]*>.*?</think\s*>", re.DOTALL | re.IGNORECASE)
_THINK_TAG_RE = re.compile(r"</?think\b[^>]*>", re.IGNORECASE)
_END_OF_TURN_RE = re.compile(r"\|\s*end[_a-z]*\s*\|", re.IGNORECASE)
# Trailing fragment after the JSON object: only fires on a run that starts at
# a marker character and contains no brace/quote-less JSON tail, so parsed
# objects (always brace-terminated) are never truncated.
_DIRTY_TAIL_RE = re.compile(
    r"(?:<\|?|\|)\s*(?:end[_a-z]*|think)?[^<|{}]*$", re.IGNORECASE
)


def _mask_json_strings(text: str) -> str:
    """Blank the bodies of double-quoted spans, keeping indexes and quotes.

    Lets the marker passes below tell a JSON string *value* from the response
    shell around it. An unbalanced quote (junk prose) simply leaves the rest of
    the text unmasked, where markers are still stripped.
    """
    out = list(text)
    in_string = False
    escaped = False
    for index, char in enumerate(out):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
                continue
            out[index] = "\x00"
        elif char == '"':
            in_string = True
    return "".join(out)


def _drop_marker_spans(text: str, pattern: re.Pattern[str]) -> str:
    """Delete every ``pattern`` match that sits outside a JSON string literal.

    A controller intent such as ``"intent": "walk to the |end| of the path"``
    is data and must survive; a trailing ``|end_of_thought|`` after the closing
    brace is transport noise and must not.
    """
    masked = _mask_json_strings(text)
    spans = [(match.start(), match.end()) for match in pattern.finditer(masked)]
    for start, end in reversed(spans):
        text = text[:start] + text[end:]
    return text


def _strip_model_noise(text: str) -> str:
    """Strip inline reasoning / end-of-turn tokens from a controller response.

    DeepSeek-family models emit their thinking INLINE inside the content
    string, which made ``json.loads`` fail and degraded every cycle to a
    blind A-press (GAP-052). Removed here, in order:

    - ``<think>...</think>`` blocks (inline or inside a ``` fence),
    - bare ``</think>`` / ``<think>`` tags with no block,
    - ``|end_of_thought|``-style end-of-turn markers,
    - trailing stray/partial marker fragments left after the closing brace
      (e.g. ``{"plan": ["UP"]} |end_of_th`` or a dangling ``<`` tail).

    Only runs that start at a marker character and reach the end of the text
    are dropped, and a JSON tail always ends with ``}`` — which the tail
    pattern refuses — so brace-terminated JSON is never truncated.
    """
    if not text:
        return ""
    cleaned = _THINK_BLOCK_RE.sub("", text)
    cleaned = _THINK_TAG_RE.sub("", cleaned)
    # Marker passes are quote-aware: only markers in the shell around the JSON
    # are removed, never a marker-shaped substring inside a JSON value.
    cleaned = _drop_marker_spans(cleaned, _END_OF_TURN_RE)
    cleaned = _drop_marker_spans(cleaned, _DIRTY_TAIL_RE)
    return cleaned.strip()


def _extract_first_json_object(text: str) -> str | None:
    """Return the first *balanced* ``{...}`` object in ``text`` (else None).

    Character scan with string/escape awareness: a ``}`` inside a JSON string
    does not close the object, and nested objects are returned whole. The
    previous ``\\{[^}]+\\}`` regex truncated at the first ``}`` and matched
    nothing at all for a response whose plan object nests another object.
    """
    start = text.find("{")
    while start != -1:
        extracted = _balanced_object_from(text, start)
        if extracted is not None:
            return extracted
        start = text.find("{", start + 1)
    return None


def _balanced_object_from(text: str, start: int) -> str | None:
    """Scan ``text`` from ``start`` for a balanced ``{...}`` (string-aware)."""
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def _load_controller_payload(text: str) -> Any | None:
    """Parse the JSON payload out of (noise-stripped) controller content.

    Direct ``json.loads`` first, so a clean response parses exactly as it did
    before; otherwise the first balanced object embedded in the content. The
    parsed value is returned as-is (any JSON type, all fields intact — the
    caller needs ``note`` / ``goal`` / ``study`` too), or ``None`` when
    nothing parses.
    """
    candidate = text.strip()
    if candidate:
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            pass
    obj = _extract_first_json_object(candidate)
    if obj is None:
        return None
    try:
        return json.loads(obj)
    except (json.JSONDecodeError, ValueError):
        return None


def _interpret_controller_response(
    text: str,
) -> tuple[str, dict[str, Any] | None]:
    """Classify a noise-stripped controller response body.

    Kinds mirror the pre-GAP-052 branches one-for-one:

    - ``plan`` — a ``{"plan": [...]}`` object (payload is the whole object);
    - ``button`` — a legacy ``{"button": "UP"}`` object;
    - ``unreadable`` — parseable JSON (or a non-object) carrying neither
      field: a blind A-press labelled ``parse_fallback``;
    - ``unparseable`` — no JSON value could be parsed at all: a blind
      A-press labelled ``parse_failure_fallback``.
    """
    payload = _load_controller_payload(text)
    if payload is None:
        return "unparseable", None
    if isinstance(payload, dict):
        if "plan" in payload:
            return "plan", payload
        if "button" in payload:
            return "button", payload
    return "unreadable", None


RECENT_DECISION_LIMIT = jev_client.RECENT_DECISION_LIMIT


def _compact_recent_text(value: Any, fallback: str) -> str:
    """Keep one prior-turn field short, scalar, and single-line."""
    text = " ".join(str(value if value not in (None, "") else fallback).split())
    return text[:160] or fallback


def _record_recent_decision(
    history: list[dict[str, Any]],
    event: dict[str, Any],
    *,
    outcome: str,
    agent_context: BoundedAgentContext | None = None,
    text_facts: list[Any] | None = None,
) -> dict[str, Any]:
    """Append one cheap decision summary and enforce the per-run window bound."""
    raw_plan = event.get("plan")
    raw_action = event.get("action")
    if raw_action in (None, "") and isinstance(raw_plan, list):
        raw_action = ", ".join(str(item) for item in raw_plan)

    raw_cycle = event.get("cycle")
    cycle: int = raw_cycle if isinstance(raw_cycle, int) else 0
    turn = {
        "cycle": cycle,
        "screen": _compact_recent_text(
            event.get("screen") or event.get("state"), "unknown"
        ),
        "action": _compact_recent_text(raw_action, "none"),
        "intent": _compact_recent_text(event.get("intent"), "none"),
        "outcome": _compact_recent_text(outcome, "unknown"),
    }
    history.append(turn)
    del history[:-RECENT_DECISION_LIMIT]
    if agent_context is not None:
        agent_context.record(
            cycle=cycle,
            decision=turn["intent"],
            action=turn["action"],
            result=turn["outcome"],
            text_facts=text_facts,
        )
    return turn


def _recent_decisions_block(history: list[dict[str, Any]]) -> str:
    """Render only the bounded prior-turn summaries for a reasoning request."""
    return jev_client.recent_decisions_block(
        history,
        limit=RECENT_DECISION_LIMIT,
    )


def controller_plan(
    client: OpenRouterClient,
    spatial_desc: dict[str, Any],
    last_button: str,
    last_result: str,
    blocked_dir: str = "",
    blocked_count: int = 0,
    max_actions: int = 6,
    screenshot: Any = None,
    frame_ref: str | None = None,
    goal: str = "",
    notes: str = "",
    last_dialog: str = "",
    study_result: str = "",
    boot_memory: str = "",
    model: str | None = None,
    recent_decisions: list[dict[str, Any]] | None = None,
    running_summary: str = "",
    world_facts: list[str] | None = None,
) -> dict[str, Any]:
    """Controller model (Luna via OpenRouter) outputs a movement PLAN.

    Now takes the cartographer's spatial JSON directly (adjacent tiles,
    visible_exits, player_facing, suggested_action) instead of an ASCII
    tile map. The model gets richer, more accurate spatial info.

    ``boot_memory`` (MEM-2) is the once-per-run BOOT MEMORY block built by
    ``_build_boot_memory_blocks()`` and appended to the system prompt; it is
    empty for a fresh store, in which case the prompt is byte-identical to
    the pre-MEM-2 form apart from the tool-filing lines.

    ``recent_decisions`` (S3) is the bounded, per-run prior-turn window. It
    rides in the user message because it changes every cycle, while the system
    prompt remains stable instructions plus boot memory.

    ``running_summary`` holds the capped compact form of turns that rolled out
    of that window. It is empty for legacy/direct callers.

    When `screenshot` is provided, the live game frame is attached as an
    image so Luna can use its own vision to see the screen.

    When `frame_ref` is provided (uuid of a previously-seen identical
    frame from the persistent FrameCache), NO image is attached — the
    prompt instead carries a text marker telling Luna this exact frame
    was already sent before, so it should rely on the spatial summary
    (identical visuals). Saves the image tokens on repeat sightings.

    ``model`` (GAP-052) selects the controller model; ``None`` resolves
    through ``resolve_controller_model()`` (env override, else the default
    Luna string), so the request is unchanged when no override is set.
    Response parsing strips inline reasoning tokens (``<think>`` blocks,
    end-of-turn markers) and takes the first balanced JSON object before
    falling back to a blind A-press; one retry with a larger completion
    budget is made when the first answer yields no plan.
    """
    resolved_model = resolve_controller_model(model)
    spatial_summary = _controller_spatial_summary(spatial_desc)
    system = _controller_system_prompt(max_actions=max_actions, boot_memory=boot_memory)
    msg = _controller_user_message(
        spatial_summary,
        last_button=last_button,
        last_result=last_result,
        blocked_dir=blocked_dir,
        blocked_count=blocked_count,
        goal=goal,
        notes=notes,
        last_dialog=last_dialog,
        study_result=study_result,
        world_facts=world_facts,
        running_summary=running_summary,
        recent_decisions=recent_decisions,
        max_actions=max_actions,
    )
    user_content = _controller_user_content(msg, screenshot=screenshot, frame_ref=frame_ref)

    response = client.chat_completion(
        model=resolved_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ],
        temperature=0.3,
        max_tokens=CONTROLLER_MAX_TOKENS,
        thinking={"type": "disabled"},
    )

    # PERCEPT-1: keep the provider's usage block for the run rollup. On the
    # retry path the usage from BOTH attempts is summed so the plan's cost
    # reflects every API call it took.
    plan_usage = _extract_vision_usage(response)

    text = _strip_model_noise(response.get("content") or "")
    kind, payload = _interpret_controller_response(text)
    if kind in ("unreadable", "unparseable"):
        # GAP-052(c): ONE retry with a larger completion budget — a truncated
        # or plan-less answer often completes on the second attempt. Exactly
        # one retry, then the same blind A-press fallback as before.
        retry = client.chat_completion(
            model=resolved_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
            temperature=0.3,
            max_tokens=CONTROLLER_MAX_TOKENS + CONTROLLER_RETRY_TOKEN_BUMP,
            thinking={"type": "disabled"},
        )
        retry_text = _strip_model_noise(retry.get("content") or "")
        retry_usage = _extract_vision_usage(retry)
        if retry_usage is not None:
            plan_usage = _sum_vision_usage(plan_usage, retry_usage)
        if retry_text:
            text = retry_text
            kind, payload = _interpret_controller_response(text)

    return _controller_plan_result(
        kind,
        payload,
        text=text,
        plan_usage=plan_usage,
        spatial_desc=spatial_desc,
    )


def _controller_spatial_summary(spatial_desc: dict[str, Any]) -> str:
    """Build the compact spatial summary string (map, tile, facing, exits)."""
    facing = spatial_desc.get("player_facing", "?")
    adj = spatial_desc.get("adjacent", {})
    exits = spatial_desc.get("visible_exits", [])
    suggested = spatial_desc.get("suggested_action", "")
    text = spatial_desc.get("text_content", [])
    map_name = spatial_desc.get("map_name", "Unknown")
    tile_x = spatial_desc.get("player_tile_x", "?")
    tile_y = spatial_desc.get("player_tile_y", "?")

    adj_str = ", ".join(
        f"{d}={adj.get(d, '?')}" for d in ["up", "down", "left", "right"]
    )
    exits_str = "; ".join(exits) if exits else "none visible"
    text_str = " | ".join(text) if text else "none"

    spatial_summary = (
        f"MAP: {map_name}\n"
        f"PLAYER TILE: x={tile_x}, y={tile_y}\n"
        f"PLAYER FACING: {facing}\n"
        f"ADJACENT TILES: {adj_str}\n"
        f"VISIBLE EXITS: {exits_str}\n"
        f"SCREEN TEXT: {text_str}\n"
        f"SUGGESTED ACTION: {suggested}"
    )
    navigation_hold = spatial_desc.get("navigation_hold")
    if isinstance(navigation_hold, dict) and navigation_hold.get("active"):
        visited_maps = ", ".join(
            str(name) for name in navigation_hold.get("visited_maps") or []
        )
        spatial_summary += (
            "\nNAVIGATION HOLD: transition "
            f"{navigation_hold.get('previous_map_name')} -> "
            f"{navigation_hold.get('current_map_name')} is complete; "
            f"never press {navigation_hold.get('blocked_return_direction')} because "
            "that traverses the completed edge backward. "
            f"Visited maps: {visited_maps or 'none'}."
        )
    return spatial_summary


def _controller_system_prompt(*, max_actions: int, boot_memory: str) -> str:
    """Assemble the controller system prompt (+ MEM-2 boot-memory injection).

    MEM-2: the run-start memory blocks ride in the system prompt (built once
    by the caller), never in the per-cycle user message.
    """
    system = (
        load_system_prompt(hint_level=HINT_LEVEL)
        + "\n\n"
        + (
            "You are controlling a Game Boy game player character.\n\n"
            "You receive a SPATIAL OBSERVATION describing what's around the player.\n"
            "Output a MOVEMENT PLAN — a sequence of button presses to execute.\n\n"
            "Respond with ONLY a JSON object:\n"
            '{"plan": ["UP","DOWN","LEFT","RIGHT","A","B","START","SELECT",...], "intent": "reason"}\n\n'
            "RULES:\n"
            f"- Maximum {max_actions} actions in the plan.\n"
            "- UP/DOWN/LEFT/RIGHT move one tile in that direction.\n"
            "- A interacts with adjacent objects/NPCs/doors.\n"
            "- B cancels, START opens menu.\n\n"
            "EXPLORATION STRATEGY:\n"
            "- Start with SHORT moves (2-3 tiles) in new areas.\n"
            "- MAX 3 of the SAME direction in a plan. Never 4+ of any direction.\n"
            "- If you hit a wall, switch directions immediately.\n"
            "- Walk toward visible exits (doors, stairs, paths).\n"
            "- If adjacent tile is 'wall' in one direction, do NOT try that direction.\n"
            "- If adjacent tile is 'door', walk into it (or press A on it).\n"
            "- If adjacent tile is 'npc', walk toward it and press A to talk.\n"
            "- If adjacent tile is 'stair', walk onto it.\n"
            "- When ALL directions are blocked (walls/objects all around): press A.\n"
            "- After interacting (A), next action should move away.\n"
            "- INDOOR rooms are small (3-6 tiles wide). Plan 2-3 tile moves.\n"
            "- OUTDOOR areas (grass, paths visible): 4-6 tile moves OK.\n\n"
            "MEMORY — you maintain your own knowledge in DuckBrain (persists across runs):\n"
            "- ACTIVE GOAL / RECENT NOTES / LAST DIALOG are injected each cycle.\n"
            "- Optional output fields (JSON only):\n"
            '  "note": a fact you just learned (NPC info, map info, objective, mechanic).\n'
            '  "goal": your current objective — include it when it changes or is new.\n'
            '  "study": a memory key to read next cycle, e.g. "/maps/oaks-lab" or "/guides/how-battles-work".\n'
            "- Use note/goal/study when you learn something — memory is how you win.\n"
            "- NEVER guess: read text, note what it says, act on it.\n"
            "TOOL FILING (where each output field is filed):\n"
            '- "study" → reads the requested key; found content is copied to '
            "/game/mechanics/* (the game itself; survives save resets).\n"
            '- "note" → /notes/overworld-<cycle>, this run\'s lessons, and '
            "/game/learning/<navigation|battle|strategy>.\n"
            '- "goal" → /goals/current + this run\'s lessons (your current intent).\n'
        )
    )
    if boot_memory:
        system = f"{system}\n\n{boot_memory}"
    return system


def _controller_user_message(
    spatial_summary: str,
    *,
    last_button: str,
    last_result: str,
    blocked_dir: str,
    blocked_count: int,
    goal: str,
    notes: str,
    last_dialog: str,
    study_result: str,
    world_facts: list[str] | None,
    running_summary: str,
    recent_decisions: list[dict[str, Any]] | None,
    max_actions: int,
) -> str:
    """Assemble the per-cycle controller user message (memory + history)."""
    blocked_msg = ""
    if blocked_dir and blocked_count >= 2:
        blocked_msg = (
            f"\n⚠️  WARNING: Previously pressed {blocked_dir} {blocked_count}+ times "
            f"with no progress. That direction is likely BLOCKED. "
            f"Do NOT include {blocked_dir} in your plan.\n"
        )

    msg = (
        f"{spatial_summary}\n\n"
        f"LAST BUTTON: {last_button or 'none'}\n"
        f"LAST RESULT: {last_result or 'unknown'}\n"
        f"{blocked_msg}\n"
    )

    memory_ctx = (
        "MEMORY CONTEXT:\n"
        f"ACTIVE GOAL: {goal or '(not set yet — set one when you learn an objective from text)'}\n"
        f"RECENT NOTES: {notes or 'none yet'}\n"
        f"LAST DIALOG: {last_dialog or 'none'}\n"
        f"STUDY RESULT: {study_result or '(none)'}\n"
    )
    world_memory_ctx = _world_memory_block(world_facts)
    recent_ctx = _recent_decisions_block(recent_decisions or [])
    msg += memory_ctx
    if world_memory_ctx:
        msg += f"\n{world_memory_ctx}\n"
    if running_summary:
        msg += f"\nEARLIER TURN SUMMARY (capped):\n{running_summary[:1200]}\n"
    if recent_ctx:
        msg += f"\n{recent_ctx}\n"
    msg += "\nOutput a movement plan (max {max_actions} actions). JSON only.\n".format(
        max_actions=max_actions
    )
    return msg


def _controller_user_content(
    msg: str,
    *,
    screenshot: Any,
    frame_ref: str | None,
) -> Any:
    """Build the user message content — image attach or text-only forms.

    Include the live screenshot for Luna's own vision. On a FrameCache hit
    (frame_ref set), attach a text marker instead of the image: Luna has seen
    this exact frame before, so the spatial summary + reference carry the same
    information at ~zero image tokens.
    """
    user_content: Any
    if frame_ref:
        ref_marker = (
            f"\n[SCREEN REF {frame_ref}] This exact game frame was sent to you "
            f"in a previous cycle — identical pixels (same location, same "
            f"dialog/state). Use the spatial summary above; no new image needed.\n"
        )
        user_content = f"{ref_marker}{msg}"
    elif screenshot is not None:
        try:
            img_b64 = screenshot_to_base64(screenshot)
            user_content = [
                {"type": "text", "text": msg},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{img_b64}"},
                },
            ]
        except Exception:
            user_content = msg
    else:
        user_content = msg
    return user_content


def _controller_plan_result(
    kind: str,
    payload: dict[str, Any] | None,
    *,
    text: str,
    plan_usage: dict[str, Any] | None,
    spatial_desc: dict[str, Any],
) -> dict[str, Any]:
    """Normalize the parsed controller answer into the plan dict the loop runs."""
    if kind == "plan" and payload is not None:
        payload["raw_response"] = text
        payload["vision_usage"] = plan_usage
        return _apply_navigation_hold_to_decision(payload, spatial_desc)
    if kind == "button" and payload is not None:
        return _apply_navigation_hold_to_decision(
            {
                "plan": [payload["button"]],
                "intent": payload.get("intent", ""),
                "raw_response": text,
                "vision_usage": plan_usage,
            },
            spatial_desc,
        )
    if kind == "unreadable":
        return {
            "plan": ["A"],
            "intent": "parse_fallback",
            "raw_response": text,
            "vision_usage": plan_usage,
        }
    return {
        "plan": ["A"],
        "intent": "parse_failure_fallback",
        "raw_response": text,
        "vision_usage": plan_usage,
    }


# ── Main ────────────────────────────────────────────────────────────


def _resolve_boot_state(arg: str | None) -> Path | None:
    """Resolve the checkpoint to boot from, or None to intro-bypass.

    - ``None`` (flag omitted): use ``DEFAULT_BOOT_STATE`` when it exists.
    - ``"skip"``: never boot from a checkpoint (legacy intro bypass).
    - otherwise: treat the argument as a literal path.
    Returns ``None`` when no usable checkpoint file exists.
    """
    if arg is not None and arg.lower() == "skip":
        return None
    candidate = Path(arg) if arg else DEFAULT_BOOT_STATE
    return candidate if candidate.is_file() else None


# Controller intents that mean the model never authored the plan: the
# parser could not read a plan out of the response and the runner blind-
# pressed A instead (GAP-053). Any other intent — including an empty or
# absent one — comes from a real controller response.
FALLBACK_INTENTS: frozenset[str] = frozenset(
    {"parse_fallback", "parse_failure_fallback"}
)


def _classify_decision_intents(
    results: list[dict[str, Any]],
) -> tuple[int, int]:
    """Split the run's controller decisions into (real, fallback) counts.

    Only rows carrying an ``intent`` key are controller decisions: the
    main loop stamps it on every plan entry, while event rows
    (memory_note/goal/study, giveup_walk), error rows and per-button
    execution rows never set it. A decision whose intent is one of
    ``FALLBACK_INTENTS`` is a blind A-press the controller never authored;
    every other decision is a real one.

    Returns ``(real_decisions, fallback_decisions)``.
    """
    real = 0
    fallback = 0
    for row in results:
        if "intent" not in row:
            continue
        intent = row.get("intent")
        if isinstance(intent, str) and intent in FALLBACK_INTENTS:
            fallback += 1
        else:
            real += 1
    return real, fallback


# JEV-1 (PRD v3 AC-1): the per-run autonomy counters live at the END of the
# run log as their own row, so `grep -c '"autonomy_ratio"'` over
# `cron_logs/run_<id>.jsonl` is the run's autonomy proof.
AUTONOMY_LOG_EVENT = "run_autonomy"
JEV_DEGRADATION_LOG_EVENT = "run_degradation"
JEV_DEGRADED_RATE = 0.5
JEV_DEGRADED_MIN_DECISIONS = 5


def _decision_map_key(row: dict[str, Any]) -> tuple[str, int | str] | None:
    """Return a stable map identity from one stamped decision row."""
    map_id = row.get("map_id")
    if isinstance(map_id, int) and not isinstance(map_id, bool):
        return ("id", map_id)
    map_name = row.get("map_name")
    if isinstance(map_name, str) and map_name:
        return ("name", map_name)
    return None


def _decision_tile_state(
    row: dict[str, Any],
) -> tuple[str, int | str, int, int] | None:
    """Return the stamped map/tile state, or None when it is not observable."""
    map_key = _decision_map_key(row)
    tile_x = row.get("player_tile_x")
    tile_y = row.get("player_tile_y")
    if (
        map_key is None
        or not isinstance(tile_x, int)
        or isinstance(tile_x, bool)
        or not isinstance(tile_y, int)
        or isinstance(tile_y, bool)
    ):
        return None
    return (*map_key, tile_x, tile_y)


def _autonomy_counters(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Derive the run's autonomy block from the per-decision rows (JEV-1).

    PRD v3 AC-1: the counters are COUNTED from the rows the main loop
    stamped, never incremented by the summary printer — a run that made no
    decisions reports ``decisions_total == 0`` and ``autonomy_ratio is
    None`` instead of a fabricated (or vacuously perfect) ratio.

    The population is exactly ``_classify_decision_intents``'s: rows carrying
    an ``intent`` key. Event rows (memory_note/goal/study, giveup_walk,
    recovery, state_saved), error rows and per-button execution rows never
    set ``intent`` and move no counter here.

    EFF-1 derives movement efficiency in the SAME pass and from the SAME
    stamped decision-row population. The summary printer never increments a
    transition or backtrack counter: otherwise a repeated wrong decision could
    still report perfect autonomy without exposing that the player did not
    move. A map transition is each comparable consecutive decision pair whose
    stamped map changed, matching S0's per-transition denominator. A backtrack
    is a comparable map/tile state that is unchanged or was visited earlier.

    Returns the autonomy counters plus ``map_transitions_observed``,
    ``decisions_per_map_transition``, ``state_comparisons``,
    ``backtrack_events`` and ``backtrack_rate``. Ratios are rounded to 4 dp and
    remain ``None`` when their denominator is unavailable or zero.
    """
    decisions_total = 0
    jev_answered = 0
    escalated = 0
    jev_transport_failures = 0
    jev_errors: list[str] = []
    escalated_by_class: Counter[str | None] = Counter()
    scenario_resolved_classes: set[str] = set()
    handoff_triggers: Counter[str] = Counter()
    handoff_blocked = 0
    memory_navigation_hits = 0
    memory_navigation_fallbacks = 0
    agentic_tool_calls = 0
    pipeline_counts: Counter[str] = Counter()
    map_transitions_observed = 0
    map_transition_comparisons = 0
    previous_map: tuple[str, int | str] | None = None
    state_comparisons = 0
    backtrack_events = 0
    previous_state: tuple[str, int | str, int, int] | None = None
    visited_states: set[tuple[str, int | str, int, int]] = set()

    for row in results:
        if "intent" not in row:
            continue
        decisions_total += 1
        map_transitions_observed, map_transition_comparisons, previous_map = (
            _count_map_transition(
                row,
                map_transitions_observed,
                map_transition_comparisons,
                previous_map,
            )
        )
        state_comparisons, backtrack_events, previous_state, visited_states = (
            _count_tile_state(
                row,
                state_comparisons,
                backtrack_events,
                previous_state,
                visited_states,
            )
        )
        pipeline = row.get("pipeline")
        if isinstance(pipeline, str) and pipeline:
            pipeline_counts[pipeline] += 1
        agentic_tool_calls += _as_int(row.get("agentic_tool_calls"))
        if row.get("jev_answered"):
            jev_answered += 1
        jev_transport_failures, jev_errors = _count_jev_failure(
            row, jev_transport_failures, jev_errors
        )
        handoff_blocked, handoff_triggers = _count_handoff(row, handoff_triggers, handoff_blocked)
        scenario_resolved_classes = _count_scenario_resolution(row, scenario_resolved_classes)
        escalated, escalated_by_class = _count_escalation(row, escalated, escalated_by_class)
        memory_navigation_hits, memory_navigation_fallbacks = (
            _count_memory_navigation(row, memory_navigation_hits, memory_navigation_fallbacks)
        )

    ratio, rates, jev_failure_rate, degraded, decisions_per_map_transition, backtrack_rate = _autonomy_rates(
        decisions_total=decisions_total,
        jev_answered=jev_answered,
        jev_transport_failures=jev_transport_failures,
        escalated=escalated,
        escalated_by_class=escalated_by_class,
        scenario_resolved_classes=scenario_resolved_classes,
        map_transitions_observed=map_transitions_observed,
        state_comparisons=state_comparisons,
        backtrack_events=backtrack_events,
    )
    return {
        "decisions_total": decisions_total,
        "jev_answered": jev_answered,
        "escalated": escalated,
        "autonomy_ratio": ratio,
        "escalation_rate_by_missing_class": rates,
        "jev_transport_failures": jev_transport_failures,
        "jev_transport_failure_rate": jev_failure_rate,
        "jev_errors": jev_errors[:3],
        "degraded": degraded,
        "handoff_trigger_counts": dict(handoff_triggers),
        "handoff_blocked": handoff_blocked,
        # S6 NAV-MEM: navigation decisions answered from ``world/path/*`` memory
        # vs those that were consulted and fell through to the existing path.
        "memory_navigation_hits": memory_navigation_hits,
        "memory_navigation_fallbacks": memory_navigation_fallbacks,
        # S7 BENCH-PAR: derive the run-level tool-surface stamp from the same
        # decision-row population as every other autonomy counter. This keeps
        # benchmark summaries directly comparable with their source rows.
        "agentic_tool_calls": agentic_tool_calls,
        "pipeline_counts": dict(pipeline_counts),
        # EFF-1: evidence-bearing cycle efficiency, counted from decision rows.
        "map_transitions_observed": map_transitions_observed,
        "map_transition_comparisons": map_transition_comparisons,
        "decisions_per_map_transition": decisions_per_map_transition,
        "state_comparisons": state_comparisons,
        "backtrack_events": backtrack_events,
        "backtrack_rate": backtrack_rate,
    }


def _count_jev_failure(
    row: dict[str, Any],
    failures: int,
    errors: list[str],
) -> tuple[int, list[str]]:
    """Count a JEV transport failure and collect its (unique) error text."""
    if row.get("jev_ok") is not False:
        return failures, errors
    failures += 1
    error = row.get("jev_error")
    if isinstance(error, str) and error and error not in errors:
        errors.append(error)
    return failures, errors


def _count_handoff(
    row: dict[str, Any],
    triggers: Counter[str],
    blocked: int,
) -> tuple[int, Counter[str]]:
    """Count handoff provenance: which trigger fired, how often policy refused it.

    Counted from the rows, never incremented by the printer — the same rule
    the other counters follow.
    """
    trigger = row.get("handoff_trigger")
    if isinstance(trigger, str) and trigger not in ("", "none"):
        triggers[trigger] += 1
    if row.get("handoff_allowed") is False:
        blocked += 1
    return blocked, triggers


def _count_scenario_resolution(
    row: dict[str, Any],
    resolved_classes: set[str],
) -> set[str]:
    """Record the class a scenario patch actually resolved (evidence-bearing)."""
    reported_class = row.get("reported_missing_class")
    if row.get("scenario_patch_applied") and isinstance(reported_class, str):
        resolved_classes.add(reported_class)
    return resolved_classes


def _count_escalation(
    row: dict[str, Any],
    escalated: int,
    by_class: Counter[str | None],
) -> tuple[int, Counter[str | None]]:
    """Count an escalated decision row, bucketed by its missing class."""
    if not row.get("escalated"):
        return escalated, by_class
    escalated += 1
    missing_class = row.get("missing_class")
    by_class[missing_class if isinstance(missing_class, str) else None] += 1
    return escalated, by_class


def _autonomy_rates(
    *,
    decisions_total: int,
    jev_answered: int,
    jev_transport_failures: int,
    escalated: int,
    escalated_by_class: Counter[str | None],
    scenario_resolved_classes: set[str],
    map_transitions_observed: int,
    state_comparisons: int,
    backtrack_events: int,
) -> tuple[float | None, dict[str | None, float], float, bool, float | None, float | None]:
    """Derive the ratio/rate tail of the autonomy block.

    Returns ``(autonomy_ratio, rates, jev_failure_rate, degraded,
    decisions_per_map_transition, backtrack_rate)``. Ratios are rounded to 4 dp
    and remain ``None`` when their denominator is unavailable or zero.
    """
    ratio: float | None = (
        round(jev_answered / decisions_total, 4) if decisions_total else None
    )
    rates: dict[str | None, float] = (
        {
            missing_class: round(count / escalated, 4)
            for missing_class, count in escalated_by_class.items()
        }
        if escalated
        else {}
    )
    # AC-7's zero is evidence-bearing rather than fabricated: only a decision
    # row that actually consulted a matching scenario can add its class here.
    for resolved_class in sorted(scenario_resolved_classes):
        rates.setdefault(resolved_class, 0.0)
    raw_jev_failure_rate = (
        jev_transport_failures / decisions_total if decisions_total else 0.0
    )
    jev_failure_rate = round(raw_jev_failure_rate, 4)
    degraded = (
        decisions_total >= JEV_DEGRADED_MIN_DECISIONS
        and raw_jev_failure_rate > JEV_DEGRADED_RATE
    )
    decisions_per_map_transition = (
        round(decisions_total / map_transitions_observed, 4)
        if decisions_total and map_transitions_observed
        else None
    )
    backtrack_rate = (
        round(backtrack_events / state_comparisons, 4) if state_comparisons else None
    )
    return (
        ratio,
        rates,
        jev_failure_rate,
        degraded,
        decisions_per_map_transition,
        backtrack_rate,
    )


def _count_map_transition(
    row: dict[str, Any],
    transitions: int,
    comparisons: int,
    previous_map: tuple[str, int | str] | None,
) -> tuple[int, int, tuple[str, int | str] | None]:
    """Count one decision row's map transition against the previous row.

    Do not bridge an unobservable decision: that would invent a map
    transition between two rows that were not consecutive evidence.
    """
    map_key = _decision_map_key(row)
    if map_key is None:
        return transitions, comparisons, None
    if previous_map is not None:
        comparisons += 1
        if map_key != previous_map:
            transitions += 1
    return transitions, comparisons, map_key


def _count_tile_state(
    row: dict[str, Any],
    comparisons: int,
    backtracks: int,
    previous_state: tuple[str, int | str, int, int] | None,
    visited_states: set[tuple[str, int | str, int, int]],
) -> tuple[int, int, tuple[str, int | str, int, int] | None, set[tuple[str, int | str, int, int]]]:
    """Count one decision row's tile state against history for backtracking."""
    state = _decision_tile_state(row)
    if state is None:
        return comparisons, backtracks, None, visited_states
    if previous_state is not None:
        comparisons += 1
        if state == previous_state or state in visited_states:
            backtracks += 1
    visited_states.add(state)
    return comparisons, backtracks, state, visited_states


def _count_memory_navigation(
    row: dict[str, Any],
    hits: int,
    fallbacks: int,
) -> tuple[int, int]:
    """Count a row's S6 NAV-MEM route outcome (hit vs miss/error fallback).

    A navigation decision either replayed a proven route from
    ``world/path/*`` (hit) or was consulted and fell through to the
    existing path (miss/error). Counted from the rows, never incremented
    by the summary printer.
    """
    route = row.get("memory_navigation")
    if isinstance(route, dict):
        if route.get("result") == "hit" and route.get("key"):
            hits += 1
        elif route.get("result") in ("miss", "error"):
            fallbacks += 1
    return hits, fallbacks


def teacher_escalation_records(results: list[dict[str, Any]]) -> dict[str, int]:
    """Count JEV-2 teacher proof rows without changing decision semantics."""
    rows = [row for row in results if row.get("event") == "teacher_escalation"]
    return {
        "count": len(rows),
        "improved": sum(bool(row.get("improved")) for row in rows),
    }


def _format_autonomy_tail(autonomy: dict[str, Any] | None) -> str:
    """Render the JEV-1 autonomy tail appended to the summary line.

    Shape: ``autonomy=J/D (E escalated)``. With no decision rows — or an
    older caller that supplies no block — the ratio prints as ``n/a``: AC-1
    forbids inventing a number the run cannot back up.

    S6 NAV-MEM appends ``nav-mem: H hits/F fallbacks`` on EVERY summary (even
    at zero) so the metric is visible without a separate probe.
    """
    if not autonomy:
        return (
            "autonomy=n/a (0 decisions, 0 escalated) | efficiency: n/a "
            "dec/map-transition, backtrack n/a | nav-mem: 0 hits/0 fallbacks"
        )
    decisions_total = _as_int(autonomy.get("decisions_total"))
    jev_answered = _as_int(autonomy.get("jev_answered"))
    escalated = _as_int(autonomy.get("escalated"))
    nav_tail = (
        f" | nav-mem: {_as_int(autonomy.get('memory_navigation_hits'))} hits/"
        f"{_as_int(autonomy.get('memory_navigation_fallbacks'))} fallbacks"
    )
    raw_decisions_per_transition = autonomy.get("decisions_per_map_transition")
    decisions_per_transition = (
        f"{float(raw_decisions_per_transition):.2f}"
        if isinstance(raw_decisions_per_transition, (int, float))
        and not isinstance(raw_decisions_per_transition, bool)
        else "n/a"
    )
    raw_backtrack_rate = autonomy.get("backtrack_rate")
    backtrack = (
        f"{float(raw_backtrack_rate):.0%}"
        if isinstance(raw_backtrack_rate, (int, float))
        and not isinstance(raw_backtrack_rate, bool)
        else "n/a"
    )
    efficiency_tail = (
        f" | efficiency: {decisions_per_transition} dec/map-transition, "
        f"backtrack {backtrack}"
    )
    if not decisions_total:
        return (
            f"autonomy=n/a (0 decisions, {escalated} escalated)"
            f"{efficiency_tail}{nav_tail}"
        )
    tail = f"autonomy={jev_answered}/{decisions_total} ({escalated} escalated)"
    if autonomy.get("degraded"):
        failures = _as_int(autonomy.get("jev_transport_failures"))
        rate = float(autonomy.get("jev_transport_failure_rate") or 0.0)
        tail += (
            f" | JEV DEGRADED: {failures}/{decisions_total} transport failures "
            f"({rate:.0%})"
        )
    return tail + efficiency_tail + nav_tail


def _write_autonomy_row(
    log_file: TextIO,
    run_id: str,
    autonomy: dict[str, Any],
    teacher: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Append the JEV-1 autonomy block as one JSON line to the run log.

    Written with the same ``json.dumps(row, default=str)`` idiom as every
    other row in ``cron_logs/run_<id>.jsonl``. The row is deliberately NOT
    appended to ``results``: that list's length is the legacy ``Done. N
    actions.`` count and the DuckBrain ``cycles``/ladder input, so adding a
    summary row to it would silently inflate both.

    Returns the row that was written (for callers/tests to assert on).
    """
    pipeline_counts = autonomy.get("pipeline_counts", {})
    if not isinstance(pipeline_counts, dict):
        pipeline_counts = {}
    pipelines = [str(name) for name, count in pipeline_counts.items() if count]
    pipeline = pipelines[0] if len(pipelines) == 1 else ("mixed" if pipelines else None)
    row: dict[str, Any] = {
        "run_id": run_id,
        "event": AUTONOMY_LOG_EVENT,
        "decisions_total": _as_int(autonomy.get("decisions_total")),
        "jev_answered": _as_int(autonomy.get("jev_answered")),
        "escalated": _as_int(autonomy.get("escalated")),
        "autonomy_ratio": autonomy.get("autonomy_ratio"),
        "escalation_rate_by_missing_class": autonomy.get(
            "escalation_rate_by_missing_class", {}
        ),
        "jev_transport_failures": _as_int(autonomy.get("jev_transport_failures")),
        "jev_transport_failure_rate": autonomy.get("jev_transport_failure_rate", 0.0),
        "degraded": bool(autonomy.get("degraded")),
        "teacher_escalations": teacher or {"count": 0, "improved": 0},
        # M5: the mode AND the effective handoff policy are recorded on the run
        # row, so a run's decision architecture is recoverable from its log
        # alone — not only from the command line that produced it.
        "decision_mode": DECISION_MODE,
        "decision_mode_family": current_mode_family(),
        # S7 BENCH-PAR: the run summary carries the same tool-surface fields as
        # every decision row, so benchmark consumers need not infer the surface
        # from a mode spelling or silently compare unlike logs.
        "agentic_tools_enabled": _model_tools_enabled(DECISION_MODE),
        "agentic_tool_calls": _as_int(autonomy.get("agentic_tool_calls")),
        "pipeline": pipeline,
        "pipeline_counts": pipeline_counts,
        # EFF-1 mirrors the counted movement evidence onto the run-level row
        # consumed by BENCH-PAR; benchmark episodes need no second inference.
        "map_transitions_observed": _as_int(autonomy.get("map_transitions_observed")),
        "map_transition_comparisons": _as_int(
            autonomy.get("map_transition_comparisons")
        ),
        "decisions_per_map_transition": autonomy.get("decisions_per_map_transition"),
        "state_comparisons": _as_int(autonomy.get("state_comparisons")),
        "backtrack_events": _as_int(autonomy.get("backtrack_events")),
        "backtrack_rate": autonomy.get("backtrack_rate"),
        "handoff_policy": dict(HANDOFF_POLICY),
        # Which triggers fired this run, and how often the policy refused one.
        # Counted from the decision rows by _autonomy_counters.
        "handoff_trigger_counts": autonomy.get("handoff_trigger_counts", {}),
        "handoff_blocked": _as_int(autonomy.get("handoff_blocked")),
        # S6 NAV-MEM: navigation decisions answered from ``world/path/*`` memory
        # vs those consulted and left to the existing path.
        "memory_navigation_hits": _as_int(autonomy.get("memory_navigation_hits")),
        "memory_navigation_fallbacks": _as_int(
            autonomy.get("memory_navigation_fallbacks")
        ),
    }
    log_file.write(json.dumps(row, default=str) + "\n")
    log_file.flush()
    return row


def _write_degradation_row(
    log_file: TextIO,
    run_id: str,
    autonomy: dict[str, Any],
) -> dict[str, Any] | None:
    """Append a queryable row only when JEV transport health crossed the gate."""
    if not autonomy.get("degraded"):
        return None
    failures = _as_int(autonomy.get("jev_transport_failures"))
    jev_errors = list(autonomy.get("jev_errors") or [])[:3]
    row: dict[str, Any] = {
        "run_id": run_id,
        "event": JEV_DEGRADATION_LOG_EVENT,
        "failures": failures,
        "jev_transport_failures": failures,
        "decisions": _as_int(autonomy.get("decisions_total")),
        "rate": autonomy.get("jev_transport_failure_rate", 0.0),
        "threshold": JEV_DEGRADED_RATE,
        "min_decisions": JEV_DEGRADED_MIN_DECISIONS,
        "jev_errors": jev_errors,
        "errors": jev_errors,
    }
    log_file.write(json.dumps(row, default=str) + "\n")
    log_file.flush()
    return row


def _format_summary(
    run_id: str,
    n_actions: int,
    screens: set[str],
    lock_warn_cycles: int,
    total_cycles: int,
    distinct_tiles: int,
    real_decisions: int = 0,
    fallback_decisions: int = 0,
    autonomy: dict[str, Any] | None = None,
    teacher: dict[str, int] | None = None,
    movement_progress_cycles: int = 0,
    movement_observed_cycles: int = 0,
    vision_usage: dict[str, Any] | None = None,
) -> str:
    """Format the final summary line, including the per-run lock-rate.

    ``real_decisions``/``fallback_decisions`` (GAP-053) split the run's
    controller decisions by intent class. They are APPENDED to the line so
    the historical ``Done. N actions.`` shape — and every log parser keyed
    on it — stays intact.

    ``autonomy`` (JEV-1) is the block from ``_autonomy_counters`` and is
    appended after the GAP-053 counters. The GAP-053 computation and wording
    are unchanged. ``movement_progress_cycles`` (DF-USE-1) is separately
    derived from consecutive RAM tile observations, never from decisions.

    ``vision_usage`` (PERCEPT-1) is the per-run rollup from
    ``_rollup_vision_usage`` — vision tokens and cost for the whole run —
    appended after movement progress so the existing tail wording and every
    parser keyed on it stay byte-identical.
    """
    lock_rate = lock_warn_cycles / total_cycles
    movement_rate = (
        movement_progress_cycles / movement_observed_cycles
        if movement_observed_cycles
        else 0.0
    )
    teacher_tail = ""
    if teacher and _as_int(teacher.get("count")):
        teacher_tail = (
            f" | teacher={_as_int(teacher.get('count'))} escalations "
            f"({_as_int(teacher.get('improved'))} improved)"
        )
    vision_tail = ""
    if vision_usage is not None:
        cost = vision_usage.get("cost_usd")
        cost_str = f"${float(cost):.6f}" if cost is not None else "unknown"
        image_tokens = vision_usage.get("image_tokens")
        image_str = str(int(image_tokens)) if image_tokens is not None else "unknown"
        vision_tail = (
            f" | vision: {int(vision_usage.get('prompt_tokens') or 0)} prompt + "
            f"{int(vision_usage.get('completion_tokens') or 0)} completion tokens "
            f"({image_str} image) across {int(vision_usage.get('calls') or 0)} calls, "
            f"cost {cost_str}"
        )
    return (
        f"[{run_id}] Done. {n_actions} actions. Screens: {screens} "
        f"| lock-rate: {lock_warn_cycles}/{total_cycles} cycles with "
        f"direction-lock warnings ({lock_rate:.0%}) "
        f"| distinct tiles: {distinct_tiles} "
        f"| real_decisions={real_decisions} "
        f"fallback_decisions={fallback_decisions} "
        f"{_format_autonomy_tail(autonomy)}"
        f"{teacher_tail}"
        f" | movement-progress: {movement_progress_cycles}/"
        f"{movement_observed_cycles} comparable cycles changed tile "
        f"({movement_rate:.0%})"
        f"{vision_tail}"
    )


def _record_run_memory(
    run_id: str,
    results: list[dict[str, Any]],
    ram_reader: Any = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Best-effort DuckBrain record of one completed run and readable RAM truth."""
    from src.core import duckbrain_client

    try:
        extra = extra or {}
        events = Counter(
            event
            for row in results
            if isinstance((event := row.get("event")), str) and event
        )
        screens = Counter(
            screen
            for row in results
            if isinstance((screen := row.get("screen")), str) and screen
        )

        distinct_maps = _distinct_map_names(results)
        battle_events = _count_battle_events(results)

        # GAP-053: split controller decisions by intent class so a run that
        # burned its budget on blind A-presses is visible as such.
        real_decisions, fallback_decisions = _classify_decision_intents(results)
        autonomy = _autonomy_counters(results)

        ladder = _run_ladder(events, battle_events, distinct_maps)
        log_path = str(extra.get("log_path", ""))
        summary_attributes = _run_summary_attributes(
            results,
            extra,
            events=events,
            screens=screens,
            real_decisions=real_decisions,
            fallback_decisions=fallback_decisions,
            autonomy=autonomy,
            distinct_maps=distinct_maps,
            battle_events=battle_events,
            log_path=log_path,
            ladder=ladder,
        )

        duckbrain_client.remember(
            key=f"/game/runs/{run_id}/summary",
            domain="game/runs",
            attributes=summary_attributes,
            embedding_text=(
                f"Run {run_id}: {len(results)} cycles, "
                f"{summary_attributes['n_actions']} actions, "
                f"progress {ladder['map_progress'] or 'unknown'}"
            ),
            namespace="pokemon-global",
        )

        _record_run_lessons(duckbrain_client, run_id, results)
        if ram_reader is not None:
            _record_ram_truth(duckbrain_client, ram_reader)
        _record_run_index(duckbrain_client, run_id, results, ladder)
    except Exception as exc:
        safe_print(f"[MEM] recorder failed: {exc}")


def _distinct_map_names(results: list[dict[str, Any]]) -> list[str]:
    """Ordered distinct map names visited during the run (last 40 kept)."""
    distinct_maps: list[str] = []
    for row in results:
        map_name = row.get("map_name")
        if isinstance(map_name, str) and map_name and map_name not in distinct_maps:
            distinct_maps.append(map_name)
    return distinct_maps[-40:]


def _count_battle_events(results: list[dict[str, Any]]) -> int:
    """Count TOP-LEVEL battle event rows (DF-AIPP-2).

    Every battle transition writes its own row straight into ``results`` — one
    ``battle_start`` when the battle screen is entered and one
    ``battle_end`` when it is left — while the cycle row of that same
    iteration ALSO carries the StateWindow transitions in its nested
    ``battle_events`` list. Counting both described the same battles
    twice (run dgf_0923b: 2 top-level rows + 4 nested events summed to a
    ladder of 6 for a single battle), so the nested lists are skipped
    entirely: the top-level rows cover the start+end transitions
    deterministically. The ladder key stays present (0 when no battle).
    """
    return sum(
        1 for row in results if str(row.get("event", "")).startswith("battle_")
    )


def _run_ladder(
    events: Counter[str],
    battle_events: int,
    distinct_maps: list[str],
) -> dict[str, Any]:
    """Build the run's ladder summary (memory/battle progress + starter)."""
    return {
        "memory_events": sum(
            events[name] for name in ("memory_note", "memory_goal", "memory_study")
        ),
        "battle_events": battle_events,
        "map_progress": distinct_maps[-1] if distinct_maps else None,
        "starter_picked": events["starter_picked"] > 0,
    }


def _run_summary_attributes(
    results: list[dict[str, Any]],
    extra: dict[str, Any],
    *,
    events: Counter[str],
    screens: Counter[str],
    real_decisions: int,
    fallback_decisions: int,
    autonomy: dict[str, Any],
    distinct_maps: list[str],
    battle_events: int,
    log_path: str,
    ladder: dict[str, Any],
) -> dict[str, Any]:
    """Assemble the /game/runs/<id>/summary attribute payload."""
    summary_attributes: dict[str, Any] = {
        "events": dict(events),
        "screens": dict(screens),
        "n_actions": int(
            extra.get(
                "n_actions",
                sum(bool(row.get("action")) for row in results),
            )
        ),
        "real_decisions": real_decisions,
        "fallback_decisions": fallback_decisions,
        "autonomy": autonomy,
        "degraded": bool(autonomy.get("degraded")),
        "degradation": (
            {
                "event": JEV_DEGRADATION_LOG_EVENT,
                "jev_transport_failures": autonomy["jev_transport_failures"],
                "decisions": autonomy["decisions_total"],
                "rate": autonomy["jev_transport_failure_rate"],
                "threshold": JEV_DEGRADED_RATE,
                "errors": autonomy["jev_errors"],
            }
            if autonomy.get("degraded")
            else None
        ),
        "distinct_maps": distinct_maps,
        "battle_events": battle_events,
        "cycles": len(results),
        "log_path": str(extra.get("log_path", log_path)),
        "ladder": ladder,
    }
    if "distinct_tiles" in extra:
        summary_attributes["distinct_tiles"] = int(extra["distinct_tiles"])
    if "movement_progress_cycles" in extra or "movement_observed_cycles" in extra:
        movement_progress_cycles = int(extra.get("movement_progress_cycles", 0))
        movement_observed_cycles = int(extra.get("movement_observed_cycles", 0))
        summary_attributes.update(
            {
                "movement_progress_cycles": movement_progress_cycles,
                "movement_observed_cycles": movement_observed_cycles,
                "movement_progress_rate": round(
                    movement_progress_cycles / movement_observed_cycles, 4
                )
                if movement_observed_cycles
                else 0.0,
            }
        )
    if "summary" in extra:
        summary_attributes["summary"] = str(extra["summary"])
    return summary_attributes


def _record_run_lessons(
    duckbrain_client: Any,
    run_id: str,
    results: list[dict[str, Any]],
) -> None:
    """Persist the run's collected notes and goals (last 20 of each)."""
    notes = [
        str(row["note"])
        for row in results
        if row.get("event") == "memory_note" and row.get("note")
    ][-20:]
    goals = [
        str(row["goal"])
        for row in results
        if row.get("event") == "memory_goal" and row.get("goal")
    ][-20:]
    if notes or goals:
        duckbrain_client.remember(
            key=f"/game/runs/{run_id}/lessons",
            domain="game/runs",
            attributes={"notes": notes, "goals": goals},
            embedding_text=" | ".join([*notes, *goals])[:2000],
            namespace="pokemon-global",
        )


def _record_ram_truth(duckbrain_client: Any, ram_reader: Any) -> None:
    """Persist readable RAM truth: party, items, and current location."""
    try:
        party = {
            "party_count": ram_reader.party_count(),
            "species_hint": ram_reader.first_party_species_hint(),
        }
        duckbrain_client.remember(
            key="/game/save/party",
            domain="game/save",
            attributes=party,
            embedding_text=(
                f"Party count {party['party_count']}; "
                f"first species {party['species_hint'] or 'unknown'}"
            ),
            namespace="pokemon-global",
        )
    except Exception as exc:
        safe_print(f"[MEM] save party skipped: {exc}")

    _record_items(duckbrain_client, ram_reader)
    _record_location(duckbrain_client, ram_reader)


def _record_items(duckbrain_client: Any, ram_reader: Any) -> None:
    """Persist the readable inventory snapshot (best-effort)."""
    item_reader = next(
        (
            method
            for name in ("read_items", "read_inventory", "inventory")
            if callable((method := getattr(ram_reader, name, None)))
        ),
        None,
    )
    if item_reader is not None:
        try:
            items = item_reader()
            if isinstance(items, list):
                items = items[-40:]
            duckbrain_client.remember(
                key="/game/save/items",
                domain="game/save",
                attributes={"items": items},
                embedding_text=f"Current items: {items}",
                namespace="pokemon-global",
            )
        except Exception as exc:
            safe_print(f"[MEM] save items skipped: {exc}")
    else:
        safe_print("[MEM] save items skipped: no public item reader")


def _record_location(duckbrain_client: Any, ram_reader: Any) -> None:
    """Persist the current map/position snapshot (best-effort)."""
    try:
        location = {
            "map_id": ram_reader.current_map_id(),
            "map_name": ram_reader.current_map_name(),
            "pos": {
                "x": ram_reader.player_tile_x(),
                "y": ram_reader.player_tile_y(),
            },
        }
        duckbrain_client.remember(
            key="/game/save/location",
            domain="game/save",
            attributes=location,
            embedding_text=(
                f"At {location['map_name']} map {location['map_id']} "
                f"tile {location['pos']['x']},{location['pos']['y']}"
            ),
            namespace="pokemon-global",
        )
    except Exception as exc:
        safe_print(f"[MEM] save location skipped: {exc}")


def _record_run_index(
    duckbrain_client: Any,
    run_id: str,
    results: list[dict[str, Any]],
    ladder: dict[str, Any],
) -> None:
    """Prepend this run's digest to the recent-runs index (last 10 kept)."""
    previous = duckbrain_client.get(
        key="/game/runs/index",
        namespace="pokemon-global",
    )
    previous_attributes = previous.get("attributes", {}) if previous else {}
    previous_runs = previous_attributes.get("runs", [])
    if not isinstance(previous_runs, list):
        previous_runs = []
    run_digest = {
        "run_id": run_id,
        "ts": datetime.now(timezone.utc).isoformat(),
        "cycles": len(results),
        "ladder": ladder,
    }
    runs = [run_digest, *previous_runs][:10]
    duckbrain_client.remember(
        key="/game/runs/index",
        domain="game/runs",
        attributes={"runs": runs},
        embedding_text=(
            "Recent Pokemon runs: "
            + ", ".join(str(run.get("run_id", "unknown")) for run in runs)
        ),
        namespace="pokemon-global",
    )


WORLD_MEMORY_NAMESPACE = "pokemon-global"
_WORLD_TILE_OFFSETS: dict[str, tuple[int, int]] = {
    "up": (0, -1),
    "down": (0, 1),
    "left": (-1, 0),
    "right": (1, 0),
}
_WORLD_UNREMARKABLE_TILES = frozenset({"", "?", "unknown", "void", "floor"})


def _append_run_event(
    event: dict[str, Any],
    *,
    results: list[dict[str, Any]],
    log_file: TextIO,
) -> None:
    """Keep an observable run event identical in memory and on disk."""
    results.append(event)
    log_file.write(json.dumps(event, default=str) + "\n")
    log_file.flush()


# Walkability values the JEV projection treats as ROM-resolved. Anything else
# ("unknown", "void", "", None) is absence of knowledge, not a fact about the
# tile, so it is never rendered into the projection: a recalled record stays in
# DuckBrain for the rest of the run, and memory answering "unknown" forever is
# what kept JEV re-reporting map_topology on already-mapped tiles.
_KNOWN_WALKABILITY: frozenset[str] = frozenset({"walkable", "blocked"})

_WALK_DIRECTION_LABELS: tuple[tuple[str, str], ...] = (
    ("up", "U"),
    ("down", "D"),
    ("left", "L"),
    ("right", "R"),
)


def _known_walkability(values: Any) -> dict[str, str]:
    """Return the ROM-resolved subset of a walkability mapping, normalized."""
    if not isinstance(values, dict):
        return {}
    return {
        str(direction): str(value).lower()
        for direction, value in values.items()
        if str(value).lower() in _KNOWN_WALKABILITY
    }


def _walkability_from_collision_grid(value: Any) -> dict[str, str]:
    """Derive adjacent movement truth from a RAMReader collision grid.

    ``RAMReader.build_collision_grid()`` emits exactly one ``O`` for the player,
    ``.`` for walkable, ``#`` for blocked, and ``?`` where ROM topology cannot
    resolve a tile. Only the two resolved symbols become facts; unresolved or
    malformed cells are omitted rather than persisted as sticky ``unknown``.
    """
    if not isinstance(value, str):
        return {}
    rows = value.splitlines()
    player_cells = [
        (x, y)
        for y, row in enumerate(rows)
        for x, cell in enumerate(row)
        if cell == "O"
    ]
    if len(player_cells) != 1:
        return {}
    player_x, player_y = player_cells[0]
    resolved: dict[str, str] = {}
    for direction, (dx, dy) in _WORLD_TILE_OFFSETS.items():
        x, y = player_x + dx, player_y + dy
        if y < 0 or y >= len(rows) or x < 0 or x >= len(rows[y]):
            continue
        cell = rows[y][x]
        if cell == ".":
            resolved[direction] = "walkable"
        elif cell == "#":
            resolved[direction] = "blocked"
    return resolved


def _walkability_text(values: dict[str, str]) -> str:
    """Render a walkability mapping in a fixed direction order."""
    return ",".join(
        f"{short}:{values[direction]}"
        for direction, short in _WALK_DIRECTION_LABELS
        if direction in values
    )


def _record_tile(attributes: dict[str, Any]) -> tuple[int, int] | None:
    """Return the tile a recalled map record was observed at, when typed."""
    tile = attributes.get("player_tile")
    if not isinstance(tile, dict):
        return None
    x, y = tile.get("x"), tile.get("y")
    if isinstance(x, int) and isinstance(y, int):
        return (x, y)
    return None


def _fresh_topology_fact(observation: dict[str, Any]) -> str | None:
    """Render live ROM collision truth for the CURRENT map/tile as a fact.

    A memory record is written once and replayed for the rest of the run, so it
    can serve "unknown" walkability (or an older tile's truth) indefinitely.
    This fact is rebuilt from the live RAM read every cycle and carries the
    ``/world/map/<id>:`` key shape, so an already-mapped tile presents one
    unambiguous walkability per direction and a freshly entered map is
    resolvable on its first cycle (retrieval runs before writes, so a new map
    has no recalled record yet).

    Returns ``None`` unless the live read resolved all four directions: a
    partial read must never masquerade as fresh truth.
    """
    map_id = observation.get("map_id")
    if not isinstance(map_id, int) or map_id < 0:
        return None
    walkability = _walkability_from_collision_grid(observation.get("collision_grid"))
    if set(walkability) < {"up", "down", "left", "right"}:
        return None
    parts = ["live ROM collision truth (this cycle)"]
    tile_x = observation.get("player_tile_x")
    tile_y = observation.get("player_tile_y")
    if isinstance(tile_x, int) and isinstance(tile_y, int):
        parts.append(f"tile={tile_x},{tile_y}")
    parts.append(f"walkability={_walkability_text(walkability)}")
    return f"/world/map/{map_id}: " + "; ".join(parts)


def _world_fact_text(
    record: dict[str, Any],
    *,
    fresh_walkability: dict[str, str] | None = None,
    fresh_tile: tuple[int, int] | None = None,
    fresh_collision_grid: str | None = None,
) -> str:
    """Render one recalled world record as bounded factual projection text.

    A recalled record is a snapshot: its ``adjacent_walkability`` may be
    "unknown" for the rest of the run. Only ROM-resolved directions are
    rendered, so stale memory can never contradict the live ROM truth in the
    same projection; when the record is for the tile the player is standing on
    right now, the live ROM read for that tile outranks the stored one. A
    record for a different tile keeps its own known values and never borrows
    the current tile's (that would misattribute truth to the wrong tile).
    """
    key = str(record.get("key") or "world/fact")
    text = str(record.get("embedding_text") or "").strip()
    attributes = record.get("attributes")
    if not isinstance(attributes, dict):
        return f"{key}: {text}" if text else key

    parts = [text] if text else []
    parts.extend(_world_fact_tile_parts(attributes))
    walkability, collision_grid = _world_fact_walkability(
        attributes,
        fresh_walkability=fresh_walkability,
        fresh_tile=fresh_tile,
        fresh_collision_grid=fresh_collision_grid,
    )
    if walkability:
        parts.append(f"walkability={_walkability_text(walkability)}")

    parts.extend(_world_fact_terrain_part(attributes))
    if isinstance(collision_grid, str) and collision_grid.strip():
        parts.append(f"local_collision={collision_grid.strip().replace(chr(10), '/')}")

    parts.extend(_world_fact_exit_parts(attributes))
    parts.extend(_world_fact_route_parts(attributes))
    return f"{key}: {'; '.join(parts)}" if parts else key


def _world_fact_tile_parts(attributes: dict[str, Any]) -> list[str]:
    """Render the recorded player tile as projection parts."""
    parts: list[str] = []
    player_tile = attributes.get("player_tile")
    if isinstance(player_tile, dict):
        x, y = player_tile.get("x"), player_tile.get("y")
        if isinstance(x, int) and isinstance(y, int):
            parts.append(f"tile={x},{y}")
    return parts


def _world_fact_walkability(
    attributes: dict[str, Any],
    *,
    fresh_walkability: dict[str, str] | None,
    fresh_tile: tuple[int, int] | None,
    fresh_collision_grid: str | None,
) -> tuple[dict[str, str], str | None]:
    """Merge stored walkability with live ROM truth for the CURRENT tile.

    When the record is for the tile the player is standing on right now, the
    live ROM read for that tile outranks the stored one. A record for a
    different tile keeps its own known values and never borrows the current
    tile's (that would misattribute truth to the wrong tile).
    """
    walkability = _known_walkability(attributes.get("adjacent_walkability"))
    collision_grid = attributes.get("local_collision_grid")
    if fresh_tile is not None and _record_tile(attributes) == fresh_tile:
        walkability.update(_known_walkability(fresh_walkability))
        if isinstance(fresh_collision_grid, str) and fresh_collision_grid.strip():
            collision_grid = fresh_collision_grid
    return walkability, collision_grid


def _world_fact_terrain_part(attributes: dict[str, Any]) -> list[str]:
    """Render known adjacent terrain as a projection part."""
    terrain = attributes.get("adjacent_tiles")
    if not (isinstance(terrain, dict) and terrain):
        return []
    rendered_terrain = ",".join(
        f"{short}:{terrain[direction]}"
        for direction, short in _WALK_DIRECTION_LABELS
        if direction in terrain
        and str(terrain[direction]).lower() not in {"unknown", "void"}
    )
    if not rendered_terrain:
        return []
    return [f"terrain={rendered_terrain}"]


def _world_fact_exit_parts(attributes: dict[str, Any]) -> list[str]:
    """Render visible and proven exits as projection parts."""
    parts: list[str] = []
    exits = attributes.get("visible_exits")
    if isinstance(exits, list):
        parts.append(
            f"exits={','.join(str(item) for item in exits) if exits else 'none'}"
        )
    proven_exits = attributes.get("exits")
    if isinstance(proven_exits, list) and proven_exits:
        parts.append(f"proven_exits={json.dumps(proven_exits, sort_keys=True)}")
    door = _tile_from_point(attributes.get("door_tile"))
    if door is not None:
        parts.append(f"door_tile={door[0]},{door[1]}")
    return parts


def _world_fact_route_parts(attributes: dict[str, Any]) -> list[str]:
    """Render recorded route tiles as a projection part."""
    route_tiles = attributes.get("route_tiles")
    if not (isinstance(route_tiles, list) and route_tiles):
        return []
    rendered_route = [
        f"{tile[0]},{tile[1]}"
        for item in route_tiles
        if (tile := _tile_from_point(item)) is not None
    ]
    if not rendered_route:
        return []
    return [f"route_tiles={'|'.join(rendered_route)}"]


def _populate_world_memory(
    *,
    observation: dict[str, Any],
    run_id: str,
    cycle: int,
    results: list[dict[str, Any]],
    log_file: TextIO,
    written_keys: set[str],
    retrieval_targets: list[str] | None = None,
    transition: dict[str, Any] | None = None,
) -> list[str]:
    """Retrieve current-map facts, then persist newly observed world facts.

    Retrieval deliberately runs before writes. Therefore a retrieval event for
    cycle N can only contain a fact that was already in DuckBrain when cycle N
    started; facts first written by this run on cycle N-1 become available to
    the JEV projection on the next cycle.
    """
    ctx = _world_memory_context(observation, retrieval_targets)
    if ctx is None:
        return []

    typed_map_id = ctx["map_id"]
    typed_tile_x = ctx["tile_x"]
    typed_tile_y = ctx["tile_y"]
    map_name = ctx["map_name"]
    map_key = ctx["map_key"]

    from src.core import duckbrain_client as _dbc

    retrieved_facts, current_map_record, transition_source_record = (
        _retrieve_world_facts(
            _dbc,
            ctx,
            observation=observation,
            cycle=cycle,
            results=results,
            log_file=log_file,
            transition=transition,
        )
    )

    evidence = {
        "run_id": run_id,
        "cycle": cycle,
        "map": {"id": typed_map_id, "name": map_name},
        "tile": {"x": typed_tile_x, "y": typed_tile_y},
    }
    confidence = 1.0 if USE_RAM_READER else 0.75
    map_attributes = _map_observation_attributes(
        observation,
        current_map_record,
        map_id=typed_map_id,
        map_name=map_name,
        tile_x=typed_tile_x,
        tile_y=typed_tile_y,
        fresh_walkability=ctx["fresh_walkability"],
    )
    writes: list[dict[str, Any]] = [
        {
            "key": map_key,
            "domain": ctx["map_domain"],
            "attributes": map_attributes,
            "embedding_text": (
                f"Observed {map_name} (map {typed_map_id}) at tile "
                f"({typed_tile_x},{typed_tile_y})"
            ),
            "labels": ["world", ctx["map_domain"]],
            "confidence": confidence,
            "evidence": evidence,
        }
    ]
    writes.extend(_tile_object_writes(observation, map_attributes, evidence, confidence))
    writes.extend(_transition_writes(
        transition,
        observation=observation,
        evidence=evidence,
        confidence=confidence,
        existing=transition_source_record,
    ))

    _commit_world_writes(
        _dbc,
        writes,
        transition=transition,
        written_keys=written_keys,
        cycle=cycle,
        results=results,
        log_file=log_file,
    )
    return retrieved_facts


def _world_memory_context(
    observation: dict[str, Any],
    retrieval_targets: list[str] | None,
) -> dict[str, Any] | None:
    """Derive typed map/tile identity and fresh ROM facts for world memory."""
    map_id = observation.get("map_id")
    player_tile_x = observation.get("player_tile_x")
    player_tile_y = observation.get("player_tile_y")
    if (
        not isinstance(map_id, int)
        or not isinstance(player_tile_x, int)
        or not isinstance(player_tile_y, int)
    ):
        return None

    typed_map_id = map_id
    typed_tile_x = player_tile_x
    typed_tile_y = player_tile_y
    map_name = str(observation.get("map_name") or f"Map_{typed_map_id:02X}")
    map_domain = f"world/map/{typed_map_id}"
    fresh_grid = observation.get("collision_grid")
    # Movement truth is derived from RAMReader's collision grid. The adjacent
    # terrain labels may come from vision and are metadata only.
    fresh_walkability = _walkability_from_collision_grid(fresh_grid)
    fresh_topology = _fresh_topology_fact(observation)
    normalized_targets: list[str] = []
    for target in retrieval_targets or []:
        if (
            isinstance(target, str)
            and target.startswith("/world/")
            and target not in normalized_targets
        ):
            normalized_targets.append(target)
    return {
        "map_id": typed_map_id,
        "tile_x": typed_tile_x,
        "tile_y": typed_tile_y,
        "map_name": map_name,
        "map_domain": map_domain,
        "map_key": f"/{map_domain}",
        "object_prefix": f"/world/object/{typed_map_id}/",
        "path_prefix": f"{PATH_MEMORY_PREFIX}{_map_slug(map_name, typed_map_id)}->",
        "fresh_grid": fresh_grid,
        "fresh_walkability": fresh_walkability,
        "fresh_topology": fresh_topology,
        "targets": normalized_targets,
    }


def _retrieve_world_facts(
    duckbrain_client: Any,
    ctx: dict[str, Any],
    *,
    observation: dict[str, Any],
    cycle: int,
    results: list[dict[str, Any]],
    log_file: TextIO,
    transition: dict[str, Any] | None,
) -> tuple[list[str], dict[str, Any] | None, dict[str, Any] | None]:
    """Recall and render world-memory facts; never raise (memory must not stop gameplay).

    Retrieval deliberately runs before writes. Therefore a retrieval event for
    cycle N can only contain a fact that was already in DuckBrain when cycle N
    started; facts first written by this run on cycle N-1 become available to
    the JEV projection on the next cycle.

    Returns ``(retrieved_facts, current_map_record, transition_source_record)``.
    """
    typed_map_id = ctx["map_id"]
    typed_tile_x = ctx["tile_x"]
    typed_tile_y = ctx["tile_y"]
    map_name = ctx["map_name"]
    map_key = ctx["map_key"]
    fresh_grid = ctx["fresh_grid"]
    fresh_walkability = ctx["fresh_walkability"]
    fresh_topology = ctx["fresh_topology"]
    normalized_targets = ctx["targets"]

    retrieved_facts: list[str] = []
    current_map_record: dict[str, Any] | None = None
    transition_source_record: dict[str, Any] | None = None
    try:
        targeted_records: list[dict[str, Any]] = []
        for target in normalized_targets:
            targeted_records.extend(
                duckbrain_client.recall(
                    key=target,
                    namespace=WORLD_MEMORY_NAMESPACE,
                    limit=8,
                )
            )
        recalled = _recall_world_records(duckbrain_client, ctx, targeted_records)
        if isinstance(transition, dict):
            source_id = transition.get("from_map_id")
            if isinstance(source_id, int) and source_id >= 0:
                source_records = duckbrain_client.recall(
                    key=f"/world/map/{source_id}",
                    namespace=WORLD_MEMORY_NAMESPACE,
                    limit=WORLD_MEMORY_TOP_K,
                )
                if source_records:
                    transition_source_record = max(
                        source_records,
                        key=lambda record: str(record.get("created_at") or ""),
                    )
        recalled_by_key = _dedupe_recall_by_key(recalled)
        current_map_record = recalled_by_key.get(map_key)
        _report_teacher_targets(
            ctx,
            recalled_by_key,
            cycle=cycle,
            results=results,
            log_file=log_file,
        )
        retrieved_facts = [
            _world_fact_text(
                record,
                fresh_walkability=fresh_walkability,
                fresh_tile=(typed_tile_x, typed_tile_y),
                fresh_collision_grid=(
                    fresh_grid if isinstance(fresh_grid, str) else None
                ),
            )
            for record in list(recalled_by_key.values())[:WORLD_MEMORY_TOP_K]
        ]
        retrieved_facts = _apply_fresh_topology(
            fresh_topology,
            retrieved_facts,
            map_id=typed_map_id,
            map_name=map_name,
            tile_x=typed_tile_x,
            tile_y=typed_tile_y,
            walkability=fresh_walkability,
            cycle=cycle,
            results=results,
            log_file=log_file,
        )
        if recalled_by_key:
            retrieval_event = {
                "cycle": cycle,
                "event": "world_memory_retrieval",
                "namespace": WORLD_MEMORY_NAMESPACE,
                "map_id": typed_map_id,
                "map_name": map_name,
                "keys": list(recalled_by_key),
                "records": list(recalled_by_key.values()),
            }
            _append_run_event(retrieval_event, results=results, log_file=log_file)
            safe_print(
                f"  [MEM-WORLD] cycle {cycle} retrieved "
                f"{len(recalled_by_key)} fact(s): {', '.join(recalled_by_key)}"
            )
    except Exception as exc:  # memory must not stop gameplay
        retrieved_facts = []
        _append_run_event(
            {
                "cycle": cycle,
                "event": "world_memory_retrieval_failed",
                "namespace": WORLD_MEMORY_NAMESPACE,
                "map_id": typed_map_id,
                "error": str(exc),
            },
            results=results,
            log_file=log_file,
        )
        safe_print(f"  [MEM-WORLD] retrieval failed: {exc}")
    return retrieved_facts, current_map_record, transition_source_record


def _recall_world_records(
    duckbrain_client: Any,
    ctx: dict[str, Any],
    targeted_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Recall map, path, object, and targeted records for the current map."""
    return [
        *duckbrain_client.recall(
            key=ctx["map_key"],
            namespace=WORLD_MEMORY_NAMESPACE,
            limit=WORLD_MEMORY_TOP_K,
        ),
        *duckbrain_client.recall(
            key_prefix=ctx["path_prefix"],
            namespace=WORLD_MEMORY_NAMESPACE,
            limit=WORLD_MEMORY_TOP_K,
        ),
        *duckbrain_client.recall(
            key_prefix=ctx["object_prefix"],
            namespace=WORLD_MEMORY_NAMESPACE,
            limit=WORLD_MEMORY_TOP_K,
        ),
        *targeted_records,
    ]


def _dedupe_recall_by_key(
    recalled: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Keep the newest record per recalled key."""
    recalled_by_key: dict[str, dict[str, Any]] = {}
    for record in recalled:
        key = record.get("key")
        if not isinstance(key, str):
            continue
        current = recalled_by_key.get(key)
        if current is None or str(record.get("created_at") or "") > str(
            current.get("created_at") or ""
        ):
            recalled_by_key[key] = record
    return recalled_by_key


def _report_teacher_targets(
    ctx: dict[str, Any],
    recalled_by_key: dict[str, dict[str, Any]],
    *,
    cycle: int,
    results: list[dict[str, Any]],
    log_file: TextIO,
) -> None:
    """Log which teacher retrieval targets were actually matched in memory."""
    normalized_targets = ctx["targets"]
    if not normalized_targets:
        return
    matched_keys = [
        target for target in normalized_targets if target in recalled_by_key
    ]
    _append_run_event(
        {
            "cycle": cycle,
            "event": "world_memory_teacher_targets_consumed",
            "namespace": WORLD_MEMORY_NAMESPACE,
            "targets": normalized_targets,
            "matched_keys": matched_keys,
        },
        results=results,
        log_file=log_file,
    )
    safe_print(
        f"  [MEM-WORLD] consumed {len(normalized_targets)} teacher target(s); "
        f"matched {len(matched_keys)}"
    )


def _apply_fresh_topology(
    fresh_topology: str | None,
    retrieved_facts: list[str],
    *,
    map_id: int,
    map_name: str,
    tile_x: int,
    tile_y: int,
    walkability: dict[str, str],
    cycle: int,
    results: list[dict[str, Any]],
    log_file: TextIO,
) -> list[str]:
    """Lead the supplied facts with live ROM topology truth when available.

    Live ROM collision truth leads the supplied facts: memory is a snapshot
    from whenever it was written, the collision read is this cycle's. It also
    gives a freshly entered map (retrieval runs before writes, so it has no
    recalled record yet) a factual topology entry instead of leaving the
    projection with none.
    """
    if fresh_topology is None:
        return _bounded_world_facts(retrieved_facts)
    _append_run_event(
        {
            "cycle": cycle,
            "event": "world_memory_topology_refresh",
            "namespace": WORLD_MEMORY_NAMESPACE,
            "map_id": map_id,
            "map_name": map_name,
            "tile": {"x": tile_x, "y": tile_y},
            "walkability": dict(walkability),
            "fact": fresh_topology,
        },
        results=results,
        log_file=log_file,
    )
    retrieved_facts.insert(0, fresh_topology)
    retrieved_facts = _bounded_world_facts(retrieved_facts)
    safe_print(
        f"  [MEM-WORLD] cycle {cycle} live ROM topology fact -> JEV projection"
    )
    return retrieved_facts


def _map_observation_attributes(
    observation: dict[str, Any],
    current_map_record: dict[str, Any] | None,
    *,
    map_id: int,
    map_name: str,
    tile_x: int,
    tile_y: int,
    fresh_walkability: dict[str, str],
) -> dict[str, Any]:
    """Build the map-observation write attributes (merge over recalled attrs)."""
    map_attributes: dict[str, Any] = {}
    if isinstance(current_map_record, dict) and isinstance(
        current_map_record.get("attributes"), dict
    ):
        map_attributes.update(current_map_record["attributes"])
    existing_exits = map_attributes.get("exits")
    map_attributes["exits"] = (
        [dict(item) for item in existing_exits if isinstance(item, dict)]
        if isinstance(existing_exits, list)
        else []
    )
    existing_landmarks = map_attributes.get("landmarks")
    map_attributes["landmarks"] = (
        [dict(item) for item in existing_landmarks if isinstance(item, dict)]
        if isinstance(existing_landmarks, list)
        else []
    )
    existing_tiles = map_attributes.get("tiles_visited")
    tiles_visited = (
        [dict(item) for item in existing_tiles if isinstance(item, dict)]
        if isinstance(existing_tiles, list)
        else []
    )
    current_point = {"x": tile_x, "y": tile_y}
    if current_point not in tiles_visited:
        tiles_visited.append(current_point)
    map_attributes.update(
        {
            "fact_type": "map_observation",
            "map_id": map_id,
            "map_name": map_name,
            "player_tile": current_point,
            "map_dimensions": observation.get("map_dimensions"),
            "map_tileset": observation.get("map_tileset"),
            "visible_exits": list(observation.get("visible_exits") or []),
            "tiles_visited": tiles_visited,
            "adjacent_tiles": dict(observation.get("adjacent") or {}),
            # Never persist vision-derived labels as movement truth. Missing
            # collision cells stay absent and are re-derived on retrieval.
            "adjacent_walkability": dict(fresh_walkability),
            "local_collision_grid": str(observation.get("collision_grid") or ""),
        }
    )
    return map_attributes


def _tile_object_writes(
    observation: dict[str, Any],
    map_attributes: dict[str, Any],
    evidence: dict[str, Any],
    confidence: float,
) -> list[dict[str, Any]]:
    """Build per-tile object writes for remarkable adjacent tiles."""
    typed_map_id = evidence["map"]["id"]
    map_name = evidence["map"]["name"]
    map_domain = evidence["map"]["id"]
    domain = f"world/map/{map_domain}"
    adjacent = observation.get("adjacent")
    player_x = observation.get("player_x")
    player_y = observation.get("player_y")
    if not (
        isinstance(adjacent, dict)
        and isinstance(player_x, int)
        and isinstance(player_y, int)
    ):
        return []

    writes: list[dict[str, Any]] = []
    for direction, (dx, dy) in _WORLD_TILE_OFFSETS.items():
        tile_type = str(adjacent.get(direction) or "").lower()
        if tile_type in _WORLD_UNREMARKABLE_TILES:
            continue
        object_x = player_x + dx
        object_y = player_y + dy
        landmark = {
            "tile": {"x": object_x, "y": object_y},
            "kind": tile_type,
        }
        landmarks = map_attributes["landmarks"]
        if isinstance(landmarks, list) and landmark not in landmarks:
            landmarks.append(landmark)
        object_domain = f"world/object/{typed_map_id}/{object_x}_{object_y}"
        writes.append(
            {
                "key": f"/{object_domain}",
                "domain": object_domain,
                "attributes": {
                    "fact_type": "tile_observation",
                    "map_id": typed_map_id,
                    "map_name": map_name,
                    "position": {
                        "x": object_x,
                        "y": object_y,
                        "coordinate_space": "map_block",
                    },
                    "tile_type": tile_type,
                    "relative_direction": direction,
                },
                "embedding_text": (
                    f"{map_name} map block ({object_x},{object_y}) is "
                    f"{tile_type}, observed {direction} of the player"
                ),
                "labels": ["world", domain, object_domain],
                "confidence": confidence,
                "evidence": evidence,
                "applies_when": {"map_id": typed_map_id},
            }
        )
    return writes


def _transition_writes(
    transition: dict[str, Any] | None,
    *,
    observation: dict[str, Any],
    evidence: dict[str, Any],
    confidence: float,
    existing: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Build the S6 NAV-MEM path/exit writes for an observed map transition.

    An observed map transition IS a proven edge. Storing it as
    ``/world/path/<from>-><to>`` lets a later navigation gap replay the
    route instead of re-deriving it (or paying a teacher for it).
    """
    if not isinstance(transition, dict):
        return []
    writes: list[dict[str, Any]] = []
    path_write = _path_memory_write(
        transition,
        observation=observation,
        evidence=evidence,
        confidence=confidence,
    )
    if path_write is not None:
        writes.append(path_write)
    source_map_write = _transition_map_exit_write(
        transition,
        existing=existing,
        evidence=evidence,
        confidence=confidence,
    )
    if source_map_write is not None:
        writes.append(source_map_write)
    return writes


def _commit_world_writes(
    duckbrain_client: Any,
    writes: list[dict[str, Any]],
    *,
    transition: dict[str, Any] | None,
    written_keys: set[str],
    cycle: int,
    results: list[dict[str, Any]],
    log_file: TextIO,
) -> None:
    """Persist world-memory writes, deduped per run unless transition-forced.

    Fail-closed contract (MEM-PROJ T3): a failed retrieval supplies NO facts,
    so the projection keeps its previous bytes. Write failures are logged and
    never stop gameplay.
    """
    forced_keys = {
        str(write["key"])
        for write in writes
        if isinstance(transition, dict)
        and str(write["key"]) == f"/world/map/{transition.get('from_map_id')}"
    }
    for write in writes:
        key = str(write["key"])
        if key in written_keys and key not in forced_keys:
            continue
        try:
            memory_id = duckbrain_client.remember(
                **write,
                namespace=WORLD_MEMORY_NAMESPACE,
            )
            written_keys.add(key)
            _append_run_event(
                {
                    "cycle": cycle,
                    "event": "world_memory_write",
                    "namespace": WORLD_MEMORY_NAMESPACE,
                    "key": key,
                    "memory_id": memory_id,
                    "record": write,
                },
                results=results,
                log_file=log_file,
            )
            safe_print(f"  [MEM-WORLD] wrote {key}")
        except Exception as exc:  # memory must not stop gameplay
            _append_run_event(
                {
                    "cycle": cycle,
                    "event": "world_memory_write_failed",
                    "namespace": WORLD_MEMORY_NAMESPACE,
                    "key": key,
                    "error": str(exc),
                },
                results=results,
                log_file=log_file,
            )
            safe_print(f"  [MEM-WORLD] write failed for {key}: {exc}")


# DF-AIPP-3 category mapping for the two durable knowledge layers. Agent notes
# mentioning combat vocabulary are battle lessons; location/direction vocabulary
# (or a named map) is navigation; everything else is cross-run strategy. Studied
# records use the four canonical mechanics keys consumed by the boot reader.
_BATTLE_MEMORY_TERMS: tuple[str, ...] = (
    "battle",
    "fight",
    "attack",
    "damage",
    "faint",
    "opponent",
    "enemy",
    "switch",
    "type advantage",
    "move-selection",
)
_NAVIGATION_MEMORY_TERMS: tuple[str, ...] = (
    "route",
    "path",
    "north",
    "south",
    "east",
    "west",
    "door",
    "exit",
    "stairs",
    "map",
    "town",
    "city",
    "lab",
    "house",
    "location",
    "walk",
)
_MENU_MEMORY_TERMS: tuple[str, ...] = (
    "menu",
    "inventory",
    "item",
    "party",
    "select",
    "cursor",
)
_TEXT_MEMORY_TERMS: tuple[str, ...] = (
    "text",
    "dialog",
    "read",
    "npc",
    "talk",
)


def _learning_category(note: str, map_name: str) -> str:
    """Map a note to navigation, battle, or strategy for durable learning."""
    note_text = note.lower()
    if any(term in note_text for term in _BATTLE_MEMORY_TERMS):
        return "battle"
    navigation_text = f"{note_text} {map_name.lower()}"
    if any(term in navigation_text for term in _NAVIGATION_MEMORY_TERMS):
        return "navigation"
    return "strategy"


def _mechanics_category(study_key: str, content: str) -> str:
    """Map studied content to a canonical mechanics key read during boot."""
    studied = f"{study_key} {content}".lower()
    if any(term in studied for term in _BATTLE_MEMORY_TERMS):
        return "battle"
    if any(term in studied for term in _MENU_MEMORY_TERMS):
        return "menus"
    if any(term in studied for term in _TEXT_MEMORY_TERMS):
        return "text"
    return "controls"


def _apply_agent_memory_outputs(
    *,
    decision: dict[str, Any],
    results: list[dict[str, Any]],
    log_file: TextIO,
    cycle: int,
    map_name: str,
    mem_goal: str,
    mem_notes: list[str],
    pending_study_result: str,
) -> tuple[str, list[str], str]:
    """Run one cycle's agent memory outputs: note / goal / study.

    The controller maintains its own knowledge; these optional decision fields
    are executed here and persisted to DuckBrain (namespace pokemon-global).

    Each event is appended to ``results`` right next to its log line (DF-AIPP-1)
    so ``_record_run_memory``'s ladder counts them and the run's
    ``/game/runs/<id>/lessons`` record can extract notes/goals.

    Returns the updated ``(mem_goal, mem_notes, pending_study_result)`` for the
    caller to rebind.
    """
    from src.core import duckbrain_client as _dbc

    _mem_note = (decision.get("note") or "").strip()
    _mem_new_goal = (decision.get("goal") or "").strip()
    _mem_study_key = (decision.get("study") or "").strip()
    if _mem_note:
        mem_notes = _process_memory_note(
            _dbc,
            _mem_note,
            map_name=map_name,
            cycle=cycle,
            mem_notes=mem_notes,
            results=results,
            log_file=log_file,
        )
    if _mem_new_goal:
        mem_goal = _process_memory_goal(
            _dbc,
            _mem_new_goal,
            cycle=cycle,
            results=results,
            log_file=log_file,
        )
    if _mem_study_key:
        pending_study_result = _process_memory_study(
            _dbc,
            _mem_study_key,
            cycle=cycle,
            results=results,
            log_file=log_file,
        )
    return mem_goal, mem_notes, pending_study_result


def _append_event(
    evt: dict[str, Any],
    *,
    results: list[dict[str, Any]],
    log_file: TextIO,
) -> None:
    """Append one memory event to results and to the run log."""
    results.append(evt)
    log_file.write(json.dumps(evt, default=str) + "\n")
    log_file.flush()


def _process_memory_note(
    duckbrain_client: Any,
    note: str,
    *,
    map_name: str,
    cycle: int,
    mem_notes: list[str],
    results: list[dict[str, Any]],
    log_file: TextIO,
) -> list[str]:
    """Persist an agent note (+ learning mirror) and prepend it to mem_notes."""
    try:
        duckbrain_client.remember(
            key=f"/notes/overworld-{cycle}",
            domain="concept",
            attributes={
                "fact": note[:300],
                "source": "agent",
                "map": map_name,
                "cycle": cycle,
            },
            embedding_text=note[:300],
            namespace="pokemon-global",
        )
        learning_category = _learning_category(note, map_name)
        try:
            duckbrain_client.remember(
                key=f"/game/learning/{learning_category}",
                domain="game/learning",
                attributes={
                    "fact": note[:300],
                    "category": learning_category,
                    "source": "agent-note",
                    "map": map_name,
                    "cycle": cycle,
                },
                embedding_text=note[:300],
                namespace="pokemon-global",
            )
        except Exception as learning_error:
            safe_print(f"  [MEM] learning mirror failed: {learning_error}")
        mem_notes.insert(0, f"[{map_name}] {note[:120]}")
        mem_notes = mem_notes[:6]
        safe_print(f"  [MEM] note: {note[:80]}")
        evt = {
            "cycle": cycle,
            "event": "memory_note",
            "map": map_name,
            "note": note[:300],
        }
        _append_event(evt, results=results, log_file=log_file)
    except Exception as _e:
        safe_print(f"  [MEM] note failed: {_e}")
    return mem_notes


def _process_memory_goal(
    duckbrain_client: Any,
    new_goal: str,
    *,
    cycle: int,
    results: list[dict[str, Any]],
    log_file: TextIO,
) -> str:
    """Persist the agent's current goal and log the memory_goal event."""
    mem_goal = new_goal[:200]
    try:
        duckbrain_client.remember(
            key="/goals/current",
            domain="goal",
            attributes={"goal": mem_goal, "source": "agent"},
            embedding_text=f"Current goal: {mem_goal}",
        )
        safe_print(f"  [MEM] goal: {mem_goal[:80]}")
        evt = {"cycle": cycle, "event": "memory_goal", "goal": mem_goal}
        _append_event(evt, results=results, log_file=log_file)
    except Exception as _e:
        safe_print(f"  [MEM] goal failed: {_e}")
    return mem_goal


def _process_memory_study(
    duckbrain_client: Any,
    study_key: str,
    *,
    cycle: int,
    results: list[dict[str, Any]],
    log_file: TextIO,
) -> str:
    """Read a memory key, mirror mechanics content, and log memory_study."""
    pending_study_result: str
    try:
        _rec = duckbrain_client.get(key=study_key)
        if _rec:
            pending_study_result = _mirror_studied_content(
                duckbrain_client, study_key, _rec, cycle=cycle
            )
        else:
            pending_study_result = (
                f"(nothing at {study_key} — you haven't "
                f"learned it yet; explore and remember it)"
            )
        safe_print(f"  [MEM] study {study_key} -> {pending_study_result[:60]}")
        evt = {
            "cycle": cycle,
            "event": "memory_study",
            "key": study_key,
            "result": pending_study_result[:250],
        }
        _append_event(evt, results=results, log_file=log_file)
    except Exception as _e:
        pending_study_result = f"(study failed: {_e})"
    return pending_study_result


def _mirror_studied_content(
    duckbrain_client: Any,
    study_key: str,
    record: dict[str, Any],
    *,
    cycle: int,
) -> str:
    """Copy studied content into the canonical mechanics key for boot reads."""
    _attrs = record.get("attributes", {})
    _body = _attrs.get("fact") or _attrs.get("goal") or record.get("embedding_text", "")
    studied_content = str(_body).strip()[:300]
    pending = f"{record.get('key')}: {studied_content[:250]}"
    if studied_content:
        mechanics_category = _mechanics_category(study_key, studied_content)
        try:
            duckbrain_client.remember(
                key=f"/game/mechanics/{mechanics_category}",
                domain="game/mechanics",
                attributes={
                    "fact": studied_content,
                    "source": "agent-study",
                    "source_key": study_key,
                    "cycle": cycle,
                },
                embedding_text=studied_content,
                namespace="pokemon-global",
            )
        except Exception as mechanics_error:
            safe_print(f"  [MEM] mechanics write failed: {mechanics_error}")
    return pending


# ── Boot memory injection (MEM-2, PRD_v2_lifecycle.md §R3) ──────────
# `_record_run_memory()` above is the WRITER (layers 1+3 as they land in
# DuckBrain ns `pokemon-global`); this half is the READER. At run boot it
# gathers mechanics / save-state / runs-index / learning and renders the
# compact "BOOT MEMORY" block that rides in the controller system prompt
# for every cycle. Reads are read-only and offline-safe (the client
# returns None/[] for missing keys), and any failure degrades to "no boot
# memory" rather than failing the run.

BOOT_MEMORY_NAMESPACE = "pokemon-global"  # matches MEM-1's writer namespace
BOOT_MECHANICS_KEYS: tuple[str, ...] = (
    "/game/mechanics/controls",
    "/game/mechanics/menus",
    "/game/mechanics/battle",
    "/game/mechanics/text",
)
BOOT_SAVE_KEYS: tuple[str, ...] = (
    "/game/save/party",
    "/game/save/items",
    "/game/save/location",
)
# DF-AIPP-5: the freshest distilled save record (written by the run-truth
# distillation / MEM-3 backfill). duckbrain_client.get() already returns the
# most recent active record for the key, so freshness is the store's job.
BOOT_SAVE_CURRENT_KEY = "/game/save/current"
BOOT_LEARNING_KEYS: tuple[str, ...] = (
    "/game/learning/battle",
    "/game/learning/navigation",
    "/game/learning/strategy",
    "/game/learning/self",
)
BOOT_RUNS_INDEX_KEY = "/game/runs/index"
BOOT_RUNS_DIGEST_LIMIT = 10  # last-10 digest (matches MEM-1's rolling cap)
BOOT_VALUE_CHAR_CAP = 240  # per attribute value, before line assembly
BOOT_BLOCK_CHAR_CAP = 1200  # per-block render cap
BOOT_TOTAL_CHAR_BUDGET = 5000  # whole payload cap (per-decision latency guard)
BOOT_BODY_FIRST_ATTR_KEYS: tuple[str, ...] = (
    "fact",
    "text",
    "body",
    "lesson",
    "summary",
    "content",
    "value",
    "description",
    "detail",
)
BOOT_SKIP_ATTR_KEYS = frozenset(
    {"id", "status", "created_at", "ts", "source", "cycle", "run_id", "probe"}
)


@dataclass
class BootMemory:
    """Rendered boot-memory payload (MEM-2) + whether it carries real data."""

    text: str
    has_content: bool


def _as_int(value: Any, default: int = 0) -> int:
    """Tolerant int coercion — DuckBrain records are free-form JSON."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _collapse_ws(text: str) -> str:
    """Collapse any run of whitespace to one space (single-line rendering)."""
    return " ".join(str(text).split())


def _format_memory_value(value: Any, limit: int = BOOT_VALUE_CHAR_CAP) -> str:
    """Render one attribute value as compact single-line text."""
    if isinstance(value, bool):
        text = "true" if value else "false"
    elif isinstance(value, (int, float)):
        text = str(value)
    elif isinstance(value, str):
        text = value
    elif isinstance(value, (list, tuple)):
        parts = [_format_memory_value(item, limit) for item in value]
        text = "; ".join(part for part in parts if part)
    else:
        try:
            text = json.dumps(value, default=str, sort_keys=True)
        except (TypeError, ValueError):
            text = str(value)
    text = _collapse_ws(text)
    if len(text) > limit:
        text = text[: limit - 3].rstrip() + "..."
    return text


def _compact_memory_attributes(attributes: Any) -> str:
    """Flatten one record's attributes into a compact single-line body.

    Body-first keys (``fact``, ``text``, ...) render bare — they ARE the
    fact; everything else renders as ``key=value`` so the model can tell a
    party count from a map name.
    """
    if not isinstance(attributes, dict) or not attributes:
        return ""
    chunks: list[str] = []
    for key in BOOT_BODY_FIRST_ATTR_KEYS:
        if key in attributes:
            rendered = _format_memory_value(attributes[key])
            if rendered:
                chunks.append(rendered)
    for key in sorted(attributes):
        if key in BOOT_BODY_FIRST_ATTR_KEYS or key in BOOT_SKIP_ATTR_KEYS:
            continue
        rendered = _format_memory_value(attributes[key])
        if rendered:
            chunks.append(f"{key}={rendered}")
    return " | ".join(chunks)


def _memory_record_body(record: dict[str, Any]) -> str:
    """Generic record body: compact attributes, else the embedding text."""
    body = _compact_memory_attributes(record.get("attributes"))
    if not body:
        body = _collapse_ws(str(record.get("embedding_text", "")))
    return body


def _get_boot_record(client: Any, key: str) -> dict[str, Any] | None:
    """Read one DuckBrain key; None when absent (or empty)."""
    record = client.get(key=key, namespace=BOOT_MEMORY_NAMESPACE)
    return record if isinstance(record, dict) and record else None


def _gather_memory_entries(client: Any, keys: tuple[str, ...]) -> list[str]:
    """One rendered line per present mechanics / learning key."""
    lines: list[str] = []
    for key in keys:
        record = _get_boot_record(client, key)
        if record is None:
            continue
        body = _memory_record_body(record)
        if body:
            lines.append(f"- {key}: {body}")
    return lines


def _render_save_party(record: dict[str, Any]) -> str:
    """Party line from MEM-1's RAM-truth ``{party_count, species_hint}``."""
    attributes = record.get("attributes") or {}
    count = attributes.get("party_count")
    species = attributes.get("species_hint")
    if count is None and not species:
        return _memory_record_body(record)
    text = f"{_as_int(count)} party member(s)"
    if species:
        text += f"; first species {_collapse_ws(str(species))}"
    return text


def _render_save_items(record: dict[str, Any]) -> str:
    """Items line from MEM-1's ``{items: [...]}`` (dicts or plain names)."""
    attributes = record.get("attributes") or {}
    items = attributes.get("items")
    if items is None:
        return _memory_record_body(record)
    if isinstance(items, list) and items:
        if all(isinstance(item, str) for item in items):
            return "; ".join(
                f"{name} x{count}" for name, count in sorted(Counter(items).items())
            )
        rendered: list[str] = []
        for item in items:
            if isinstance(item, dict):
                name = item.get("name") or item.get("item") or "?"
                count = item.get("count", item.get("quantity"))
                rendered.append(
                    f"{name} x{_as_int(count)}" if count is not None else str(name)
                )
            else:
                rendered.append(_format_memory_value(item))
        return "; ".join(part for part in rendered if part)
    if isinstance(items, dict) and items:
        return "; ".join(f"{name} x{_as_int(count)}" for name, count in items.items())
    if isinstance(items, list):
        return "(none)"
    return _format_memory_value(items)


def _render_save_location(record: dict[str, Any]) -> str:
    """Location line from MEM-1's ``{map_id, map_name, pos:{x, y}}``."""
    attributes = record.get("attributes") or {}
    name = attributes.get("map_name")
    map_id = attributes.get("map_id")
    pos = attributes.get("pos")
    if name is None and map_id is None and pos is None:
        return _memory_record_body(record)
    text = _collapse_ws(str(name or "unknown map"))
    if map_id is not None:
        text += f" (map {map_id})"
    if isinstance(pos, dict):
        x, y = pos.get("x"), pos.get("y")
        if x is not None and y is not None:
            text += f" at {x},{y}"
    elif isinstance(pos, (list, tuple)) and len(pos) == 2:
        text += f" at {pos[0]},{pos[1]}"
    return text


def _render_save_current(record: dict[str, Any]) -> str:
    """Freshest-save line (DF-AIPP-5) from whatever fields the record carries."""
    attributes = record.get("attributes") or {}
    if not isinstance(attributes, dict):
        attributes = {}
    text = _save_location_text(attributes)
    party_count = attributes.get("party_count")
    if party_count is not None:
        if text:
            text += "; "
        text += f"{_as_int(party_count)} party member(s)"
    if text:
        return text
    # Defensive fallback: truncated JSON dump so *some* truth still rides.
    body = _memory_record_body(record)
    if not body:
        body = json.dumps(record.get("attributes") or {}, default=str)
    return body[:200]


def _save_location_text(attributes: dict[str, Any]) -> str:
    """Render map/position truth from a save record's attributes."""
    text = ""
    name = attributes.get("map_name")
    map_id = attributes.get("map_id")
    pos = attributes.get("pos")
    if name is not None or map_id is not None or pos is not None:
        text = _collapse_ws(str(name or "unknown map"))
        if map_id is not None:
            text += f" (map {map_id})"
        if isinstance(pos, dict):
            x, y = pos.get("x"), pos.get("y")
            if x is not None and y is not None:
                text += f" at {x},{y}"
        elif isinstance(pos, (list, tuple)) and len(pos) == 2:
            text += f" at {pos[0]},{pos[1]}"
    return text


def _gather_save_state(client: Any) -> list[str]:
    """Rendered SAVE-STATE lines: party, items, location, current (whichever exist)."""
    renderers = (_render_save_party, _render_save_items, _render_save_location)
    lines: list[str] = []
    for label, key, renderer in zip(
        ("party", "items", "location"), BOOT_SAVE_KEYS, renderers, strict=True
    ):
        record = _get_boot_record(client, key)
        if record is None:
            continue
        body = renderer(record)
        if body:
            lines.append(f"- {label}: {body}")
    current_record = _get_boot_record(client, BOOT_SAVE_CURRENT_KEY)
    if current_record is not None:
        body = _render_save_current(current_record)
        if body:
            lines.append(f"- current: {body}")
    return lines


def _format_run_digest(run: dict[str, Any]) -> str:
    """One compact history line for a ``/game/runs/index`` entry."""
    run_id = str(run.get("run_id") or run.get("id") or "unknown")
    parts: list[str] = []
    cycles = run.get("cycles")
    if cycles is not None:
        parts.append(f"{_as_int(cycles)} cycles")
    ladder = run.get("ladder")
    if isinstance(ladder, dict):
        parts.append(
            "memory_events={mem}, battle_events={battle}, map={map}, "
            "starter={starter}".format(
                mem=_as_int(ladder.get("memory_events")),
                battle=_as_int(ladder.get("battle_events")),
                map=ladder.get("map_progress") or "unknown",
                starter="yes" if ladder.get("starter_picked") else "no",
            )
        )
    else:
        # Legacy / partial digests: derive the same one-liner from whatever
        # fields the record does carry (older marathon harness wrote
        # events/maps_sequence/final_map instead of a ladder block).
        legacy_events = run.get("events")
        events: dict[Any, Any] = (
            legacy_events if isinstance(legacy_events, dict) else {}
        )
        memory_events = sum(
            _as_int(events.get(name))
            for name in ("memory_note", "memory_goal", "memory_study")
        )
        battle_events = run.get("battle_events")
        if not isinstance(battle_events, int):
            battle_events = sum(
                _as_int(value)
                for name, value in events.items()
                if str(name).startswith("battle_")
            )
        progress = run.get("final_map")
        maps_sequence = run.get("maps_sequence")
        if not progress and isinstance(maps_sequence, list) and maps_sequence:
            progress = maps_sequence[-1]
        parts.append(
            f"memory_events={memory_events}, battle_events={_as_int(battle_events)}, "
            f"map={progress or 'unknown'}"
        )
    stamp = str(run.get("ts") or "")[:10]
    label = f"{run_id} [{stamp}]" if stamp else run_id
    return f"{label}: " + ", ".join(parts)


def _gather_runs_index(client: Any) -> list[str]:
    """Rendered last-10 digest lines from ``/game/runs/index``."""
    record = _get_boot_record(client, BOOT_RUNS_INDEX_KEY)
    if record is None:
        return []
    runs = (record.get("attributes") or {}).get("runs")
    if not isinstance(runs, list):
        return []
    lines: list[str] = []
    for run in runs[:BOOT_RUNS_DIGEST_LIMIT]:
        if isinstance(run, dict):
            lines.append(f"- {_format_run_digest(run)}")
    return lines


def _cap_boot_block(text: str, cap: int = BOOT_BLOCK_CHAR_CAP) -> str:
    """Cap one block's text at ``cap`` chars, marking the cut with "..."."""
    if len(text) <= cap:
        return text
    return text[: cap - 3].rstrip() + "..."


def _cap_boot_payload(text: str, budget: int = BOOT_TOTAL_CHAR_BUDGET) -> str:
    """Whole-payload cap — the last-resort latency guard after block caps."""
    if len(text) <= budget:
        return text
    return text[: budget - 3].rstrip() + "..."


def _render_boot_block(lines: list[str], placeholder: str) -> str:
    """Join a block's lines, or fall back to its empty-store placeholder."""
    if not lines:
        return placeholder
    return _cap_boot_block("\n".join(lines))


def _build_boot_memory_blocks() -> BootMemory:
    """Gather + render the run-start memory blocks from DuckBrain (MEM-2).

    Called once per run, before the cycle loop. Never raises: any
    DuckBrain/JSONL failure logs one line and returns an empty payload, so
    the run continues with today's prompt.
    """
    try:
        from src.core import duckbrain_client

        mechanics = _gather_memory_entries(duckbrain_client, BOOT_MECHANICS_KEYS)
        save_state = _gather_save_state(duckbrain_client)
        runs = _gather_runs_index(duckbrain_client)
        learning = _gather_memory_entries(duckbrain_client, BOOT_LEARNING_KEYS)
    except Exception as exc:
        safe_print(f"[MEM] boot injection skipped: {exc}")
        return BootMemory(text="", has_content=False)

    sections: tuple[tuple[str, list[str], str], ...] = (
        ("MECHANICS", mechanics, "(no mechanics recorded yet)"),
        ("SAVE", save_state, "(no save-state recorded yet)"),
        ("RUN HISTORY", runs, "(no runs recorded yet)"),
        ("LEARNING", learning, "(no learning recorded yet)"),
    )
    rendered = [
        f"[{label}]\n{_render_boot_block(lines, placeholder)}"
        for label, lines, placeholder in sections
    ]
    return BootMemory(
        text=_cap_boot_payload(
            "BOOT MEMORY (from previous runs):\n" + "\n".join(rendered)
        ),
        has_content=any(lines for _, lines, _ in sections),
    )


def _boot_memory_prompt(boot: BootMemory) -> str:
    """The system-prompt section to inject, or "" when there is nothing real.

    A fresh clone (no keys, or only placeholders) must keep today's prompt
    byte-identical, so placeholders alone are never injected.
    """
    return boot.text if boot.has_content else ""


def controller_key() -> str | None:
    """Return the controller key the runner would construct, or ``None``.

    Mirrors ``OpenRouterClient.__init__`` (``api_key or
    os.environ["OPENROUTER_API_KEY"]``) so preflight can validate the same
    key the run will use. Never prints the key itself.
    """
    key = os.environ.get("OPENROUTER_API_KEY")
    return key or None


def _run_jev_preflight(
    *,
    decision_mode: str,
    skip_preflight: bool,
    current_run_id: str,
    current_log_path: Path,
) -> dict[str, Any]:
    """Run or explicitly skip the real JEV startup probe and persist its row."""
    if decision_mode_family(decision_mode) == MODE_SYSTEM2:
        # Only system2 skips: it never calls the fast tier. system1 and
        # system1+system2 both do, so the preflight matters for them.
        row: dict[str, Any] = {
            "run_id": current_run_id,
            "event": "preflight",
            "component": "jev",
            "status": "skipped",
            "reason": f"decision_mode={decision_mode} (fast tier not used)",
        }
    elif skip_preflight:
        row = {
            "run_id": current_run_id,
            "event": "preflight",
            "component": "jev",
            "status": "skipped",
            "reason": "--skip-preflight",
        }
    elif controller_key() is None:
        # The run would construct OpenRouterClient() later and crash with a
        # generic ValueError; fail here, during preflight, with the truthful
        # controller-key message instead of a stub path.
        row = {
            "run_id": current_run_id,
            "event": "preflight",
            "component": "controller",
            "status": "auth_failure",
            "key_name": "OPENROUTER_API_KEY",
            "error": (
                "controller key OPENROUTER_API_KEY is not set — set it in "
                "the clone's .env or the environment before running"
            ),
        }
    else:
        outcome = jev_client.preflight(timeout=15)
        status = str(outcome.get("status") or "transient")
        row = {
            "run_id": current_run_id,
            "event": "preflight_warning" if status == "transient" else "preflight",
            "component": "jev",
            **outcome,
        }

    current_log_path.parent.mkdir(parents=True, exist_ok=True)
    current_log_path.write_text(json.dumps(row, default=str) + "\n")

    status = row["status"]
    key_name = row.get("key_name") or "unknown key"
    if status == "auth_failure":
        safe_print(
            f"[{current_run_id}] JEV PREFLIGHT AUTH FAILURE ({key_name}): "
            f"{row.get('error', 'authentication rejected')}"
        )
    elif status == "transient":
        safe_print(
            f"[{current_run_id}] JEV PREFLIGHT WARNING ({key_name}): "
            f"{row.get('error', 'transient failure')} — continuing"
        )
    elif status == "pass":
        safe_print(f"[{current_run_id}] JEV preflight passed ({key_name})")
    else:
        safe_print(f"[{current_run_id}] JEV preflight skipped: {row.get('reason')}")
    return row


def _main_parser() -> argparse.ArgumentParser:
    """Build the real CLI parser main() uses (module-level so tests can parse)."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--cycles", type=int, default=CYCLES)
    parser.add_argument(
        "--rom",
        default=None,
        help=(
            "Path to the Gen-1 GB ROM to boot (default: "
            "data/rom/Pokemon - Blue Version (USA, Europe) (SGB Enhanced).gb)."
        ),
    )
    parser.add_argument(
        "--boot-state",
        default=None,
        help=(
            "Path to a known-good .state checkpoint to boot from instead of "
            "the intro bypass (default: data/boot.state when present; "
            "'skip' forces the legacy intro bypass)."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Validate setup (ROM + boot-state paths, config summary, "
            "API-key liveness) and exit 0 — no emulator boot, no LLM "
            "completions (GAP-032, GAP-048)."
        ),
    )
    parser.add_argument(
        "--skip-key-check",
        action="store_true",
        help=(
            "With --dry-run: skip the API-key liveness probes and report "
            "key presence only (offline validation, pre-GAP-048 behavior)."
        ),
    )
    parser.add_argument(
        "--skip-preflight",
        action="store_true",
        help=(
            "Skip the real JEV startup probe for a JEV-mode run. The skip is "
            "still stamped in the run log."
        ),
    )
    parser.add_argument(
        "--controller-model",
        default=None,
        help=(
            "Model id for the overworld controller (default: "
            "openai/gpt-5.6-luna). Overrides the CRON_CONTROLLER_MODEL / "
            "POKE_CONTROLLER_MODEL env vars — e.g. "
            "'--controller-model deepseek-chat' sends the controller to "
            "api.deepseek.com via DEEPSEEK_API_KEY (GAP-052)."
        ),
    )
    parser.add_argument(
        "--decision-mode",
        default=None,
        choices=list(DECISION_MODES),
        help=(
            "Who decides each cycle. 'system1': the fast System-One tier "
            "decides EVERY cycle and never hands back. 'system2' (alias 'llm') "
            "and 'agentic': the controller decides EVERY cycle through the "
            "verified model-tool surface; the fast tier is never called. Every "
            "decision row stamps whether tools were enabled and how many calls "
            "ran. JEV/hybrid never enables this surface. 'system1+system2' "
            "(alias 'jev', the default): the fast tier decides and hands back "
            "to the reasoning teacher when a trigger fires and --handoff allows "
            "it. Overrides the AIPP_DECISION_MODE / CRON_DECISION_MODE env vars."
        ),
    )
    parser.add_argument(
        "--handoff",
        default=None,
        help=(
            "Which handoff trigger families may hand back to the reasoning "
            "teacher in 'system1+system2': 'off' (== system1), 'any' (default), "
            "'failure', 'gap', 'confidence', or a comma list of those. "
            "'failure' = the last action changed nothing; 'gap' = the fast tier "
            "reports its state insufficient or names a missing class; "
            "'confidence' = low action confidence with the layered gate. "
            "Overrides AIPP_HANDOFF / CRON_HANDOFF."
        ),
    )
    parser.add_argument(
        "--handoff-confidence",
        type=float,
        default=None,
        help=(
            "Action-confidence floor for the confidence trigger "
            f"(default {DEFAULT_HANDOFF_CONFIDENCE}). The default mirrors the "
            "threshold already in code, so changing it invalidates comparison "
            "against existing runs."
        ),
    )
    parser.add_argument(
        "--handoff-ambiguity",
        type=float,
        default=None,
        help=(
            "Ambiguity gate for the layered confidence trigger "
            f"(default {DEFAULT_HANDOFF_AMBIGUITY}); low confidence alone does "
            "not hand back unless the phase is irreversible."
        ),
    )
    parser.add_argument(
        "--handoff-classes",
        default=None,
        help=(
            "Comma list of missing-information classes allowed to hand off "
            "(e.g. 'map_topology'). Unset means any class may."
        ),
    )
    parser.add_argument(
        "--teacher-max-per-episode",
        type=int,
        default=None,
        help=(
            "Hard cap on teacher handoffs per episode. On exhaustion the run "
            "keeps playing on the fast tier and records why the handoff was "
            "blocked. Unset means unlimited."
        ),
    )
    return parser


def main() -> None:
    """Entry point: parse args, preflight, boot, run all cycles, finalize."""
    global CYCLES, ROM, run_id, log_path

    # Load the clone's .env BEFORE the JEV preflight reads os.environ (REV-4
    # regression fix): _load_dotenv_stdlib is no-override, so real environment
    # variables keep precedence and the preflight now validates the key a
    # fresh clone actually has on disk. Previously this was only called inside
    # _dry_run_summary, so every real run without an exported key died at
    # preflight with "controller key OPENROUTER_API_KEY is not set".
    _load_dotenv_stdlib()

    args = _main_parse_and_dry_run()
    if args is None:
        # --dry-run: setup validation already printed its summary.
        return
    if args.rom:
        ROM = args.rom
    CYCLES = max(1, args.cycles)
    run_id = args.run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = LOG_DIR / f"run_{run_id}.jsonl"
    preflight_row = _run_jev_preflight(
        decision_mode=DECISION_MODE,
        skip_preflight=args.skip_preflight,
        current_run_id=run_id,
        current_log_path=log_path,
    )
    if preflight_row.get("status") == "auth_failure":
        raise SystemExit(2)

    R = _main_runtime_setup(args)
    ctx = _main_boot(R, args)
    _main_run(R, args, preflight_row, ctx)


def _main_parse_and_dry_run():
    """Parse CLI args, set DECISION_MODE/HANDOFF_POLICY, handle --dry-run.

    Returns the parsed args, or None when a dry run already completed (the
    caller must return without touching runtime dependencies).
    """
    global DECISION_MODE, HANDOFF_POLICY
    parser = _main_parser()
    args = parser.parse_args()
    # Decision mode (flag > env > default). Stamped into every decision row,
    # so a log alone reveals whether a run was fast-tier or pure-LLM.
    DECISION_MODE = resolve_decision_mode(args.decision_mode)
    HANDOFF_POLICY = build_handoff_policy(
        handoff=args.handoff,
        confidence=args.handoff_confidence,
        ambiguity=args.handoff_ambiguity,
        classes=args.handoff_classes,
        teacher_max=args.teacher_max_per_episode,
    )
    # system1 means "never hand back", so the policy is emptied regardless of
    # --handoff. The mode is the stronger statement and the two must not be able
    # to contradict each other in the log.
    if current_mode_family() == MODE_SYSTEM1 and HANDOFF_POLICY["families"]:
        HANDOFF_POLICY = {**HANDOFF_POLICY, "families": []}
    if args.dry_run:
        # Keep setup validation on the stdlib-only path: no emulator, SDL, numpy,
        # or model-client imports are needed to print the summary.
        dry_run_status = _dry_run_summary(
            args.run_id,
            max(1, args.cycles),
            args.boot_state,
            args.rom,
            skip_key_check=args.skip_key_check,
            controller_model=args.controller_model,
        )
        if dry_run_status:
            raise SystemExit(dry_run_status)
        return None
    return args


def _main_runtime_setup(args):
    """Runtime-only imports + emulator/pipeline/client initialization.

    Runtime-only dependencies stay behind argparse and the fail-fast preflight.
    In particular, Emulator imports PyBoy/SDL and PIL imports numpy transitively.
    """
    global SCREENSHOT_DIR
    global SimpleNamespace, Emulator, GlobalContext, run_agentic_cycle
    from types import SimpleNamespace

    from PIL import Image
    from src.core.ai_client import OpenRouterClient
    from src.core.emulator import Emulator
    from src.core.frame_cache import FrameCache
    from src.core.global_context import GlobalContext
    from src.core.ram_reader import RAMReader
    from src.core.agentic_loop import run_agentic_cycle

    if USE_VISION_CLIENT:
        from src.core.vision import VisionClient
    if not USE_RAM_READER:
        _load_cartographer_assets()

    SCREENSHOT_DIR = Path("screenshots") / f"run_{run_id}"
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

    R = SimpleNamespace()
    R.image_module = Image
    R.emu = Emulator(ROM)
    _apply_boot_checkpoint(R, args)

    # Init RAM reader (instant state reads) or fall back to vision cartographer
    if USE_RAM_READER:
        R.ram_reader = RAMReader(R.emu, ROM)
        R.pipeline_name = "RAM reader"
        safe_print(f"[{run_id}] Starting run with RAM reader pipeline...")
    else:
        R.ram_reader = None
        R.pipeline_name = "cartographer"
        safe_print(
            f"[{run_id}] Starting run with visual-reference cartographer pipeline..."
        )
        safe_print("  Reference image: reference/bedroom_overworld.png")

    # Persistent frame cache — UUID references for repeated screenshots.
    # Survives runs, so revisiting a map in a later session also hits.
    R.frame_cache = FrameCache("data/frame_cache.json")
    safe_print(
        f"[{run_id}] Frame cache: {R.frame_cache.unique_frames} known frames "
        f"({R.frame_cache.total_seen} total references) — {R.frame_cache.MAX_ENTRIES} max"
    )

    # Init AI clients
    if USE_VISION_CLIENT:
        vision = VisionClient()  # noqa: F841 — conditionally enabled debug classifier
    R.controller_client = OpenRouterClient()  # uses DEEPSEEK_API_KEY from .env
    # GAP-052: flag > CRON_CONTROLLER_MODEL/POKE_CONTROLLER_MODEL > default
    # Luna. Deepseek models reach their own API through this same client.
    # GAP-052: the controller model is resolved once here — explicit arg, else
    # env override, else the default Luna string — and this resolution feeds
    # controller_plan, whose ``model=controller_model`` argument is the wiring
    # every decision path inherits. A '*deepseek*' id routes to
    # api.deepseek.com through the same client (src/core/ai_client.py).
    resolved_model = resolve_controller_model(args.controller_model)
    R.controller_model = resolved_model
    safe_print(f"[{run_id}] Controller model: {R.controller_model}")

    # A-mash batch constants — also used by the main-loop name_entry
    # handler, so they live OUTSIDE the guarded intro block (booting from
    # a checkpoint skips the intro but can still re-enter name_entry).
    R._A_BURST = 10  # A-presses per batch — Gen 1 text advances in a few presses
    R._A_FRAMES = 5  # hold A for 5 frames each press
    R._FF_FRAMES = 30  # fast-forward between presses (~350 frames per burst total)
    R._NAME_ENTRY_STUCK_MAX = 3  # after 3 cycles → programmatic entry
    return R


def _apply_boot_checkpoint(R, args):
    """Boot from a known-good checkpoint when one resolves (GAP-028).

    A fresh run that boots from the title screen and A-mashes through
    the intro can land in a degenerate overworld state (player facing
    a wall) that direction-locks on every cycle. When a known-good
    checkpoint is available, boot from it instead so the run starts
    from a verified overworld position with the starter already picked.
    """
    boot_path = _resolve_boot_state(args.boot_state)
    R.boot_from_state = boot_path is not None
    _warn_boot_state_rom_mismatch(run_id, boot_path, ROM)
    if R.boot_from_state:
        R.emu.load_state(cast(Path, boot_path))
        R.emu.wait(30)  # settle after state restore
        safe_print(
            f"[{run_id}] Booting from checkpoint {boot_path} — skipping intro bypass"
        )
    elif args.boot_state and args.boot_state.lower() != "skip":
        safe_print(
            f"[{run_id}] Boot checkpoint {args.boot_state} not found — falling back to intro bypass"
        )


def _main_boot(R, args):
    """Boot the game world: checkpoint or intro bypass, then GlobalContext."""
    if R.boot_from_state:
        R._player_named = False
        R._rival_named = False
    else:
        R._player_named, R._rival_named = _intro_bypass(R)
        _intro_walk_out(R)

    ctx = GlobalContext(
        generation="gen1", location="pallet_town" if R.boot_from_state else "bedroom"
    )
    # If we bypassed the intro, set player/rival names
    if R._player_named:
        ctx.player_name = "ASH"
    if R._rival_named:
        ctx.rival_name = "GARY"
    return ctx


def _intro_bypass(R):
    """Deterministic intro bypass: A-mash through the intro to the overworld.

    Decoupled: A-mash aggressively in large batches, sparse observation checks
    (RAM reader is instant, cartographer has 1-60s latency). RAM reader path:
    instant state reads, no LLM calls.

    Returns (player_named, rival_named).
    """
    safe_print(f"[{run_id}] Bypassing intro via {R.pipeline_name}...")

    # Step 1: Title screen → press START. PyBoy starts before the title is
    # ready for input, so let it finish drawing before sending START.
    R.emu.wait(180)
    R.emu.bypass_title()
    # Brief settle — intro loop detects state changes via RAM, no need for long waits.
    R.emu.wait(30)
    # Press A — if no save file, this selects NEW GAME directly.
    # If save exists, cursor is on CONTINUE — we'll detect old save below.
    R.emu.press_button("a", frames=15)
    R.emu.fast_forward(60)  # let game load (or Oak appear)

    intro = SimpleNamespace(
        checks=0,
        player_named=False,
        rival_named=False,
        save_detected=False,
        name_entry_stuck=0,
        last_phase=None,
    )
    max_checks = 15  # raised from 12 — programmatic name entry takes fewer cycles

    while intro.checks < max_checks:
        intro.checks += 1
        screenshot = R.emu.capture()

        # Use RAM reader or cartographer for screen classification
        patch_data, _carto_raw = _intro_observe(R, screenshot)
        st = patch_data.get("result", "unknown")

        # ── Save file detection: if we're in overworld without naming ──
        if st == "overworld" and not intro.player_named and _intro_save_restart(R, intro, patch_data):
            continue

        if st == "overworld":
            if intro.last_phase != "overworld":
                safe_print(
                    f"  [intro] Phase: {intro.last_phase} → overworld — intro complete ({intro.checks} checks)"
                )
            print(
                f"  [intro] {R.pipeline_name} says overworld — intro complete ({intro.checks} checks)"
            )
            break
        elif st == "name_entry":
            _intro_name_entry_step(R, intro)
        elif st == "title":
            intro.name_entry_stuck = 0  # reset — we're not in name entry
            R.emu.press_button("start", frames=30)
            R.emu.wait(90)
        else:
            # dialog / name_confirm / cutscene / unknown — A-mash aggressively
            intro.name_entry_stuck = 0  # reset — out of name entry
            _intro_mash(R)

        # ── Phase transition logging ───────────────────────────
        if st != intro.last_phase:
            if intro.last_phase is not None:
                safe_print(
                    f"  [intro] Phase: {intro.last_phase} → {st} (check {intro.checks})"
                )
            intro.last_phase = st

    if intro.checks >= max_checks:
        print(
            f"  [!] Intro bypass hit {max_checks} check cap — proceeding anyway"
        )
    else:
        print(f"  Intro bypass complete in {intro.checks} checks")

    return intro.player_named, intro.rival_named


def _intro_observe(R, screenshot):
    """Classify one intro screen via RAM reader or cartographer."""
    if USE_RAM_READER:
        patch_data = R.ram_reader.observe()
        carto_raw = json.dumps(
            {"source": "ram_reader", "result": patch_data.get("result")}
        )
    else:
        patch_data, carto_raw = cartographer_analyze(
            R.controller_client, screenshot
        )
    return patch_data, carto_raw


def _intro_save_restart(R, intro, patch_data):
    """Restart from scratch when an old save was loaded by mistake.

    Returns True only when the restart happened (the caller must re-classify).
    """
    tc = patch_data.get("text_content", [])
    if not (not tc and not USE_RAM_READER):
        # RAM reader always returns empty text_content
        return False
    if intro.save_detected:
        return False
    intro.save_detected = True
    print("  [intro] SAVE DETECTED — restarting with NEW GAME")
    # Reset the emulator from scratch
    R.emu.stop()
    R.emu = Emulator(ROM)
    R.emu.bypass_title()
    R.emu.wait(120)
    # Move cursor from CONTINUE (default) to NEW GAME
    R.emu.press_button("down", frames=15)
    R.emu.wait(15)
    R.emu.press_button("a", frames=15)
    R.emu.wait(120)
    intro.checks = 0  # reset counter
    return True


def _intro_name_entry_step(R, intro):
    """One name_entry cycle: accept programmatically when stuck, else A-mash."""
    intro.name_entry_stuck += 1
    if intro.name_entry_stuck >= R._NAME_ENTRY_STUCK_MAX:
        # A-mashing may already have filled the name. Navigate from
        # the default A key directly to END and accept it.
        if not intro.player_named:
            safe_print("  [intro] Name entry stuck — accepting player name")
            R.emu.submit_name()
            intro.player_named = True
        elif not intro.rival_named:
            safe_print("  [intro] Rival name stuck — accepting rival name")
            R.emu.submit_name()
            intro.rival_named = True
        intro.name_entry_stuck = 0
    else:
        # Not stuck yet — A-mash to advance through any pending dialog
        # that sits between cycles (e.g. "So, your name is X?" confirmation).
        # NOTE: do NOT set player_named/rival_named here — only programmatic
        # typing actually writes the name, so flags must wait until enter_name()
        # has run. Setting them prematurely caused the second name_entry
        # cycle to be skipped and the rival to be named "----" (default).
        _intro_mash(R)


def _intro_mash(R):
    """A-mash one burst to advance intro/name-entry dialog."""
    for _ in range(R._A_BURST):
        R.emu.press_button("a", frames=R._A_FRAMES)
        R.emu.fast_forward(R._FF_FRAMES)


def _intro_walk_out(R):
    """Post-intro: save checkpoint, step away from the TV, leave the bedroom."""
    # ── Save state at center of bedroom (before moving) ──────────
    # The bedroom start position faces the TV; saving before we move
    # gives the controller a clean starting position to navigate from.
    try:
        R.emu.save_state(0)
        R._last_saved_slot = 0
        print("  [CKPT] Post-intro state saved to slot 0")
    except Exception as exc:
        print(f"  [CKPT] Failed to save post-intro state: {exc}")

    # ── Step away from what we're facing ─────────────────────────
    # Walk LEFT (toward the bed/stairs area). The stairs down are on
    # the left side of the bedroom; walking LEFT avoids the TV loop
    # AND positions the character near the exit.
    safe_print("  [intro] Stepping away from TV...")
    R.emu.press_button("up", frames=15)  # face away from TV
    R.emu.fast_forward(30)
    # Clear any lingering dialog box
    R.emu.press_button("b", frames=30)
    R.emu.wait(30)

    # ── Leave bedroom ────────────────────────────────────────────
    # A 30-frame press advances roughly two tiles. The collision-verified path
    # from spawn (3,6) to the bedroom warp (7,1) is R,U,U,U,R.
    safe_print("  [intro] Walking to bedroom stairs (R,U,U,U,R)...")
    for button in ("right", "up", "up", "up", "right"):
        R.emu.press_button(button, frames=30)
        R.emu.fast_forward(60)
    R.emu.wait(90)

    # Continue through the ground floor so the controller starts outdoors.
    if R.emu.read_u8(0xD35E) == 0x25:  # wCurMap: Red's House 1F
        safe_print("  [intro] Leaving ground floor for Pallet Town...")
        for button in ("down", "down", "down", "left", "left", "down"):
            R.emu.press_button(button, frames=30)
            R.emu.fast_forward(60)
        R.emu.wait(90)


def _main_run(R, args, preflight_row, ctx):
    """Open the run log, initialize loop state, run all cycles, finalize."""
    # Open log file for incremental writing (web viewer polls this). The
    # preflight row was written before emulator construction, so append here;
    # final closeout still rewrites the complete in-memory result list.
    log_file = open(log_path, "a")
    log_file.flush()

    S = _main_loop_state(R, ctx, log_file)
    S.preflight_row = preflight_row
    S.args = args
    _run_cycles(S)
    _finalize_run(S)


def _main_loop_state(R, ctx, log_file):
    """Initialize the per-run mutable state namespace for the main loop."""
    S = SimpleNamespace()
    S.R = R
    S.ctx = ctx
    S.log_file = log_file
    S.results = []
    S.run_id = run_id
    _init_recovery_trackers(S)
    _init_memory_state(S)
    return S


def _init_recovery_trackers(S):
    """Per-run stuck-detection / recovery / frame-hash trackers."""
    # ── Checkpoint / recovery state (STUCK-RECOVER) ─────────────────
    S._checkpoint_slot = 0
    S._last_saved_slot = None
    S._dir_blacklist = set()  # directions that caused checkpoint recovery
    S._last_direction = ""  # last direction pressed (for controller context)
    S._last_result = "unknown"  # last movement result
    # The teacher gets one attempt per missing-information class for this run.
    # Membership is recorded before the API call, so failures remain bounded.
    S._teacher_escalated_classes = set()
    # Per-episode teacher budget (--teacher-max-per-episode). Counted at the API
    # boundary so a failing call still spends it; None cap means unlimited.
    S._teacher_budget = {"used": 0}
    # A teacher patch's missing facts are bound to exact /world/* keys after the
    # decision, then consumed once by the following cycle's memory retrieval.
    S._pending_teacher_memory_targets = []

    # ── Stuck detection (4 independent dimensions) ──────────────────
    S._same_dir = None  # last repeated direction
    S._same_dir_count = 0  # consecutive same-direction presses
    S._same_screen_count = 0  # consecutive cycles on same screen type
    S._last_screen_type = ""  # for same-screen detection
    S._same_tile_count = 0  # consecutive cycles on same RAM tile
    S._last_tile = None
    # S6 NAV-MEM: the tile stood on before this cycle's observation — the door
    # tile of any map transition observed this cycle.
    S._departure_tile = None
    S._void_tile_pct = 0.0  # % of tiles classified as unknown/void
    S._void_cycles = 0  # consecutive cycles with >95% void tiles

    # ── A-press loop detection (STUCK-A-LOOP) ──────────────────────
    S._a_press_count = 0  # consecutive A presses without direction change
    S._MAX_A_PRESS = 3  # after 3 consecutive A presses → trigger recovery
    S._last_action_button = ""  # last non-direction button pressed

    # ── Escalating recovery ────────────────────────────────────────
    S._recovery_level = 0  # current rung of the escalation ladder
    S._recovery_attempts = 0  # total recovery escalations (capped at MAX)
    S._last_state_key = ""  # composite key for state-change detection
    S._gave_up = False  # True once max recovery attempts exhausted
    S._same_frame_count = 0  # consecutive pixel-identical frames (dialog-loop detector)
    S._prev_frame_hash = ""  # previous cycle's frame hash for the counter above
    S._last_saved_frame_hash = ""  # empty guarantees the first cycle is saved
    S._last_plan_sig = ""  # signature of last executed plan (no-op plan guard)
    S._same_plan_count = 0  # consecutive cycles with identical plan + unchanged position
    S._last_pos_key = ""  # last cycle's map:tile position key

    # ── Frame hashing for cartographer cache ───────────────────────
    S._last_frame_hash = ""  # for frame hashing — skip cartographer on identical frames
    S._cached_patch = {}  # cached cartographer output
    S._cached_carto_raw = ""  # cached raw cartographer text

    # ── Frame hashing for Luna vision (controller screenshot dedup) ─
    # Only attach the screenshot to the controller prompt when the
    # frame CHANGED since the last call. Identical frames (standing
    # still, dialog open) re-send the same ~2500 image tokens every
    # cycle — pure waste. RAM text still flows every cycle.
    S._last_controller_frame_hash = ""

    # Persistent counter for the main loop's name_entry handler. The
    # intro loop has its own name-entry-stuck counter; this list-of-one is
    # scoped to the main loop so a re-entry into name_entry outside
    # the intro phase still escalates to programmatic typing after 3
    # cycles.
    S._main_ne_stuck_box = [0]
    S._player_named = S.R._player_named
    S._rival_named = S.R._rival_named


def _init_memory_state(S):
    """Agent memory, metrics, navigation hold, and boot-memory state."""
    global run_agentic_cycle
    from src.core.agentic_loop import (
        BoundedAgentContext,
        DuckBrainAgentMemory,
        ModelResearchDelegate,
        run_agentic_cycle,
    )

    # ── Per-run metrics (GAP-028, DF-USE-1) ───────────────────────
    S._dir_lock_warn_cycles = 0  # cycles with >=1 direction-lock warning
    S._visited_tiles: set[tuple[int, int, int]] = set()  # (map_id, x, y) seen
    # Ordered unique source-map tiles become the proven route on a transition.
    S._route_map_id = None
    S._route_tiles = []
    S._movement_progress_cycles = 0  # comparable cycles whose RAM tile changed
    S._movement_observed_cycles = 0  # cycles with current + previous RAM tiles
    # JEV projection cross-cycle material (DF-JEV-1, PRD v3 §3.4): how many
    # times each tile of the CURRENT map has been stood on. Repeat counts are
    # the projection's stuck signal, so they are reset on a map change.
    S._tile_visits = {}
    S._tile_visits_map_id = None

    S._last_party_count = S.R.ram_reader.party_count() if USE_RAM_READER else 0
    # One-shot starter-pick milestone flag: the milestone fires once per run,
    # either on an in-run 0→1 transition or from a post-pick boot baseline.
    S._starter_milestone_emitted = False
    S._failed_flee_attempts = 0

    # ── Agent memory state (self-maintained, DuckBrain-backed) ──
    # The agent tracks its own goal, notes, and world map across cycles
    # AND across runs. goal/notes/last_dialog/study are injected into the
    # controller prompt each cycle; note/goal/study outputs are executed
    # here and persisted to DuckBrain (namespace pokemon-global).
    S._mem_goal = ""
    S._mem_notes: list[str] = []  # most recent first, capped at 6
    S._last_dialog_text = ""
    S._pending_study_key = ""  # controller asked to study a key
    S._pending_study_result = ""  # fetched content, injected once
    # Deduplicate deterministic world facts within this run. DuckBrain remains
    # the source of truth; retrieval still reads the store on every cycle.
    S._world_memory_written_keys: set[str] = set()
    # S3 context is deliberately run-local: cheap scalar summaries survive the
    # cycle loop, but a new main() invocation starts with no prior turns.
    S._recent_decisions: list[dict[str, Any]] = []
    S._agent_context = BoundedAgentContext()
    S._agent_memory = DuckBrainAgentMemory()
    S._research_delegate = ModelResearchDelegate(
        S.R.controller_client, S.R.controller_model
    )
    # HOLD-1: unlike the bounded transcript, map-edge memory is authoritative
    # run state. It survives every decision cycle and owns the anti-regression
    # goal plus the reverse edge that must not be traversed.
    S._navigation_state = _NavigationHoldState()

    # ── Boot memory (MEM-2, PRD_v2_lifecycle.md §R3) ───────────────
    # Built ONCE here (not per cycle) from the four DuckBrain layers
    # MEM-1 writes: MECHANICS + SAVE + RUN HISTORY + LEARNING. The
    # rendered string rides in the controller system prompt every cycle;
    # a fresh/empty store yields "" so the prompt is unchanged.
    S._boot_memory = _boot_memory_prompt(_build_boot_memory_blocks())
    if S._boot_memory:
        safe_print(
            f"  [MEM] boot injection: {len(S._boot_memory)} chars across "
            f"{S._boot_memory.count('[')} block markers"
        )

    # NOTE: the frame cache is bound in the pipeline-init block, before the
    # main loop. Do NOT re-assign it here — an assignment would wipe it.
    assert S.R.frame_cache is not None  # bound in pipeline-init block above

    if USE_RAM_READER:
        try:
            from src.core import duckbrain_client as _dbc

            _goal_rec = _dbc.get(key="/goals/current")
            if _goal_rec:
                attrs = _goal_rec.get("attributes", {})
                S._mem_goal = str(
                    attrs.get("goal") or _goal_rec.get("embedding_text", "")
                )[:200]
        except Exception as _e:
            safe_print(f"  [MEM] goal load failed: {_e}")


def _run_cycles(S):
    """Run every cycle: shared header, per-screen handling, cycle tail."""
    for cycle in range(CYCLES):
        try:
            header = _cycle_header(S, cycle)
            t0 = time.time()

            # Oak's empty-party menu routes to JEV's starter-species choice.
            if USE_RAM_READER and _should_select_starter(
                map_id=header["map_id"],
                party_count=header["party_count"],
                screen_type=header["st"],
                menu_state=header["menu_state"],
            ):
                _starter_selection(S, cycle, header, t0)
                continue

            if header["st"] == "overworld":
                if _overworld_cycle(S, cycle, header, t0):
                    continue
            elif header["st"] == "name_entry":
                _name_entry_cycle(S, cycle, header, t0)
            else:
                _state_window_cycle(S, cycle, header, t0)
            _cycle_tail(S, cycle, header)
        except Exception:
            traceback.print_exc()
            err_entry = {"cycle": cycle + 1, "error": traceback.format_exc()}
            S.results.append(err_entry)
            S.log_file.write(json.dumps(err_entry, default=str) + "\n")
            S.log_file.flush()


def _cycle_capture(S, cycle):
    """Capture the emulator frame and save the progress screenshot on change."""
    S._cycle_dir_lock_warned = False  # per-cycle flag (GAP-028 metric)
    screenshot = S.R.emu.capture()
    frame_hash = _cycle_frame_hash(screenshot)

    # PNG encoding/writes measured 0.692ms on a static screen versus
    # 0.080ms with this gate. Keep ``img`` for the unconditional battle
    # milestone capture below, but write progress frames only on change.
    img = S.R.image_module.fromarray(screenshot)
    S._img = img
    S._last_saved_frame_hash = _save_cycle_screenshot(
        img,
        cycle=cycle + 1,
        frame_hash=frame_hash,
        last_saved_frame_hash=S._last_saved_frame_hash,
        screenshot_dir=SCREENSHOT_DIR,
    )
    return screenshot, frame_hash


def _cycle_observe(S, screenshot, frame_hash):
    """Classify the screen: RAM reader, or cartographer with frame hashing."""
    if USE_RAM_READER:
        # RAM reader: instant reads; the cycle hash still gates progress saves.
        # RAM reader is instant — always re-observe for accurate state
        patch_data = S.R.ram_reader.observe()
        carto_raw = json.dumps(
            {"source": "ram_reader", "result": patch_data.get("result")}
        )
        return patch_data, carto_raw

    # ── Frame hashing: skip cartographer if nothing changed ──
    # Hash the raw screenshot bytes. If identical to last frame,
    # the character hasn't moved — reuse cached observation.
    # Works for ALL screen types including battles. During battle idle
    # (both Pokémon standing, same HP), the frame is identical and
    # the cached observation is still valid. The Controller/StateWindow
    # still runs and makes decisions — we just skip re-observing.
    if S._last_frame_hash != frame_hash or not S._cached_patch:
        # Frame changed (or first cycle) — call cartographer
        patch_data, carto_raw = cartographer_analyze(
            S.R.controller_client, screenshot
        )
        S._cached_patch = patch_data
        S._cached_carto_raw = carto_raw
        S._last_frame_hash = frame_hash
    else:
        # Frame unchanged — reuse cached observation
        patch_data = S._cached_patch
        carto_raw = S._cached_carto_raw
        safe_print(
            f"  [SKIP] Frame unchanged, reusing cached cartographer ({patch_data.get('result', '?')})"
        )

    # ── Frame-locked detection (pixel-identical, not just same screen TYPE) ──
    # l2_accept_1 failure mode: "My POKéMON looks a..." dialog page
    # recurred 50+ cycles — same screen_type ('dialog') so the
    # same-screen tracker never fired, recovery exhausted, then
    # passive A-mash. Identical pixels = nothing is changing.
    if frame_hash == S._prev_frame_hash:
        S._same_frame_count += 1
    else:
        S._same_frame_count = 0
    S._prev_frame_hash = frame_hash
    return patch_data, carto_raw


def _cycle_track_tiles(S, patch_data):
    """Track visited tiles, proven routes, tile-visit counts, and movement."""
    raw_map_id = patch_data.get("map_id")
    raw_tile_x = patch_data.get("player_tile_x")
    raw_tile_y = patch_data.get("player_tile_y")
    current_tile = None
    if (
        isinstance(raw_map_id, int)
        and isinstance(raw_tile_x, int)
        and isinstance(raw_tile_y, int)
    ):
        current_tile = (raw_map_id, raw_tile_x, raw_tile_y)
    if current_tile is not None:
        S._visited_tiles.add(current_tile)
        if S._route_map_id is None:
            S._route_map_id = current_tile[0]
        if current_tile[0] == S._route_map_id:
            route_tile = {"x": current_tile[1], "y": current_tile[2]}
            if route_tile not in S._route_tiles:
                S._route_tiles.append(route_tile)
        _update_tile_visits(S, current_tile)
    progress_delta, observed_delta = _movement_progress_delta(
        current_tile, S._last_tile
    )
    S._movement_progress_cycles += progress_delta
    S._movement_observed_cycles += observed_delta
    # S6 NAV-MEM: keep the tile stood on BEFORE this cycle's update —
    # it is the door tile of any transition detected just below.
    S._departure_tile = S._last_tile
    S._last_tile, S._same_tile_count = _track_same_tile(
        current_tile, S._last_tile, S._same_tile_count
    )
    tile_recovery_reason = _tile_lock_reason(S._last_tile, S._same_tile_count)

    map_id = int(raw_map_id) if isinstance(raw_map_id, int) else -1
    return {
        "raw_map_id": raw_map_id,
        "raw_tile_x": raw_tile_x,
        "raw_tile_y": raw_tile_y,
        "current_tile": current_tile,
        "tile_recovery_reason": tile_recovery_reason,
        "map_id": map_id,
    }


def _update_tile_visits(S, current_tile):
    """JEV projection (DF-JEV-1): repeat counts for the current map's tiles."""
    if S._tile_visits_map_id != current_tile[0]:
        S._tile_visits.clear()
        S._tile_visits_map_id = current_tile[0]
    tile_visits_key = (current_tile[1], current_tile[2])
    S._tile_visits[tile_visits_key] = (
        S._tile_visits.get(tile_visits_key, 0) + 1
    )


def _handle_navigation_transition(S, cycle, st, patch_data, current_tile, map_id):
    """Detect a map-edge crossing and persist the navigation-hold state.

    HOLD-1: detect the edge before asking either decision path. The
    resulting goal and reverse-edge guard persist for every later
    cycle on the destination map. Saving an anchor here also ensures
    the recovery ladder cannot roll a held transition back to an old
    checkpoint on the source map.
    """
    _navigation_transition = S._navigation_state.observe(
        map_id,
        str(patch_data.get("map_name") or ""),
        S._last_direction,
    )
    if _navigation_transition is None:
        return None
    # S6 NAV-MEM: the departure tile is the door tile of the proven
    # edge, and only counts when it was on the SOURCE map.
    if (
        S._departure_tile is not None
        and S._departure_tile[0] == _navigation_transition["from_map_id"]
    ):
        _navigation_transition["departure_tile"] = {
            "x": S._departure_tile[1],
            "y": S._departure_tile[2],
        }
    _navigation_transition["route_tiles"] = list(S._route_tiles)
    if current_tile is not None:
        S._route_map_id = current_tile[0]
        S._route_tiles = [{"x": current_tile[1], "y": current_tile[2]}]
    S._mem_goal = S._navigation_state.goal
    S._same_dir = None
    S._same_dir_count = 0
    S._recovery_level = 0
    S._recovery_attempts = 0
    S._dir_blacklist.clear()
    if not _navigation_transition["regression"] and st == "overworld":
        try:
            S.R.emu.save_state(S._checkpoint_slot)
            _navigation_transition["anchor_checkpoint_slot"] = (
                S._checkpoint_slot
            )
            S._last_saved_slot = S._checkpoint_slot
            S._checkpoint_slot = (S._checkpoint_slot + 1) % CHECKPOINT_SLOTS
        except Exception as exc:
            _navigation_transition["anchor_checkpoint_error"] = str(exc)
    _navigation_transition = {
        "cycle": cycle + 1,
        **_navigation_transition,
    }
    S.results.append(_navigation_transition)
    S.log_file.write(json.dumps(_navigation_transition, default=str) + "\n")
    S.log_file.flush()
    safe_print(
        "  [NAV-HOLD] "
        f"{_navigation_transition['from_map_name']} -> "
        f"{_navigation_transition['to_map_name']} | "
        f"block={_navigation_transition['blocked_return_direction']} | "
        f"regression={_navigation_transition['regression']}"
    )
    return _navigation_transition


def _cycle_world_and_goal(S, cycle, patch_data, map_id, transition):
    """Populate world memory and seed the default exploration goal (GAP-038)."""
    # S2 world memory: retrieve facts already present at cycle start,
    # then persist this observation. The ordering makes next-cycle use
    # observable in the JEV projection.
    _teacher_targets_for_cycle = S._pending_teacher_memory_targets
    S._pending_teacher_memory_targets = []
    _world_facts = _populate_world_memory(
        observation=patch_data,
        run_id=run_id,
        cycle=cycle + 1,
        results=S.results,
        log_file=S.log_file,
        written_keys=S._world_memory_written_keys,
        retrieval_targets=_teacher_targets_for_cycle,
        transition=transition,
    )

    # ── Default exploration goal (GAP-038) ──────────────
    # Fresh boot states (no stored DuckBrain goal) leave the
    # controller with an empty goal; seed a context-aware
    # default so the agent doesn't wander aimlessly.
    if not S._mem_goal:
        if map_id == OAKS_LAB_MAP_ID:
            S._mem_goal = (
                "Leave Oaks Lab and head toward Route 1 to begin your "
                "Pokemon journey."
            )
        else:
            S._mem_goal = "Explore the current area and look for exits or points of interest."
    return _world_facts


def _cycle_party_state(S, patch_data):
    """Read party count and menu state from RAM or the cartographer patch."""
    if USE_RAM_READER:
        party_count = S.R.ram_reader.party_count()
        menu_state = S.R.ram_reader.read_menu_state()
    else:
        raw_party_count = patch_data.get("party_count", 0)
        party_count = (
            int(raw_party_count) if isinstance(raw_party_count, int) else 0
        )
        raw_menu_state = patch_data.get("menu_state", {})
        menu_state = raw_menu_state if isinstance(raw_menu_state, dict) else {}
    return party_count, menu_state


def _cycle_starter_milestone(S, cycle, party_count):
    """Emit the one-shot starter-picked milestone when the party grows."""
    starter_event, S._starter_milestone_emitted = _starter_milestone_for_cycle(
        previous_party_count=S._last_party_count,
        current_party_count=party_count,
        species_hint=(
            S.R.ram_reader.first_party_species_hint() if USE_RAM_READER else None
        ),
        baseline_starter_name=(
            S.R.ram_reader.first_party_starter_name() if USE_RAM_READER else None
        ),
        milestone_emitted=S._starter_milestone_emitted,
    )
    if starter_event is not None:
        milestone = {"cycle": cycle + 1, **starter_event}
        S.results.append(milestone)
        S.log_file.write(json.dumps(milestone, default=str) + "\n")
        S.log_file.flush()
        safe_print(
            "  [STARTER-PICKED] "
            f"party_count={party_count} "
            f"species_hint={starter_event['species_hint']}"
        )
    S._last_party_count = party_count


def _cycle_header(S, cycle):
    """Run the shared per-cycle prologue: capture, observe, track, remember.

    Returns the cycle bundle (observation, screen type, tiles, party state)
    consumed by the per-screen handlers and the cycle tail.
    """
    screenshot, frame_hash = _cycle_capture(S, cycle)
    patch_data, carto_raw = _cycle_observe(S, screenshot, frame_hash)
    st = patch_data.get("result", "unknown")
    if st != "battle":
        S._failed_flee_attempts = 0

    # ── Dialog text carry-over ──
    # When a dialog box is on screen, capture its text so the NEXT
    # overworld decision can see what was said (Oak's instructions,
    # NPC hints). This is the agent's information channel.
    if st == "dialog" and patch_data.get("text_content"):
        S._last_dialog_text = str(patch_data["text_content"][0])[:200]

    tiles = _cycle_track_tiles(S, patch_data)
    transition = _handle_navigation_transition(
        S, cycle, st, patch_data, tiles["current_tile"], tiles["map_id"]
    )
    world_facts = _cycle_world_and_goal(
        S, cycle, patch_data, tiles["map_id"], transition
    )
    party_count, menu_state = _cycle_party_state(S, patch_data)
    _cycle_starter_milestone(S, cycle, party_count)
    return {
        "cycle": cycle,
        "screenshot": screenshot,
        "frame_hash": frame_hash,
        "patch_data": patch_data,
        "carto_raw": carto_raw,
        "st": st,
        "world_facts": world_facts,
        "party_count": party_count,
        "menu_state": menu_state,
        "pipeline_name": S.R.pipeline_name,
        "img": S._img,
        **tiles,
    }


def _starter_selection(S, cycle, header, t0):
    """Handle Oak's Lab starter selection; always consumes the cycle."""
    safe_print(
        f"  [STARTER] Oak's Lab menu detected at cycle {cycle + 1}; "
        "asking JEV to choose a species"
    )
    starter_decision: dict[str, Any] = {}
    selected_party_count = _select_starter_from_menu(
        S.R.emu,
        S.R.ram_reader,
        decision_out=starter_decision,
    )
    starter_choice = starter_decision.get("starter_choice")
    selection_entry = {
        "cycle": cycle + 1,
        "screen": header["st"],
        "event": "starter_selection",
        "action": "jev_starter_choice",
        "intent": f"select starter {starter_choice or 'unavailable'}",
        "map_id": header["map_id"],
        "party_count_before": header["party_count"],
        "party_count_after": selected_party_count,
        "player_tile_x": header["raw_tile_x"],
        "player_tile_y": header["raw_tile_y"],
        **starter_decision,
    }
    S.results.append(selection_entry)
    S.log_file.write(json.dumps(selection_entry, default=str) + "\n")
    S.log_file.flush()

    starter_event, S._starter_milestone_emitted = (
        _starter_milestone_for_cycle(
            previous_party_count=header["party_count"],
            current_party_count=selected_party_count,
            species_hint=S.R.ram_reader.first_party_species_hint(),
            baseline_starter_name=None,
            milestone_emitted=S._starter_milestone_emitted,
        )
    )
    if starter_event is not None:
        milestone = {"cycle": cycle + 1, **starter_event}
        S.results.append(milestone)
        S.log_file.write(json.dumps(milestone, default=str) + "\n")
        S.log_file.flush()
        safe_print(
            "  [STARTER-PICKED] "
            f"party_count={selected_party_count} "
            f"species_hint={starter_event['species_hint']}"
        )
    S._last_party_count = selected_party_count
    _record_recent_decision(
        S._recent_decisions,
        selection_entry,
        outcome=(
            f"party count {header['party_count']} -> {selected_party_count}; "
            f"starter={starter_choice or 'unavailable'}"
        ),
    )
    safe_print(
        f"  [{cycle + 1}/{CYCLES}] starter_selection | "
        f"party={selected_party_count} | {time.time() - t0:.1f}s"
    )


def _overworld_cycle(S, cycle, header, t0):
    """One overworld cycle: stuck tracking, decision tiers, plan filters, execution.

    Returns True when the caller must skip the cycle tail (recovery consumed
    the cycle via the starter approach).
    """
    patch_data = header["patch_data"]
    st = header["st"]
    # Out of name_entry — reset stuck counter for any future re-entry.
    S._main_ne_stuck_box[0] = 0
    # ── Visual-Reference Pipeline ──────────────────────
    # Cartographer already gave us spatial info (adjacent tiles,
    # visible_exits, player_facing, suggested_action).
    # Feed this directly to the controller — no MapIntegrator needed.
    _ow_track_stuck(S, patch_data, st)
    if _ow_recovery_gate(S, cycle, header):
        return True

    # Frame-cache dedup: hash the raw screenshot; if this exact
    # frame was seen before (same tile, same dialog box, battle
    # idle, looping flow), pass a text UUID reference instead of
    # re-sending the image bytes. First sighting → send image.
    vision_frame, frame_ref = _ow_frame_cache(S, cycle, header)

    decision, pipeline, _jev_outcome, navigation_context = _ow_decide(
        S, cycle, header, vision_frame, frame_ref
    )
    _decision_pipeline = pipeline
    _missing_class = decision.get("missing_class")
    # Study result is injected once, then cleared
    S._pending_study_result = ""
    plan = decision.get("plan", ["A"])
    intent = decision.get("intent", "")

    # ── Agent memory outputs: note / goal / study ──────
    # The controller maintains its own knowledge. These fields
    # are optional; when present they are executed here and
    # persisted to DuckBrain (namespace pokemon-global).
    if USE_RAM_READER:
        S._mem_goal, S._mem_notes, S._pending_study_result = (
            _apply_agent_memory_outputs(
                decision=decision,
                results=S.results,
                log_file=S.log_file,
                cycle=cycle,
                map_name=patch_data.get("map_name", "unknown"),
                mem_goal=S._mem_goal,
                mem_notes=S._mem_notes,
                pending_study_result=S._pending_study_result,
            )
        )

    # ── Programmatic direction override ───────────────
    # Chain-rotate through blacklist. If ALL 4 directions
    # blacklisted, use A (interact) instead — stop walking.
    plan = _apply_dir_blacklist(S, plan)

    # ── Spatial pre-filter: strip wall/object directions ──
    # The cartographer tells us what's actually adjacent. If it says
    # a tile is "wall" or "object", walking there is impossible.
    # Strip those directions BEFORE execution regardless of LLM output.
    plan = _apply_spatial_filter(S, plan, patch_data)

    # ── No-op plan guard (Bane 09-11: 'repeated screens being the
    # same → try something else') — identical plan + unchanged
    # position = the last plan did nothing. Force variation
    # instead of re-sending the same false presses.
    plan, agentic_tool_cycle = _ow_noop_guard(S, cycle, plan, decision, patch_data)

    # ── Run-length cap: max 3 consecutive same direction ──
    # The cartographer only sees the immediate adjacent tile.
    # Long plans (6x RIGHT) walk into walls 2-3 tiles away.
    # Cap consecutive same-direction moves to 3 regardless of LLM.
    plan = _cap_direction_runs(S, plan)

    # ── Post-exhaustion movement injection ─────────────
    # recovery_exhausted used to mean passive A-mash until the
    # run ended (l2_accept_1: ~50 wasted cycles). Instead:
    # rotate real inputs — walk, open menu, back out. The
    # injected presses can also RESET a stuck state, which
    # re-enables normal recovery on later cycles.
    plan = _ow_giveup_plan(S, cycle, plan, agentic_tool_cycle)

    # HOLD-1 is the final movement filter so blacklist rotation,
    # no-op recovery, and post-exhaustion injection cannot
    # reintroduce the completed edge's reverse direction.
    plan = _ow_navigation_guard(S, cycle, plan, decision, navigation_context)

    plan_entry = {
        "cycle": cycle + 1,
        "screen": header["st"],
        "pipeline": _decision_pipeline,
        # The family the spelling means. `decision_mode` keeps its
        # historical value so existing logs stay comparable (M6);
        # this field is the branchable one.
        "decision_mode_family": current_mode_family(),
        "agentic_tools_enabled": _model_tools_enabled(DECISION_MODE),
        "agentic_tool_calls": int(decision.get("agentic_tool_calls", 0)),
        "context_evidence": S._agent_context.evidence(),
        "context_snapshot": S._agent_context.render(),
        "plan": plan,
        "intent": intent,
        "navigation_hold": navigation_context,
        "navigation_hold_applied": decision.get("_navigation_hold_applied", False),
        # JEV-1 (PRD v3 AC-1): every decision row carries the
        # autonomy fields. DF-JEV-1 wired the JEV tier into this
        # loop, so a row JEV decided (`pipeline="jev"`) fills them
        # from JEV's real payload, `raw_distribution` included; a
        # row from the controller fallback path carries none of
        # these keys and reports the defaults, which is exactly the
        # split `_autonomy_counters` counts at closeout.
        "jev_answered": bool(decision.get("jev_answered", False)),
        "escalated": bool(decision.get("escalated", False)),
        # PERCEPT-1: this decision's own API usage (tokens +
        # provider cost), None when the provider reported none.
        "vision_usage": decision.get("vision_usage"),
        "_cartographer_usage": header["patch_data"].get("_cartographer_usage"),
        "missing_class": (
            _missing_class if isinstance(_missing_class, str) else None
        ),
        "reported_missing_class": decision.get("reported_missing_class"),
        # S6 NAV-MEM: the path-memory outcome of this navigation
        # decision — a hit cites the exact ``/world/path/...`` key
        # the route came from; a miss names why no route was used.
        "memory_navigation": decision.get("memory_navigation"),
        "raw_distribution": decision.get("raw_distribution"),
        "scenario_post_distribution": decision.get(
            "scenario_post_distribution"
        ),
        "scenario_patch_id": decision.get("scenario_patch_id"),
        "scenario_patch_evidence": decision.get("scenario_patch_evidence"),
        "scenario_patch_applied": bool(
            decision.get("scenario_patch_applied", False)
        ),
        # Handoff provenance (M3/M5): which trigger fired, whether
        # this run's policy allowed it, and why not when it did not.
        "handoff_trigger": decision.get("handoff_trigger"),
        "handoff_allowed": decision.get("handoff_allowed"),
        "handoff_blocked_reason": decision.get("handoff_blocked_reason"),
        **_jev_outcome,
        "jev_projection_chars": decision.get("jev_projection_chars"),
        "controller_raw": decision.get("raw_response", ""),
        "frame_cache": "hit" if frame_ref else "miss",
        "frame_uuid": frame_ref,
        "cartographer_raw": header["carto_raw"],
        "map_id": header["patch_data"].get("map_id"),
        "map_name": header["patch_data"].get("map_name"),
        "player_x": header["patch_data"].get("player_x"),
        "player_y": header["patch_data"].get("player_y"),
        "player_tile_x": header["patch_data"].get("player_tile_x"),
        "player_tile_y": header["patch_data"].get("player_tile_y"),
    }

    S.results.append(plan_entry)
    S.log_file.write(json.dumps(plan_entry, default=str) + "\n")
    S.log_file.flush()

    # ── Execute the plan ──────────────────────────────
    _ow_execute_plan(S, plan)

    if plan:
        S._last_result = f"executed {len(plan)} input(s): " + ", ".join(
            str(button).upper() for button in plan
        )
    else:
        S._last_result = "no input executed (WAIT)"
    _record_recent_decision(
        S._recent_decisions,
        plan_entry,
        outcome=S._last_result,
        agent_context=S._agent_context,
        text_facts=(
            patch_data.get("text_content") or patch_data.get("text_lines") or []
        ),
    )

    elapsed = time.time() - t0
    safe_print(
        f"  [{cycle + 1}/{CYCLES}] {st} | {pipeline} x{CART_STEPS} | {elapsed:.1f}s"
    )
    return False


def _ow_track_stuck(S, patch_data, st):
    """Track void tiles, same-screen streaks, and state changes (overworld)."""
    # ── Stuck detection: track void tiles from cartographer output ──
    adj = patch_data.get("adjacent", {})
    if adj:
        unknown_tiles = sum(
            1 for v in adj.values() if v in ("unknown", "?", "")
        )
        total_tiles = len(adj)
        S._void_tile_pct = (
            unknown_tiles / total_tiles if total_tiles > 0 else 0.0
        )
        if S._void_tile_pct > 0.95:
            S._void_cycles += 1
            safe_print(
                f"  [VOID] {unknown_tiles}/{total_tiles} tiles unknown ({S._void_tile_pct:.0%}) — cycle {S._void_cycles}/{MAX_VOID_CYCLES} | map_id={patch_data.get('map_id')} map={patch_data.get('map_name')} player=({patch_data.get('player_tile_x')},{patch_data.get('player_tile_y')})"
            )
        else:
            S._void_cycles = 0
    else:
        S._void_tile_pct = 0.0
        S._void_cycles = 0

    # ── Same-screen tracking ───────────────────────────
    if st == S._last_screen_type:
        S._same_screen_count += 1
    else:
        S._same_screen_count = 0
    S._last_screen_type = st

    # ── State-change detection (resets recovery counter) ──
    state_key = f"{st}:{patch_data.get('screen_subtype', '')}:{adj.get('up', '')}{adj.get('down', '')}{adj.get('left', '')}{adj.get('right', '')}"
    if state_key != S._last_state_key and S._last_state_key != "":
        S._recovery_attempts = 0
        S._recovery_level = 0
        safe_print(f"  [STATE] Changed → {st} — recovery counter reset")
    S._last_state_key = state_key


def _ow_needs_recovery(S, tile_recovery_reason, st):
    """Evaluate the overworld stuck conditions; returns (needs, reason)."""
    del st  # kept for signature symmetry with the StateWindow variant
    # ── Recovery check: any stuck condition triggers escalation ──
    if S._gave_up:
        return False, ""  # already exhausted — no more recovery
    if tile_recovery_reason:
        return True, tile_recovery_reason
    if S._same_dir_count >= MAX_STUCK_SAME_DIR:
        return True, (
            f"direction-locked ({S._same_dir} x{S._same_dir_count})"
        )
    if (
        S._same_screen_count >= MAX_SAME_SCREEN_CYCLES
        and S._last_screen_type != "overworld"
    ):
        return True, (
            f"screen-locked ({S._last_screen_type} x{S._same_screen_count})"
        )
    if S._same_frame_count >= MAX_SAME_FRAME_CYCLES:
        return True, (
            f"frame-locked (identical pixels x{S._same_frame_count})"
        )
    if S._void_cycles >= MAX_VOID_CYCLES:
        return True, f"void-locked ({S._void_cycles} cycles, {S._void_tile_pct:.0%} unknown)"
    if S._a_press_count >= S._MAX_A_PRESS:
        return True, f"A-press locked (A x{S._a_press_count})"
    return False, ""


def _ow_recovery_gate(S, cycle, header):
    """Check the overworld stuck conditions and run one recovery attempt.

    Returns True when the recovery consumed the cycle (starter approach).
    """
    needs, reason = _ow_needs_recovery(S, header["tile_recovery_reason"], header["st"])
    if not needs:
        return False
    if S._recovery_attempts >= MAX_RECOVERY_ATTEMPTS:
        _recovery_give_up(S, cycle, reason, label="recovery attempts")
        return False
    S._recovery_attempts += 1
    return _execute_recovery(S, cycle, reason, header)


def _recovery_give_up(S, cycle, reason, *, label):
    """Stamp recovery_exhausted once; the run then injects rotation input."""
    if not S._gave_up:
        S._gave_up = True
        safe_print(
            f"  [RECOVER] GIVING UP after {S._recovery_attempts} {label} ({reason})"
        )
        evt = {
            "cycle": cycle + 1,
            "event": "recovery_exhausted",
            "reason": reason,
            "attempts": S._recovery_attempts,
        }
        S.results.append(evt)
        S.log_file.write(json.dumps(evt, default=str) + "\n")
        S.log_file.flush()


def _maybe_approach_starter(S, reason, header):
    """Tile-lock in Oaks Lab with an empty party: walk to the first ball."""
    if (
        "tile-locked" in reason
        and USE_RAM_READER
        and header["map_id"] == OAKS_LAB_MAP_ID
        and header["party_count"] == 0
    ):
        return _approach_first_starter(S.R.emu, S.R.ram_reader)
    return False


def _execute_recovery(S, cycle, reason, header):
    """Run one escalating-recovery attempt and stamp its event row.

    Returns True when the recovery took the starter-approach shortcut.
    """
    starter_approached = _maybe_approach_starter(S, reason, header)
    recovery_decision: dict[str, Any] = {}
    if starter_approached:
        strategy, desc = (
            "starter_approach",
            "moved to the nearest Poké Ball and opened its dialog",
        )
    else:
        strategy, desc = _escalating_recovery(
            S.R.emu,
            S._recovery_level,
            S._last_direction,
            S._last_saved_slot,
            game_state=header["patch_data"],
            decision_out=recovery_decision,
            forbidden_directions=(
                {S._navigation_state.blocked_return_direction}
                if S._navigation_state.blocked_return_direction
                else None
            ),
        )
    S._recovery_level += 1
    _blacklist_on_checkpoint(S, strategy)
    safe_print(
        f"  [RECOVER] Level {S._recovery_level - 1}: {strategy} — {desc} ({reason}) [attempt {S._recovery_attempts}/{MAX_RECOVERY_ATTEMPTS}]"
    )
    evt = {
        "cycle": cycle + 1,
        "event": "recovery",
        "level": S._recovery_level - 1,
        "strategy": strategy,
        "reason": reason,
        "attempt": S._recovery_attempts,
        "description": desc,
        **recovery_decision,
    }
    S.results.append(evt)
    S.log_file.write(json.dumps(evt, default=str) + "\n")
    S.log_file.flush()
    _apply_reset_trackers(
        S,
        _reset_recovery_trackers(
            reason,
            same_dir=S._same_dir,
            same_dir_count=S._same_dir_count,
            same_screen_count=S._same_screen_count,
            same_tile_count=S._same_tile_count,
            void_cycles=S._void_cycles,
            a_press_count=S._a_press_count,
        ),
    )
    return starter_approached


def _blacklist_on_checkpoint(S, strategy):
    """Blacklist the blocked direction on checkpoint restore."""
    if (
        strategy == "load_checkpoint"
        and S._same_dir
        and S._same_dir in _DIR_ROTATION
    ):
        S._dir_blacklist.add(S._same_dir)
        safe_print(
            f"  [BLACKLIST] {S._same_dir} added to blacklist: {S._dir_blacklist}"
        )


def _apply_reset_trackers(S, trackers):
    """Rebind the six recovery trackers from a _reset_recovery_trackers result."""
    S._same_dir = trackers.same_dir
    S._same_dir_count = trackers.same_dir_count
    S._same_screen_count = trackers.same_screen_count
    S._same_tile_count = trackers.same_tile_count
    S._void_cycles = trackers.void_cycles
    S._a_press_count = trackers.a_press_count


def _ow_frame_cache(S, cycle, header):
    """Frame-cache dedup for the controller screenshot; returns (frame, ref)."""
    screenshot = header["screenshot"]
    st = header["st"]
    ctrl_frame_hash = header["frame_hash"]
    frame_ref = None
    cached_entry = (
        S.R.frame_cache.lookup(ctrl_frame_hash) if S.R.frame_cache else None
    )
    if cached_entry is not None:
        # Repeat sighting — reference, don't re-send the image
        S.R.frame_cache.touch(cached_entry, cycle + 1)
        vision_frame = None
        frame_ref = cached_entry["uuid"]
        seen_n = cached_entry.get("seen_count", 1)
        safe_print(
            f"  [CACHE-HIT] frame {ctrl_frame_hash[:8]} → ref {frame_ref} (seen {seen_n}x)"
        )
    else:
        # New frame — send the image, remember it
        vision_frame = screenshot
        frame_ref = None
        if S.R.frame_cache is not None:
            S.R.frame_cache.register(
                ctrl_frame_hash,
                cycle + 1,
                map_name=header["patch_data"].get("map_name", ""),
                screen=st,
            )
    return vision_frame, frame_ref


def _ow_jev_attempt(S, header):
    """Ask the JEV tier for this cycle's plan (DF-JEV-1, PRD v3 stages 5-6).

    The cheap System-One tier decides this overworld cycle from
    the bounded RAM projection BEFORE the reasoning controller is
    consulted at all, so a JEV hit skips the controller call and
    its image tokens. A miss (invalid action, transport error)
    falls through to controller_plan() exactly as before; the only
    way JEV can express "press nothing" is an empty plan, and the
    loop never invents a press for an answer it could not read.
    """
    _jev_attempt = _jev_or_none(
        header["patch_data"],
        goal=S._mem_goal,
        visited=S._tile_visits,
        recent_events=S.results,
        recent_decisions=S._recent_decisions,
        world_facts=header["world_facts"],
        last_action=S._last_direction or "",
        # PRD v3 §3.2 trigger 1 (failure): a DIRECTION press that
        # left the player on the same (map, tile) changed nothing,
        # so the gate must escalate regardless of confidence. A
        # non-movement last action leaves the result UNKNOWN.
        last_action_changed_state=(
            S._same_tile_count == 1
            if S._last_direction in _DIR_ROTATION
            else None
        ),
        teacher_api_client=S.R.controller_client,
        teacher_model=S.R.controller_model,
        teacher_memory=S._boot_memory or None,
        teacher_log_file=S.log_file,
        teacher_cycle=header["cycle"] + 1,
        teacher_results=S.results,
        escalated_classes=S._teacher_escalated_classes,
        handoff_policy=HANDOFF_POLICY,
        teacher_budget=S._teacher_budget,
        scenario_path=DEFAULT_JEV_SCENARIO_PATH,
        # S6 NAV-MEM: the maps this run has already entered, so a
        # proven route is only replayed toward NEW ground.
        visited_maps=S._navigation_state.visited_maps,
    )
    return _jev_attempt


def _ow_queue_teacher_targets(S, jev_attempt):
    """Queue a teacher patch's /world/* retrieval targets for next cycle."""
    if not isinstance(jev_attempt, dict):
        return
    raw_targets = jev_attempt.get("teacher_memory_targets")
    if isinstance(raw_targets, list):
        S._pending_teacher_memory_targets = [
            target
            for target in raw_targets
            if isinstance(target, str) and target.startswith("/world/")
        ]
        if S._pending_teacher_memory_targets:
            safe_print(
                "  [MEM-WORLD] queued teacher targets for next cycle: "
                + ", ".join(S._pending_teacher_memory_targets)
            )


def _ow_decide(S, cycle, header, vision_frame, frame_ref):
    """Run the decision tiers for this overworld cycle (Step 2a/2b).

    Returns (decision, pipeline, jev_outcome, navigation_context).
    """
    global controller_model
    controller_model = header["pipeline_name"] and S.R.controller_model
    pipeline_name = header["pipeline_name"]
    # HOLD-1 projects the run-local map history into the reasoning
    # path while the fast tier receives the same persistent goal.
    navigation_context = S._navigation_state.context()
    controller_spatial = {
        **header["patch_data"],
        "navigation_hold": navigation_context,
    }

    _jev_attempt = _ow_jev_attempt(S, header)
    _ow_queue_teacher_targets(S, _jev_attempt)
    _jev_outcome = (
        _jev_outcome_fields(_jev_attempt)
        if isinstance(_jev_attempt, dict)
        else {"jev_ok": None}
    )
    # ── Step 2a-pre: S6 NAV-MEM result ─────────────────────
    # A proven route from ``world/path/*`` already answered this
    # navigation decision, so neither the teacher (LLM) nor the
    # reasoning controller is consulted; the row is stamped with the
    # memory pipeline and the cited key.
    _memory_route = (
        _jev_attempt.get("memory_navigation")
        if isinstance(_jev_attempt, dict)
        else None
    )
    _memory_hit = bool(
        isinstance(_memory_route, dict)
        and _memory_route.get("result") == "hit"
    )
    if (
        _memory_hit
        and isinstance(_jev_attempt, dict)
        and isinstance(_memory_route, dict)
    ):
        decision = {**_jev_attempt, **_jev_outcome}
        _decision_pipeline = MEMORY_NAV_PIPELINE
        pipeline = _decision_pipeline
        safe_print(
            f"  [NAV-MEM] {decision['intent']} | no LLM call | "
            f"cited {_memory_route['key']}"
        )
    elif _jev_attempt and _jev_attempt.get("jev_answered"):
        decision = {**_jev_attempt, **_jev_outcome}
        _decision_pipeline = JEV_PIPELINE
        pipeline = _decision_pipeline
        safe_print(
            f"  [JEV] {decision['intent']} | projection "
            f"{decision['jev_projection_chars']} chars | "
            f"escalated={decision['escalated']} "
            f"({decision.get('jev_escalate_reason')})"
        )
    else:
        # ── Step 2b: controller outputs the movement PLAN ──
        # from the spatial description (JEV miss / unavailable).
        if _model_tools_enabled(DECISION_MODE):
            agentic_result = run_agentic_cycle(
                client=S.R.controller_client,
                emulator=S.R.emu,
                observe=(
                    S.R.ram_reader.observe
                    if USE_RAM_READER
                    else lambda: dict(header["patch_data"])
                ),
                projection=header["patch_data"],
                context=S._agent_context,
                memory=S._agent_memory,
                delegate=S._research_delegate,
                model=controller_model,
                cycle=cycle + 1,
                decision_mode=DECISION_MODE,
                decision_mode_family=current_mode_family(),
                run_id=run_id,
            )
            decision = agentic_result.decision
            for tool_event in agentic_result.events:
                S.results.append(tool_event)
                S.log_file.write(json.dumps(tool_event, default=str) + "\n")
            if agentic_result.events:
                S.log_file.flush()
            _decision_pipeline = "agentic_tools"
            pipeline = _decision_pipeline
        else:
            decision = controller_plan(
                S.R.controller_client,
                controller_spatial,
                S._last_direction or "",
                S._last_result,
                blocked_dir=S._same_dir or "",
                blocked_count=S._same_dir_count,
                max_actions=CART_STEPS,
                screenshot=vision_frame,  # None on cache hit → no image cost
                frame_ref=frame_ref,  # UUID text ref on cache hit
                goal=S._mem_goal,
                notes=" | ".join(S._mem_notes[:6])[:300],
                last_dialog=S._last_dialog_text,
                study_result=S._pending_study_result,
                boot_memory=S._boot_memory,  # MEM-2: built once at boot
                recent_decisions=S._recent_decisions,
                running_summary=S._agent_context.summary,
                world_facts=header["world_facts"],
                # GAP-052: model=controller_model, resolved once at runtime setup
                # as S.R.controller_model.
                model=controller_model,
            )
            _decision_pipeline = pipeline_name
            pipeline = _decision_pipeline
        decision.update(_jev_outcome)
    return decision, pipeline, _jev_outcome, navigation_context


def _apply_dir_blacklist(S, plan):
    """Chain-rotate blacklisted directions out of the plan.

    If ALL 4 directions blacklisted, use A (interact) instead — stop walking.
    """
    if not S._dir_blacklist:
        return plan
    filtered_plan = []
    for btn in plan:
        btn_upper = btn.upper()
        direction = btn_upper
        if direction in ("UP", "DOWN", "LEFT", "RIGHT"):
            for _ in range(4):
                if (
                    direction in S._dir_blacklist
                    and direction in _DIR_ROTATION
                ):
                    direction = _DIR_ROTATION[direction]
                else:
                    break
            # If we cycled back to a blacklisted direction, all 4 blocked
            if direction in S._dir_blacklist:
                direction = "A"  # interact instead
        filtered_plan.append(direction)
    if filtered_plan != [b.upper() for b in plan]:
        safe_print(
            f"  [OVERRIDE] Blacklisted {S._dir_blacklist}, plan {plan[:6]}→{filtered_plan[:6]}..."
        )
    return filtered_plan


def _apply_spatial_filter(S, plan, patch_data):
    """Strip wall/object directions the cartographer says are impossible."""
    blocked_spatial = _blocked_spatial_directions(patch_data)
    if not blocked_spatial:
        return plan
    before_filter = plan[:]
    blocked_upper = {d.upper() for d in blocked_spatial}
    filtered = [
        b
        for b in plan
        if b.upper() not in blocked_upper
        or b.upper() not in ("UP", "DOWN", "LEFT", "RIGHT")
    ]
    # If filtering removed everything, keep the original plan.
    # The cartographer's adjacent data can be wrong (e.g. bed
    # mislabeled as "wall"), and the LLM may know better.
    if filtered:
        plan = filtered
    if len(plan) < len(before_filter):
        safe_print(
            f"  [SPATIAL] Removed {blocked_spatial} from "
            f"plan {before_filter[:3]}→{plan[:3]}..."
        )
    return plan


def _ow_noop_guard(S, cycle, plan, decision, patch_data):
    """No-op plan guard; returns (plan, agentic_tool_cycle)."""
    pos_key = f"{patch_data.get('map_id')}:{patch_data.get('player_tile_x')},{patch_data.get('player_tile_y')}"
    plan_sig = ",".join(b.upper() for b in plan[:6])
    if plan_sig == S._last_plan_sig and pos_key == S._last_pos_key:
        S._same_plan_count += 1
    else:
        S._same_plan_count = 0
    S._last_plan_sig = plan_sig
    S._last_pos_key = pos_key
    agentic_tool_cycle = bool(
        _model_tools_enabled(DECISION_MODE)
        and int(decision.get("agentic_tool_calls", 0)) > 0
    )
    if S._same_plan_count >= 2 and not agentic_tool_cycle:
        alt = _GIVEUP_SEQUENCE[S._same_plan_count % len(_GIVEUP_SEQUENCE)]
        plan = [alt, "A"]
        safe_print(
            f"  [NOOP-GUARD] identical plan x{S._same_plan_count} + no movement — forcing [{alt}, A]"
        )
        evt = {
            "cycle": cycle + 1,
            "event": "noop_plan_guard",
            "identical_plan": plan_sig,
            "pos": pos_key,
            "forced": [alt, "A"],
        }
        S.results.append(evt)
        S.log_file.write(json.dumps(evt, default=str) + "\n")
        S.log_file.flush()
    return plan, agentic_tool_cycle


def _cap_direction_runs(S, plan):
    """Cap consecutive same-direction moves to 3 regardless of LLM output."""
    del S
    rle = 1
    for i in range(1, len(plan)):
        if plan[i].upper() == plan[i - 1].upper() and plan[i].upper() in (
            "UP",
            "DOWN",
            "LEFT",
            "RIGHT",
        ):
            rle += 1
        else:
            rle = 1
        if rle > 3:
            plan[i] = "A"  # replace with interact
            rle = 1
            safe_print(
                f"  [CAP] Truncated same-direction run at position {i}"
            )
    return plan


def _ow_giveup_plan(S, cycle, plan, agentic_tool_cycle):
    """Post-exhaustion rotation: inject real inputs instead of A-mashing."""
    if S._gave_up and not agentic_tool_cycle:
        plan = [_GIVEUP_SEQUENCE[cycle % len(_GIVEUP_SEQUENCE)]]
        safe_print(
            f"  [GIVEUP-WALK] injecting {plan} (post-exhaustion rotation)"
        )
        evt = {"cycle": cycle + 1, "event": "giveup_walk", "injected": plan}
        S.results.append(evt)
        S.log_file.write(json.dumps(evt, default=str) + "\n")
        S.log_file.flush()
    return plan


def _ow_navigation_guard(S, cycle, plan, decision, navigation_context):
    """HOLD-1 final movement filter; stamps the navigation_hold_guard row."""
    controller_hold_event = decision.get("navigation_hold_event")
    plan, _final_hold_event = _guard_navigation_plan(
        plan,
        navigation_context,
    )
    navigation_hold_event = (
        _final_hold_event
        if _final_hold_event is not None
        else (
            controller_hold_event
            if isinstance(controller_hold_event, dict)
            else None
        )
    )
    decision["_navigation_hold_applied"] = navigation_hold_event is not None
    if navigation_hold_event is not None:
        navigation_hold_event = {
            "cycle": cycle + 1,
            "event": "navigation_hold_guard",
            **navigation_hold_event,
            "executed_plan": plan,
        }
        S.results.append(navigation_hold_event)
        S.log_file.write(
            json.dumps(navigation_hold_event, default=str) + "\n"
        )
        S.log_file.flush()
        safe_print(
            "  [NAV-HOLD] blocked "
            f"{navigation_hold_event['blocked_direction']} -> "
            f"{navigation_hold_event['replacement_direction']} | "
            f"plan={plan}"
        )
    return plan


def _ow_execute_plan(S, plan):
    """Press each planned button, tracking stuck/A-press counters per press."""
    # ── Execute the plan ──────────────────────────────
    btn_map = {
        "UP": "up",
        "DOWN": "down",
        "LEFT": "left",
        "RIGHT": "right",
        "A": "a",
        "B": "b",
        "START": "start",
        "SELECT": "select",
    }
    for button in plan:
        button = button.upper()
        btn = btn_map.get(button, "a")
        S.R.emu.press_button(btn, frames=PRESS_FRAMES)
        if button in ("UP", "DOWN", "LEFT", "RIGHT"):
            _settle_directional_step(S.R.emu, S.R.ram_reader)
        else:
            S.R.emu.fast_forward(STEP_FORWARD)
        S._last_direction = button

        # Blocked-direction tracking (per-button for recovery)
        if button in ("UP", "DOWN", "LEFT", "RIGHT"):
            if button == S._same_dir:
                S._same_dir_count += 1
            else:
                S._same_dir = button
                S._same_dir_count = 1
            # Direction press resets A-press counter
            S._a_press_count = 0
        elif button == "A":
            S._same_dir = None
            S._same_dir_count = 0
            S._a_press_count += 1
            S._last_action_button = "A"
            if S._a_press_count == 3:
                safe_print(
                    "  [WARN] A-press lock detected: A x3 — triggering recovery"
                )
        else:
            S._same_dir = None
            S._same_dir_count = 0
            S._a_press_count = 0

        if S._same_dir_count == 3:
            safe_print(
                f"  [WARN] Direction-locking detected: {S._same_dir} x3"
            )
            S._cycle_dir_lock_warned = True
        # Recovery is now handled centrally in the stuck-detection block
        # after cartographer analysis, using the escalating recovery ladder.


def _name_entry_cycle(S, cycle, header, t0):
    """Main-loop name-entry bypass: programmatic typing after stuck cycles."""
    # ── Name entry bypass (main loop) ──────────────────
    # Use programmatic typing after 3 stuck cycles. The intro
    # loop handles the first two name_entry screens; if we
    # hit one again here (e.g. New Game from title without
    # intro), drive the keyboard directly. A-mashing alone
    # fills the name field with "AAAAAAAA" / "A..." rather
    # than the canonical ASH/BLUE, so always prefer enter_name.
    # Counter held in a single-element list so it persists
    # across main-loop cycles without adding new state attrs
    # to emu/ctx or a new import.
    S._main_ne_stuck_box[0] += 1
    main_ne_stuck = S._main_ne_stuck_box[0]

    if main_ne_stuck >= S.R._NAME_ENTRY_STUCK_MAX:
        if not S._player_named:
            safe_print("  [main] Name entry stuck — accepting player name")
            S.R.emu.submit_name()
            S._player_named = True
            S.ctx.player_name = "ASH"
        elif not S._rival_named:
            safe_print("  [main] Rival name stuck — accepting rival name")
            S.R.emu.submit_name()
            S._rival_named = True
            S.ctx.rival_name = "GARY"
        S._main_ne_stuck_box[0] = 0
    else:
        # Not yet stuck — A-mash briefly to give dialog time to advance
        _intro_mash(S.R)

    elapsed = time.time() - t0
    entry = {
        "cycle": cycle + 1,
        "screen": header["st"],
        "action": "name_bypass",
        "elapsed_s": round(elapsed, 1),
        "cartographer_raw": header["carto_raw"],
    }
    S.results.append(entry)
    _record_recent_decision(
        S._recent_decisions,
        entry,
        outcome=f"name-entry bypass attempt {main_ne_stuck}",
    )
    S.log_file.write(json.dumps(entry, default=str) + "\n")
    S.log_file.flush()
    safe_print(
        f"  [{cycle + 1}/{CYCLES}] {header['st']} | name_bypass "
        f"(stuck={main_ne_stuck}/{S.R._NAME_ENTRY_STUCK_MAX}) | {elapsed:.1f}s"
    )


def _state_window_cycle(S, cycle, header, t0):
    """Traditional StateWindow flow for dialog/battle/menu/other screens."""
    st = header["st"]
    patch_data = header["patch_data"]
    # ── Traditional StateWindow flow ───────────────────
    # Reset name_entry stuck counter — we've left name_entry.
    S._main_ne_stuck_box[0] = 0
    vis_dict = _sw_vis_dict(S, st, patch_data)
    _sw_battle_transition_events(S, cycle, st, vis_dict)
    _sw_track_stuck(S, st, vis_dict)
    if _sw_recovery(S, cycle, header, st):
        return
    state_type = st
    if vis_dict.get("screen_subtype") == "keyboard":
        state_type = "name_entry"

    # ── Rival battle detection ────────────────────────
    if vis_dict.get("screen_subtype") == "rival_battle":
        _sw_rival_battle(S, cycle)

    # Normal battle turns ask JEV first. StateWindow executes the typed
    # choice directly; its established model/select_move(1) path remains
    # the fallback when JEV is disabled, unavailable, or malformed.
    battle_jev_decision = (
        _observe_battle_decision(vis_dict)
        if state_type == "battle"
        else None
    )
    _sw_run_window(S, cycle, header, st, state_type, vis_dict, battle_jev_decision, t0)


def _sw_vis_dict(S, st, patch_data):
    """Build the StateWindow vision dict (with RAM enrichment when enabled)."""
    # Build StateWindow-compatible vision dict from cartographer output
    vis_dict = {
        "screen_type": st,
        "screen_subtype": patch_data.get("screen_subtype", ""),
        "name_field": patch_data.get("name_field", ""),
        "text_lines": patch_data.get("text_lines", []),
        "text_content": patch_data.get(
            "text_content", patch_data.get("text_lines", [])
        ),
        "menu_items": patch_data.get("menu_items", []),
        "adjacent_tiles": patch_data.get("adjacent_tiles", {}),
        "keyboard_grid": patch_data.get("keyboard_grid", {}),
    }

    # ── RAM reader enrichment for battle/dialog screens ──
    # When USE_RAM_READER is True, inject live RAM state into
    # the StateWindow vision dict so it can build compact prompts.
    if USE_RAM_READER:
        ram_reader = S.R.ram_reader
        if st == "battle":
            bs = ram_reader.read_battle_state()
            vis_dict["battle_state"] = bs
            vis_dict["render"] = ram_reader.render_battle()
            vis_dict["result"] = "battle"
        elif st == "dialog":
            vis_dict["render"] = ram_reader.render_dialog()
            vis_dict["result"] = "dialog"
        elif st == "menu" or st == "list_menu":
            ms = ram_reader.read_menu_state()
            if ms.get("menu_id", 0) > 0:
                vis_dict["render"] = ram_reader.render_menu()
                vis_dict["result"] = "menu"
    return vis_dict


def _sw_battle_transition_events(S, cycle, st, vis_dict):
    """Log battle_start / battle_end transitions from screen-type changes."""
    # ── Battle start/end logging ──────────────────────
    if st == "battle" and S._last_screen_type != "battle":
        evt = {
            "cycle": cycle + 1,
            "event": "battle_start",
            "battle_type": vis_dict.get("battle_state", {}).get(
                "battle_type", "unknown"
            ),
        }
        S.results.append(evt)
        S.log_file.write(json.dumps(evt, default=str) + "\n")
        S.log_file.flush()
        safe_print(
            f"  [BATTLE-START] {vis_dict.get('battle_state', {}).get('battle_type', 'unknown')} battle began"
        )
    elif st != "battle" and S._last_screen_type == "battle":
        evt = {"cycle": cycle + 1, "event": "battle_end", "next_screen": st}
        S.results.append(evt)
        S.log_file.write(json.dumps(evt, default=str) + "\n")
        S.log_file.flush()
        safe_print(f"  [BATTLE-END] → {st}")


def _sw_track_stuck(S, st, vis_dict):
    """Same-screen tracking + state-change reset for StateWindow screens."""
    # ── Stuck detection: unified tracking + escalating recovery ──
    # Track same-screen (already tracked in overworld pipeline, but
    # StateWindow path handles other screen types — dialog, battle, menu)
    if st == S._last_screen_type:
        S._same_screen_count += 1
    else:
        S._same_screen_count = 0
    S._last_screen_type = st

    # State-change detection resets recovery counter
    state_key = f"{st}:{vis_dict.get('screen_subtype', '')}"
    if state_key != S._last_state_key and S._last_state_key != "":
        S._recovery_attempts = 0
        S._recovery_level = 0
        safe_print(f"  [STATE] Changed → {st} — recovery counter reset")
    S._last_state_key = state_key


def _sw_needs_recovery(S, tile_recovery_reason, st):
    """Evaluate the StateWindow stuck conditions; returns (needs, reason)."""
    # Check if recovery needed
    if S._gave_up:
        return False, ""
    if tile_recovery_reason:
        return True, tile_recovery_reason
    if S._same_screen_count >= MAX_SAME_SCREEN_CYCLES and st != "overworld":
        return True, f"screen-locked ({st} x{S._same_screen_count})"
    if S._same_dir_count >= MAX_STUCK_SAME_DIR:
        return True, (
            f"direction-locked ({S._same_dir} x{S._same_dir_count})"
        )
    return False, ""


def _sw_recovery(S, cycle, header, st):
    """StateWindow recovery ladder (incl. the dialog fast-path).

    Returns True when the cycle must skip StateWindow (recovery or the
    dialog fast-path consumed it).
    """
    needs, reason = _sw_needs_recovery(S, header["tile_recovery_reason"], st)
    if not needs:
        return False
    if S._recovery_attempts >= MAX_RECOVERY_ATTEMPTS:
        _recovery_give_up(S, cycle, reason, label="attempts")
        return False
    S._recovery_attempts += 1
    starter_approached = _maybe_approach_starter(S, reason, header)
    # ── Dialog fast-path ─────────────────────────
    # A dialog box is NOT a stuck state — it needs A
    # presses to advance the text. The generic ladder
    # (START→B→B menu_redraw) is wrong here and was
    # keeping the agent trapped in Oak's dialog for
    # 70+ cycles. A-mash to advance the conversation.
    if st == "dialog" and not starter_approached:
        for _ in range(12):
            S.R.emu.press_button("a", frames=S.R._A_FRAMES)
            S.R.emu.fast_forward(S.R._FF_FRAMES)
        strategy, desc = (
            "dialog_advance",
            "12× A — advancing dialog text",
        )
        safe_print(
            f"  [RECOVER] {strategy} — {desc} ({reason}) [attempt {S._recovery_attempts}/{MAX_RECOVERY_ATTEMPTS}]"
        )
        evt = {
            "cycle": cycle + 1,
            "event": "recovery",
            "level": S._recovery_level,
            "strategy": strategy,
            "reason": reason,
            "attempt": S._recovery_attempts,
            "description": desc,
        }
        S.results.append(evt)
        S.log_file.write(json.dumps(evt, default=str) + "\n")
        S.log_file.flush()
        _apply_reset_trackers(
            S,
            _reset_recovery_trackers(
                reason,
                same_dir=S._same_dir,
                same_dir_count=S._same_dir_count,
                same_screen_count=S._same_screen_count,
                same_tile_count=S._same_tile_count,
                void_cycles=S._void_cycles,
                a_press_count=S._a_press_count,
            ),
        )
        return True  # skip StateWindow, let next cycle re-classify
    _execute_recovery(S, cycle, reason, header)
    return True  # skip StateWindow, let next cycle re-classify


def _sw_rival_battle(S, cycle):
    """Stamp the RIVAL_BATTLE_REACHED milestone with a screenshot."""
    S.ctx.set_location("rival_battle")
    battle_png = SCREENSHOT_DIR / f"BATTLE_{cycle + 1:04d}.png"
    S._img.save(battle_png)
    evt = {
        "cycle": cycle + 1,
        "event": "RIVAL_BATTLE_REACHED",
    }
    S.results.append(evt)
    S.log_file.write(json.dumps(evt, default=str) + "\n")
    S.log_file.flush()
    safe_print(f"  [!] RIVAL BATTLE REACHED at cycle {cycle + 1}")


def _sw_run_window(S, cycle, header, st, state_type, vis_dict, battle_jev_decision, t0):
    """Create and run the StateWindow, then stamp the cycle's entry row."""
    from src.core.state_window import (
        StateWindow,
    )  # deferred: ~592ms import, sys.path[0] ordering not relied on

    win = StateWindow(
        state_type,
        S.ctx,
        S.R.emu,
        vis_dict,
        generation="gen1",
        max_steps=(
            # Battle needs room to act: query → attack → verify
            # within one window. max_steps=1 meant a single
            # query_global consumed the whole budget each cycle
            # and the battle never progressed (T192/T197 stall).
            5
            if state_type == "battle"
            else (1 if state_type == "name_entry" else STATE_STEPS)
        ),
        hint_level=HINT_LEVEL,
        use_ram_prompts=True,
        failed_flee_attempts=S._failed_flee_attempts,
        battle_tool_call=(
            _jev_battle_tool_call(battle_jev_decision, vis_dict)
            if state_type == "battle"
            else None
        ),
    )
    result = win.run()
    if state_type == "battle":
        S._failed_flee_attempts = int(
            result.get("_failed_flee_attempts", S._failed_flee_attempts)
        )
    S.R.emu.fast_forward(FAST_FORWARD_FRAMES)
    elapsed = time.time() - t0

    # --- Battle event logging ---
    battle_events = result.get("_battle_events", [])
    for be in battle_events:
        safe_print(
            f"  [BATTLE] {be.get('event')}: {be.get('screen_type', be.get('outcome', '?'))}"
        )

    # Extract last action
    last_action = "?"
    for h in reversed(win._history):
        tc = h.get("tool_call", {})
        if tc:
            last_action = (
                f"{tc.get('name', '?')}({tc.get('arguments', {})})"
            )
            break

    entry = {
        "cycle": cycle + 1,
        "screen": st,
        "state": state_type,
        "action": last_action,
        "elapsed_s": round(elapsed, 1),
        "cartographer_raw": header["carto_raw"],
        "state_window_raw": "\n\n---\n".join(win._raw_responses)
        if getattr(win, "_raw_responses", None)
        else "",
        "battle_events": battle_events,
        "failed_flee_attempts": S._failed_flee_attempts,
    }
    _stamp_battle_observability(
        entry,
        state_type=state_type,
        history=win._history,
        jev_decision=battle_jev_decision,
    )
    state_outcome = next(
        (
            str(item["action"])
            for item in reversed(win._history)
            if item.get("action") not in (None, "")
        ),
        f"executed {last_action}",
    )
    _record_recent_decision(
        S._recent_decisions,
        entry,
        outcome=state_outcome,
    )
    S.results.append(entry)
    S.log_file.write(json.dumps(entry, default=str) + "\n")
    S.log_file.flush()
    safe_print(
        f"  [{cycle + 1}/{CYCLES}] {st} | {last_action} | {elapsed:.1f}s"
    )


def _cycle_tail(S, cycle, header):
    """Post-branch progression handling: names, location, checkpoint save."""
    st = header["st"]
    patch_data = header["patch_data"]

    # Handle progression
    if S._cycle_dir_lock_warned:
        S._dir_lock_warn_cycles += 1  # GAP-028 per-run lock-rate metric
    if st == "name_confirm" and patch_data.get("name_field"):
        if not S.ctx.player_name:
            S.ctx.player_name = patch_data["name_field"]
        elif not S.ctx.rival_name:
            S.ctx.rival_name = patch_data["name_field"]

    if st == "overworld" and S.ctx.location in ("title", "intro"):
        S.ctx.set_location("bedroom")
        S.ctx.add_goal("leave bedroom")
        S.ctx.add_goal("reach rival battle")

    _cycle_checkpoint_save(S, cycle)


def _cycle_checkpoint_save(S, cycle):
    """Checkpoint save every N cycles (rolling slots)."""
    # ── Checkpoint save every N cycles ────────────────────
    if (cycle + 1) % CHECKPOINT_INTERVAL == 0:
        try:
            S.R.emu.save_state(S._checkpoint_slot)
            evt = {
                "cycle": cycle + 1,
                "event": "state_saved",
                "slot": S._checkpoint_slot,
            }
            S.results.append(evt)
            S.log_file.write(json.dumps(evt, default=str) + "\n")
            S.log_file.flush()
            safe_print(f"  [CKPT] Saved state to slot {S._checkpoint_slot}")
            S._last_saved_slot = S._checkpoint_slot
            S._checkpoint_slot = (S._checkpoint_slot + 1) % CHECKPOINT_SLOTS
        except Exception as exc:
            safe_print(f"  [CKPT] Failed to save state: {exc}")


def _finalize_run(S):
    """Stop the emulator, rewrite the run log, print the summary, persist."""
    S.R.emu.stop()

    # JEV-1 (PRD v3 AC-1): per-run autonomy counters, counted from the
    # per-decision rows only (never incremented by the summary printer).
    autonomy = _autonomy_counters(S.results)
    teacher_summary = teacher_escalation_records(S.results)

    # Write log
    log_file = S.log_file
    log_file.seek(0)
    log_file.truncate()
    log_file.write(json.dumps(S.preflight_row, default=str) + "\n")
    for entry in S.results:
        log_file.write(json.dumps(entry, default=str) + "\n")
    # AC-1's proof row: one JSON line carrying decisions_total / jev_answered
    # / escalated / autonomy_ratio, written with the same idiom as every
    # other row. Kept out of `results` so the legacy "Done. N actions."
    # count and the DuckBrain ladder/cycles stay byte-identical.
    _write_autonomy_row(log_file, S.run_id, autonomy, teacher_summary)
    _write_degradation_row(log_file, S.run_id, autonomy)
    log_file.close()

    # Summary
    screens = set(r.get("screen", "unknown") for r in S.results)
    real_decisions, fallback_decisions = _classify_decision_intents(S.results)
    # PERCEPT-1: per-run vision token/cost rollup, derived from the same
    # per-decision rows the decision trace wrote — no hand-rolled recount.
    vision_usage = _rollup_vision_usage(S.results)
    final_summary = _format_summary(
        S.run_id,
        len(S.results),
        screens,
        S._dir_lock_warn_cycles,
        CYCLES,
        len(S._visited_tiles),
        real_decisions=real_decisions,
        fallback_decisions=fallback_decisions,
        autonomy=autonomy,
        teacher=teacher_summary,
        movement_progress_cycles=S._movement_progress_cycles,
        movement_observed_cycles=S._movement_observed_cycles,
        vision_usage=vision_usage,
    )
    safe_print(f"\n{final_summary}")
    safe_print(f"Log: {log_path}")
    safe_print(f"Screenshots: {SCREENSHOT_DIR}")

    _persist_run_memory(S, final_summary)

    # Persist frame cache for the next run (cross-run dedup)
    if S.R.frame_cache is not None:
        S.R.frame_cache.save()
        safe_print(
            f"[{S.run_id}] Frame cache saved: {S.R.frame_cache.unique_frames} unique "
            f"frames / {S.R.frame_cache.total_seen} total references "
            f"({S.R.frame_cache.stats()['max_entries']} max) — "
            f"{S.R.frame_cache.stats()['cache_size_mb']} MB on disk, "
            f"eviction: {S.R.frame_cache.stats()['eviction_policy']}"
        )


def _persist_run_memory(S, final_summary):
    """Persist machine-written evidence after emulator/log finalization."""
    try:
        _record_run_memory(
            S.run_id,
            S.results,
            ram_reader=S.R.ram_reader,
            extra={
                "n_actions": len(S.results),
                "distinct_tiles": len(S._visited_tiles),
                "movement_progress_cycles": S._movement_progress_cycles,
                "movement_observed_cycles": S._movement_observed_cycles,
                "log_path": str(log_path),
                "summary": final_summary,
            },
        )
    except Exception as exc:
        safe_print(f"[MEM] recorder failed: {exc}")


if __name__ == "__main__":
    with _SGBSuppress():
        main()
