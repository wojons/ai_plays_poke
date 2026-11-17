#!/usr/bin/env bash
# MCP stdio wrapper for the ai-plays-poke game bridge.
#
# Keeps the session-scoping in ONE place: this wrapper is what the MCP entry
# points at, and it resolves the per-session token file. With no token file the
# tools fail closed with a clear message rather than silently doing nothing.
set -euo pipefail

export AIPP_BRIDGE_TOKEN_FILE="${AIPP_BRIDGE_TOKEN_FILE:-$HOME/.hermes/aipp_bridge/session.token}"
export AIPP_BRIDGE_PORT="${AIPP_BRIDGE_PORT:-8770}"
export PYTHONUNBUFFERED=1

# Resolve the checkout from this wrapper's own location (never a fixed home path):
# the same wrapper has to work from the main clone, a worktree, or any clone.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Interpreter: AIPP_PYTHON wins; else the checkout's own venv, whichever it carries
# (the py3.11 `venv/` is the complete env, `.venv/` the held py3.13 one).
PY="${AIPP_PYTHON:-}"
if [ -z "$PY" ]; then
  for cand in "$REPO_ROOT/venv/bin/python" "$REPO_ROOT/.venv/bin/python"; do
    if [ -x "$cand" ]; then
      PY="$cand"
      break
    fi
  done
fi
if [ -z "$PY" ]; then
  echo "aipp-mcp-wrapper: no interpreter found (set AIPP_PYTHON)" >&2
  exit 2
fi

exec "$PY" "$REPO_ROOT/scripts/aipp_mcp.py"
