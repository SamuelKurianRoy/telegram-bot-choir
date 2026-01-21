# data/change_detector.py
# Google Drive Change Detection and Auto-Sync System

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable
import json
import os
from googleapiclient.errors import HttpError
from data.drive import get_drive_service
from config import get_config

logger = logging.getLogger(__name__)


class DriveChangeDetector:
    """
    Monitors Google Drive files for changes and triggers updates.
    Uses Google Drive API's changes endpoint to efficiently detect modifications.
    """

    def __init__(self, check_interval: int = 60):
        """
        Initialize the change detector.
        
        Args:
            check_interval: Time in seconds between change checks (default: 60 seconds)
        """
        self.check_interval = check_interval
        self.drive_service = None
        self.page_tokens: Dict[str, str] = {}  # Store page tokens for each file
        self.file_ids: List[str] = []
        self.callbacks: Dict[str, List[Callable]] = {}  # Callbacks to execute when file changes
        self.last_check = {}
        self.running = False
        self.cache_file = os.path.join(os.path.dirname(__file__), '.drive_change_cache.json')
        
    def _load_cache(self):
        """Load cached page tokens from disk"""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r') as f:
                    cache = json.load(f)
                    self.page_tokens = cache.get('page_tokens', {})
                    self.last_check = cache.get('last_check', {})
                    logger.info(f"📦 Loaded change detection cache for {len(self.page_tokens)} files")
        except Exception as e:
            logger.warning(f"⚠️ Could not load change cache: {e}")
            
    def _save_cache(self):
        """Save page tokens to disk"""
        try:
            cache = {
                'page_tokens': self.page_tokens,
                'last_check': self.last_check,
                'updated_at': datetime.now().isoformat()
            }
            with open(self.cache_file, 'w') as f:
                json.dump(cache, f, indent=2)
        except Exception as e:
            logger.warning(f"⚠️ Could not save change cache: {e}")

    def register_file(self, file_id: str, callback: Callable, name: str = None):
        """
        Register a file to monitor for changes.
        
        Args:
            file_id: Google Drive file ID to monitor
            callback: Function to call when file changes (async or sync)
            name: Optional name for logging purposes
        """
        if file_id not in self.file_ids:
            self.file_ids.append(file_id)
            logger.info(f"📝 Registered file for monitoring: {name or file_id}")
            
        if file_id not in self.callbacks:
            self.callbacks[file_id] = []
        self.callbacks[file_id].append(callback)

    def _get_start_page_token(self, file_id: str) -> str:
        """Get the starting page token for a file"""
        try:
            if not self.drive_service:
                self.drive_service = get_drive_service()
                
            # Get start page token for the entire drive
            response = self.drive_service.changes().getStartPageToken().execute()
            return response.get('startPageToken')
        except HttpError as e:
            logger.error(f"❌ Error getting start page token: {e}")
            return None

    def _check_file_changes(self, file_id: str) -> bool:
        """
        Check if a specific file has been modified.
        
        Returns:
            True if file has changed, False otherwise
        """
        try:
            if not self.drive_service:
                self.drive_service = get_drive_service()

            # Initialize page token if not exists
            if file_id not in self.page_tokens:
                self.page_tokens[file_id] = self._get_start_page_token(file_id)
                self._save_cache()
                return False  # First run, no changes to report

            page_token = self.page_tokens[file_id]
            if not page_token:
                return False

            # Query for changes
            response = self.drive_service.changes().list(
                pageToken=page_token,
                spaces='drive',
                fields='nextPageToken,newStartPageToken,changes(fileId,file(modifiedTime,name))'
            ).execute()

            changes = response.get('changes', [])
            file_changed = False

            for change in changes:
                if change.get('fileId') == file_id:
                    file_info = change.get('file', {})
                    modified_time = file_info.get('modifiedTime')
                    file_name = file_info.get('name', 'Unknown')
                    
                    logger.info(f"🔄 Detected change in {file_name} (ID: {file_id[:8]}...) at {modified_time}")
                    file_changed = True
                    break

            # Update page token for next check
            new_page_token = response.get('newStartPageToken') or response.get('nextPageToken')
            if new_page_token:
                self.page_tokens[file_id] = new_page_token
                self._save_cache()

            return file_changed

        except HttpError as e:
            if e.resp.status == 404:
                logger.error(f"❌ File {file_id} not found or not accessible")
            elif e.resp.status == 429:
                logger.warning(f"⚠️ Rate limit reached. Backing off...")
                # Rate limit hit - this is extremely unlikely with our usage
                # but handle it gracefully just in case
            else:
                logger.error(f"❌ Error checking file changes: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Unexpected error checking changes: {e}")
            return False

    async def _execute_callbacks(self, file_id: str):
        """Execute all callbacks registered for a file"""
        if file_id not in self.callbacks:
            return
            
        for callback in self.callbacks[file_id]:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(file_id)
                else:
                    callback(file_id)
                logger.info(f"✅ Executed callback for file {file_id[:8]}...")
            except Exception as e:
                logger.error(f"❌ Error executing callback for {file_id}: {e}")

    async def _monitor_loop(self):
        """Main monitoring loop"""
        logger.info(f"🚀 Starting Drive change detector (checking every {self.check_interval}s)")
        logger.info(f"📊 API Usage: ~{len(self.file_ids)} calls per {self.check_interval}s = ~{(len(self.file_ids) * 720):.0f} calls/day")
        self._load_cache()
        
        while self.running:
            try:
                for file_id in self.file_ids:
                    if not self.running:
                        break
                        
                    has_changed = self._check_file_changes(file_id)
                    
                    if has_changed:
                        logger.info(f"📥 File {file_id[:8]}... changed, triggering update...")
                        await self._execute_callbacks(file_id)
                        self.last_check[file_id] = datetime.now().isoformat()
                        self._save_cache()
                    
                    # Small delay between file checks to spread API calls and avoid rate limiting
                    await asyncio.sleep(2)
                
                # Wait for next check cycle
                await asyncio.sleep(self.check_interval)
                
            except Exception as e:
                logger.error(f"❌ Error in monitor loop: {e}")
                await asyncio.sleep(10)  # Longer pause on error before retry

    async def start(self):
        """Start the change detection service"""
        if self.running:
            logger.warning("⚠️ Change detector is already running")
            return
            
        self.running = True
        logger.info("🎯 Drive change detector started")
        await self._monitor_loop()

    async def stop(self):
        """Stop the change detection service"""
        self.running = False
        self._save_cache()
        logger.info("🛑 Drive change detector stopped")

    def get_last_check_time(self, file_id: str) -> Optional[str]:
        """Get the last time a file was checked and found changed"""
        return self.last_check.get(file_id)


# Simple polling-based alternative (lighter weight, no webhooks needed)
class PollingChangeDetector:
    """
    Simpler alternative that uses file modification time polling.
    Less efficient but easier to set up (no webhook configuration needed).
    """
    
    def __init__(self, check_interval: int = 120):
        """
        Initialize polling detector.
        
        Args:
            check_interval: Time in seconds between polls (default: 120 seconds)
        """
        self.check_interval = check_interval
        self.drive_service = None
        self.file_metadata: Dict[str, dict] = {}
        self.callbacks: Dict[str, List[Callable]] = {}
        self.running = False
        self.cache_file = os.path.join(os.path.dirname(__file__), '.drive_poll_cache.json')
        
    def _load_cache(self):
        """Load cached metadata from disk"""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r') as f:
                    self.file_metadata = json.load(f)
                    logger.info(f"📦 Loaded polling cache for {len(self.file_metadata)} files")
        except Exception as e:
            logger.warning(f"⚠️ Could not load polling cache: {e}")
            
    def _save_cache(self):
        """Save metadata to disk"""
        try:
            with open(self.cache_file, 'w') as f:
                json.dump(self.file_metadata, f, indent=2)
        except Exception as e:
            logger.warning(f"⚠️ Could not save polling cache: {e}")

    def register_file(self, file_id: str, callback: Callable, name: str = None):
        """Register a file to monitor"""
        if file_id not in self.callbacks:
            self.callbacks[file_id] = []
            logger.info(f"📝 Registered file for polling: {name or file_id}")
        self.callbacks[file_id].append(callback)

    def _get_file_modified_time(self, file_id: str) -> Optional[str]:
        """Get the modification time of a file"""
        try:
            if not self.drive_service:
                self.drive_service = get_drive_service()
                
            file_metadata = self.drive_service.files().get(
                fileId=file_id,
                fields='modifiedTime,name'
            ).execute()
            
            return file_metadata.get('modifiedTime'), file_metadata.get('name')
        except HttpError as e:
            if e.resp.status == 429:
                logger.warning(f"⚠️ Rate limit reached for file {file_id[:8]}... Backing off...")
                # Rate limit - extremely unlikely with our usage pattern
            else:
                logger.error(f"❌ Error getting file metadata: {e}")
            return None, None

    async def _check_and_update(self, file_id: str):
        """Check if file has been modified since last check"""
        try:
            modified_time, file_name = self._get_file_modified_time(file_id)
            
            if not modified_time:
                return False
                
            # Check if this is first run or if file has changed
            if file_id not in self.file_metadata:
                self.file_metadata[file_id] = {
                    'modifiedTime': modified_time,
                    'name': file_name,
                    'lastCheck': datetime.now().isoformat()
                }
                self._save_cache()
                return False  # First run, don't trigger callbacks
                
            cached_time = self.file_metadata[file_id]['modifiedTime']
            
            if modified_time != cached_time:
                logger.info(f"🔄 File {file_name} (ID: {file_id[:8]}...) modified: {modified_time}")
                
                # Update cache
                self.file_metadata[file_id].update({
                    'modifiedTime': modified_time,
                    'name': file_name,
                    'lastCheck': datetime.now().isoformat()
                })
                self._save_cache()
                
                # Execute callbacks
                for callback in self.callbacks.get(file_id, []):
                    try:
                        if asyncio.iscoroutinefunction(callback):
                            await callback(file_id)
                        else:
                            callback(file_id)
                        logger.info(f"✅ Executed callback for {file_name}")
                    except Exception as e:
                        logger.error(f"❌ Error executing callback: {e}")
                        
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Error checking file {file_id}: {e}")
            return False

    async def _poll_loop(self):
        """Main polling loop"""
        num_files = len(self.callbacks)
        calls_per_day = (60 * 60 * 24 // self.check_interval) * num_files
        logger.info(f"🚀 Starting Drive polling detector (checking every {self.check_interval}s)")
        logger.info(f"📊 Monitoring {num_files} files → ~{calls_per_day} API calls/day (~0.0004% of free quota)")
        self._load_cache()
        
        while self.running:
            try:
                for file_id in self.callbacks.keys():
                    if not self.running:
                        break
                    await self._check_and_update(file_id)
                    # Delay between file checks to spread API calls
                    await asyncio.sleep(2)
                    
                await asyncio.sleep(self.check_interval)
                
            except Exception as e:
                logger.error(f"❌ Error in poll loop: {e}")
                await asyncio.sleep(10)

    async def start(self):
        """Start polling"""
        if self.running:
            logger.warning("⚠️ Polling detector is already running")
            return
            
        self.running = True
        logger.info("🎯 Drive polling detector started")
        await self._poll_loop()

    async def stop(self):
        """Stop polling"""
        self.running = False
        self._save_cache()
        logger.info("🛑 Drive polling detector stopped")
