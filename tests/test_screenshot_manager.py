"""Unit tests for screenshot_manager.py — ScreenshotManager and LiveView."""

import base64
import time
from pathlib import Path
from unittest import mock

import numpy as np
import pytest
from PIL import Image

from src.core.screenshot_manager import ScreenshotManager, LiveView


# ── helpers ──────────────────────────────────────────────────────────

def _fake_screen() -> np.ndarray:
    """Create a small test image (not 160x144 to keep tests fast)."""
    return np.zeros((20, 30, 3), dtype=np.uint8)


def _save_png(path: Path, arr: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(arr).save(path)


# ── ScreenshotManager tests ──────────────────────────────────────────

class TestScreenshotManagerInit:
    def test_creates_main_dir(self, tmp_path):
        d = tmp_path / "ss"
        ScreenshotManager(str(d))
        assert d.exists()

    def test_creates_subdirs(self, tmp_path):
        d = tmp_path / "ss"
        ScreenshotManager(str(d))
        assert (d / "battles").exists()
        assert (d / "overworld").exists()
        assert (d / "menus").exists()

    def test_idempotent_init(self, tmp_path):
        d = tmp_path / "ss"
        ScreenshotManager(str(d))
        ScreenshotManager(str(d))  # no error
        assert d.exists()

    def test_dirs_are_path_objects(self, tmp_path):
        d = tmp_path / "ss"
        sm = ScreenshotManager(str(d))
        assert isinstance(sm.screenshot_dir, Path)
        assert isinstance(sm.battle_dir, Path)


class TestSaveScreenshot:
    def test_saves_png(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        arr = np.ones((10, 10, 3), dtype=np.uint8) * 255
        path = sm.save_screenshot(arr, "test")
        assert path.exists()
        assert path.suffix == ".png"

    def test_returns_path_object(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        path = sm.save_screenshot(_fake_screen(), "test")
        assert isinstance(path, Path)

    def test_filename_contains_prefix(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        path = sm.save_screenshot(_fake_screen(), "my_prefix")
        assert "my_prefix" in path.name

    def test_filename_contains_timestamp(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        path = sm.save_screenshot(_fake_screen(), "ts")
        parts = path.stem.split("_")
        # e.g., "ts_20260625_120000_123456"
        assert len(parts) >= 3

    def test_game_state_battle(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        path = sm.save_screenshot(_fake_screen(), "battle_test", game_state="battle")
        assert "battles" in str(path)

    def test_game_state_overworld(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        path = sm.save_screenshot(_fake_screen(), "ow", game_state="overworld")
        assert "overworld" in str(path)

    def test_game_state_menu(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        path = sm.save_screenshot(_fake_screen(), "menu", game_state="menu")
        assert "menus" in str(path)

    def test_game_state_none(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        path = sm.save_screenshot(_fake_screen(), "root")
        # Should be in root screenshot_dir, not in subdir
        assert sm.screenshot_dir.name in str(path.parent)
        assert "battles" not in str(path)

    def test_saved_file_is_valid_png(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        arr = np.random.randint(0, 255, (20, 30, 3), dtype=np.uint8)
        path = sm.save_screenshot(arr, "valid_png")
        loaded = Image.open(path)
        assert loaded.size == (30, 20)  # (width, height) in PIL


class TestGetLatestScreenshot:
    def test_returns_none_when_empty(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        assert sm.get_latest_screenshot() is None

    def test_returns_latest_by_mtime(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        sm.save_screenshot(_fake_screen(), "first")
        time.sleep(0.01)
        p2 = sm.save_screenshot(_fake_screen(), "second")
        latest = sm.get_latest_screenshot()
        assert latest == p2

    def test_filter_by_battle(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        sm.save_screenshot(_fake_screen(), "b1", game_state="battle")
        # get_latest with filter should not raise
        latest = sm.get_latest_screenshot(game_state="battle")
        assert latest is not None

    def test_filter_by_overworld(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        sm.save_screenshot(_fake_screen(), "ow1", game_state="overworld")
        latest = sm.get_latest_screenshot(game_state="overworld")
        assert latest is not None

    def test_filter_does_not_cross_contaminate(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        sm.save_screenshot(_fake_screen(), "ow", game_state="overworld")
        # battle dir should be empty
        assert sm.get_latest_screenshot(game_state="battle") is None

    def test_filter_by_menu(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        sm.save_screenshot(_fake_screen(), "menu1", game_state="menu")
        latest = sm.get_latest_screenshot(game_state="menu")
        assert latest is not None
        assert "menus" in str(latest)

    def test_filter_by_menu_empty(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        assert sm.get_latest_screenshot(game_state="menu") is None


class TestGetScreenshotAsBase64:
    def test_returns_string(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        path = sm.save_screenshot(_fake_screen(), "b64_test")
        b64 = sm.get_screenshot_as_base64(path)
        assert isinstance(b64, str)
        assert len(b64) > 0

    def test_is_valid_base64(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        path = sm.save_screenshot(_fake_screen(), "b64_test")
        b64 = sm.get_screenshot_as_base64(path)
        decoded = base64.b64decode(b64)
        assert len(decoded) > 0

    def test_file_not_found_raises(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        with pytest.raises(FileNotFoundError):
            sm.get_screenshot_as_base64(Path("/nonexistent/file.png"))


class TestCreateGridView:
    def test_returns_path(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        sm.save_screenshot(_fake_screen(), "g1")
        grid_path = sm.create_grid_view(recent_count=1)
        assert isinstance(grid_path, Path)

    def test_grid_file_exists(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        sm.save_screenshot(_fake_screen(), "g2")
        grid_path = sm.create_grid_view(recent_count=1)
        assert grid_path.exists()

    def test_grid_is_valid_png(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        sm.save_screenshot(_fake_screen(), "g3")
        grid_path = sm.create_grid_view(recent_count=1)
        img = Image.open(grid_path)
        assert img is not None

    def test_no_screenshots_raises_value_error(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        with pytest.raises(ValueError, match="No screenshots"):
            sm.create_grid_view()

    def test_with_custom_output_path(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        sm.save_screenshot(_fake_screen(), "g4")
        out_path = tmp_path / "custom_grid.png"
        result = sm.create_grid_view(recent_count=1, output_path=out_path)
        assert result == out_path
        assert out_path.exists()

    def test_grid_with_multiple_screenshots(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        for i in range(5):
            arr = np.random.randint(0, 255, (20, 30, 3), dtype=np.uint8)
            sm.save_screenshot(arr, f"multi_{i}")
        grid_path = sm.create_grid_view(recent_count=5)
        # 5 images → 2 rows × 4 cols, grid height = 2*288 = 576, width = 4*320 = 1280
        img = Image.open(grid_path)
        assert img.size[0] > 0 and img.size[1] > 0

    def test_recent_count_limits_images(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        for i in range(10):
            sm.save_screenshot(_fake_screen(), f"limit_{i}")
        # Should not crash with count > total
        grid_path = sm.create_grid_view(recent_count=3)
        assert grid_path.exists()

    def test_corrupted_image_skipped(self, tmp_path):
        """Broken PNG file → cv2.imread returns None → skipped."""
        sm = ScreenshotManager(str(tmp_path / "ss"))
        # Save a valid PNG first so grid has at least one image
        sm.save_screenshot(_fake_screen(), "valid")
        # Corrupt it by truncating
        broken = list(sm.screenshot_dir.glob("*.png"))[0]
        broken.write_bytes(b"")  # empty file → cv2.imread returns None

        # Create a second valid image so we still have something to grid
        sm.save_screenshot(_fake_screen(), "g5")
        grid_path = sm.create_grid_view(recent_count=2)
        assert grid_path.exists()

    def test_timestamp_unknown_fallback(self, tmp_path):
        """Filename with no timestamp → 'Unknown' fallback."""
        sm = ScreenshotManager(str(tmp_path / "ss"))
        # Create a PNG with a stem that splits to <2 elements (e.g., "simple")
        weird_path = sm.screenshot_dir / "simple.png"
        _save_png(weird_path, _fake_screen())
        grid_path = sm.create_grid_view(recent_count=1)
        assert grid_path.exists()


class TestCleanupOldScreenshots:
    def test_keeps_specified_count(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        paths = []
        for i in range(10):
            time.sleep(0.005)  # ensure different mtimes
            paths.append(sm.save_screenshot(_fake_screen(), f"cleanup_{i}"))
        sm.cleanup_old_screenshots(keep_count=5)
        remaining = list(sm.screenshot_dir.glob("*.png"))
        assert len(remaining) == 5

    def test_keeps_most_recent(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        for i in range(5):
            time.sleep(0.005)
            sm.save_screenshot(_fake_screen(), f"recent_{i}")
        p_newest = sm.save_screenshot(_fake_screen(), "newest")
        sm.cleanup_old_screenshots(keep_count=1)
        remaining = list(sm.screenshot_dir.glob("*.png"))
        assert len(remaining) == 1
        assert remaining[0] == p_newest

    def test_keep_count_greater_than_total(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        for i in range(3):
            sm.save_screenshot(_fake_screen(), f"few_{i}")
        sm.cleanup_old_screenshots(keep_count=100)
        remaining = list(sm.screenshot_dir.glob("*.png"))
        assert len(remaining) == 3  # all kept

    def test_keep_count_zero_behavior(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        for i in range(3):
            sm.save_screenshot(_fake_screen(), f"del_{i}")
        sm.cleanup_old_screenshots(keep_count=0)
        remaining = list(sm.screenshot_dir.glob("*.png"))
        # keep_count=0 → all_screenshots[:-0] is [] in Python (slice quirk)
        # so nothing is deleted; this is the actual behavior
        assert len(remaining) == 3


class TestGetScreenshotStats:
    def test_empty_stats(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        stats = sm.get_screenshot_stats()
        assert stats == {"total": 0, "battles": 0, "overworld": 0, "menus": 0}

    def test_all_zeroes_when_no_screenshots(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        stats = sm.get_screenshot_stats()
        for v in stats.values():
            assert v == 0

    def test_counts_total(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        for i in range(7):
            sm.save_screenshot(_fake_screen(), f"stat_{i}")
        stats = sm.get_screenshot_stats()
        assert stats["total"] == 7

    def test_counts_by_game_state(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        sm.save_screenshot(_fake_screen(), "b1", game_state="battle")
        sm.save_screenshot(_fake_screen(), "b2", game_state="battle")
        sm.save_screenshot(_fake_screen(), "o1", game_state="overworld")
        sm.save_screenshot(_fake_screen(), "m1", game_state="menu")
        sm.save_screenshot(_fake_screen(), "root1")  # no game_state → root dir
        stats = sm.get_screenshot_stats()
        assert stats["battles"] == 2
        assert stats["overworld"] == 1
        assert stats["menus"] == 1
        assert stats["total"] == 1  # only root dir screenshots (no game_state)

    def test_returns_int_values(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        sm.save_screenshot(_fake_screen(), "type_test")
        stats = sm.get_screenshot_stats()
        for v in stats.values():
            assert isinstance(v, int)


# ── LiveView tests ───────────────────────────────────────────────────

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
        assert "display_window" in lv.__dict__


class TestLiveViewDisplayScreenshot:
    def test_missing_file_returns_none(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        lv = LiveView(sm)
        # cv2.imread returns None for missing file → method returns None
        result = lv.display_screenshot(Path("/nonexistent/img.png"))
        assert result is None

    def test_valid_file_does_not_crash(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        lv = LiveView(sm)
        path = sm.save_screenshot(_fake_screen(), "view_test")
        # Mock cv2.imshow + cv2.imread to avoid GUI
        with mock.patch("cv2.imshow"), mock.patch("cv2.waitKey"):
            # cv2.imread will actually succeed since it's a real file
            lv.display_screenshot(path, duration=0.01)
        # Should not raise


class TestLiveViewUpdateDisplay:
    def test_not_displaying_returns_early(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        lv = LiveView(sm)
        # Should return immediately without calling cv2.imshow
        result = lv.update_display(_fake_screen())
        assert result is None

    def test_when_displaying_calls_cv2(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        lv = LiveView(sm)
        lv.is_displaying = True
        with mock.patch("cv2.imshow") as mock_imshow, \
             mock.patch("cv2.waitKey", return_value=0), \
             mock.patch("cv2.resize", side_effect=lambda x, size, **kw: x), \
             mock.patch("cv2.cvtColor", side_effect=lambda x, code: x), \
             mock.patch("cv2.putText"):
            lv.update_display(_fake_screen())
            mock_imshow.assert_called_once()

    def test_q_key_stops_display(self, tmp_path):
        """Pressing 'q' in the live view stops the display."""
        sm = ScreenshotManager(str(tmp_path / "ss"))
        lv = LiveView(sm)
        lv.is_displaying = True
        with mock.patch("cv2.imshow"), \
             mock.patch("cv2.waitKey", return_value=ord("q")), \
             mock.patch("cv2.resize", side_effect=lambda x, size, **kw: x), \
             mock.patch("cv2.cvtColor", side_effect=lambda x, code: x), \
             mock.patch("cv2.putText"), \
             mock.patch("cv2.destroyWindow") as mock_destroy:
            lv.update_display(_fake_screen())
            mock_destroy.assert_called_once()
            assert lv.is_displaying is False


class TestLiveViewStartStop:
    def test_start_display(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        lv = LiveView(sm)
        with mock.patch("cv2.namedWindow"), mock.patch("cv2.resizeWindow"):
            lv.start_display()
        assert lv.is_displaying is True

    def test_stop_display(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        lv = LiveView(sm)
        lv.is_displaying = True
        with mock.patch("cv2.destroyWindow"):
            lv.stop_display()
        assert lv.is_displaying is False

    def test_stop_when_not_displaying_is_noop(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path / "ss"))
        lv = LiveView(sm)
        # Should not call cv2.destroyWindow
        lv.stop_display()
        assert lv.is_displaying is False
