# data/hybrid_detector.py
# Hybrid change detection: Webhooks (instant) + Polling (fallback)

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable, Set
from googleapiclient.errors import HttpError
from data.drive import get_drive_service
from data.change_detector import PollingChangeDetector
from config import get_config
import uuid

logger = logging.getLogger(__name__)


class HybridChangeDetector:
    """
    Hybrid change detector that uses webhooks for instant detection
    with polling as a reliable fallback.
    
    Strategy:
    1. Try to register webhooks for instant notifications
    2. Always run polling in background as safety net
    3. If webhook fails/expires, polling takes over seamlessly
    """
    
    def __init__(self, polling_interval: int = 10, webhook_enabled: bool = True):
        """
        Initialize hybrid detector.
        
        Args:
            polling_interval: Polling fallback interval in seconds (default: 10)
            webhook_enabled: Whether to attempt webhook registration (default: True)
        """
        self.polling_interval = polling_interval
        self.webhook_enabled = webhook_enabled
        self.drive_service = None
        
        # Polling detector (always active as fallback)
        self.polling_detector = PollingChangeDetector(check_interval=polling_interval)
        
        # Webhook state
        self.webhook_channels: Dict[str, dict] = {}  # file_id -> channel info
        self.webhook_active_files: Set[str] = set()  # Files with active webhooks
        self.last_webhook_event: Dict[str, datetime] = {}  # Track webhook events
        
        # Callbacks
        self.callbacks: Dict[str, List[Callable]] = {}
        
        self.running = False
        
    def register_file(self, file_id: str, callback: Callable, name: str = None):
        """Register a file to monitor"""
        # Register with polling detector (always)
        self.polling_detector.register_file(file_id, callback, name)
        
        # Store callback for webhook use
        if file_id not in self.callbacks:
            self.callbacks[file_id] = []
        self.callbacks[file_id].append(callback)
        
        logger.info(f"📝 Registered {name or file_id} for hybrid monitoring (webhooks + polling)")
        
    def _try_register_webhook(self, file_id: str) -> bool:
        """
        Try to register a webhook for a file.
        Returns True if successful, False otherwise.
        """
        if not self.webhook_enabled:
            return False
            
        try:
            if not self.drive_service:
                self.drive_service = get_drive_service()
            
            # Note: This requires a public HTTPS endpoint
            # For Streamlit, we'd need to set up a webhook receiver
            # For now, this is a placeholder that gracefully fails
            config = get_config()
            webhook_url = getattr(config, 'WEBHOOK_URL', None)
            
            if not webhook_url:
                logger.info(f"ℹ️ No WEBHOOK_URL configured, using polling-only mode")
                return False
            
            channel_id = str(uuid.uuid4())
            expiration = int((datetime.now() + timedelta(hours=24)).timestamp() * 1000)
            
            # Register webhook
            channel = self.drive_service.files().watch(
                fileId=file_id,
                body={
                    'id': channel_id,
                    'type': 'web_hook',
                    'address': webhook_url,
                    'expiration': expiration
                }
            ).execute()
            
            self.webhook_channels[file_id] = {
                'id': channel_id,
                'resource_id': channel.get('resourceId'),
                'expiration': expiration
            }
            self.webhook_active_files.add(file_id)
            
            logger.info(f"✅ Webhook registered for file {file_id[:8]}... (expires in 24h)")
            return True
            
        except HttpError as e:
            if e.resp.status == 401:
                logger.warning(f"⚠️ Webhook registration failed: Unauthorized. Using polling-only mode.")
            elif e.resp.status == 400:
                logger.warning(f"⚠️ Webhook registration failed: Invalid endpoint. Using polling-only mode.")
            else:
                logger.warning(f"⚠️ Webhook registration failed: {e}. Using polling-only mode.")
            return False
        except Exception as e:
            logger.warning(f"⚠️ Webhook registration error: {e}. Using polling-only mode.")
            return False
    
    def _stop_webhook(self, file_id: str):
        """Stop a webhook channel"""
        if file_id not in self.webhook_channels:
            return
            
        try:
            if not self.drive_service:
                self.drive_service = get_drive_service()
                
            channel = self.webhook_channels[file_id]
            self.drive_service.channels().stop(
                body={
                    'id': channel['id'],
                    'resourceId': channel['resource_id']
                }
            ).execute()
            
            logger.info(f"🛑 Stopped webhook for file {file_id[:8]}...")
            
        except Exception as e:
            logger.warning(f"⚠️ Error stopping webhook: {e}")
        finally:
            self.webhook_channels.pop(file_id, None)
            self.webhook_active_files.discard(file_id)
    
    async def handle_webhook_notification(self, file_id: str):
        """
        Handle a webhook notification (called by webhook endpoint).
        
        This would be called by your Streamlit webhook handler.
        """
        self.last_webhook_event[file_id] = datetime.now()
        logger.info(f"⚡ Webhook notification received for file {file_id[:8]}...")
        
        # Execute callbacks immediately (instant detection!)
        if file_id in self.callbacks:
            for callback in self.callbacks[file_id]:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(file_id)
                    else:
                        callback(file_id)
                except Exception as e:
                    logger.error(f"❌ Error executing webhook callback: {e}")
    
    async def _webhook_monitor_loop(self):
        """Monitor webhook health and renew when needed"""
        if not self.webhook_enabled:
            return
            
        logger.info("🔔 Webhook monitor started")
        
        while self.running:
            try:
                # Try to register webhooks for any files that don't have them
                for file_id in self.callbacks.keys():
                    if file_id not in self.webhook_active_files:
                        self._try_register_webhook(file_id)
                
                # Check for expiring webhooks (renew before 1 hour left)
                now = datetime.now().timestamp() * 1000
                for file_id, channel in list(self.webhook_channels.items()):
                    expiration = channel['expiration']
                    if expiration - now < 3600000:  # Less than 1 hour left
                        logger.info(f"🔄 Renewing webhook for {file_id[:8]}...")
                        self._stop_webhook(file_id)
                        self._try_register_webhook(file_id)
                
                # Check every 30 minutes
                await asyncio.sleep(1800)
                
            except Exception as e:
                logger.error(f"❌ Error in webhook monitor: {e}")
                await asyncio.sleep(60)
    
    async def start(self):
        """Start the hybrid detector"""
        if self.running:
            logger.warning("⚠️ Hybrid detector already running")
            return
        
        self.running = True
        
        # Try to register webhooks for all files
        webhook_count = 0
        if self.webhook_enabled:
            for file_id in self.callbacks.keys():
                if self._try_register_webhook(file_id):
                    webhook_count += 1
        
        if webhook_count > 0:
            logger.info(f"🎯 Hybrid mode: {webhook_count} webhooks active + polling fallback every {self.polling_interval}s")
            # Start webhook monitor
            asyncio.create_task(self._webhook_monitor_loop())
        else:
            logger.info(f"🎯 Polling-only mode: Checking every {self.polling_interval}s (webhooks unavailable)")
        
        # Always start polling as fallback
        await self.polling_detector.start()
    
    async def stop(self):
        """Stop the hybrid detector"""
        self.running = False
        
        # Stop all webhooks
        for file_id in list(self.webhook_channels.keys()):
            self._stop_webhook(file_id)
        
        # Stop polling
        await self.polling_detector.stop()
        
        logger.info("🛑 Hybrid detector stopped")
    
    def get_status(self) -> dict:
        """Get current status"""
        return {
            'running': self.running,
            'webhook_enabled': self.webhook_enabled,
            'active_webhooks': len(self.webhook_active_files),
            'polling_active': self.polling_detector.running,
            'polling_interval': self.polling_interval,
            'monitored_files': len(self.callbacks),
            'webhook_files': list(self.webhook_active_files),
            'last_webhook_events': {
                fid: evt.isoformat() for fid, evt in self.last_webhook_event.items()
            }
        }
