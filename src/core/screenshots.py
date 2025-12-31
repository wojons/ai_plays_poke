"""
Screenshot Manager for AI Plays Pokemon

Captures, saves, and organizes screenshots from the emulator.
Provides a live view for users to monitor game progress.
"""

import base64
from datetime import datetime
from pathlib import Path
from typing import Optional
import json

import numpy as np
from PIL import Image


class ScreenshotManager:
    """Manages screenshot capture, storage, and retrieval"""
    
    def __init__(self, save_dir: str):
        """
        Initialize screenshot manager
        
        Args:
            save_dir: Base directory for saving all screenshots
        """
        self.save_dir = Path(save_dir)
        
        # Create subdirectories for organization
        self.save_dir.mkdir(parents=True, exist_ok=True)
        self.battle_dir = self.save_dir / "battles"
        self.overworld_dir = self.save_dir / "overworld"
        self.menu_dir = self.save_dir / "menus"
        self.dialog_dir = self.save_dir / "dialogs"
        self.latest_dir = self.save_dir / "latest"
        
        for dir_path in [self.battle_dir, self.overworld_dir, self.menu_dir, 
                        self.dialog_dir, self.latest_dir]:
            dir_path.mkdir(exist_ok=True)
    
    def save_screenshot(self, screenshot: np.ndarray, name_prefix: str,
                       state_type: str = "overworld", 
                       tick: int = 0) -> Path:
        """
        Save screenshot and return its path
        
        Args:
            screenshot: RGB numpy array (160x144 or scaled version)
            name_prefix: Prefix for filename
            state_type: "battle", "overworld", "menu", "dialog"
            tick: Current game tick
            
        Returns:
            Path to saved screenshot
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        
        # Determine save directory
        state_dirs = {
            "battle": self.battle_dir,
            "overworld": self.overworld_dir,
            "menu": self.menu_dir,
            "dialog": self.dialog_dir
        }
        save_dir = state_dirs.get(state_type, self.save_dir)
        
        # Create filename
        filename = f"tick_{tick:06d}_{name_prefix}_{timestamp}.png"
        filepath = save_dir / filename
        
        # Also save to 'latest' directory with simple name
        latest_file = self.latest_dir / f"latest_{state_type}.png"
        
        # Convert numpy array to PIL Image and save
        image = Image.fromarray(screenshot)
        image.save(filepath)
        image.save(latest_file)
        
        return filepath
    
    def get_latest_screenshot(self, state_type: Optional[str] = None) -> Optional[Path]:
        """
        Get path to most recent screenshot
        
        Args:
            state_type: Filter by state type or None for all
            
        Returns:
            Path to latest screenshot or None if none exist
        """
        state_dirs = {
            "battle": self.battle_dir,
            "overworld": self.overworld_dir,
            "menu": self.menu_dir,
            "dialog": self.dialog_dir
        }
        
        search_dir = state_dirs.get(state_type, self.save_dir)
        screenshots = list(search_dir.glob("*.png"))
        
        if not screenshots:
            return None
        
        # Get most recently modified
        return max(screenshots, key=lambda p: p.stat().st_mtime)
    
    def get_screenshot_as_base64(self, filepath: Path) -> str:
        """Convert screenshot to base64 for web display or API use"""
        with open(filepath, "rb") as f:
            return base64.b64encode(f.read()).decode()
    
    def get_screenshots_info(self, state_type: Optional[str] = None) -> list:
        """
        Get info about stored screenshots
        
        Args:
            state_type: Filter by state type
            
        Returns:
            List of dicts with screenshot info
        """
        state_dirs = {
            "battle": self.battle_dir,
            "overworld": self.overworld_dir,
            "menu": self.menu_dir,
            "dialog": self.dialog_dir
        }
        
        search_dir = state_dirs.get(state_type, self.save_dir)
        screenshots = list(search_dir.glob("*.png"))
        
        info = []
        for filepath in screenshots:
            info.append({
                "path": str(filepath),
                "name": filepath.name,
                "size_bytes": filepath.stat().st_size,
                "modified": datetime.fromtimestamp(filepath.stat().st_mtime).isoformat()
            })
        
        return sorted(info, key=lambda x: x["modified"], reverse=True)
    
    def save_screenshot_with_metadata(self, screenshot: np.ndarray,
                                    metadata: dict) -> Path:
        """Save screenshot with JSON metadata"""
        filepath = self.save_screenshot(
            screenshot,
            metadata.get("name_prefix", "screenshot"),
            metadata.get("state_type", "overworld"),
            metadata.get("tick", 0)
        )
        
        # Save metadata as JSON alongside image
        metadata_path = filepath.with_suffix('.json')
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2, default=str)
        
        return filepath
    
    def cleanup_old_screenshots(self, keep_count: int = 1000):
        """Keep only the most recent screenshots to save disk space"""
        all_screenshots = list(self.save_dir.glob("*.png"))
        all_screenshots.sort(key=lambda p: p.stat().st_mtime)
        
        deleted_count = 0
        for screenshot in all_screenshots[:-keep_count]:
            # Delete the image file
            screenshot.unlink()
            # Also delete metadata if present
            metadata = screenshot.with_suffix('.json')
            if metadata.exists():
                metadata.unlink()
            deleted_count += 1
        
        if deleted_count > 0:
            print(f"🧹 Cleaned up {deleted_count} old screenshots (kept {keep_count})")
        
        return deleted_count
    
    def get_stats(self) -> dict:
        """Get statistics about stored screenshots"""
        return {
            "total": len(list(self.save_dir.glob("*.png"))),
            "battles": len(list(self.battle_dir.glob("*.png"))),
            "overworld": len(list(self.overworld_dir.glob("*.png"))),
            "menus": len(list(self.menu_dir.glob("*.png"))),
            "dialogs": len(list(self.dialog_dir.glob("*.png"))),
            "latest": self.get_latest_screenshot()
        }


class SimpleLiveView:
    """
    Simple screenshot viewer using PIL
    Works without cv2 dependency
    """
    
    def __init__(self, screenshot_manager: ScreenshotManager):
        self.screenshot_manager = screenshot_manager
        self.current_image = None
        self.should_display = False
    
    def update_display(self, screenshot: np.ndarray):
        """Update the current screenshot (for simple viewing)"""
        self.current_image = screenshot
        self.should_display = True
        
        # Save to 'latest' for easy viewing
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        latest_path = self.screenshot_manager.save_dir / "latest" / f"current.png"
        image = Image.fromarray(screenshot)
        
        # Add timestamp overlay
        from PIL import ImageDraw, ImageFont
        draw = ImageDraw.Draw(image)
        
        try:
            # Try to use default font
            font = ImageFont.load_default()
        except:
            font = None
        
        text = f"Tick: {getattr(self, 'tick', 0)} | Time: {timestamp}"
        if font:
            draw.text((5, 5), text, fill=(255, 255, 255), font=font)
        else:
            draw.text((5, 5), text, fill=(255, 255, 255))
        
        image.save(latest_path)


# Example usage
if __name__ == "__main__":
    # Create test screenshot (red square)
    test_screen = np.zeros((144, 160, 3), dtype=np.uint8)
    test_screen[50:100, 50:100] = [255, 0, 0]  # Red square
    
    # Initialize manager
    manager = ScreenshotManager("./test_screenshots")
    
    # Save test screenshots
    for i in range(3):
        manager.save_screenshot(
            test_screen,
            f"test_{i}",
            state_type="overworld",
            tick=i*100
        )
    
    # Get stats
    stats = manager.get_stats()
    print(f"Stats: {stats}")
    
    # Get latest
    latest = manager.get_latest_screenshot("overworld")
    print(f"Latest: {latest}")
