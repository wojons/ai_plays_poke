"""Ensure package initializers exist so act-leg mypy runs don't red on missing ``src``/``src.vision`` packages.

This is a CI/container-side guard only. It never edits tracked source files when the
initializers are already present, and it does not weaken product imports.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_INIT = REPO_ROOT / "src" / "__init__.py"
VISION_INIT = REPO_ROOT / "src" / "vision" / "__init__.py"

_SRC_INIT_CONTENT = """\
# AI Plays Pokemon - Source Package

\"\"\"
Orchestrated Intelligence Framework for Pokemon

This package contains:
- core/: Emulator interface, vision processing, memory management
- cognition/: Observer, Strategist, Tactician, Reflection Engine
- models/: Thinking and Acting model interfaces
- analytics/: Decision logging and metrics aggregation
- ui/: Dashboard and visualization
\"\"\"

__version__ = "1.0.0"
"""

_VISION_INIT_CONTENT = """\
\"\"\"
Vision & Perception Engine for Pokemon AI

Provides comprehensive visual analysis capabilities including:
- Screenshot preprocessing and normalization
- OCR for text recognition
- Sprite recognition for Pokemon and UI elements
- Battle state analysis
- Location detection
\"\"\"

from src import __version__ as __version__

from .battle import BattleAnalyzer
from .location import LocationDetector
from .ocr import OCREngine
from .pipeline import VisionPipeline
from .sprite import SpriteRecognizer

__all__ = [
    "VisionPipeline",
    "OCREngine",
    "SpriteRecognizer",
    "BattleAnalyzer",
    "LocationDetector",
]
"""


def _write_if_missing(path: Path, content: str) -> bool:
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def main() -> int:
    created: list[Path] = []
    for path, content in (
        (SRC_INIT, _SRC_INIT_CONTENT),
        (VISION_INIT, _VISION_INIT_CONTENT),
    ):
        if _write_if_missing(path, content):
            created.append(path)

    if created:
        print(
            f"Created missing package initializers: {', '.join(str(p) for p in created)}"
        )
        return 0
    print("Package initializers present.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
