"""
Unit tests for src/core/screenshots.py — ScreenshotManager + SimpleLiveView.

Covers: init, save, get_latest, base64, info, metadata, cleanup, stats, live view.
Uses tmp_path fixtures — no ROM or API key needed.
"""

import json
import time
from pathlib import Path

import numpy as np
from PIL import Image

from src.core.screenshots import ScreenshotManager, SimpleLiveView


# ── Fixtures ──────────────────────────────────────────────────────────

def _make_screen(width=160, height=144):
    """Create a test RGB numpy array with deterministic content."""
    screen = np.zeros((height, width, 3), dtype=np.uint8)
    screen[10:50, 20:80] = [255, 0, 0]   # Red rectangle
    screen[70:110, 90:140] = [0, 255, 0]  # Green rectangle
    return screen


# ── ScreenshotManager: __init__ ───────────────────────────────────────

class TestInit:
    """Test ScreenshotManager.__init__ creates all subdirectories."""

    def test_creates_all_subdirs(self, tmp_path):
        ScreenshotManager(str(tmp_path))
        for sub in ["battles", "overworld", "menus", "dialogs", "latest"]:
            p = tmp_path / sub
            assert p.exists(), f"Missing subdirectory: {sub}"
            assert p.is_dir()

    def test_idempotent_init(self, tmp_path):
        """Second init on same dir doesn't raise."""
        sm1 = ScreenshotManager(str(tmp_path))
        sm2 = ScreenshotManager(str(tmp_path))
        # Should not raise
        assert sm1.save_dir == sm2.save_dir

    def test_creates_parent_dirs(self, tmp_path):
        """mkdir(parents=True) creates intermediate directories."""
        deep = tmp_path / "a" / "b" / "screenshots"
        ScreenshotManager(str(deep))
        assert deep.exists()


# ── ScreenshotManager: save_screenshot ────────────────────────────────

class TestSaveScreenshot:
    """Test save_screenshot writes PNGs to correct directories."""

    def test_saves_to_state_dir(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path))
        screen = _make_screen()
        path = sm.save_screenshot(screen, "test", state_type="battle", tick=42)
        assert path.exists()
        assert path.parent == sm.battle_dir
        assert "tick_000042" in path.name
        assert path.suffix == ".png"

    def test_saves_latest_copy(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path))
        screen = _make_screen()
        sm.save_screenshot(screen, "test", state_type="overworld", tick=7)
        latest = sm.latest_dir / "latest_overworld.png"
        assert latest.exists()

    def test_default_state_type_is_overworld(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path))
        screen = _make_screen()
        path = sm.save_screenshot(screen, "auto")
        assert path.parent == sm.overworld_dir

    def test_unknown_state_type_falls_back_to_save_dir(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path))
        screen = _make_screen()
        path = sm.save_screenshot(screen, "x", state_type="nonexistent", tick=0)
        assert path.parent == sm.save_dir

    def test_returns_path(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path))
        path = sm.save_screenshot(_make_screen(), "ret")
        assert isinstance(path, Path)

    def test_saved_image_is_valid_png(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path))
        path = sm.save_screenshot(_make_screen(), "img", tick=1)
        img = Image.open(path)
        assert img.size == (160, 144)

    def test_saved_image_preserves_pixel_data(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path))
        screen = _make_screen()
        screen[0, 0] = [1, 2, 3]
        path = sm.save_screenshot(screen, "pix")
        img = np.array(Image.open(path))
        assert tuple(img[0, 0]) == (1, 2, 3)

    def test_multiple_saves_dont_collide(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path))
        p1 = sm.save_screenshot(_make_screen(), "a", tick=1)
        time.sleep(0.001)  # ensure timestamp differs
        p2 = sm.save_screenshot(_make_screen(), "a", tick=1)
        assert p1 != p2

    def test_latest_overwrites_per_state_type(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path))
        sm.save_screenshot(_make_screen(), "battle", state_type="battle", tick=1)
        time.sleep(0.001)
        sm.save_screenshot(_make_screen(), "overworld", state_type="overworld", tick=2)
        # both latest files should exist
        assert (sm.latest_dir / "latest_battle.png").exists()
        assert (sm.latest_dir / "latest_overworld.png").exists()


# ── ScreenshotManager: get_latest_screenshot ──────────────────────────

class TestGetLatestScreenshot:
    """Test get_latest_screenshot returns correct file or None."""

    def test_returns_latest_by_mtime_in_subdir(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path))
        sm.save_screenshot(_make_screen(), "first", state_type="battle", tick=1)
        time.sleep(0.002)
        p2 = sm.save_screenshot(_make_screen(), "second", state_type="battle", tick=2)
        # get_latest_screenshot without state_type searches save_dir root (empty)
        # — use state_type filter to search the battle subdir
        latest = sm.get_latest_screenshot("battle")
        assert latest == p2

    def test_returns_latest_from_root_when_direct_saves(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path))
        # Save directly to save_dir root (not a typed subdir)
        p1_path = sm.save_dir / "first.png"
        img = Image.fromarray(_make_screen())
        img.save(p1_path)
        time.sleep(0.002)
        p2_path = sm.save_dir / "second.png"
        img.save(p2_path)
        latest = sm.get_latest_screenshot()
        assert latest == p2_path

    def test_filters_by_state_type(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path))
        sm.save_screenshot(_make_screen(), "b", state_type="battle", tick=1)
        time.sleep(0.002)
        sm.save_screenshot(_make_screen(), "o", state_type="overworld", tick=2)
        latest_battle = sm.get_latest_screenshot("battle")
        assert latest_battle is not None
        assert latest_battle.parent == sm.battle_dir

    def test_returns_none_for_empty_dir(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path))
        assert sm.get_latest_screenshot() is None

    def test_returns_none_for_empty_state_type(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path))
        sm.save_screenshot(_make_screen(), "b", state_type="battle", tick=1)
        # no overworld screenshots
        assert sm.get_latest_screenshot("overworld") is None

    def test_returns_none_for_unknown_state_type(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path))
        # unknown type falls back to save_dir which is empty
        assert sm.get_latest_screenshot("unknown") is None

    def test_returns_latest_when_save_dir_has_direct_pngs(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path))
        # Save directly in save_dir (not a typed subdir)
        screen = _make_screen()
        img = Image.fromarray(screen)
        img.save(sm.save_dir / "direct.png")
        latest = sm.get_latest_screenshot()
        assert latest is not None
        assert latest.name == "direct.png"


# ── ScreenshotManager: get_screenshot_as_base64 ───────────────────────

class TestGetScreenshotAsBase64:
    """Test base64 conversion."""

    def test_returns_non_empty_string(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path))
        path = sm.save_screenshot(_make_screen(), "b64", tick=0)
        b64 = sm.get_screenshot_as_base64(path)
        assert isinstance(b64, str)
        assert len(b64) > 0

    def test_result_is_valid_base64(self, tmp_path):
        import base64
        sm = ScreenshotManager(str(tmp_path))
        path = sm.save_screenshot(_make_screen(), "b64v", tick=0)
        b64 = sm.get_screenshot_as_base64(path)
        decoded = base64.b64decode(b64)
        assert len(decoded) > 0

    def test_different_screenshots_produce_different_base64(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path))
        s1 = _make_screen()
        s2 = _make_screen()
        s2[0, 0] = [255, 255, 255]
        p1 = sm.save_screenshot(s1, "a")
        p2 = sm.save_screenshot(s2, "b")
        assert sm.get_screenshot_as_base64(p1) != sm.get_screenshot_as_base64(p2)


# ── ScreenshotManager: get_screenshots_info ───────────────────────────

class TestGetScreenshotsInfo:
    """Test get_screenshots_info returns sorted metadata list."""

    def test_returns_list(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path))
        sm.save_screenshot(_make_screen(), "info", state_type="overworld", tick=1)
        info = sm.get_screenshots_info("overworld")
        assert isinstance(info, list)

    def test_returns_expected_keys(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path))
        sm.save_screenshot(_make_screen(), "keys", state_type="overworld", tick=3)
        info = sm.get_screenshots_info("overworld")
        entry = info[0]
        for key in ["path", "name", "size_bytes", "modified"]:
            assert key in entry

    def test_sorted_by_modified_desc(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path))
        sm.save_screenshot(_make_screen(), "old", state_type="overworld", tick=1)
        time.sleep(0.002)
        sm.save_screenshot(_make_screen(), "new", state_type="overworld", tick=2)
        info = sm.get_screenshots_info("overworld")
        # newest first
        assert "new" in info[0]["name"]
        assert "old" in info[-1]["name"]

    def test_filters_by_state_type(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path))
        sm.save_screenshot(_make_screen(), "b", state_type="battle", tick=1)
        sm.save_screenshot(_make_screen(), "o", state_type="overworld", tick=2)
        battle_info = sm.get_screenshots_info("battle")
        assert len(battle_info) == 1
        assert "b" in battle_info[0]["name"]

    def test_empty_dir_returns_empty_list(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path))
        assert sm.get_screenshots_info() == []
        # Also empty with state_type filter
        assert sm.get_screenshots_info("battle") == []

    def test_size_bytes_is_positive(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path))
        sm.save_screenshot(_make_screen(), "size", state_type="overworld", tick=0)
        info = sm.get_screenshots_info("overworld")
        assert info[0]["size_bytes"] > 0


# ── ScreenshotManager: save_screenshot_with_metadata ──────────────────

class TestSaveWithMetadata:
    """Test save_screenshot_with_metadata writes JSON alongside PNG."""

    def test_writes_json_file(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path))
        meta = {"name_prefix": "meta", "state_type": "battle", "tick": 99,
                 "extra": "custom_data"}
        path = sm.save_screenshot_with_metadata(_make_screen(), meta)
        json_path = path.with_suffix(".json")
        assert json_path.exists()

    def test_json_contains_metadata(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path))
        meta = {"name_prefix": "j", "state_type": "menu", "tick": 5,
                 "hp": 35}
        path = sm.save_screenshot_with_metadata(_make_screen(), meta)
        with open(path.with_suffix(".json")) as f:
            saved = json.load(f)
        assert saved["hp"] == 35
        assert saved["state_type"] == "menu"

    def test_defaults_when_metadata_missing_keys(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path))
        path = sm.save_screenshot_with_metadata(_make_screen(), {})
        assert path.exists()
        json_path = path.with_suffix(".json")
        with open(json_path) as f:
            saved = json.load(f)
        assert saved == {}

    def test_png_still_valid_with_metadata(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path))
        path = sm.save_screenshot_with_metadata(_make_screen(), {"tick": 7})
        img = Image.open(path)
        assert img.size == (160, 144)


# ── ScreenshotManager: cleanup_old_screenshots ────────────────────────

class TestCleanupOldScreenshots:
    """Test cleanup_old_screenshots prunes old files."""

    def test_cleans_up_excess_files(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path))
        # Save directly to save_dir root (cleanup only scans save_dir, not subdirs)
        paths = []
        for i in range(5):
            p = sm.save_dir / f"cleanup_{i}.png"
            img = Image.fromarray(_make_screen())
            img.save(p)
            paths.append(p)
        # Keep only 3
        deleted = sm.cleanup_old_screenshots(keep_count=3)
        assert deleted == 2
        remaining = list(sm.save_dir.glob("*.png"))
        assert len(remaining) == 3

    def test_smaller_than_keep_count_does_nothing(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path))
        sm.save_screenshot(_make_screen(), "d1", tick=0)
        sm.save_screenshot(_make_screen(), "d2", tick=1)
        deleted = sm.cleanup_old_screenshots(keep_count=5)
        assert deleted == 0

    def test_deletes_metadata_json_alongside(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path))
        for i in range(5):
            meta_path = sm.save_dir / f"screenshot_{i}.png"
            img = Image.fromarray(_make_screen())
            img.save(meta_path)
            # touch metadata
            with open(meta_path.with_suffix(".json"), "w") as f:
                json.dump({"i": i}, f)
        deleted = sm.cleanup_old_screenshots(keep_count=2)
        assert deleted == 3
        # Only 2 screenshots + 2 metadata files should remain
        pngs_left = list(sm.save_dir.glob("*.png"))
        jsons_left = list(sm.save_dir.glob("*.json"))
        assert len(pngs_left) == 2
        assert len(jsons_left) == 2

    def test_returns_zero_deleted_when_empty(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path))
        assert sm.cleanup_old_screenshots(keep_count=10) == 0

    def test_metadata_not_present_no_error(self, tmp_path):
        """cleanup shouldn't error if .json doesn't exist alongside .png."""
        sm = ScreenshotManager(str(tmp_path))
        for i in range(5):
            p = sm.save_dir / f"no_meta_{i}.png"
            img = Image.fromarray(_make_screen())
            img.save(p)
        deleted = sm.cleanup_old_screenshots(keep_count=2)
        assert deleted == 3  # Should still delete .png even without .json


# ── ScreenshotManager: get_stats ──────────────────────────────────────

class TestGetStats:
    """Test get_stats returns dict with counts per state type."""

    def test_returns_dict_with_expected_keys(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path))
        stats = sm.get_stats()
        for key in ["total", "battles", "overworld", "menus", "dialogs", "latest"]:
            assert key in stats, f"Missing key: {key}"

    def test_counts_are_zero_when_empty(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path))
        stats = sm.get_stats()
        assert stats["total"] == 0
        assert stats["battles"] == 0

    def test_counts_reflect_saved_screenshots(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path))
        sm.save_screenshot(_make_screen(), "b1", state_type="battle", tick=1)
        sm.save_screenshot(_make_screen(), "b2", state_type="battle", tick=2)
        sm.save_screenshot(_make_screen(), "m1", state_type="menu", tick=3)
        stats = sm.get_stats()
        assert stats["battles"] == 2
        assert stats["menus"] == 1
        assert stats["overworld"] == 0

    def test_total_excludes_subdirs(self, tmp_path):
        """get_stats counts only *.png in save_dir root, not subdir files.
        
        Note: save_screenshot writes to typed subdirectories (battle_dir, etc.),
        not to save_dir root. So total counts direct saves only.
        """
        sm = ScreenshotManager(str(tmp_path))
        # Direct save to save_dir (simulates old path or edge case)
        img = Image.fromarray(_make_screen())
        img.save(sm.save_dir / "direct_root.png")
        # Subdir save
        sm.save_screenshot(_make_screen(), "sub", state_type="battle", tick=1)
        stats = sm.get_stats()
        # total only counts root-level .png
        assert stats["total"] == 1
        assert stats["battles"] == 1

    def test_latest_is_none_when_no_screenshots(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path))
        stats = sm.get_stats()
        assert stats["latest"] is None

    def test_latest_is_path_when_screenshots_exist(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path))
        # get_latest_screenshot() without args searches save_dir root
        img = Image.fromarray(_make_screen())
        img.save(sm.save_dir / "latest_test.png")
        stats = sm.get_stats()
        assert stats["latest"] is not None
        assert isinstance(stats["latest"], Path)


# ── SimpleLiveView ────────────────────────────────────────────────────

class TestSimpleLiveView:
    """Test SimpleLiveView.update_display saves current.png."""

    def test_init_stores_manager(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path))
        lv = SimpleLiveView(sm)
        assert lv.screenshot_manager is sm

    def test_init_defaults(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path))
        lv = SimpleLiveView(sm)
        assert lv.current_image is None
        assert lv.should_display is False

    def test_update_display_saves_current_png(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path))
        lv = SimpleLiveView(sm)
        lv.update_display(_make_screen())
        current = sm.latest_dir / "current.png"
        assert current.exists()

    def test_update_display_sets_fields(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path))
        lv = SimpleLiveView(sm)
        screen = _make_screen()
        lv.update_display(screen)
        assert lv.current_image is not None
        assert lv.should_display is True
        assert lv.current_image.shape == screen.shape

    def test_update_display_image_is_valid_png(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path))
        lv = SimpleLiveView(sm)
        lv.update_display(_make_screen())
        img = Image.open(sm.latest_dir / "current.png")
        assert img.size == (160, 144)

    def test_multiple_updates_overwrite(self, tmp_path):
        sm = ScreenshotManager(str(tmp_path))
        lv = SimpleLiveView(sm)
        s1 = _make_screen()
        s1[0, 0] = [1, 2, 3]
        lv.update_display(s1)
        s2 = _make_screen()
        s2[0, 0] = [4, 5, 6]
        lv.update_display(s2)
        # current.png should reflect s2
        img = np.array(Image.open(sm.latest_dir / "current.png"))
        assert tuple(img[0, 0]) == (4, 5, 6)
