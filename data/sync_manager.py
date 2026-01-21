# data/sync_manager.py
# Automatic synchronization manager for Google Drive datasets

import asyncio
import logging
from typing import Optional
from datetime import datetime
from data.hybrid_detector import HybridChangeDetector
from data.datasets import load_datasets, get_all_data
from data.drive import load_game_scores
from config import get_config

logger = logging.getLogger(__name__)


class DatasetSyncManager:
    """
    Manages automatic synchronization of datasets from Google Drive.
    Monitors files for changes and triggers reloads when updates are detected.
    """
    
    def __init__(self, check_interval: int = 120, auto_start: bool = True, webhook_enabled: bool = True):
        """
        Initialize the sync manager.
        
        Args:
            check_interval: Seconds between checking for changes (default: 120)
            auto_start: Whether to start monitoring automatically
            webhook_enabled: Whether to try using webhooks for instant detection (default: True)
        """
        self.detector = HybridChangeDetector(
            polling_interval=check_interval,
            webhook_enabled=webhook_enabled
        )
        self.config = get_config()
        self.last_sync_times = {}
        self.sync_in_progress = {}
        self.auto_start = auto_start
        
    def _register_all_files(self):
        """Register all configured Google Drive files for monitoring"""
        
        # Index Database (HLCFILE)
        if self.config.HLCFILE_ID:
            self.detector.register_file(
                self.config.HLCFILE_ID,
                self._on_hlc_file_changed,
                "Index Database (Hymn/Lyric/Convention Lists)"
            )
            
        # Main Excel File (FILE_ID)
        if self.config.FILE_ID:
            self.detector.register_file(
                self.config.FILE_ID,
                self._on_main_file_changed,
                "Main Excel File (Song History)"
            )
            
        # Tune Database (TFILE_ID)
        if self.config.TFILE_ID:
            self.detector.register_file(
                self.config.TFILE_ID,
                self._on_tune_file_changed,
                "Tune Database"
            )
            
        # Game Score Database
        if self.config.GAME_SCORE:
            self.detector.register_file(
                self.config.GAME_SCORE,
                self._on_game_score_changed,
                "Game Score Database"
            )
            
        # User Database
        if self.config.U_DATABASE:
            self.detector.register_file(
                self.config.U_DATABASE,
                self._on_user_db_changed,
                "User Database"
            )
            
        logger.info("✅ Registered all files for change detection")

    async def _reload_datasets_safe(self, file_name: str):
        """Safely reload datasets with error handling and debouncing"""
        
        # Prevent multiple simultaneous reloads
        if self.sync_in_progress.get(file_name, False):
            logger.info(f"⏭️ Skipping reload for {file_name} - sync already in progress")
            return
            
        try:
            self.sync_in_progress[file_name] = True
            logger.info(f"🔄 Reloading datasets due to {file_name} change...")
            
            # Small delay to allow file to fully save on Drive
            await asyncio.sleep(2)
            
            # Reload the datasets (synchronous call in async context)
            await asyncio.get_event_loop().run_in_executor(None, load_datasets)
            
            self.last_sync_times[file_name] = datetime.now()
            logger.info(f"✅ Successfully reloaded datasets for {file_name}")
            
        except Exception as e:
            logger.error(f"❌ Error reloading datasets for {file_name}: {e}")
        finally:
            self.sync_in_progress[file_name] = False

    async def _on_hlc_file_changed(self, file_id: str):
        """Callback when Index Database changes"""
        logger.info("📊 Index Database (HLC) changed, triggering sync...")
        await self._reload_datasets_safe("Index Database")

    async def _on_main_file_changed(self, file_id: str):
        """Callback when Main Excel File changes"""
        logger.info("📊 Main Excel File (Song History) changed, triggering sync...")
        await self._reload_datasets_safe("Main Excel File")

    async def _on_tune_file_changed(self, file_id: str):
        """Callback when Tune Database changes"""
        logger.info("📊 Tune Database changed, triggering sync...")
        await self._reload_datasets_safe("Tune Database")

    async def _on_game_score_changed(self, file_id: str):
        """Callback when Game Score Database changes"""
        logger.info("📊 Game Score Database changed, triggering sync...")
        await self._reload_datasets_safe("Game Score Database")

    async def _on_user_db_changed(self, file_id: str):
        """Callback when User Database changes"""
        logger.info("📊 User Database changed, triggering sync...")
        await self._reload_datasets_safe("User Database")

    async def start(self):
        """Start the sync manager"""
        logger.info("🚀 Starting Dataset Sync Manager...")
        self._register_all_files()
        await self.detector.start()

    async def stop(self):
        """Stop the sync manager"""
        logger.info("🛑 Stopping Dataset Sync Manager...")
        await self.detector.stop()

    def get_sync_status(self) -> dict:
        """Get the current sync status for all monitored files"""
        detector_status = self.detector.get_status()
        status = {
            'last_sync_times': self.last_sync_times,
            'sync_in_progress': self.sync_in_progress,
            'monitored_files': detector_status['monitored_files'],
            'running': detector_status['running'],
            'mode': 'hybrid' if detector_status['active_webhooks'] > 0 else 'polling',
            'active_webhooks': detector_status['active_webhooks'],
            'polling_interval': detector_status['polling_interval'],
            'webhook_files': detector_status.get('webhook_files', []),
            'last_webhook_events': detector_status.get('last_webhook_events', {})
        }
        return status

    def force_sync(self, file_name: Optional[str] = None):
        """
        Force a manual sync of datasets.
        
        Args:
            file_name: Optional specific file to sync (None for all)
        """
        logger.info(f"🔄 Manual sync triggered for: {file_name or 'all files'}")
        asyncio.create_task(self._reload_datasets_safe(file_name or "Manual Trigger"))


# Global instance
_sync_manager: Optional[DatasetSyncManager] = None


def get_sync_manager(check_interval: int = 120) -> DatasetSyncManager:
    """
    Get or create the global sync manager instance.
    
    Args:
        check_interval: Seconds between checks (only used on first call)
    """
    global _sync_manager
    if _sync_manager is None:
        _sync_manager = DatasetSyncManager(check_interval=check_interval)
    return _sync_manager


async def start_auto_sync(check_interval: int = 120):
    """
    Start automatic synchronization of datasets.
    
    Args:
        check_interval: Seconds between checking for changes (default: 120)
    """
    manager = get_sync_manager(check_interval)
    await manager.start()


async def stop_auto_sync():
    """Stop automatic synchronization"""
    manager = get_sync_manager()
    await manager.stop()


def get_sync_status() -> dict:
    """Get current sync status"""
    manager = get_sync_manager()
    return manager.get_sync_status()


def force_manual_sync():
    """Force a manual sync of all datasets"""
    manager = get_sync_manager()
    manager.force_sync()
