"""
Dynamic Prompt Selection System for AI Plays Pokemon

Manages prompt templates for different game scenarios and enables
AI to dynamically choose relevant prompts for each screenshot.
"""

import os
import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

@dataclass
class PromptTemplate:
    """Individual prompt template with metadata"""
    name: str
    category: str  # battle, menu, exploration, dialog, strategic
    description: str
    content: str
    priority: int = 1  # Higher priority = more relevant
    use_cases: List[str] = field(default_factory=list)  # When to use this prompt
    
    def __post_init__(self):
        """Initialize default use_cases if empty"""
        if not self.use_cases:
            self.use_cases = [self.category]

class PromptManager:
    """
    Manages dynamic prompt selection for AI decision making
    
    Features:
    - Load prompt templates from filesystem
    - Categorize prompts by game scenario
    - Enable AI to choose relevant prompts dynamically
    - Track prompt usage and effectiveness
    """
    
    def __init__(self, prompts_dir: str = "prompts"):
        """
        Initialize prompt manager
        
        Args:
            prompts_dir: Path to prompts directory
        """
        self.prompts_dir = Path(prompts_dir)
        self.prompt_templates: List[PromptTemplate] = []
        self.load_prompts()
        
        # Usage tracking for analytics
        self.prompt_usage_stats = {}
    
    def load_prompts(self):
        """Load all prompt templates from filesystem"""
        if not self.prompts_dir.exists():
            print(f"⚠️  Prompts directory not found: {self.prompts_dir}")
            return
        
        # Load prompts from each category folder
        for category_dir in self.prompts_dir.iterdir():
            if category_dir.is_dir():
                category = category_dir.name
                
                # Load each prompt file in category
                for prompt_file in category_dir.glob("*.txt"):
                    try:
                        template = self._load_prompt_file(prompt_file, category)
                        if template:
                            self.prompt_templates.append(template)
                            print(f"✅ Loaded prompt: {template.category}/{template.name}")
                    except Exception as e:
                        print(f"⚠️  Failed to load prompt {prompt_file}: {e}")
        
        print(f"📋 Prompt Manager loaded {len(self.prompt_templates)} templates")
    
    def _load_prompt_file(self, file_path: Path, category: str) -> Optional[PromptTemplate]:
        """Load individual prompt file"""
        try:
            content = file_path.read_text(encoding='utf-8')
            name = file_path.stem  # filename without extension
            
            # Extract metadata from content (first few lines starting with #)
            description = ""
            priority = 1
            
            lines = content.split('\n')
            for line in lines:
                if line.startswith('#') and not line.startswith('##'):
                    description = line.strip('# ').strip()
                elif line.startswith('**Priority'):
                    # Try to extract priority level
                    import re
                    match = re.search(r'**Priority:\s*(\d+)', line)
                    if match:
                        priority = int(match.group(1))
            
            # Create template
            template = PromptTemplate(
                name=name,
                category=category,
                description=description or f"Game {category} prompt",
                content=content,
                priority=priority,
                use_cases=[category]  # Basic categorization
            )
            
            return template
            
        except Exception as e:
            print(f"⚠️  Error loading prompt {file_path}: {e}")
            return None
    
    def get_relevant_prompts(self, game_state_type: str, context: Dict[str, Any]) -> List[PromptTemplate]:
        """
        Get prompts relevant for current game state
        
        Args:
            game_state_type: Current game state (battle, menu, exploration, dialog)
            context: Additional context for prompt selection
            
        Returns:
            List of relevant prompt templates
        """
        # Filter prompts by category and relevance
        relevant_prompts = []
        
        for template in self.prompt_templates:
            # Direct category match
            if template.category == game_state_type:
                relevant_prompts.append(template)
            elif game_state_type == "battle" and template.category in ["strategic", "battle"]:
                relevant_prompts.append(template)
            elif game_state_type == "menu" and template.category in ["exploration", "strategic"]:
                relevant_prompts.append(template)
            elif game_state_type == "overworld" and template.category in ["exploration", "strategic"]:
                relevant_prompts.append(template)
            elif game_state_type == "dialog" and template.category in ["strategic", "battle"]:
                relevant_prompts.append(template)
        
        # Sort by priority (higher first)
        relevant_prompts.sort(key=lambda x: x.priority, reverse=True)
        
        # Limit to most relevant prompts (top 3)
        return relevant_prompts[:3]
    
    def select_prompts_for_ai(self, game_state_type: str, context: Dict[str, Any], ai_preference: str = "balanced") -> List[str]:
        """
        Select specific prompts for AI analysis
        
        Args:
            game_state_type: Type of current game state
            context: Game state context
            ai_preference: AI preference (balanced, tactical, strategic)
            
        Returns:
            List of selected prompt contents for AI
        """
        relevant_templates = self.get_relevant_prompts(game_state_type, context)
        
        # Apply AI preference filtering
        selected_prompts = []
        
        for template in relevant_templates:
            if ai_preference == "balanced":
                # Use all relevant prompts
                selected_prompts.append(template.content)
            elif ai_preference == "tactical":
                # Focus on immediate action prompts
                if "tactical" in template.name.lower() or template.category == "battle":
                    selected_prompts.append(template.content)
            elif ai_preference == "strategic":
                # Focus on strategic planning prompts
                if "strategic" in template.name.lower() or template.category == "strategic":
                    selected_prompts.append(template.content)
            else:
                # Default balanced approach
                selected_prompts.append(template.content)
        
        return selected_prompts
    
    def track_prompt_usage(self, prompt_name: str, effectiveness: float = 1.0):
        """Track prompt usage for analytics"""
        if prompt_name not in self.prompt_usage_stats:
            self.prompt_usage_stats[prompt_name] = {
                'usage_count': 0,
                'effectiveness_sum': 0.0,
                'last_used': None
            }
        
        stats = self.prompt_usage_stats[prompt_name]
        stats['usage_count'] += 1
        stats['effectiveness_sum'] += effectiveness
        stats['last_used'] = "now"  # Could use timestamp
    
    def get_prompt_analytics(self) -> Dict[str, Any]:
        """Get analytics on prompt usage and effectiveness"""
        analytics = {}
        
        for prompt_name, stats in self.prompt_usage_stats.items():
            analytics[prompt_name] = {
                'usage_count': stats['usage_count'],
                'average_effectiveness': stats['effectiveness_sum'] / stats['usage_count'] if stats['usage_count'] > 0 else 0,
                'last_used': stats['last_used']
            }
        
        return analytics

# Example usage
if __name__ == "__main__":
    # Initialize prompt manager
    prompt_manager = PromptManager("prompts")
    
    # Test dynamic prompt selection
    game_context = {"enemy_pokemon": "Pidgey", "player_hp": 85}
    prompts = prompt_manager.select_prompts_for_ai("battle", game_context, "tactical")
    
    print("Selected prompts for tactical battle analysis:")
    for i, prompt in enumerate(prompts, 1):
        print(f"{i}. {prompt[:100]}...")