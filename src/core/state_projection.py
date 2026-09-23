"""Bounded state projection: RAM observation -> Jev-readable state text.

Why this exists: Jev self-reports `sufficient_state` and names a `missing_class`
when the state it is handed cannot support a decision. The first live run showed
it flagging `map_topology` even on a trivial overworld walk, which means the
fast model was being asked to decide from a projection too thin to decide from.

Rules for this projection:
  * BOUNDED. Jev is paid per input token ($0.042/Mtok) and a decision must stay
    under ~100ms of budget; cap every variable-length section.
  * FACTUAL. Only what RAM actually reports. No hints, no suggested actions, no
    story text. The projection must never do the deciding.
  * DETERMINISTIC. Same RAM -> same text, so a repeat means a real repeat and the
    failure-triggered escalation can trust it.

Deliberately NOT included: the legacy `_MAP_HINTS` / `suggested_action` strings.
Those are per-map hardcoded directions; feeding them to Jev would smuggle the
old assist layer back in through the state instead of through the code.
"""

from __future__ import annotations

from typing import Any, Iterable

MAX_MINIMAP_CHARS = 900
MAX_EVENTS = 8
MAX_VISITED = 12
MAX_MECHANICS_CHARS = 1200


def _cap(text: str, limit: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _adjacent_line(adj: dict[str, Any]) -> str:
    if not adj:
        return "  (no adjacency data)"
    order = ["up", "down", "left", "right"]
    parts = []
    for d in order:
        if d in adj:
            parts.append(f"{d.upper()}={adj[d]}")
    for d, v in adj.items():
        if d not in order:
            parts.append(f"{d.upper()}={v}")
    return "  " + " ".join(parts)


def _visited_line(
    visited: Iterable[tuple[int, int]] | dict[Any, int] | None, current: tuple[int, int]
) -> str:
    """Render the visited set with repeat counts — repeats are the stuck signal."""
    if not visited:
        return "  (none recorded yet)"
    if isinstance(visited, dict):
        items = sorted(visited.items(), key=lambda kv: -kv[1])
    else:
        counts: dict[tuple[int, int], int] = {}
        for t in visited:
            counts[t] = counts.get(t, 0) + 1
        items = sorted(counts.items(), key=lambda kv: -kv[1])
    shown = []
    for tile, n in items[:MAX_VISITED]:
        mark = "*" if tuple(tile) == tuple(current) else ""
        shown.append(f"{tuple(tile)}{mark}x{n}")
    extra = len(items) - len(shown)
    line = "  " + " ".join(shown)
    if extra > 0:
        line += f"  (+{extra} more)"
    return line


def _recent_lines(events: Iterable[Any] | None) -> list[str]:
    """Render recent events, newest last. Events are the reasoning LLM's raw
    material on escalation, so keep them factual and short."""
    if not events:
        return ["  (none)"]
    evs = list(events)[-MAX_EVENTS:]
    out = []
    for e in evs:
        if isinstance(e, dict):
            bits = []
            for k in (
                "cycle",
                "event",
                "strategy",
                "reason",
                "action",
                "map_name",
                "detail",
                "result",
            ):
                if e.get(k) is not None:
                    bits.append(f"{k}={_cap(str(e[k]), 60)}")
            out.append("  " + (" ".join(bits) if bits else _cap(str(e), 120)))
        else:
            out.append("  " + _cap(str(e), 120))
    return out


def build(
    obs: dict[str, Any],
    *,
    goal: str = "",
    visited: Iterable[tuple[int, int]] | dict[Any, int] | None = None,
    recent_events: Iterable[Any] | None = None,
    last_action: str = "",
    last_action_changed_state: bool | None = None,
    mechanics: Iterable[str] | None = None,
    extra_facts: Iterable[str] | None = None,
) -> str:
    """Render a RAM observation into a bounded, factual state text for Jev.

    The caller owns `goal`, `visited`, `recent_events` and `mechanics` because
    they are cross-cycle/session state, not readable from a single RAM snapshot.
    """
    st = obs.get("result", "unknown")
    mid = obs.get("map_id")
    mname = obs.get("map_name") or "unknown"
    ptx, pty = obs.get("player_tile_x"), obs.get("player_tile_y")
    facing = obs.get("player_facing") or "?"
    party = obs.get("party_count")
    species = obs.get("first_party_species")

    lines: list[str] = []
    lines.append("GAME: Pokemon Blue (Gen 1)")
    dims = obs.get("map_dimensions")
    tileset = obs.get("map_tileset")
    head = f"MAP: {mname}"
    if mid is not None:
        head += f" (id {mid})"
    if dims:
        head += f" [{dims}"
        head += f", tileset {tileset}]" if tileset else "]"
    lines.append(head)
    lines.append(f"PLAYER TILE: ({ptx},{pty})  facing {facing}")
    if party:
        s = f"PARTY: {party} Pokemon"
        if species:
            s += f" ({species})"
        lines.append(s)
    else:
        lines.append("PARTY: empty (no Pokemon yet)")
    lines.append(f"SCREEN: {st}")

    # ── topology: this is the section Jev said was missing ──────────────────
    lines.append("TOPOLOGY (what is adjacent to the player right now):")
    lines.append(_adjacent_line(obs.get("adjacent") or {}))

    grid = obs.get("minimap") or obs.get("overworld_grid") or ""
    if grid:
        lines.append("LOCAL MAP (O=player, . floor, # blocked):")
        for ln in _cap(grid, MAX_MINIMAP_CHARS).splitlines():
            lines.append("  " + ln)

    exits = obs.get("visible_exits") or []
    lines.append(f"VISIBLE EXITS: {', '.join(exits) if exits else '(none adjacent)'}")

    # ── conversation / menu / battle content, only when on that screen ─────
    if st in ("dialog", "menu", "battle", "name_entry"):
        render = obs.get("render") or ""
        if render:
            lines.append("SCREEN CONTENT:")
            for ln in _cap(render, 700).splitlines():
                lines.append("  " + ln)
        ms = obs.get("menu_state") or {}
        if ms.get("num_items"):
            lines.append(
                f"MENU: {ms.get('num_items')} items, "
                f"cursor {ms.get('current_item')}, kind {ms.get('menu_kind')}"
            )

    # ── cross-cycle state (caller-supplied, factual) ───────────────────────
    lines.append("TILES VISITED THIS RUN (tile xCount, * = now):")
    lines.append(_visited_line(visited, (ptx or 0, pty or 0)))

    lines.append("RECENT EVENTS (oldest first):")
    lines.extend(_recent_lines(recent_events))

    if last_action:
        chg = (
            "changed nothing (blocked or rejected)"
            if last_action_changed_state is False
            else "produced a state change"
            if last_action_changed_state
            else "unknown"
        )
        lines.append(f"LAST ACTION: {last_action} — {chg}")

    if goal:
        lines.append(f"GOAL: {goal}")

    if mechanics:
        lines.append("MECHANICS (game rules, no story):")
        for m in mechanics:
            lines.append("  - " + _cap(str(m), 240))

    if extra_facts:
        lines.append("SUPPLIED FACTS:")
        for f in extra_facts:
            lines.append("  - " + _cap(str(f), 240))

    proj = "\n".join(lines)
    # hard ceiling so a pathological map cannot blow the per-decision budget
    return _cap(proj, 6000)


# ── mechanics knowledge (game rules only, never story) ──────────────────────

DEFAULT_MECHANICS: tuple[str, ...] = (
    "Interacting with an object or NPC requires standing next to it and facing it, "
    "then pressing A. You cannot interact diagonally.",
    "A text box advances one page per A press. A prompt with YES/NO is answered "
    "with A (yes) or B (no). Pressing B also cancels most menus.",
    "Objects on top of tables/desks are usually reachable by standing directly "
    "below them and pressing A, not by walking onto the table.",
    "If several consecutive actions produce no state change, the player is blocked "
    "in that direction; a different direction or an A press is required.",
)
