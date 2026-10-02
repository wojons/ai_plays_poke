"""
Vision & Perception Engine for Pokemon AI

Provides comprehensive visual analysis capabilities including:
- Screenshot preprocessing and normalization
- OCR for text recognition
- Sprite recognition for Pokemon and UI elements
- Battle state analysis
- Location detection
"""

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
