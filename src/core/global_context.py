"""
Global Context Manager for AI Plays Pokémon.

Maintains the compacted global game state that persists across state
window transitions. Tracks: player/rival names, location, party status,
active goals, key events, and battle history.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class GlobalContext:
    """Compacted global state passed to every state window.

    Designed to be compact (~500 tokens max) — state windows get
    this plus their own focused workflow.
    """

    # ── Identity ──────────────────────────────────────────────────────
    player_name: str = ""
    rival_name: str = ""

    # ── Location ─────────────────────────────────────────────────────
    location: str = "bedroom"  # bedroom, house_downstairs, pallet_town, route_1, ...
    generation: str = "gen1"

    # ── Party ────────────────────────────────────────────────────────
    party: list[dict[str, Any]] = field(default_factory=list)
    # [{"name": "SQUIRTLE", "hp_pct": 100, "level": 5, "status": null}, ...]

    # ── Goals ─────────────────────────────────────────────────────────
    goals: list[str] = field(default_factory=list)
    # ["reach rival battle", "get starter pokemon", ...]
    active_goal: str = ""

    # ── Progression ───────────────────────────────────────────────────
    badges: list[str] = field(default_factory=list)
    key_items: list[str] = field(default_factory=list)
    story_flags: set[str] = field(default_factory=set)
    # {"got_starter", "beat_rival_1", "delivered_parcel", ...}

    # ── Recent events ─────────────────────────────────────────────────
    recent_actions: list[str] = field(default_factory=list)
    # ["walked left 3x", "pressed A on stairs", "entered downstairs"]

    # ── Meta ──────────────────────────────────────────────────────────
    run_id: str = field(default_factory=lambda: datetime.now().strftime("%Y%m%d_%H%M%S"))
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    # ── DuckBrain integration target ──────────────────────────────────
    duckbrain_namespace: str = ""  # set at init

    # ──────────────────────────────────────────────────────────────────
    # Compact representation
    # ──────────────────────────────────────────────────────────────────

    def compact(self) -> str:
        """Return a ~500-token summary string for injection into state windows."""
        lines: list[str] = []

        lines.append(f"GAME: Pokémon {self.generation.upper()} — {self.location}")
        if self.player_name:
            lines.append(f"PLAYER: {self.player_name}")
        if self.rival_name:
            lines.append(f"RIVAL: {self.rival_name}")

        # Party
        if self.party:
            party_strs = []
            for p in self.party:
                hp = p.get("hp_pct", "?")
                lvl = p.get("level", "?")
                name = p.get("name", "?")
                status = p.get("status", "")
                s = f"{name} Lv{lvl} HP:{hp}%"
                if status:
                    s += f" [{status}]"
                party_strs.append(s)
            lines.append(f"PARTY: {' | '.join(party_strs)}")
        else:
            lines.append("PARTY: none")

        # Goals
        if self.goals:
            lines.append(f"GOALS: {', '.join(self.goals)}")
        if self.active_goal:
            lines.append(f"ACTIVE: {self.active_goal}")

        # Story progress
        if self.story_flags:
            lines.append(f"PROGRESS: {', '.join(sorted(self.story_flags))}")

        # Recent actions (last 5)
        if self.recent_actions:
            recent = self.recent_actions[-5:]
            lines.append(f"RECENT: {' → '.join(recent)}")

        # Key items
        if self.key_items:
            lines.append(f"ITEMS: {', '.join(self.key_items)}")

        return "\n".join(lines)

    # ──────────────────────────────────────────────────────────────────
    # Mutations
    # ──────────────────────────────────────────────────────────────────

    def record_action(self, action: str) -> None:
        """Append an action to recent history."""
        self.recent_actions.append(action)
        if len(self.recent_actions) > 20:
            self.recent_actions = self.recent_actions[-20:]

    def add_goal(self, goal: str) -> None:
        """Add a goal if not already present."""
        if goal not in self.goals:
            self.goals.append(goal)
        if not self.active_goal:
            self.active_goal = goal

    def complete_goal(self, goal: str) -> None:
        """Mark a goal as completed."""
        if goal in self.goals:
            self.goals.remove(goal)
        if self.active_goal == goal:
            self.active_goal = self.goals[0] if self.goals else ""

    def set_flag(self, flag: str) -> None:
        """Record a story progression flag."""
        self.story_flags.add(flag)

    def update_party(self, party: list[dict[str, Any]]) -> None:
        """Replace party state."""
        self.party = party

    def set_location(self, location: str) -> None:
        """Update current location."""
        self.location = location
