"""
Unit tests for src/core/screenshot_manager.py
Tests ScreenshotManager + LiveView classes with tmp_path — no ROM/API needed.
"""
import base64
import io
import os
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import pytest

from src.core.screenshot_manager import LiveView, ScreenshotManager


# ── helpers ────────────────────────────────────────────────────────────────

def _make_rgb(w: int = 160, h: int = 144) -> np.ndarray:
    """Create a test RGB image (non-black)."""
    arr = np.zeros((h, w, 3), dtype=np.uint8)
    arr[20:80, 30:130] = [255, 100, 50]  # orange rectangle
    return arr


def _save_png(path: Path, arr: np.ndarray) -> None:
    """Save numpy array as PNG to path."""
    import cv2
    cv2.imwrite(str(path), cv2.cvtColor(arr, cv2.COLOR_RGB2BGR))


# ── ScreenshotManager tests ────────────────────────────────────────────────

class TestScreenshotManagerInit:
    def test_creates_dirs(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        assert sm.screenshot_dir.exists()
        assert sm.battle_dir.exists()
        assert sm.overworld_dir.exists()
        assert sm.menus_dir.exists()

    def test_idempotent_init(self, tmp_path):
        sm1 = ScreenshotManager(str(tmp_path / "ss"))
        sm2 = ScreenshotManager(str(tmp_path / "ss"))
        assert sm2.battle_dir == sm1.battle_dir

    def test_subdirs_are_correct_paths(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path))
        assert sm.battle_dir.name == "battles"
        assert sm.overworld_dir.name == "overworld"
        assert sm.menus_dir.name == "menus"


class TestSaveScreenshot:
    def test_saves_to_overworld(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        img = _make_rgb()
        path = sm.save_screenshot(img, "test", "overworld")
        assert path.exists()
        assert path.parent == sm.overworld_dir
        assert path.name.startswith("test_")

    def test_saves_to_battle(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        img = _make_rgb()
        path = sm.save_screenshot(img, "combat", "battle")
        assert path.parent == sm.battle_dir

    def test_saves_to_menu(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        img = _make_rgb()
        path = sm.save_screenshot(img, "menu", "menu")
        assert path.parent == sm.menus_dir

    def test_saves_to_root_when_none(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        img = _make_rgb()
        path = sm.save_screenshot(img, "other", None)
        assert path.parent == sm.screenshot_dir

    def test_returns_path_object(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        path = sm.save_screenshot(_make_rgb(), "t1")
        assert isinstance(path, Path)

    def test_saved_file_is_valid_png(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        path = sm.save_screenshot(_make_rgb(), "valid")
        img = cv2.imread(str(path))
        assert img is not None
        assert img.shape[:2] == (144, 160)  # original dimensions

    def test_filename_contains_timestamp(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        path = sm.save_screenshot(_make_rgb(), "prefix")
        # Should match: prefix_YYYYMMDD_HHMMSS_microseconds.png
        stem = path.stem
        assert stem.startswith("prefix_")
        parts = stem.split("_")
        assert len(parts) >= 3  # prefix, date, time


class TestGetLatestScreenshot:
    def test_empty_returns_none(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        assert sm.get_latest_screenshot() is None

    def test_returns_latest_by_mtime(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        img = _make_rgb()
        p1 = sm.save_screenshot(img, "first")
        time.sleep(0.01)
        p2 = sm.save_screenshot(img, "second")
        result = sm.get_latest_screenshot()
        assert result == p2

    def test_filter_by_battle(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        img = _make_rgb()
        sm.save_screenshot(img, "b1", "battle")
        sm.save_screenshot(img, "o1", "overworld")
        result = sm.get_latest_screenshot("battle")
        assert result is not None
        assert result.parent == sm.battle_dir

    def test_filter_by_overworld(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        img = _make_rgb()
        sm.save_screenshot(img, "b1", "battle")
        o1 = sm.save_screenshot(img, "o1", "overworld")
        result = sm.get_latest_screenshot("overworld")
        assert result == o1

    def test_filter_by_menu_empty_returns_none(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        img = _make_rgb()
        sm.save_screenshot(img, "b1", "battle")
        assert sm.get_latest_screenshot("menu") is None

    def test_no_filter_searches_root_only(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        img = _make_rgb()
        latest = sm.save_screenshot(img, "root")
        time.sleep(0.01)
        sm.save_screenshot(img, "o", "overworld")
        # No filter only searches root dir, not subdirs
        assert sm.get_latest_screenshot() == latest

    def test_unknown_game_state_returns_none(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        assert sm.get_latest_screenshot("invalid") is None


class TestGetScreenshotAsBase64:
    def test_valid_file_returns_base64(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        p = sm.save_screenshot(_make_rgb(), "enc")
        b64 = sm.get_screenshot_as_base64(p)
        assert isinstance(b64, str)
        decoded = base64.b64decode(b64)
        assert len(decoded) > 100  # valid PNG data

    def test_file_not_found_raises(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        with pytest.raises(FileNotFoundError):
            sm.get_screenshot_as_base64(Path("/nonexistent/path.png"))

    def test_is_valid_base64_encoding(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        p = sm.save_screenshot(_make_rgb(), "valid")
        b64 = sm.get_screenshot_as_base64(p)
        # Should decode without error
        base64.b64decode(b64)


class TestCreateGridView:
    def test_creates_grid_file(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        for i in range(5):
            _save_png(sm.screenshot_dir / f"test_{i:04d}.png", _make_rgb())
        grid_path = sm.create_grid_view(recent_count=5)
        assert grid_path.exists()
        img = cv2.imread(str(grid_path))
        assert img is not None

    def test_no_screenshots_raises_valueerror(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        with pytest.raises(ValueError, match="No screenshots"):
            sm.create_grid_view()

    def test_custom_output_path(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        _save_png(sm.screenshot_dir / "test.png", _make_rgb())
        custom = tmp_path / "custom_grid.png"
        result = sm.create_grid_view(output_path=custom)
        assert result == custom
        assert custom.exists()

    def test_grid_dimensions(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        for i in range(8):
            _save_png(sm.screenshot_dir / f"img_{i:04d}.png", _make_rgb())
        grid_path = sm.create_grid_view(recent_count=8)
        img = cv2.imread(str(grid_path))
        # 8 images ÷ 4 cols = 2 rows × 288px = 576 high, 4 cols × 320px = 1280 wide
        assert img.shape[0] == 576
        assert img.shape[1] == 1280

    def test_grid_with_single_image(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        _save_png(sm.screenshot_dir / "single.png", _make_rgb())
        grid = sm.create_grid_view(recent_count=1)
        img = cv2.imread(str(grid))
        assert img.shape[0] == 288  # 1 row
        assert img.shape[1] == 1280  # grid always uses 4 columns

    def test_grid_respects_recent_count(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        for i in range(10):
            _save_png(sm.screenshot_dir / f"img_{i:04d}.png", _make_rgb())
        grid_path = sm.create_grid_view(recent_count=3)
        img = cv2.imread(str(grid_path))
        # 3 images ÷ 4 cols = 1 row
        assert img.shape[0] == 288

    def test_corrupted_image_skipped(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        _save_png(sm.screenshot_dir / "good.png", _make_rgb())
        # Write a broken file
        (sm.screenshot_dir / "broken.png").write_text("not an image")
        # Should not crash — corrupted image skipped
        grid = sm.create_grid_view(recent_count=2)
        assert grid.exists()


class TestCleanupOldScreenshots:
    def test_keeps_most_recent(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        paths = []
        for i in range(5):
            path = sm.screenshot_dir / f"img_{i:04d}.png"
            _save_png(path, _make_rgb())
            os.utime(path, (time.time(), time.time() - (5 - i)))
            paths.append(path)
        sm.cleanup_old_screenshots(keep_count=2)
        remaining = list(sm.screenshot_dir.glob("*.png"))
        assert len(remaining) == 2
        # Oldest 3 should be deleted
        assert paths[0] not in remaining

    def test_keep_count_greater_than_total(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        for i in range(3):
            _save_png(sm.screenshot_dir / f"img_{i}.png", _make_rgb())
        sm.cleanup_old_screenshots(keep_count=100)
        assert len(list(sm.screenshot_dir.glob("*.png"))) == 3

    def test_empty_dir_no_error(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        sm.cleanup_old_screenshots()  # should not raise

    def test_keep_count_zero_keeps_none(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        for i in range(3):
            _save_png(sm.screenshot_dir / f"img_{i}.png", _make_rgb())
        sm.cleanup_old_screenshots(keep_count=0)
        # Keep_count=0: all_screenshots[:-0] = all_screenshots (Python slice), so nothing removed
        assert len(list(sm.screenshot_dir.glob("*.png"))) == 3


class TestGetScreenshotStats:
    def test_empty_stats(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        stats = sm.get_screenshot_stats()
        assert stats == {"total": 0, "battles": 0, "overworld": 0, "menus": 0}

    def test_populated_stats(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        img = _make_rgb()
        sm.save_screenshot(img, "b1", "battle")
        sm.save_screenshot(img, "b2", "battle")
        sm.save_screenshot(img, "o1", "overworld")
        sm.save_screenshot(img, "m1", "menu")
        sm.save_screenshot(img, "root")
        stats = sm.get_screenshot_stats()
        assert stats["battles"] == 2
        assert stats["overworld"] == 1
        assert stats["menus"] == 1
        assert stats["total"] == 1  # only root dir

    def test_single_category(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        sm.save_screenshot(_make_rgb(), "only", "battle")
        stats = sm.get_screenshot_stats()
        assert stats["battles"] == 1
        assert stats["overworld"] == 0
        assert stats["menus"] == 0

    def test_all_keys_present(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        stats = sm.get_screenshot_stats()
        for key in ("total", "battles", "overworld", "menus"):
            assert key in stats


# ── LiveView tests ─────────────────────────────────────────────────────────

class TestLiveViewInit:
    def test_stores_manager(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        lv = LiveView(sm)
        assert lv.screenshot_manager is sm

    def test_not_displaying_by_default(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        lv = LiveView(sm)
        assert lv.is_displaying is False

    def test_has_window_name(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        lv = LiveView(sm)
        assert isinstance(lv.display_window, str)
        assert len(lv.display_window) > 0


class TestLiveViewUpdateDisplay:
    def test_not_displaying_returns_early(self, tmp_path):
        """update_display should be a no-op when not displaying."""
        sm = ScreenshotManager(str(tmp_path / "ss"))
        lv = LiveView(sm)
        img = _make_rgb()
        # Should not crash
        lv.update_display(img)

    @patch("cv2.resize")
    @patch("cv2.putText")
    @patch("cv2.imshow")
    @patch("cv2.cvtColor")
    @patch("cv2.waitKey", return_value=0)
    def test_scales_when_displaying(self, mock_waitkey, mock_cvt, mock_imshow, mock_puttext, mock_resize, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        lv = LiveView(sm)
        lv.is_displaying = True
        img = _make_rgb()
        lv.update_display(img)
        mock_resize.assert_called_once()
        # Check resize args
        call_args = mock_resize.call_args[0]
        assert call_args[1] == (640, 576)


class TestLiveViewStartStop:
    @patch("cv2.namedWindow")
    @patch("cv2.resizeWindow")
    def test_start_display(self, mock_resize, mock_named, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        lv = LiveView(sm)
        lv.start_display()
        assert lv.is_displaying is True
        mock_named.assert_called_once()

    @patch("cv2.destroyWindow")
    def test_stop_display(self, mock_destroy, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        lv = LiveView(sm)
        lv.is_displaying = True
        lv.stop_display()
        assert lv.is_displaying is False
        mock_destroy.assert_called_once()

    def test_stop_when_not_displaying_is_noop(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        lv = LiveView(sm)
        lv.is_displaying = False
        # Should not crash
        lv.stop_display()


class TestLiveViewDisplayScreenshot:
    @patch("cv2.imread")
    @patch("cv2.putText")
    @patch("cv2.imshow")
    @patch("cv2.waitKey")
    def test_valid_file_displays(self, mock_wait, mock_imshow, mock_puttext, mock_imread, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        lv = LiveView(sm)
        dummy = np.zeros((144, 160, 3), dtype=np.uint8)
        mock_imread.return_value = dummy
        lv.display_screenshot(Path("/fake/path.png"))
        mock_imread.assert_called_once()

    @patch("cv2.imread", return_value=None)
    def test_missing_file_returns_early(self, mock_imread, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        lv = LiveView(sm)
        lv.display_screenshot(Path("/nonexistent.png"))
        mock_imread.assert_called_once()
        # No error — just returns


# ── Integration ────────────────────────────────────────────────────────────

class TestIntegration:
    def test_save_and_get_latest(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        img = _make_rgb()
        p1 = sm.save_screenshot(img, "one", "overworld")
        time.sleep(0.01)
        p2 = sm.save_screenshot(img, "two", "overworld")
        assert sm.get_latest_screenshot("overworld") == p2

    def test_full_workflow(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        img = _make_rgb()

        # Save in different states
        sm.save_screenshot(img, "b", "battle")
        sm.save_screenshot(img, "o", "overworld")
        sm.save_screenshot(img, "m", "menu")
        sm.save_screenshot(img, "root")

        # Stats
        stats = sm.get_screenshot_stats()
        assert stats["battles"] == 1
        assert stats["overworld"] == 1
        assert stats["menus"] == 1

        # Get latest
        latest = sm.get_latest_screenshot()
        assert latest is not None

        # Base64
        b64 = sm.get_screenshot_as_base64(latest)
        assert len(b64) > 0

        # Grid
        grid = sm.create_grid_view(recent_count=4)
        assert grid.exists()

        # Cleanup
        sm.cleanup_old_screenshots(keep_count=2)
        assert len(list(sm.screenshot_dir.glob("*.png"))) == 2
