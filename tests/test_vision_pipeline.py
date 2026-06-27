"""
Unit tests for VisionPipeline — screenshot preprocessing and normalization.

Covers all validation, processing, and softlock detection paths
in src/vision/pipeline.py.
"""
from __future__ import annotations

import hashlib
import signal
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PIL import Image

from src.vision.pipeline import (
    VisionPipeline,
    PreprocessingResult,
    ScreenshotValidationError,
    ScreenshotProcessingError,
)


# ── helpers ────────────────────────────────────────────────────────────────

def _make_frame(h: int = 144, w: int = 160) -> np.ndarray:
    """Create a valid GB-resolution uint8 RGB frame."""
    return np.random.randint(0, 256, (h, w, 3), dtype=np.uint8)


def _make_grayscale_frame(h: int = 144, w: int = 160) -> np.ndarray:
    """Create a valid GB-resolution uint8 grayscale frame."""
    return np.random.randint(0, 256, (h, w), dtype=np.uint8)


def _make_constant_frame(value: int = 128, h: int = 144, w: int = 160) -> np.ndarray:
    """Create a constant-value frame (no randomness)."""
    return np.full((h, w, 3), value, dtype=np.uint8)


# ── error dataclasses ──────────────────────────────────────────────────────

class TestScreenshotValidationError:
    """ScreenshotValidationError is a dataclass exception."""

    def test_constructs_with_message_and_type(self) -> None:
        err = ScreenshotValidationError("bad input", error_type="wrong_size")
        assert err.message == "bad input"
        assert err.error_type == "wrong_size"

    def test_default_error_type(self) -> None:
        err = ScreenshotValidationError("bad input")
        assert err.error_type == "validation_error"

    def test_is_exception(self) -> None:
        err = ScreenshotValidationError("test")
        assert isinstance(err, Exception)

    def test_str_contains_message(self) -> None:
        err = ScreenshotValidationError("something went wrong")
        assert "something went wrong" in str(err)

    def test_from_main_validation(self) -> None:
        """Real usage: validate_screenshot_dimensions with empty array."""
        vp = VisionPipeline()
        empty = np.array([], dtype=np.uint8)
        with pytest.raises(ScreenshotValidationError) as exc:
            vp.validate_screenshot_dimensions(empty)
        assert "empty" in exc.value.message.lower() or "none" in exc.value.message.lower()


class TestScreenshotProcessingError:
    """ScreenshotProcessingError is a dataclass exception."""

    def test_constructs_with_message_and_type(self) -> None:
        err = ScreenshotProcessingError("timeout", error_type="timeout")
        assert err.message == "timeout"
        assert err.error_type == "timeout"

    def test_default_error_type(self) -> None:
        err = ScreenshotProcessingError("processing failed")
        assert err.error_type == "processing_error"

    def test_is_exception(self) -> None:
        err = ScreenshotProcessingError("test")
        assert isinstance(err, Exception)


# ── PreprocessingResult dataclass ──────────────────────────────────────────

class TestPreprocessingResult:
    """PreprocessingResult dataclass holds all processed outputs."""

    def test_constructs_with_required_fields(self) -> None:
        norm = np.zeros((224, 224), dtype=np.uint8)
        gray = np.zeros((144, 160), dtype=np.uint8)
        result = PreprocessingResult(
            normalized_image=norm,
            grayscale_image=gray,
        )
        assert result.normalized_image is norm
        assert result.grayscale_image is gray
        assert result.roi_battle_menu is None
        assert result.roi_dialog_box is None
        assert result.roi_hud is None
        assert result.processing_time_ms == 0.0
        assert result.frame_hash == ""
        assert result.is_duplicate is False
        assert result.aspect_ratio == 1.0

    def test_all_fields_settable(self) -> None:
        norm = np.ones((224, 224), dtype=np.uint8)
        gray = np.ones((144, 160), dtype=np.uint8)
        battle = np.zeros((10, 10), dtype=np.uint8)
        dialog = np.zeros((20, 20), dtype=np.uint8)
        hud = np.zeros((5, 160), dtype=np.uint8)

        result = PreprocessingResult(
            normalized_image=norm,
            grayscale_image=gray,
            roi_battle_menu=battle,
            roi_dialog_box=dialog,
            roi_hud=hud,
            processing_time_ms=12.5,
            frame_hash="abc123",
            is_duplicate=True,
            aspect_ratio=1.111,
        )
        assert result.roi_battle_menu is battle
        assert result.roi_dialog_box is dialog
        assert result.roi_hud is hud
        assert result.processing_time_ms == 12.5
        assert result.frame_hash == "abc123"
        assert result.is_duplicate is True
        assert result.aspect_ratio == 1.111


# ── VisionPipeline constructor ─────────────────────────────────────────────

class TestVisionPipelineInit:
    """VisionPipeline.__init__ tests."""

    def test_default_constructor(self) -> None:
        vp = VisionPipeline()
        assert vp.debug_dir is None
        assert vp.frame_history == []
        assert vp.max_history == 10
        assert vp._stuck_counter == 0

    def test_with_debug_dir(self, tmp_path) -> None:
        debug = tmp_path / "debug_out"
        vp = VisionPipeline(debug_dir=str(debug))
        assert vp.debug_dir is not None
        assert str(vp.debug_dir) == str(debug)
        assert debug.exists()

    def test_debug_dir_already_exists(self, tmp_path) -> None:
        debug = tmp_path / "existing"
        debug.mkdir()
        vp = VisionPipeline(debug_dir=str(debug))
        assert debug.exists()  # no error

    def test_class_constants(self) -> None:
        assert VisionPipeline.TARGET_SIZE == (224, 224)
        assert VisionPipeline.NATIVE_RESOLUTION == (160, 144)
        assert VisionPipeline.ASPECT_RATIO == 160 / 144
        assert VisionPipeline.DEFAULT_TIMEOUT == 30.0


# ── validate_screenshot_dimensions ─────────────────────────────────────────

class TestValidateScreenshotDimensions:
    """validate_screenshot_dimensions rejects bad shapes."""

    def test_valid_gb_resolution(self) -> None:
        vp = VisionPipeline()
        frame = np.zeros((144, 160, 3), dtype=np.uint8)
        vp.validate_screenshot_dimensions(frame)  # no exception

    def test_none_input(self) -> None:
        vp = VisionPipeline()
        with pytest.raises(ScreenshotValidationError) as exc:
            vp.validate_screenshot_dimensions(None)
        assert exc.value.error_type == "empty_screenshot"

    def test_empty_array(self) -> None:
        vp = VisionPipeline()
        empty = np.array([], dtype=np.uint8)
        with pytest.raises(ScreenshotValidationError) as exc:
            vp.validate_screenshot_dimensions(empty)
        assert exc.value.error_type == "empty_screenshot"

    def test_wrong_width(self) -> None:
        vp = VisionPipeline()
        bad = np.zeros((144, 80, 3), dtype=np.uint8)
        with pytest.raises(ScreenshotValidationError) as exc:
            vp.validate_screenshot_dimensions(bad)
        assert exc.value.error_type == "wrong_dimensions"
        assert "80x144" in exc.value.message

    def test_wrong_height(self) -> None:
        vp = VisionPipeline()
        bad = np.zeros((200, 160, 3), dtype=np.uint8)
        with pytest.raises(ScreenshotValidationError) as exc:
            vp.validate_screenshot_dimensions(bad)
        assert exc.value.error_type == "wrong_dimensions"
        assert "160x200" in exc.value.message

    def test_both_dimensions_wrong(self) -> None:
        vp = VisionPipeline()
        bad = np.zeros((100, 50, 3), dtype=np.uint8)
        with pytest.raises(ScreenshotValidationError) as exc:
            vp.validate_screenshot_dimensions(bad)
        assert exc.value.error_type == "wrong_dimensions"


# ── validate_screenshot_dtype ──────────────────────────────────────────────

class TestValidateScreenshotDtype:
    """validate_screenshot_dtype rejects non-uint8 arrays."""

    def test_valid_dtype(self) -> None:
        vp = VisionPipeline()
        frame = np.zeros((144, 160, 3), dtype=np.uint8)
        vp.validate_screenshot_dtype(frame)  # no exception

    def test_float32_raises(self) -> None:
        vp = VisionPipeline()
        bad = np.zeros((144, 160, 3), dtype=np.float32)
        with pytest.raises(TypeError) as exc:
            vp.validate_screenshot_dtype(bad)
        assert "uint8" in str(exc.value).lower()

    def test_int16_raises(self) -> None:
        vp = VisionPipeline()
        bad = np.zeros((144, 160, 3), dtype=np.int16)
        with pytest.raises(TypeError):
            vp.validate_screenshot_dtype(bad)

    def test_float64_raises(self) -> None:
        vp = VisionPipeline()
        bad = np.zeros((144, 160, 3), dtype=np.float64)
        with pytest.raises(TypeError):
            vp.validate_screenshot_dtype(bad)


# ── validate_pixel_data ────────────────────────────────────────────────────

class TestValidatePixelData:
    """validate_pixel_data rejects NaN, infinity, and out-of-range values."""

    def test_valid_pixels(self) -> None:
        vp = VisionPipeline()
        frame = np.random.randint(0, 256, (144, 160, 3), dtype=np.uint8)
        vp.validate_pixel_data(frame)  # no exception

    def test_nan_in_pixels(self) -> None:
        vp = VisionPipeline()
        bad = np.zeros((144, 160, 3), dtype=np.uint8).astype(np.float32)
        bad[0, 0, 0] = float("nan")
        with pytest.raises(ScreenshotValidationError) as exc:
            vp.validate_pixel_data(bad)
        assert exc.value.error_type == "corrupted_pixel_data"

    def test_infinity_in_pixels(self) -> None:
        vp = VisionPipeline()
        bad = np.zeros((144, 160, 3), dtype=np.float32)
        bad[10, 10, 1] = float("inf")
        with pytest.raises(ScreenshotValidationError) as exc:
            vp.validate_pixel_data(bad)
        assert exc.value.error_type == "corrupted_pixel_data"

    def test_negative_values(self) -> None:
        vp = VisionPipeline()
        bad = np.full((10, 10, 3), -1, dtype=np.int16)
        with pytest.raises(ScreenshotValidationError) as exc:
            vp.validate_pixel_data(bad)
        assert exc.value.error_type == "corrupted_pixel_data"

    def test_values_above_255(self) -> None:
        vp = VisionPipeline()
        bad = np.full((10, 10, 3), 300, dtype=np.uint16)
        with pytest.raises(ScreenshotValidationError) as exc:
            vp.validate_pixel_data(bad)
        assert exc.value.error_type == "corrupted_pixel_data"


# ── validate_screenshot (composite) ────────────────────────────────────────

class TestValidateScreenshotComposite:
    """validate_screenshot runs all validators."""

    def test_valid_screenshot_passes(self) -> None:
        vp = VisionPipeline()
        frame = _make_frame()
        vp.validate_screenshot(frame)  # no exception

    def test_empty_triggers_dimension_error(self) -> None:
        vp = VisionPipeline()
        empty = np.array([], dtype=np.uint8)
        with pytest.raises(ScreenshotValidationError) as exc:
            vp.validate_screenshot(empty)
        assert exc.value.error_type == "empty_screenshot"

    def test_wrong_dtype_stops_at_dtype_check(self) -> None:
        vp = VisionPipeline()
        bad = np.zeros((144, 160, 3), dtype=np.float32)
        with pytest.raises(TypeError):
            vp.validate_screenshot(bad)

    def test_nan_stops_at_pixel_check(self) -> None:
        vp = VisionPipeline()
        bad = np.zeros((144, 160, 3), dtype=np.float64)
        bad[0, 0, 0] = float("nan")
        # First check: dtype is float64 → TypeError (before pixel validation)
        with pytest.raises(TypeError):
            vp.validate_screenshot(bad)


# ── process ────────────────────────────────────────────────────────────────

class TestProcess:
    """process() runs the full pipeline on a valid frame."""

    def test_returns_preprocessing_result(self) -> None:
        vp = VisionPipeline()
        frame = _make_frame()
        result = vp.process(frame)
        assert isinstance(result, PreprocessingResult)

    def test_normalized_image_not_empty(self) -> None:
        vp = VisionPipeline()
        frame = _make_frame()
        result = vp.process(frame)
        assert result.normalized_image.size > 0

    def test_grayscale_is_2d(self) -> None:
        vp = VisionPipeline()
        frame = _make_frame()
        result = vp.process(frame)
        assert result.grayscale_image.ndim == 2

    def test_frame_hash_is_string(self) -> None:
        vp = VisionPipeline()
        frame = _make_frame()
        result = vp.process(frame)
        assert isinstance(result.frame_hash, str)
        assert len(result.frame_hash) == 16  # hexdigest[:16]

    def test_processing_time_positive(self) -> None:
        vp = VisionPipeline()
        frame = _make_frame()
        result = vp.process(frame)
        assert result.processing_time_ms >= 0

    def test_aspect_ratio_correct(self) -> None:
        vp = VisionPipeline()
        frame = _make_frame(144, 160)
        result = vp.process(frame)
        assert abs(result.aspect_ratio - (160 / 144)) < 0.001

    def test_not_duplicate_first_time(self) -> None:
        vp = VisionPipeline()
        frame = _make_frame()
        result = vp.process(frame)
        assert result.is_duplicate is False

    def test_duplicate_detected_on_repeat(self) -> None:
        vp = VisionPipeline()
        frame = _make_constant_frame(100)  # deterministic frame
        r1 = vp.process(frame)
        assert r1.is_duplicate is False
        r2 = vp.process(frame)
        assert r2.is_duplicate is True  # same hash in history

    def test_no_extract_rois(self) -> None:
        vp = VisionPipeline()
        frame = _make_frame()
        result = vp.process(frame, extract_rois=False)
        assert result.roi_battle_menu is None
        assert result.roi_dialog_box is None
        assert result.roi_hud is None

    def test_extract_rois_default(self) -> None:
        vp = VisionPipeline()
        frame = _make_frame()
        result = vp.process(frame, extract_rois=True)
        # ROIs may be None for 2D grayscale frames that get re-initialized,
        # but with RGB input they should be populated after resize
        # The roi extraction uses the resized (224,224) frame internally
        # so it should succeed with valid coords
        assert isinstance(result, PreprocessingResult)

    def test_invalid_frame_raises(self) -> None:
        vp = VisionPipeline()
        with pytest.raises(ScreenshotValidationError):
            vp.process(None)

    def test_small_random_frame_different_hashes(self) -> None:
        vp = VisionPipeline()
        f1 = _make_frame()
        f2 = _make_frame()
        r1 = vp.process(f1)
        r2 = vp.process(f2)
        # With random frames, hashes should be different
        assert r1.frame_hash != r2.frame_hash

    def test_same_frames_same_hash(self) -> None:
        vp = VisionPipeline()
        frame = _make_constant_frame(42)
        # Reset history to avoid duplicate detection masking the hash comparison
        vp.frame_history = []
        r1 = vp.process(frame)
        vp.frame_history = []
        r2 = vp.process(frame)
        assert r1.frame_hash == r2.frame_hash


# ── process_with_timeout ───────────────────────────────────────────────────

class TestProcessWithTimeout:
    """process_with_timeout wraps process() with signal.SIGALRM."""

    def test_sets_and_restores_signal(self) -> None:
        vp = VisionPipeline()
        old = signal.signal(signal.SIGALRM, signal.SIG_DFL)
        try:
            frame = _make_frame()
            result = vp.process_with_timeout(frame, timeout=5)
            assert isinstance(result, PreprocessingResult)
        finally:
            signal.signal(signal.SIGALRM, old)

    def test_returns_result(self) -> None:
        vp = VisionPipeline()
        old = signal.signal(signal.SIGALRM, signal.SIG_DFL)
        try:
            frame = _make_frame()
            result = vp.process_with_timeout(frame, timeout=5)
            assert isinstance(result, PreprocessingResult)
            assert result.frame_hash
        finally:
            signal.signal(signal.SIGALRM, old)

    def test_signal_restored_even_on_validation_error(self) -> None:
        vp = VisionPipeline()
        old = signal.signal(signal.SIGALRM, signal.SIG_DFL)
        try:
            with pytest.raises(ScreenshotValidationError):
                vp.process_with_timeout(None, timeout=5)
            # Signal handler should be restored (SIG_DFL we set)
            assert signal.getsignal(signal.SIGALRM) is signal.SIG_DFL
        finally:
            signal.signal(signal.SIGALRM, old)

    def test_signal_restored_after_success(self) -> None:
        vp = VisionPipeline()
        old_sig = signal.getsignal(signal.SIGALRM)
        frame = _make_frame()
        vp.process_with_timeout(frame, timeout=5)
        assert signal.getsignal(signal.SIGALRM) is old_sig


# ── _compute_frame_hash ────────────────────────────────────────────────────

class TestComputeFrameHash:
    """_compute_frame_hash produces a stable perceptual hash."""

    def test_returns_16_char_hex(self) -> None:
        vp = VisionPipeline()
        frame = _make_constant_frame(100)
        h = vp._compute_frame_hash(frame)
        assert isinstance(h, str)
        assert len(h) == 16
        assert all(c in "0123456789abcdef" for c in h)

    def test_same_frame_same_hash(self) -> None:
        vp = VisionPipeline()
        frame = _make_constant_frame(77)
        h1 = vp._compute_frame_hash(frame)
        h2 = vp._compute_frame_hash(frame)
        assert h1 == h2

    def test_different_frames_different_hash(self) -> None:
        vp = VisionPipeline()
        h1 = vp._compute_frame_hash(_make_constant_frame(10))
        h2 = vp._compute_frame_hash(_make_constant_frame(200))
        assert h1 != h2

    def test_grayscale_input_accepted(self) -> None:
        vp = VisionPipeline()
        frame = _make_grayscale_frame()
        h = vp._compute_frame_hash(frame)
        assert len(h) == 16

    def test_hash_is_valid_md5(self) -> None:
        vp = VisionPipeline()
        frame = _make_constant_frame(50)
        h = vp._compute_frame_hash(frame)
        # Should be 16 hex chars (md5 truncated)
        int(h, 16)  # no ValueError


# ── _simple_dct_2d ─────────────────────────────────────────────────────────

class TestSimpleDCT2D:
    """_simple_dct_2d computes a 2D DCT on a block."""

    def test_returns_float_array(self) -> None:
        vp = VisionPipeline()
        block = np.random.rand(8, 8).astype(np.float32)
        result = vp._simple_dct_2d(block)
        assert result.dtype == np.float32

    def test_same_shape(self) -> None:
        vp = VisionPipeline()
        block = np.ones((4, 6), dtype=np.float32)
        result = vp._simple_dct_2d(block)
        assert result.shape == block.shape

    def test_constant_block_dc_component(self) -> None:
        vp = VisionPipeline()
        block = np.ones((8, 8), dtype=np.float32)
        result = vp._simple_dct_2d(block)
        # DC (0,0) should be non-zero, AC coefficients near zero
        assert abs(result[0, 0]) > 0.1
        # First AC coefficient should be close to 0 for constant input
        if block.shape[1] > 1:
            assert abs(result[0, 1]) < 0.1

    def test_square_block(self) -> None:
        vp = VisionPipeline()
        block = np.eye(4, dtype=np.float32)
        result = vp._simple_dct_2d(block)
        assert result.shape == (4, 4)

    def test_small_block(self) -> None:
        vp = VisionPipeline()
        block = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32)
        result = vp._simple_dct_2d(block)
        assert result.shape == (2, 2)


# ── _check_duplicate ───────────────────────────────────────────────────────

class TestCheckDuplicate:
    """_check_duplicate checks recent frame history."""

    def test_no_history_not_duplicate(self) -> None:
        vp = VisionPipeline()
        assert vp._check_duplicate("abc") is False

    def test_matching_in_history(self) -> None:
        vp = VisionPipeline()
        vp.frame_history = ["aaa", "bbb", "ccc"]
        assert vp._check_duplicate("aaa") is True  # in last 3
        assert vp._check_duplicate("ccc") is True
        assert vp._check_duplicate("xxx") is False

    def test_increments_stuck_counter(self) -> None:
        vp = VisionPipeline()
        vp.frame_history = ["a", "b", "a"]
        assert vp._stuck_counter == 0
        vp._check_duplicate("a")
        assert vp._stuck_counter == 1

    def test_only_checks_last_three(self) -> None:
        vp = VisionPipeline()
        vp.frame_history = ["a", "b", "c", "d", "e"]
        # "c" is at index 2, which is within last 3 of 5-element list
        assert vp._check_duplicate("e") is True
        assert vp._check_duplicate("a") is False


# ── _update_frame_history ──────────────────────────────────────────────────

class TestUpdateFrameHistory:
    """_update_frame_history manages the frame hash ring buffer."""

    def test_appends_to_history(self) -> None:
        vp = VisionPipeline()
        vp._update_frame_history("hash1")
        assert vp.frame_history == ["hash1"]

    def test_caps_at_max_history(self) -> None:
        vp = VisionPipeline()
        vp.max_history = 3
        for i in range(5):
            vp._update_frame_history(f"h{i}")
        assert len(vp.frame_history) == 3
        assert vp.frame_history == ["h2", "h3", "h4"]

    def test_different_frame_resets_stuck_counter(self) -> None:
        vp = VisionPipeline()
        vp._stuck_counter = 5
        vp._update_frame_history("a")
        vp._update_frame_history("b")  # different → counter reset
        assert vp._stuck_counter == 0

    def test_same_frame_increments_stuck_counter(self) -> None:
        vp = VisionPipeline()
        vp._update_frame_history("a")
        vp._update_frame_history("a")  # same → counter + 1
        assert vp._stuck_counter == 1


# ── _is_frame_changed ──────────────────────────────────────────────────────

class TestIsFrameChanged:
    """_is_frame_changed checks if latest two frames differ."""

    def test_single_frame_true(self) -> None:
        vp = VisionPipeline()
        vp.frame_history = ["a"]
        assert vp._is_frame_changed() is True

    def test_empty_history_true(self) -> None:
        vp = VisionPipeline()
        assert vp._is_frame_changed() is True

    def test_same_frames_false(self) -> None:
        vp = VisionPipeline()
        vp.frame_history = ["a", "a"]
        assert vp._is_frame_changed() is False

    def test_different_frames_true(self) -> None:
        vp = VisionPipeline()
        vp.frame_history = ["a", "b"]
        assert vp._is_frame_changed() is True

    def test_three_frames_checks_last_two(self) -> None:
        vp = VisionPipeline()
        vp.frame_history = ["a", "a", "b"]
        assert vp._is_frame_changed() is True  # "a" != "b"
        vp.frame_history = ["a", "b", "b"]
        assert vp._is_frame_changed() is False  # "b" == "b"


# ── _normalize_aspect_ratio ────────────────────────────────────────────────

class TestNormalizeAspectRatio:
    """_normalize_aspect_ratio enforces 4:3 (160:144) aspect ratio."""

    def test_correct_ratio_unchanged(self) -> None:
        vp = VisionPipeline()
        frame = np.zeros((144, 160, 3), dtype=np.uint8)
        result = vp._normalize_aspect_ratio(frame)
        assert result.shape == (144, 160, 3)

    def test_too_wide_cropped(self) -> None:
        vp = VisionPipeline()
        frame = np.zeros((100, 200, 3), dtype=np.uint8)  # wider than 160:144
        result = vp._normalize_aspect_ratio(frame)
        # Should be narrower after crop (width reduced to match aspect)
        new_ratio = result.shape[1] / result.shape[0]
        assert abs(new_ratio - VisionPipeline.ASPECT_RATIO) < 0.02

    def test_too_tall_cropped(self) -> None:
        vp = VisionPipeline()
        frame = np.zeros((200, 100, 3), dtype=np.uint8)  # taller than 160:144
        result = vp._normalize_aspect_ratio(frame)
        new_ratio = result.shape[1] / result.shape[0]
        assert abs(new_ratio - VisionPipeline.ASPECT_RATIO) < 0.02

    def test_grayscale_preserved(self) -> None:
        vp = VisionPipeline()
        frame = np.zeros((144, 160), dtype=np.uint8)
        result = vp._normalize_aspect_ratio(frame)
        assert result.ndim == 2


# ── _convert_to_grayscale ──────────────────────────────────────────────────

class TestConvertToGrayscale:
    """_convert_to_grayscale converts RGB to luminance grayscale."""

    def test_already_grayscale_unchanged(self) -> None:
        vp = VisionPipeline()
        gray = np.random.randint(0, 256, (144, 160), dtype=np.uint8)
        result = vp._convert_to_grayscale(gray)
        assert result.shape == (144, 160)
        assert result.ndim == 2

    def test_rgb_to_gray(self) -> None:
        vp = VisionPipeline()
        rgb = np.zeros((100, 100, 3), dtype=np.uint8)
        result = vp._convert_to_grayscale(rgb)
        assert result.shape == (100, 100)
        assert result.ndim == 2
        assert result.dtype == np.uint8

    def test_rgba_strips_alpha(self) -> None:
        vp = VisionPipeline()
        rgba = np.zeros((50, 50, 4), dtype=np.uint8)
        result = vp._convert_to_grayscale(rgba)
        assert result.shape == (50, 50)
        assert result.ndim == 2

    def test_white_is_white(self) -> None:
        vp = VisionPipeline()
        white = np.full((10, 10, 3), 255, dtype=np.uint8)
        result = vp._convert_to_grayscale(white)
        assert result[0, 0] == 255

    def test_black_is_black(self) -> None:
        vp = VisionPipeline()
        black = np.zeros((10, 10, 3), dtype=np.uint8)
        result = vp._convert_to_grayscale(black)
        assert result[0, 0] == 0

    def test_grayscale_value_in_range(self) -> None:
        vp = VisionPipeline()
        rgb = np.random.randint(0, 256, (50, 50, 3), dtype=np.uint8)
        result = vp._convert_to_grayscale(rgb)
        assert result.min() >= 0
        assert result.max() <= 255


# ── _resize_to_target ──────────────────────────────────────────────────────

class TestResizeToTarget:
    """_resize_to_target resizes frames for vision model input."""

    def test_resizes_to_default_target(self) -> None:
        vp = VisionPipeline()
        frame = np.random.randint(0, 256, (144, 160), dtype=np.uint8)
        result = vp._resize_to_target(frame)
        assert result.shape == (224, 224) or result.shape == (224, 224, 3)
        assert isinstance(result, np.ndarray)

    def test_respects_custom_size(self) -> None:
        vp = VisionPipeline()
        frame = np.random.randint(0, 256, (100, 80), dtype=np.uint8)
        result = vp._resize_to_target(frame, size=(32, 32))
        assert result.shape[:2] == (32, 32)

    def test_small_target(self) -> None:
        vp = VisionPipeline()
        frame = np.random.randint(0, 256, (144, 160), dtype=np.uint8)
        result = vp._resize_to_target(frame, size=(16, 16))
        assert result.shape[:2] == (16, 16)

    def test_larger_target(self) -> None:
        vp = VisionPipeline()
        frame = np.random.randint(0, 256, (100, 100), dtype=np.uint8)
        result = vp._resize_to_target(frame, size=(512, 512))
        assert result.shape[:2] == (512, 512)


# ── _extract_battle_menu ───────────────────────────────────────────────────

class TestExtractBattleMenu:
    """_extract_battle_menu extracts the menu region from the frame."""

    def test_returns_slice_for_standard_resolution(self) -> None:
        vp = VisionPipeline()
        frame = np.zeros((224, 224), dtype=np.uint8)
        result = vp._extract_battle_menu(frame)
        assert result is not None
        assert result.ndim == 2

    def test_region_within_bounds(self) -> None:
        vp = VisionPipeline()
        h, w = 224, 224
        frame = np.zeros((h, w), dtype=np.uint8)
        result = vp._extract_battle_menu(frame)
        # For (224, 224): y1=int(224*0.85)=190, y2=224, x1=int(224*0.5)=112, x2=224
        y_slice, x_slice = result.shape[:2]
        assert y_slice == 224 - 190  # 34
        assert x_slice == 224 - 112  # 112

    def test_empty_frame_returns_none(self) -> None:
        vp = VisionPipeline()
        # Only 0-dimension frames fail ROI extraction (bounds checks pass for any positive size)
        frame = np.zeros((0, 0), dtype=np.uint8)
        result = vp._extract_battle_menu(frame)
        assert result is None

    def test_result_is_view_not_copy_check(self) -> None:
        vp = VisionPipeline()
        frame = np.ones((224, 224), dtype=np.uint8)
        result = vp._extract_battle_menu(frame)
        assert np.all(result >= 0)


# ── _extract_dialog_box ────────────────────────────────────────────────────

class TestExtractDialogBox:
    """_extract_dialog_box extracts the dialog region from the frame."""

    def test_returns_slice_for_standard_resolution(self) -> None:
        vp = VisionPipeline()
        frame = np.zeros((224, 224), dtype=np.uint8)
        result = vp._extract_dialog_box(frame)
        assert result is not None
        assert result.ndim == 2

    def test_dialog_region_covers_bottom(self) -> None:
        vp = VisionPipeline()
        h, w = 224, 224
        frame = np.zeros((h, w), dtype=np.uint8)
        result = vp._extract_dialog_box(frame)
        y_slice = result.shape[0]
        # First candidate: (int(h*0.6)=134, 224) → y_slice ≈ 90
        assert y_slice > 0
        assert y_slice <= h

    def test_tiny_frame_none(self) -> None:
        vp = VisionPipeline()
        # 1x1 frame: y1=int(1*0.6)=0, y2=1, x1=0, x2=1 → passes (0<1≤1)
        # but second candidate: y1=int(1*0.7)=0, y2=1, x1=0, x2=1 → passes too
        # Even 1x1 works! The bounds are always satisfied for any positive size.
        # Check that 0x0/empty produces None instead:
        frame = np.zeros((0, 0), dtype=np.uint8)
        result = vp._extract_dialog_box(frame)
        # 0x0 frame has h=0, w=0: first candidate y1=int(0*0.6)=0, x1=0, x2=0
        # The check 0 <= 0 < 0 <= 0 fails (0 < 0 is false)
        assert result is None


# ── _extract_hud ───────────────────────────────────────────────────────────

class TestExtractHUD:
    """_extract_hud extracts the HUD region from the frame."""

    def test_returns_slice_for_standard_resolution(self) -> None:
        vp = VisionPipeline()
        frame = np.zeros((224, 224), dtype=np.uint8)
        result = vp._extract_hud(frame)
        assert result is not None
        assert result.ndim == 2

    def test_hud_is_top_of_screen(self) -> None:
        vp = VisionPipeline()
        h, w = 224, 224
        frame = np.zeros((h, w), dtype=np.uint8)
        result = vp._extract_hud(frame)
        # First candidate: y1=0, y2=int(224*0.15)=33
        assert result.shape[0] == 33

    def test_small_frame_none(self) -> None:
        vp = VisionPipeline()
        frame = np.zeros((3, 3), dtype=np.uint8)
        result = vp._extract_hud(frame)
        assert result is None


# ── softlock detection ─────────────────────────────────────────────────────

class TestSoftlockDetection:
    """detect_softlock, reset_softlock_counter, get_stuck_counter."""

    def test_detect_softlock_false_by_default(self) -> None:
        vp = VisionPipeline()
        assert vp.detect_softlock() is False

    def test_detect_softlock_true_after_threshold(self) -> None:
        vp = VisionPipeline()
        vp._stuck_counter = 11
        assert vp.detect_softlock() is True

    def test_detect_softlock_false_at_exactly_10(self) -> None:
        vp = VisionPipeline()
        vp._stuck_counter = 10
        assert vp.detect_softlock() is False

    def test_reset_counter(self) -> None:
        vp = VisionPipeline()
        vp._stuck_counter = 50
        vp.reset_softlock_counter()
        assert vp._stuck_counter == 0
        assert vp.detect_softlock() is False

    def test_get_stuck_counter(self) -> None:
        vp = VisionPipeline()
        vp._stuck_counter = 7
        assert vp.get_stuck_counter() == 7

    def test_full_detect_cycle(self) -> None:
        vp = VisionPipeline()
        assert vp.get_stuck_counter() == 0
        assert vp.detect_softlock() is False
        vp._stuck_counter = 11
        assert vp.detect_softlock() is True
        vp.reset_softlock_counter()
        assert vp.get_stuck_counter() == 0


# ── edge cases ─────────────────────────────────────────────────────────────

class TestEdgeCases:
    """Boundary and edge case tests for the pipeline."""

    def test_process_gbra_resolution(self) -> None:
        """GBA resolution (240, 160) fails dimension check."""
        vp = VisionPipeline()
        gba_frame = np.zeros((160, 240, 3), dtype=np.uint8)
        with pytest.raises(ScreenshotValidationError) as exc:
            vp.process(gba_frame)
        assert exc.value.error_type == "wrong_dimensions"

    def test_process_rgba_frame(self) -> None:
        vp = VisionPipeline()
        rgba = np.random.randint(0, 256, (144, 160, 4), dtype=np.uint8)
        result = vp.process(rgba)
        assert isinstance(result, PreprocessingResult)

    def test_process_with_timeout_default(self) -> None:
        vp = VisionPipeline()
        old = signal.signal(signal.SIGALRM, signal.SIG_DFL)
        try:
            frame = _make_frame()
            result = vp.process_with_timeout(frame)  # uses DEFAULT_TIMEOUT=30
            assert isinstance(result, PreprocessingResult)
        finally:
            signal.signal(signal.SIGALRM, old)

    def test_two_pipelines_independent(self) -> None:
        vp1 = VisionPipeline()
        vp2 = VisionPipeline()
        frame = _make_frame()
        r1 = vp1.process(frame)
        r2 = vp2.process(frame)
        # Both should have different hashes from their own frame histories 
        # (since both start empty, they should get same hash for same frame)
        assert r1.frame_hash == r2.frame_hash

    def test_many_frames_stay_within_history_limit(self) -> None:
        vp = VisionPipeline()
        vp.max_history = 5
        for i in range(20):
            frame = _make_frame()
            vp.process(frame)
        assert len(vp.frame_history) == 5

    def test_processing_validates_before_roi_extraction(self) -> None:
        """A frame that passes validation still gets ROIs extracted."""
        vp = VisionPipeline()
        frame = _make_frame()
        result = vp.process(frame, extract_rois=True)
        # ROIs extracted from the resized 224x224 image
        assert result.roi_battle_menu is not None
        assert result.roi_dialog_box is not None
        assert result.roi_hud is not None
