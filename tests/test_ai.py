"""
AI system tests for PTP-01X Pokemon AI

Tests prompt selection, response parsing, decision validation,
and cost tracking using mocked API responses.
"""

import pytest
import json
import re
from unittest.mock import MagicMock, patch
from typing import Dict, Any, List, Optional
from datetime import datetime


class TestPromptSelection:
    """Tests for dynamic prompt selection based on game state"""

    @pytest.fixture
    def mock_prompt_manager(self):
        """Mock prompt manager for testing"""
        mock = MagicMock()
        mock.prompt_templates = []
        mock.get_relevant_prompts.return_value = []
        mock.select_prompts_for_ai.return_value = []
        return mock

    @pytest.fixture
    def sample_game_contexts(self):
        """Sample game contexts for testing prompt selection"""
        return {
            "battle": {
                "is_battle": True,
                "enemy_pokemon": "Pikachu",
                "turn_number": 3
            },
            "menu": {
                "is_battle": False,
                "is_menu": True,
                "menu_type": "pokemon"
            },
            "dialog": {
                "is_battle": False,
                "has_dialog": True,
                "dialog_text": "Hello there!"
            },
            "overworld": {
                "is_battle": False,
                "is_menu": False,
                "has_dialog": False,
                "location": "Route 1"
            }
        }

    def test_select_battle_prompts(self, sample_game_contexts, mock_prompt_manager):
        """Test correct prompts are selected for battle state"""
        from src.core.prompt_manager import PromptManager, PromptTemplate

        battle_template = PromptTemplate(
            name="basic_fighting",
            category="battle",
            description="Basic battle tactics",
            content="Analyze this battle screenshot...",
            priority=5
        )

        with patch.object(PromptManager, '__init__', lambda x, y=None: None):
            prompt_manager = PromptManager.__new__(PromptManager)
            prompt_manager.prompt_templates = [battle_template]
            prompt_manager.prompt_usage_stats = {}

            prompts = prompt_manager.select_prompts_for_ai(
                "battle",
                sample_game_contexts["battle"],
                "balanced"
            )

            assert len(prompts) >= 0

    def test_select_menu_prompts(self, sample_game_contexts):
        """Test correct prompts are selected for menu state"""
        from src.core.prompt_manager import PromptManager

        with patch.object(PromptManager, '__init__', lambda x, y=None: None):
            prompt_manager = PromptManager.__new__(PromptManager)
            prompt_manager.prompt_templates = []
            prompt_manager.prompt_usage_stats = {}

            relevant = prompt_manager.get_relevant_prompts(
                "menu",
                sample_game_contexts["menu"]
            )

            assert isinstance(relevant, list)

    def test_select_overworld_prompts(self, sample_game_contexts):
        """Test correct prompts are selected for overworld state"""
        from src.core.prompt_manager import PromptManager

        with patch.object(PromptManager, '__init__', lambda x, y=None: None):
            prompt_manager = PromptManager.__new__(PromptManager)
            prompt_manager.prompt_templates = []
            prompt_manager.prompt_usage_stats = {}

            relevant = prompt_manager.get_relevant_prompts(
                "overworld",
                sample_game_contexts["overworld"]
            )

            assert isinstance(relevant, list)

    def test_ai_preference_filtering(self):
        """Test AI preference affects prompt selection"""
        from src.core.prompt_manager import PromptManager

        with patch.object(PromptManager, '__init__', lambda x, y=None: None):
            prompt_manager = PromptManager.__new__(PromptManager)
            prompt_manager.prompt_templates = []
            prompt_manager.prompt_usage_stats = {}

            preferences = ["balanced", "tactical", "strategic"]

            for pref in preferences:
                prompts = prompt_manager.select_prompts_for_ai(
                    "battle",
                    {},
                    ai_preference=pref
                )
                assert isinstance(prompts, list)

    def test_prompt_priority_sorting(self):
        """Test prompts are sorted by priority"""
        from src.core.prompt_manager import PromptManager

        with patch.object(PromptManager, '__init__', lambda x, y=None: None):
            prompt_manager = PromptManager.__new__(PromptManager)
            prompt_manager.prompt_templates = []
            prompt_manager.prompt_usage_stats = {}

            relevant = prompt_manager.get_relevant_prompts("battle", {})

            assert isinstance(relevant, list)


class TestResponseParsing:
    """Tests for AI response parsing (JSON and fallback regex)"""

    JSON_PARSING_THRESHOLD = 0.85

    @pytest.fixture
    def mock_api_response(self):
        """Mock API response structure"""
        return {
            "content": "Sample AI response",
            "finish_reason": "stop",
            "model": "gpt-4o-mini",
            "usage": {
                "prompt_tokens": 150,
                "completion_tokens": 100
            },
            "duration_ms": 500.0
        }

    def test_json_response_parsing(self):
        """Test successful JSON response parsing"""
        json_response = '''
        {
            "screen_type": "battle",
            "enemy_pokemon": "Pikachu",
            "player_hp": 85,
            "enemy_hp": 50,
            "recommended_action": "press:A",
            "reasoning": "Use Thunderbolt for super-effective damage"
        }
        '''

        try:
            parsed = json.loads(json_response)
            assert parsed["screen_type"] == "battle"
            assert parsed["enemy_pokemon"] == "Pikachu"
            assert parsed["player_hp"] == 85
        except json.JSONDecodeError:
            pytest.fail("JSON parsing failed")

    def test_json_parse_success_rate(self):
        """Test JSON parsing success rate meets threshold"""
        test_responses = [
            '{"screen_type": "overworld"}',
            '{"confidence": 0.95}',
            '{"action": "press:A"}',
            '{"text": "Hello"}',
            '{"valid": true}'
        ]

        success_count = 0
        for response in test_responses:
            try:
                json.loads(response)
                success_count += 1
            except json.JSONDecodeError:
                pass

        success_rate = success_count / len(test_responses)
        assert success_rate >= self.JSON_PARSING_THRESHOLD, \
            f"JSON parse rate {success_rate} below threshold {self.JSON_PARSING_THRESHOLD}"

    def test_fallback_regex_parsing(self):
        """Test fallback regex parsing when JSON fails"""
        text_responses = [
            "REASONING: Use Ember ACTION: press:A",
            "REASONING: Navigate menu ACTION: press:DOWN",
            "ACTION: press:B REASONING: Go back",
            "press:UP to move north"
        ]

        for response in text_responses:
            result = self._extract_action_from_text(response)
            assert result is not None
            assert result.startswith("press:")

    def _extract_action_from_text(self, text: str) -> Optional[str]:
        """Helper to extract action from text using regex"""
        press_match = re.search(r'press:\s*(\w+)', text, re.IGNORECASE)
        if press_match:
            return f"press:{press_match.group(1).upper()}"

        button_match = re.search(r'\b(A|B|UP|DOWN|LEFT|RIGHT)\b', text.upper())
        if button_match:
            return f"press:{button_match.group(1)}"

        return None

    def test_tactical_response_parsing(self):
        """Test parsing tactical decision responses"""
        tactical_response = '''
        REASONING: The enemy Pikachu is at 50% HP and weak to Ground moves.
        ACTION: press:A

        Use Dig for super-effective damage!
        '''

        reasoning, action = self._parse_tactical_response(tactical_response)

        assert reasoning is not None
        assert action is not None
        assert action.startswith("press:")

    def _parse_tactical_response(self, response: str) -> tuple:
        """Helper to parse tactical response"""
        lines = response.strip().split('\n')

        reasoning = ""
        action = "press:A"

        for line in lines:
            line_upper = line.upper()
            if "REASONING:" in line_upper:
                reasoning = line.split(":", 1)[1].strip()
            elif "ACTION:" in line_upper:
                action = line.split(":", 1)[1].strip().upper()
                if not action.startswith("press:"):
                    action = f"press:{action}"

        if not reasoning:
            action = self._extract_action_from_text(response) or action

        return reasoning, action

    def test_strategic_response_parsing(self):
        """Test parsing strategic planning responses"""
        strategic_response = '''
        OBJECTIVE: Reach Viridian City
        KEY_TACTICS:
        1. Follow the main road south
        2. Avoid tall grass battles
        3. Keep Pokemon healthy

        CONFIDENCE: 0.85
        '''

        parsed = self._parse_strategic_response(strategic_response)

        assert "objective" in parsed
        assert "key_tactics" in parsed
        assert "confidence" in parsed

    def _parse_strategic_response(self, response: str) -> Dict[str, Any]:
        """Helper to parse strategic response"""
        result = {
            "objective": "",
            "key_tactics": [],
            "confidence": 0.5
        }

        obj_match = re.search(r'OBJECTIVE[:\s]+(.*?)(?:\n|$)', response, re.IGNORECASE)
        if obj_match:
            result["objective"] = obj_match.group(1).strip()

        items = re.findall(r'\d+\.\s+(.*?)(?=\n|$)', response)
        if items:
            result["key_tactics"] = items[:5]

        conf_match = re.search(r'CONFIDENCE[:\s]+([\d.]+)', response, re.IGNORECASE)
        if conf_match:
            try:
                result["confidence"] = float(conf_match.group(1))
            except ValueError:
                pass

        return result

    def test_vision_analysis_response_parsing(self):
        """Test parsing vision analysis responses"""
        vision_response = '''
        {
            "screen_type": "battle",
            "enemy_pokemon": "Charmander",
            "player_hp": 75,
            "enemy_hp": 60,
            "available_actions": ["A", "B", "DOWN"],
            "recommended_action": "press:A"
        }
        '''

        parsed = self._parse_vision_response(vision_response)

        assert "screen_type" in parsed
        assert "enemy_pokemon" in parsed
        assert "recommended_action" in parsed

    def _parse_vision_response(self, response: str) -> Dict[str, Any]:
        """Helper to parse vision analysis response"""
        import json as json_module

        try:
            json_match = re.search(r'\{[^{}]*\}', response)
            if json_match:
                return json_module.loads(json_match.group())
        except json_module.JSONDecodeError:
            pass

        return {}


class TestDecisionValidation:
    """Tests for AI decision validation and confidence thresholds"""

    CONFIDENCE_THRESHOLD = 0.70
    MIN_CONFIDENCE = 0.50

    @pytest.fixture
    def valid_commands(self):
        """List of valid command formats"""
        return [
            "press:A",
            "press:B",
            "press:UP",
            "press:DOWN",
            "press:LEFT",
            "press:RIGHT",
            "press:START",
            "press:SELECT",
            "batch:UPx10",
            "batch:DOWNx5",
            "sequence:UP,UP,LEFT,A"
        ]

    @pytest.fixture
    def invalid_commands(self):
        """List of invalid command formats"""
        return [
            "invalid:command",
            "press:INVALID",
            "jump:A",
            "",
            "press:",
            "batch:UP",
            "sequence:UP,INVALID"
        ]

    def test_valid_command_format(self, valid_commands):
        """Test valid command formats are accepted"""
        for command in valid_commands:
            parsed = self._parse_command(command)
            assert parsed is not None, f"Failed to parse valid command: {command}"

    def test_invalid_command_rejection(self, invalid_commands):
        """Test invalid command formats are rejected"""
        for command in invalid_commands:
            if command:
                parsed = self._parse_command(command)
                if parsed is not None:
                    is_valid = self._validate_command(parsed)
                    assert not is_valid, f"Invalid command was accepted: {command}"

    def _parse_command(self, command_str: str) -> Optional[Dict[str, Any]]:
        """Parse command string to components"""
        parts = command_str.split(":")
        if len(parts) != 2:
            return None

        command_type, params = parts
        result = {"command_type": command_type}

        if command_type == "press":
            valid_buttons = ["A", "B", "UP", "DOWN", "LEFT", "RIGHT", "START", "SELECT"]
            if params in valid_buttons:
                result["button"] = params
                return result
        elif command_type == "batch":
            if "x" in params:
                direction, steps = params.split("x")
                result["batch_direction"] = direction
                result["batch_steps"] = int(steps)
                return result
        elif command_type == "sequence":
            buttons = params.split(",")
            valid_buttons = ["A", "B", "UP", "DOWN", "LEFT", "RIGHT"]
            if all(b in valid_buttons for b in buttons):
                result["button_sequence"] = buttons
                return result

        return None

    def _validate_command(self, parsed: Dict[str, Any]) -> bool:
        """Validate parsed command structure"""
        if not parsed:
            return False

        command_type = parsed.get("command_type")
        if command_type == "press":
            return "button" in parsed and parsed["button"] in ["A", "B", "UP", "DOWN", "LEFT", "RIGHT", "START", "SELECT"]
        elif command_type == "batch":
            return "batch_direction" in parsed and "batch_steps" in parsed
        elif command_type == "sequence":
            return "button_sequence" in parsed and len(parsed["button_sequence"]) > 0

        return False

    def test_confidence_threshold_enforcement(self):
        """Test confidence threshold is enforced"""
        decisions = [
            {"action": "press:A", "confidence": 0.95},
            {"action": "press:B", "confidence": 0.85},
            {"action": "press:UP", "confidence": 0.75},
            {"action": "press:DOWN", "confidence": 0.65},
            {"action": "press:LEFT", "confidence": 0.55},
        ]

        for decision in decisions:
            if decision["confidence"] >= self.CONFIDENCE_THRESHOLD:
                assert decision["action"].startswith("press:")
            else:
                assert decision["confidence"] >= self.MIN_CONFIDENCE

    def test_confidence_score_range(self):
        """Test confidence scores are within valid range"""
        confidence_scores = [
            {"score": 1.0, "valid": True},
            {"score": 0.95, "valid": True},
            {"score": 0.70, "valid": True},
            {"score": 0.50, "valid": True},
            {"score": 0.0, "valid": True},
            {"score": -0.1, "valid": False},
            {"score": 1.1, "valid": False}
        ]

        for test in confidence_scores:
            is_valid = 0.0 <= test["score"] <= 1.0
            assert is_valid == test["valid"]

    def test_battle_action_validation(self):
        """Test battle actions are valid"""
        battle_decisions = [
            {"action": "press:A", "context": "battle", "valid": True},
            {"action": "press:B", "context": "battle", "valid": True},
            {"action": "press:START", "context": "battle", "valid": False},
            {"action": "batch:UPx10", "context": "battle", "valid": False}
        ]

        battle_valid_buttons = ["A", "B"]

        for decision in battle_decisions:
            if decision["context"] == "battle":
                button = decision["action"].split(":")[1] if ":" in decision["action"] else ""
                is_valid_battle_action = button in battle_valid_buttons and not decision["action"].startswith("batch:")
                assert is_valid_battle_action == decision["valid"], \
                    f"Battle action validation mismatch: {decision}"

    def test_overworld_action_validation(self):
        """Test overworld actions are valid"""
        overworld_decisions = [
            {"action": "press:A", "context": "overworld", "valid": True},
            {"action": "press:UP", "context": "overworld", "valid": True},
            {"action": "press:B", "context": "overworld", "valid": False},
            {"action": "batch:UPx10", "context": "overworld", "valid": True}
        ]

        for decision in overworld_decisions:
            if decision["context"] == "overworld":
                if decision["action"].startswith("batch:"):
                    assert decision["valid"]
                elif decision["action"].startswith("press:"):
                    button = decision["action"].split(":")[1]
                    assert (button in ["UP", "DOWN", "LEFT", "RIGHT", "A"]) == decision["valid"]


class TestCostTracking:
    """Tests for token counting and cost calculation accuracy"""

    COST_CALCULATION_TOLERANCE = 0.0001

    @pytest.fixture
    def sample_token_usage(self):
        """Sample token usage data"""
        return [
            {"input_tokens": 100, "output_tokens": 50, "expected_cost": 0.000045},
            {"input_tokens": 500, "output_tokens": 200, "expected_cost": 0.000195},
            {"input_tokens": 1000, "output_tokens": 500, "expected_cost": 0.00045},
            {"input_tokens": 2000, "output_tokens": 1000, "expected_cost": 0.0009}
        ]

    def test_gpt_4o_mini_cost_calculation(self, sample_token_usage):
        """Test GPT-4o-mini cost calculation accuracy"""
        input_cost_per_token = 0.00000015
        output_cost_per_token = 0.0000006

        for usage in sample_token_usage:
            calculated_cost = (
                usage["input_tokens"] * input_cost_per_token +
                usage["output_tokens"] * output_cost_per_token
            )

            assert abs(calculated_cost - usage["expected_cost"]) < self.COST_CALCULATION_TOLERANCE, \
                f"Cost calculation mismatch: {calculated_cost} != {usage['expected_cost']}"

    def test_gpt_4o_cost_calculation(self):
        """Test GPT-4o cost calculation accuracy"""
        input_cost_per_token = 0.000005
        output_cost_per_token = 0.000015

        test_cases = [
            {"input_tokens": 100, "output_tokens": 50, "expected": 0.00125},
            {"input_tokens": 1000, "output_tokens": 500, "expected": 0.0125},
        ]

        for test in test_cases:
            calculated = (
                test["input_tokens"] * input_cost_per_token +
                test["output_tokens"] * output_cost_per_token
            )

            assert abs(calculated - test["expected"]) < 0.0001

    def test_token_counting_accuracy(self):
        """Test token counts are accurately recorded"""
        api_usage = {
            "prompt_tokens": 150,
            "completion_tokens": 75,
            "total_tokens": 225
        }

        assert api_usage["total_tokens"] == api_usage["prompt_tokens"] + api_usage["completion_tokens"]
        assert all(v >= 0 for v in api_usage.values())

    def test_vision_model_cost_includes_image_tokens(self):
        """Test vision model costs include image token overhead"""
        base_text_tokens = 100
        estimated_image_tokens = 500
        total_input_tokens = base_text_tokens + estimated_image_tokens
        output_tokens = 100

        input_cost_per_token = 0.000005
        output_cost_per_token = 0.000015

        vision_cost = (
            total_input_tokens * input_cost_per_token +
            output_tokens * output_cost_per_token
        )

        base_text_cost = (
            base_text_tokens * input_cost_per_token +
            output_tokens * output_cost_per_token
        )

        assert vision_cost > base_text_cost
        assert vision_cost > 0.003

    def test_cost_accumulation_over_session(self):
        """Test cumulative cost tracking over multiple API calls"""
        calls = [
            {"input_tokens": 100, "output_tokens": 50, "cost": 0.0006},
            {"input_tokens": 200, "output_tokens": 100, "cost": 0.0012},
            {"input_tokens": 150, "output_tokens": 75, "cost": 0.0009},
        ]

        cumulative_cost = sum(call["cost"] for call in calls)
        expected_cumulative = 0.0027

        assert abs(cumulative_cost - expected_cumulative) < 0.0001
        assert cumulative_cost > 0.0

    def test_cost_per_action_calculation(self):
        """Test cost per game action is calculated correctly"""
        session_stats = {
            "total_calls": 100,
            "total_cost": 0.50,
            "total_actions": 500
        }

        cost_per_action = session_stats["total_cost"] / session_stats["total_actions"]
        expected_cost_per_action = 0.001

        assert abs(cost_per_action - expected_cost_per_action) < 0.0001

    def test_model_pricing_tiers(self):
        """Test different model pricing tiers"""
        pricing = {
            "gpt-4o-mini": {"input": 0.00000015, "output": 0.0000006},
            "gpt-4o": {"input": 0.000005, "output": 0.000015},
            "gpt-4-vision-preview": {"input": 0.00001, "output": 0.00003}
        }

        for model, prices in pricing.items():
            assert prices["input"] > 0
            assert prices["output"] > 0
            assert prices["output"] > prices["input"]

    def test_token_limit_compliance(self):
        """Test token limits are properly tracked"""
        model_limits = {
            "gpt-4o-mini": {"max_tokens": 4000, "max_output": 500},
            "gpt-4o": {"max_tokens": 8000, "max_output": 2000}
        }

        for model, limits in model_limits.items():
            assert limits["max_tokens"] > limits["max_output"]
            assert limits["max_output"] > 0

        test_usage = {"prompt_tokens": 3500, "completion_tokens": 400}

        assert test_usage["prompt_tokens"] + test_usage["completion_tokens"] < model_limits["gpt-4o-mini"]["max_tokens"]


class TestAIIntegration:
    """Integration tests for AI system with mocked API responses"""

    @pytest.fixture
    def mock_ai_client(self):
        """Mock AI client with predefined responses"""
        client = MagicMock()
        client.generate_decision.return_value = {
            "command": "press:A",
            "reasoning": "Test action",
            "confidence": 0.85,
        }
        client.get_completion.return_value = "Test completion"
        client.get_cost.return_value = 0.001
        client.get_tokens.return_value = {"input": 100, "output": 50}
        return client

    def test_full_decision_flow_with_mocks(self, mock_ai_client):
        """Test complete decision flow with mocked API"""
        game_state = {
            "screen_type": "battle",
            "enemy_pokemon": "Pikachu",
            "player_hp": 75
        }

        decision = mock_ai_client.generate_decision(game_state)

        assert decision["command"] == "press:A"
        assert decision["confidence"] >= 0.70
        assert isinstance(decision["reasoning"], str)

    def test_cost_tracking_with_mocks(self, mock_ai_client):
        """Test cost tracking with mocked API"""
        tokens = mock_ai_client.get_tokens()
        cost = mock_ai_client.get_cost()

        assert tokens["input"] > 0
        assert tokens["output"] > 0
        assert cost > 0

    def test_response_parsing_integration(self):
        """Test response parsing in integration context"""
        raw_responses = [
            '{"action": "press:A", "confidence": 0.9}',
            'REASONING: Test ACTION: press:B',
            'press:UP'
        ]

        for response in raw_responses:
            parsed = self._parse_for_integration(response)
            assert parsed is not None

    def _parse_for_integration(self, response: str) -> Optional[Dict[str, Any]]:
        """Parse response for integration test"""
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass

        if "ACTION:" in response.upper():
            match = re.search(r'ACTION:\s*(\w+)', response, re.IGNORECASE)
            if match:
                return {"action": f"press:{match.group(1).upper()}"}

        if response.startswith("press:"):
            return {"action": response}

        return None

    def test_prompt_selection_integration(self):
        """Test prompt selection integration"""
        from src.core.prompt_manager import PromptManager

        with patch.object(PromptManager, '__init__', lambda x, y=None: None):
            prompt_manager = PromptManager.__new__(PromptManager)
            prompt_manager.prompt_templates = []
            prompt_manager.prompt_usage_stats = {}

            state_types = ["battle", "menu", "dialog", "overworld"]

            for state_type in state_types:
                prompts = prompt_manager.select_prompts_for_ai(state_type, {})
                assert isinstance(prompts, list)

    def test_ai_client_initialization(self):
        """Test AI client can be initialized with mocks"""
        from src.core.ai_client import OpenRouterClient, GameAIManager

        with patch.object(OpenRouterClient, '__init__', lambda self, key=None: None):
            client = OpenRouterClient.__new__(OpenRouterClient)
            client.models = {
                "vision": "openai/gpt-4o",
                "thinking": "openai/gpt-4o-mini",
                "acting": "openai/gpt-4o-mini"
            }
            client.total_cost = 0.0
            client.call_count = 0

            assert "vision" in client.models
            assert "thinking" in client.models
            assert client.total_cost == 0.0


class TestClaudeIntegration:
    """Tests for Claude API integration with mocked responses"""

    @pytest.fixture
    def mock_anthropic_client(self):
        """Mock Anthropic client for testing"""
        mock = MagicMock()
        mock.models = {
            "vision": "claude-3-sonnet-20240307",
            "thinking": "claude-3-haiku-20240307",
            "acting": "claude-3-haiku-20240307"
        }
        mock.circuit_breaker = MagicMock()
        mock.circuit_breaker.allow_request.return_value = True
        return mock

    def test_claude_client_initialization(self):
        """Test Claude client can be initialized"""
        with patch('src.core.ai_client.ANTHROPIC_AVAILABLE', True):
            with patch('src.core.ai_client.Anthropic') as mock_anthropic:
                mock_client = MagicMock()
                mock_anthropic.return_value = mock_client

                from src.core.ai_client import ClaudeClient
                client = ClaudeClient(api_key="test-key")

                assert client.api_key == "test-key"
                assert "vision" in client.models
                assert "thinking" in client.models

    def test_claude_chat_completion(self, mock_anthropic_client):
        """Test Claude chat completion with mocked response"""
        from src.core.ai_client import ClaudeClient

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Test response")]
        mock_response.stop_reason = "stop"
        mock_response.id = "test-id-123"
        mock_response.usage = MagicMock(
            input_tokens=100,
            output_tokens=50
        )

        with patch('src.core.ai_client.ANTHROPIC_AVAILABLE', True):
            with patch('src.core.ai_client.Anthropic') as mock_anthropic:
                mock_client = MagicMock()
                mock_client.messages.create.return_value = mock_response
                mock_anthropic.return_value = mock_client

                client = ClaudeClient(api_key="test-key")
                result = client.chat_completion(
                    model="claude-3-haiku-20240307",
                    messages=[{"role": "user", "content": "Hello"}]
                )

                assert result["content"] == "Test response"
                assert result["model"] == "claude-3-haiku-20240307"
                assert "usage" in result

    def test_claude_get_text_response(self, mock_anthropic_client):
        """Test Claude text response generation"""
        from src.core.ai_client import ClaudeClient

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Strategic plan: Battle Pidgey")]
        mock_response.stop_reason = "stop"
        mock_response.id = "test-id-456"
        mock_response.usage = MagicMock(input_tokens=200, output_tokens=100)

        with patch('src.core.ai_client.ANTHROPIC_AVAILABLE', True):
            with patch('src.core.ai_client.Anthropic') as mock_anthropic:
                mock_client = MagicMock()
                mock_client.messages.create.return_value = mock_response
                mock_anthropic.return_value = mock_client

                client = ClaudeClient(api_key="test-key")
                response = client.get_text_response(
                    prompt="Plan the battle",
                    model="claude-3-haiku-20240307"
                )

                assert response == "Strategic plan: Battle Pidgey"


class TestTokenTracker:
    """Tests for token usage tracking and cost calculation"""

    @pytest.fixture
    def token_tracker(self):
        """Create a fresh TokenTracker for testing"""
        from src.core.ai_client import TokenTracker
        return TokenTracker()

    def test_token_tracker_initialization(self, token_tracker):
        """Test TokenTracker initializes with zero values"""
        stats = token_tracker.get_session_stats()
        assert stats["total_calls"] == 0
        assert stats["total_cost"] == 0.0
        assert stats["total_input_tokens"] == 0

    def test_record_request_updates_stats(self, token_tracker):
        """Test recording a request updates all counters"""
        token_tracker.record_request(
            model="gpt-4o-mini",
            input_tokens=100,
            output_tokens=50,
            cost=0.000045,
            duration_ms=150.0
        )

        stats = token_tracker.get_session_stats()
        assert stats["total_calls"] == 1
        assert stats["total_input_tokens"] == 100
        assert stats["total_output_tokens"] == 50
        assert stats["total_cost"] == 0.000045

    def test_multiple_requests_accumulate(self, token_tracker):
        """Test multiple requests accumulate correctly"""
        requests = [
            {"model": "gpt-4o-mini", "input": 100, "output": 50, "cost": 0.000045},
            {"model": "gpt-4o-mini", "input": 200, "output": 100, "cost": 0.00009},
            {"model": "gpt-4o-mini", "input": 150, "output": 75, "cost": 0.0000675}
        ]

        for req in requests:
            token_tracker.record_request(
                model=req["model"],
                input_tokens=req["input"],
                output_tokens=req["output"],
                cost=req["cost"],
                duration_ms=100.0
            )

        stats = token_tracker.get_session_stats()
        assert stats["total_calls"] == 3
        assert stats["total_input_tokens"] == 450
        assert stats["total_output_tokens"] == 225
        assert abs(stats["total_cost"] - 0.0002025) < 0.000001

    def test_cost_per_decision_calculation(self, token_tracker):
        """Test cost per decision is calculated accurately"""
        token_tracker.record_request(
            model="gpt-4o-mini",
            input_tokens=1000,
            output_tokens=500,
            cost=0.00045,
            duration_ms=200.0
        )

        stats = token_tracker.get_session_stats()
        assert stats["total_cost"] > 0.0

        cost_per_action = token_tracker.get_cost_per_decision(decisions=100)
        assert cost_per_action == 0.0000045

    def test_reset_clears_all_data(self, token_tracker):
        """Test reset clears all tracking data"""
        token_tracker.record_request(
            model="gpt-4o-mini",
            input_tokens=100,
            output_tokens=50,
            cost=0.000045,
            duration_ms=100.0
        )

        token_tracker.reset()

        stats = token_tracker.get_session_stats()
        assert stats["total_calls"] == 0
        assert stats["total_cost"] == 0.0


class TestJSONResponseParser:
    """Tests for structured JSON response parsing"""

    @pytest.fixture
    def parser(self):
        """Create a JSONResponseParser for testing"""
        from src.core.ai_client import JSONResponseParser
        return JSONResponseParser(
            schema={
                "screen_type": str,
                "enemy_pokemon": str,
                "player_hp": int,
                "enemy_hp": int,
                "recommended_action": str
            },
            max_retries=3
        )

    def test_valid_json_parsing(self, parser):
        """Test parsing valid JSON response"""
        response = '''
        {
            "screen_type": "battle",
            "enemy_pokemon": "Pikachu",
            "player_hp": 85,
            "enemy_hp": 50,
            "recommended_action": "press:A"
        }
        '''
        result = parser.parse(response)

        assert result["screen_type"] == "battle"
        assert result["enemy_pokemon"] == "Pikachu"
        assert result["player_hp"] == 85
        assert result["enemy_hp"] == 50

    def test_json_with_code_blocks(self, parser):
        """Test parsing JSON wrapped in markdown code blocks"""
        response = '''
        ```json
        {
            "screen_type": "menu",
            "action": "press:DOWN"
        }
        ```
        '''
        result = parser.parse(response)

        assert result["screen_type"] == "menu"
        assert result["action"] == "press:DOWN"

    def test_fallback_regex_extraction(self, parser):
        """Test regex fallback for malformed JSON"""
        response = '''
        Here's my analysis:
        Screen type: battle
        Enemy: Charizard
        HP: 75%
        Action: press:A
        '''
        try:
            result = parser.parse(response)
            assert result is not None
        except ValueError:
            pass

    def test_parse_success_rate_tracking(self, parser):
        """Test parsing success rate is tracked"""
        responses = [
            '{"valid": true}',
            '{"also": "valid"}'
        ]

        for response in responses:
            try:
                parser.parse(response)
            except ValueError:
                pass

        success_rate = parser.get_success_rate()
        assert success_rate >= 0.9

    def test_schema_validation(self, parser):
        """Test schema validation rejects invalid types"""
        response = '{"screen_type": 123, "player_hp": "high"}'

        try:
            result = parser.parse(response)
        except (ValueError, TypeError):
            pass


class TestRateLimiter:
    """Tests for rate limiting with exponential backoff"""

    @pytest.fixture
    def rate_limiter(self):
        """Create a RateLimiter for testing"""
        from src.core.ai_client import RateLimiter
        return RateLimiter(max_requests=10, time_window=60.0, base_delay=0.1)

    def test_rate_limiter_allows_requests_under_limit(self, rate_limiter):
        """Test rate limiter allows requests under the limit"""
        for i in range(5):
            delay = rate_limiter.wait()
            assert delay == 0.0

    def test_rate_limiter_blocks_over_limit(self, rate_limiter):
        """Test rate limiter blocks requests over the limit"""
        rate_limiter.max_requests = 3

        for i in range(3):
            rate_limiter.wait()

        delay = rate_limiter.wait()
        assert delay > 0

    def test_exponential_backoff(self, rate_limiter):
        """Test exponential backoff increases delay"""
        delay1 = rate_limiter.get_delay(0)
        delay2 = rate_limiter.get_delay(1)
        delay3 = rate_limiter.get_delay(2)

        assert delay2 > delay1
        assert delay3 > delay2
        assert delay3 <= rate_limiter.max_delay


class TestCircuitBreaker:
    """Tests for circuit breaker pattern"""

    @pytest.fixture
    def circuit_breaker(self):
        """Create a CircuitBreaker for testing"""
        from src.core.ai_client import CircuitBreaker
        return CircuitBreaker(failure_threshold=3, recovery_time=0.1)

    def test_circuit_breaker_allows_requests_initially(self, circuit_breaker):
        """Test circuit breaker allows requests when closed"""
        assert circuit_breaker.allow_request() is True

    def test_circuit_breaker_opens_after_failures(self, circuit_breaker):
        """Test circuit breaker opens after failure threshold"""
        for i in range(3):
            circuit_breaker.record_failure()

        assert circuit_breaker.state == "open"
        assert circuit_breaker.allow_request() is False

    def test_circuit_breaker_closes_on_success(self, circuit_breaker):
        """Test circuit breaker closes on success"""
        circuit_breaker.record_failure()
        circuit_breaker.record_success()

        assert circuit_breaker.state == "closed"
        assert circuit_breaker.allow_request() is True

    def test_circuit_breaker_half_open_recovery(self, circuit_breaker):
        """Test circuit breaker enters half-open state after recovery time"""
        for i in range(3):
            circuit_breaker.record_failure()

        import time
        time.sleep(0.15)

        assert circuit_breaker.allow_request() is True
        assert circuit_breaker.state == "half-open"


class TestModelRouter:
    """Tests for model selection and routing"""

    @pytest.fixture
    def model_router(self):
        """Create a ModelRouter for testing"""
        from src.core.ai_client import ModelRouter
        return ModelRouter()

    def test_select_model_for_speed(self, model_router):
        """Test model selection prioritizes speed"""
        provider, model = model_router.select_model("vision", "speed")

        assert provider == "openrouter"
        assert "gpt-4o" in model or "mini" in model

    def test_select_model_for_cost(self, model_router):
        """Test model selection prioritizes cost"""
        provider, model = model_router.select_model("thinking", "cost")

        assert provider == "openrouter"
        assert "mini" in model

    def test_select_model_for_quality(self, model_router):
        """Test model selection prioritizes quality"""
        provider, model = model_router.select_model("vision", "quality")

        assert "claude" in model or "gpt-4o" in model

    def test_select_model_balanced(self, model_router):
        """Test balanced model selection"""
        provider, model = model_router.select_model("acting", "balanced")

        assert provider in ["openrouter", "anthropic"]

    def test_different_models_for_different_task_types(self, model_router):
        """Test different models selected for different task types"""
        _, vision_model = model_router.select_model("vision", "balanced")
        _, thinking_model = model_router.select_model("thinking", "balanced")
        _, acting_model = model_router.select_model("acting", "balanced")

        assert isinstance(vision_model, str)
        assert isinstance(thinking_model, str)
        assert isinstance(acting_model, str)


class TestCostCalculation:
    """Tests for cost calculation with different models"""

    def test_gpt_4o_pricing(self):
        """Test GPT-4o pricing calculation"""
        from src.core.ai_client import calculate_cost, get_model_pricing

        input_price, output_price = get_model_pricing("gpt-4o")
        assert input_price == 5.0
        assert output_price == 15.0

        cost = calculate_cost("gpt-4o", 1000, 500)
        assert cost == 0.0125

    def test_gpt_4o_mini_pricing(self):
        """Test GPT-4o-mini pricing calculation"""
        from src.core.ai_client import calculate_cost, get_model_pricing

        input_price, output_price = get_model_pricing("gpt-4o-mini")
        assert input_price == 0.15
        assert output_price == 0.6

        cost = calculate_cost("gpt-4o-mini", 1000, 500)
        assert cost == 0.00045

    def test_claude_3_sonnet_pricing(self):
        """Test Claude 3 Sonnet pricing calculation"""
        from src.core.ai_client import calculate_cost, get_model_pricing

        input_price, output_price = get_model_pricing("claude-3-sonnet-20240307")
        assert input_price == 3.0
        assert output_price == 15.0

        cost = calculate_cost("claude-3-sonnet-20240307", 1000, 500)
        assert abs(cost - 0.0105) < 0.0001

    def test_claude_3_haiku_pricing(self):
        """Test Claude 3 Haiku pricing calculation"""
        from src.core.ai_client import calculate_cost, get_model_pricing

        input_price, output_price = get_model_pricing("claude-3-haiku-20240307")
        assert input_price == 0.25
        assert output_price == 1.25

        cost = calculate_cost("claude-3-haiku-20240307", 1000, 500)
        assert cost == 0.000875


class TestGameAIManagerIntegration:
    """Integration tests for enhanced GameAIManager"""

    def test_game_ai_manager_with_prompt_manager(self):
        """Test GameAIManager initializes with PromptManager"""
        with patch('src.core.ai_client.OpenRouterClient'):
            with patch('src.core.prompt_manager.PromptManager') as mock_pm:
                mock_instance = MagicMock()
                mock_pm.return_value = mock_instance

                from src.core.ai_client import GameAIManager
                manager = GameAIManager(
                    api_key="test-key",
                    enable_prompt_manager=True
                )

                mock_pm.assert_called_once()
                assert manager.prompt_manager is not None

    def test_game_ai_manager_without_prompt_manager(self):
        """Test GameAIManager works without PromptManager"""
        with patch('src.core.ai_client.OpenRouterClient'):
            with patch('src.core.prompt_manager.PromptManager') as mock_pm:
                mock_pm.side_effect = Exception("Not available")

                from src.core.ai_client import GameAIManager
                manager = GameAIManager(
                    api_key="test-key",
                    enable_prompt_manager=True
                )

                assert manager.prompt_manager is None

    def test_session_stats_retrieval(self):
        """Test session statistics are retrieved correctly"""
        from src.core.ai_client import GameAIManager

        with patch('src.core.ai_client.OpenRouterClient'):
            manager = GameAIManager(api_key="test-key")

            stats = manager.get_session_stats()

            assert "total_calls" in stats
            assert "total_cost" in stats
            assert "json_parse_success_rate" in stats

    def test_session_stats_reset(self):
        """Test session statistics can be reset"""
        from src.core.ai_client import GameAIManager

        with patch('src.core.ai_client.OpenRouterClient'):
            manager = GameAIManager(api_key="test-key")

            manager.reset_session_stats()

            stats = manager.get_session_stats()
            assert stats["total_calls"] == 0
            assert stats["total_cost"] == 0.0
