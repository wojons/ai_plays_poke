#!/usr/bin/env bash
# ────────────────────────────────────────────────────────────────────────────
# ai_plays_poke — Autonomous decision-loop runner for Hermes cron
# ────────────────────────────────────────────────────────────────────────────
#
# Runs the DecisionLoop for N cycles, then commit-tags checkpoint screenshots
# so progress is visible between cron ticks.
#
# Usage:
#   .coding-hermes/cron.sh                    # uses defaults (ROM, cycles)
#   .coding-hermes/cron.sh --rom path/to.gba  # custom ROM
#   .coding-hermes/cron.sh --cycles 50        # 50 decision cycles
# ────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPTPATH="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPTPATH/.." && pwd)"

cd "$PROJECT_ROOT"

# ── defaults ───────────────────────────────────────────────────────────────
ROM="${ROM:-data/rom/PokemonLeafGreenVersion.gba}"
CYCLES="${CYCLES:-20}"
SCREENSHOT_INTERVAL="${SCREENSHOT_INTERVAL:-60}"
GENERATION="${GENERATION:-gen3}"

# ── parse args ─────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --rom)      ROM="$2";      shift 2 ;;
        --cycles)   CYCLES="$2";   shift 2 ;;
        --gen)      GENERATION="$2"; shift 2 ;;
        --interval) SCREENSHOT_INTERVAL="$2"; shift 2 ;;
        *)          echo "Unknown arg: $1"; exit 1 ;;
    esac
done

# ── activate venv ──────────────────────────────────────────────────────────
if [ -f venv/bin/activate ]; then
    source venv/bin/activate
else
    echo "ERROR: venv not found at $PROJECT_ROOT/venv" >&2
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
echo "  ROM:      $ROM"
echo "  Cycles:   $CYCLES"
echo "  Interval: $SCREENSHOT_INTERVAL"
echo "  Gen:      $GENERATION"
echo ""

# ── run decision loop ──────────────────────────────────────────────────────
python3 << PYEOF
import sys
sys.path.insert(0, "$PROJECT_ROOT")

from src.core.emulator import Emulator
from src.core.decision import DecisionLoop

emu = Emulator("$ROM")
print(f"[+] Emulator loaded: {emu.platform} ROM at {emu.rom_path}")

# --- skip intro ---
print("[+] Skipping intro sequence...")
emu.skip_intro()
print("[+] Intro skipped")

loop = DecisionLoop(
    emu,
    generation="$GENERATION",
    thinking_model="openrouter/owl-alpha",
    vision_model="google/gemma-3-12b-it",
)

results = loop.run(max_steps=$CYCLES, screenshot_interval=$SCREENSHOT_INTERVAL)

# summary
successes = sum(1 for r in results if r.get("success"))
print(f"\n=== Results: {successes}/{len(results)} steps successful ===")
for i, r in enumerate(results):
    status = "✓" if r.get("success") else "✗"
    print(f"  {status} step {i:03d}: {r.get('screen_type', '?'):12s} → {r.get('action', '?')}")

emu.stop()
PYEOF

echo ""
echo "=== Cron tick complete ==="
