#!/usr/bin/env bash
# ────────────────────────────────────────────────────────────────────────────
# ai_plays_poke — Autonomous decision-loop runner for Hermes cron
# ────────────────────────────────────────────────────────────────────────────
#
# Wraps cron_runner.py (the maintained RAM-reader pipeline) for the Hermes cron.
# Writes run logs to cron_logs/run_<id>.jsonl and screenshots to
# screenshots/run_<id>/.
#
# Usage:
#   .coding-hermes/cron.sh                              # uses defaults (ROM, cycles)
#   .coding-hermes/cron.sh --rom path/to.gb             # custom ROM (Gen-1 Red/Blue only)
#   .coding-hermes/cron.sh --cycles 50                  # 50 decision cycles
#   .coding-hermes/cron.sh --run-id tick_1234           # label this run's logs/screenshots
#   .coding-hermes/cron.sh --boot-state path/to.state   # boot from a known-good checkpoint (or 'skip')
#   .coding-hermes/cron.sh --dry-run                    # validate setup, no emulator boot / LLM calls
# ────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPTPATH="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPTPATH/.." && pwd)"

cd "$PROJECT_ROOT"

# ── defaults ───────────────────────────────────────────────────────────────
ROM="${ROM:-data/rom/Pokemon - Blue Version (USA, Europe) (SGB Enhanced).gb}"
CYCLES="${CYCLES:-20}"
RUN_ID="${RUN_ID:-}"
BOOT_STATE="${BOOT_STATE:-}"
DRY_RUN="${DRY_RUN:-}"

# ── parse args ─────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --rom)        ROM="$2";        shift 2 ;;
        --cycles)     CYCLES="$2";     shift 2 ;;
        --run-id)     RUN_ID="$2";     shift 2 ;;
        --boot-state) BOOT_STATE="$2"; shift 2 ;;
        --dry-run)    DRY_RUN=1;       shift ;;
        *)            echo "Unknown arg: $1"; exit 1 ;;
    esac
done

# Reject GBA (Gen-3) ROMs — this pipeline is Gen-1 Red/Blue only; a LeafGreen
# run would read Blue RAM offsets from a GBA game = garbage state. Fire BEFORE
# the ROM-exists check and BEFORE any emulator boot.
if [[ "${ROM,,}" == *.gba ]]; then
    echo "ERROR: unsupported ROM: $ROM — this pipeline is Gen-1 Red/Blue only (SGB Blue ROM required); GBA (LeafGreen etc.) ROMs are not supported" >&2
    exit 1
fi

# ── activate venv ──────────────────────────────────────────────────────────
# Priority: $VENV (explicit override) > venv/ (legacy) > .venv/ (README Quick Start).
if [ -n "${VENV:-}" ]; then
    # Explicit override — $VENV must point at a venv directory
    if [ -f "$VENV/bin/activate" ]; then
        source "$VENV/bin/activate"
    else
        echo "ERROR: \$VENV is set to '$VENV' but no activate script found at $VENV/bin/activate" >&2
        exit 1
    fi
elif [ -f venv/bin/activate ]; then
    source venv/bin/activate
elif [ -f .venv/bin/activate ]; then
    source .venv/bin/activate
else
    echo "ERROR: no Python venv found — checked $PROJECT_ROOT/venv and $PROJECT_ROOT/.venv (README Quick Start creates .venv; or set \$VENV to override)" >&2
    exit 1
fi

# ── verify ROM exists ──────────────────────────────────────────────────────
if [ ! -f "$ROM" ]; then
    echo "ERROR: ROM not found: $ROM" >&2
    exit 1
fi

# ── check API key ──────────────────────────────────────────────────────────
if [ -z "${OPENROUTER_API_KEY:-}" ]; then
    # Try .env file
    if [ -f .env ]; then
        export OPENROUTER_API_KEY="$(grep OPENROUTER_API_KEY .env | cut -d= -f2-)"
    fi
    if [ -z "${OPENROUTER_API_KEY:-}" ]; then
        echo "WARNING: OPENROUTER_API_KEY not set — AI decisions will be stubs" >&2
    fi
fi

echo "=== ai_plays_poke cron tick ==="
echo "  ROM:        $ROM"
echo "  Cycles:     $CYCLES"
echo "  Run ID:     ${RUN_ID:-<auto>}"
echo "  Boot state: ${BOOT_STATE:-data/boot.state (cron_runner default)}"
echo ""

# ── run decision loop (cron_runner.py — maintained entry point, GAP-033) ──
# Replaces the legacy embedded DecisionLoop heredoc. The ROM always passes
# through --rom (the default here is the same file as cron_runner's module
# constant); --run-id/--boot-state pass through only when provided so
# cron_runner's own defaults apply otherwise. --gen/--interval are NOT
# cron_runner flags and were dropped from this script (GAP-033).
_RUN_ARGS=(--rom "$ROM" --cycles "$CYCLES")
if [ -n "$RUN_ID" ]; then
    _RUN_ARGS+=(--run-id "$RUN_ID")
fi
if [ -n "$BOOT_STATE" ]; then
    _RUN_ARGS+=(--boot-state "$BOOT_STATE")
fi
if [ -n "$DRY_RUN" ]; then
    _RUN_ARGS+=(--dry-run)
fi
python "$PROJECT_ROOT/cron_runner.py" "${_RUN_ARGS[@]}"

echo ""
echo "=== Cron tick complete ==="
