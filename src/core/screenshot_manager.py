"""
Screenshot Manager for AI Plays Pokemon

Handles capturing, saving, and organizing screenshots from the emulator.
Creates a live view for users to monitor game progress.
"""

import base64
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image


class ScreenshotManager:
    """Manages screenshot capture, storage, and retrieval"""
    
    def __init__(self, screenshot_dir: str):
        self.screenshot_dir = Path(screenshot_dir)
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        
        # Subdirectories for organization
        self.battle_dir = self.screenshot_dir / "battles"
        self.overworld_dir = self.screenshot_dir / "overworld"
        self.menus_dir = self.screenshot_dir / "menus"
        
        for dir_path in [self.battle_dir, self.overworld_dir, self.menus_dir]:
            dir_path.mkdir(exist_ok=True)
    
    def save_screenshot(self, screenshot: np.ndarray, name_prefix: str, 
                       game_state: Optional[str] = None) -> Path:
        """
        Save screenshot to appropriate directory
        
        Args:
            screenshot: RGB numpy array (160x144)
            name_prefix: Prefix for filename
            game_state: "battle", "overworld", "menu" or None
            
        Returns:
            Path to saved screenshot
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        
        # Determine save directory based on game state
        if game_state == "battle":
            save_dir = self.battle_dir
        elif game_state == "overworld":
            save_dir = self.overworld_dir
        elif game_state == "menu":
            save_dir = self.menus_dir
        else:
            save_dir = self.screenshot_dir
        
        filename = f"{name_prefix}_{timestamp}.png"
        filepath = save_dir / filename
        
        # Convert numpy array to PIL Image and save
        image = Image.fromarray(screenshot)
        image.save(filepath)
        
        return filepath
    
    def get_latest_screenshot(self, game_state: Optional[str] = None) -> Optional[Path]:
        """
        Get path to most recent screenshot
        
        Args:
            game_state: Filter by game state or None for all
            
        Returns:
            Path to latest screenshot or None if none exist
        """
        search_dir = self.screenshot_dir
        if game_state == "battle":
            search_dir = self.battle_dir
        elif game_state == "overworld":
            search_dir = self.overworld_dir
        elif game_state == "menu":
            search_dir = self.menus_dir
        
        screenshots = list(search_dir.glob("*.png"))
        if not screenshots:
            return None
        
        return max(screenshots, key=lambda p: p.stat().st_mtime)
    
    def get_screenshot_as_base64(self, filepath: Path) -> str:
        """
        Convert screenshot to base64 for web display or API use
        
        Args:
            filepath: Path to screenshot file
            
        Returns:
            Base64 encoded image string
        """
        with open(filepath, "rb") as f:
            return base64.b64encode(f.read()).decode()
    
    def create_grid_view(self, recent_count: int = 12, 
                        output_path: Optional[Path] = None) -> Path:
        """
        Create a grid view of recent screenshots
        
        Args:
            recent_count: Number of recent screenshots to include
            output_path: Where to save the grid (defaults to screenshot_dir)
            
        Returns:
            Path to generated grid image
        """
        # Get recent screenshots
        all_screenshots = list(self.screenshot_dir.glob("*.png"))
        all_screenshots.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        
        recent_screenshots = all_screenshots[:recent_count]
        if not recent_screenshots:
            raise ValueError("No screenshots available to create grid")
        
        # Calculate grid dimensions
        cols = 4
        rows = (len(recent_screenshots) + cols - 1) // cols
        
        # Load and resize images
        images = []
        for screenshot_path in recent_screenshots:
            img = cv2.imread(str(screenshot_path))
            # Scale up for better visibility (2x)
            img_resized = cv2.resize(img, (320, 288), interpolation=cv2.INTER_NEAREST)
            images.append(img_resized)
        
        # Create grid
        cell_height, cell_width = images[0].shape[:2]
        grid = np.zeros((cell_height * rows, cell_width * cols, 3), dtype=np.uint8)
        
        for idx, img in enumerate(images):
            row = idx // cols
            col = idx % cols
            y_start = row * cell_height
            y_end = (row + 1) * cell_height
            x_start = col * cell_width
            x_end = (col + 1) * cell_width
            
            grid[y_start:y_end, x_start:x_end] = img
        
        # Add timestamps below each screenshot
        for idx, screenshot_path in enumerate(recent_screenshots):
            row = idx // cols
            col = idx % cols
            
            # Extract timestamp from filename
            timestamp_str = screenshot_path.stem.split("_")[-2:]
            if len(timestamp_str) >= 2:
                timestamp = f"{timestamp_str[0]} {timestamp_str[1][:6]}"
            else:
                timestamp = "Unknown"
            
            # Add text
            y_pos = (row + 1) * cell_height - 10
            x_pos = col * cell_width + 5
            
            cv2.putText(grid, timestamp, (x_pos, y_pos),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
        
        # Save grid
        if output_path is None:
            output_path = self.screenshot_dir / f"grid_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        
        cv2.imwrite(str(output_path), grid)
        
        return output_path
    
    def cleanup_old_screenshots(self, keep_count: int = 1000):
        """
        Keep only the most recent screenshots to save disk space
        
        Args:
            keep_count: Number of recent screenshots to keep
        """
        all_screenshots = list(self.screenshot_dir.glob("*.png"))
        all_screenshots.sort(key=lambda p: p.stat().st_mtime)
        
        # Delete old screenshots
        for screenshot in all_screenshots[:-keep_count]:
            screenshot.unlink()
        
        print(f"🧹 Cleaned up {len(all_screenshots) - keep_count} old screenshots")
    
    def get_screenshot_stats(self) -> Dict[str, int]:
        """Get statistics about stored screenshots"""
        stats = {
            "total": len(list(self.screenshot_dir.glob("*.png"))),
            "battles": len(list(self.battle_dir.glob("*.png"))),
            "overworld": len(list(self.overworld_dir.glob("*.png"))),
            "menus": len(list(self.menus_dir.glob("*.png")))
        }
        return stats


class LiveView:
    """
    Real-time view of game screenshots for monitoring
    Can be used by humans or for debugging
    """
    
    def __init__(self, screenshot_manager: ScreenshotManager):
        self.screenshot_manager = screenshot_manager
        self.is_displaying = False
        self.display_window = "AI Plays Pokemon - Live View"
    
    def start_display(self):
        """Start displaying screenshots in real-time"""
        cv2.namedWindow(self.display_window, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(self.display_window, 640, 576)  # 4x scale
        self.is_displaying = True
        
        print(f"🖼️ Live view started. Window: {self.display_window}")
        print("Press 'q' in the window to close")
    
    def stop_display(self):
        """Stop the live view display"""
        if self.is_displaying:
            cv2.destroyWindow(self.display_window)
            self.is_displaying = False
    
    def update_display(self, screenshot: np.ndarray):
        """Update the live view with a new screenshot"""
        if not self.is_displaying:
            return
        
        # Scale up for better visibility
        scaled = cv2.resize(screenshot, (640, 576), interpolation=cv2.INTER_NEAREST)
        
        # Add timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cv2.putText(scaled, timestamp, (10, 20),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        # Display
        cv2.imshow(self.display_window, cv2.cvtColor(scaled, cv2.COLOR_RGB2BGR))
        
        # Check for quit key
        if cv2.waitKey(1) & 0xFF == ord('q'):
            self.stop_display()
    
    def display_screenshot(self, filepath: Path, duration: float = 2.0):
        """
        Display a specific screenshot for a duration
        
        Args:
            filepath: Path to screenshot file
            duration: Seconds to display
        """
        img = cv2.imread(str(filepath))
        
        # Get original filename
        filename = filepath.name
        cv2.putText(img, filename, (10, 20),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        cv2.imshow(self.display_window, img)
        cv2.waitKey(int(duration * 1000))


# Example usage
if __name__ == "__main__":
    import numpy as np
    
    # Create test screenshot (red square)
    test_screen = np.zeros((144, 160, 3), dtype=np.uint8)
    test_screen[50:100, 50:100] = [255, 0, 0]  # Red square
    
    # Initialize manager
    manager = ScreenshotManager("./test_screenshots")
    
    # Save test screenshot
    filepath = manager.save_screenshot(test_screen, "test_red", "overworld")
    print(f"Saved: {filepath}")
    
    # Get latest
    latest = manager.get_latest_screenshot()
    print(f"Latest: {latest}")
    
    # Create grid (with just one image)
    try:
        grid_path = manager.create_grid_view()
        print(f"Grid saved: {grid_path}")
    except ValueError as e:
        print(f"Grid creation: {e}")
    
    # Stats
    stats = manager.get_screenshot_stats()
    print(f"Stats: {stats}")
    
    # Live view example
    live = LiveView(manager)
    live.start_display()
    
    for i in range(10):
        # Create random screenshot
        random_screen = np.random.randint(0, 255, (144, 160, 3), dtype=np.uint8)
        manager.save_screenshot(random_screen, f"random_{i}")
        live.update_display(random_screen)
        time.sleep(0.5)
    
    live.stop_display()
