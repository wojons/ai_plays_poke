"""
Vision & Perception Engine for Pokemon AI

Provides comprehensive visual analysis capabilities including:
- Screenshot preprocessing and normalization
- OCR for text recognition
- Sprite recognition for Pokemon and UI elements
- Battle state analysis
- Location detection
"""

from .pipeline import VisionPipeline
from .ocr import OCREngine
from .sprite import SpriteRecognizer
from .battle import BattleAnalyzer
from .location import LocationDetector

__all__ = [
    "VisionPipeline",
    "OCREngine",
    "SpriteRecognizer",
    "BattleAnalyzer",
    "LocationDetector",
]

__version__ = "1.0.0"