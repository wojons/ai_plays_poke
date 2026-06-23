"""
Stacked Prompt Config System for AI Plays Pokémon.

Loads YAML prompt configs organized by generation and screen type,
then assembles them into a full prompt string with injected game state.
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


GAME_NAMES: Dict[str, str] = {
    "gen1": "Pokémon Red/Blue/Yellow",
    "gen3": "Pokémon FireRed/LeafGreen",
}

GEN_LABELS: Dict[str, str] = {
    "gen1": "Generation 1 (Game Boy)",
    "gen3": "Generation 3 (Game Boy Advance)",
}

LAYER_ORDER = ("system", "tools", "observation", "memory", "examples")


class SafeDict(dict):
    """Dict subclass that returns the missing key placeholder instead of raising KeyError."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _join_list(value: Any, sep: str = "\n  ") -> str:
    """Join a list into a string, returning empty string for non-list/empty values."""
    if value is None:
        return ""
    if isinstance(value, list):
        return sep.join(str(item) for item in value)
    if isinstance(value, str):
        return value
    return str(value)


def _build_hp_info(vision: Dict[str, Any]) -> str:
    """Build HP info string from raw vision data fields."""
    player_pct = vision.get("player_hp_pct")
    enemy_pct = vision.get("enemy_hp_pct")
    parts: List[str] = []
    if player_pct is not None:
        parts.append(f"Your HP: {player_pct}%")
    if enemy_pct is not None:
        parts.append(f"Enemy HP: {enemy_pct}%")
    if not parts:
        # Try composite key as fallback
        hp_info = vision.get("hp_info")
        if hp_info:
            return str(hp_info)
    return " | ".join(parts) if parts else ""


def _build_enemy_info(vision: Dict[str, Any]) -> str:
    """Build enemy info string from raw vision data fields."""
    enemy = vision.get("enemy_pokemon")
    if enemy:
        return f"Enemy: {enemy}"
    enemy_info = vision.get("enemy_info")
    if enemy_info:
        return str(enemy_info)
    return ""


class PromptStack:
    """
    Loads and assembles stacked prompt configs from YAML files.

    Config layout::

        configs/prompts/
            gen1/
                battle.yaml
                overworld.yaml
                menu.yaml
                dialog.yaml
            gen3/
                battle.yaml
                overworld.yaml
                menu.yaml
                dialog.yaml

    Each YAML file contains five layers: system, tools, observation, memory, examples.
    The assemble() method formats these layers with live vision and memory data.
    """

    def __init__(self, configs_dir: str = "configs/prompts"):
        self._configs_dir = Path(configs_dir)
        self._cache: Dict[str, Dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_stack(self, generation: str, screen_type: str) -> Dict[str, str]:
        """
        Return the 5-layer prompt config for a generation + screen combo.

        Returns a dict with keys: system, tools, observation, memory, examples.
        Each value is the raw template string (unformatted).
        """
        key = f"{generation}/{screen_type}"
        if key not in self._cache:
            path = self._configs_dir / generation / f"{screen_type}.yaml"
            if not path.exists():
                raise FileNotFoundError(
                    f"Prompt config not found: {path}\n"
                    f"Available configs dir: {self._configs_dir.resolve()}"
                )
            with open(path, "r", encoding="utf-8") as fh:
                self._cache[key] = yaml.safe_load(fh)
        return dict(self._cache[key])

    def assemble(
        self,
        generation: str,
        screen_type: str,
        vision_output: Dict[str, Any],
        memory_context: Dict[str, Any],
    ) -> str:
        """
        Assemble a full prompt string by layering system → tools →
        observation → memory → examples, with live data injected.

        Args:
            generation: e.g. 'gen1', 'gen3'
            screen_type: e.g. 'battle', 'overworld', 'menu', 'dialog'
            vision_output: Raw vision data dict (screen_type, enemy_pokemon,
                           player_hp_pct, enemy_hp_pct, text_lines, menu_items, …)
            memory_context: Memory data dict (recent_actions, party_status, active_goal)

        Returns:
            Fully formatted prompt string with all layers concatenated.
        """
        stack = self.load_stack(generation, screen_type)

        # Build the formatting context
        fmt: Dict[str, Any] = SafeDict()

        # --- Generation / game metadata ---
        fmt["generation"] = GEN_LABELS.get(generation, generation)
        fmt["game_name"] = GAME_NAMES.get(generation, f"Pokémon ({generation})")

        # --- Vision data ---
        fmt["screen_type"] = vision_output.get("screen_type", screen_type)

        # Composite fields built from raw vision keys
        fmt["enemy_info"] = _build_enemy_info(vision_output)
        fmt["hp_info"] = _build_hp_info(vision_output)

        # List fields — join for display
        fmt["text_lines"] = _join_list(vision_output.get("text_lines"), sep="\n  ")
        fmt["menu_items"] = _join_list(
            vision_output.get("menu_items", vision_output.get("menu_options")), sep=", "
        )

        # --- Memory context ---
        fmt["recent_actions"] = _join_list(memory_context.get("recent_actions"), sep="\n  ")
        fmt["party_status"] = memory_context.get("party_status", "")
        fmt["active_goal"] = memory_context.get("active_goal", "")

        # --- Assemble layers ---
        parts: List[str] = []
        for layer in LAYER_ORDER:
            template = stack.get(layer, "")
            if template:
                formatted = self._format_layer(template, fmt)
                if formatted:
                    parts.append(formatted)

        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _format_layer(template: Any, fmt: Dict[str, Any]) -> str:
        """Format a single layer, handling both strings and example lists."""
        if isinstance(template, str):
            return template.format_map(fmt)
        if isinstance(template, list):
            # Examples layer: list of {"input": ..., "output": ...} dicts
            # These are static references — do NOT format_map them since
            # their JSON outputs contain literal curly braces.
            lines: List[str] = ["Examples of correct responses:"]
            for i, example in enumerate(template, 1):
                inp = example.get("input", "")
                out = example.get("output", "")
                lines.append(f"\nExample {i}:")
                lines.append(f"  Input: {inp}")
                lines.append(f"  Output: {out}")
            return "\n".join(lines)
        return str(template)

    # ------------------------------------------------------------------
    # Introspection helpers
    # ------------------------------------------------------------------

    def available_stacks(self) -> List[str]:
        """Return list of available generation/screen_type keys."""
        stacks: List[str] = []
        if self._configs_dir.exists():
            for gen_dir in sorted(self._configs_dir.iterdir()):
                if gen_dir.is_dir():
                    for yaml_file in sorted(gen_dir.glob("*.yaml")):
                        stacks.append(f"{gen_dir.name}/{yaml_file.stem}")
        return stacks
