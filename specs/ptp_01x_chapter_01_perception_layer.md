# PTP-01X Chapter 1: Perception Layer – Visual Interface & Grid Normalization

## Executive Summary

The **Perception Layer** serves as the agent's sensory cortex, responsible for ingesting, normalizing, and semantically interpreting the raw video output from the Game Boy's Picture Processing Unit (PPU). While the agent has access to memory states (via WRAM), visual verification provides a critical redundancy layer, essential for:

1. Detecting visual-only cues (text box frames, animation glitches)
2. Validating that internal memory state aligns with rendered reality
3. Identifying interactive entities (NPCs, signs, items)
4. Performing OCR on dialogue and menu text

**Core Design Philosophy:**
- The Game Boy displays only **4 shades** (White, Light Gray, Dark Gray, Black)
- Modern emulation introduces artifacts requiring **Color Quantization**
- Screen resolution: **160×144 pixels** at **59.7 Hz refresh rate**
- Output: **Semantic Grid** (10×9 blocks) for Navigation Engine

---

## 1.1 Pixel-Buffer Acquisition and Synchronization

### Technical Specifications

| Parameter | Value |
|-----------|-------|
| Resolution | 160 × 144 pixels |
| Color Depth | 4 shades (DMG-01) |
| Refresh Rate | ~59.7 Hz |
| Buffer Format | NumPy array (H × W × C) |
| PyBoy API | `pyboy.screen.get_ndarray()` |

### Synchronous "Tick-Read-Act" Cycle

The architecture mandates a strict timing protocol:

```
TICK:     Advance emulation by 1 frame
          ↓
READ:     Extract frame buffer immediately
          ↓
VERIFY:   Compare Vision vs Memory consistency
          ↓
DECIDE:   Plan action based on combined data
          ↓
ACT:      Execute button press
          ↓
REPEAT
```

**Critical Timing Rule:**  
If buffer read is de-coupled from emulation clock, agent risks "blind inputs" where it assumes a menu is open when it has closed.

### PyBoy Implementation

```python
import numpy as np
from pyboy import PyBoy

class PixelBufferAcquisition:
    """
    Handles synchronous frame buffer acquisition from PyBoy emulator.
    Ensures pixel-perfect timing for real-time decision making.
    """
    
    def __init__(self, pyboy: PyBoy):
        self.pyboy = pyboy
        self.frame_buffer = None
        self.last_frame_hash = None
        self.frame_count = 0
        
    def tick(self) -> np.ndarray:
        """
        Advance emulation and capture frame buffer.
        
        Returns:
            3D NumPy array (H × W × C) representing the frame
        """
        # Advance emulation by one tick
        self.pyboy.tick()
        
        # Immediately capture frame buffer (before any logic)
        self.frame_buffer = self.pyboy.screen.get_ndarray()
        
        self.frame_count += 1
        return self.frame_buffer
    
    def get_frame_hash(self) -> str:
        """
        Generate hash of current frame for change detection.
        Used to skip inference on unchanged screens.
        """
        import hashlib
        frame_bytes = self.frame_buffer.tobytes()
        return hashlib.md5(frame_bytes).hexdigest()
    
    def has_frame_changed(self) -> bool:
        """
        Check if current frame differs from last frame.
        Optimizes API calls by skipping static screens.
        """
        current_hash = self.get_frame_hash()
        if current_hash == self.last_frame_hash:
            return False
        self.last_frame_hash = current_hash
        return True


class HeadlessRenderer:
    """
    Enables high-speed training by decoupling graphical output
    from internal buffer generation.
    """
    
    def __init__(self, pyboy: PyBoy, speed_multiplier: int = 10):
        self.pyboy = pyboy
        self.speed_multiplier = speed_multiplier
        self.original_headless = pyboy.headless_toggle
        
    def set_headless_mode(self, enabled: bool):
        """
        Toggle headless rendering for high-speed training.
        
        Args:
            enabled: If True, disable host display rendering
        """
        if enabled:
            pyboy.set_headless(True)  # Decouple display from simulation
        else:
            pyboy.set_headless(False)  # Restore normal rendering
    
    def fast_forward(self, ticks: int = 100):
        """
        Advance simulation without rendering for speed.
        
        Args:
            ticks: Number of frames to advance
        """
        self.set_headless_mode(True)
        for _ in range(ticks):
            self.pyboy.tick()
        self.set_headless_mode(False)
```

---

## 1.2 Color Space Quantization and Palette Normalization

### The Problem

Original Game Boy hardware displays only **4 distinct shades**, but modern emulation introduces:
- Bicubic upscaling artifacts
- Color correction shaders
- Anti-aliasing interpolation
- Thousands of interpolated RGB values

**For deterministic AI:** `RGB(240, 240, 240)` must equal `RGB(255, 255, 255)`

### Quantization Logic

The PTP-01X enforces rigorous Color Quantization:

```
For each pixel in raw buffer:
    1. Calculate Euclidean distance to 4 canonical colors:
       - White (255, 255, 255)
       - Light Gray (170, 170, 170)
       - Dark Gray (85, 85, 85)
       - Black (0, 0, 0)
    
    2. Assign pixel to nearest color index (0-3)
    
    3. Output: 2-bit indexed image (4 values per pixel)
```

### Implementation

```python
import numpy as np
from typing import Tuple

class ColorQuantizer:
    """
    Converts 24-bit RGB to 4-color palette (Gen 1 DMG style).
    Provides deterministic visual input regardless of emulator settings.
    """
    
    # Canonical Game Boy DMG palette (RGB)
    PALETTE = np.array([
        [255, 255, 255],  # 0: White (Background)
        [170, 170, 170],  # 1: Light Gray
        [85, 85, 85],     # 2: Dark Gray
        [0, 0, 0]         # 3: Black (Foreground)
    ], dtype=np.uint8)
    
    def __init__(self):
        # Pre-calculate palette for vectorized distance computation
        self._palette = self.PALETTE
    
    def quantize(self, frame: np.ndarray) -> np.ndarray:
        """
        Convert 24-bit RGB frame to 4-color indexed palette.
        
        Args:
            frame: NumPy array (H × W × 3) with RGB values
            
        Returns:
            NumPy array (H × W) with color indices (0-3)
        """
        # Reshape for vectorized computation
        pixels = frame.reshape(-1, 3)  # (H*W, 3)
        
        # Vectorized Euclidean distance to each palette color
        # Shape: (H*W, 4)
        distances = np.linalg.norm(
            pixels[:, np.newaxis] - self._palette[np.newaxis, :],
            axis=2
        )
        
        # Assign nearest palette index
        quantized = np.argmin(distances, axis=1)
        
        # Reshape back to original dimensions
        return quantized.reshape(frame.shape[:2])
    
    def quantize_with_rgb_output(self, frame: np.ndarray) -> np.ndarray:
        """
        Convert to palette colors for display/debugging.
        
        Returns:
            NumPy array (H × W × 3) with quantized RGB values
        """
        indices = self.quantize(frame)
        return self._palette[indices]
    
    def get_color_histogram(self, frame: np.ndarray) -> dict:
        """
        Get distribution of 4 colors in frame.
        Useful for detecting menu screens vs battles.
        """
        indices = self.quantize(frame)
        histogram = {}
        for i in range(4):
            histogram[i] = np.sum(indices == i)
        return histogram


class VisualNoiseFilter:
    """
    Filters out emulator-specific visual noise while preserving
    semantic content (text, sprites, tiles).
    """
    
    def __init__(self, quantizer: ColorQuantizer):
        self.quantizer = quantizer
    
    def denoise_frame(self, frame: np.ndarray) -> np.ndarray:
        """
        Remove visual artifacts while preserving game content.
        
        Pipeline:
        1. Color quantization (4 colors)
        2. Median filter (remove salt-and-pepper noise)
        3. Morphological opening (remove small artifacts)
        """
        import cv2
        
        # Step 1: Quantize to 4 colors
        quantized = self.quantizer.quantize(frame)
        
        # Step 2: Convert to RGB for OpenCV operations
        rgb = self.quantizer.quantize_with_rgb_output(frame)
        
        # Step 3: Median filter (3x3) to remove noise
        denoised = cv2.medianBlur(rgb, ksize=3)
        
        # Step 4: Morphological opening to remove small artifacts
        kernel = np.ones((2, 2), np.uint8)
        opened = cv2.morphologyEx(denoised, cv2.MORPH_OPEN, kernel)
        
        return opened
    
    def is_static_frame(self, frame1: np.ndarray, frame2: np.ndarray) -> bool:
        """
        Detect if two frames are visually identical.
        Used to skip API calls on unchanged screens.
        """
        diff = np.abs(frame1.astype(int) - frame2.astype(int))
        return np.sum(diff) < 100  # Threshold for "identical"
```

---

## 1.3 Sprite and Background Segmentation

### The Problem

The agent must distinguish between:
- **Static geometry:** Walls, floors, water tiles
- **Dynamic entities:** NPCs, player avatar, interactive objects

**Game Boy Architecture:**
- Background tiles: VRAM Bank 0 (0x9800-0x9BFF)
- Moving objects: Object Attribute Memory (OAM)

### Segmentation Algorithm

```
Expected Background = Read from VRAM (0x9800-0x9BFF)
                     ↓
Live Frame = Capture from screen buffer
            ↓
Difference Mask = Live Frame - Expected Background
                ↓
Connected Components = Find clusters in mask
                     ↓
Sprite Entities = Each cluster = one dynamic entity
```

### Implementation

```python
import numpy as np
from typing import List, Tuple, Dict

class SpriteSegmenter:
    """
    Separates static background from dynamic sprites using
    difference-masking against VRAM tile data.
    """
    
    def __init__(self, pyboy):
        self.pyboy = pyboy
        self.last_known_background = None
    
    def get_vram_background(self) -> np.ndarray:
        """
        Read static background tiles from VRAM.
        VRAM Bank 0 at 0x9800-0x9BFF contains tile map.
        """
        # Read tile map from VRAM
        tile_map = []
        for addr in range(0x9800, 0x9BFF + 1):
            tile_id = self.pyboy.memory[addr]
            tile_data = self._get_tile_pixels(tile_id)
            tile_map.append(tile_data)
        
        # Reconstruct full background
        background = self._reconstruct_background(tile_map)
        return background
    
    def segment_sprites(self, frame: np.ndarray) -> List[Dict]:
        """
        Identify all dynamic sprites in the current frame.
        
        Returns:
            List of sprite bounding boxes and properties
        """
        import cv2
        
        # Get expected background (from VRAM or cached)
        if self.last_known_background is None:
            self.last_known_background = self.get_vram_background()
        
        # Convert to grayscale for difference detection
        frame_gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
        bg_gray = cv2.cvtColor(self.last_known_background, cv2.COLOR_RGB2GRAY)
        
        # Compute difference mask
        diff = cv2.absdiff(frame_gray, bg_gray)
        
        # Threshold for "different" pixels
        _, mask = cv2.threshold(diff, 30, 255, cv2.THRESH_BINARY)
        
        # Find connected components
        contours, _ = cv2.findContours(
            mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        
        sprites = []
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            
            # Filter out tiny noise
            if w < 8 or h < 8:
                continue
            
            sprites.append({
                'x': x,
                'y': y,
                'width': w,
                'height': h,
                'area': w * h,
                'center': (x + w // 2, y + h // 2),
                'type': self._classify_sprite(contour, frame)
            })
        
        return sprites
    
    def _classify_sprite(self, contour: np.ndarray, frame: np.ndarray) -> str:
        """
        Classify sprite type based on size and position.
        
        Categories:
        - PLAYER: Center-bottom of screen, ~16x16 pixels
        - NPC: Walking around, similar size to player
        - TRAINER: Larger than NPCs, ~24x24 pixels
        - ITEM: Small, floating, ~8x8 pixels
        - SIGN: Static but detected as sprite (edge case)
        """
        x, y, w, h = cv2.boundingRect(contour)
        
        # Player is typically at bottom center
        if (100 < x < 130) and (110 < y < 140) and (12 < w < 20) and (12 < h < 20):
            return 'PLAYER'
        
        # Items are small and high in frame
        if w < 12 and h < 12 and y < 80:
            return 'ITEM'
        
        # Trainers are larger
        if w > 20 or h > 20:
            return 'TRAINER'
        
        return 'NPC'
    
    def update_background_cache(self):
        """
        Update cached background after map changes.
        Called when Map_ID changes.
        """
        self.last_known_background = None


class EntityTracker:
    """
    Tracks dynamic entities (NPCs, sprites) across frames.
    Enables prediction of movement and collision avoidance.
    """
    
    def __init__(self):
        self.entities = {}  # entity_id -> {position, velocity, type}
        self.entity_id_counter = 0
    
    def update(self, sprites: List[Dict]) -> Dict:
        """
        Match new sprite detections with tracked entities.
        
        Returns:
            Updated entity positions and any new entities found
        """
        updated_entities = {}
        
        for sprite in sprites:
            # Try to match with existing entity based on position
            matched_id = self._find_matching_entity(sprite)
            
            if matched_id is not None:
                # Update existing entity
                self.entities[matched_id].update({
                    'position': (sprite['x'], sprite['y']),
                    'last_seen': self.entity_id_counter,
                    'size': (sprite['width'], sprite['height'])
                })
                updated_entities[matched_id] = self.entities[matched_id]
            else:
                # Create new entity
                new_id = f"entity_{self.entity_id_counter}"
                self.entity_id_counter += 1
                
                self.entities[new_id] = {
                    'type': sprite['type'],
                    'position': (sprite['x'], sprite['y']),
                    'first_seen': self.entity_id_counter,
                    'last_seen': self.entity_id_counter,
                    'size': (sprite['width'], sprite['height']),
                    'movement_pattern': self._infer_movement_pattern(sprite)
                }
                updated_entities[new_id] = self.entities[new_id]
        
        # Clean up stale entities (not seen in 60 frames)
        current_time = self.entity_id_counter
        stale_ids = [
            eid for eid, entity in self.entities.items()
            if current_time - entity.get('last_seen', 0) > 60
        ]
        for eid in stale_ids:
            del self.entities[eid]
        
        return updated_entities
    
    def _find_matching_entity(self, sprite: Dict) -> str:
        """Find entity ID that matches this sprite position."""
        sprite_center = sprite['center']
        
        for eid, entity in self.entities.items():
            entity_pos = entity.get('position', (0, 0))
            distance = np.linalg.norm(
                np.array(sprite_center) - np.array(entity_pos)
            )
            if distance < 20:  # Within 20 pixels
                return eid
        
        return None
    
    def _infer_movement_pattern(self, sprite: Dict) -> str:
        """Infer how this entity moves based on characteristics."""
        if sprite['type'] == 'NPC':
            return 'WANDER'
        elif sprite['type'] == 'TRAINER':
            return 'STATIONARY'  # Most trainers don't move
        elif sprite['type'] == 'ITEM':
            return 'FLOATING'
        return 'UNKNOWN'
```

---

## 1.4 Semantic Grid Classification

### Overview

The visual world is tiled:
- **Screen:** 160×144 pixels
- **Tiles:** 20×18 tiles of 8×8 pixels each
- **Macro Tiles:** 10×9 blocks of 16×16 pixels (functional game logic)

### Classification Pipeline

```
Raw Frame (160x144)
        ↓
Slice into 16x16 blocks (10x9 grid)
        ↓
For each block:
    ├── Hash pixel data (MD5 or perceptual hash)
    ├── Query TileDatabase (pre-computed)
    ├── If match found → Assign semantic type
    └── If no match → Fallback CNN classifier
        ↓
Semantic Grid Output (10x9 array)
        ↓
Navigation Engine
```

### Implementation

```python
import numpy as np
import hashlib
from typing import Dict, List, Tuple, Optional
from enum import Enum

class SemanticType(Enum):
    """Semantic classification for tiles"""
    WALKABLE = "walkable"
    WALL = "wall"
    WARP = "warp"
    LEDGE = "ledge"
    WATER = "water"
    GRASS = "grass"
    NPC = "npc"
    TRAINER = "trainer"
    ITEM = "item"
    SIGN = "sign"
    UNKNOWN = "unknown"


class TileDatabase:
    """
    Pre-computed database mapping visual hashes to semantic types.
    Built from tile screenshots during initialization.
    """
    
    def __init__(self):
        self.tile_hash_to_type = {}
        self.tile_hash_to_properties = {}
    
    def add_tile(self, tile_pixels: np.ndarray, tile_type: SemanticType, 
                 properties: Dict = None):
        """
        Add a tile to the database.
        
        Args:
            tile_pixels: 16x16 pixel array
            tile_type: Semantic classification
            properties: Additional properties (navigable, encounter_rate, etc.)
        """
        tile_hash = self._compute_tile_hash(tile_pixels)
        self.tile_hash_to_type[tile_hash] = tile_type
        self.tile_hash_to_properties[tile_hash] = properties or {}
    
    def lookup(self, tile_pixels: np.ndarray) -> Tuple[SemanticType, Dict]:
        """
        Look up semantic type for a tile.
        
        Returns:
            (semantic_type, properties)
        """
        tile_hash = self._compute_tile_hash(tile_pixels)
        
        if tile_hash in self.tile_hash_to_type:
            return (
                self.tile_hash_to_type[tile_hash],
                self.tile_hash_to_properties.get(tile_hash, {})
            )
        
        return (SemanticType.UNKNOWN, {})
    
    def _compute_tile_hash(self, tile_pixels: np.ndarray) -> str:
        """
        Compute perceptual hash of tile for matching.
        Uses MD5 for exact matching (could use pHash for tolerance).
        """
        # Resample to consistent size if needed
        if tile_pixels.shape != (16, 16, 3):
            import cv2
            tile_pixels = cv2.resize(tile_pixels, (16, 16))
        
        tile_bytes = tile_pixels.tobytes()
        return hashlib.md5(tile_bytes).hexdigest()


class SemanticGridClassifier:
    """
    Converts raw pixel frame into semantic grid for Navigation Engine.
    """
    
    BLOCK_SIZE = 16  # 16x16 pixel macro tiles
    GRID_WIDTH = 10  # 160 / 16
    GRID_HEIGHT = 9  # 144 / 16
    
    def __init__(self, tile_db: TileDatabase, fallback_classifier=None):
        self.tile_db = tile_db
        self.fallback_classifier = fallback_classifier
    
    def classify_frame(self, frame: np.ndarray) -> np.ndarray:
        """
        Convert frame to semantic grid.
        
        Returns:
            2D array (9x10) of SemanticType enums
        """
        grid = np.empty((self.GRID_HEIGHT, self.GRID_WIDTH), dtype=SemanticType)
        
        for row in range(self.GRID_HEIGHT):
            for col in range(self.GRID_WIDTH):
                # Extract 16x16 block
                y_start = row * self.BLOCK_SIZE
                y_end = y_start + self.BLOCK_SIZE
                x_start = col * self.BLOCK_SIZE
                x_end = x_start + self.BLOCK_SIZE
                
                block = frame[y_start:y_end, x_start:x_end]
                
                # Look up in database
                tile_type, properties = self.tile_db.lookup(block)
                
                # Fallback to CNN if unknown
                if tile_type == SemanticType.UNKNOWN and self.fallback_classifier:
                    tile_type = self.fallback_classifier.classify(block)
                
                grid[row, col] = tile_type
        
        return grid
    
    def get_navigation_grid(self, semantic_grid: np.ndarray) -> np.ndarray:
        """
        Convert semantic grid to binary navigation matrix.
        
        Returns:
            2D array (9x10) where 1 = walkable, 0 = blocked
        """
        navigation_grid = np.ones_like(semantic_grid, dtype=int)
        
        for row in range(semantic_grid.shape[0]):
            for col in range(semantic_grid.shape[1]):
                tile_type = semantic_grid[row, col]
                
                # Non-walkable tile types
                if tile_type in [
                    SemanticType.WALL,
                    SemanticType.WATER,  # Unless Surf available
                    SemanticType.LEDGE,  # Directional - handled separately
                ]:
                    navigation_grid[row, col] = 0
        
        return navigation_grid
    
    def get_ledge_directions(self, semantic_grid: np.ndarray) -> Dict[Tuple[int, int], str]:
        """
        Identify ledges and their allowed traversal directions.
        
        Returns:
            Dict mapping (row, col) to allowed direction ('down', 'right', etc.)
        """
        ledges = {}
        
        for row in range(semantic_grid.shape[0]):
            for col in range(semantic_grid.shape[1]):
                if semantic_grid[row, col] == SemanticType.LEDGE:
                    # Analyze surrounding tiles to determine direction
                    # Typically, ledges allow movement from high to low elevation
                    ledges[(row, col)] = self._determine_ledge_direction(
                        semantic_grid, row, col
                    )
        
        return ledges
    
    def _determine_ledge_direction(self, grid: np.ndarray, 
                                    row: int, col: int) -> str:
        """
        Determine allowed direction for a ledge tile.
        
        Gen 1 ledges are almost always "down" only.
        """
        # Check if we can go down
        if row < grid.shape[0] - 1:
            below_tile = grid[row + 1, col]
            if below_tile != SemanticType.WALL:
                return 'down'
        
        # Check if we can go right
        if col < grid.shape[1] - 1:
            right_tile = grid[row, col + 1]
            if right_tile != SemanticType.WALL:
                return 'right'
        
        # Default to down (most common)
        return 'down'
```

---

## 1.5 OCR and Text Event Detection

### The Problem

Standard OCR (Tesseract) fails on Game Boy pixel fonts:
- Low resolution (8x8 characters)
- Non-standard glyphs (PKMN, symbols)
- Text box overlay patterns

### Template Matching Engine

```python
import numpy as np
from typing import List, Tuple, Dict
import cv2

class GameBoyOCR:
    """
    Custom OCR for Game Boy pixel fonts using template matching.
    Based on OpenCV's matchTemplate function.
    """
    
    def __init__(self):
        # Load character templates during initialization
        self.char_templates = self._load_character_templates()
    
    def _load_character_templates(self) -> Dict[str, np.ndarray]:
        """
        Load reference bitmaps for all Game Boy characters.
        A-Z, 0-9, and special symbols (PKMN, etc.)
        """
        # Templates would be loaded from asset files
        # Each template is an 8x8 binary image of the character
        return {
            'A': self._load_template('assets/chars/A.png'),
            'B': self._load_template('assets/chars/B.png'),
            # ... all uppercase letters
            '0': self._load_template('assets/chars/0.png'),
            '1': self._load_template('assets/chars/1.png'),
            # ... all digits
            ' ': self._load_template('assets/chars/space.png'),
            '?': self._load_template('assets/chars/question.png'),
            '!': self._load_template('assets/chars/exclamation.png'),
            '.': self._load_template('assets/chars/period.png'),
            "'": self._load_template('assets/chars/quote.png'),
            '-': self._load_template('assets/chars/dash.png'),
            # Special Game Boy symbols
            'PK': self._load_template('assets/chars/PK.png'),
            'MN': self._load_template('assets/chars/MN.png'),
        }
    
    def _load_template(self, path: str) -> np.ndarray:
        """Load a character template from file."""
        import cv2
        img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        _, binary = cv2.threshold(img, 128, 255, cv2.THRESH_BINARY)
        return binary
    
    def detect_text_regions(self, frame: np.ndarray) -> List[Dict]:
        """
        Find regions of the screen that contain text.
        Primarily monitors bottom quadrant (y: 104-144) for text boxes.
        """
        import cv2
        
        # Convert to grayscale
        gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
        
        # Look for text box frame (characteristic border pattern)
        # Bottom of screen typically contains dialogue
        bottom_region = gray[104:144, :]
        
        # Detect horizontal lines (text box top/bottom borders)
        _, horizontal_lines = cv2.threshold(
            bottom_region, 200, 255, cv2.THRESH_BINARY_INV
        )
        horizontal_kernel = cv2.getStructuringElement(
            cv2.MORPH_RECT, (20, 1)
        )
        horiz_dilated = cv2.dilate(horizontal_lines, horizontal_kernel)
        horiz_contours, _ = cv2.findContours(
            horiz_dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        
        text_regions = []
        for contour in horiz_contours:
            x, y, w, h = cv2.boundingRect(contour)
            if w > 40 and h > 5:  # Reasonable text box size
                text_regions.append({
                    'x': x,
                    'y': 104 + y,
                    'width': w,
                    'height': h,
                    'type': 'dialogue'
                })
        
        return text_regions
    
    def ocr_region(self, frame: np.ndarray, region: Dict) -> str:
        """
        Perform OCR on a specific screen region.
        
        Args:
            frame: Full screen frame
            region: {'x', 'y', 'width', 'height'} of text region
            
        Returns:
            Extracted text string
        """
        import cv2
        
        # Extract region
        x, y = region['x'], region['y']
        w, h = region['width'], region['height']
        text_region = frame[y:y+h, x:x+w]
        
        # Convert to grayscale and binarize
        gray = cv2.cvtColor(text_region, cv2.COLOR_RGB2GRAY)
        _, binary = cv2.threshold(gray, 128, 255, cv2.THRESH_BINARY_INV)
        
        # Scan character by character
        characters = []
        char_width = 8  # Standard Game Boy character width
        
        for char_x in range(0, w - char_width, char_width):
            char_slice = binary[:, char_x:char_x + char_width]
            
            # Skip empty columns
            if np.sum(char_slice) < 50:
                continue
            
            # Match against templates
            best_match, best_score = None, float('inf')
            for char_name, template in self.char_templates.items():
                # Resize template to match if needed
                if template.shape != char_slice.shape:
                    template_resized = cv2.resize(template, 
                                                 (char_width, h))
                else:
                    template_resized = template
                
                # Template matching (MSE)
                score = np.sum((char_slice.astype(float) - 
                               template_resized.astype(float)) ** 2)
                
                if score < best_score:
                    best_score = score
                    best_match = char_name
            
            # Threshold for acceptable matches
            if best_score < 1000:  # Adjust based on testing
                characters.append(best_match)
        
        # Reconstruct string (group multi-character templates)
        return self._reconstruct_string(characters)
    
    def _reconstruct_string(self, characters: List[str]) -> str:
        """
        Convert character list to string, handling multi-char templates.
        """
        result = ""
        i = 0
        while i < len(characters):
            # Check for multi-character templates
            if i < len(characters) - 1:
                two_char = characters[i] + characters[i + 1]
                if two_char in ['PK', 'MN']:  # Special cases
                    result += "PKMN"[two_char.index(characters[i])]
                    i += 2
                    continue
            
            result += characters[i]
            i += 1
        
        return result


class TextEventDetector:
    """
    Detects game events from OCR text output.
    Maps extracted text to game states and triggers.
    """
    
    # Event keywords and their meanings
    EVENT_KEYWORDS = {
        # Battle events
        'A wild': 'wild_encounter',
        ' wants to fight': 'trainer_battle',
        'What will': 'battle_menu',
        'Go!': 'send_out_pokemon',
        ' caught ': 'pokemon_caught',
        'fainted': 'pokemon_fainted',
        
        # Dialogue events
        ' received ': 'item_received',
        ' obtained ': 'item_obtained',
        'Badge': 'badge_earned',
        
        # Menu events
        'Heal your': 'pokemon_center',
        'Buy': 'mart_menu',
        'Save': 'save_prompt',
        
        # Game over
        'Black': 'blacked_out',
        'Game Over': 'game_over'
    }
    
    def __init__(self, ocr: GameBoyOCR):
        self.ocr = ocr
    
    def detect_events(self, frame: np.ndarray) -> List[Dict]:
        """
        Scan frame for text and extract game events.
        
        Returns:
            List of detected events with confidence scores
        """
        events = []
        
        # Find text regions
        text_regions = self.ocr.detect_text_regions(frame)
        
        for region in text_regions:
            text = self.ocr.ocr_region(frame, region)
            
            # Check for keywords
            for keyword, event_type in self.EVENT_KEYWORDS.items():
                if keyword in text:
                    events.append({
                        'type': event_type,
                        'text': text,
                        'confidence': self._calculate_confidence(text, keyword),
                        'region': region
                    })
        
        return events
    
    def _calculate_confidence(self, text: str, keyword: str) -> float:
        """
        Calculate confidence that the detected event is correct.
        Based on keyword position and surrounding context.
        """
        # Higher confidence if keyword appears at start
        if text.startswith(keyword):
            return 0.95
        elif keyword in text:
            return 0.80
        return 0.0
    
    def parse_dialogue_choice(self, text: str) -> Optional[str]:
        """
        Detect Yes/No choices in dialogue and determine correct answer
        based on current goal context.
        """
        if 'Yes' in text and 'No' in text:
            return 'YES_OR_NO_CHOICE'
        elif 'Yes' in text:
            return 'YES_ONLY'
        elif 'No' in text:
            return 'NO_ONLY'
        return None
```

---

## 1.6 Visual Anomaly and Shake Detection

### The Problem

Visual effects (screen shakes, flashes) cause frame-to-frame noise:
- Poison damage screen shake
- Thunder attack flash
- Critical hit animations
- Entry animations

### Global Optical Flow Monitoring

```python
import numpy as np
from typing import Tuple, Dict

class VisualAnomalyDetector:
    """
    Detects visual anomalies (screen shakes, flashes) that could
    confuse the segmentation and navigation logic.
    """
    
    SHAKE_THRESHOLD = 50  # Pixel shift threshold for "shake"
    FLASH_THRESHOLD = 200  # Brightness change for "flash"
    
    def __init__(self):
        self.last_frame = None
        self.shake_detected = False
        self.flash_detected = False
    
    def analyze_frame(self, frame: np.ndarray) -> Dict:
        """
        Analyze current frame for anomalies.
        
        Returns:
            Dict with 'is_shake', 'is_flash', 'global_shift'
        """
        result = {
            'is_shake': False,
            'is_flash': False,
            'global_shift': (0, 0),
            'anomaly_type': None
        }
        
        if self.last_frame is None:
            self.last_frame = frame
            return result
        
        # Calculate global pixel shift
        shift = self._calculate_global_shift(self.last_frame, frame)
        result['global_shift'] = shift
        
        # Check for shake
        shift_magnitude = np.linalg.norm(shift)
        if shift_magnitude > self.SHAKE_THRESHOLD:
            result['is_shake'] = True
            result['anomaly_type'] = 'shake'
        
        # Check for flash (global brightness change)
        brightness_change = self._calculate_brightness_change(
            self.last_frame, frame
        )
        if brightness_change > self.FLASH_THRESHOLD:
            result['is_flash'] = True
            result['anomaly_type'] = 'flash'
        
        # Update last frame
        self.last_frame = frame
        
        return result
    
    def _calculate_global_shift(self, frame1: np.ndarray, 
                                 frame2: np.ndarray) -> Tuple[int, int]:
        """
        Calculate global pixel shift between two frames.
        Uses phase correlation for sub-pixel accuracy.
        """
        import cv2
        
        # Convert to grayscale
        gray1 = cv2.cvtColor(frame1, cv2.COLOR_RGB2GRAY)
        gray2 = cv2.cvtColor(frame2, cv2.COLOR_RGB2GRAY)
        
        # Calculate phase correlation
        (shifted, _) = cv2.phaseCorrelate(
            gray1.astype(np.float32),
            gray2.astype(np.float32)
        )
        
        return (int(shifted[0]), int(shifted[1]))
    
    def _calculate_brightness_change(self, frame1: np.ndarray,
                                      frame2: np.ndarray) -> float:
        """
        Calculate average brightness change between frames.
        """
        # Convert to grayscale and average
        gray1 = np.mean(frame1)
        gray2 = np.mean(frame2)
        
        return abs(gray2 - gray1)
    
    def should_skip_processing(self, anomaly_result: Dict) -> bool:
        """
        Determine if current frame should be skipped due to anomaly.
        """
        return anomaly_result['is_shake'] or anomaly_result['is_flash']


class PerceptionHold:
    """
    Temporarily suspends perception processing during visual anomalies.
    """
    
    def __init__(self, anomaly_detector: VisualAnomalyDetector):
        self.anomaly_detector = anomaly_detector
        self.hold_counter = 0
        self.max_hold_frames = 10  # Hold for up to 10 frames
    
    def enter_hold(self):
        """Enter perception hold mode."""
        self.hold_counter = self.max_hold_frames
    
    def should_hold(self) -> bool:
        """Check if currently in hold mode."""
        return self.hold_counter > 0
    
    def tick(self):
        """Call each frame to decrement hold counter."""
        if self.hold_counter > 0:
            self.hold_counter -= 1
    
    def process_with_hold(self, frame: np.ndarray) -> Optional[Dict]:
        """
        Process frame, returning None if in hold mode.
        """
        if self.should_hold():
            self.tick()
            return None
        
        anomaly = self.anomaly_detector.analyze_frame(frame)
        
        if anomaly['is_shake'] or anomaly['is_flash']:
            self.enter_hold()
            return None
        
        # Normal processing would continue here
        return anomaly
```

---

## 1.7 Data Fusion: Visual-Memory Reconciliation

### Overview

Final stage of Perception Layer: **fuse Visual data with Memory data**

```
┌─────────────────────────────────────────────────────────────┐
│                    DATA FUSION ENGINE                        │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  VISION LAYER                    MEMORY LAYER                 │
│  ─────────────                   ────────────                 │
│  • Semantic Grid                 • Player coords ($D362,$D361)│
│  • Detected entities             • Map ID ($D35E)             │
│  • OCR text                      • Battle status ($D057)      │
│  • Visual anomalies              • Party data                 │
│                                                              │
│                           │                                  │
│                           ▼                                  │
│              ┌─────────────────────────────┐                 │
│              │   CONFLICT RESOLUTION       │                 │
│              │                             │                 │
│              │ • Compare positions         │                 │
│              │ • Check map ID match        │                 │
│              │ • Validate entity locations │                 │
│              └─────────────────────────────┘                 │
│                           │                                  │
│                           ▼                                  │
│              ┌─────────────────────────────┐                 │
│              │   STATE RECONCILIATION      │                 │
│              │                             │                 │
│              │ • Aligned: Use combined     │                 │
│              │ • Conflict: Re-localize     │                 │
│              │ • Log anomaly for review    │                 │
│              └─────────────────────────────┘                 │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Implementation

```python
from typing import Dict, Tuple, Optional, List

class VisualMemoryFusion:
    """
    Fuses visual perception data with memory state for
    reconciliation and validation.
    """
    
    def __init__(self, 
                 semantic_classifier,
                 memory_interface,
                 anomaly_detector: VisualAnomalyDetector):
        self.semantic_classifier = semantic_classifier
        self.memory = memory_interface
        self.anomaly_detector = anomaly_detector
        self.desync_counter = 0
        self.max_desync_count = 3
    
    def fuse_data(self, frame: np.ndarray) -> Dict:
        """
        Combine visual and memory data into unified state.
        
        Returns:
            Unified state dict with position, map, entities, etc.
        """
        # Get visual data
        semantic_grid = self.semantic_classifier.classify_frame(frame)
        entities = self.semantic_classifier.segment_sprites(frame)
        
        # Get memory data
        mem_position = self.memory.get_player_position()
        mem_map_id = self.memory.get_current_map()
        mem_battle_status = self.memory.is_in_battle()
        
        # Detect visual anomalies
        anomaly = self.anomaly_detector.analyze_frame(frame)
        
        # Reconcile data
        position = self._reconcile_position(
            semantic_grid, mem_position, entities
        )
        map_match = self._check_map_consistency(semantic_grid, mem_map_id)
        
        # Build unified state
        unified_state = {
            'visual': {
                'semantic_grid': semantic_grid,
                'entities': entities,
                'anomaly': anomaly,
            },
            'memory': {
                'position': mem_position,
                'map_id': mem_map_id,
                'in_battle': mem_battle_status,
            },
            'reconciled': {
                'position': position,
                'map_consistent': map_match,
                'confidence': self._calculate_confidence(
                    semantic_grid, mem_position, position
                )
            }
        }
        
        # Handle conflicts
        if not map_match:
            self._handle_desync(semantic_grid, mem_map_id)
        
        return unified_state
    
    def _reconcile_position(self,
                            semantic_grid: np.ndarray,
                            mem_position: Tuple[int, int],
                            entities: List[Dict]) -> Tuple[int, int]:
        """
        Reconcile visual and memory position data.
        Memory is authoritative for exact coordinates.
        """
        # Memory gives us the "true" position
        return mem_position
    
    def _check_map_consistency(self, 
                               semantic_grid: np.ndarray,
                               mem_map_id: int) -> bool:
        """
        Check if visual grid matches memory map ID.
        Returns False if mismatch (possible desync).
        """
        # This would use a visual classifier trained on map boundaries
        # For now, we trust memory unless strong visual evidence otherwise
        return True  # Simplified - would be more complex in production
    
    def _handle_desync(self, semantic_grid: np.ndarray, 
                       mem_map_id: int):
        """
        Handle detected visual-memory desynchronization.
        
        Protocol:
        1. Log the anomaly
        2. Trigger re-localization protocol
        3. Reset anomaly detector
        """
        self.desync_counter += 1
        
        if self.desync_counter >= self.max_desync_count:
            # Persistent desync - trigger recovery
            self._trigger_relocalization_protocol()
            self.desync_counter = 0
    
    def _trigger_relocalization_protocol(self):
        """
        Re-localize agent by rescanning environment.
        
        Steps:
        1. Pause action inputs
        2. Capture current frame
        3. Run full visual analysis
        4. Compare with memory
        5. Determine root cause
        6. Resume or fail-safe
        """
        # Implementation would pause the game loop,
        # perform intensive visual analysis,
        # and either resume or trigger failsafe
        pass
    
    def _calculate_confidence(self,
                              semantic_grid: np.ndarray,
                              mem_position: Tuple[int, int],
                              reconciled_position: Tuple[int, int]) -> float:
        """
        Calculate confidence score for reconciled state.
        Higher = more confident.
        """
        # Base confidence from memory reliability
        confidence = 0.95
        
        # Reduce confidence if recent desyncs
        confidence -= (self.desync_counter * 0.05)
        
        return max(0.0, min(1.0, confidence))
```

---

## 1.8 Complete Perception Pipeline

```python
class PerceptionPipeline:
    """
    Complete perception pipeline integrating all components.
    Main entry point for visual input processing.
    """
    
    def __init__(self, pyboy, memory_interface):
        self.pyboy = pyboy
        self.memory = memory_interface
        
        # Initialize all components
        self.pixel_acquisition = PixelBufferAcquisition(pyboy)
        self.color_quantizer = ColorQuantizer()
        self.denoise_filter = VisualNoiseFilter(self.color_quantizer)
        self.tile_db = TileDatabase()
        self.semantic_classifier = SemanticGridClassifier(self.tile_db)
        self.entity_tracker = EntityTracker()
        self.ocr = GameBoyOCR()
        self.text_detector = TextEventDetector(self.ocr)
        self.anomaly_detector = VisualAnomalyDetector()
        self.perception_hold = PerceptionHold(self.anomaly_detector)
        self.data_fusion = VisualMemoryFusion(
            self.semantic_classifier, memory_interface, self.anomaly_detector
        )
    
    def tick(self) -> Dict:
        """
        Execute one perception tick.
        
        Returns:
            Unified state dict containing all perceived information
        """
        # 1. Acquire frame
        frame = self.pixel_acquisition.tick()
        
        # 2. Skip if in anomaly hold
        if self.perception_hold.should_hold():
            return {'status': 'hold', 'frame': frame}
        
        # 3. Process with anomaly detection
        anomaly = self.anomaly_detector.analyze_frame(frame)
        if anomaly['anomaly_type']:
            return {'status': 'anomaly', 'anomaly': anomaly}
        
        # 4. Quantize and denoise
        quantized = self.color_quantizer.quantize(frame)
        denoised = self.denoise_filter.denoise_frame(frame)
        
        # 5. Classify semantic grid
        semantic_grid = self.semantic_classifier.classify_frame(denoised)
        
        # 6. Segment entities
        sprites = self.semantic_classifier.segment_sprites(denoised)
        entities = self.entity_tracker.update(sprites)
        
        # 7. OCR and text detection
        text_events = self.text_detector.detect_events(denoised)
        
        # 8. Fuse with memory
        unified_state = self.data_fusion.fuse_data(denoised)
        
        # Build final output
        return {
            'status': 'success',
            'frame': frame,
            'quantized': quantized,
            'semantic_grid': semantic_grid,
            'entities': entities,
            'text_events': text_events,
            'anomaly': anomaly,
            'unified': unified_state
        }
    
    def get_navigation_input(self) -> Dict:
        """
        Get processed data specifically for Navigation Engine.
        """
        result = self.tick()
        
        if result['status'] != 'success':
            return {'ready': False, 'reason': result['status']}
        
        return {
            'ready': True,
            'semantic_grid': result['semantic_grid'],
            'entities': result['entities'],
            'position': result['unified']['reconciled']['position'],
            'confidence': result['unified']['reconciled']['confidence']
        }
```

---

## Summary

| Section | Purpose | Key Components |
|---------|---------|----------------|
| **1.1 Pixel Buffer** | Synchronous frame capture | PyBoy API, Tick-Read-Act cycle |
| **1.2 Color Quantization** | 4-color palette normalization | Euclidean distance matching |
| **1.3 Sprite Segmentation** | Entity detection | Difference masking, OAM parsing |
| **1.4 Semantic Grid** | Tile classification | Hash-matching, TileDatabase |
| **1.5 OCR** | Text extraction | Template matching, Event detection |
| **1.6 Anomaly Detection** | Shake/flash handling | Optical flow, Global shift |
| **1.7 Data Fusion** | Visual-Memory reconciliation | Conflict resolution, Re-localization |
| **1.8 Pipeline** | Integration | Complete Perception Pipeline class |

---

**Document Version:** 1.0  
**Last Updated:** December 31, 2025  
**Protocol:** PTP-01X - Chapter 1: Perception Layer  
**Source:** Pallet Town Protocol Master Architectural Schema