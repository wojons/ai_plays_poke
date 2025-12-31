"""
Vision Pipeline - Screenshot Preprocessing and Normalization

Handles pixel buffer normalization, color space conversion, and ROI extraction
for optimal vision model input.
"""

import hashlib
import time
from typing import Optional, Tuple, Union
from dataclasses import dataclass
from pathlib import Path
import signal

import numpy as np
from PIL import Image, ImageOps


@dataclass
class ScreenshotValidationError(Exception):
    """Exception raised for screenshot validation errors"""
    message: str
    error_type: str = "validation_error"


@dataclass
class ScreenshotProcessingError(Exception):
    """Exception raised for screenshot processing errors"""
    message: str
    error_type: str = "processing_error"


@dataclass
class PreprocessingResult:
    """Result of screenshot preprocessing"""
    normalized_image: np.ndarray
    grayscale_image: np.ndarray
    roi_battle_menu: Optional[np.ndarray] = None
    roi_dialog_box: Optional[np.ndarray] = None
    roi_hud: Optional[np.ndarray] = None
    processing_time_ms: float = 0.0
    frame_hash: str = ""
    is_duplicate: bool = False
    aspect_ratio: float = 1.0


class VisionPipeline:
    """
    Preprocesses game screenshots for vision analysis
    
    Pipeline stages:
    1. Raw capture validation
    2. Aspect ratio normalization
    3. Color space conversion
    4. ROI extraction
    5. Quality assessment
    """
    
    TARGET_SIZE = (224, 224)
    NATIVE_RESOLUTION = (160, 144)
    ASPECT_RATIO = 160 / 144
    DEFAULT_TIMEOUT = 30.0
    
    def __init__(self, debug_dir: Optional[str] = None):
        """Initialize Vision Pipeline"""
        self.debug_dir = Path(debug_dir) if debug_dir else None
        self.frame_history: list = []
        self.max_history = 10
        self._stuck_counter = 0
        
        if self.debug_dir:
            self.debug_dir.mkdir(parents=True, exist_ok=True)
    
    def validate_screenshot_dimensions(self, image: np.ndarray) -> None:
        """
        Validate that screenshot has correct dimensions (160x144 for Game Boy)
        
        Args:
            image: Input screenshot array
            
        Raises:
            ScreenshotValidationError: If dimensions are incorrect
        """
        if image is None or image.size == 0:
            raise ScreenshotValidationError(
                message="Screenshot is empty or None",
                error_type="empty_screenshot"
            )
        
        height, width = image.shape[:2]
        expected_width, expected_height = self.NATIVE_RESOLUTION
        
        if width != expected_width or height != expected_height:
            raise ScreenshotValidationError(
                message=f"Screenshot has wrong dimensions: got {width}x{height}, "
                        f"expected {expected_width}x{expected_height}",
                error_type="wrong_dimensions"
            )
    
    def validate_screenshot_dtype(self, image: np.ndarray) -> None:
        """
        Validate that screenshot has correct data type (uint8)
        
        Args:
            image: Input screenshot array
            
        Raises:
            TypeError: If dtype is incorrect
        """
        if image.dtype != np.uint8:
            raise TypeError(
                f"Screenshot has wrong dtype: got {image.dtype}, expected uint8"
            )
    
    def validate_pixel_data(self, image: np.ndarray) -> None:
        """
        Validate that screenshot pixel data is valid (no NaN, infinity, out-of-range values)
        
        Args:
            image: Input screenshot array
            
        Raises:
            ScreenshotValidationError: If pixel data is corrupted or invalid
        """
        if not np.isfinite(image).all():
            raise ScreenshotValidationError(
                message="Screenshot contains NaN or infinity values",
                error_type="corrupted_pixel_data"
            )
        
        if image.size > 0:
            min_val = np.min(image)
            max_val = np.max(image)
            if min_val < 0 or max_val > 255:
                raise ScreenshotValidationError(
                    message=f"Screenshot has out-of-range pixel values: "
                            f"min={min_val}, max={max_val}, expected [0, 255]",
                    error_type="corrupted_pixel_data"
                )
    
    def validate_screenshot(self, image: np.ndarray) -> None:
        """
        Complete validation of screenshot input
        
        Args:
            image: Input screenshot array
            
        Raises:
            ScreenshotValidationError: If any validation fails
        """
        self.validate_screenshot_dimensions(image)
        self.validate_screenshot_dtype(image)
        self.validate_pixel_data(image)
    
    def process(
        self, 
        raw_screenshot: np.ndarray,
        extract_rois: bool = True,
        timeout: Optional[float] = None
    ) -> PreprocessingResult:
        """
        Process a screenshot through the full pipeline
        
        Args:
            raw_screenshot: Input screenshot array (must be 160x144 uint8)
            extract_rois: Whether to extract regions of interest
            timeout: Optional timeout in seconds for processing
            
        Returns:
            PreprocessingResult with processed image data
            
        Raises:
            ScreenshotValidationError: If input validation fails
            ScreenshotProcessingError: If processing times out
        """
        self.validate_screenshot(raw_screenshot)
        
        start_time = time.perf_counter()
        
        try:
            frame_hash = self._compute_frame_hash(raw_screenshot)
            is_duplicate = self._check_duplicate(frame_hash)
            
            aspect_ratio = raw_screenshot.shape[1] / raw_screenshot.shape[0]
            
            normalized = self._normalize_aspect_ratio(raw_screenshot)
            grayscale = self._convert_to_grayscale(normalized)
            resized = self._resize_to_target(grayscale)
            
            roi_battle_menu = None
            roi_dialog_box = None
            roi_hud = None
            
            if extract_rois:
                roi_battle_menu = self._extract_battle_menu(resized)
                roi_dialog_box = self._extract_dialog_box(resized)
                roi_hud = self._extract_hud(resized)
            
            processing_time = (time.perf_counter() - start_time) * 1000
            
            result = PreprocessingResult(
                normalized_image=resized,
                grayscale_image=grayscale,
                roi_battle_menu=roi_battle_menu,
                roi_dialog_box=roi_dialog_box,
                roi_hud=roi_hud,
                processing_time_ms=processing_time,
                frame_hash=frame_hash,
                is_duplicate=is_duplicate,
                aspect_ratio=aspect_ratio
            )
            
            self._update_frame_history(frame_hash)
            
            return result
            
        except (ValueError, TypeError, ScreenshotValidationError):
            raise
        except Exception as e:
            raise ScreenshotProcessingError(
                message=f"Processing failed: {str(e)}",
                error_type="processing_error"
            ) from e
    
    def process_with_timeout(
        self,
        raw_screenshot: np.ndarray,
        timeout: float = DEFAULT_TIMEOUT,
        extract_rois: bool = True
    ) -> PreprocessingResult:
        """
        Process a screenshot with timeout protection
        
        Args:
            raw_screenshot: Input screenshot array
            timeout: Timeout in seconds (default 30.0)
            extract_rois: Whether to extract regions of interest
            
        Returns:
            PreprocessingResult with processed image data
            
        Raises:
            ScreenshotProcessingError: If processing times out
            ScreenshotValidationError: If input validation fails
        """
        self.validate_screenshot(raw_screenshot)
        
        def timeout_handler(signum, frame):
            raise ScreenshotProcessingError(
                message=f"Screenshot processing timed out after {timeout} seconds",
                error_type="timeout"
            )
        
        old_handler = signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(int(timeout))
        
        try:
            result = self.process(raw_screenshot, extract_rois=extract_rois)
            return result
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)
    
    def _compute_frame_hash(self, frame: np.ndarray) -> str:
        """Compute perceptual hash of frame for duplicate detection"""
        if len(frame.shape) == 3:
            frame = self._convert_to_grayscale(frame)
        
        resized = self._resize_to_target(frame, (16, 16))
        resized_float = resized.astype(np.float32) / 255.0
        dct_low = self._simple_dct_2d(resized_float)[:8, :8]
        
        median = np.median(dct_low)
        hash_bits = (dct_low > median).astype(int)
        hash_str = ''.join(str(b) for b in hash_bits.flatten())
        return hashlib.md5(hash_str.encode()).hexdigest()[:16]
    
    def _simple_dct_2d(self, block: np.ndarray) -> np.ndarray:
        """Simple 2D DCT implementation using numpy"""
        n, m = block.shape
        result = np.zeros_like(block, dtype=np.float32)
        
        for u in range(n):
            for v in range(m):
                sum_val = 0.0
                for x in range(n):
                    for y in range(m):
                        cos_x = np.cos((2 * x + 1) * u * np.pi / (2 * n))
                        cos_y = np.cos((2 * y + 1) * v * np.pi / (2 * m))
                        sum_val += block[x, y] * cos_x * cos_y
                
                cu = 1.0 if u > 0 else 1.0 / np.sqrt(2)
                cv = 1.0 if v > 0 else 1.0 / np.sqrt(2)
                result[u, v] = 0.25 * cu * cv * sum_val
        
        return result
    
    def _check_duplicate(self, frame_hash: str) -> bool:
        """Check if frame is duplicate of recent frames"""
        for recent_hash in self.frame_history[-3:]:
            if recent_hash == frame_hash:
                self._stuck_counter += 1
                return True
        return False
    
    def _update_frame_history(self, frame_hash: str):
        """Update frame history for duplicate detection"""
        self.frame_history.append(frame_hash)
        if len(self.frame_history) > self.max_history:
            self.frame_history.pop(0)
        if not self._is_frame_changed():
            self._stuck_counter += 1
        else:
            self._stuck_counter = 0
    
    def _is_frame_changed(self) -> bool:
        """Check if any frame changed since last check"""
        if len(self.frame_history) < 2:
            return True
        return self.frame_history[-1] != self.frame_history[-2]
    
    def _normalize_aspect_ratio(self, frame: np.ndarray) -> np.ndarray:
        """Normalize frame to 4:3 aspect ratio"""
        height, width = frame.shape[:2]
        current_ratio = width / height
        
        if abs(current_ratio - self.ASPECT_RATIO) < 0.01:
            return frame
        
        if current_ratio > self.ASPECT_RATIO:
            target_width = int(height * self.ASPECT_RATIO)
            left_pad = (width - target_width) // 2
            frame = frame[:, left_pad:left_pad + target_width]
        else:
            target_height = int(width / self.ASPECT_RATIO)
            top_pad = (height - target_height) // 2
            frame = frame[top_pad:top_pad + target_height, :]
        
        return frame
    
    def _convert_to_grayscale(self, frame: np.ndarray) -> np.ndarray:
        """Convert RGB to grayscale using luminance formula"""
        if len(frame.shape) == 2:
            return frame
        
        if frame.shape[2] == 4:
            frame = frame[:, :, :3]
        
        r = frame[:, :, 0].astype(np.float32)
        g = frame[:, :, 1].astype(np.float32)
        b = frame[:, :, 2].astype(np.float32)
        
        gray = (0.299 * r + 0.587 * g + 0.114 * b).astype(np.uint8)
        
        return gray
    
    def _resize_to_target(
        self, 
        frame: np.ndarray, 
        size: Optional[Tuple[int, int]] = None
    ) -> np.ndarray:
        """Resize frame to target dimensions for vision model"""
        target = size or self.TARGET_SIZE
        
        pil_img = Image.fromarray(frame)
        resized = ImageOps.contain(pil_img, target, method=Image.Resampling.LANCZOS)
        
        result = np.array(resized)
        
        if result.shape[:2] != target[::-1]:
            result = np.array(resized.resize(target, Image.Resampling.LANCZOS))
        
        return result
    
    def _extract_battle_menu(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """Extract battle menu region from frame"""
        h, w = frame.shape[:2]
        
        menu_regions = [
            (int(h * 0.85), h, int(w * 0.5), w),
            (int(h * 0.7), h, 0, int(w * 0.5)),
        ]
        
        for y1, y2, x1, x2 in menu_regions:
            if 0 <= x1 < x2 <= w and 0 <= y1 < y2 <= h:
                return frame[y1:y2, x1:x2]
        
        return None
    
    def _extract_dialog_box(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """Extract dialog box region from frame"""
        h, w = frame.shape[:2]
        
        dialog_candidates = [
            (int(h * 0.6), h, 0, w),
            (int(h * 0.7), h, 0, w),
        ]
        
        for y1, y2, x1, x2 in dialog_candidates:
            if 0 <= x1 < x2 <= w and 0 <= y1 < y2 <= h:
                return frame[y1:y2, x1:x2]
        
        return None
    
    def _extract_hud(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """Extract HUD (heads-up display) region from frame"""
        h, w = frame.shape[:2]
        
        hud_regions = [
            (0, int(h * 0.15), 0, w),
            (0, int(h * 0.2), int(w * 0.6), w),
        ]
        
        for y1, y2, x1, x2 in hud_regions:
            if 0 <= x1 < x2 <= w and 0 <= y1 < y2 <= h:
                return frame[y1:y2, x1:x2]
        
        return None
    
    def detect_softlock(self) -> bool:
        """Detect potential softlock condition"""
        return self._stuck_counter > 10
    
    def reset_softlock_counter(self):
        """Reset softlock detection counter"""
        self._stuck_counter = 0
    
    def get_stuck_counter(self) -> int:
        """Get current stuck counter value"""
        return self._stuck_counter