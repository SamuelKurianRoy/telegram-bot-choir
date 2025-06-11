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
from pathlib import Path
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse

try:
    import yt_dlp
except ImportError:
    yt_dlp = None

try:
    import requests
except ImportError:
    requests = None

# Setup logging
logger = logging.getLogger(__name__)

class AudioDownloader:
    """Audio downloader class for YouTube and Spotify"""

    def __init__(self, temp_dir: str = "temp"):
        self.temp_dir = Path(temp_dir)
        self.temp_dir.mkdir(exist_ok=True)

        # Set FFmpeg path - check for local installation first
        self.ffmpeg_path = self._find_ffmpeg_path()

    def _find_ffmpeg_path(self) -> Optional[str]:
        """Find FFmpeg installation path"""
        # Check local ffmpeg directory first
        local_ffmpeg_paths = [
            "./ffmpeg/ffmpeg.exe",  # Windows
            "./ffmpeg/ffmpeg",      # Linux/Mac
            "ffmpeg/ffmpeg.exe",    # Windows (relative)
            "ffmpeg/ffmpeg",        # Linux/Mac (relative)
        ]

        for path in local_ffmpeg_paths:
            if Path(path).exists():
                logger.info(f"Found local FFmpeg at: {path}")
                return str(Path(path).absolute())

        # Check system PATH
        import shutil
        system_ffmpeg = shutil.which("ffmpeg")
        if system_ffmpeg:
            logger.info(f"Found system FFmpeg at: {system_ffmpeg}")
            return system_ffmpeg

        logger.warning("FFmpeg not found. Audio conversion may fail.")
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

            # Add FFmpeg location if found
            if self.ffmpeg_path:
                ydl_opts['ffmpeg_location'] = str(Path(self.ffmpeg_path).parent)
            
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

            # Add FFmpeg location if found
            if self.ffmpeg_path:
                spotdl_cmd.extend(["--ffmpeg", self.ffmpeg_path])
            
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
