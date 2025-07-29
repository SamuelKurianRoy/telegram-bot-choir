"""
Audio Downloader Module for Telegram Bot
Supports YouTube and Spotify audio downloads
"""

import os
import re
import time
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
                    lambda: sp.run(["spotdl", "--version"], capture_output=True, text=True, timeout=10)
                ),
                timeout=15
            )

            if result.returncode == 0:
                test_result['status'] = 'working'
                test_result['version'] = result.stdout.strip()
                logger.info(f"spotdl is working: {test_result['version']}")

                # Also test help to see available commands
                try:
                    help_result = sp.run(["spotdl", "--help"], capture_output=True, text=True, timeout=5)
                    if help_result.returncode == 0:
                        test_result['help_output'] = help_result.stdout
                        logger.info("spotdl help command successful")
                except Exception as help_error:
                    logger.warning(f"Could not get spotdl help: {help_error}")

            else:
                test_result['status'] = 'error'
                test_result['error'] = result.stderr or result.stdout
                logger.error(f"spotdl version check failed: {test_result['error']}")

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
    
    async def extract_info(self, url: str) -> Optional[Dict]:
        """Extract basic info from URL"""
        if not yt_dlp:
            raise Exception("yt-dlp not installed")
            
        platform = self.detect_platform(url)
        
        try:
            if platform == 'Spotify':
                return await self.extract_spotify_info(url)
            else:
                # Use yt-dlp for other platforms
                ydl_opts = {
                    'quiet': True,
                    'no_warnings': True,
                    'extract_flat': False,
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

    async def download_audio(self, url: str, quality: str = "medium", chat_id: str = None) -> Optional[Tuple[Path, Dict]]:
        """Download audio from URL, passing chat_id for checkpoint/resume."""
        platform = self.detect_platform(url)
        if platform == 'Spotify':
            return await self.download_spotify_audio(url, quality, chat_id=chat_id)
        else:
            return await self.download_youtube_audio(url, quality, chat_id=chat_id)
    
    async def download_youtube_audio(self, url: str, quality: str, chat_id: str = None) -> Optional[Tuple[Path, Dict]]:
        """Download audio from YouTube using yt-dlp, with checkpoint/resume support."""
        import hashlib
        import json
        from datetime import datetime, timedelta

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
            }

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
            
            # Download with timeout
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None, lambda: ydl.extract_info(url, download=True)
                    ),
                    timeout=300  # 5 minute timeout
                )
            
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
            # Proxy fallback for 403 Forbidden
            if ("403" in str(e) or "Forbidden" in str(e)):
                logger.warning("403 Forbidden detected. Retrying with proxy...")
                proxy_url = 'http://proxy.scrapeops.io:5353'  # Example reliable public proxy
                ydl_opts['proxy'] = proxy_url
                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = await asyncio.wait_for(
                            asyncio.get_event_loop().run_in_executor(
                                None, lambda: ydl.extract_info(url, download=True)
                            ),
                            timeout=300
                        )
                    downloaded_files = list(self.temp_dir.glob(f"{temp_filename}.*"))
                    if not downloaded_files:
                        raise FileNotFoundError("Download failed - no file found (proxy)")
                    downloaded_file = downloaded_files[0]
                    file_info = {
                        'title': info.get('title', 'Unknown'),
                        'artist': info.get('uploader', 'Unknown'),
                        'duration': info.get('duration', 0),
                        'size_mb': downloaded_file.stat().st_size / (1024 * 1024),
                        'platform': 'YouTube (proxy)'
                    }
                    # (Optional: repeat renaming and metadata logic here if needed)
                    return downloaded_file, file_info
                except Exception as proxy_e:
                    logger.error(f"Proxy download also failed: {proxy_e}")
                    return None
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
                        file_path, file_info = result
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
            
            # Prepare spotdl command with better output handling for Streamlit Cloud
            if self.is_streamlit_cloud:
                # Use a simpler output pattern for Streamlit Cloud
                spotdl_cmd = [
                    "spotdl",
                    "download",
                    url,
                    "--bitrate", f"{bitrate}k",
                    "--format", "mp3",
                    "--output", str(output_dir),
                    "--print-errors"  # Show more detailed errors
                ]
            else:
                spotdl_cmd = [
                    "spotdl",
                    "download",
                    url,
                    "--bitrate", f"{bitrate}k",
                    "--format", "mp3",
                    "--output", str(output_dir)
                ]

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
            if result.stdout:
                logger.info(f"spotdl stdout: {result.stdout}")
            if result.stderr:
                logger.error(f"spotdl stderr: {result.stderr}")

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

                logger.error(f"Command: {' '.join(spotdl_cmd)}")
                logger.error(f"Working directory: {output_dir}")

                # Check if it's an FFmpeg-related error
                if result.stderr and ("ffmpeg" in result.stderr.lower() or "code -11" in result.stderr):
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
            # Try fallback
            return await self.download_spotify_fallback(url, quality)
    
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
                # Fallback to generic search
                search_query = f"spotify track {track_id[:8]}"

            logger.info(f"Searching YouTube for: {search_query}")

            # Search YouTube for the track
            youtube_url = await self.search_youtube(search_query)
            if youtube_url:
                logger.info(f"Found YouTube alternative: {youtube_url}")
                result = await self.download_youtube_audio(youtube_url, quality)

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
            return None

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

                # Extract title from page
                title_match = re.search(r'<title[^>]*>([^<]+)</title>', html)
                if title_match:
                    title_text = title_match.group(1)
                    # Remove " | Spotify" from the end
                    title_text = title_text.replace(' | Spotify', '').strip()

                    downloader_logger.info(f"Raw title from Spotify page: {title_text}")

                    if title_text and title_text != 'Spotify':
                        # Clean up the title for better search results
                        # Remove common unwanted patterns
                        cleaned_title = title_text

                        # Remove things like "(Official Video)", "(Lyrics)", etc.
                        cleaned_title = re.sub(r'\([^)]*(?:official|video|lyrics|audio|music|mv)\)', '', cleaned_title, flags=re.IGNORECASE)
                        cleaned_title = re.sub(r'\[[^\]]*(?:official|video|lyrics|audio|music|mv)\]', '', cleaned_title, flags=re.IGNORECASE)

                        # Clean up extra spaces
                        cleaned_title = ' '.join(cleaned_title.split())

                        downloader_logger.info(f"Cleaned search query: {cleaned_title}")
                        logger.info(f"Extracted search query from page title: {cleaned_title}")
                        return cleaned_title

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

            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'default_search': 'ytsearch3:',  # Get top 3 results for better matching
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
                    for i, entry in enumerate(search_results['entries'][:3]):
                        title = entry.get('title', 'Unknown')
                        uploader = entry.get('uploader', 'Unknown')
                        duration = entry.get('duration', 0)
                        url = entry.get('webpage_url', 'No URL')
                        downloader_logger.info(f"  {i+1}. {title} by {uploader} ({duration}s) - {url}")

                    # Use the first result
                    selected_result = search_results['entries'][0]
                    selected_url = selected_result['webpage_url']
                    selected_title = selected_result.get('title', 'Unknown')

                    downloader_logger.info(f"Selected YouTube result: {selected_title} - {selected_url}")
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
