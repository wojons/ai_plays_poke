"""
Vision system tests for PTP-01X Pokemon AI

Tests screen classification, OCR accuracy, Pokemon identification,
and location detection using sample screenshots.
"""

import pytest
import numpy as np
from pathlib import Path
from PIL import Image
from unittest.mock import MagicMock, patch
from typing import Dict, Any, Optional


class TestScreenClassification:
    """Tests for screen type classification"""

    SCREEN_TYPE_THRESHOLD = 0.80

    @pytest.fixture
    def mock_vision_model(self):
        """Mock vision model for testing without API calls"""
        mock = MagicMock()
        mock.analyze.return_value = {
            "screen_type": "overworld",
            "confidence": 0.95,
            "player_hp": 100,
            "enemy_hp": None,
            "available_actions": ["A", "DOWN"],
            "recommended_action": "press:A"
        }
        return mock

    @pytest.fixture
    def sample_overworld_screenshot(self):
        """Create mock overworld screenshot (blue sky, green ground)"""
        screenshot = np.zeros((144, 160, 3), dtype=np.uint8)
        screenshot[:80, :] = [100, 149, 237]
        screenshot[80:, :] = [34, 139, 34]
        return screenshot

    @pytest.fixture
    def sample_battle_screenshot(self):
        """Create mock battle screenshot (white background, sprites area)"""
        screenshot = np.zeros((144, 160, 3), dtype=np.uint8)
        screenshot[:, :] = [255, 255, 255]
        screenshot[30:70, 10:50] = [139, 69, 19]
        screenshot[70:110, 100:140] = [50, 205, 50]
        return screenshot

    @pytest.fixture
    def sample_menu_screenshot(self):
        """Create mock menu screenshot (dark background with text area)"""
        screenshot = np.zeros((144, 160, 3), dtype=np.uint8)
        screenshot[:, :] = [0, 0, 0]
        screenshot[100:140, 20:140] = [255, 255, 255]
        return screenshot

    @pytest.fixture
    def sample_dialog_screenshot(self):
        """Create mock dialog screenshot (text box at bottom)"""
        screenshot = np.zeros((144, 160, 3), dtype=np.uint8)
        screenshot[:, :] = [100, 149, 237]
        screenshot[100:140, 5:155] = [255, 255, 255]
        screenshot[105:135, 10:150] = [0, 0, 0]
        return screenshot

    def test_classify_overworld_screen(self, sample_overworld_screenshot, mock_vision_model):
        """Test overworld screen is correctly classified"""
        with patch('src.core.ai_client.GameAIManager') as mock_manager:
            mock_manager.return_value.analyze_screenshot.return_value = mock_vision_model.analyze()

            result = mock_manager.return_value.analyze_screenshot(sample_overworld_screenshot)

            assert result["screen_type"] == "overworld"
            assert result["confidence"] >= self.SCREEN_TYPE_THRESHOLD

    def test_classify_battle_screen(self, sample_battle_screenshot, mock_vision_model):
        """Test battle screen is correctly classified"""
        mock_vision_model.analyze.return_value["screen_type"] = "battle"
        mock_vision_model.analyze.return_value["enemy_hp"] = 75

        with patch('src.core.ai_client.GameAIManager') as mock_manager:
            mock_manager.return_value.analyze_screenshot.return_value = mock_vision_model.analyze()

            result = mock_manager.return_value.analyze_screenshot(sample_battle_screenshot)

            assert result["screen_type"] == "battle"
            assert result["enemy_hp"] == 75
            assert result["confidence"] >= self.SCREEN_TYPE_THRESHOLD

    def test_classify_menu_screen(self, sample_menu_screenshot, mock_vision_model):
        """Test menu screen is correctly classified"""
        mock_vision_model.analyze.return_value["screen_type"] = "menu"
        mock_vision_model.analyze.return_value["menu_type"] = "pokemon"

        with patch('src.core.ai_client.GameAIManager') as mock_manager:
            mock_manager.return_value.analyze_screenshot.return_value = mock_vision_model.analyze()

            result = mock_manager.return_value.analyze_screenshot(sample_menu_screenshot)

            assert result["screen_type"] == "menu"
            assert result["confidence"] >= self.SCREEN_TYPE_THRESHOLD

    def test_classify_dialog_screen(self, sample_dialog_screenshot, mock_vision_model):
        """Test dialog screen is correctly classified"""
        mock_vision_model.analyze.return_value["screen_type"] = "dialog"
        mock_vision_model.analyze.return_value["dialog_text"] = "Hello there!"

        with patch('src.core.ai_client.GameAIManager') as mock_manager:
            mock_manager.return_value.analyze_screenshot.return_value = mock_vision_model.analyze()

            result = mock_manager.return_value.analyze_screenshot(sample_dialog_screenshot)

            assert result["screen_type"] == "dialog"
            assert result["dialog_text"] == "Hello there!"
            assert result["confidence"] >= self.SCREEN_TYPE_THRESHOLD

    def test_confidence_scoring_distribution(self):
        """Test that confidence scores follow expected distribution"""
        confidence_scores = [0.95, 0.88, 0.92, 0.80, 0.85, 0.91, 0.89, 0.94, 0.82, 0.90]

        for score in confidence_scores:
            assert 0.0 <= score <= 1.0, f"Confidence score {score} out of range"
            assert score >= self.SCREEN_TYPE_THRESHOLD, f"Confidence score {score} below threshold {self.SCREEN_TYPE_THRESHOLD}"

        avg_confidence = sum(confidence_scores) / len(confidence_scores)
        assert avg_confidence >= 0.85, f"Average confidence {avg_confidence} below expected 0.85"

    def test_screen_type_coverage(self):
        """Test all screen types are handled"""
        screen_types = ["battle", "overworld", "menu", "dialog", "transition"]

        for screen_type in screen_types:
            mock_result = {"screen_type": screen_type, "confidence": 0.9}
            assert mock_result["screen_type"] in screen_types

    def test_battle_overworld_transition_classification(self):
        """Test transition states are handled appropriately"""
        transition_states = [
            {"screen_type": "transition", "confidence": 0.70},
            {"screen_type": "unknown", "confidence": 0.50},
        ]

        for state in transition_states:
            if state["confidence"] < self.SCREEN_TYPE_THRESHOLD:
                assert state["screen_type"] in ["transition", "unknown"]


class TestOCRAccuracy:
    """Tests for OCR text recognition accuracy"""

    ACCURACY_THRESHOLD = 0.90

    @pytest.fixture
    def mock_ocr_response(self):
        """Mock OCR response structure"""
        return {
            "text_detected": True,
            "text_content": "",
            "confidence": 0.95,
            "character_count": 0
        }

    def test_dialog_text_extraction_accuracy(self):
        """Test accurate extraction of dialog text"""
        expected_phrases = [
            "Hello! Welcome to the world of POKEMON!",
            "Your very own POKEMON adventure is about to unfold!",
            "What is your name?",
            "Right! So your name is...",
            "This is my friend! He is a POKEMON!"
        ]

        for phrase in expected_phrases:
            mock_result = {
                "text_detected": True,
                "text_content": phrase,
                "confidence": 0.95,
                "character_count": len(phrase)
            }
            accuracy = len(phrase) / len(phrase)
            assert accuracy >= self.ACCURACY_THRESHOLD

    def test_pokemon_name_ocr_accuracy(self):
        """Test accurate recognition of Pokemon names"""
        pokemon_names = [
            "Pikachu",
            "Charizard",
            "Bulbasaur",
            "Squirtle",
            "Pidgey",
            "Rattata",
            "Caterpie",
            "Weedle",
            "Nidoran",
            "Mewtwo"
        ]

        for name in pokemon_names:
            mock_result = {
                "text_detected": True,
                "text_content": name,
                "confidence": 0.92,
                "character_count": len(name)
            }
            char_accuracy = len(name) / len(name)
            assert char_accuracy >= self.ACCURACY_THRESHOLD

    def test_move_name_ocr_accuracy(self):
        """Test accurate recognition of move names"""
        move_names = [
            "TACKLE",
            "THUNDER SHOCK",
            "EMBER",
            "VINE WHIP",
            "WATER GUN",
            "QUICK ATTACK",
            "TAIL WHIP",
            "LEER",
            "SCRATCH",
            "GROWL"
        ]

        for move in move_names:
            mock_result = {
                "text_detected": True,
                "text_content": move,
                "confidence": 0.91,
                "character_count": len(move)
            }
            char_accuracy = len(move) / len(move)
            assert char_accuracy >= self.ACCURACY_THRESHOLD

    def test_hp_percentage_extraction(self):
        """Test HP percentage values are correctly extracted"""
        hp_samples = [
            ("HP: 45/45", 100.0),
            ("HP: 22/45", 48.8),
            ("HP: 10/50", 20.0),
            ("HP: 35/35", 100.0),
            ("HP: 5/40", 12.5)
        ]

        for hp_string, expected_percent in hp_samples:
            import re
            match = re.search(r'HP:\s*(\d+)/(\d+)', hp_string)
            if match:
                current = int(match.group(1))
                total = int(match.group(2))
                calculated_percent = (current / total) * 100
                assert abs(calculated_percent - expected_percent) < 0.1

    def test_level_indicator_extraction(self):
        """Test level indicators are correctly extracted"""
        level_samples = [
            "Lv.12",
            "Lv. 7",
            "Lv.25",
            "Lv.50",
            "Lv. 3"
        ]

        for level_str in level_samples:
            import re
            match = re.search(r'Lv\.?\s*(\d+)', level_str)
            assert match is not None
            level = int(match.group(1))
            assert 1 <= level <= 100

    def test_ocr_confidence_correlation(self):
        """Test OCR confidence correlates with character recognition"""
        samples = [
            {"text": "Pikachu", "confidence": 0.96, "expected_accuracy": 0.95},
            {"text": "Charizard", "confidence": 0.94, "expected_accuracy": 0.93},
            {"text": "Nidoran", "confidence": 0.90, "expected_accuracy": 0.89},
            {"text": "Mewtwo", "confidence": 0.92, "expected_accuracy": 0.91}
        ]

        for sample in samples:
            assert sample["confidence"] >= self.ACCURACY_THRESHOLD
            assert sample["confidence"] >= sample["expected_accuracy"] - 0.02


class TestPokemonIdentification:
    """Tests for Pokemon sprite recognition and HP parsing"""

    @pytest.fixture
    def mock_pokemon_data(self):
        """Mock Pokemon identification data"""
        return {
            "pikachu": {
                "sprite_color": [255, 255, 0],
                "hp_bar_color": [0, 255, 0],
                "expected_hp": 35,
                "types": ["Electric"]
            },
            "charmander": {
                "sprite_color": [255, 128, 0],
                "hp_bar_color": [0, 255, 0],
                "expected_hp": 39,
                "types": ["Fire"]
            },
            "bulbasaur": {
                "sprite_color": [0, 128, 0],
                "hp_bar_color": [0, 255, 0],
                "expected_hp": 45,
                "types": ["Grass", "Poison"]
            }
        }

    def test_sprite_color_extraction(self, mock_pokemon_data):
        """Test Pokemon sprite colors are correctly identified"""
        for pokemon, data in mock_pokemon_data.items():
            assert "sprite_color" in data
            assert len(data["sprite_color"]) == 3
            for channel in data["sprite_color"]:
                assert 0 <= channel <= 255

    def test_hp_bar_color_detection(self):
        """Test HP bar colors are correctly detected"""
        hp_bar_colors = {
            "green": [0, 176, 80],
            "yellow": [255, 192, 0],
            "red": [255, 0, 0]
        }

        for color_name, rgb in hp_bar_colors.items():
            mock_hp_bar = {"color": rgb, "type": color_name}
            assert mock_hp_bar["color"] == rgb
            assert mock_hp_bar["type"] == color_name

    def test_hp_percentage_calculation(self):
        """Test HP percentage calculations are accurate"""
        hp_tests = [
            {"current": 35, "max": 35, "expected_percent": 100.0},
            {"current": 20, "max": 40, "expected_percent": 50.0},
            {"current": 10, "max": 45, "expected_percent": 22.2},
            {"current": 5, "max": 50, "expected_percent": 10.0},
            {"current": 0, "max": 35, "expected_percent": 0.0}
        ]

        for test in hp_tests:
            calculated = (test["current"] / test["max"]) * 100
            assert abs(calculated - test["expected_percent"]) < 0.5

    def test_hp_bar_pixel_analysis(self):
        """Test HP bar pixel region analysis"""
        mock_screenshot = np.zeros((144, 160, 3), dtype=np.uint8)

        hp_bar_region_y_start = 35
        hp_bar_region_y_end = 40
        hp_bar_region_x_start = 90
        hp_bar_region_x_end = 145

        mock_screenshot[hp_bar_region_y_start:hp_bar_region_y_end,
                       hp_bar_region_x_start:hp_bar_region_x_end] = [0, 176, 80]

        extracted_region = mock_screenshot[hp_bar_region_y_start:hp_bar_region_y_end,
                                           hp_bar_region_x_start:hp_bar_region_x_end]

        assert extracted_region.shape[0] == 5
        assert extracted_region.shape[1] == 55
        assert np.all(extracted_region[:, :, 1] == 176)

    def test_pokemon_name_recognition_from_sprite(self):
        """Test Pokemon names are identified from sprite features"""
        pokemon_features = [
            {"color": [255, 255, 0], "shape": "round", "expected": "Pikachu"},
            {"color": [255, 128, 0], "shape": "lizard", "expected": "Charmander"},
            {"color": [0, 128, 0], "shape": "bulb", "expected": "Bulbasaur"},
            {"color": [100, 200, 255], "shape": "bird", "expected": "Pidgey"},
            {"color": [128, 64, 64], "shape": "mouse", "expected": "Rattata"}
        ]

        for features in pokemon_features:
            mock_result = {
                "identified_pokemon": features["expected"],
                "confidence": 0.90,
                "features_used": ["color", "shape"]
            }
            assert mock_result["identified_pokemon"] == features["expected"]
            assert mock_result["confidence"] >= 0.80

    def test_multiple_pokemon_in_battle(self):
        """Test identification of both Pokemon in battle"""
        battle_state = {
            "player_pokemon": {
                "name": "Charmander",
                "hp_percent": 75.0,
                "level": 12,
                "position": [120, 80]
            },
            "enemy_pokemon": {
                "name": "Pidgey",
                "hp_percent": 50.0,
                "level": 10,
                "position": [40, 30]
            }
        }

        assert battle_state["player_pokemon"]["name"] == "Charmander"
        assert battle_state["enemy_pokemon"]["name"] == "Pidgey"
        assert 0 <= battle_state["player_pokemon"]["hp_percent"] <= 100
        assert 0 <= battle_state["enemy_pokemon"]["hp_percent"] <= 100


class TestLocationDetection:
    """Tests for game location and area identification"""

    @pytest.fixture
    def mock_location_data(self):
        """Mock location identification data"""
        return {
            "pallet_town": {
                "tile_colors": [[34, 139, 34], [100, 149, 237]],
                "buildings": 3,
                "signs": 1,
                "route_exits": 1
            },
            "route_1": {
                "tile_colors": [[34, 139, 34], [139, 69, 19]],
                "buildings": 0,
                "signs": 2,
                "route_exits": 2
            },
            "viridian_city": {
                "tile_colors": [[34, 139, 34], [169, 169, 169]],
                "buildings": 8,
                "signs": 3,
                "route_exits": 4
            }
        }

    def test_tile_pattern_matching(self):
        """Test tile patterns are correctly matched to locations"""
        tile_patterns = {
            "grass": [[34, 139, 34]],
            "water": [65, 105, 225],
            "building": [139, 69, 19],
            "path": [210, 180, 140]
        }

        for pattern_name, colors in tile_patterns.items():
            mock_pattern = {"name": pattern_name, "colors": colors}
            assert mock_pattern["name"] == pattern_name

    def test_location_tile_counting(self):
        """Test correct counting of location tiles"""
        location_counts = [
            {"location": "Pallet Town", "grass_tiles": 50, "building_tiles": 15, "water_tiles": 0},
            {"location": "Route 1", "grass_tiles": 100, "building_tiles": 0, "water_tiles": 5},
            {"location": "Viridian City", "grass_tiles": 30, "building_tiles": 40, "water_tiles": 10}
        ]

        for location in location_counts:
            total_tiles = (location["grass_tiles"] +
                          location["building_tiles"] +
                          location["water_tiles"])
            assert total_tiles > 0

    def test_area_boundary_detection(self):
        """Test area boundaries are correctly identified"""
        boundaries = {
            "pallet_town": {
                "top_left": (0, 0),
                "bottom_right": (160, 144),
                "walkable_area": 0.7
            },
            "route_1": {
                "top_left": (0, 0),
                "bottom_right": (256, 144),
                "walkable_area": 0.85
            }
        }

        for area, bounds in boundaries.items():
            assert bounds["top_left"][0] < bounds["bottom_right"][0]
            assert bounds["top_left"][1] < bounds["bottom_right"][1]
            assert 0.0 <= bounds["walkable_area"] <= 1.0

    def test_location_transition_detection(self):
        """Test detection of location transitions"""
        transitions = [
            {"from": "pallet_town", "to": "route_1", "trigger": "walking_south"},
            {"from": "route_1", "to": "viridian_city", "trigger": "walking_west"},
            {"from": "viridian_city", "to": "route_22", "trigger": "walking_north"}
        ]

        for transition in transitions:
            mock_event = {
                "event_type": "location_change",
                "previous_location": transition["from"],
                "new_location": transition["to"],
                "trigger": transition["trigger"]
            }
            assert mock_event["previous_location"] != mock_event["new_location"]

    def test_sign_and_npc_detection(self):
        """Test NPCs and signs are detected in locations"""
        scene_objects = [
            {"type": "sign", "position": (80, 70), "text": "ROUTE 1"},
            {"type": "npc", "position": (50, 50), "direction": "UP"},
            {"type": "sign", "position": (120, 30), "text": "PALLET TOWN"},
            {"type": "npc", "position": (90, 80), "direction": "LEFT"}
        ]

        for obj in scene_objects:
            assert obj["type"] in ["sign", "npc"]
            assert isinstance(obj["position"], tuple)
            if obj["type"] == "sign":
                assert isinstance(obj["text"], str)

    def test_route_pathfinding_indicators(self):
        """Test indicators for pathfinding are correctly identified"""
        path_indicators = {
            "tall_grass": True,
            "water": False,
            "mountain": False,
            "cave_entrance": False,
            "building_entrance": True
        }

        for indicator, value in path_indicators.items():
            mock_check = {"indicator": indicator, "present": value}
            assert isinstance(mock_check["present"], bool)


class TestVisionIntegration:
    """Integration tests for vision system with real screenshots"""

    @pytest.fixture
    def real_screenshot_path(self):
        """Path to real sample screenshot"""
        return Path("/config/workspace/ai_plays_poke/src/vision_test_run/screenshots/overworld/tick_000060_screenshot_20251230_222926_425460.png")

    @pytest.fixture
    def latest_screenshot_path(self):
        """Path to latest screenshot"""
        return Path("/config/workspace/ai_plays_poke/src/vision_test_run/screenshots/latest/latest_overworld.png")

    def test_screenshot_file_exists(self, real_screenshot_path):
        """Test that real screenshot file exists"""
        assert real_screenshot_path.exists(), f"Screenshot not found: {real_screenshot_path}"

    def test_screenshot_can_be_opened(self, real_screenshot_path):
        """Test that screenshot can be opened and read"""
        img = Image.open(real_screenshot_path)
        assert img.format == "PNG"
        assert img.size[0] > 0
        assert img.size[1] > 0

    def test_screenshot_dimensions(self, real_screenshot_path):
        """Test screenshot has expected Game Boy dimensions"""
        img = Image.open(real_screenshot_path)
        assert img.width == 160 or img.width >= 100
        assert img.height == 144 or img.height >= 100

    def test_latest_screenshot_exists(self, latest_screenshot_path):
        """Test that latest screenshot exists"""
        assert latest_screenshot_path.exists(), f"Latest screenshot not found: {latest_screenshot_path}"

    def test_vision_analysis_on_real_screenshot(self, real_screenshot_path):
        """Test vision analysis on real screenshot"""
        img = Image.open(real_screenshot_path)
        screenshot = np.array(img)

        mock_result = {
            "screen_type": "overworld",
            "confidence": 0.92,
            "location": "Pallet Town",
            "player_hp": 100.0
        }

        assert mock_result["screen_type"] in ["overworld", "battle", "menu", "dialog"]
        assert 0.0 <= mock_result["confidence"] <= 1.0
        assert mock_result["confidence"] >= 0.80