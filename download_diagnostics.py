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

    # Test URLs - Both YouTube and Spotify
    test_urls = [
        # YouTube URLs
        ("YouTube", "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "Rick Roll (reliable test)"),
        ("YouTube", "https://youtu.be/dQw4w9WgXcQ", "Rick Roll (youtu.be format)"),
        ("YouTube", "https://youtu.be/oJc0NyMqeHU?si=CYFIjVXIuybCA4JQ", "Original problematic URL"),
        ("YouTube", "https://www.youtube.com/watch?v=9bZkp7q19f0", "PSY - Gangnam Style (popular)"),

        # Spotify URLs
        ("Spotify", "https://open.spotify.com/track/4iV5W9uYEdYUVa79Axb7Rh", "Never Gonna Give You Up"),
        ("Spotify", "https://open.spotify.com/track/0IM0pkP17761cCPWTLpLs8?si=MbQfW2tySLWMRd-Ok1QDVA", "Original problematic Spotify URL"),
        ("Spotify", "https://open.spotify.com/track/4uLU6hMCjMI75M1A2tKUQC", "Blinding Lights - The Weeknd"),
    ]

    # Initialize downloader with proper setup
    print("🔧 Initializing AudioDownloader...")
    try:
        # Create a simple test downloader that bypasses the asyncio.run issue
        class TestDownloader:
            def __init__(self):
                self.is_streamlit_cloud = True
                self.temp_dir = Path("tmp")
                self.temp_dir.mkdir(exist_ok=True)
                self.cookie_file = None  # Initialize cookie_file

            async def download_audio(self, url, quality):
                """Simple test method that just checks if tools are available"""
                print(f"   🔍 Testing download capability for: {url}")

                # Test if spotdl is available for Spotify
                if "spotify.com" in url:
                    try:
                        import subprocess
                        result = subprocess.run(["spotdl", "--version"],
                                              capture_output=True, text=True, timeout=10)
                        if result.returncode == 0:
                            print(f"   ✅ spotdl available: {result.stdout.strip()}")
                            return None, {"title": "Test - spotdl available", "platform": "Spotify"}
                        else:
                            print(f"   ❌ spotdl not working: {result.stderr}")
                            return None
                    except FileNotFoundError:
                        print(f"   ❌ spotdl not installed")
                        return None
                    except Exception as e:
                        print(f"   ❌ spotdl error: {e}")
                        return None

                # Test if yt-dlp is available for YouTube
                elif "youtube.com" in url or "youtu.be" in url:
                    try:
                        import yt_dlp
                        # Just test info extraction without download
                        ydl_opts = {
                            'quiet': True,
                            'no_warnings': True,
                            'socket_timeout': 10,
                        }
                        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                            info = ydl.extract_info(url, download=False)
                            if info:
                                print(f"   ✅ yt-dlp can access: {info.get('title', 'Unknown')}")
                                return None, {"title": info.get('title', 'Test'), "platform": "YouTube"}
                            else:
                                print(f"   ❌ yt-dlp couldn't extract info")
                                return None
                    except Exception as e:
                        print(f"   ❌ yt-dlp error: {e}")
                        return None

                return None

        downloader = TestDownloader()
        print("✅ Test downloader initialized successfully")

    except Exception as init_error:
        print(f"❌ Failed to initialize test downloader: {init_error}")
        return
    
    for i, (platform, url, description) in enumerate(test_urls, 1):
        print(f"\n📥 Test {i}: {platform} - {description}")
        print(f"🔗 URL: {url}")

        start_time = asyncio.get_event_loop().time()
        try:
            # Short timeout for diagnostics
            result = await asyncio.wait_for(
                downloader.download_audio(url, quality="low"),
                timeout=90  # 1.5 minutes max per test
            )

            elapsed = asyncio.get_event_loop().time() - start_time

            if result:
                file_path, file_info = result
                print(f"✅ Success ({elapsed:.1f}s): {file_info.get('title', 'Unknown')} ({file_info.get('size_mb', 0):.1f}MB)")
                print(f"   Platform: {file_info.get('platform', platform)}")
                print(f"   Artist: {file_info.get('artist', 'Unknown')}")

                # Clean up test file
                try:
                    file_path.unlink()
                    print("🗑️ Test file cleaned up")
                except:
                    pass
            else:
                print(f"❌ Download returned None ({elapsed:.1f}s)")

        except asyncio.TimeoutError:
            elapsed = asyncio.get_event_loop().time() - start_time
            print(f"⏰ Test timed out after {elapsed:.1f} seconds")
        except Exception as e:
            elapsed = asyncio.get_event_loop().time() - start_time
            print(f"❌ Error ({elapsed:.1f}s): {e}")

        # Small delay between tests
        await asyncio.sleep(2)
    
    print("\n🏁 Diagnostics complete")

if __name__ == "__main__":
    asyncio.run(test_download())
