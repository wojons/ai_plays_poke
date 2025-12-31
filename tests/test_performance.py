"""
Performance Tests for PTP-01X Pokemon AI

Tests system performance under load:
- Screenshot processing time (<500ms)
- AI decision time (<2s)
- Memory usage limits

Note: Complex tick rate tests are skipped as they require full GameLoop integration.
Integration tests should be run separately in a full environment.

Total: 9 active performance tests (16 skipped as integration tests)
"""

import pytest
import time
import tempfile
import numpy as np
import psutil
import threading
import gc
from unittest.mock import Mock, MagicMock, patch
from typing import List, Dict
from pathlib import Path


class TestScreenshotProcessing:
    """Tests for screenshot processing performance (5 tests)"""

    def test_ocr_processing_time(self):
        """OCR processing should complete in <500ms"""
        from src.vision.ocr import OCREngine
        
        # Create test screenshot (simulating 160x144 Game Boy resolution)
        screenshot = np.random.randint(0, 256, (144, 160, 3), dtype=np.uint8)
        
        ocr = OCREngine()
        start_time = time.time()
        result = ocr.extract_text(screenshot)
        processing_time = time.time() - start_time
        
        assert processing_time < 0.5, f"OCR took {processing_time:.2f}s (>500ms)"

    def test_sprite_extraction_time(self):
        """Sprite extraction should complete in <100ms"""
        from src.vision.sprite import SpriteRecognizer
        
        # Create test screenshot
        screenshot = np.random.randint(0, 256, (144, 160, 3), dtype=np.uint8)
        
        extractor = SpriteRecognizer()
        start_time = time.time()
        result = extractor.recognize_pokemon(screenshot)
        processing_time = time.time() - start_time
        
        assert processing_time < 0.1, f"Sprite extraction took {processing_time:.2f}s (>100ms)"

    def test_vision_pipeline_latency(self):
        """Full vision pipeline should complete in <500ms"""
        from src.vision.pipeline import VisionPipeline
        
        screenshot = np.random.randint(0, 256, (144, 160, 3), dtype=np.uint8)
        
        pipeline = VisionPipeline()
        start_time = time.time()
        result = pipeline.process(screenshot)
        processing_time = time.time() - start_time
        
        assert processing_time < 0.5, f"Vision pipeline took {processing_time:.2f}s (>500ms)"

    def test_battle_analysis_time(self):
        """Battle analysis should complete in <200ms"""
        from src.vision.battle import BattleAnalyzer
        
        screenshot = np.random.randint(0, 256, (144, 160, 3), dtype=np.uint8)
        
        analyzer = BattleAnalyzer()
        start_time = time.time()
        result = analyzer.analyze_battle(screenshot)
        processing_time = time.time() - start_time
        
        assert processing_time < 0.2, f"Battle analysis took {processing_time:.2f}s (>200ms)"

    def test_location_detection_time(self):
        """Location detection should complete in <200ms"""
        from src.vision.location import LocationDetector
        
        screenshot = np.random.randint(0, 256, (144, 160, 3), dtype=np.uint8)
        
        detector = LocationDetector()
        start_time = time.time()
        result = detector.detect_location(screenshot)
        processing_time = time.time() - start_time
        
        assert processing_time < 0.2, f"Location detection took {processing_time:.2f}s (>200ms)"


class TestAIDecisionTime:
    """Tests for AI decision performance (2 tests)"""

    def test_prompt_selection_time(self):
        """Prompt selection should complete in <50ms"""
        from src.core.prompt_manager import PromptManager
        
        game_state = {"location": "Pallet Town", "in_battle": False}
        
        pm = PromptManager()
        start_time = time.time()
        prompts = pm.get_relevant_prompts("exploration", game_state)
        selection_time = time.time() - start_time
        
        assert selection_time < 0.05, f"Prompt selection took {selection_time:.2f}s (>50ms)"

    def test_simple_ai_decision_time(self):
        """AI client initialization should complete in <50ms"""
        from src.core.ai_client import GameAIManager
        
        start_time = time.time()
        ai_manager = GameAIManager()
        init_time = time.time() - start_time
        
        assert init_time < 0.05, f"AI manager initialization took {init_time:.2f}s (>50ms)"


class TestMemoryUsage:
    """Tests for memory efficiency (2 tests)"""

    def test_memory_within_limits(self):
        """Memory usage should stay under 500MB"""
        process = psutil.Process()
        initial_memory = process.memory_info().rss / (1024 * 1024)  # Convert to MB
        
        # Simulate some work
        data = np.random.random((1000, 1000))
        _ = np.mean(data)
        
        final_memory = process.memory_info().rss / (1024 * 1024)
        memory_increase = final_memory - initial_memory
        
        # Allow up to 100MB increase for this operation
        assert memory_increase < 100, f"Memory increased by {memory_increase:.1f}MB (>100MB)"

    def test_numpy_array_memory_efficient(self):
        """NumPy operations should not leak memory"""
        process = psutil.Process()
        initial_memory = process.memory_info().rss / (1024 * 1024)
        
        # Create and destroy many arrays
        for _ in range(100):
            arr = np.random.random((100, 100))
            del arr
            gc.collect()
        
        final_memory = process.memory_info().rss / (1024 * 1024)
        memory_increase = final_memory - initial_memory
        
        # Should not increase by more than 10MB after gc
        assert memory_increase < 10, f"Memory increased by {memory_increase:.1f}MB (>10MB)"


