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

class AudioDownloader:
    """Audio downloader class for YouTube and Spotify"""

    def __init__(self, temp_dir: str = "temp"):
        self.temp_dir = Path(temp_dir)
        self.temp_dir.mkdir(exist_ok=True)

        # Set FFmpeg path - use the complete setup from audio_downloader_bot.py
        self.ffmpeg_path = asyncio.run(self._setup_ffmpeg())

        # Configure FFmpeg in PATH if local installation found
        if self.ffmpeg_path and self.ffmpeg_path != "system":
            # Add FFmpeg directory to PATH (same as audio_downloader_bot.py)
            current_path = os.environ.get("PATH", "")
            if self.ffmpeg_path not in current_path:
                os.environ["PATH"] = self.ffmpeg_path + os.pathsep + current_path
                logger.info(f"Added FFmpeg to PATH: {self.ffmpeg_path}")

            # Configure spotdl to use local FFmpeg
            system = platform.system().lower()
            if system == "windows":
                ffmpeg_exe = Path(self.ffmpeg_path) / "ffmpeg.exe"
            else:
                ffmpeg_exe = Path(self.ffmpeg_path) / "ffmpeg"

            if ffmpeg_exe.exists():
                os.environ["FFMPEG_BINARY"] = str(ffmpeg_exe)
                logger.info(f"Set FFMPEG_BINARY environment variable: {ffmpeg_exe}")

    async def _setup_ffmpeg(self) -> Optional[str]:
        """Setup FFmpeg using the complete logic from audio_downloader_bot.py"""
        try:
            # First, check if ffmpeg is already installed on the system
            try:
                result = sp.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    logger.info("FFmpeg is already installed on the system")
                    return "system"  # Indicates system FFmpeg should be used
            except:
                logger.info("FFmpeg not found in system PATH, checking local directory")

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

                    # Try multiple sources for Linux FFmpeg (prioritize simple downloads)
                    ffmpeg_urls = [
                        # Direct static binary (most reliable)
                        "https://github.com/BtbN/FFmpeg-Builds/releases/download/autobuild-2023-12-09-12-49/ffmpeg-n6.1-2-g31f1a25352-linux64-gpl-6.1.tar.xz",
                        # Alternative static binary
                        "https://johnvansickle.com/ffmpeg/builds/ffmpeg-git-amd64-static.tar.xz",
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

                            # Test the downloaded version
                            test_result = sp.run([str(linux_ffmpeg_path), "-version"],
                                               capture_output=True, text=True, timeout=10)
                            if test_result.returncode == 0:
                                logger.info("Downloaded Linux FFmpeg is working correctly")
                                success = True
                                break
                            else:
                                logger.warning("Downloaded FFmpeg is not working, trying next source")
                                linux_ffmpeg_path.unlink(missing_ok=True)

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
                    # Try apt-get (Ubuntu/Debian systems like Streamlit Cloud)
                    install_result = sp.run(
                        ["apt-get", "update", "&&", "apt-get", "install", "-y", "ffmpeg"],
                        capture_output=True, text=True, timeout=120, shell=True
                    )
                    if install_result.returncode == 0:
                        logger.info("Successfully installed FFmpeg via apt-get")
                        # Test if it's now available
                        test_result = sp.run(["ffmpeg", "-version"], capture_output=True, text=True)
                        if test_result.returncode == 0:
                            logger.info("System FFmpeg is now working")
                            return "system"  # System FFmpeg is available
                    else:
                        logger.warning(f"Failed to install FFmpeg via apt-get: {install_result.stderr}")
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
            return None

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
        """Extract Spotify track info"""
        try:
            # Extract track ID from URL
            track_id_match = re.search(r'track/([a-zA-Z0-9]+)', url)
            if not track_id_match:
                return None
                
            # For now, return basic info - in production you'd use Spotify API
            return {
                'title': 'Spotify Track',
                'artist': 'Unknown Artist',
                'duration': 0,
                'platform': 'Spotify'
            }
        except Exception as e:
            logger.error(f"Error extracting Spotify info: {e}")
            return None
    
    async def download_audio(self, url: str, quality: str = "medium") -> Optional[Tuple[Path, Dict]]:
        """Download audio from URL"""
        platform = self.detect_platform(url)
        
        if platform == 'Spotify':
            return await self.download_spotify_audio(url, quality)
        else:
            return await self.download_youtube_audio(url, quality)
    
    async def download_youtube_audio(self, url: str, quality: str) -> Optional[Tuple[Path, Dict]]:
        """Download audio from YouTube using yt-dlp"""
        if not yt_dlp:
            raise Exception("yt-dlp not installed")
            
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
            
            return downloaded_file, file_info
            
        except Exception as e:
            logger.error(f"YouTube download failed: {e}")
            return None
    
    async def download_spotify_audio(self, url: str, quality: str) -> Optional[Tuple[Path, Dict]]:
        """Download Spotify audio using spotdl"""
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
            
            # Prepare spotdl command
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
            
            # Run spotdl with timeout
            result = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: sp.run(
                        spotdl_cmd,
                        capture_output=True,
                        text=True,
                        timeout=300,
                        cwd=str(output_dir)
                    )
                ),
                timeout=320
            )
            
            if result.returncode != 0:
                # Try fallback to YouTube search
                return await self.download_spotify_fallback(url, quality)
            
            # Find downloaded file
            downloaded_files = list(output_dir.glob("*.mp3"))
            if not downloaded_files:
                raise FileNotFoundError("Download failed - no MP3 file found")
            
            downloaded_file = downloaded_files[0]
            filename = downloaded_file.stem
            
            # Parse artist and title from filename
            if " - " in filename:
                parts = filename.split(" - ", 1)
                artist = parts[0].strip()
                title = parts[1].strip()
            else:
                title = filename
                artist = "Unknown Artist"
            
            file_info = {
                'title': title,
                'artist': artist,
                'duration': 0,
                'size_mb': downloaded_file.stat().st_size / (1024 * 1024),
                'platform': 'Spotify'
            }
            
            return downloaded_file, file_info
            
        except Exception as e:
            logger.error(f"Spotify download failed: {e}")
            # Try fallback
            return await self.download_spotify_fallback(url, quality)
    
    async def download_spotify_fallback(self, url: str, quality: str) -> Optional[Tuple[Path, Dict]]:
        """Fallback: search for Spotify track on YouTube"""
        try:
            # Extract basic info from Spotify URL (simplified)
            # In production, you'd use Spotify API here
            search_query = "spotify track"  # Placeholder
            
            # Search YouTube for the track
            youtube_url = await self.search_youtube(search_query)
            if youtube_url:
                return await self.download_youtube_audio(youtube_url, quality)
            
            return None
            
        except Exception as e:
            logger.error(f"Spotify fallback failed: {e}")
            return None
    
    async def search_youtube(self, query: str) -> Optional[str]:
        """Search YouTube for a track"""
        if not yt_dlp:
            return None
            
        try:
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'default_search': 'ytsearch1:',
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                search_results = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None, lambda: ydl.extract_info(query, download=False)
                    ),
                    timeout=30
                )
                
                if search_results and 'entries' in search_results and search_results['entries']:
                    return search_results['entries'][0]['webpage_url']
            
            return None
            
        except Exception as e:
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
