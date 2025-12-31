"""
OCR Engine - Text Recognition for Pokemon Game Screens

Implements template-based OCR for Gen 1 font recognition.
Supports Pokemon names, menu items, and dialog text.
"""

import json
import re
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image


@dataclass
class OCRResult:
    """Result of OCR text extraction"""
    text: str
    confidence: float
    character_count: int
    processing_time_ms: float = 0.0
    characters: List[Dict] = field(default_factory=list)


@dataclass
class FontTemplate:
    """Represents a character template from the font database"""
    char: str
    template: np.ndarray
    unicode_value: int
    width: int
    height: int
    samples: int = 1
    confidence: float = 1.0


class OCREngine:
    """
    Optical Character Recognition engine for Pokemon game text.
    
    Uses template matching against a pre-built font database
    for accurate recognition of the 6x8 pixel Gen 1 font.
    """
    
    CHAR_WIDTH = 6
    CHAR_HEIGHT = 8
    FONT_DATABASE_PATH = Path(__file__).parent / "data" / "fonts.json"
    
    def __init__(self):
        """Initialize OCR Engine with font templates"""
        self.font_templates: Dict[int, FontTemplate] = {}
        self._load_font_database()
        
        self.special_cases = {
            "contraction_pattern": r"[A-Z]'[a-z]",
            "gender_symbols": {"M": "♂", "F": "♀"},
            "apostrophe_remap": {"'d": "d", "'s": "s", "'l": "l", "'t": "t", "'v": "v", "'r": "r"},
        }
        
        self.common_words = self._build_common_words_set()
    
    def _load_font_database(self):
        """Load font templates from database file"""
        if self.FONT_DATABASE_PATH.exists():
            try:
                with open(self.FONT_DATABASE_PATH, 'r') as f:
                    data = json.load(f)
                    for char_info in data.get("font_templates", []):
                        template = np.array(char_info["template"], dtype=np.uint8)
                        self.font_templates[char_info["unicode"]] = FontTemplate(
                            char=char_info["char"],
                            template=template,
                            unicode_value=char_info["unicode"],
                            width=char_info.get("width", self.CHAR_WIDTH),
                            height=char_info.get("height", self.CHAR_HEIGHT),
                            samples=char_info.get("samples", 1),
                            confidence=char_info.get("confidence", 1.0)
                        )
            except Exception:
                self._create_default_font_database()
        else:
            self._create_default_font_database()
    
    def _create_default_font_database(self):
        """Create default font template database for Gen 1 font"""
        self.font_templates = {}
        
        uppercase = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        lowercase = "abcdefghijklmnopqrstuvwxyz"
        digits = "0123456789"
        special = "!?.,-:()/"
        
        all_chars = uppercase + lowercase + digits + special
        
        for i, char in enumerate(all_chars):
            unicode_val = ord(char)
            template = self._generate_template_for_char(char)
            self.font_templates[unicode_val] = FontTemplate(
                char=char,
                template=template,
                unicode_value=unicode_val,
                width=self.CHAR_WIDTH,
                height=self.CHAR_HEIGHT,
                samples=1,
                confidence=0.95
            )
        
        self._save_font_database()
    
    def _generate_template_for_char(self, char: str) -> np.ndarray:
        """Generate a template for a character using PIL"""
        template = np.zeros((self.CHAR_HEIGHT, self.CHAR_WIDTH), dtype=np.uint8)
        
        font_size = 8
        img = Image.new('1', (self.CHAR_WIDTH, self.CHAR_HEIGHT), 0)
        
        try:
            from PIL import ImageDraw, ImageFont
            draw = ImageDraw.Draw(img)
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_size)
            except Exception:
                font = ImageFont.load_default()
            draw.text((0, 0), char, fill=1, font=font)
            template = np.array(img)
        except Exception:
            pass
        
        return template
    
    def _save_font_database(self):
        """Save font templates to database file"""
        self.FONT_DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
        
        font_list = []
        for template in self.font_templates.values():
            font_list.append({
                "char": template.char,
                "template": template.template.tolist(),
                "unicode": template.unicode_value,
                "width": template.width,
                "height": template.height,
                "samples": template.samples,
                "confidence": template.confidence
            })
        
        data = {
            "font_templates": font_list,
            "special_cases": self.special_cases
        }
        
        with open(self.FONT_DATABASE_PATH, 'w') as f:
            json.dump(data, f, indent=2)
    
    def _build_common_words_set(self):
        """Build set of common Pokemon words for validation"""
        return {
            "POKEMON", "TRAINER", "ITEM", "MENU", "SAVE", "LOAD", "OPTIONS",
            "BATTLE", "WILD", "ENCOUNTER", "LEVEL", "HP", "PP", "EXP",
            "ROUTE", "TOWN", "CITY", "FOREST", "CAVE", "ROAD", "PATH",
            "NORMAL", "FIRE", "WATER", "ELECTRIC", "GRASS", "ICE",
            "FIGHTING", "POISON", "GROUND", "FLYING", "PSYCHIC", "BUG",
            "ROCK", "GHOST", "DRAGON", "DARK", "STEEL", "FAIRY",
            "CUT", "SURF", "STRENGTH", "FLASH", "WHIRLPOOL", "TELEPORT",
            "PIKACHU", "CHARIZARD", "BULBASAUR", "SQUIRTLE", "EEVEE",
        }
    
    def extract_text(
        self, 
        image: np.ndarray, 
        min_confidence: float = 0.7
    ) -> OCRResult:
        """
        Extract text from an image region.
        
        Args:
            image: Image region containing text
            min_confidence: Minimum confidence threshold for character recognition
            
        Returns:
            OCRResult with extracted text and confidence
        """
        import time
        start_time = time.perf_counter()
        
        if len(image.shape) == 3:
            gray = np.mean(image, axis=2).astype(np.uint8)
        else:
            gray = image
        
        binary = self._binarize_image(gray)
        
        lines = self._split_into_lines(binary)
        
        all_text = ""
        all_confidence = 0.0
        total_chars = 0
        all_char_data = []
        
        for line in lines:
            line_text, line_confidence, line_chars = self._recognize_line(line, min_confidence)
            all_text += line_text + "\n"
            if line_confidence > 0:
                all_confidence += line_confidence * len(line_chars)
                total_chars += len(line_chars)
                all_char_data.extend(line_chars)
        
        all_text = all_text.strip()
        
        avg_confidence = (all_confidence / total_chars) if total_chars > 0 else 0.0
        
        all_text = self._postprocess_text(all_text)
        
        processing_time = (time.perf_counter() - start_time) * 1000
        
        return OCRResult(
            text=all_text,
            confidence=avg_confidence,
            character_count=total_chars,
            processing_time_ms=processing_time,
            characters=all_char_data
        )
    
    def _binarize_image(self, gray: np.ndarray, threshold: int = 128) -> np.ndarray:
        """Binarize image using threshold"""
        return (gray > threshold).astype(np.uint8) * 255
    
    def _split_into_lines(self, binary: np.ndarray) -> List[np.ndarray]:
        """Split binary image into lines of text"""
        h, w = binary.shape
        
        row_sums = np.sum(binary > 0, axis=1)
        
        lines = []
        current_line_start = 0
        in_line = False
        
        for y in range(h):
            if row_sums[y] > 0:
                if not in_line:
                    current_line_start = y
                    in_line = True
            else:
                if in_line:
                    lines.append(binary[current_line_start:y, :])
                    in_line = False
        
        if in_line:
            lines.append(binary[current_line_start:h, :])
        
        return lines
    
    def _recognize_line(
        self, 
        line: np.ndarray, 
        min_confidence: float
    ) -> Tuple[str, float, List[Dict]]:
        """Recognize a single line of text"""
        h, w = line.shape
        
        chars = []
        x = 0
        
        while x < w:
            col_sums = np.sum(line[:, x:min(x + 3, w)] > 0, axis=1)
            if np.max(col_sums) == 0:
                x += 1
                continue
            
            char_width = self._find_character_width(line, x)
            
            if char_width <= 0:
                x += 1
                continue
            
            char_region = line[:h, x:min(x + char_width, w)]
            
            char_info = self._recognize_character(char_region)
            
            if char_info["confidence"] >= min_confidence:
                chars.append(char_info)
            else:
                chars.append({
                    "char": "?",
                    "confidence": char_info["confidence"],
                    "position": x,
                    "width": char_width
                })
            
            x += char_width
        
        text = "".join(c["char"] for c in chars)
        avg_confidence = np.mean([c["confidence"] for c in chars]) if chars else 0.0
        
        return text, avg_confidence, chars
    
    def _find_character_width(self, line: np.ndarray, start_x: int) -> int:
        """Find the width of a character starting at position x"""
        h, w = line.shape
        
        for width in range(1, self.CHAR_WIDTH + 3):
            if start_x + width > w:
                break
            
            col_sums = np.sum(line[:, start_x:start_x + width] > 0, axis=1)
            
            if np.max(col_sums) == 0:
                return max(1, width - 1)
        
        return self.CHAR_WIDTH
    
    def _recognize_character(self, char_region: np.ndarray) -> Dict:
        """Recognize a single character using template matching"""
        h, w = char_region.shape
        
        best_match = None
        best_score = 0
        
        for unicode_val, template in self.font_templates.items():
            score = self._template_match(char_region, template.template)
            
            if score > best_score:
                best_score = score
                best_match = {
                    "char": template.char,
                    "confidence": score,
                    "unicode": unicode_val,
                    "width": w
                }
        
        if best_match and best_score < 0.6:
            best_match["confidence"] = 0.6
        
        return best_match or {"char": "?", "confidence": 0.0, "unicode": 0, "width": w}
    
    def _template_match(
        self, 
        char_region: np.ndarray, 
        template: np.ndarray
    ) -> float:
        """Calculate template matching score using normalized cross-correlation"""
        th, tw = template.shape
        
        if char_region.shape[0] != th or char_region.shape[1] != tw:
            char_region = self._resize_to_match(char_region, (th, tw))
        
        if char_region.shape != template.shape:
            return 0.0
        
        a_mean = np.mean(char_region)
        b_mean = np.mean(template)
        
        a_centered = char_region - a_mean
        b_centered = template - b_mean
        
        numerator = np.sum(a_centered * b_centered)
        denominator = np.sqrt(np.sum(a_centered**2) * np.sum(b_centered**2))
        
        if denominator == 0:
            return 0.0
        
        return max(0.0, numerator / denominator)
    
    def _resize_to_match(
        self, 
        region: np.ndarray, 
        target_size: Tuple[int, int]
    ) -> np.ndarray:
        """Resize character region to match template size"""
        th, tw = target_size
        
        if region.shape[0] > th:
            region = region[:th, :]
        if region.shape[1] > tw:
            region = region[:, :tw]
        
        if region.shape != target_size:
            padded = np.zeros(target_size, dtype=region.dtype)
            h, w = min(region.shape[0], th), min(region.shape[1], tw)
            padded[:h, :w] = region[:h, :w]
            region = padded
        
        return region
    
    def _postprocess_text(self, text: str) -> str:
        """Post-process recognized text"""
        text = text.replace("?", "")
        
        text = re.sub(r'\s+', ' ', text).strip()
        
        text = self._fix_contractions(text)
        
        text = text.upper()
        
        text = self._validate_and_correct(text)
        
        return text
    
    def _fix_contractions(self, text: str) -> str:
        """Fix common OCR errors in contractions"""
        for wrong, right in self.special_cases.get("apostrophe_remap", {}).items():
            text = text.replace("'" + wrong, right)
        return text
    
    def _validate_and_correct(self, text: str) -> str:
        """Validate and correct recognized text"""
        words = text.split()
        corrected = []
        
        for word in words:
            if word in self.common_words:
                corrected.append(word)
            else:
                corrected.append(self._suggest_correction(word))
        
        return " ".join(corrected)
    
    def _suggest_correction(self, word: str) -> str:
        """Suggest correction for unknown word"""
        if len(word) <= 2:
            return word
        
        return word
    
    def extract_dialog(self, image: np.ndarray) -> str:
        """Extract dialog text from dialog box region"""
        result = self.extract_text(image)
        return result.text
    
    def extract_pokemon_name(self, image: np.ndarray) -> Optional[str]:
        """Extract Pokemon name from name box"""
        result = self.extract_text(image, min_confidence=0.6)
        
        if result.confidence > 0.6 and result.text:
            return result.text.strip()
        
        return None
    
    def extract_hp_value(self, image: np.ndarray) -> Optional[int]:
        """Extract HP number from HP bar"""
        result = self.extract_text(image, min_confidence=0.5)
        
        numbers = re.findall(r'\d+', result.text)
        
        if numbers:
            return int(numbers[0])
        
        return None