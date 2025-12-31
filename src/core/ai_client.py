"""
OpenRouter API Client for AI Models

Supports both vision and text-only models from OpenRouter
"""

import os
import time
import base64
import json
from typing import Optional, Dict, Any, List
from pathlib import Path
from datetime import datetime

import numpy as np
from PIL import Image
import requests


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
        # Load API key from environment or parameter
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ValueError(
                "OpenRouter API key not found. Set OPENROUTER_API_KEY environment variable "
                "or pass api_key parameter. Check .env file."
            )
        
        self.base_url = "https://openrouter.ai/api/v1"
        
        # Available models (actual vision-capable OpenRouter models)
        self.models = {
            "vision": "openai/gpt-4o",               # Official OpenAI multimodal model
            "thinking": "openai/gpt-4o-mini",        # Fast thinking model
            "acting": "openai/gpt-4o-mini"           # Fast acting model
        }
        
        self.total_cost = 0.0
        self.call_count = 0
    
    def chat_completion(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        images: Optional[List[np.ndarray]] = None,
        max_tokens: Optional[int] = 500,
        temperature: float = 0.3,
        top_p: float = 0.95,
        stream: bool = False
    ) -> Dict[str, Any]:
        """
        Make a chat completion request to OpenRouter
        
        Args:
            model: Model name (use self.models["vision"], self.models["thinking"], etc)
            messages: List of message dicts with 'role' and 'content'
            images: List of numpy arrays for vision inputs (only for vision models)
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            top_p: Nucleus sampling
            stream: Whether to stream response
            
        Returns:
            Response dict with content, usage, etc.
        """
        
        # Prepare headers
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://ai-plays-pokemon.com"
        }
        
        # Prepare payload
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "stream": stream
        }
        
            # Add images if vision model and images provided
        if images and len(images) > 0:
            # Convert images to base64 for OpenAI-compatible format
            image_content = []
            for img in images:
                if isinstance(img, np.ndarray):
                    pil_img = Image.fromarray(img)
                    
                    # Resize if too large (OpenAI has size limits)
                    if pil_img.size[0] > 1024:
                        pil_img = pil_img.resize((1024, int(1024 * pil_img.size[1] / pil_img.size[0])))
                    
                    # Convert to base64
                    import io
                    buffered = io.BytesIO()
                    pil_img.save(buffered, format="PNG")
                    image_base64 = base64.b64encode(buffered.getvalue()).decode()
                    
                    image_content.append({
                        "type": "image_url",
                        "image_url": f"data:image/png;base64,{image_base64}"
                    })
            
            # Find the user message and add images to it
            user_message_found = False
            for i, message in enumerate(payload["messages"]):
                if message.get("role") == "user":
                    user_message = message
                    
                    # Get original content
                    original_content = user_message.get("content", "")
                    if not original_content:
                        original_content = "Analyze this game screenshot."
                    
                    # Create combined content array
                    content_array = [
                        {"type": "text", "text": original_content},
                        *image_content
                    ]
                    
                    # Replace user message content with array
                    user_message["content"] = content_array
                    user_message_found = True
                    break
            
            # If no user message found, create one
            if not user_message_found:
                payload["messages"].append({
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Analyze this game screenshot."},
                        *image_content
                    ]
                })
        
        # Make request
        start_time = time.time()
        
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=30
            )
            duration_ms = (time.time() - start_time) * 1000
            
            if response.status_code != 200:
                error_info = response.json() if response.content else response.text
                print(f"OpenRouter API error {response.status_code}: {error_info}")
                raise Exception(f"OpenRouter API error {response.status_code}: {error_info}")
            
            result = response.json()
            
            # Track usage and cost
            usage = result.get("usage", {})
            input_tokens = usage.get("prompt_tokens", 0)
            output_tokens = usage.get("completion_tokens", 0)
            
            # Approximate cost calculation (OpenRouter pricing varies by model)
            # GPT-4o pricing: ~$5.00/1M input tokens, ~$15.00/1M output tokens
            # Note: Vision models have higher input costs due to image tokens
            if "gpt-4o" in model:
                cost = (input_tokens * 0.000005 + output_tokens * 0.000015)
            elif "gpt-4-vision" in model or "vision" in model:
                cost = (input_tokens * 0.00001 + output_tokens * 0.00003)
            elif "gpt-4o-mini" in model:
                cost = (input_tokens * 0.00000015 + output_tokens * 0.0000006)
            else:
                cost = (input_tokens * 0.00001 + output_tokens * 0.00003)  # Default pricing
            
            self.total_cost += cost
            self.call_count += 1
            
            # Log API call with proper logging function
            log_api_call(model, duration_ms, input_tokens, output_tokens, cost, True)
            
            return {
                "content": result.get("choices", [{}])[0].get("message", {}).get("content", ""),
                "finish_reason": result.get("choices", [{}])[0].get("finish_reason", "stop"),
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
        """
        Get vision model response (simplified interface)
        
        Args:
            prompt: Text prompt to accompany the image
            image: Screenshot as numpy array
            model: Model name (defaults to configured vision model)
            max_tokens: Max tokens to generate
            
        Returns:
            Generated text response
        """
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
        """
        Get text-only model response (simplified interface)
        
        Args:
            prompt: Text prompt
            model: Model name (defaults to configured thinking model)
            max_tokens: Max tokens to generate
            temperature: Sampling temperature
            
        Returns:
            Generated text response
        """
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


class GameAIManager:
    """
    Manages AI models for Pokemon gameplay
    
    Coordinates between vision model (for reading screens)
    and text models (for strategic/thinking/reasoning)
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize AI manager
        
        Args:
            api_key: OpenRouter API key
        """
        # Import PromptManager (temporarily disabled for core AI fix)
        print("⚠️  PromptManager temporarily disabled")
        self.prompt_manager = None
        
        self.client = OpenRouterClient(api_key)
        
        # Model assignments (actual available OpenRouter models)
        # NOTE: Use GPT-4o for vision - it's the actual vision-capable model
        self.vision_model = "openai/gpt-4o"               # ✅ Vision capable model
        self.thinking_model = "openai/gpt-4o-mini"        # Fast thinking model
        self.acting_model = "openai/gpt-4o-mini"          # Fast acting model
        
        # Prompt templates
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
    
    def analyze_screenshot(self, screenshot: np.ndarray) -> Dict[str, Any]:
        """
        Analyze screenshot using vision model
        
        Args:
            screenshot: Screenshot as numpy array
            
        Returns:
            Parsed structured data from vision analysis
        """
        print(f"👀 Analyzing screenshot with vision model: {self.vision_model}")
        
        prompt = self.prompts["vision_analysis"]
        
        try:
            response = self.client.get_vision_response(prompt, screenshot)
            print(f"📝 Vision response ({len(response)} chars): {response[:200]}...")
            
            # Parse the JSON response (simple JSON extraction)
            result = self._parse_json_response(response)
            
            # Log vision analysis
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
            # Return default state
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
        """
        Make strategic planning decision using thinking model
        
        Args:
            journey_summary: Journey narrative summary
            battle_state: Current battle state
            objective: Current objective
            past_failures: Mistakes to learn from
            model: Model to use (optional)
            
        Returns:
            Parsed strategic plan
        """
        print(f"🧠 Strategic planning with thinking model...")
        
        prompt = self.prompts["strategic_planning"].format(
            journey_summary=journey_summary or "No journey summary yet",
            battle_state=battle_state or "No battle",
            past_failures=past_failures or "No past failures",
            objective=objective or "Explore the world"
        )
        
        model = model or self.thinking_model
        
        try:
            response = self.client.get_text_response(prompt, model=model)
            print(f"Strategic model response: {response[:200]}...")
            
            # Parse response (extract structured data)
            result = self._parse_text_response(response)
            
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
        """
        Make immediate tactical decision using acting model
        
        Args:
            player_pokemon: Player's Pokemon name
            player_hp: Player HP percentage (0-100)
            enemy_pokemon: Enemy Pokemon name
            enemy_hp: Enemy HP percentage (0-100)
            enemy_type: Enemy Pokemon type(s)
            moves: Available moves
            weaknesses: Type weaknesses
            recent_actions: Recent battle actions
            strategy: Strategic guidance
            turn: Current battle turn
            model: Model to use (optional)
            
        Returns:
            Tactical decision: action and reasoning
        """
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
        
        model = model or self.acting_model
        
        try:
            response = self.client.get_text_response(
                prompt, 
                model=model,
                max_tokens=300,
                temperature=0.3
            )
            print(f"Tactical model response: {response[:200]}...")
            
            # Parse for REASONING and ACTION
            result = self._parse_tactical_response(response)
            
            print(f"✅ Tactical: REASONING: {result.get('reasoning', '')[:100]}... "
                  f"ACTION: {result.get('action', 'press:A')}")
            
            return result
            
        except Exception as e:
            print(f"❌ Tactical decision failed: {e}")
            return {
                "reasoning": "Default action - Press basic move",
                "action": "press:A"
            }
    
    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        """Simple JSON parser"""
        import json
        import re
        
        # Try to find JSON in response
        json_match = re.search(r'\{[^{}]*\}', response)
        if json_match:
            try:
                return json.loads(json_match.group())
            except:
                pass
        
        # Fallback: extract key information using heuristics
        result = {
            "screen_type": self._extract_screen_type(response),
            "enemy_pokemon": self._extract_pokemon_name(response),
            "player_hp": self._extract_number(response, "player hp") or 100,
            "enemy_hp": self._extract_number(response, "enemy hp") or 100,
            "available_actions": self._extract_actions(response),
            "recommended_action": self._extract_action(response),
            "reasoning": response[:200]  # First 200 chars
        }
        
        return result
    
    def _parse_text_response(self, response: str) -> Dict[str, Any]:
        """Parse text response for structured data"""
        return {
            "objective": self._extract_objective(response),
            "key_tactics": self._extract_list(response),
            "risks": "Unknown",
            "confidence": 0.5
        }
    
    def _parse_tactical_response(self, response: str) -> Dict[str, Any]:
        """Parse tactical decision response"""
        # Look for REASONING: and ACTION:
        lines = response.strip().split('\n')
        
        reasoning = ""
        action = "press:A"  # Default
        
        for line in lines:
            line_upper = line.upper()
            if "REASONING:" in line_upper:
                reasoning = line.split(":", 1)[1].strip()
            elif "ACTION:" in line_upper:
                action = line.split(":", 1)[1].strip().upper()
        
        # Fallback: extract action if not found
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
            return "overworld"  # Default
    
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
        import re
        
        # Look for percentages like "HP: 45%"
        percent_match = re.search(r'\d+%', text)
        if percent_match:
            return int(percent_match.group(0)[:-1])
        
        # Look for numbers near keyword
        if keyword:
            pattern = rf'{keyword}[^:]*:?\s*(\d+)'
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return int(match.group(1))
        
        return None
    
    def _extract_actions(self, text: str) -> List[str]:
        """Extract available actions"""
        # Look for action lists like "A, B, UP"
        import re
        actions_match = re.search(r'Actions?[:\s]+(.*)', text, re.IGNORECASE)
        if actions_match:
            actions_text = actions_match.group(1)
            # Split and clean
            actions = [a.strip() for a in re.split(r'[,;\s]+', actions_text) if a.strip()]
            return actions[:6]  # Limit to 6 actions
        
        return ["A", "DOWN"]  # Default
    
    def _extract_action(self, text: str) -> str:
        """Extract button press action"""
        # Look for "press:" pattern
        import re
        press_match = re.search(r'press:\s*(\w+)', text, re.IGNORECASE)
        if press_match:
            return f"press:{press_match.group(1).upper()}"
        
        # Look for button mentions
        for button in ["A", "B", "UP", "DOWN", "LEFT", "RIGHT"]:
            if button in text:
                return f"press:{button}"
        
        return "press:A"  # Default
    
    def _extract_objective(self, text: str) -> str:
        """Extract objective from strategic response"""
        # Simple: take first line or extract OBJECTIVE section
        import re
        obj_match = re.search(r'OBJECTIVE[:\s]+(.*?)(?:\n|$)', text, re.IGNORECASE)
        if obj_match:
            return obj_match.group(1).strip()
        
        # Fallback: first line
        lines = text.strip().split('\n')
        if lines:
            return lines[0][:100]  # First 100 chars
        
        return text[:100]  # First 100 chars
    
    def _extract_list(self, text: str) -> List[str]:
        """Extract list of tactics from response"""
        # Extract numbered or bulleted list items
        import re
        items = re.findall(r'\d+\.\s+(.*?)(?=\n|$)', text)
        if not items:
            items = re.findall(r'[-*]\s+(.*?)(?=\n|$)', text)
        
        return items[:5]  # Limit to 5 tactics


# Example usage
if __name__ == "__main__":
    # Test the client
    try:
        ai_manager = GameAIManager()
        print("✅ OpenRouter client initialized")
        
        # Test with fake screenshot
        test_screenshot = np.random.randint(50, 200, (144, 160, 3), dtype=np.uint8)
        
        # Test vision analysis
        print("\n--- Testing Vision Analysis ---")
        vision_result = ai_manager.analyze_screenshot(test_screenshot)
        print(f"Vision result: {vision_result}")
        
        # Test strategic thinking
        print("\n--- Testing Strategic Planning ---")
        strategic_result = ai_manager.make_strategic_decision(
            journey_summary="Started in Pallet Town, have Charmander",
            battle_state="Fighting a Level 3 Pidgey, my Charmander has 85 HP",
            objective="Get to Viridian Forest and capture more Pokemon",
            past_failures="Lost to Geodude by using Fire moves instead of Water"
        )
        print(f"Strategic result: {strategic_result}")
        
        # Test tactical decision
        print("\n--- Testing Tactical Decision ---")
        tactical_result = ai_manager.make_tactical_decision(
            player_pokemon="Charmander",
            player_hp=85.0,
            enemy_pokemon="Pidgey",
            enemy_hp=60.0,
            enemy_type="Flying",
            moves=["Ember", "Scratch", "Growl"],
            weaknesses=["Electric", "Rock", "Ice"],
            recent_actions="Used Ember (Pidgey took 25% damage)",
            strategy="Use super-effective moves",
            turn=2
        )
        print(f"Tactical result: {tactical_result}")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")