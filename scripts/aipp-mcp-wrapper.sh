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

exec /home/kara/ai_plays_poke/.venv/bin/python \
  /home/kara/ai_plays_poke/scripts/aipp_mcp.py
