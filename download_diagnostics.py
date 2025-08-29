#!/usr/bin/env python3
"""
Quick diagnostic script to test download functionality
"""

import asyncio
import sys
from pathlib import Path

# Add the project root to Python path
sys.path.insert(0, str(Path(__file__).parent))

from downloader import AudioDownloader

async def test_download():
    """Test download functionality with timeout"""
    print("🔧 Starting download diagnostics...")
    
    # Test URLs
    test_urls = [
        "https://youtu.be/oJc0NyMqeHU?si=CYFIjVXIuybCA4JQ",  # Current problematic URL
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",        # Rick Roll (short, reliable)
        "https://youtu.be/dQw4w9WgXcQ",                       # Same as youtu.be format
    ]
    
    downloader = AudioDownloader()
    
    for i, url in enumerate(test_urls, 1):
        print(f"\n📥 Test {i}: {url}")
        try:
            # Very short timeout for diagnostics
            result = await asyncio.wait_for(
                downloader.download_audio(url, quality="low"),
                timeout=60  # 1 minute max per test
            )
            
            if result:
                file_path, file_info = result
                print(f"✅ Success: {file_info.get('title', 'Unknown')} ({file_info.get('size_mb', 0):.1f}MB)")
                # Clean up test file
                try:
                    file_path.unlink()
                    print("🗑️ Test file cleaned up")
                except:
                    pass
            else:
                print("❌ Download returned None")
                
        except asyncio.TimeoutError:
            print(f"⏰ Test timed out after 60 seconds")
        except Exception as e:
            print(f"❌ Error: {e}")
    
    print("\n🏁 Diagnostics complete")

if __name__ == "__main__":
    asyncio.run(test_download())
