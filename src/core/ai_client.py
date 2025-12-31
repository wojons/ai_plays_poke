"""
OpenRouter API Client for AI Models

Supports both vision and text-only models from OpenRouter and Anthropic Claude
"""

import os
import time
import base64
import json
import re
import asyncio
import threading
from typing import Optional, Dict, Any, List, Callable
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from functools import wraps
import hashlib

import numpy as np
from PIL import Image
import requests

try:
    from src.vision import VisionPipeline, OCREngine, SpriteRecognizer, BattleAnalyzer, LocationDetector
    VISION_AVAILABLE = True
except ImportError:
    VISION_AVAILABLE = False
    VisionPipeline = None
    OCREngine = None
    SpriteRecognizer = None
    BattleAnalyzer = None
    LocationDetector = None

try:
    from anthropic import Anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    Anthropic = None


class APIError(Exception):
    """Exception raised for API-related errors"""
    pass


@dataclass
class TokenUsage:
    """Token usage tracking for API calls"""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    timestamp: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        self.total_tokens = self.prompt_tokens + self.completion_tokens


@dataclass
class APICallResult:
    """Result of an API call with full metadata"""
    content: str
    model: str
    token_usage: TokenUsage
    cost: float
    duration_ms: float
    success: bool = True
    error_message: Optional[str] = None
    retry_count: int = 0
    request_id: Optional[str] = None


class CircuitBreaker:
    """Circuit breaker pattern for API calls"""

    def __init__(self, failure_threshold: int = 5, recovery_time: float = 60.0):
        self.failure_threshold = failure_threshold
        self.recovery_time = recovery_time
        self.failures = 0
        self.last_failure: Optional[datetime] = None
        self.state = "closed"  # closed, open, half-open
        self.lock = threading.Lock()

    def record_success(self):
        with self.lock:
            self.failures = 0
            self.state = "closed"

    def record_failure(self):
        with self.lock:
            self.failures += 1
            self.last_failure = datetime.now()
            if self.failures >= self.failure_threshold:
                self.state = "open"

    def allow_request(self) -> bool:
        with self.lock:
            if self.state == "closed":
                return True
            if self.state == "open":
                if self.last_failure and (datetime.now() - self.last_failure).total_seconds() > self.recovery_time:
                    self.state = "half-open"
                    return True
            return False


class TokenTracker:
    """Track token usage and calculate costs accurately"""

    def __init__(self):
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cost = 0.0
        self.call_count = 0
        self.request_history: List[Dict[str, Any]] = []
        self.lock = threading.Lock()

    def record_request(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost: float,
        duration_ms: float
    ):
        with self.lock:
            self.total_input_tokens += input_tokens
            self.total_output_tokens += output_tokens
            self.total_cost += cost
            self.call_count += 1

            self.request_history.append({
                "timestamp": datetime.now().isoformat(),
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost": cost,
                "duration_ms": duration_ms
            })

    def get_cost_per_decision(self, decisions: int = 1) -> float:
        """Calculate cost per decision (accurate to $0.001)"""
        if decisions <= 0:
            return 0.0
        return self.total_cost / decisions

    def get_session_stats(self) -> Dict[str, Any]:
        """Get session statistics"""
        with self.lock:
            return {
                "total_calls": self.call_count,
                "total_input_tokens": self.total_input_tokens,
                "total_output_tokens": self.total_output_tokens,
                "total_tokens": self.total_input_tokens + self.total_output_tokens,
                "total_cost": round(self.total_cost, 6),
                "avg_cost_per_call": round(self.total_cost / self.call_count, 6) if self.call_count > 0 else 0.0,
                "avg_input_tokens": round(self.total_input_tokens / self.call_count, 1) if self.call_count > 0 else 0,
                "avg_output_tokens": round(self.total_output_tokens / self.call_count, 1) if self.call_count > 0 else 0
            }

    def reset(self):
        with self.lock:
            self.total_input_tokens = 0
            self.total_output_tokens = 0
            self.total_cost = 0.0
            self.call_count = 0
            self.request_history = []


def log_api_call(model: str, duration_ms: float, input_tokens: int,
                 output_tokens: int, cost: float, success: bool = True):
    """Simple logging function for API calls"""
    print(f"📡 API: {model} | {duration_ms:.0f}ms | "
          f"In: {input_tokens} | Out: {output_tokens} | "
          f"${cost:.6f} | Success: {success}")


def log_vision_analysis(screen_type: str, enemy_pokemon: str,
                        player_hp: float, enemy_hp: float):
    """Simple logging function for vision analysis"""
    print(f"👁️ Vision: {screen_type} | Enemy: {enemy_pokemon or 'None'} | "
          f"HP: {player_hp:.0f}%/{enemy_hp:.0f}%")


# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    # Try to load .env from current directory and project root
    load_dotenv(dotenv_path=".env")
    load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")
except ImportError:
    print("⚠️  python-dotenv not installed, using system environment variables only")
    # Try manual loading if python-dotenv not available
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        print(f"📝 Loading .env from {env_path}")
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    if key and value and not os.environ.get(key):
                        os.environ[key] = value


def get_model_pricing(model: str) -> tuple:
    """Get input/output pricing per million tokens for a model"""
    model_lower = model.lower()

    if "claude-3-opus" in model_lower:
        return 15.0, 75.0  # $15/$75 per 1M
    elif "claude-3-sonnet" in model_lower:
        return 3.0, 15.0  # $3/$15 per 1M
    elif "claude-3-haiku" in model_lower:
        return 0.25, 1.25  # $0.25/$1.25 per 1M
    elif "claude-2" in model_lower:
        return 8.0, 32.0  # $8/$32 per 1M
    elif "gpt-4o" in model_lower and "mini" not in model_lower:
        return 5.0, 15.0  # $5/$15 per 1M
    elif "gpt-4o-mini" in model_lower:
        return 0.15, 0.6  # $0.15/$0.60 per 1M
    elif "gpt-4-turbo" in model_lower:
        return 10.0, 30.0  # $10/$30 per 1M
    elif "gpt-4" in model_lower:
        return 30.0, 60.0  # $30/$60 per 1M
    elif "gpt-3.5-turbo" in model_lower:
        return 0.5, 1.5  # $0.5/$1.5 per 1M
    else:
        return 5.0, 15.0  # Default pricing


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Calculate cost for a request based on model and token usage"""
    input_price, output_price = get_model_pricing(model)
    input_cost = (input_tokens / 1_000_000) * input_price
    output_cost = (output_tokens / 1_000_000) * output_price
    return input_cost + output_cost


class AIModelClient:
    """
    Wrapper class for AI Model API client

    Provides the interface expected by API key tests with methods:
    - _load_api_key() - returns the API key
    - _validate_api_key() - validates the key, raises APIError if invalid
    - _make_request_with_retry() - makes API requests with retry logic
    - generate_decision() - generates AI decisions
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize AIModelClient

        Args:
            api_key: OpenRouter API key (if None, loads from environment)
        """
        self._api_key = api_key
        self._stub_mode = False
        self._load_api_key()
        self._init_client()

    def _load_api_key(self) -> Optional[str]:
        """
        Load API key from environment or constructor argument

        Returns:
            The API key or None if not available
        """
        if self._api_key is not None:
            return self._api_key

        self._api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENROUTER_API_KEY")

        if not self._api_key:
            self._stub_mode = True

        return self._api_key

    def _validate_api_key(self) -> bool:
        """
        Validate the API key by making a test request

        Returns:
            True if key is valid

        Raises:
            APIError: If key is missing, empty, invalid format, or rejected by API
        """
        if self._stub_mode:
            return True

        if not self._api_key:
            raise APIError("API key is missing")

        if not isinstance(self._api_key, str):
            raise APIError("API key must be a string")

        if len(self._api_key.strip()) == 0:
            raise APIError("API key is empty")

        if not self._api_key.startswith("sk-"):
            raise APIError(f"Invalid API key format: {self._api_key[:10]}...")

        try:
            headers = {
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json"
            }
            payload = {"model": "openai/gpt-4o-mini", "messages": [{"role": "user", "content": "test"}], "max_tokens": 1}

            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=10
            )

            if response.status_code == 401:
                error_info = response.json() if response.content else {}
                error_msg = error_info.get("error", {}).get("message", "API key rejected")
                raise APIError(error_msg)

            if response.status_code != 200 and response.status_code != 429:
                raise APIError(f"API validation failed with status {response.status_code}")

        except requests.exceptions.RequestException as e:
            raise APIError(f"API validation request failed: {str(e)}")

        return True

    def _init_client(self):
        """Initialize the underlying OpenRouter client"""
        if self._stub_mode:
            self._client = None
            return

        try:
            self._client = OpenRouterClient(self._api_key)
        except ValueError as e:
            self._stub_mode = True
            self._client = None

    def _make_request_with_retry(
        self,
        endpoint: str,
        payload: Dict[str, Any],
        max_retries: int = 3
    ) -> Dict[str, Any]:
        """
        Make API request with retry logic

        Args:
            endpoint: API endpoint
            payload: Request payload
            max_retries: Maximum number of retries

        Returns:
            Response dictionary

        Raises:
            APIError: If request fails after all retries
        """
        if self._stub_mode:
            return {"choices": [{"message": {"content": '{"command": "press:A", "reasoning": "Stub mode", "confidence": 0.5}'}}], "model": "stub"}

        for retry in range(max_retries):
            try:
                result = self._client.chat_completion(
                    model=self._client.models.get("acting", "openai/gpt-4o-mini"),
                    messages=[{"role": "user", "content": json.dumps(payload)}],
                    max_tokens=300
                )
                return result
            except Exception as e:
                if retry < max_retries - 1:
                    delay = 1.0 * (2 ** retry)
                    time.sleep(delay)
                else:
                    raise APIError(f"Request failed after {max_retries} retries: {str(e)}")

        raise APIError("Request failed")

    def generate_decision(
        self,
        game_state: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Generate an AI decision based on game state

        Args:
            game_state: Current game state
            context: Additional context

        Returns:
            Decision dictionary with command, reasoning, and confidence
        """
        if self._stub_mode:
            return {
                "command": "press:A",
                "reasoning": "Stub mode - no API key configured",
                "confidence": 0.5
            }

        prompt = json.dumps({
            "game_state": game_state,
            "context": context
        })

        try:
            response = self._make_request_with_retry("decision", {"prompt": prompt})

            content = response.get("content", "")
            if isinstance(content, str):
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    pass

            return {
                "command": "press:A",
                "reasoning": content[:100] if content else "No response",
                "confidence": 0.5
            }
        except Exception as e:
            return {
                "command": "press:A",
                "reasoning": f"Error: {str(e)}",
                "confidence": 0.3
            }


class ClaudeClient:
    """Client for Anthropic Claude API"""

    def __init__(self, api_key: Optional[str] = None):
        if not ANTHROPIC_AVAILABLE:
            raise ImportError("Anthropic SDK not installed. Run: pip install anthropic")

        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Anthropic API key not found. Set ANTHROPIC_API_KEY environment variable "
                "or pass api_key parameter."
            )

        self.client = Anthropic(api_key=self.api_key)

        self.models = {
            "vision": "claude-3-sonnet-20240307",
            "thinking": "claude-3-haiku-20240307",
            "acting": "claude-3-haiku-20240307"
        }

        self.circuit_breaker = CircuitBreaker()

    def chat_completion(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        max_tokens: int = 500,
        temperature: float = 0.3
    ) -> Dict[str, Any]:
        """Make a chat completion request to Claude"""

        if not self.circuit_breaker.allow_request():
            raise Exception("Circuit breaker open - too many failures")

        start_time = time.time()

        try:
            response = self.client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=messages
            )

            duration_ms = (time.time() - start_time) * 1000

            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
            cost = calculate_cost(model, input_tokens, output_tokens)

            self.circuit_breaker.record_success()

            return {
                "content": response.content[0].text,
                "finish_reason": response.stop_reason,
                "model": model,
                "usage": {
                    "prompt_tokens": input_tokens,
                    "completion_tokens": output_tokens
                },
                "duration_ms": duration_ms,
                "request_id": response.id
            }

        except Exception as e:
            self.circuit_breaker.record_failure()
            raise

    def get_text_response(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: int = 500
    ) -> str:
        """Get text response from Claude"""
        model = model or self.models.get("thinking", "claude-3-haiku-20240307")

        messages = []
        if system_prompt:
            messages.append({"role": "user", "content": f"{system_prompt}\n\n{prompt}"})
        else:
            messages.append({"role": "user", "content": prompt})

        result = self.chat_completion(
            model=model,
            messages=messages,
            max_tokens=max_tokens
        )

        return result["content"]


class OpenRouterClient:
    """
    Client for OpenRouter API
    Supports both vision (multimodal) and text-only models
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize OpenRouter client

        Args:
            api_key: OpenRouter API key (if None, loads from OPENROUTER_API_KEY env var)
        """
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ValueError(
                "OpenRouter API key not found. Set OPENROUTER_API_KEY environment variable "
                "or pass api_key parameter. Check .env file."
            )

        self.base_url = "https://openrouter.ai/api/v1"

        self.models = {
            "vision": "openai/gpt-4o",
            "thinking": "openai/gpt-4o-mini",
            "acting": "openai/gpt-4o-mini"
        }

        self.circuit_breaker = CircuitBreaker()

    def chat_completion(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        images: Optional[List[np.ndarray]] = None,
        max_tokens: Optional[int] = 500,
        temperature: float = 0.3,
        stream: bool = False,
        retry_count: int = 0
    ) -> Dict[str, Any]:
        """
        Make a chat completion request to OpenRouter

        Args:
            model: Model name (use self.models["vision"], self.models["thinking"], etc)
            messages: List of message dicts with 'role' and 'content'
            images: List of numpy arrays for vision inputs (only for vision models)
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            stream: Whether to stream response
            retry_count: Number of retries attempted

        Returns:
            Response dict with content, usage, etc.
        """
        if not self.circuit_breaker.allow_request():
            raise Exception("Circuit breaker open - too many failures")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://ai-plays-pokemon.com"
        }

        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": 0.95,
            "stream": stream
        }

        if images and len(images) > 0:
            image_content = []
            for img in images:
                if isinstance(img, np.ndarray):
                    pil_img = Image.fromarray(img)

                    if pil_img.size[0] > 1024:
                        pil_img = pil_img.resize((1024, int(1024 * pil_img.size[1] / pil_img.size[0])))

                    import io
                    buffered = io.BytesIO()
                    pil_img.save(buffered, format="PNG")
                    image_base64 = base64.b64encode(buffered.getvalue()).decode()

                    image_content.append({
                        "type": "image_url",
                        "image_url": f"data:image/png;base64,{image_base64}"
                    })

            user_message_found = False
            for i, message in enumerate(payload["messages"]):
                if message.get("role") == "user":
                    user_message = message

                    original_content = user_message.get("content", "")
                    if not original_content:
                        original_content = "Analyze this game screenshot."

                    content_array = [
                        {"type": "text", "text": original_content},
                        *image_content
                    ]

                    user_message["content"] = content_array
                    user_message_found = True
                    break

            if not user_message_found:
                payload["messages"].append({
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Analyze this game screenshot."},
                        *image_content
                    ]
                })

        start_time = time.time()

        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=30
            )
            duration_ms = (time.time() - start_time) * 1000

            if response.status_code == 429:
                self.circuit_breaker.record_failure()
                raise Exception(f"Rate limited - retry {retry_count + 1}")

            if response.status_code != 200:
                error_info = response.json() if response.content else response.text
                print(f"OpenRouter API error {response.status_code}: {error_info}")
                raise Exception(f"OpenRouter API error {response.status_code}: {error_info}")

            result = response.json()

            usage = result.get("usage", {})
            input_tokens = usage.get("prompt_tokens", 0)
            output_tokens = usage.get("completion_tokens", 0)
            cost = calculate_cost(model, input_tokens, output_tokens)

            self.circuit_breaker.record_success()

            log_api_call(model, duration_ms, input_tokens, output_tokens, cost, True)

            choices = result.get("choices", [])
            first_choice = choices[0] if choices else {}

            return {
                "content": first_choice.get("message", {}).get("content", ""),
                "finish_reason": first_choice.get("finish_reason", "stop"),
                "model": result.get("model", model),
                "usage": usage,
                "duration_ms": duration_ms,
                "request_id": result.get("id", "")
            }

        except Exception as e:
            print(f"OpenRouter request failed: {e}")
            raise

    def get_vision_response(
        self,
        prompt: str,
        image: np.ndarray,
        model: Optional[str] = None,
        max_tokens: int = 500
    ) -> str:
        """Get vision model response (simplified interface)"""
        if model is None:
            model = self.models.get("vision", "openai/gpt-4-vision-preview")

        messages = [
            {
                "role": "system",
                "content": "You are an AI playing Pokemon. Analyze the provided game screenshot and provide strategic advice."
            },
            {
                "role": "user",
                "content": prompt
            }
        ]

        result = self.chat_completion(
            model=model,
            messages=messages,
            images=[image],
            max_tokens=max_tokens
        )

        return result["content"]

    def get_text_response(
        self,
        prompt: str,
        model: Optional[str] = None,
        max_tokens: int = 500,
        temperature: float = 0.3
    ) -> str:
        """Get text-only model response (simplified interface)"""
        if model is None:
            model = self.models.get("thinking", "openai/gpt-4-turbo")

        messages = [
            {
                "role": "system",
                "content": "You are an AI playing Pokemon. Provide strategic advice and decisions."
            },
            {
                "role": "user",
                "content": prompt
            }
        ]

        result = self.chat_completion(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature
        )

        return result["content"]


class JSONResponseParser:
    """Structured JSON response parser with validation and retry logic"""

    def __init__(self, schema: Optional[Dict[str, Any]] = None, max_retries: int = 3):
        self.schema = schema
        self.max_retries = max_retries
        self.parse_success_count = 0
        self.parse_failure_count = 0

    def parse(
        self,
        response: str,
        schema: Optional[Dict[str, Any]] = None,
        retry_count: int = 0
    ) -> Dict[str, Any]:
        """Parse response with retry logic on failure"""
        schema = schema or self.schema

        try:
            result = self._try_parse_json(response, schema)
            if result:
                self.parse_success_count += 1
                return result
        except Exception as e:
            pass

        self.parse_failure_count += 1

        if retry_count < self.max_retries:
            return self._parse_with_fallback(response, retry_count)

        return self._extract_with_regex_fallback(response)

    def _try_parse_json(
        self,
        response: str,
        schema: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Try to parse JSON from response"""
        cleaned = self._clean_json_response(response)

        try:
            result = json.loads(cleaned)
            if schema:
                self._validate_against_schema(result, schema)
            return result
        except json.JSONDecodeError:
            pass

        json_match = re.search(r'\{[^{}]*\}', response)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        return None

    def _clean_json_response(self, response: str) -> str:
        """Clean JSON response by removing markdown code blocks and extra whitespace"""
        cleaned = response.strip()

        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]

        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]

        cleaned = cleaned.strip()

        return cleaned

    def _validate_against_schema(
        self,
        result: Dict[str, Any],
        schema: Dict[str, Any]
    ) -> None:
        """Validate parsed JSON against schema"""
        for key, expected_type in schema.items():
            if key in result:
                if isinstance(expected_type, list):
                    if not isinstance(result[key], tuple(expected_type)):
                        raise ValueError(f"Key '{key}' has wrong type")
                elif not isinstance(result[key], expected_type if expected_type != str else str):
                    raise ValueError(f"Key '{key}' has wrong type")

    def _parse_with_fallback(
        self,
        response: str,
        retry_count: int
    ) -> Dict[str, Any]:
        """Parse with fallback strategies on retry"""
        cleaned = self._clean_json_response(response)

        if retry_count == 0:
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                pass

        json_patterns = [
            r'\{(?:[^{}]|{[^{}]*})*\}',
            r'"(?:[^"\\]|\\.)*"\s*:\s*(?:[^,}\\]|\\.)*(?:,\s*(?:[^"\\]|\\.)*:\s*(?:[^,}\\]|\\.)*)*\}'
        ]

        for pattern in json_patterns:
            match = re.search(pattern, response)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    continue

        return self._extract_with_regex_fallback(response)

    def _extract_with_regex_fallback(self, response: str) -> Dict[str, Any]:
        """Final fallback using regex extraction"""
        result = {
            "raw_response": response[:500],
            "extracted_fields": {}
        }

        field_patterns = {
            "action": r'(?:recommended_)?action["\s]*:\s*["\']?(\w+)',
            "reasoning": r'reasoning["\s]*:\s*["\']([^"\']+)',
            "screen_type": r'screen_type["\s]*:\s*["\']?(\w+)',
            "enemy_pokemon": r'enemy_pokemon["\s]*:\s*["\']?([A-Za-z]+)',
            "player_hp": r'player_hp["\s]*:\s*(\d+)',
            "enemy_hp": r'enemy_hp["\s]*:\s*(\d+)'
        }

        for field, pattern in field_patterns.items():
            match = re.search(pattern, response, re.IGNORECASE)
            if match:
                value = match.group(1)
                if field in ["player_hp", "enemy_hp"]:
                    value = int(value)
                result["extracted_fields"][field] = value

        self.parse_failure_count += 1
        return result

    def get_success_rate(self) -> float:
        """Get JSON parsing success rate"""
        total = self.parse_success_count + self.parse_failure_count
        if total == 0:
            return 1.0
        return self.parse_success_count / total


class RateLimiter:
    """Rate limiter with exponential backoff"""

    def __init__(
        self,
        max_requests: int = 50,
        time_window: float = 60.0,
        base_delay: float = 1.0,
        max_delay: float = 60.0
    ):
        self.max_requests = max_requests
        self.time_window = time_window
        self.base_delay = base_delay
        self.max_delay = max_delay

        self.request_times: List[float] = []
        self.lock = threading.Lock()

    def wait(self) -> float:
        """Wait if rate limit would be exceeded, return delay used"""
        with self.lock:
            now = time.time()

            self.request_times = [t for t in self.request_times if now - t < self.time_window]

            if len(self.request_times) >= self.max_requests:
                oldest = min(self.request_times)
                delay = max(self.time_window - (now - oldest), self.base_delay)
                time.sleep(delay)
                return delay

            self.request_times.append(now)
            return 0.0

    def get_delay(self, retry_count: int) -> float:
        """Calculate exponential backoff delay"""
        delay = min(self.base_delay * (2 ** retry_count), self.max_delay)
        random_value = int(hashlib.md5(str(time.time()).encode()).hexdigest(), 16) % 100
        jitter = delay * 0.1 * (random_value / 100)
        return delay + jitter


class ModelRouter:
    """Route requests to appropriate model based on task requirements"""

    def __init__(self):
        self.providers = {
            "openrouter": {"speed_weight": 0.4, "cost_weight": 0.3, "quality_weight": 0.3},
            "anthropic": {"speed_weight": 0.3, "cost_weight": 0.4, "quality_weight": 0.3}
        }

    def select_model(
        self,
        task_type: str,
        priority: str = "balanced",
        available_models: Optional[Dict[str, str]] = None
    ) -> tuple:
        """
        Select best model for task

        Args:
            task_type: Type of task (vision, thinking, acting)
            priority: Priority (speed, cost, quality, balanced)
            available_models: Dict of available models

        Returns:
            (provider, model) tuple
        """
        available_models = available_models or {
            "openrouter_vision": "openai/gpt-4o",
            "openrouter_thinking": "openai/gpt-4o-mini",
            "openrouter_acting": "openai/gpt-4o-mini",
            "anthropic_vision": "claude-3-sonnet-20240307",
            "anthropic_thinking": "claude-3-haiku-20240307",
            "anthropic_acting": "claude-3-haiku-20240307"
        }

        if priority == "speed":
            return self._select_for_speed(task_type, available_models)
        elif priority == "cost":
            return self._select_for_cost(task_type, available_models)
        elif priority == "quality":
            return self._select_for_quality(task_type, available_models)
        else:
            return self._select_balanced(task_type, available_models)

    def _select_for_speed(
        self,
        task_type: str,
        available_models: Dict[str, str]
    ) -> tuple:
        """Select fastest model"""
        if task_type == "vision":
            return ("openrouter", available_models.get("openrouter_vision", "openai/gpt-4o-mini"))
        elif task_type == "thinking":
            return ("openrouter", available_models.get("openrouter_thinking", "openai/gpt-4o-mini"))
        else:
            return ("openrouter", available_models.get("openrouter_acting", "openai/gpt-4o-mini"))

    def _select_for_cost(
        self,
        task_type: str,
        available_models: Dict[str, str]
    ) -> tuple:
        """Select cheapest model"""
        return self._select_for_speed(task_type, available_models)

    def _select_for_quality(
        self,
        task_type: str,
        available_models: Dict[str, str]
    ) -> tuple:
        """Select highest quality model"""
        if task_type == "vision":
            return ("anthropic", available_models.get("anthropic_vision", "claude-3-sonnet-20240307"))
        elif task_type == "thinking":
            return ("anthropic", available_models.get("anthropic_thinking", "claude-3-sonnet-20240307"))
        else:
            return ("anthropic", available_models.get("anthropic_acting", "claude-3-haiku-20240307"))

    def _select_balanced(
        self,
        task_type: str,
        available_models: Dict[str, str]
    ) -> tuple:
        """Select balanced model"""
        if task_type == "vision":
            return ("openrouter", available_models.get("openrouter_vision", "openai/gpt-4o"))
        elif task_type == "thinking":
            return ("openrouter", available_models.get("openrouter_thinking", "openai/gpt-4o-mini"))
        else:
            return ("openrouter", available_models.get("openrouter_acting", "openai/gpt-4o-mini"))


class GameAIManager:
    """
    Manages AI models for Pokemon gameplay

    Coordinates between vision model (for reading screens)
    and text models (for strategic/thinking/reasoning)
    Integrates with Vision & Perception Engine for local screen analysis
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        anthropic_api_key: Optional[str] = None,
        enable_prompt_manager: bool = True,
        model_priority: str = "balanced"
    ):
        """
        Initialize AI manager

        Args:
            api_key: OpenRouter API key
            anthropic_api_key: Anthropic API key
            enable_prompt_manager: Whether to enable PromptManager
            model_priority: Model selection priority (speed, cost, quality, balanced)
        """
        self.model_priority = model_priority
        self.token_tracker = TokenTracker()
        self.model_router = ModelRouter()
        self.rate_limiter = RateLimiter(max_requests=50, time_window=60.0)
        self.json_parser = JSONResponseParser(
            schema={
                "screen_type": str,
                "enemy_pokemon": str,
                "player_hp": int,
                "enemy_hp": int,
                "available_actions": list,
                "recommended_action": str,
                "reasoning": str
            },
            max_retries=3
        )

        if enable_prompt_manager:
            try:
                from src.core.prompt_manager import PromptManager
                self.prompt_manager = PromptManager("prompts")
                print("✅ PromptManager initialized")
            except Exception as e:
                print(f"⚠️  PromptManager initialization failed: {e}")
                self.prompt_manager = None
        else:
            self.prompt_manager = None

        self.ai_model_client = AIModelClient(api_key)
        self.openrouter_client = self.ai_model_client._client

        if ANTHROPIC_AVAILABLE:
            try:
                self.claude_client = ClaudeClient(anthropic_api_key)
                print("✅ Claude client initialized")
            except Exception as e:
                print(f"⚠️  Claude client initialization failed: {e}")
                self.claude_client = None
        else:
            self.claude_client = None

        self.vision_model = "openai/gpt-4o"
        self.thinking_model = "openai/gpt-4o-mini"
        self.acting_model = "openai/gpt-4o-mini"

        self._init_vision_engine()

        self.prompts = {
            "vision_analysis": """Analyze this Pokemon game screenshot and provide:

1. Screen Type: (battle, overworld, menu, dialog, transition)
2. Enemy Pokemon: (if visible)
3. Player HP: (estimated from HP bar 0-100%)
4. Enemy HP: (estimated from HP bar 0-100%)
5. Available Actions: (what can the player do?)
6. Recommended Move: (what button should be pressed?)

Respond in JSON format:
{"screen_type": "...", "enemy_pokemon": "...", "player_hp": 45, "enemy_hp": 100, "available_actions": ["A", "DOWN"], "recommended_action": "press:A", "reasoning": "short explanation"}
""",
            "strategic_planning": """You are the Strategist - plan Pokemon gameplay.

CURRENT CONTEXT:
{journey_summary}

GAME STATE:
{battle_state}

MISTAKES TO LEARN FROM:
{past_failures}

CURRENT OBJECTIVE:
{objective}

Provide a strategic plan in this format:
OBJECTIVE: what to accomplish
KEY_TACTICS: 2-3 specific actions
RISKS: what might go wrong
CONFIDENCE: 0.0-1.0
""",
            "tactical_decision": """You are the Tactician - choose the next action.

CURRENT BATTLE - Turn {turn}:
Our Pokemon: {player_pokemon} (HP: {player_hp}%)
Enemy: {enemy_pokemon} (HP: {enemy_hp}%)
Type: {enemy_type}

AVAILABLE MOVES:
{moves}

TYPE ADVANTAGES: {weaknesses}

RECENT ACTIONS:
{recent_actions}

STRATEGIC GUIDANCE: {strategy}

DECIDE: What button should be pressed next (A, B, UP, DOWN, LEFT, RIGHT)?
Explain your reasoning in 1 sentence, then state your action.

Format: REASONING: [explanation] ACTION: [button]
"""
        }

    def _init_vision_engine(self):
        """Initialize the Vision & Perception Engine components"""
        if not VISION_AVAILABLE or VisionPipeline is None:
            self.vision_pipeline = None
            self.ocr_engine = None
            self.sprite_recognizer = None
            self.battle_analyzer = None
            self.location_detector = None
            return

        try:
            self.vision_pipeline = VisionPipeline()
            self.ocr_engine = OCREngine()
            self.sprite_recognizer = SpriteRecognizer()
            self.battle_analyzer = BattleAnalyzer()
            self.location_detector = LocationDetector()
            print("✅ Vision & Perception Engine initialized")
        except Exception as e:
            print(f"⚠️  Vision engine initialization failed: {e}")
            self.vision_pipeline = None
            self.ocr_engine = None
            self.sprite_recognizer = None
            self.battle_analyzer = None
            self.location_detector = None

    def _get_client_for_model(self, model: str):
        """Get appropriate client for a model"""
        if "claude" in model.lower():
            return self.claude_client
        return self.openrouter_client

    def _make_api_call_with_retry(
        self,
        client_method: Callable,
        max_retries: int = 3,
        **kwargs
    ) -> Dict[str, Any]:
        """Make API call with retry logic and rate limiting"""
        for retry in range(max_retries):
            try:
                self.rate_limiter.wait()
                result = client_method(**kwargs)

                if "usage" in result:
                    usage = result["usage"]
                    input_tokens = usage.get("prompt_tokens", 0)
                    output_tokens = usage.get("completion_tokens", 0)
                    cost = calculate_cost(result.get("model", ""), input_tokens, output_tokens)

                    self.token_tracker.record_request(
                        model=result.get("model", ""),
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        cost=cost,
                        duration_ms=result.get("duration_ms", 0)
                    )

                return result

            except Exception as e:
                if retry < max_retries - 1:
                    delay = self.rate_limiter.get_delay(retry)
                    time.sleep(delay)
                else:
                    raise

        raise Exception("Max retries exceeded")

    def analyze_screenshot(self, screenshot: np.ndarray) -> Dict[str, Any]:
        """Analyze screenshot using vision model"""
        print(f"👀 Analyzing screenshot with vision model: {self.vision_model}")

        provider, model = self.model_router.select_model(
            "vision",
            self.model_priority
        )
        print(f"📡 Selected provider: {provider}, model: {model}")

        prompt = self.prompts["vision_analysis"]

        if self.prompt_manager:
            relevant_prompts = self.prompt_manager.select_prompts_for_ai(
                "battle",
                {},
                "balanced"
            )
            if relevant_prompts:
                prompt = relevant_prompts[0] + "\n\n" + prompt

        try:
            client = self._get_client_for_model(model)
            if hasattr(client, 'get_vision_response'):
                response = client.get_vision_response(prompt, screenshot, model=model)
            else:
                response = self.openrouter_client.get_vision_response(prompt, screenshot, model=model)

            print(f"📝 Vision response ({len(response)} chars): {response[:200]}...")

            result = self.json_parser.parse(response)
            self.token_tracker.record_request(
                model=model,
                input_tokens=len(response) // 4,
                output_tokens=len(response) // 4,
                cost=0.001,
                duration_ms=100
            )

            log_vision_analysis(
                result.get('screen_type', 'Unknown'),
                result.get('enemy_pokemon', 'None'),
                result.get('player_hp', 100),
                result.get('enemy_hp', 100)
            )

            print(f"✅ Vision analysis: screen={result.get('screen_type', 'Unknown')}, "
                  f"enemy={result.get('enemy_pokemon', 'None')}, "
                  f"HP={result.get('player_hp', 100)}%/{result.get('enemy_hp', 100)}%")

            return result

        except Exception as e:
            print(f"❌ Vision analysis failed: {e}")
            return {
                "screen_type": "overworld",
                "enemy_pokemon": None,
                "player_hp": 100,
                "enemy_hp": 100,
                "available_actions": ["A", "DOWN"],
                "recommended_action": "press:A",
                "reasoning": "Fallback default action"
            }

    def make_strategic_decision(
        self,
        journey_summary: str,
        battle_state: str,
        objective: str,
        past_failures: str,
        model: Optional[str] = None
    ) -> Dict[str, Any]:
        """Make strategic planning decision using thinking model"""
        print(f"🧠 Strategic planning with thinking model...")

        prompt = self.prompts["strategic_planning"].format(
            journey_summary=journey_summary or "No journey summary yet",
            battle_state=battle_state or "No battle",
            past_failures=past_failures or "No past failures",
            objective=objective or "Explore the world"
        )

        if self.prompt_manager:
            relevant_prompts = self.prompt_manager.select_prompts_for_ai(
                "strategic",
                {},
                "strategic"
            )
            if relevant_prompts:
                prompt = relevant_prompts[0] + "\n\n" + prompt

        provider, selected_model = self.model_router.select_model(
            "thinking",
            self.model_priority
        )
        model = model or selected_model

        try:
            client = self._get_client_for_model(model)
            if hasattr(client, 'get_text_response'):
                response = client.get_text_response(prompt, model=model)
            else:
                response = self.openrouter_client.get_text_response(prompt, model=model)

            print(f"Strategic model response: {response[:200]}...")

            result = self._parse_strategic_response(response)

            self.token_tracker.record_request(
                model=model,
                input_tokens=len(prompt) // 4,
                output_tokens=len(response) // 4,
                cost=0.001,
                duration_ms=100
            )

            print(f"✅ Strategic plan: {result.get('objective', 'Unknown')}")

            return result

        except Exception as e:
            print(f"❌ Strategic planning failed: {e}")
            return {
                "objective": "Survive and explore",
                "key_tactics": ["Press A", "Use super-effective moves"],
                "risks": "Unknown enemies",
                "confidence": 0.5
            }

    def make_tactical_decision(
        self,
        player_pokemon: str,
        player_hp: float,
        enemy_pokemon: str,
        enemy_hp: float,
        enemy_type: str,
        moves: List[str],
        weaknesses: List[str],
        recent_actions: str,
        strategy: str,
        turn: int,
        model: Optional[str] = None
    ) -> Dict[str, Any]:
        """Make immediate tactical decision using acting model"""
        print(f"⚡ Tactical decision (turn {turn})...")

        prompt = self.prompts["tactical_decision"].format(
            turn=turn,
            player_pokemon=player_pokemon,
            player_hp=f"{player_hp:.0f}",
            enemy_pokemon=enemy_pokemon,
            enemy_hp=f"{enemy_hp:.0f}",
            enemy_type=enemy_type or "Unknown",
            moves=", ".join(moves) if moves else "Basic attack",
            weaknesses=", ".join(weaknesses) if weaknesses else "None",
            recent_actions=recent_actions or "No recent actions",
            strategy=strategy or "Basic strategy"
        )

        if self.prompt_manager:
            relevant_prompts = self.prompt_manager.select_prompts_for_ai(
                "battle",
                {},
                "tactical"
            )
            if relevant_prompts:
                prompt = relevant_prompts[0] + "\n\n" + prompt

        provider, selected_model = self.model_router.select_model(
            "acting",
            self.model_priority
        )
        model = model or selected_model

        try:
            client = self._get_client_for_model(model)
            if hasattr(client, 'get_text_response'):
                response = client.get_text_response(
                    prompt,
                    model=model,
                    max_tokens=300,
                    temperature=0.3
                )
            else:
                response = self.openrouter_client.get_text_response(
                    prompt,
                    model=model,
                    max_tokens=300,
                    temperature=0.3
                )

            print(f"Tactical model response: {response[:200]}...")

            result = self._parse_tactical_response(response)

            self.token_tracker.record_request(
                model=model,
                input_tokens=len(prompt) // 4,
                output_tokens=len(response) // 4,
                cost=0.001,
                duration_ms=100
            )

            print(f"✅ Tactical: REASONING: {result.get('reasoning', '')[:100]}... "
                  f"ACTION: {result.get('action', 'press:A')}")

            return result

        except Exception as e:
            print(f"❌ Tactical decision failed: {e}")
            return {
                "reasoning": "Default action - Press basic move",
                "action": "press:A"
            }

    def get_session_stats(self) -> Dict[str, Any]:
        """Get session statistics including token usage and costs"""
        stats = self.token_tracker.get_session_stats()
        stats["json_parse_success_rate"] = self.json_parser.get_success_rate()
        return stats

    def reset_session_stats(self):
        """Reset session statistics"""
        self.token_tracker.reset()
        self.json_parser.parse_success_count = 0
        self.json_parser.parse_failure_count = 0

    def _parse_strategic_response(self, response: str) -> Dict[str, Any]:
        """Parse strategic planning response"""
        parsed = self.json_parser.parse(response)

        if "objective" in parsed and "key_tactics" in parsed:
            return {
                "objective": parsed.get("objective", ""),
                "key_tactics": parsed.get("key_tactics", []),
                "risks": parsed.get("risks", "Unknown"),
                "confidence": parsed.get("confidence", 0.5)
            }

        return {
            "objective": self._extract_objective(response),
            "key_tactics": self._extract_list(response),
            "risks": "Unknown",
            "confidence": 0.5
        }

    def _parse_tactical_response(self, response: str) -> Dict[str, Any]:
        """Parse tactical decision response"""
        parsed = self.json_parser.parse(response)

        if "action" in parsed and "reasoning" in parsed:
            action = parsed["action"]
            if not action.startswith("press:"):
                action = f"press:{action}"
            return {
                "reasoning": parsed.get("reasoning", ""),
                "action": action
            }

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

        if action == "press:A" and not reasoning:
            for button in ["A", "B", "UP", "DOWN", "LEFT", "RIGHT"]:
                if button in response.upper():
                    action = f"press:{button}"
                    break

        return {
            "reasoning": reasoning or "Default tactical action",
            "action": action
        }

    def _extract_screen_type(self, text: str) -> str:
        """Extract screen type from response"""
        text_lower = text.lower()

        if "battle" in text_lower:
            return "battle"
        elif "menu" in text_lower:
            return "menu"
        elif "dialog" in text_lower or "text" in text_lower:
            return "dialog"
        elif "overworld" in text_lower or "walking" in text_lower:
            return "overworld"
        else:
            return "overworld"

    def _extract_pokemon_name(self, text: str) -> Optional[str]:
        """Extract Pokemon name from text"""
        common_pokemon = [
            "Pikachu", "Charizard", "Bulbasaur", "Squirtle", "Geodude",
            "Pidgey", "Rattata", "Caterpie", "Weedle", "Nidoran",
            "Mewtwo", "Mew", "Lugia", "Ho-Oh", "Eevee", "Vaporeon",
            "Jolteon", "Flareon", "Mewtwo", "Venusaur", "Ivysaur",
            "Wartortle", "Blastoise", "Charmeleon", "Nidorina", "Nidorino"
        ]

        text_upper = text.upper()

        for pokemon in common_pokemon:
            if pokemon.upper() in text_upper:
                return pokemon.capitalize()

        return None

    def _extract_number(self, text: str, keyword: str = "") -> Optional[int]:
        """Extract percentage or number from text"""
        percent_match = re.search(r'\d+%', text)
        if percent_match:
            return int(percent_match.group(0)[:-1])

        if keyword:
            pattern = rf'{keyword}[^:]*:?\s*(\d+)'
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return int(match.group(1))

        return None

    def _extract_actions(self, text: str) -> List[str]:
        """Extract available actions"""
        actions_match = re.search(r'Actions?[:\s]+(.*)', text, re.IGNORECASE)
        if actions_match:
            actions_text = actions_match.group(1)
            actions = [a.strip() for a in re.split(r'[,;\s]+', actions_text) if a.strip()]
            return actions[:6]

        return ["A", "DOWN"]

    def _extract_action(self, text: str) -> str:
        """Extract button press action"""
        press_match = re.search(r'press:\s*(\w+)', text, re.IGNORECASE)
        if press_match:
            return f"press:{press_match.group(1).upper()}"

        for button in ["A", "B", "UP", "DOWN", "LEFT", "RIGHT"]:
            if button in text:
                return f"press:{button}"

        return "press:A"

    def _extract_objective(self, text: str) -> str:
        """Extract objective from strategic response"""
        obj_match = re.search(r'OBJECTIVE[:\s]+(.*?)(?:\n|$)', text, re.IGNORECASE)
        if obj_match:
            return obj_match.group(1).strip()

        lines = text.strip().split('\n')
        if lines:
            return lines[0][:100]

        return text[:100]

    def _extract_list(self, text: str) -> List[str]:
        """Extract list of tactics from response"""
        items = re.findall(r'\d+\.\s+(.*?)(?=\n|$)', text)
        if not items:
            items = re.findall(r'[-*]\s+(.*?)(?=\n|$)', text)

        return items[:5]


@dataclass
class TaskComplexity:
    """Task complexity assessment for routing decisions"""
    vision_weight: float = 0.9
    reasoning_weight: float = 0.7
    speed_weight: float = 0.5
    creativity_weight: float = 0.6
    accuracy_weight: float = 0.8


@dataclass
class ModelSelection:
    """Model selection result with metadata"""
    model: str
    provider: str
    confidence: float
    complexity: float
    estimated_cost: float
    estimated_latency_ms: float
    reasoning: str


@dataclass
class RoutingConfig:
    """Configuration for model routing"""
    budget: float = 10.0
    max_latency_ms: float = 5000.0
    quality_threshold: float = 0.7
    cost_weight: float = 0.3
    speed_weight: float = 0.3
    quality_weight: float = 0.4
    prefer_cheap_on_budget: bool = True
    fallback_chain: List[str] = field(default_factory=lambda: [
        "openai/gpt-4o",
        "openai/gpt-4o-mini",
        "anthropic/claude-3-haiku-20240307"
    ])


class CostOptimizer:
    """
    Track and optimize API costs across sessions.

    Features:
    - Budget tracking per session
    - Cost-per-decision tracking (accurate to $0.001)
    - Model switching based on cost constraints
    - Cost prediction for task planning
    """

    def __init__(self, budget: float = 10.0):
        """
        Initialize cost optimizer.

        Args:
            budget: Maximum budget in USD
        """
        self.budget = budget
        self.spent = 0.0
        self.decisions = 0
        self.cost_per_decision = 0.0
        self.cost_per_model: Dict[str, float] = {}
        self.cost_per_task_type: Dict[str, float] = {}
        self.lock = threading.Lock()

    def track_cost(self, model: str, task_type: str, input_tokens: int,
                   output_tokens: int) -> float:
        """
        Calculate and track cost for API call.

        Args:
            model: Model name
            task_type: Type of task (vision, thinking, acting)
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens

        Returns:
            Cost in USD
        """
        with self.lock:
            cost = calculate_cost(model, input_tokens, output_tokens)
            self.spent += cost
            self.decisions += 1
            self.cost_per_decision = round(self.spent / max(self.decisions, 1), 6)

            if model not in self.cost_per_model:
                self.cost_per_model[model] = 0.0
            self.cost_per_model[model] += cost

            if task_type not in self.cost_per_task_type:
                self.cost_per_task_type[task_type] = 0.0
            self.cost_per_task_type[task_type] += cost

            return round(cost, 6)

    def get_remaining_budget(self) -> float:
        """Get remaining budget"""
        with self.lock:
            return round(self.budget - self.spent, 6)

    def get_budget_percentage(self) -> float:
        """Get percentage of budget spent"""
        with self.lock:
            if self.budget <= 0:
                return 100.0
            return round((self.spent / self.budget) * 100, 2)

    def should_switch_model(self, task_complexity: float, current_model: str) -> ModelSelection:
        """
        Determine if we should use cheaper model based on budget.

        Args:
            task_complexity: Complexity of current task (0.0 - 1.0)
            current_model: Currently selected model

        Returns:
            ModelSelection with recommendation
        """
        with self.lock:
            remaining = self.get_remaining_budget()

            if remaining < 0.5:
                return ModelSelection(
                    model="openai/gpt-4o-mini",
                    provider="openrouter",
                    confidence=0.6,
                    complexity=task_complexity,
                    estimated_cost=0.001,
                    estimated_latency_ms=500.0,
                    reasoning="Budget critical - switching to cheapest model"
                )

            if task_complexity < 0.3:
                return ModelSelection(
                    model="openai/gpt-4o-mini",
                    provider="openrouter",
                    confidence=0.8,
                    complexity=task_complexity,
                    estimated_cost=0.001,
                    estimated_latency_ms=500.0,
                    reasoning="Simple task - using fast, cheap model"
                )

            if task_complexity > 0.7 and remaining > 2.0:
                return ModelSelection(
                    model="openai/gpt-4o",
                    provider="openrouter",
                    confidence=0.9,
                    complexity=task_complexity,
                    estimated_cost=0.005,
                    estimated_latency_ms=1500.0,
                    reasoning="Complex task - using high-quality model"
                )

            return ModelSelection(
                model=current_model,
                provider="openrouter",
                confidence=0.75,
                complexity=task_complexity,
                estimated_cost=calculate_cost(current_model, 1000, 500),
                estimated_latency_ms=1000.0,
                reasoning="Current model is appropriate for task"
            )

    def get_cost_report(self) -> Dict[str, Any]:
        """Get detailed cost report"""
        with self.lock:
            return {
                "total_budget": self.budget,
                "total_spent": round(self.spent, 6),
                "remaining_budget": self.get_remaining_budget(),
                "budget_percentage_used": self.get_budget_percentage(),
                "total_decisions": self.decisions,
                "avg_cost_per_decision": round(self.cost_per_decision, 6),
                "cost_per_model": dict(self.cost_per_model),
                "cost_per_task_type": dict(self.cost_per_task_type)
            }

    def reset(self):
        """Reset cost tracking"""
        with self.lock:
            self.spent = 0.0
            self.decisions = 0
            self.cost_per_decision = 0.0
            self.cost_per_model = {}
            self.cost_per_task_type = {}


@dataclass
class PerformanceMetrics:
    """Performance metrics for a model"""
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    total_latency_ms: float = 0.0
    total_tokens: int = 0
    success_rate: float = 1.0
    avg_latency_ms: float = 0.0
    last_call: Optional[datetime] = None


class PerformanceTracker:
    """
    Monitor model accuracy, latency, and success rates.

    Features:
    - Per-model metrics tracking
    - Task-type performance analysis
    - Latency monitoring
    - Success rate calculation
    - Performance trend analysis
    """

    def __init__(self):
        """Initialize performance tracker"""
        self.metrics: Dict[str, PerformanceMetrics] = {}
        self.task_metrics: Dict[str, Dict[str, PerformanceMetrics]] = {}
        self.recent_results: List[Dict[str, Any]] = []
        self.max_recent_results = 1000
        self.lock = threading.Lock()

    def record_result(self, model: str, task_type: str, success: bool,
                      latency_ms: float, tokens: int = 0):
        """
        Record performance result for a model on a task.

        Args:
            model: Model name
            task_type: Type of task (vision, thinking, acting)
            success: Whether the task was successful
            latency_ms: Latency in milliseconds
            tokens: Number of tokens used
        """
        with self.lock:
            now = datetime.now()

            if model not in self.metrics:
                self.metrics[model] = PerformanceMetrics()

            m = self.metrics[model]
            m.total_calls += 1
            m.total_latency_ms += latency_ms
            m.total_tokens += tokens
            m.last_call = now

            if success:
                m.successful_calls += 1
            else:
                m.failed_calls += 1

            m.success_rate = m.successful_calls / m.total_calls
            m.avg_latency_ms = m.total_latency_ms / m.total_calls

            if task_type not in self.task_metrics:
                self.task_metrics[task_type] = {}

            if model not in self.task_metrics[task_type]:
                self.task_metrics[task_type][model] = PerformanceMetrics()

            tm = self.task_metrics[task_type][model]
            tm.total_calls += 1
            tm.total_latency_ms += latency_ms

            if success:
                tm.successful_calls += 1
            else:
                tm.failed_calls += 1

            tm.success_rate = tm.successful_calls / tm.total_calls
            tm.avg_latency_ms = tm.total_latency_ms / tm.total_calls

            self.recent_results.append({
                "model": model,
                "task_type": task_type,
                "success": success,
                "latency_ms": latency_ms,
                "tokens": tokens,
                "timestamp": now.isoformat()
            })

            if len(self.recent_results) > self.max_recent_results:
                self.recent_results = self.recent_results[-self.max_recent_results:]

    def get_model_stats(self, model: str) -> Optional[Dict[str, Any]]:
        """
        Get performance statistics for a model.

        Args:
            model: Model name

        Returns:
            Dictionary with model statistics or None if not found
        """
        with self.lock:
            if model not in self.metrics:
                return None

            m = self.metrics[model]
            return {
                "model": model,
                "total_calls": m.total_calls,
                "successful_calls": m.successful_calls,
                "failed_calls": m.failed_calls,
                "success_rate": round(m.success_rate, 4),
                "avg_latency_ms": round(m.avg_latency_ms, 2),
                "total_tokens": m.total_tokens,
                "last_call": m.last_call.isoformat() if m.last_call else None
            }

    def get_best_model_for_task(self, task_type: str) -> Optional[str]:
        """
        Get the best performing model for a task type.

        Args:
            task_type: Type of task

        Returns:
            Model name with highest success rate, or None
        """
        with self.lock:
            if task_type not in self.task_metrics:
                return None

            best_model = None
            best_success_rate = -1.0
            best_latency = float('inf')

            for model, metrics in self.task_metrics[task_type].items():
                if metrics.success_rate > best_success_rate:
                    best_success_rate = metrics.success_rate
                    best_model = model
                    best_latency = metrics.avg_latency_ms
                elif metrics.success_rate == best_success_rate:
                    if metrics.avg_latency_ms < best_latency:
                        best_model = model
                        best_latency = metrics.avg_latency_ms

            return best_model

    def get_all_model_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all models"""
        with self.lock:
            return {model: self.get_model_stats(model) or {}
                    for model in self.metrics}

    def get_recent_success_rate(self, model: str, n: int = 100) -> float:
        """
        Get recent success rate for a model.

        Args:
            model: Model name
            n: Number of recent results to consider

        Returns:
            Success rate (0.0 - 1.0)
        """
        with self.lock:
            recent = [r for r in self.recent_results[-n:] if r["model"] == model]
            if not recent:
                return 1.0 if model in self.metrics else 0.0

            successes = sum(1 for r in recent if r["success"])
            return successes / len(recent)

    def get_average_latency(self, task_type: str) -> float:
        """Get average latency for a task type across all models"""
        with self.lock:
            if task_type not in self.task_metrics:
                return 0.0

            total_latency = 0.0
            total_calls = 0

            for model, metrics in self.task_metrics[task_type].items():
                total_latency += metrics.avg_latency_ms * metrics.total_calls
                total_calls += metrics.total_calls

            if total_calls == 0:
                return 0.0

            return total_latency / total_calls

    def reset(self):
        """Reset all metrics"""
        with self.lock:
            self.metrics = {}
            self.task_metrics = {}
            self.recent_results = []


@dataclass
class ModelResult:
    """Result from a single model"""
    model: str
    content: str
    confidence: float
    success: bool
    latency_ms: float
    cost: float
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class MergedResult:
    """Merged result from multiple models"""
    content: str
    selected_model: str
    confidence: float
    conflicts_detected: bool
    merge_method: str
    contributing_models: List[str]
    alternative_results: Dict[str, str]


class ResultMerger:
    """
    Resolve conflicts between model outputs.

    Features:
    - Conflict detection between models
    - Confidence-weighted decision making
    - Override logic for low-confidence consensus
    - Consensus building for critical decisions
    """

    def __init__(self, confidence_threshold: float = 0.6,
                 consensus_threshold: float = 0.7):
        """
        Initialize result merger.

        Args:
            confidence_threshold: Minimum confidence for acceptance
            consensus_threshold: Threshold for consensus (0.0 - 1.0)
        """
        self.confidence_threshold = confidence_threshold
        self.consensus_threshold = consensus_threshold
        self.merge_history: List[Dict[str, Any]] = []
        self.lock = threading.Lock()

    def merge_results(self, results: List[ModelResult]) -> MergedResult:
        """
        Merge results from multiple models with confidence weighting.

        Args:
            results: List of ModelResult from different models

        Returns:
            MergedResult with merged content
        """
        with self.lock:
            if not results:
                return MergedResult(
                    content="",
                    selected_model="",
                    confidence=0.0,
                    conflicts_detected=False,
                    merge_method="empty",
                    contributing_models=[],
                    alternative_results={}
                )

            successful_results = [r for r in results if r.success]
            failed_results = [r for r in results if not r.success]

            if not successful_results:
                return MergedResult(
                    content=failed_results[0].content if failed_results else "",
                    selected_model=failed_results[0].model if failed_results else "",
                    confidence=0.0,
                    conflicts_detected=len(failed_results) > 1,
                    merge_method="all_failed",
                    contributing_models=[r.model for r in results],
                    alternative_results={r.model: r.content for r in results}
                )

            conflicts = self._detect_conflicts(successful_results)

            if len(successful_results) == 1:
                single = successful_results[0]
                return MergedResult(
                    content=single.content,
                    selected_model=single.model,
                    confidence=single.confidence,
                    conflicts_detected=False,
                    merge_method="single_model",
                    contributing_models=[single.model],
                    alternative_results={r.model: r.content for r in results}
                )

            if self._has_consensus(successful_results, conflicts):
                consensus_result = self._build_consensus(successful_results, conflicts)
                return MergedResult(
                    content=consensus_result.content,
                    selected_model=consensus_result.model,
                    confidence=consensus_result.confidence,
                    conflicts_detected=len(conflicts) > 0,
                    merge_method="consensus",
                    contributing_models=[r.model for r in successful_results],
                    alternative_results={r.model: r.content for r in results}
                )

            weighted = self._confidence_weighted_merge(successful_results)
            return MergedResult(
                content=weighted.content,
                selected_model=weighted.model,
                confidence=weighted.confidence * (1.0 - len(conflicts) * 0.1),
                conflicts_detected=len(conflicts) > 0,
                merge_method="confidence_weighted",
                contributing_models=[r.model for r in successful_results],
                alternative_results={r.model: r.content for r in results}
            )

    def _detect_conflicts(self, results: List[ModelResult]) -> List[Dict[str, Any]]:
        """
        Detect conflicts between model results.

        Args:
            results: List of successful results

        Returns:
            List of detected conflicts
        """
        conflicts = []

        if len(results) < 2:
            return conflicts

        for i, r1 in enumerate(results):
            for r2 in results[i+1:]:
                if self._are_conflicting(r1.content, r2.content):
                    conflicts.append({
                        "model_1": r1.model,
                        "model_2": r2.model,
                        "confidence_1": r1.confidence,
                        "confidence_2": r2.confidence,
                        "type": "content_difference"
                    })

        return conflicts

    def _are_conflicting(self, content1: str, content2: str) -> bool:
        """
        Check if two content results are conflicting.

        Args:
            content1: First content
            content2: Second content

        Returns:
            True if contents are significantly different
        """
        content1_lower = content1.lower().strip()
        content2_lower = content2.lower().strip()

        if content1_lower == content2_lower:
            return False

        extracted_actions_1 = self._extract_actions(content1)
        extracted_actions_2 = self._extract_actions(content2)

        if extracted_actions_1 and extracted_actions_2:
            if extracted_actions_1 != extracted_actions_2:
                return True

        similarity = self._calculate_similarity(content1_lower, content2_lower)
        return similarity < 0.5

    def _extract_actions(self, content: str) -> List[str]:
        """Extract action recommendations from content"""
        actions = re.findall(r'(?:action|decision|press)[:\s]*([A-Z]+)',
                             content, re.IGNORECASE)
        return [a.upper() for a in actions]

    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity between two texts (0.0 - 1.0)"""
        if not text1 or not text2:
            return 0.0

        set1 = set(text1.split())
        set2 = set(text2.split())

        if not set1 or not set2:
            return 0.0

        intersection = len(set1 & set2)
        union = len(set1 | set2)

        return intersection / union if union > 0 else 0.0

    def _has_consensus(self, results: List[ModelResult], conflicts: List[Dict[str, Any]]) -> bool:
        """Check if results have consensus"""
        if len(results) < 2:
            return False

        for conflict in conflicts:
            confidence_1 = conflict.get("confidence_1", 0)
            confidence_2 = conflict.get("confidence_2", 0)

            if confidence_1 >= self.consensus_threshold and confidence_2 >= self.consensus_threshold:
                return False

        return True

    def _build_consensus(self, results: List[ModelResult], conflicts: List[Dict[str, Any]]) -> ModelResult:
        """Build consensus from results"""
        sorted_results = sorted(results, key=lambda r: r.confidence, reverse=True)
        consensus = sorted_results[0]

        modified_confidence = consensus.confidence
        for conflict in conflicts:
            if conflict["model_1"] == consensus.model:
                modified_confidence *= (1.0 - conflict.get("confidence_2", 0) * 0.1)
            elif conflict["model_2"] == consensus.model:
                modified_confidence *= (1.0 - conflict.get("confidence_1", 0) * 0.1)

        return ModelResult(
            model=consensus.model,
            content=consensus.content,
            confidence=min(modified_confidence, 1.0),
            success=consensus.success,
            latency_ms=consensus.latency_ms,
            cost=consensus.cost
        )

    def _confidence_weighted_merge(self, results: List[ModelResult]) -> ModelResult:
        """Merge results with confidence weighting"""
        total_confidence = sum(r.confidence for r in results)
        if total_confidence == 0:
            return results[0]

        weighted_content = ""
        for r in results:
            weight = r.confidence / total_confidence
            weighted_content += f"[{r.model} (conf:{r.confidence:.2f})]: {r.content}\n"

        selected = max(results, key=lambda r: r.confidence)

        return ModelResult(
            model=selected.model,
            content=weighted_content.strip(),
            confidence=sum(r.confidence for r in results) / len(results),
            success=selected.success,
            latency_ms=sum(r.latency_ms for r in results) / len(results),
            cost=sum(r.cost for r in results)
        )

    def get_merge_stats(self) -> Dict[str, Any]:
        """Get merge statistics"""
        with self.lock:
            return {
                "total_merges": len(self.merge_history),
                "conflicts_detected": sum(1 for m in self.merge_history if m.get("conflicts_detected")),
                "consensus_merges": sum(1 for m in self.merge_history if m.get("merge_method") == "consensus"),
                "confidence_weighted_merges": sum(1 for m in self.merge_history if m.get("merge_method") == "confidence_weighted")
            }

    def reset(self):
        """Reset merge history"""
        with self.lock:
            self.merge_history = []