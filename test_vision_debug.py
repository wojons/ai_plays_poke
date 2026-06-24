#!/usr/bin/env python3
"""
Debug script to test vision API image delivery
"""

import os
import sys
import numpy as np
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from core.ai_client import GameAIManager
from PIL import Image
import base64
import io

def test_vision_image_encoding():
    """Test if images are being encoded correctly for OpenRouter API"""
    
    print("🧪 Testing Vision API Image Delivery")
    print("=" * 50)
    
    # Create fake Pokemon-like screenshot (red/blue pattern like battle UI)
    screenshot = np.zeros((144, 160, 3), dtype=np.uint8)
    
    # Add some patterns that look like Pokemon UI
    # Top left: HP bar area (green)
    screenshot[5:15, 5:50] = [0, 255, 0]  # Green HP bar
    
    # Bottom: dialog box (white background)
    screenshot[120:144, 10:150] = [255, 255, 255]  # White dialog box
    
    # Add some text-like pixels
    screenshot[130:135, 20:40] = [0, 0, 0]  # Black "text"
    
    print(f"📸 Created test screenshot: {screenshot.shape}")
    print(f"   Data type: {screenshot.dtype}")
    print(f"   Value range: {screenshot.min()} - {screenshot.max()}")
    
    # Test OpenRouter client
    try:
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            print("❌ No OPENROUTER_API_KEY found")
            return False
            
        print(f"✅ API key found: {api_key[:10]}...")
        
        ai_manager = GameAIManager(api_key=api_key)
        print("✅ AI Manager initialized")
        
        # Test vision analysis
        print("\n🤖 Calling vision API...")
        result = ai_manager.analyze_screenshot(screenshot)
        
        print(f"\n✅ Vision API call succeeded!")
        print(f"📊 Result: {result}")
        
        # Check if result makes sense
        screen_type = result.get('screen_type', 'unknown')
        print(f"🎯 Detected screen type: {screen_type}")
        
        # The key test: Does it seem like the AI actually saw the image?
        # If it returns battle/menu/overworld specifically, it probably saw it
        # If it returns "unknown" or defaults, the image wasn't processed
        
        if screen_type == "battle" or screen_type == "menu" or screen_type == "dialog":
            print("✅ AI likely processed the image correctly!")
            return True
        else:
            print("⚠️  AI may not have processed the image - got generic response")
            return False
            
    except Exception as e:
        print(f"❌ Vision API test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_image_encoding_pipeline():
    """Test the image encoding pipeline step by step"""
    
    print("\n🔍 Testing Image Encoding Pipeline")
    print("=" * 50)
    
    # Create test image
    screenshot = np.random.randint(0, 255, (144, 160, 3), dtype=np.uint8)
    
    print("1. Original numpy array:")
    print(f"   Shape: {screenshot.shape}")
    print(f"   Dtype: {screenshot.dtype}")
    
    # Step 1: Convert to PIL
    pil_img = Image.fromarray(screenshot)
    print(f"\n2. PIL Image:")
    print(f"   Size: {pil_img.size}")
    print(f"   Mode: {pil_img.mode}")
    
    # Step 2: Resize if needed
    if pil_img.size[0] > 1024:
        print("   Resizing... (not needed for 160x144)")
        pil_img = pil_img.resize((1024, int(1024 * pil_img.size[1] / pil_img.size[0])))
    
    # Step 3: Convert to base64
    buffered = io.BytesIO()
    pil_img.save(buffered, format="PNG")
    image_base64 = base64.b64encode(buffered.getvalue()).decode()
    
    print(f"\n3. Base64 encoded:")
    print(f"   Length: {len(image_base64)} characters")
    print(f"   Preview: {image_base64[:100]}...")
    
    # Step 4: Create data URL
    data_url = f"data:image/png;base64,{image_base64}"
    print(f"\n4. Data URL:")
    print(f"   Length: {len(data_url)} characters")
    print(f"   Preview: {data_url[:100]}...")
    
    # Verify it's valid base64
    try:
        decoded = base64.b64decode(image_base64)
        print(f"\n5. Verification:")
        print(f"   Decoded length: {len(decoded)} bytes")
        print(f"   ✅ Base64 encoding is valid")
        return True
    except Exception as e:
        print(f"\n5. Verification FAILED: {e}")
        return False

if __name__ == "__main__":
    print("🔧 Vision API Debug Tool")
    print("Testing image encoding and OpenRouter API delivery\n")
    
    # Test encoding pipeline
    encoding_ok = test_image_encoding_pipeline()
    
    # Test vision API
    if encoding_ok:
        print("\n" + "=" * 60)
        vision_ok = test_vision_image_encoding()
        
        if vision_ok:
            print("\n🎉 All tests passed!")
            sys.exit(0)
        else:
            print("\n❌ Vision API test failed")
            sys.exit(1)
    else:
        print("\n❌ Encoding pipeline test failed")
        sys.exit(1)
