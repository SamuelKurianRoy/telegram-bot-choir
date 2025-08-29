"""
Audio Downloader Module for Telegram Bot
Supports YouTube and Spotify audio downloads
"""

import os
import re
import sys
import time
import random
import asyncio
import logging
import subprocess as sp
import platform
from pathlib import Path
from typing import Dict, Optional, Tuple
import hashlib
import json
from datetime import datetime, timedelta
import shutil

try:
    import yt_dlp
except ImportError:
    yt_dlp = None

try:
    import requests
except ImportError:
    requests = None

try:
    import tempfile
    import tarfile
except ImportError:
    tempfile = None
    tarfile = None

# Setup logging
logger = logging.getLogger(__name__)

# Setup file logging for downloader (will be uploaded to BFILE_ID)
downloader_logger = logging.getLogger("downloader_debug")
if not downloader_logger.handlers:
    downloader_logger.setLevel(logging.INFO)
    downloader_logger.propagate = False

    # File handler for downloader logs
    downloader_handler = logging.FileHandler("downloader_log.txt", mode='w', encoding='utf-8')
    downloader_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    downloader_logger.addHandler(downloader_handler)

class AudioDownloader:
    """Audio downloader class for YouTube and Spotify"""

    def __init__(self, temp_dir: str = "temp"):
        # Detect if running on Streamlit Cloud
        self.is_streamlit_cloud = self._detect_streamlit_cloud()
        logger.info(f"Running on Streamlit Cloud: {self.is_streamlit_cloud}")
        downloader_logger.info(f"AudioDownloader initialized - Streamlit Cloud: {self.is_streamlit_cloud}")

        self.temp_dir = Path(temp_dir)
        self.temp_dir.mkdir(exist_ok=True)

        # Set FFmpeg path - use the complete setup from audio_downloader_bot.py
        self.ffmpeg_path = asyncio.run(self._setup_ffmpeg())
        downloader_logger.info(f"FFmpeg setup result: {self.ffmpeg_path}")

        # Configure FFmpeg in PATH if local installation found
        if self.ffmpeg_path and self.ffmpeg_path != "system":
            # Add FFmpeg directory to PATH (same as audio_downloader_bot.py)
            current_path = os.environ.get("PATH", "")
            if self.ffmpeg_path not in current_path:
                os.environ["PATH"] = self.ffmpeg_path + os.pathsep + current_path
                logger.info(f"Added FFmpeg to PATH: {self.ffmpeg_path}")
                downloader_logger.info(f"Added FFmpeg to PATH: {self.ffmpeg_path}")

            # Configure spotdl to use local FFmpeg
            system = platform.system().lower()
            if system == "windows":
                ffmpeg_exe = Path(self.ffmpeg_path) / "ffmpeg.exe"
            else:
                ffmpeg_exe = Path(self.ffmpeg_path) / "ffmpeg"

            if ffmpeg_exe.exists():
                os.environ["FFMPEG_BINARY"] = str(ffmpeg_exe)
                logger.info(f"Set FFMPEG_BINARY environment variable: {ffmpeg_exe}")
                downloader_logger.info(f"Set FFMPEG_BINARY environment variable: {ffmpeg_exe}")

        # For Streamlit Cloud, ensure FFmpeg is configured for spotdl
        if self.is_streamlit_cloud and self.ffmpeg_path == "system":
            os.environ["FFMPEG_BINARY"] = "ffmpeg"
            logger.info("Configured spotdl to use system FFmpeg on Streamlit Cloud")
            downloader_logger.info("Configured spotdl to use system FFmpeg on Streamlit Cloud")

        # Setup cookie support for bypassing YouTube bot detection
        self.cookie_file = self._setup_cookies()
        downloader_logger.info(f"Cookie support initialized: {self.cookie_file}")

    def _detect_streamlit_cloud(self) -> bool:
        """Detect if running on Streamlit Cloud"""
        # Check for Streamlit Cloud environment indicators
        streamlit_indicators = [
            os.environ.get("STREAMLIT_SHARING_MODE"),
            os.environ.get("STREAMLIT_SERVER_PORT"),
            "streamlit" in os.environ.get("HOME", "").lower(),
            "app" in os.environ.get("HOME", "").lower(),
        ]
        return any(streamlit_indicators)

    async def _test_ffmpeg_on_streamlit_cloud(self) -> bool:
        """Test FFmpeg specifically for Streamlit Cloud environment"""
        try:
            # Simple test that should work on Streamlit Cloud
            test_result = sp.run([
                "ffmpeg", "-f", "lavfi", "-i", "testsrc=duration=0.1:size=32x32:rate=1",
                "-f", "null", "-"
            ], capture_output=True, text=True, timeout=10)

            if test_result.returncode == 0:
                logger.info("FFmpeg test passed on Streamlit Cloud")
                return True
            else:
                logger.warning(f"FFmpeg test failed on Streamlit Cloud: {test_result.stderr}")
                return False

        except Exception as e:
            logger.warning(f"FFmpeg test error on Streamlit Cloud: {e}")
            return False

    async def _setup_ffmpeg(self) -> Optional[str]:
        """Setup FFmpeg using the complete logic from audio_downloader_bot.py"""
        try:
            # Use the complete download_ffmpeg function from audio_downloader_bot.py
            ffmpeg_result = await self.download_ffmpeg()

            if ffmpeg_result == "system":
                # System FFmpeg is available
                self.ffmpeg_path = "system"
                logger.info("Using system FFmpeg installation")
                downloader_logger.info("Using system FFmpeg installation")

                # Configure spotdl to use system FFmpeg
                await self.configure_spotdl_ffmpeg()

            elif ffmpeg_result:
                # Local FFmpeg directory
                self.ffmpeg_path = ffmpeg_result
                # Add FFmpeg directory to PATH
                current_path = os.environ.get("PATH", "")
                if self.ffmpeg_path not in current_path:
                    os.environ["PATH"] = self.ffmpeg_path + os.pathsep + current_path
                logger.info(f"FFmpeg set up at: {self.ffmpeg_path}")
                downloader_logger.info(f"FFmpeg set up at: {self.ffmpeg_path}")

                # Configure spotdl to use local FFmpeg
                await self.configure_spotdl_ffmpeg()

            else:
                # No FFmpeg available
                self.ffmpeg_path = None
                logger.warning("FFmpeg not available - some audio conversions may not work")
                logger.info("Bot will try to download audio in native formats when possible")
                downloader_logger.warning("FFmpeg not available - some audio conversions may not work")

            return self.ffmpeg_path

            # Check for FFmpeg in the local repository directory
            ffmpeg_dir = Path.cwd() / "ffmpeg"

            # Determine platform and appropriate executable name
            system = platform.system().lower()

            if system == "windows":
                ffmpeg_names = ["ffmpeg.exe"]
            else:
                ffmpeg_names = ["ffmpeg"]

            # Check if FFmpeg exists in the local directory
            for name in ffmpeg_names:
                ffmpeg_path = ffmpeg_dir / name
                if ffmpeg_path.exists():
                    logger.info(f"Found local FFmpeg at: {ffmpeg_path}")
                    # Make sure it's executable (Linux/Mac only)
                    if system != "windows":
                        try:
                            os.chmod(ffmpeg_path, 0o755)
                        except Exception as chmod_error:
                            logger.warning(f"Could not make FFmpeg executable: {chmod_error}")

                    # Test if it works
                    try:
                        test_result = sp.run([str(ffmpeg_path), "-version"],
                                           capture_output=True, text=True, timeout=10)
                        if test_result.returncode == 0:
                            logger.info("Local FFmpeg is working correctly")
                            downloader_logger.info("Local FFmpeg is working correctly")
                            return str(ffmpeg_dir)
                        else:
                            logger.warning(f"Local FFmpeg test failed: {test_result.stderr}")
                    except Exception as test_error:
                        logger.warning(f"Could not test local FFmpeg: {test_error}")

            # If we're on Linux and only have Windows executables, try to download Linux version
            if system == "linux" and (ffmpeg_dir / "ffmpeg.exe").exists():
                logger.info("Found Windows FFmpeg but running on Linux, downloading Linux version")
                try:
                    import requests
                    import tempfile
                    import tarfile

                    # Try multiple sources for Linux FFmpeg (updated URLs)
                    ffmpeg_urls = [
                        # John Van Sickle static builds (most reliable)
                        "https://johnvansickle.com/ffmpeg/builds/ffmpeg-git-amd64-static.tar.xz",
                        # Alternative: try to get latest release from GitHub
                        "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz",
                        # Fallback: older but stable version
                        "https://github.com/BtbN/FFmpeg-Builds/releases/download/autobuild-2024-03-17-12-49/ffmpeg-n6.1.1-26-g806c2d9c72-linux64-gpl-6.1.tar.xz",
                    ]

                    success = False
                    for ffmpeg_url in ffmpeg_urls:
                        try:
                            logger.info(f"Trying to download from: {ffmpeg_url}")
                            response = requests.get(ffmpeg_url, stream=True, timeout=60)
                            response.raise_for_status()

                            # Save the Linux version
                            linux_ffmpeg_path = ffmpeg_dir / "ffmpeg"

                            if ffmpeg_url.endswith('.tar.xz'):
                                # Handle compressed archives
                                with tempfile.NamedTemporaryFile(delete=False, suffix='.tar.xz') as tmp_file:
                                    for chunk in response.iter_content(chunk_size=8192):
                                        tmp_file.write(chunk)
                                    tmp_file.flush()

                                    logger.info("Downloaded archive, extracting...")

                                    try:
                                        # Extract the archive
                                        with tarfile.open(tmp_file.name, 'r:xz') as tar:
                                            # Find ffmpeg binary in the archive
                                            ffmpeg_member = None
                                            for member in tar.getmembers():
                                                if member.name.endswith('/ffmpeg') or member.name == 'ffmpeg':
                                                    ffmpeg_member = member
                                                    break

                                            if ffmpeg_member:
                                                # Extract just the ffmpeg binary
                                                tar.extract(ffmpeg_member, path=str(ffmpeg_dir))

                                                # Move to the correct location if needed
                                                extracted_path = ffmpeg_dir / ffmpeg_member.name
                                                final_path = ffmpeg_dir / "ffmpeg"

                                                if extracted_path != final_path:
                                                    extracted_path.rename(final_path)

                                                logger.info(f"Successfully extracted FFmpeg to: {final_path}")
                                            else:
                                                logger.warning("FFmpeg binary not found in archive")
                                                continue

                                    except Exception as extract_error:
                                        logger.warning(f"Failed to extract archive: {extract_error}")
                                        continue
                                    finally:
                                        # Clean up temp file
                                        try:
                                            os.unlink(tmp_file.name)
                                        except:
                                            pass
                            else:
                                # Direct binary download
                                with open(linux_ffmpeg_path, 'wb') as f:
                                    for chunk in response.iter_content(chunk_size=8192):
                                        f.write(chunk)

                            # Make it executable
                            os.chmod(linux_ffmpeg_path, 0o755)

                            # Test the downloaded version with more thorough testing
                            try:
                                # First test: version check
                                test_result = sp.run([str(linux_ffmpeg_path), "-version"],
                                                   capture_output=True, text=True, timeout=10)
                                if test_result.returncode != 0:
                                    logger.warning(f"Downloaded FFmpeg version test failed: {test_result.stderr}")
                                    linux_ffmpeg_path.unlink(missing_ok=True)
                                    continue

                                # Second test: simple conversion test to catch crashes
                                test_conversion = sp.run([
                                    str(linux_ffmpeg_path), "-f", "lavfi", "-i", "testsrc=duration=1:size=320x240:rate=1",
                                    "-f", "null", "-"
                                ], capture_output=True, text=True, timeout=15)

                                if test_conversion.returncode == 0:
                                    logger.info("Downloaded Linux FFmpeg is working correctly")
                                    success = True
                                    break
                                else:
                                    logger.warning(f"Downloaded FFmpeg conversion test failed (code {test_conversion.returncode}): {test_conversion.stderr}")
                                    linux_ffmpeg_path.unlink(missing_ok=True)
                                    continue

                            except Exception as test_error:
                                logger.warning(f"Error testing downloaded FFmpeg: {test_error}")
                                linux_ffmpeg_path.unlink(missing_ok=True)
                                continue

                        except Exception as url_error:
                            logger.warning(f"Failed to download from {ffmpeg_url}: {url_error}")
                            continue

                    if success:
                        return str(ffmpeg_dir)
                    else:
                        logger.error("All FFmpeg download attempts failed")

                except Exception as download_error:
                    logger.error(f"Failed to download Linux FFmpeg: {download_error}")

            # Last resort: try to install FFmpeg using system package manager (for Streamlit Cloud)
            if system == "linux":
                logger.info("Attempting to install FFmpeg using system package manager...")
                try:
                    # First try: update package list
                    logger.info("Updating package list...")
                    update_result = sp.run(["apt-get", "update"], capture_output=True, text=True, timeout=60)

                    if update_result.returncode == 0:
                        logger.info("Package list updated successfully")

                        # Second try: install FFmpeg
                        logger.info("Installing FFmpeg...")
                        install_result = sp.run(
                            ["apt-get", "install", "-y", "ffmpeg"],
                            capture_output=True, text=True, timeout=120
                        )

                        if install_result.returncode == 0:
                            logger.info("Successfully installed FFmpeg via apt-get")

                            # Test if it's now available and working
                            try:
                                test_result = sp.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=10)
                                if test_result.returncode == 0:
                                    logger.info("System FFmpeg is now working")

                                    # Additional test to make sure it doesn't crash
                                    test_conversion = sp.run([
                                        "ffmpeg", "-f", "lavfi", "-i", "testsrc=duration=1:size=320x240:rate=1",
                                        "-f", "null", "-"
                                    ], capture_output=True, text=True, timeout=15)

                                    if test_conversion.returncode == 0:
                                        logger.info("System FFmpeg conversion test passed")
                                        return "system"  # System FFmpeg is available and working
                                    else:
                                        logger.warning(f"System FFmpeg conversion test failed: {test_conversion.stderr}")
                                else:
                                    logger.warning(f"System FFmpeg version test failed: {test_result.stderr}")
                            except Exception as test_error:
                                logger.warning(f"Error testing system FFmpeg: {test_error}")
                        else:
                            logger.warning(f"Failed to install FFmpeg via apt-get: {install_result.stderr}")
                    else:
                        logger.warning(f"Failed to update package list: {update_result.stderr}")

                except Exception as install_error:
                    logger.warning(f"Could not install FFmpeg via package manager: {install_error}")

            # If no working FFmpeg found, create directory and log the issue
            ffmpeg_dir.mkdir(exist_ok=True)
            logger.warning("No working FFmpeg found")
            logger.info("Bot will work with limited functionality - some audio conversions may not be available")
            logger.info("yt-dlp will try to download audio in native formats when possible")

            # Return None to indicate FFmpeg is not available
            return None

        except Exception as e:
            logger.error(f"Error setting up FFmpeg: {e}")
            downloader_logger.error(f"Error setting up FFmpeg: {e}")
            return None

    def _setup_cookies(self) -> Optional[str]:
        """Setup cookie support for bypassing YouTube bot detection"""
        try:
            if self.is_streamlit_cloud:
                # Streamlit Cloud: Only check for uploaded cookie files
                logger.info("Running on Streamlit Cloud - checking for uploaded cookie files only")
                downloader_logger.info("Streamlit Cloud mode: Browser cookie extraction disabled")

                cookie_locations = [
                    # Only check for manually uploaded cookie files
                    self.temp_dir / "youtube_cookies.txt",
                    Path.cwd() / "youtube_cookies.txt",
                    Path.cwd() / "cookies.txt",
                ]

                for cookie_path in cookie_locations:
                    if cookie_path.exists():
                        logger.info(f"Found uploaded cookie file: {cookie_path}")
                        downloader_logger.info(f"Using uploaded cookie file: {cookie_path}")
                        return str(cookie_path)

                logger.info("No uploaded cookie files found - using Streamlit Cloud optimized mode")
                downloader_logger.info("Streamlit Cloud: No cookies, using cloud-optimized anti-detection")
                return None

            else:
                # Local environment: Full browser cookie support
                cookie_locations = [
                    # Netscape format cookie files
                    self.temp_dir / "youtube_cookies.txt",
                    Path.cwd() / "youtube_cookies.txt",
                    Path.cwd() / "cookies.txt",
                    # Browser cookie extraction (if available)
                    self._get_browser_cookie_path("chrome"),
                    self._get_browser_cookie_path("firefox"),
                    self._get_browser_cookie_path("brave"),
                    self._get_browser_cookie_path("edge"),
                ]

                # Check for existing cookie files
                for cookie_path in cookie_locations:
                    if cookie_path and Path(cookie_path).exists():
                        logger.info(f"Found cookie file: {cookie_path}")
                        downloader_logger.info(f"Using cookie file: {cookie_path}")
                        return str(cookie_path)

                # Try to extract cookies from browsers automatically
                browser_success = self._try_extract_browser_cookies()
                if browser_success:
                    return browser_success

                logger.info("No cookie file found - will use cookieless mode")
                downloader_logger.info("Cookie setup: No cookies available, using enhanced anti-detection instead")
                return None

        except Exception as e:
            logger.warning(f"Cookie setup failed: {e}")
            downloader_logger.warning(f"Cookie setup failed: {e}")
            return None

    def _get_browser_cookie_path(self, browser: str) -> Optional[str]:
        """Get the cookie database path for a specific browser"""
        try:
            system = platform.system().lower()
            home = Path.home()

            if browser == "chrome":
                if system == "windows":
                    return home / "AppData/Local/Google/Chrome/User Data/Default/Cookies"
                elif system == "darwin":  # macOS
                    return home / "Library/Application Support/Google/Chrome/Default/Cookies"
                else:  # Linux
                    return home / ".config/google-chrome/Default/Cookies"

            elif browser == "brave":
                if system == "windows":
                    return home / "AppData/Local/BraveSoftware/Brave-Browser/User Data/Default/Cookies"
                elif system == "darwin":  # macOS
                    return home / "Library/Application Support/BraveSoftware/Brave-Browser/Default/Cookies"
                else:  # Linux
                    return home / ".config/BraveSoftware/Brave-Browser/Default/Cookies"

            elif browser == "firefox":
                if system == "windows":
                    profiles_dir = home / "AppData/Roaming/Mozilla/Firefox/Profiles"
                elif system == "darwin":  # macOS
                    profiles_dir = home / "Library/Application Support/Firefox/Profiles"
                else:  # Linux
                    profiles_dir = home / ".mozilla/firefox"

                if profiles_dir.exists():
                    # Find the default profile
                    for profile in profiles_dir.iterdir():
                        if profile.is_dir() and "default" in profile.name.lower():
                            return profile / "cookies.sqlite"

            elif browser == "edge":
                if system == "windows":
                    return home / "AppData/Local/Microsoft/Edge/User Data/Default/Cookies"
                elif system == "darwin":  # macOS
                    return home / "Library/Application Support/Microsoft Edge/Default/Cookies"
                else:  # Linux
                    return home / ".config/microsoft-edge/Default/Cookies"

        except Exception as e:
            logger.debug(f"Error getting {browser} cookie path: {e}")

        return None

    def _try_extract_browser_cookies(self) -> Optional[str]:
        """Try to extract cookies from browsers using yt-dlp's built-in functionality"""
        try:
            # Create a temporary cookie file
            cookie_file = self.temp_dir / "extracted_cookies.txt"

            # Try different browsers in order of preference (Brave first as it's less tracked)
            browsers = ["brave", "chrome", "firefox", "edge"]

            for browser in browsers:
                try:
                    logger.info(f"Attempting to extract cookies from {browser}...")

                    # Use yt-dlp's cookie extraction
                    import yt_dlp

                    # Test extraction with a simple YouTube URL
                    test_opts = {
                        'quiet': True,
                        'no_warnings': True,
                        'extract_flat': True,
                        'cookies_from_browser': (browser, None, None, None),
                        'cookiefile': str(cookie_file),
                    }

                    with yt_dlp.YoutubeDL(test_opts) as ydl:
                        # Try to extract info from YouTube homepage to test cookies
                        ydl.extract_info("https://www.youtube.com", download=False)

                    if cookie_file.exists() and cookie_file.stat().st_size > 0:
                        logger.info(f"Successfully extracted cookies from {browser}")
                        downloader_logger.info(f"Cookie extraction successful: {browser} -> {cookie_file}")
                        return str(cookie_file)

                except Exception as e:
                    logger.debug(f"Failed to extract cookies from {browser}: {e}")
                    continue

            logger.info("Could not extract cookies from any browser")
            return None

        except Exception as e:
            logger.warning(f"Browser cookie extraction failed: {e}")
            return None

    def _run_spotdl_command(self, args: list, timeout: int = 10):
        """Run spotdl command with appropriate Python executable"""
        import subprocess as sp

        # Determine the correct Python command
        if self.is_streamlit_cloud:
            # Streamlit Cloud uses python3
            cmd = ["python3", "-m", "spotdl"] + args
        else:
            # Local environment
            import platform
            if platform.system().lower() == "windows":
                cmd = ["py", "-m", "spotdl"] + args
            else:
                cmd = ["python3", "-m", "spotdl"] + args

        return sp.run(cmd, capture_output=True, text=True, timeout=timeout)

    async def configure_spotdl_ffmpeg(self):
        """Configure spotdl to use the available FFmpeg installation (from audio_downloader_bot.py)"""
        try:
            if self.ffmpeg_path == "system":
                # For system FFmpeg, spotdl should find it automatically
                os.environ["FFMPEG_BINARY"] = "ffmpeg"
                logger.info("Configured spotdl to use system FFmpeg")
                downloader_logger.info("Configured spotdl to use system FFmpeg")

            elif self.ffmpeg_path:
                # For local FFmpeg, set the full path
                system = platform.system().lower()
                if system == "windows":
                    ffmpeg_exe = Path(self.ffmpeg_path) / "ffmpeg.exe"
                else:
                    ffmpeg_exe = Path(self.ffmpeg_path) / "ffmpeg"

                if ffmpeg_exe.exists():
                    os.environ["FFMPEG_BINARY"] = str(ffmpeg_exe)
                    logger.info(f"Configured spotdl to use local FFmpeg: {ffmpeg_exe}")
                    downloader_logger.info(f"Configured spotdl to use local FFmpeg: {ffmpeg_exe}")
                else:
                    logger.warning(f"FFmpeg executable not found at: {ffmpeg_exe}")
                    downloader_logger.warning(f"FFmpeg executable not found at: {ffmpeg_exe}")

        except Exception as e:
            logger.error(f"Error configuring spotdl FFmpeg: {e}")
            downloader_logger.error(f"Error configuring spotdl FFmpeg: {e}")

    async def download_ffmpeg(self):
        """Complete FFmpeg download function from audio_downloader_bot.py"""
        try:
            downloader_logger.info("Starting FFmpeg setup process")

            # First, check if ffmpeg is already installed on the system
            try:
                result = sp.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    logger.info("FFmpeg is already installed on the system")
                    downloader_logger.info("FFmpeg is already installed on the system")
                    return "system"  # Indicates system FFmpeg should be used
            except Exception as e:
                logger.info("FFmpeg not found in system PATH, checking local directory")
                downloader_logger.info(f"FFmpeg not found in system PATH: {e}")

            # Check for FFmpeg in the local repository directory
            ffmpeg_dir = Path.cwd() / "ffmpeg"
            downloader_logger.info(f"Checking for local FFmpeg in: {ffmpeg_dir}")

            # Determine platform and appropriate executable name
            system = platform.system().lower()
            downloader_logger.info(f"Detected platform: {system}")

            if system == "windows":
                ffmpeg_names = ["ffmpeg.exe"]
            else:
                ffmpeg_names = ["ffmpeg"]

            # Check if FFmpeg exists in the local directory
            for name in ffmpeg_names:
                ffmpeg_path = ffmpeg_dir / name
                if ffmpeg_path.exists():
                    logger.info(f"Found local FFmpeg at: {ffmpeg_path}")
                    downloader_logger.info(f"Found local FFmpeg at: {ffmpeg_path}")

                    # Make sure it's executable (Linux/Mac only)
                    if system != "windows":
                        try:
                            os.chmod(ffmpeg_path, 0o755)
                        except Exception as chmod_error:
                            logger.warning(f"Could not make FFmpeg executable: {chmod_error}")

                    # Test if it works
                    try:
                        test_result = sp.run([str(ffmpeg_path), "-version"],
                                           capture_output=True, text=True, timeout=10)
                        if test_result.returncode == 0:
                            logger.info("Local FFmpeg is working correctly")
                            downloader_logger.info("Local FFmpeg is working correctly")
                            return str(ffmpeg_dir)
                        else:
                            logger.warning(f"Local FFmpeg test failed: {test_result.stderr}")
                            downloader_logger.warning(f"Local FFmpeg test failed: {test_result.stderr}")
                    except Exception as test_error:
                        logger.warning(f"Could not test local FFmpeg: {test_error}")
                        downloader_logger.warning(f"Could not test local FFmpeg: {test_error}")

            # If we're on Linux and only have Windows executables, try to download Linux version
            if system == "linux" and (ffmpeg_dir / "ffmpeg.exe").exists():
                logger.info("Found Windows FFmpeg but running on Linux, downloading Linux version")
                downloader_logger.info("Found Windows FFmpeg but running on Linux, downloading Linux version")

                result = await self._download_linux_ffmpeg(ffmpeg_dir)
                if result:
                    return result

            # Last resort: try to install FFmpeg using system package manager (for Streamlit Cloud)
            if system == "linux":
                logger.info("Attempting to install FFmpeg using system package manager...")
                downloader_logger.info("Attempting to install FFmpeg using system package manager...")

                result = await self._install_system_ffmpeg()
                if result:
                    return result

            # If no working FFmpeg found, create directory and log the issue
            ffmpeg_dir.mkdir(exist_ok=True)
            logger.warning("No working FFmpeg found")
            downloader_logger.warning("No working FFmpeg found")
            logger.info("Bot will work with limited functionality - some audio conversions may not be available")
            logger.info("yt-dlp will try to download audio in native formats when possible")

            # Return None to indicate FFmpeg is not available
            return None

        except Exception as e:
            logger.error(f"Error in download_ffmpeg: {e}")
            downloader_logger.error(f"Error in download_ffmpeg: {e}")
            return None

    async def _download_linux_ffmpeg(self, ffmpeg_dir: Path) -> Optional[str]:
        """Download Linux FFmpeg binary (from audio_downloader_bot.py)"""
        try:
            import requests
            import tempfile
            import tarfile

            # Try multiple sources for Linux FFmpeg (updated URLs)
            ffmpeg_urls = [
                # John Van Sickle static builds (most reliable)
                "https://johnvansickle.com/ffmpeg/builds/ffmpeg-git-amd64-static.tar.xz",
                # Alternative: try to get latest release from GitHub
                "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz",
                # Fallback: older but stable version
                "https://github.com/BtbN/FFmpeg-Builds/releases/download/autobuild-2024-03-17-12-49/ffmpeg-n6.1.1-26-g806c2d9c72-linux64-gpl-6.1.tar.xz",
            ]

            success = False
            for ffmpeg_url in ffmpeg_urls:
                try:
                    logger.info(f"Trying to download from: {ffmpeg_url}")
                    downloader_logger.info(f"Trying to download from: {ffmpeg_url}")

                    response = requests.get(ffmpeg_url, stream=True, timeout=60)
                    response.raise_for_status()

                    # Save the Linux version
                    linux_ffmpeg_path = ffmpeg_dir / "ffmpeg"

                    if ffmpeg_url.endswith('.tar.xz'):
                        # Handle compressed archives
                        with tempfile.NamedTemporaryFile(delete=False, suffix='.tar.xz') as tmp_file:
                            for chunk in response.iter_content(chunk_size=8192):
                                tmp_file.write(chunk)
                            tmp_file.flush()

                            logger.info("Downloaded archive, extracting...")
                            downloader_logger.info("Downloaded archive, extracting...")

                            try:
                                # Extract the archive
                                with tarfile.open(tmp_file.name, 'r:xz') as tar:
                                    # Find ffmpeg binary in the archive
                                    ffmpeg_member = None
                                    for member in tar.getmembers():
                                        if member.name.endswith('/ffmpeg') or member.name == 'ffmpeg':
                                            ffmpeg_member = member
                                            break

                                    if ffmpeg_member:
                                        # Extract just the ffmpeg binary
                                        tar.extract(ffmpeg_member, path=str(ffmpeg_dir))

                                        # Move to the correct location if needed
                                        extracted_path = ffmpeg_dir / ffmpeg_member.name
                                        final_path = ffmpeg_dir / "ffmpeg"

                                        if extracted_path != final_path:
                                            extracted_path.rename(final_path)

                                        logger.info(f"Successfully extracted FFmpeg to: {final_path}")
                                        downloader_logger.info(f"Successfully extracted FFmpeg to: {final_path}")
                                    else:
                                        logger.warning("FFmpeg binary not found in archive")
                                        downloader_logger.warning("FFmpeg binary not found in archive")
                                        continue

                            except Exception as extract_error:
                                logger.warning(f"Failed to extract archive: {extract_error}")
                                downloader_logger.warning(f"Failed to extract archive: {extract_error}")
                                continue
                            finally:
                                # Clean up temp file
                                try:
                                    os.unlink(tmp_file.name)
                                except:
                                    pass
                    else:
                        # Direct binary download
                        with open(linux_ffmpeg_path, 'wb') as f:
                            for chunk in response.iter_content(chunk_size=8192):
                                f.write(chunk)

                    # Make it executable
                    os.chmod(linux_ffmpeg_path, 0o755)

                    # Test the downloaded version with more thorough testing
                    try:
                        # First test: version check
                        test_result = sp.run([str(linux_ffmpeg_path), "-version"],
                                           capture_output=True, text=True, timeout=10)
                        if test_result.returncode != 0:
                            logger.warning(f"Downloaded FFmpeg version test failed: {test_result.stderr}")
                            downloader_logger.warning(f"Downloaded FFmpeg version test failed: {test_result.stderr}")
                            linux_ffmpeg_path.unlink(missing_ok=True)
                            continue

                        # Second test: simple conversion test to catch crashes
                        test_conversion = sp.run([
                            str(linux_ffmpeg_path), "-f", "lavfi", "-i", "testsrc=duration=1:size=320x240:rate=1",
                            "-f", "null", "-"
                        ], capture_output=True, text=True, timeout=15)

                        if test_conversion.returncode == 0:
                            logger.info("Downloaded Linux FFmpeg is working correctly")
                            downloader_logger.info("Downloaded Linux FFmpeg is working correctly")
                            success = True
                            break
                        else:
                            logger.warning(f"Downloaded FFmpeg conversion test failed (code {test_conversion.returncode}): {test_conversion.stderr}")
                            downloader_logger.warning(f"Downloaded FFmpeg conversion test failed (code {test_conversion.returncode}): {test_conversion.stderr}")
                            linux_ffmpeg_path.unlink(missing_ok=True)
                            continue

                    except Exception as test_error:
                        logger.warning(f"Error testing downloaded FFmpeg: {test_error}")
                        downloader_logger.warning(f"Error testing downloaded FFmpeg: {test_error}")
                        linux_ffmpeg_path.unlink(missing_ok=True)
                        continue

                except Exception as url_error:
                    logger.warning(f"Failed to download from {ffmpeg_url}: {url_error}")
                    downloader_logger.warning(f"Failed to download from {ffmpeg_url}: {url_error}")
                    continue

            if success:
                return str(ffmpeg_dir)
            else:
                logger.error("All FFmpeg download attempts failed")
                downloader_logger.error("All FFmpeg download attempts failed")
                return None

        except Exception as download_error:
            logger.error(f"Failed to download Linux FFmpeg: {download_error}")
            downloader_logger.error(f"Failed to download Linux FFmpeg: {download_error}")
            return None

    async def _install_system_ffmpeg(self) -> Optional[str]:
        """Install FFmpeg using system package manager (from audio_downloader_bot.py)"""
        try:
            # First try: update package list
            logger.info("Updating package list...")
            downloader_logger.info("Updating package list...")

            update_result = sp.run(["apt-get", "update"], capture_output=True, text=True, timeout=60)

            if update_result.returncode == 0:
                logger.info("Package list updated successfully")
                downloader_logger.info("Package list updated successfully")

                # Second try: install FFmpeg
                logger.info("Installing FFmpeg...")
                downloader_logger.info("Installing FFmpeg...")

                install_result = sp.run(
                    ["apt-get", "install", "-y", "ffmpeg"],
                    capture_output=True, text=True, timeout=120
                )

                if install_result.returncode == 0:
                    logger.info("Successfully installed FFmpeg via apt-get")
                    downloader_logger.info("Successfully installed FFmpeg via apt-get")

                    # Test if it's now available and working
                    try:
                        test_result = sp.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=10)
                        if test_result.returncode == 0:
                            logger.info("System FFmpeg is now working")
                            downloader_logger.info("System FFmpeg is now working")

                            # Additional test to make sure it doesn't crash
                            test_conversion = sp.run([
                                "ffmpeg", "-f", "lavfi", "-i", "testsrc=duration=1:size=320x240:rate=1",
                                "-f", "null", "-"
                            ], capture_output=True, text=True, timeout=15)

                            if test_conversion.returncode == 0:
                                logger.info("System FFmpeg conversion test passed")
                                downloader_logger.info("System FFmpeg conversion test passed")
                                return "system"  # System FFmpeg is available and working
                            else:
                                logger.warning(f"System FFmpeg conversion test failed: {test_conversion.stderr}")
                                downloader_logger.warning(f"System FFmpeg conversion test failed: {test_conversion.stderr}")
                        else:
                            logger.warning(f"System FFmpeg version test failed: {test_result.stderr}")
                            downloader_logger.warning(f"System FFmpeg version test failed: {test_result.stderr}")
                    except Exception as test_error:
                        logger.warning(f"Error testing system FFmpeg: {test_error}")
                        downloader_logger.warning(f"Error testing system FFmpeg: {test_error}")
                else:
                    logger.warning(f"Failed to install FFmpeg via apt-get: {install_result.stderr}")
                    downloader_logger.warning(f"Failed to install FFmpeg via apt-get: {install_result.stderr}")
            else:
                logger.warning(f"Failed to update package list: {update_result.stderr}")
                downloader_logger.warning(f"Failed to update package list: {update_result.stderr}")

        except Exception as install_error:
            logger.warning(f"Could not install FFmpeg via package manager: {install_error}")
            downloader_logger.warning(f"Could not install FFmpeg via package manager: {install_error}")

        return None

    async def diagnose_ffmpeg_issue(self) -> Dict[str, str]:
        """Diagnose FFmpeg issues and provide recommendations"""
        diagnosis = {
            'status': 'unknown',
            'issue': '',
            'recommendation': '',
            'details': []
        }

        try:
            # Check if FFmpeg path is set
            if not self.ffmpeg_path:
                diagnosis['status'] = 'not_found'
                diagnosis['issue'] = 'FFmpeg not found or configured'
                diagnosis['recommendation'] = 'Install FFmpeg or check installation'
                return diagnosis

            # Determine FFmpeg executable path
            if self.ffmpeg_path == "system":
                ffmpeg_exe = "ffmpeg"
            else:
                system = platform.system().lower()
                if system == "windows":
                    ffmpeg_exe = str(Path(self.ffmpeg_path) / "ffmpeg.exe")
                else:
                    ffmpeg_exe = str(Path(self.ffmpeg_path) / "ffmpeg")

            # Test basic FFmpeg functionality
            try:
                result = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: sp.run([ffmpeg_exe, "-version"], capture_output=True, text=True, timeout=10)
                    ),
                    timeout=15
                )

                if result.returncode != 0:
                    diagnosis['status'] = 'version_failed'
                    diagnosis['issue'] = f'FFmpeg version check failed (exit code {result.returncode})'
                    diagnosis['details'].append(f'stderr: {result.stderr}')
                    diagnosis['recommendation'] = 'FFmpeg binary may be corrupted or incompatible'
                    return diagnosis

                diagnosis['details'].append(f'Version check passed: {result.stdout.split()[2] if len(result.stdout.split()) > 2 else "unknown"}')

            except Exception as version_error:
                diagnosis['status'] = 'version_error'
                diagnosis['issue'] = f'FFmpeg version check error: {version_error}'
                diagnosis['recommendation'] = 'FFmpeg binary may not exist or be executable'
                return diagnosis

            # Test conversion capability (this is where exit code -11 typically occurs)
            try:
                test_result = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: sp.run([
                            ffmpeg_exe, "-f", "lavfi", "-i", "testsrc=duration=1:size=320x240:rate=1",
                            "-f", "null", "-"
                        ], capture_output=True, text=True, timeout=15)
                    ),
                    timeout=20
                )

                if test_result.returncode == -11:
                    diagnosis['status'] = 'segfault'
                    diagnosis['issue'] = 'FFmpeg crashes with segmentation fault (exit code -11)'
                    diagnosis['details'].append('This typically indicates binary incompatibility or missing dependencies')
                    diagnosis['recommendation'] = 'Try reinstalling FFmpeg or use system package manager'
                    return diagnosis
                elif test_result.returncode != 0:
                    diagnosis['status'] = 'conversion_failed'
                    diagnosis['issue'] = f'FFmpeg conversion test failed (exit code {test_result.returncode})'
                    diagnosis['details'].append(f'stderr: {test_result.stderr}')
                    diagnosis['recommendation'] = 'FFmpeg may have missing codecs or dependencies'
                    return diagnosis

                diagnosis['details'].append('Conversion test passed')

            except Exception as conv_error:
                diagnosis['status'] = 'conversion_error'
                diagnosis['issue'] = f'FFmpeg conversion test error: {conv_error}'
                diagnosis['recommendation'] = 'FFmpeg may be unstable or have missing dependencies'
                return diagnosis

            # If we get here, FFmpeg seems to be working
            diagnosis['status'] = 'working'
            diagnosis['issue'] = 'No issues detected'
            diagnosis['recommendation'] = 'FFmpeg appears to be working correctly'

        except Exception as e:
            diagnosis['status'] = 'diagnosis_error'
            diagnosis['issue'] = f'Error during diagnosis: {e}'
            diagnosis['recommendation'] = 'Unable to diagnose FFmpeg issues'

        return diagnosis

    async def test_spotdl_installation(self) -> Dict[str, str]:
        """Test if spotdl is installed and working"""
        test_result = {
            'status': 'unknown',
            'version': '',
            'error': '',
            'help_output': ''
        }

        try:
            # Test spotdl version
            result = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self._run_spotdl_command(["--version"], timeout=10)
                ),
                timeout=15
            )

            if result.returncode == 0:
                test_result['status'] = 'working'
                test_result['version'] = result.stdout.strip()
                logger.info(f"spotdl is working: {test_result['version']}")

                # Also test help to see available commands
                try:
                    help_result = self._run_spotdl_command(["--help"], timeout=5)
                    if help_result.returncode == 0:
                        test_result['help_output'] = help_result.stdout
                        logger.info("spotdl help command successful")
                except Exception as help_error:
                    logger.warning(f"Could not get spotdl help: {help_error}")

            else:
                test_result['status'] = 'error'
                test_result['error'] = result.stderr or result.stdout
                logger.error(f"spotdl version check failed: {test_result['error']}")

                # If spotdl is not found, try to install it
                if "no module named spotdl" in test_result['error'].lower():
                    logger.warning("spotdl not found - attempting installation during startup...")
                    try:
                        import subprocess
                        install_result = subprocess.run([
                            "python3", "-m", "pip", "install", "spotdl>=4.2.0", "--no-cache-dir"
                        ], capture_output=True, text=True, timeout=180)

                        if install_result.returncode == 0:
                            logger.info("Successfully installed spotdl during startup")
                            # Test again after installation
                            retry_result = self._run_spotdl_command(["--version"], timeout=10)
                            if retry_result.returncode == 0:
                                test_result['status'] = 'working'
                                test_result['version'] = retry_result.stdout.strip()
                                test_result['error'] = ''
                                logger.info(f"spotdl working after installation: {test_result['version']}")
                            else:
                                logger.error(f"spotdl still not working after installation: {retry_result.stderr}")
                        else:
                            logger.error(f"Failed to install spotdl during startup: {install_result.stderr}")
                    except Exception as install_error:
                        logger.error(f"spotdl installation error during startup: {install_error}")

        except Exception as e:
            test_result['status'] = 'not_found'
            test_result['error'] = str(e)
            logger.error(f"spotdl not found or not working: {e}")

        return test_result

    def detect_platform(self, url: str) -> str:
        """Detect the platform from URL"""
        url_lower = url.lower()
        
        if any(domain in url_lower for domain in ['youtube.com', 'youtu.be', 'music.youtube.com']):
            return 'YouTube'
        elif 'spotify.com' in url_lower:
            return 'Spotify'
        elif 'soundcloud.com' in url_lower:
            return 'SoundCloud'
        else:
            return 'Unknown'
    
    def is_supported_url(self, url: str) -> bool:
        """Check if URL is supported"""
        supported_domains = [
            'youtube.com', 'youtu.be', 'music.youtube.com',
            'spotify.com', 'soundcloud.com'
        ]
        url_lower = url.lower()
        return any(domain in url_lower for domain in supported_domains)

    def _validate_and_clean_url(self, url: str) -> Optional[str]:
        """Validate and clean URL to prevent corruption issues"""
        try:
            if not url or not isinstance(url, str):
                logger.error(f"Invalid URL type or empty: {type(url)} - {url}")
                return None

            # Strip whitespace and common issues
            url = url.strip()

            # Check minimum length and specific corruption patterns
            if len(url) < 10:
                logger.error(f"URL too short, likely corrupted: {url}")
                return None

            # Check for specific corruption patterns we've seen
            if url in ['y', 'youtube', 'youtu', 'http', 'https']:
                logger.error(f"URL appears to be corrupted fragment: {url}")
                return None

            # Validate URL format
            import urllib.parse as urlparse
            try:
                parsed = urlparse.urlparse(url)
                if not parsed.scheme or not parsed.netloc:
                    logger.error(f"Invalid URL format: {url}")
                    return None
            except Exception as e:
                logger.error(f"URL parsing failed: {url} - {e}")
                return None

            # Check for YouTube URL patterns
            if self.detect_platform(url) == 'YouTube':
                # Validate YouTube URL patterns
                youtube_patterns = [
                    r'youtube\.com/watch\?v=[\w-]+',
                    r'youtu\.be/[\w-]+',
                    r'youtube\.com/playlist\?list=[\w-]+',
                    r'music\.youtube\.com'
                ]

                import re
                if not any(re.search(pattern, url, re.IGNORECASE) for pattern in youtube_patterns):
                    logger.error(f"Invalid YouTube URL pattern: {url}")
                    return None

            logger.debug(f"URL validation passed: {url}")
            return url

        except Exception as e:
            logger.error(f"URL validation error: {e}")
            return None
    
    async def extract_info(self, url: str) -> Optional[Dict]:
        """Extract basic info from URL"""
        if not yt_dlp:
            raise Exception("yt-dlp not installed")

        # Validate URL first
        url = self._validate_and_clean_url(url)
        if not url:
            logger.error("Invalid URL provided to extract_info")
            return None

        platform = self.detect_platform(url)
        
        try:
            if platform == 'Spotify':
                return await self.extract_spotify_info(url)
            else:
                # Use yt-dlp for other platforms with anti-blocking measures
                user_agents = [
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                ]

                ydl_opts = {
                    'quiet': True,
                    'no_warnings': True,
                    'extract_flat': False,
                    'user_agent': random.choice(user_agents),
                    'extractor_args': {
                        'youtube': {
                            'player_client': ['android', 'web'],
                        }
                    },
                }
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: ydl.extract_info(url, download=False)
                    )
                    
                    return {
                        'title': info.get('title', 'Unknown'),
                        'artist': info.get('uploader', 'Unknown'),
                        'duration': info.get('duration', 0),
                        'platform': platform
                    }
        except Exception as e:
            logger.error(f"Error extracting info: {e}")
            return None
    
    async def extract_spotify_info(self, url: str) -> Optional[Dict]:
        """Extract Spotify track info using simplified approach (same as working audio_downloader_bot.py)"""
        try:
            # Extract track ID from URL
            track_id_match = re.search(r'track/([a-zA-Z0-9]+)', url)
            if not track_id_match:
                logger.warning(f"Could not extract track ID from Spotify URL: {url}")
                return None

            track_id = track_id_match.group(1)
            logger.info(f"Extracted Spotify track ID: {track_id}")

            # For now, return basic info that will allow the search to proceed
            # The working version also uses this approach as a fallback
            return {
                'title': 'Spotify Track',
                'artist': 'Unknown Artist',
                'duration': 0,
                'platform': 'Spotify'
            }

        except Exception as e:
            logger.error(f"Error extracting Spotify info: {e}")
            return None

    async def download_audio(self, url: str, quality: str = "medium", chat_id: str = None, download_playlist: bool = False) -> Optional[Tuple[Path, Dict]]:
        """Download audio from URL, passing chat_id for checkpoint/resume."""
        # Validate URL first
        original_url = url
        url = self._validate_and_clean_url(url)
        if not url:
            logger.error(f"Invalid URL provided to download_audio: {original_url}")
            downloader_logger.error(f"URL validation failed in download_audio: {original_url}")
            return None

        platform = self.detect_platform(url)
        if platform == 'Spotify':
            return await self.download_spotify_audio(url, quality, chat_id=chat_id)
        else:
            return await self.download_youtube_audio(url, quality, chat_id=chat_id, download_playlist=download_playlist)
    
    def get_user_friendly_error_message(self, error_str: str) -> str:
        """Convert technical errors to user-friendly messages"""
        error_lower = error_str.lower()

        # Check for DNS/URL resolution issues first (including the specific 'y' corruption)
        if "failed to resolve" in error_lower or "name or service not known" in error_lower:
            if "'y'" in error_lower or "resolve 'y'" in error_lower:
                return (
                    "🔧 **URL Corruption Detected**\n\n"
                    "The URL appears to have been corrupted during processing.\n\n"
                    "**This is a known issue that can occur when:**\n"
                    "• The URL gets truncated during transmission\n"
                    "• There's a parsing error in the bot\n"
                    "• Memory issues on the server\n\n"
                    "**Please try again:**\n"
                    "1. Send /download command again\n"
                    "2. Copy and paste the complete URL\n"
                    "3. Make sure the URL starts with https://\n"
                    "4. If it keeps failing, try a different video\n\n"
                    "*Note: This is a technical issue with URL handling, not YouTube blocking.*"
                )
            else:
                return (
                    "🌐 **Network/URL Error**\n\n"
                    "There was a problem resolving the URL or connecting to the service.\n\n"
                    "**Possible causes:**\n"
                    "• Network connectivity issues\n"
                    "• Corrupted or invalid URL\n"
                    "• DNS resolution problems\n"
                    "• Temporary server issues\n\n"
                    "**What you can do:**\n"
                    "• Check your internet connection\n"
                    "• Verify the URL is correct and complete\n"
                    "• Try again in a few minutes\n"
                    "• Try a different video/URL\n\n"
                    "*Note: This appears to be a network or URL formatting issue.*"
                )

        # Check for YouTube bot detection specifically
        elif "sign in to confirm you're not a bot" in error_lower or ("cookies" in error_lower and "authentication" in error_lower):
            cookie_status = "✅ Enabled" if hasattr(self, 'cookie_file') and self.cookie_file else "❌ Not available"

            if hasattr(self, 'is_streamlit_cloud') and self.is_streamlit_cloud:
                return (
                    "🤖 **YouTube Access Temporarily Blocked**\n\n"
                    "YouTube has implemented stronger anti-bot measures that are currently blocking downloads.\n\n"
                    f"**Cookie Authentication:** {cookie_status}\n"
                    "**Environment:** Cloud-hosted (enhanced bypass strategies active)\n\n"
                    "**Immediate Solutions:**\n"
                    "• Wait 15-30 minutes and try again\n"
                    "• Try a different video/song\n"
                    "• Use shorter videos (under 5 minutes work better)\n"
                    "• Try during off-peak hours (early morning/late night)\n\n"
                    "**Alternative Options:**\n"
                    "• Use direct YouTube links instead of Spotify links\n"
                    "• Try music from other platforms\n"
                    "• Contact admin if issue persists for multiple hours\n\n"
                    "**Technical Note:** This is a temporary YouTube restriction, not a bot malfunction.\n\n"
                    "• Upload a youtube_cookies.txt file to the app\n"
                    "• The bot automatically tries mobile client strategies\n\n"
                    "*Note: Running on Streamlit Cloud with enhanced anti-detection optimized for cloud environments.*"
                )
            else:
                return (
                    "🤖 **YouTube Bot Detection**\n\n"
                    "YouTube has detected automated access and is blocking downloads.\n\n"
                    f"**Cookie Authentication:** {cookie_status}\n\n"
                    "**What you can do:**\n"
                    "• Wait 10-15 minutes and try again\n"
                    "• Try a different video\n"
                    "• The bot automatically tries multiple bypass strategies\n"
                    "• Issue typically resolves within an hour\n\n"
                    "**For better reliability:**\n"
                    "• Use Brave browser and visit YouTube first\n"
                    "• The bot can extract cookies automatically\n\n"
                    "*Note: This is due to YouTube's anti-bot measures. The bot uses advanced bypass techniques including browser cookies when available.*"
                )
        elif "403" in error_str or "forbidden" in error_lower:
            return (
                "🚫 **YouTube Access Blocked**\n\n"
                "YouTube has temporarily blocked our download requests. This happens when:\n"
                "• Too many downloads in a short time\n"
                "• YouTube's anti-bot measures are active\n"
                "• Regional restrictions apply\n\n"
                "**Solutions:**\n"
                "• Wait 10-15 minutes and try again\n"
                "• Try a different video\n"
                "• Contact admin if the issue persists"
            )
        elif "private" in error_lower or "unavailable" in error_lower:
            return (
                "🔒 **Video Not Available**\n\n"
                "This video cannot be downloaded because:\n"
                "• Video is private or unlisted\n"
                "• Video has been removed\n"
                "• Geographic restrictions\n\n"
                "Please try a different video."
            )
        elif "age" in error_lower and "restricted" in error_lower:
            return (
                "🔞 **Age-Restricted Content**\n\n"
                "This video is age-restricted and cannot be downloaded.\n"
                "Please try a different video."
            )
        elif "copyright" in error_lower or "blocked" in error_lower:
            return (
                "⚖️ **Copyright Protected**\n\n"
                "This video is protected by copyright and cannot be downloaded.\n"
                "Please try a different video."
            )
        elif "timeout" in error_lower:
            return (
                "⏱️ **Download Timeout**\n\n"
                "The download took too long and timed out.\n"
                "This might be due to:\n"
                "• Slow internet connection\n"
                "• Large file size\n"
                "• Server issues\n\n"
                "Please try again or choose a shorter video."
            )
        else:
            return (
                "❌ **Download Failed**\n\n"
                "An unexpected error occurred during download.\n"
                "This might be temporary. Please:\n"
                "• Try again in a few minutes\n"
                "• Try a different video\n"
                "• Contact admin if the problem persists"
            )

    async def download_youtube_audio(self, url: str, quality: str, chat_id: str = None, download_playlist: bool = False) -> Optional[Tuple[Path, Dict]]:
        """Download audio from YouTube using yt-dlp, with checkpoint/resume support."""
        # Overall function timeout to prevent hanging
        # Increased timeout for cloud environment due to slower network
        overall_timeout = 600 if self.is_streamlit_cloud else 300  # 10 minutes cloud, 5 minutes local
        logger.info(f"Starting YouTube download with overall timeout of {overall_timeout}s")

        try:
            return await asyncio.wait_for(
                self._download_youtube_audio_internal(url, quality, chat_id, download_playlist),
                timeout=overall_timeout
            )
        except asyncio.TimeoutError:
            logger.error(f"YouTube download timed out after {overall_timeout}s")
            raise Exception(f"🕐 Download timed out after {overall_timeout//60} minutes. Try a shorter video or try again later.")

    async def _download_youtube_audio_internal(self, url: str, quality: str, chat_id: str = None, download_playlist: bool = False) -> Optional[Tuple[Path, Dict]]:
        """Internal YouTube download function with timeout protection."""
        import hashlib
        import json
        from datetime import datetime, timedelta

        # Validate and clean URL first
        url = self._validate_and_clean_url(url)
        if not url:
            logger.error("Invalid or corrupted URL provided")
            downloader_logger.error("URL validation failed - URL is invalid or corrupted")
            return None

        logger.info(f"Starting YouTube download for URL: {url}")
        downloader_logger.info(f"YouTube download initiated: {url}")

        def get_track_id(url):
            return hashlib.md5(url.encode()).hexdigest()[:12]

        def get_temp_paths(chat_id, track_id):
            base = Path(self.temp_dir)
            audio = base / f"{chat_id}_{track_id}.mp3"
            meta = base / f"{chat_id}_{track_id}.json"
            return audio, meta

        def cleanup_old_temp_files():
            now = datetime.now()
            for f in Path(self.temp_dir).glob("*"):
                if f.is_file() and f.suffix in {'.mp3', '.json'}:
                    mtime = datetime.fromtimestamp(f.stat().st_mtime)
                    if now - mtime > timedelta(hours=24):
                        try:
                            f.unlink()
                        except Exception as e:
                            logger.warning(f"Failed to delete old temp file {f}: {e}")

        # Clean up old temp files
        cleanup_old_temp_files()

        track_id = get_track_id(url)
        if not chat_id:
            chat_id = 'default'
        audio_path, meta_path = get_temp_paths(chat_id, track_id)

        # Check for existing audio and metadata
        if audio_path.exists() and meta_path.exists():
            try:
                with open(meta_path, 'r', encoding='utf-8') as f:
                    info = json.load(f)
                logger.info(f"Resuming: found audio and metadata for {audio_path}")
                # Try to embed metadata if not already present
                try:
                    from mutagen.id3 import ID3, TIT2, TPE1, TALB, APIC, error
                    from mutagen.mp3 import MP3
                    import requests
                    audio = MP3(audio_path, ID3=ID3)
                    try:
                        audio.add_tags()
                    except error:
                        pass
                    tags = audio.tags
                    tags.delall('TIT2')
                    tags.add(TIT2(encoding=3, text=info.get('title', 'Unknown')))
                    tags.delall('TPE1')
                    tags.add(TPE1(encoding=3, text=info.get('uploader', 'Unknown')))
                    tags.delall('TALB')
                    tags.add(TALB(encoding=3, text=info.get('album', 'YouTube')))
                    thumbnail_url = info.get('thumbnail')
                    if thumbnail_url:
                        try:
                            response = requests.get(thumbnail_url)
                            if response.status_code == 200:
                                tags.delall('APIC')
                                tags.add(
                                    APIC(
                                        encoding=3,
                                        mime='image/jpeg',
                                        type=3,
                                        desc='Cover',
                                        data=response.content
                                    )
                                )
                                logger.info(f"Embedded cover art from {thumbnail_url}")
                        except Exception as thumb_e:
                            logger.warning(f"Exception downloading or embedding thumbnail: {thumb_e}")
                    audio.save()
                    logger.info(f"Metadata and cover art embedded for {audio_path}")
                except Exception as meta_e:
                    logger.warning(f"Failed to robustly embed metadata or cover art: {meta_e}")
                file_info = {
                    'title': info.get('title', 'Unknown'),
                    'artist': info.get('uploader', 'Unknown'),
                    'duration': info.get('duration', 0),
                    'size_mb': audio_path.stat().st_size / (1024 * 1024),
                    'platform': 'YouTube',
                    'filename': str(audio_path.name)
                }
                # Delete temp files after successful resume
                try:
                    audio_path.unlink()
                    meta_path.unlink()
                except Exception as cleanup_e:
                    logger.warning(f"Failed to delete temp files after resume: {cleanup_e}")
                return audio_path, file_info
            except Exception as e:
                logger.warning(f"Failed to resume from temp files: {e}")
                # If resume fails, fall through to fresh download

        # Clean URL if single video requested (remove playlist parameters)
        if not download_playlist:
            # Remove playlist parameters from URL to force single video download
            import urllib.parse as urlparse
            parsed_url = urlparse.urlparse(url)
            query_params = urlparse.parse_qs(parsed_url.query)

            # Remove playlist-related parameters
            playlist_params = ['list', 'index', 'start_radio', 'playlist']
            for param in playlist_params:
                query_params.pop(param, None)

            # Reconstruct URL without playlist parameters
            new_query = urlparse.urlencode(query_params, doseq=True)
            cleaned_url = urlparse.urlunparse((
                parsed_url.scheme,
                parsed_url.netloc,
                parsed_url.path,
                parsed_url.params,
                new_query,
                parsed_url.fragment
            ))

            if cleaned_url != url:
                logger.info(f"Cleaned URL for single video: {url} -> {cleaned_url}")
                downloader_logger.info(f"URL cleaned to remove playlist parameters: {cleaned_url}")
                url = cleaned_url

        # Otherwise, proceed with fresh download
        try:
            # Quality mapping
            quality_map = {
                "high": "320",
                "medium": "192", 
                "low": "128"
            }
            
            bitrate = quality_map.get(quality, "192")
            
            # Generate unique filename
            temp_filename = f"audio_youtube_{int(time.time())}"
            temp_filepath = self.temp_dir / temp_filename
            
            # Enhanced anti-blocking user agents optimized for cloud environments
            if self.is_streamlit_cloud:
                # Streamlit Cloud: Use server-friendly user agents
                user_agents = [
                    # Linux server variants (common on cloud platforms)
                    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                    'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:122.0) Gecko/20100101 Firefox/122.0',
                    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Brave/121.0.0.0',
                    # Mobile variants (often less restricted)
                    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1',
                    'Mozilla/5.0 (Android 13; Mobile; rv:122.0) Gecko/122.0 Firefox/122.0',
                    'Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Mobile Safari/537.36',
                ]
            else:
                # Local environment: Full range including Brave browser
                user_agents = [
                    # Brave Browser (privacy-focused, less tracked)
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Brave/121.0.0.0',
                    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Brave/121.0.0.0',
                    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Brave/121.0.0.0',
                    # Standard browsers as fallback
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0',
                    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:122.0) Gecko/20100101 Firefox/122.0',
                    # Mobile variants
                    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1',
                    'Mozilla/5.0 (iPad; CPU OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1'
                ]

            referers = ['https://www.youtube.com/', 'https://www.google.com/', 'https://music.youtube.com/', 'https://m.youtube.com/']

            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': str(temp_filepath) + '.%(ext)s',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': bitrate,
                }],
                'quiet': True,
                'no_warnings': True,
                'noplaylist': not download_playlist,
                'extract_flat': False,
                'ignoreerrors': False,

                # Enhanced anti-blocking measures
                'user_agent': random.choice(user_agents),
                'referer': random.choice(referers),
                'sleep_interval': random.uniform(3, 6),
                'max_sleep_interval': random.uniform(15, 25),
                'extractor_retries': 8,
                'fragment_retries': 8,
                'socket_timeout': 120,

                # Advanced YouTube-specific options to bypass bot detection
                'extractor_args': {
                    'youtube': {
                        'player_client': ['android_creator', 'android_music', 'android', 'ios_music', 'ios'],
                        'player_skip': ['configs', 'webpage'],
                        'skip': ['dash', 'hls'] if self.is_streamlit_cloud else [],
                        'innertube_host': 'youtubei.googleapis.com',
                        'innertube_key': None,  # Let yt-dlp auto-detect
                        'include_live_dash': False,
                        'include_hls': False,
                    }
                },

                # Network and DNS configuration for Streamlit Cloud
                'socket_timeout': 120,
                'retries': 10,
                'fragment_retries': 10,
                'skip_unavailable_fragments': True,
                'keep_fragments': False,

                # Force IPv4 to avoid DNS issues
                'force_ipv4': True,

                # Enhanced DNS and network configuration
                'source_address': '0.0.0.0',  # Bind to all interfaces
                'force_json': False,
                'geo_bypass': True,
                'geo_bypass_country': 'US',

                # Optimized timeouts for cloud environment
                'socket_timeout': 120 if self.is_streamlit_cloud else 60,
                'read_timeout': 180 if self.is_streamlit_cloud else 120,
                'http_headers': {
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-us,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate',
                    'DNT': '1',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                },

                # Additional network robustness
                'http_chunk_size': 10485760,  # 10MB chunks
                'prefer_insecure': False,
                'no_check_certificate': False,

                # Enhanced retry logic
                'retry_sleep_functions': {
                    'http': lambda n: min(4 ** n, 100),
                    'fragment': lambda n: min(4 ** n, 100),
                    'extractor': lambda n: min(4 ** n, 100),
                },

                # Additional headers to mimic real browser behavior
                'http_headers': {
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'DNT': '1',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                    'Sec-Fetch-Dest': 'document',
                    'Sec-Fetch-Mode': 'navigate',
                    'Sec-Fetch-Site': 'none',
                    'Sec-Fetch-User': '?1',
                },
            }

            # Add cookie support if available (most effective anti-bot measure)
            if self.cookie_file:
                ydl_opts['cookiefile'] = self.cookie_file
                logger.info(f"Using cookie file for authentication: {self.cookie_file}")
                downloader_logger.info(f"Cookie authentication enabled: {self.cookie_file}")
            elif not self.is_streamlit_cloud:
                # Only try browser cookie extraction on local environments
                try:
                    # Prefer Brave browser cookies (less tracked)
                    ydl_opts['cookies_from_browser'] = ('brave', None, None, None)
                    logger.info("Attempting to use Brave browser cookies")
                    downloader_logger.info("Using Brave browser cookie extraction")
                except Exception:
                    try:
                        # Fallback to Chrome
                        ydl_opts['cookies_from_browser'] = ('chrome', None, None, None)
                        logger.info("Attempting to use Chrome browser cookies")
                        downloader_logger.info("Using Chrome browser cookie extraction")
                    except Exception:
                        logger.info("No browser cookies available - using enhanced headers only")
                        downloader_logger.info("Cookie extraction failed - using cookieless mode")
            else:
                # Streamlit Cloud: Use cloud-optimized settings without browser cookies
                logger.info("Streamlit Cloud: Using cloud-optimized anti-detection without browser cookies")
                downloader_logger.info("Streamlit Cloud mode: Enhanced headers and user agents only")

                # Additional cloud-specific optimizations for better timeout handling
                ydl_opts.update({
                    'concurrent_fragment_downloads': 1,  # Single thread for stability
                    'fragment_retries': 1,  # Minimal retries to avoid hanging
                    'file_access_retries': 1,
                    'extractor_retries': 1,  # Single extractor retry
                    'http_chunk_size': 1024 * 1024,  # 1MB chunks for better progress tracking
                    'sleep_interval': 1,  # Short delays to avoid timeouts
                    'max_sleep_interval': 3,
                })

            # Add FFmpeg location if found (using same logic as audio_downloader_bot.py)
            if self.ffmpeg_path == "system":
                # System FFmpeg is available, yt-dlp will find it automatically
                logger.info("Using system FFmpeg for yt-dlp")
            elif self.ffmpeg_path:
                # Local FFmpeg directory
                ydl_opts['ffmpeg_location'] = self.ffmpeg_path
                logger.info(f"Using local FFmpeg for yt-dlp: {self.ffmpeg_path}")
            else:
                # If no FFmpeg available, try to download audio-only formats that don't need conversion
                logger.warning("No FFmpeg available, trying audio-only formats")
                ydl_opts['format'] = 'bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio'
                # Remove post-processors that require FFmpeg
                ydl_opts['postprocessors'] = []
                # Ensure noplaylist is still set
                ydl_opts['noplaylist'] = not download_playlist
            
            # Download with retry mechanism and exponential backoff
            max_retries = 3
            info = None

            for attempt in range(max_retries):
                try:
                    # Add random delay before each attempt to avoid rate limiting
                    if attempt > 0:
                        delay = (2 ** attempt) + random.uniform(0, 2)
                        logger.info(f"Retry attempt {attempt + 1}/{max_retries} after {delay:.1f}s delay")
                        await asyncio.sleep(delay)

                        # Rotate user agent and referer for retry attempts
                        ydl_opts['user_agent'] = random.choice(user_agents)
                        ydl_opts['referer'] = random.choice(referers)

                    # Debug: Log the exact URL being passed to yt-dlp
                    logger.info(f"Passing URL to yt-dlp: '{url}' (length: {len(url)})")
                    downloader_logger.info(f"yt-dlp download attempt {attempt + 1}: URL='{url}', length={len(url)}")

                    # Adjust timeout based on environment and attempt
                    if self.is_streamlit_cloud:
                        # Streamlit Cloud needs longer timeouts due to slower network
                        download_timeout = 180 + (attempt * 60)  # 3, 4, 5 minutes per attempt
                    else:
                        download_timeout = 120  # 2 minutes for local

                    logger.info(f"Starting yt-dlp download attempt {attempt + 1} with {download_timeout}s timeout...")

                    # Create a progress task that logs every 30 seconds
                    async def progress_logger():
                        for i in range(download_timeout // 30):
                            await asyncio.sleep(30)
                            logger.info(f"Download still in progress... ({(i+1)*30}s elapsed)")

                    progress_task = asyncio.create_task(progress_logger())

                    try:
                        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                            info = await asyncio.wait_for(
                                asyncio.get_event_loop().run_in_executor(
                                    None, lambda: ydl.extract_info(url, download=True)
                                ),
                                timeout=download_timeout
                            )
                        logger.info("yt-dlp download completed successfully")
                    finally:
                        progress_task.cancel()  # Stop the progress logger
                    break  # Success, exit retry loop

                except Exception as e:
                    logger.error(f"Download attempt {attempt + 1} failed: {e}")
                    logger.error(f"Error type: {type(e).__name__}")
                    logger.error(f"Full error details: {repr(e)}")
                    downloader_logger.error(f"Download attempt {attempt + 1} failed: {e}")
                    downloader_logger.error(f"Error type: {type(e).__name__}")
                    downloader_logger.error(f"Full error details: {repr(e)}")

                    # Log specific error patterns for debugging
                    error_str = str(e).lower()
                    if "403" in error_str or "forbidden" in error_str:
                        logger.error("HTTP 403 Forbidden error detected - YouTube blocking access")
                    elif "429" in error_str or "too many requests" in error_str:
                        logger.error("Rate limiting error detected - too many requests")
                    elif "sign in" in error_str or "bot" in error_str:
                        logger.error("Bot detection error detected - YouTube detected automation")
                    elif "timeout" in error_str:
                        logger.error("Timeout error detected - request took too long")
                    elif "connection" in error_str:
                        logger.error("Connection error detected - network issue")
                    elif "unavailable" in error_str:
                        logger.error("Video unavailable error detected")
                    elif "private" in error_str or "deleted" in error_str:
                        logger.error("Video access error detected - private or deleted")

                    if attempt == max_retries - 1:
                        raise  # Re-raise on final attempt

                    # Check for DNS resolution issues and try different approach
                    if "Failed to resolve 'y'" in str(e) or "Name or service not known" in str(e):
                        logger.info("DNS resolution issue detected, trying alternative configuration")
                        # Use more basic configuration for next attempt
                        ydl_opts['force_ipv4'] = True
                        ydl_opts['socket_timeout'] = 60
                        ydl_opts['extractor_args'] = {
                            'youtube': {
                                'player_client': ['android'],  # Use only Android client
                            }
                        }
                        # Remove complex headers that might cause issues
                        ydl_opts['http_headers'] = {
                            'User-Agent': random.choice(user_agents),
                            'Accept': '*/*',
                        }
                    # Check if it's a 403 error and adjust strategy
                    elif "403" in str(e) or "Forbidden" in str(e):
                        logger.info("403 error detected, adjusting strategy for next attempt")
                        # Use more conservative settings for next attempt
                        ydl_opts['sleep_interval'] = random.uniform(5, 8)
                        ydl_opts['max_sleep_interval'] = random.uniform(15, 20)

            if info is None:
                logger.error("All download attempts failed - no video info extracted")
                downloader_logger.error("All download attempts failed - no video info extracted")
                raise Exception("All download attempts failed - unable to extract video information")
            
            # Find downloaded file
            downloaded_files = list(self.temp_dir.glob(f"{temp_filename}.*"))
            if not downloaded_files:
                raise FileNotFoundError("Download failed - no file found")
            
            downloaded_file = downloaded_files[0]
            file_info = {
                'title': info.get('title', 'Unknown'),
                'artist': info.get('uploader', 'Unknown'),
                'duration': info.get('duration', 0),
                'size_mb': downloaded_file.stat().st_size / (1024 * 1024),
                'platform': 'YouTube'
            }

            # --- Rename file to '<title> - <artist>.mp3' ---
            try:
                import re
                def sanitize(s):
                    return re.sub(r'[\\/:*?\"<>|]', '', s)
                title = sanitize(info.get('title', 'Unknown'))
                artist = sanitize(info.get('uploader', 'Unknown'))
                new_filename = f"{title} - {artist}.mp3"
                new_filepath = downloaded_file.parent / new_filename
                downloaded_file.rename(new_filepath)
                logger.info(f"Renamed file to: {new_filename}")
                downloaded_file = new_filepath
            except Exception as rename_e:
                logger.warning(f"Failed to rename file: {rename_e}")
            # --- End renaming ---

            # --- Robustly embed metadata and cover art using mutagen.id3 ---
            try:
                from mutagen.id3 import ID3, TIT2, TPE1, TALB, APIC, error
                from mutagen.mp3 import MP3
                import requests

                audio = MP3(downloaded_file, ID3=ID3)
                # Add ID3 tag if it doesn't exist
                try:
                    audio.add_tags()
                except error:
                    pass
                tags = audio.tags
                tags.delall('TIT2')
                tags.add(TIT2(encoding=3, text=info.get('title', 'Unknown')))
                tags.delall('TPE1')
                tags.add(TPE1(encoding=3, text=info.get('uploader', 'Unknown')))
                tags.delall('TALB')
                tags.add(TALB(encoding=3, text=info.get('album', 'YouTube')))

                # Download and embed cover art (YouTube thumbnail)
                thumbnail_url = info.get('thumbnail')
                if thumbnail_url:
                    try:
                        response = requests.get(thumbnail_url)
                        if response.status_code == 200:
                            tags.delall('APIC')
                            tags.add(
                                APIC(
                                    encoding=3,  # 3 is for utf-8
                                    mime='image/jpeg',
                                    type=3,  # Cover (front)
                                    desc='Cover',
                                    data=response.content
                                )
                            )
                            logger.info(f"Embedded cover art from {thumbnail_url}")
                        else:
                            logger.warning(f"Failed to download thumbnail: {thumbnail_url} (status {response.status_code})")
                    except Exception as thumb_e:
                        logger.warning(f"Exception downloading or embedding thumbnail: {thumb_e}")
                else:
                    logger.warning("No thumbnail URL found in YouTube info for cover art.")
                audio.save()
                logger.info(f"Metadata and cover art embedded for {downloaded_file}")
            except Exception as meta_e:
                logger.warning(f"Failed to robustly embed metadata or cover art: {meta_e}")
            # --- End robust metadata embedding ---

            # Save metadata
            with open(meta_path, 'w', encoding='utf-8') as f:
                json.dump(info, f)

            file_info = {
                'title': info.get('title', 'Unknown'),
                'artist': info.get('uploader', 'Unknown'),
                'duration': info.get('duration', 0),
                'size_mb': downloaded_file.stat().st_size / (1024 * 1024),
                'platform': 'YouTube',
                'filename': str(downloaded_file.name)
            }

            return downloaded_file, file_info
            
        except Exception as e:
            logger.error(f"YouTube download failed: {e}")

            # Special handling for DNS resolution issues (Failed to resolve 'y')
            if "Failed to resolve 'y'" in str(e) or "Name or service not known" in str(e):
                logger.warning("DNS resolution issue detected - trying comprehensive URL and DNS workarounds")

                # Quick network connectivity test and DNS resolution test
                try:
                    import socket
                    socket.setdefaulttimeout(10)
                    socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(('8.8.8.8', 53))
                    logger.info("Basic internet connectivity confirmed")

                    # Test DNS resolution for YouTube
                    try:
                        youtube_ip = socket.gethostbyname('www.youtube.com')
                        logger.info(f"YouTube DNS resolution successful: {youtube_ip}")
                    except Exception as dns_e:
                        logger.error(f"YouTube DNS resolution failed: {dns_e}")
                        # Try direct IP connection as workaround
                        try:
                            # Try connecting to YouTube's known IP addresses
                            youtube_ips = ['142.250.191.78', '172.217.14.206', '216.58.194.174']  # Common YouTube IPs
                            for ip in youtube_ips:
                                try:
                                    socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((ip, 443))
                                    logger.info(f"Direct YouTube IP connection successful: {ip}")
                                    break
                                except:
                                    continue
                        except Exception as ip_e:
                            logger.error(f"Direct IP connection also failed: {ip_e}")

                except Exception as net_e:
                    logger.error(f"Network connectivity issue detected: {net_e}")
                    # Still try the workarounds even if network test fails
                try:
                    # Try multiple URL transformations and DNS fixes
                    transformed_urls = []

                    # Transform youtu.be URLs to full youtube.com format
                    if 'youtu.be/' in url:
                        video_id = url.split('youtu.be/')[-1].split('?')[0].split('&')[0]
                        # Try multiple YouTube domain variations AND direct IP access
                        transformed_urls.extend([
                            f"https://www.youtube.com/watch?v={video_id}",
                            f"https://youtube.com/watch?v={video_id}",
                            f"https://m.youtube.com/watch?v={video_id}",
                            f"https://music.youtube.com/watch?v={video_id}",
                            # Try direct IP access as DNS workaround
                            f"https://142.250.191.78/watch?v={video_id}",  # YouTube IP
                            f"https://172.217.14.206/watch?v={video_id}",  # YouTube IP
                        ])
                    elif 'youtube.com' in url:
                        # Try alternative YouTube domains and formats
                        video_id = None
                        if 'watch?v=' in url:
                            video_id = url.split('watch?v=')[1].split('&')[0]

                        if video_id:
                            transformed_urls.extend([
                                f"https://www.youtube.com/watch?v={video_id}",
                                f"https://youtube.com/watch?v={video_id}",
                                f"https://m.youtube.com/watch?v={video_id}",
                                f"https://music.youtube.com/watch?v={video_id}",
                            ])
                        else:
                            transformed_urls.extend([
                                url.replace('www.youtube.com', 'youtube.com'),
                                url.replace('youtube.com', 'm.youtube.com'),
                                url.replace('youtube.com', 'music.youtube.com'),
                            ])
                    else:
                        transformed_urls.append(url)

                    for attempt_url in transformed_urls:
                        logger.info(f"DNS workaround attempt: {attempt_url}")

                        # Try with ULTRA-minimal configuration to bypass DNS issues
                        minimal_opts = {
                            'format': 'worst',  # Simplest format selection
                            'outtmpl': str(temp_filepath) + '.%(ext)s',
                            'quiet': True,
                            'no_warnings': True,
                            'socket_timeout': 30,  # Shorter timeout for faster failure
                            'retries': 0,  # No retries to avoid hanging
                            'user_agent': 'Mozilla/5.0 (compatible)',  # Simple user agent
                            # Minimal extractor args
                            'extractor_args': {
                                'youtube': {
                                    'player_client': ['web'],
                                }
                            },
                        }

                        # Much shorter timeout for DNS workaround attempts
                        logger.info(f"Trying DNS workaround with 30s timeout: {attempt_url}")
                        with yt_dlp.YoutubeDL(minimal_opts) as ydl:
                            info = await asyncio.wait_for(
                                asyncio.get_event_loop().run_in_executor(
                                    None, lambda: ydl.extract_info(attempt_url, download=True)
                                ),
                                timeout=30  # Very short timeout for workarounds
                            )

                        # If successful, find the downloaded file
                        downloaded_files = list(self.temp_dir.glob(f"{temp_filename}.*"))
                        if downloaded_files:
                            downloaded_file = downloaded_files[0]
                            file_info = {
                                'title': info.get('title', 'Unknown'),
                                'artist': info.get('uploader', 'Unknown'),
                                'duration': info.get('duration', 0),
                                'size_mb': downloaded_file.stat().st_size / (1024 * 1024),
                                'platform': 'YouTube (DNS workaround)',
                                'filename': str(downloaded_file.name)
                            }
                            logger.info("DNS workaround with URL transformation succeeded!")
                            return downloaded_file, file_info

                except Exception as transform_e:
                    logger.warning(f"DNS workaround failed: {transform_e}")

            # Enhanced fallback for 403 Forbidden with multiple strategies
            if ("403" in str(e) or "Forbidden" in str(e) or "HTTP Error 403" in str(e)):
                logger.warning("403 Forbidden detected. Trying multiple fallback strategies...")

                # Enhanced fallback strategies optimized for environment
                if self.is_streamlit_cloud:
                    # Streamlit Cloud optimized strategies
                    fallback_strategies = [
                        # Strategy 1: Android mobile client (cloud-friendly)
                        {
                            'user_agent': 'Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Mobile Safari/537.36',
                            'referer': 'https://m.youtube.com/',
                            'extractor_args': {
                                'youtube': {
                                    'player_client': ['android'],
                                    'innertube_host': 'youtubei.googleapis.com',
                                }
                            },
                            'sleep_interval': 8,
                            'max_sleep_interval': 30,
                            'http_headers': {
                                'Accept': '*/*',
                                'Accept-Language': 'en-US,en;q=0.9',
                                'X-YouTube-Client-Name': '3',
                                'X-YouTube-Client-Version': '18.11.34',
                            },
                        },
                        # Strategy 2: iOS client (often bypasses detection)
                        {
                            'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
                            'referer': 'https://m.youtube.com/',
                            'extractor_args': {
                                'youtube': {
                                    'player_client': ['ios'],
                                    'innertube_host': 'youtubei.googleapis.com',
                                }
                            },
                            'sleep_interval': 10,
                            'max_sleep_interval': 35,
                            'http_headers': {
                                'Accept': '*/*',
                                'Accept-Language': 'en-US,en;q=0.9',
                                'X-YouTube-Client-Name': '5',
                                'X-YouTube-Client-Version': '17.31.35',
                            },
                        },
                    ]
                else:
                    # Local environment strategies with browser cookie support
                    fallback_strategies = [
                        # Strategy 1: Brave browser with cookies (most effective)
                        {
                            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Brave/121.0.0.0',
                            'referer': 'https://www.youtube.com/',
                            'cookies_from_browser': ('brave', None, None, None),
                            'extractor_args': {
                                'youtube': {
                                    'player_client': ['web'],
                                    'innertube_host': 'youtubei.googleapis.com',
                                }
                            },
                            'sleep_interval': 5,
                            'max_sleep_interval': 20,
                            'http_headers': {
                                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                                'Accept-Language': 'en-US,en;q=0.9',
                                'Sec-Fetch-Dest': 'document',
                                'Sec-Fetch-Mode': 'navigate',
                                'Sec-Fetch-Site': 'none',
                                'Sec-Fetch-User': '?1',
                            },
                        },
                    # Strategy 2: iOS mobile client (often bypasses bot detection)
                    {
                        'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
                        'referer': 'https://m.youtube.com/',
                        'extractor_args': {
                            'youtube': {
                                'player_client': ['ios'],
                                'innertube_host': 'youtubei.googleapis.com',
                                'innertube_key': None,
                            }
                        },
                        'sleep_interval': 8,
                        'max_sleep_interval': 30,
                        'http_headers': {
                            'Accept': '*/*',
                            'Accept-Language': 'en-US,en;q=0.9',
                            'X-YouTube-Client-Name': '5',
                            'X-YouTube-Client-Version': '17.31.35',
                        },
                    },
                    # Strategy 2: Android TV client (different API endpoint)
                    {
                        'user_agent': 'Mozilla/5.0 (Linux; Android 10; SM-G973F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
                        'referer': 'https://www.youtube.com/',
                        'extractor_args': {
                            'youtube': {
                                'player_client': ['android'],
                                'innertube_host': 'youtubei.googleapis.com',
                            }
                        },
                        'sleep_interval': 10,
                        'max_sleep_interval': 35,
                        'http_headers': {
                            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                            'Accept-Language': 'en-US,en;q=0.5',
                            'X-YouTube-Client-Name': '3',
                            'X-YouTube-Client-Version': '18.11.34',
                        },
                    },
                    # Strategy 3: Web client with different headers
                    {
                        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                        'referer': 'https://www.google.com/',
                        'extractor_args': {
                            'youtube': {
                                'player_client': ['web'],
                                'innertube_host': 'youtubei.googleapis.com',
                            }
                        },
                        'sleep_interval': 12,
                        'max_sleep_interval': 40,
                        'http_headers': {
                            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                            'Accept-Language': 'en-US,en;q=0.9',
                            'Cache-Control': 'no-cache',
                            'Pragma': 'no-cache',
                        },
                    },
                    {
                        'user_agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                        'referer': 'https://music.youtube.com/',
                        'extractor_args': {'youtube': {'player_client': ['web']}},
                        'sleep_interval': 10,
                        'max_sleep_interval': 30,
                    }
                ]

                for i, strategy in enumerate(fallback_strategies):
                    logger.info(f"Trying fallback strategy {i + 1}/{len(fallback_strategies)}")
                    ydl_opts_fallback = ydl_opts.copy()
                    ydl_opts_fallback.update(strategy)
                    try:
                        # Add delay before each fallback strategy
                        if i > 0:
                            delay = random.uniform(3, 6)
                            logger.info(f"Waiting {delay:.1f}s before trying next strategy")
                            await asyncio.sleep(delay)

                        with yt_dlp.YoutubeDL(ydl_opts_fallback) as ydl:
                            info = await asyncio.wait_for(
                                asyncio.get_event_loop().run_in_executor(
                                    None, lambda: ydl.extract_info(url, download=True)
                                ),
                                timeout=300
                            )

                        downloaded_files = list(self.temp_dir.glob(f"{temp_filename}.*"))
                        if not downloaded_files:
                            raise FileNotFoundError("Download failed - no file found")

                        downloaded_file = downloaded_files[0]
                        file_info = {
                            'title': info.get('title', 'Unknown'),
                            'artist': info.get('uploader', 'Unknown'),
                            'duration': info.get('duration', 0),
                            'size_mb': downloaded_file.stat().st_size / (1024 * 1024),
                            'platform': f'YouTube (fallback strategy {i + 1})',
                            'filename': str(downloaded_file.name)
                        }

                        logger.info(f"Fallback strategy {i + 1} succeeded!")
                        return downloaded_file, file_info

                    except Exception as fallback_e:
                        logger.warning(f"Fallback strategy {i + 1} failed: {fallback_e}")
                        if i == len(fallback_strategies) - 1:
                            logger.error("All fallback strategies failed")
                            downloader_logger.error(f"All YouTube fallback strategies failed: {fallback_e}")
                        continue

                # Try one more time with minimal options (last resort)
                logger.warning("Trying minimal extraction as last resort...")
                try:
                    minimal_opts = {
                        'format': 'bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio',
                        'outtmpl': str(temp_filepath) + '.%(ext)s',
                        'quiet': False,  # Show output for debugging
                        'no_warnings': False,
                        'user_agent': 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)',
                        'sleep_interval': 5,
                        'extractor_args': {
                            'youtube': {
                                'player_client': ['web'],
                            }
                        },
                    }

                    with yt_dlp.YoutubeDL(minimal_opts) as ydl:
                        info = await asyncio.wait_for(
                            asyncio.get_event_loop().run_in_executor(
                                None, lambda: ydl.extract_info(url, download=True)
                            ),
                            timeout=180
                        )

                    # Find downloaded file
                    downloaded_files = list(self.temp_dir.glob(f"{temp_filename}.*"))
                    if downloaded_files:
                        downloaded_file = downloaded_files[0]
                        file_info = {
                            'title': info.get('title', 'Unknown'),
                            'artist': info.get('uploader', 'Unknown'),
                            'duration': info.get('duration', 0),
                            'size_mb': downloaded_file.stat().st_size / (1024 * 1024),
                            'platform': 'YouTube (minimal)',
                            'filename': str(downloaded_file.name)
                        }
                        logger.info("Minimal extraction successful")
                        return downloaded_file, file_info
                    else:
                        logger.error("Minimal extraction failed - no file found")

                except Exception as minimal_e:
                    logger.error(f"Minimal extraction also failed: {minimal_e}")

                # Store user-friendly error message for the calling function
                error_msg = self.get_user_friendly_error_message(str(e))
                logger.error(f"Final download failure. User message: {error_msg}")
                return None

            # Store user-friendly error message for the calling function
            error_msg = self.get_user_friendly_error_message(str(e))
            logger.error(f"Download failed completely. User message: {error_msg}")
            return None

    async def download_playlist_progressive(self, url: str, quality: str, chat_id: str = None):
        """
        Generator that yields individual audio files from a YouTube playlist as they're downloaded.
        This allows for progressive delivery instead of waiting for the entire playlist.
        """
        if not yt_dlp:
            logger.error("yt-dlp not available for playlist download")
            return

        try:
            logger.info(f"Starting progressive playlist download: {url}")
            downloader_logger.info(f"Progressive playlist download started: {url}")

            # First, get playlist info to know how many videos we're dealing with
            info_opts = {
                'quiet': True,
                'extract_flat': True,  # Just get basic info, don't download
                'dump_single_json': True,
            }

            with yt_dlp.YoutubeDL(info_opts) as ydl:
                playlist_info = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: ydl.extract_info(url, download=False)
                )

            if 'entries' not in playlist_info:
                logger.error("No playlist entries found")
                return

            entries = [entry for entry in playlist_info['entries'] if entry is not None]
            total_videos = len(entries)
            logger.info(f"Found {total_videos} videos in playlist")

            # Download each video individually
            for index, entry in enumerate(entries, 1):
                try:
                    video_url = entry.get('url') or f"https://www.youtube.com/watch?v={entry['id']}"
                    logger.info(f"Downloading video {index}/{total_videos}: {entry.get('title', 'Unknown')}")

                    # Download single video (not playlist)
                    result = await self.download_youtube_audio(video_url, quality, chat_id=chat_id, download_playlist=False)

                    if result is not None:
                        _, file_info = result
                        # Add playlist context to file info
                        file_info['playlist_position'] = f"{index}/{total_videos}"
                        file_info['playlist_title'] = playlist_info.get('title', 'Unknown Playlist')
                        yield result
                    else:
                        logger.warning(f"Failed to download video {index}/{total_videos}")
                        yield None

                except Exception as e:
                    logger.error(f"Error downloading video {index}/{total_videos}: {e}")
                    yield None

        except Exception as e:
            logger.error(f"Error in progressive playlist download: {e}")
            downloader_logger.error(f"Progressive playlist download failed: {e}")

    async def download_spotify_audio(self, url: str, quality: str, chat_id: str = None) -> Optional[Tuple[Path, Dict]]:
        """Download Spotify audio using spotdl with Streamlit Cloud optimizations and checkpoint/resume support."""
        import hashlib
        import json
        from datetime import datetime, timedelta
        import shutil

        def get_track_id(url):
            return hashlib.md5(url.encode()).hexdigest()[:12]

        def get_temp_paths(chat_id, track_id):
            base = Path(self.temp_dir)
            audio = base / f"{chat_id}_{track_id}.mp3"
            meta = base / f"{chat_id}_{track_id}.json"
            return audio, meta

        def cleanup_old_temp_files():
            now = datetime.now()
            for f in Path(self.temp_dir).glob("*"):
                if f.is_file() and f.suffix in {'.mp3', '.json'}:
                    mtime = datetime.fromtimestamp(f.stat().st_mtime)
                    if now - mtime > timedelta(hours=24):
                        try:
                            f.unlink()
                        except Exception as e:
                            logger.warning(f"Failed to delete old temp file {f}: {e}")

        # Clean up old temp files
        cleanup_old_temp_files()

        track_id = get_track_id(url)
        if not chat_id:
            chat_id = 'default'
        audio_path, meta_path = get_temp_paths(chat_id, track_id)

        # Check for existing audio and metadata
        if audio_path.exists() and meta_path.exists():
            try:
                with open(meta_path, 'r', encoding='utf-8') as f:
                    info = json.load(f)
                logger.info(f"Resuming: found audio and metadata for {audio_path}")
                # Try to embed metadata if not already present
                try:
                    from mutagen.id3 import ID3, TIT2, TPE1, TALB, APIC, error
                    from mutagen.mp3 import MP3
                    import requests
                    audio = MP3(audio_path, ID3=ID3)
                    try:
                        audio.add_tags()
                    except error:
                        pass
                    tags = audio.tags
                    tags.delall('TIT2')
                    tags.add(TIT2(encoding=3, text=info.get('title', 'Unknown')))
                    tags.delall('TPE1')
                    tags.add(TPE1(encoding=3, text=info.get('artist', 'Unknown')))
                    tags.delall('TALB')
                    tags.add(TALB(encoding=3, text=info.get('album', 'Spotify')))
                    thumbnail_url = info.get('thumbnail')
                    if thumbnail_url:
                        try:
                            response = requests.get(thumbnail_url)
                            if response.status_code == 200:
                                tags.delall('APIC')
                                tags.add(
                                    APIC(
                                        encoding=3,
                                        mime='image/jpeg',
                                        type=3,
                                        desc='Cover',
                                        data=response.content
                                    )
                                )
                                logger.info(f"Embedded cover art from {thumbnail_url}")
                        except Exception as thumb_e:
                            logger.warning(f"Exception downloading or embedding thumbnail: {thumb_e}")
                    audio.save()
                    logger.info(f"Metadata and cover art embedded for {audio_path}")
                except Exception as meta_e:
                    logger.warning(f"Failed to robustly embed metadata or cover art: {meta_e}")
                file_info = {
                    'title': info.get('title', 'Unknown'),
                    'artist': info.get('artist', 'Unknown'),
                    'duration': info.get('duration', 0),
                    'size_mb': audio_path.stat().st_size / (1024 * 1024),
                    'platform': 'Spotify',
                    'filename': str(audio_path.name)
                }
                # Delete temp files after successful resume
                try:
                    audio_path.unlink()
                    meta_path.unlink()
                except Exception as cleanup_e:
                    logger.warning(f"Failed to delete temp files after resume: {cleanup_e}")
                return audio_path, file_info
            except Exception as e:
                logger.warning(f"Failed to resume from temp files: {e}")
                # If resume fails, fall through to fresh download

        # Log the Spotify URL being processed
        downloader_logger.info(f"Processing Spotify URL: {url}")

        # Extract and log track ID for reference
        track_id_match = re.search(r'track/([a-zA-Z0-9]+)', url)
        if track_id_match:
            track_id = track_id_match.group(1)
            downloader_logger.info(f"Spotify track ID: {track_id}")

        # Otherwise, proceed with fresh download
        try:
            # Quality mapping
            quality_map = {
                "high": "320",
                "medium": "192",
                "low": "128"
            }

            bitrate = quality_map.get(quality, "192")

            # Generate unique output directory
            output_dir = self.temp_dir / f"spotify_{int(time.time())}"
            output_dir.mkdir(exist_ok=True)
            
            # Prepare spotdl command with valid arguments only
            # Use appropriate Python command based on environment
            if self.is_streamlit_cloud:
                # Streamlit Cloud uses python3
                python_cmd = ["python3", "-m", "spotdl"]
            else:
                # Local Windows uses py launcher, Linux uses python3
                import platform
                if platform.system().lower() == "windows":
                    python_cmd = ["py", "-m", "spotdl"]
                else:
                    python_cmd = ["python3", "-m", "spotdl"]

            base_cmd = python_cmd + [
                "download",
                url,
                "--bitrate", f"{bitrate}k",
                "--format", "mp3",
                "--output", str(output_dir),
                "--print-errors",  # Show detailed errors
                "--max-retries", "3",  # Valid spotdl argument
                "--no-cache",  # Valid spotdl argument (not --no-cache-dir)
            ]

            # Add cookie support if available
            if hasattr(self, 'cookie_file') and self.cookie_file and Path(self.cookie_file).exists():
                base_cmd.extend(["--cookie-file", str(self.cookie_file)])
                logger.info(f"Using cookie file for spotdl: {self.cookie_file}")

            # Additional options for Streamlit Cloud
            if self.is_streamlit_cloud:
                base_cmd.extend([
                    "--threads", "1",  # Single thread for stability
                    "--simple-tui",    # Simpler output for cloud
                    "--restrict-filenames",  # Avoid filename issues
                ])

            spotdl_cmd = base_cmd

            # Add FFmpeg path explicitly for spotdl (using same logic as audio_downloader_bot.py)
            if self.ffmpeg_path == "system":
                # For system FFmpeg, let spotdl find it automatically
                logger.info("Using system FFmpeg for spotdl")
            elif self.ffmpeg_path:
                # For local FFmpeg, specify the path explicitly
                system = platform.system().lower()
                if system == "windows":
                    ffmpeg_exe = Path(self.ffmpeg_path) / "ffmpeg.exe"
                else:
                    ffmpeg_exe = Path(self.ffmpeg_path) / "ffmpeg"

                if ffmpeg_exe.exists():
                    spotdl_cmd.extend(["--ffmpeg", str(ffmpeg_exe)])
                    logger.info(f"Using local FFmpeg for spotdl: {ffmpeg_exe}")
                else:
                    logger.warning(f"FFmpeg not found at expected path: {ffmpeg_exe}")
            else:
                logger.warning("No FFmpeg configured - spotdl may fail")
            
            # Run spotdl with timeout (shorter timeout for Streamlit Cloud)
            logger.info(f"Running spotdl command: {' '.join(spotdl_cmd)}")
            logger.info(f"Working directory: {output_dir}")
            logger.info(f"FFmpeg path configured: {self.ffmpeg_path}")
            logger.info(f"Streamlit Cloud mode: {self.is_streamlit_cloud}")

            downloader_logger.info(f"Starting spotdl download for URL: {url}")
            downloader_logger.info(f"Command: {' '.join(spotdl_cmd)}")
            downloader_logger.info(f"Quality: {bitrate}k, Format: mp3")

            # Check if output directory exists and is writable
            if not output_dir.exists():
                logger.error(f"Output directory does not exist: {output_dir}")
                output_dir.mkdir(parents=True, exist_ok=True)
                logger.info(f"Created output directory: {output_dir}")

            # Adjust timeouts for Streamlit Cloud
            if self.is_streamlit_cloud:
                process_timeout = 180  # 3 minutes for Streamlit Cloud
                async_timeout = 200    # 3.3 minutes
            else:
                process_timeout = 300  # 5 minutes for local
                async_timeout = 320    # 5.3 minutes

            result = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: sp.run(
                        spotdl_cmd,
                        capture_output=True,
                        text=True,
                        timeout=process_timeout,
                        cwd=str(output_dir)
                    )
                ),
                timeout=async_timeout
            )

            # Log detailed output for debugging
            logger.info(f"spotdl exit code: {result.returncode}")
            downloader_logger.info(f"spotdl command completed with exit code: {result.returncode}")

            if result.stdout:
                logger.info(f"spotdl stdout: {result.stdout}")
                downloader_logger.info(f"spotdl stdout: {result.stdout}")

                # Try to extract track info from spotdl output
                if "Found" in result.stdout and "by" in result.stdout:
                    downloader_logger.info(f"spotdl found track info in output: {result.stdout}")

            if result.stderr:
                logger.error(f"spotdl stderr: {result.stderr}")
                downloader_logger.error(f"spotdl stderr: {result.stderr}")

            # Check what files were created in the output directory
            created_files = list(output_dir.glob("*"))
            logger.info(f"Files in output directory after spotdl: {[f.name for f in created_files]}")

            if result.returncode != 0:
                logger.error(f"spotdl failed with exit code {result.returncode}")
                downloader_logger.error(f"spotdl FAILED - Exit code: {result.returncode}")
                downloader_logger.error(f"Command: {' '.join(spotdl_cmd)}")
                downloader_logger.error(f"Working directory: {output_dir}")
                downloader_logger.error(f"stdout: {result.stdout}")
                downloader_logger.error(f"stderr: {result.stderr}")

                # Analyze the specific error type
                error_output = (result.stderr or "") + (result.stdout or "")

                # Check if spotdl module is missing
                if "no module named spotdl" in error_output.lower():
                    logger.error("spotdl module not found - attempting to install")
                    downloader_logger.error("spotdl module missing - trying installation")

                    try:
                        import subprocess
                        logger.info("Installing spotdl...")
                        install_result = subprocess.run([
                            "python3", "-m", "pip", "install", "spotdl>=4.2.0", "--no-cache-dir"
                        ], capture_output=True, text=True, timeout=180)

                        if install_result.returncode == 0:
                            logger.info("Successfully installed spotdl - retrying download")
                            downloader_logger.info("spotdl installation successful - retrying")

                            # Retry the download after installation
                            retry_result = subprocess.run(spotdl_cmd, capture_output=True, text=True, timeout=timeout)
                            if retry_result.returncode == 0:
                                logger.info("spotdl download successful after installation")
                                result = retry_result  # Use the successful result
                            else:
                                logger.error(f"spotdl still failed after installation: {retry_result.stderr}")
                                raise Exception(f"spotdl failed even after installation: {retry_result.stderr}")
                        else:
                            logger.error(f"Failed to install spotdl: {install_result.stderr}")
                            raise Exception(f"spotdl not available and installation failed: {install_result.stderr}")
                    except Exception as install_error:
                        logger.error(f"spotdl installation error: {install_error}")
                        raise Exception(f"spotdl not available and installation failed: {install_error}")

                # Check for YouTube bot detection in spotdl
                if any(phrase in error_output.lower() for phrase in [
                    "sign in to confirm you're not a bot",
                    "unable to download api page",
                    "failed to resolve 'y'",
                    "http error 403",
                    "forbidden"
                ]):
                    logger.error("YouTube bot detection affecting spotdl backend")
                    downloader_logger.error("spotdl failed due to YouTube anti-bot measures")

                    # Try with alternative spotdl configuration
                    logger.info("Attempting spotdl with alternative configuration...")
                    alternative_result = await self._try_alternative_spotdl(url, quality, output_dir)
                    if alternative_result:
                        return alternative_result

                # Check if it's an FFmpeg-related error
                elif result.stderr and ("ffmpeg" in result.stderr.lower() or "code -11" in result.stderr):
                    logger.error("FFmpeg-related error detected. Running diagnostics...")
                    downloader_logger.error("FFmpeg-related error detected in spotdl output")

                    # Run FFmpeg diagnostics
                    diagnosis = await self.diagnose_ffmpeg_issue()
                    logger.error(f"FFmpeg diagnosis: {diagnosis['status']} - {diagnosis['issue']}")
                    logger.error(f"Recommendation: {diagnosis['recommendation']}")
                    downloader_logger.error(f"FFmpeg diagnosis: {diagnosis}")

                    for detail in diagnosis['details']:
                        logger.info(f"Diagnosis detail: {detail}")

                # Try fallback to YouTube search
                logger.info("Attempting fallback to YouTube search")
                downloader_logger.info(f"STARTING FALLBACK - Spotify URL: {url}")
                return await self.download_spotify_fallback(url, quality)
            
            # Find downloaded file - check for various audio formats recursively
            audio_extensions = ["*.mp3", "*.m4a", "*.webm", "*.ogg", "*.wav"]
            downloaded_files = []

            # First check the main directory
            for ext in audio_extensions:
                files = list(output_dir.glob(ext))
                downloaded_files.extend(files)
                logger.info(f"Found {len(files)} files with extension {ext} in main directory")

            # Then check ALL subdirectories recursively (spotdl creates nested dirs)
            for ext in audio_extensions:
                recursive_files = list(output_dir.rglob(ext))  # rglob searches recursively
                # Filter out files already found in main directory
                new_files = [f for f in recursive_files if f not in downloaded_files]
                downloaded_files.extend(new_files)
                logger.info(f"Found {len(new_files)} additional files with extension {ext} in subdirectories")

            logger.info(f"Total downloaded files found: {len(downloaded_files)}")
            for file in downloaded_files:
                logger.info(f"Downloaded file: {file} (size: {file.stat().st_size} bytes)")
                downloader_logger.info(f"Downloaded file: {file} (size: {file.stat().st_size} bytes)")

            if not downloaded_files:
                # List all files in output directory for debugging
                all_files = list(output_dir.rglob("*"))
                logger.error(f"No audio files found. All files in output directory:")
                downloader_logger.error(f"No audio files found. All files in output directory:")
                for file in all_files:
                    if file.is_file():
                        logger.error(f"  {file} (size: {file.stat().st_size} bytes)")
                        downloader_logger.error(f"  {file} (size: {file.stat().st_size} bytes)")
                raise FileNotFoundError("Download failed - no audio file found")
            
            # Use the first (and hopefully only) downloaded file
            downloaded_file = downloaded_files[0]
            filename = downloaded_file.stem
            file_extension = downloaded_file.suffix

            logger.info(f"Processing downloaded file: {downloaded_file}")
            logger.info(f"File extension: {file_extension}")

            # If the file is not MP3, we might need to convert it or just use it as-is
            if file_extension.lower() != '.mp3':
                logger.warning(f"Downloaded file is {file_extension}, not MP3. Using as-is.")

            # Parse artist and title from filename
            if " - " in filename:
                parts = filename.split(" - ", 1)
                artist = parts[0].strip()
                title = parts[1].strip()
            else:
                title = filename
                artist = "Unknown Artist"

            # After finding and processing the downloaded file:
            # Save metadata
            info = {
                'title': title,
                'artist': artist,
                'duration': 0,
                'album': 'Spotify',
                'thumbnail': None,  # You can add thumbnail extraction if available
            }
            with open(meta_path, 'w', encoding='utf-8') as f:
                json.dump(info, f)
            # Copy audio to temp path
            shutil.copy(str(downloaded_file), str(audio_path))
            # Delete temp files after successful download
            try:
                audio_path.unlink()
                meta_path.unlink()
            except Exception as cleanup_e:
                logger.warning(f"Failed to delete temp files after download: {cleanup_e}")
            file_info = {
                'title': title,
                'artist': artist,
                'duration': 0,
                'size_mb': downloaded_file.stat().st_size / (1024 * 1024),
                'platform': 'Spotify',
                'filename': str(downloaded_file.name)
            }
            return downloaded_file, file_info
        except Exception as e:
            logger.error(f"Spotify download failed: {e}")
            downloader_logger.error(f"Spotify download failed for URL {url}: {e}")
            downloader_logger.error(f"Error type: {type(e).__name__}")
            downloader_logger.error(f"Error details: {str(e)}")

            # Try fallback
            logger.info("Attempting Spotify fallback via YouTube search...")
            fallback_result = await self.download_spotify_fallback(url, quality)

            if fallback_result is None:
                logger.error("Both Spotify direct download and YouTube fallback failed")
                downloader_logger.error("Both Spotify direct download and YouTube fallback failed")

                # Provide helpful error message for users
                error_msg = self._get_spotify_error_message(str(e))
                raise Exception(error_msg)

            return fallback_result
    
    async def download_spotify_fallback(self, url: str, quality: str) -> Optional[Tuple[Path, Dict]]:
        """Fallback: search for Spotify track on YouTube using simplified approach"""
        try:
            logger.info(f"Attempting Spotify fallback for URL: {url}")

            # Extract track ID for basic search
            track_id_match = re.search(r'track/([a-zA-Z0-9]+)', url)
            if not track_id_match:
                logger.error("Could not extract track ID for fallback search")
                return None

            track_id = track_id_match.group(1)

            # Try to get basic track info from Spotify page title
            search_query = await self.get_spotify_search_query(url)
            if not search_query:
                # Fallback to generic search using track ID
                search_query = f"spotify track {track_id[:8]}"
                logger.warning(f"Could not extract song info from Spotify page, using generic search: {search_query}")
            else:
                logger.info(f"Extracted search query from Spotify: {search_query}")

            logger.info(f"Searching YouTube for: {search_query}")
            downloader_logger.info(f"YouTube search query for Spotify fallback: {search_query}")

            # Search YouTube for the track
            youtube_url = await self.search_youtube(search_query)
            if youtube_url:
                logger.info(f"Found YouTube alternative: {youtube_url}")
                result = await self.download_youtube_audio(youtube_url, quality, download_playlist=False)

                # If successful, update the platform info to indicate it's a Spotify fallback
                if result:
                    file_path, file_info = result
                    file_info['platform'] = 'Spotify (via YouTube)'
                    file_info['original_url'] = url
                    return file_path, file_info

            logger.warning("No suitable YouTube alternative found")
            return None

        except Exception as e:
            logger.error(f"Spotify fallback failed: {e}")
            downloader_logger.error(f"Spotify fallback failed for URL {url}: {e}")
            downloader_logger.error(f"Fallback error type: {type(e).__name__}")
            downloader_logger.error(f"Fallback error details: {str(e)}")
            return None

    async def _try_alternative_spotdl(self, url: str, quality: str, output_dir: Path) -> Optional[Tuple[Path, Dict]]:
        """Try alternative spotdl configuration when standard approach fails."""
        try:
            logger.info("Trying alternative spotdl configuration...")

            # Map quality to bitrate
            quality_map = {"high": "320", "medium": "192", "low": "128"}
            bitrate = quality_map.get(quality, "192")

            # Ultra-conservative spotdl command with valid arguments only
            # Use appropriate Python command based on environment
            if self.is_streamlit_cloud:
                # Streamlit Cloud uses python3
                python_cmd = ["python3", "-m", "spotdl"]
            else:
                # Local Windows uses py launcher, Linux uses python3
                import platform
                if platform.system().lower() == "windows":
                    python_cmd = ["py", "-m", "spotdl"]
                else:
                    python_cmd = ["python3", "-m", "spotdl"]

            alt_cmd = python_cmd + [
                "download",
                url,
                "--bitrate", f"{bitrate}k",
                "--format", "mp3",
                "--output", str(output_dir),
                "--simple-tui",  # Valid argument
                "--restrict",  # Valid argument (not --restrict-filenames)
                "--no-cache",  # Valid argument
                "--threads", "1",  # Valid argument
                "--max-retries", "2",  # Valid argument (not --retries)
            ]

            logger.info(f"Alternative spotdl command: {' '.join(alt_cmd)}")

            # Shorter timeout for alternative attempt
            result = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: sp.run(
                        alt_cmd,
                        capture_output=True,
                        text=True,
                        timeout=120,  # 2 minutes only
                        cwd=str(output_dir)
                    )
                ),
                timeout=140
            )

            if result.returncode == 0:
                logger.info("Alternative spotdl configuration succeeded!")

                # Find downloaded file
                audio_extensions = ["*.mp3", "*.m4a", "*.webm", "*.ogg"]
                downloaded_files = []
                for ext in audio_extensions:
                    downloaded_files.extend(list(output_dir.glob(ext)))

                if downloaded_files:
                    downloaded_file = downloaded_files[0]
                    logger.info(f"Alternative spotdl downloaded: {downloaded_file.name}")

                    # Create basic file info
                    file_info = {
                        'title': downloaded_file.stem,
                        'artist': 'Unknown',
                        'duration': 0,
                        'size_mb': downloaded_file.stat().st_size / (1024 * 1024),
                        'platform': 'Spotify (alternative)',
                        'filename': str(downloaded_file.name)
                    }
                    return downloaded_file, file_info

            logger.warning("Alternative spotdl configuration also failed")
            return None

        except Exception as e:
            logger.error(f"Alternative spotdl attempt failed: {e}")
            return None

    def _get_spotify_error_message(self, error_str: str) -> str:
        """Generate user-friendly error message for Spotify download failures."""
        error_lower = error_str.lower()

        if any(phrase in error_lower for phrase in [
            "sign in to confirm you're not a bot",
            "unable to download api page",
            "failed to resolve 'y'",
            "http error 403",
            "forbidden"
        ]):
            return (
                "🎵 **Spotify Download Currently Unavailable**\n\n"
                "Spotify downloads are temporarily blocked due to YouTube's enhanced anti-bot measures.\n\n"
                "**Why this happens:**\n"
                "• Spotify downloads use YouTube as the audio source\n"
                "• YouTube is currently blocking automated downloads\n"
                "• This affects all Spotify download services globally\n\n"
                "**Alternative Solutions:**\n"
                "• Use direct YouTube links instead of Spotify links\n"
                "• Try during off-peak hours (early morning/late night)\n"
                "• Wait 30-60 minutes and try again\n"
                "• Use shorter songs (under 5 minutes work better)\n\n"
                "**This is temporary** - Spotify downloads typically resume within 1-2 hours."
            )
        elif "ffmpeg" in error_lower:
            return (
                "🔧 **Audio Processing Error**\n\n"
                "There was an issue processing the audio file.\n\n"
                "**What you can do:**\n"
                "• Try again in a few minutes\n"
                "• Try a different song\n"
                "• Use 'Medium' or 'Low' quality settings\n"
                "• Contact admin if issue persists"
            )
        else:
            return (
                "🎵 **Spotify Download Failed**\n\n"
                "The Spotify download encountered an unexpected error.\n\n"
                "**Recommended actions:**\n"
                "• Try using a direct YouTube link instead\n"
                "• Wait 15-30 minutes and try again\n"
                "• Try during off-peak hours\n"
                "• Contact admin if problem persists\n\n"
                "**Note:** Spotify downloads depend on YouTube availability."
            )

    async def get_spotify_search_query(self, url: str) -> Optional[str]:
        """Get a search query from Spotify URL by fetching page title"""
        try:
            downloader_logger.info(f"Attempting to extract search query from Spotify URL: {url}")

            if not requests:
                downloader_logger.error("Requests library not available")
                return None

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }

            response = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: requests.get(url, headers=headers, timeout=10)
                ),
                timeout=15
            )

            downloader_logger.info(f"Spotify page response status: {response.status_code}")

            if response.status_code == 200:
                html = response.text

                # Try multiple methods to extract song information
                search_query = None

                # Method 1: Extract from meta tags (more reliable)
                meta_patterns = [
                    r'<meta property="og:title" content="([^"]+)"',
                    r'<meta name="twitter:title" content="([^"]+)"',
                    r'<meta property="music:song" content="([^"]+)"',
                ]

                for pattern in meta_patterns:
                    meta_match = re.search(pattern, html, re.IGNORECASE)
                    if meta_match:
                        search_query = meta_match.group(1)
                        downloader_logger.info(f"Found song info in meta tags: {search_query}")
                        break

                # Method 2: Extract from page title (fallback)
                if not search_query:
                    title_match = re.search(r'<title[^>]*>([^<]+)</title>', html)
                    if title_match:
                        search_query = title_match.group(1)
                        downloader_logger.info(f"Found song info in page title: {search_query}")

                if search_query:
                    # Clean up the extracted text
                    # Remove " | Spotify", " - Spotify", etc.
                    search_query = re.sub(r'\s*[\|\-]\s*Spotify.*$', '', search_query, flags=re.IGNORECASE)

                    # Remove common unwanted patterns
                    search_query = re.sub(r'\([^)]*(?:official|video|lyrics|audio|music|mv|explicit)\)', '', search_query, flags=re.IGNORECASE)
                    search_query = re.sub(r'\[[^\]]*(?:official|video|lyrics|audio|music|mv|explicit)\]', '', search_query, flags=re.IGNORECASE)

                    # Clean up extra spaces and special characters
                    search_query = ' '.join(search_query.split())
                    search_query = search_query.strip()

                    downloader_logger.info(f"Cleaned search query: {search_query}")

                    if search_query and search_query.lower() not in ['spotify', 'music', 'song']:
                        logger.info(f"Successfully extracted search query: {search_query}")
                        return search_query

            downloader_logger.warning("Could not extract title from Spotify page")
            return None

        except Exception as e:
            downloader_logger.error(f"Error getting Spotify search query: {e}")
            logger.warning(f"Error getting Spotify search query: {e}")
            return None
    
    async def search_youtube(self, query: str) -> Optional[str]:
        """Search YouTube for a track"""
        if not yt_dlp:
            downloader_logger.error("yt-dlp not available for YouTube search")
            return None

        try:
            downloader_logger.info(f"Searching YouTube for: '{query}'")

            # Enhanced search for music content with anti-blocking
            user_agents = [
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            ]

            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'default_search': 'ytsearch5:',  # Get top 5 results for better matching
                'user_agent': random.choice(user_agents),
                'extractor_args': {
                    'youtube': {
                        'player_client': ['android', 'web'],
                    }
                },
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                search_results = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None, lambda: ydl.extract_info(query, download=False)
                    ),
                    timeout=30
                )

                if search_results and 'entries' in search_results and search_results['entries']:
                    # Log all found results for debugging
                    downloader_logger.info(f"Found {len(search_results['entries'])} YouTube results:")
                    for i, entry in enumerate(search_results['entries'][:5]):
                        title = entry.get('title', 'Unknown')
                        uploader = entry.get('uploader', 'Unknown')
                        duration = entry.get('duration', 0)
                        url = entry.get('webpage_url', 'No URL')
                        downloader_logger.info(f"  {i+1}. {title} by {uploader} ({duration}s) - {url}")

                    # Try to select the best music-related result
                    selected_result = None

                    # Look for music-related keywords in titles and uploaders
                    music_keywords = ['official', 'music', 'audio', 'song', 'track', 'album', 'artist', 'band']
                    non_music_keywords = ['tutorial', 'how to', 'fix', 'browser', 'chrome', 'guide', 'review', 'unboxing']

                    for entry in search_results['entries'][:5]:
                        title = entry.get('title', '').lower()
                        uploader = entry.get('uploader', '').lower()

                        # Skip clearly non-music content
                        if any(keyword in title for keyword in non_music_keywords):
                            downloader_logger.info(f"Skipping non-music result: {entry.get('title', 'Unknown')}")
                            continue

                        # Prefer music-related content
                        if any(keyword in title or keyword in uploader for keyword in music_keywords):
                            selected_result = entry
                            downloader_logger.info(f"Selected music-related result: {entry.get('title', 'Unknown')}")
                            break

                    # If no music-specific result found, use the first one
                    if not selected_result:
                        selected_result = search_results['entries'][0]
                        downloader_logger.info(f"No music-specific result found, using first result: {selected_result.get('title', 'Unknown')}")

                    selected_url = selected_result['webpage_url']
                    selected_title = selected_result.get('title', 'Unknown')

                    downloader_logger.info(f"Final selected YouTube result: {selected_title} - {selected_url}")
                    logger.info(f"Found YouTube alternative: {selected_title}")

                    return selected_url
                else:
                    downloader_logger.warning("No YouTube search results found")

            return None

        except Exception as e:
            downloader_logger.error(f"YouTube search failed: {e}")
            logger.error(f"YouTube search failed: {e}")
            return None
    
    def cleanup_file(self, file_path: Path):
        """Clean up downloaded file"""
        try:
            if file_path.exists():
                file_path.unlink()
                # Also try to remove parent directory if it's empty
                try:
                    file_path.parent.rmdir()
                except:
                    pass
        except Exception as e:
            logger.error(f"Error cleaning up file {file_path}: {e}")
