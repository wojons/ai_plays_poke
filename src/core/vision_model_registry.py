"""Ordered vision model configuration with legacy environment compatibility."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class VisionModel:
    provider: str
    model: str

    @property
    def model_id(self) -> str:
        return self.model


def parse_vision_models(raw: str) -> list[VisionModel]:
    """Parse an ordered JSON list of {provider, model} entries."""
    try:
        value: Any = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("AIPP_VISION_MODELS must be a JSON array") from exc
    if not isinstance(value, list) or not value:
        raise ValueError("AIPP_VISION_MODELS must be a non-empty JSON array")
    models: list[VisionModel] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ValueError(f"vision model entry {index} must be an object")
        provider, model = item.get("provider"), item.get("model")
        if not isinstance(provider, str) or not provider.strip():
            raise ValueError(f"vision model entry {index} needs a provider")
        if not isinstance(model, str) or not model.strip():
            raise ValueError(f"vision model entry {index} needs a model")
        models.append(VisionModel(provider.strip(), model.strip()))
    return models


def configured_vision_models(
    environ: dict[str, str] | None = None,
) -> list[VisionModel]:
    """Load ordered model pairs, falling back to the legacy single-model env."""
    env = os.environ if environ is None else environ
    configured = env.get("AIPP_VISION_MODELS", "").strip()
    if configured:
        return parse_vision_models(configured)
    legacy = env.get("AIPP_VISION_MODEL", "").strip()
    if legacy:
        return [VisionModel("openrouter", legacy)]
    return [VisionModel("openrouter", "openai/gpt-5.6-luna")]
