#!/usr/bin/env python3
"""
Feature Control System for Admin Management
Uses Google Drive Excel sheet (DISABLED_DB) for persistent storage
"""

import pandas as pd
import logging
import streamlit as st
from typing import Dict, List, Optional
from datetime import datetime
import io
from data.drive import get_drive_service
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload

logger = logging.getLogger(__name__)

class FeatureController:
    """Manages enabled/disabled features using Google Drive Excel sheet"""

    def __init__(self):
        self.disabled_db_id = st.secrets.get("DISABLED_DB")
        if not self.disabled_db_id:
            logger.error("DISABLED_DB file ID not found in secrets")
            raise ValueError("DISABLED_DB configuration missing")

        self.drive_service = get_drive_service()
        self._cache = None
        self._cache_timestamp = None
        
        # Cache timeout in seconds (5 minutes)
        self.cache_timeout = 300

        # Default feature definitions (fallback if Excel is unavailable)
        self.default_features = {
            'download': {
                'name': 'Download Commands',
                'description': 'YouTube and Spotify audio downloads',
                'commands': '/download, URL downloads',
                'enabled': True
            },
            'search': {
                'name': 'Song Search',
                'description': 'Search for hymns and songs',
                'commands': '/search',
                'enabled': True
            },
            'date': {
                'name': 'Date Commands',
                'description': 'Check song dates and history',
                'commands': '/date',
                'enabled': True
            },
            'bible': {
                'name': 'Bible Verses',
                'description': 'Bible verse lookup and search',
                'commands': '/bible',
                'enabled': True
            },
            'check': {
                'name': 'Song Checking',
                'description': 'Check specific hymn numbers',
                'commands': '/check',
                'enabled': True
            },
            'last': {
                'name': 'Last Sung',
                'description': 'Check when songs were last sung',
                'commands': '/last',
                'enabled': True
            }
        }
    
    def _load_from_drive(self) -> pd.DataFrame:
        """Load feature configuration from Google Drive Excel sheet"""
        try:
            # Check cache first
            if self._cache is not None and self._cache_timestamp is not None:
                cache_age = (datetime.now() - self._cache_timestamp).total_seconds()
                if cache_age < self.cache_timeout:
                    logger.debug("Using cached feature data")
                    return self._cache

            logger.info("Loading feature configuration from Google Drive...")

            # Download Excel file from Google Drive
            request = self.drive_service.files().get_media(fileId=self.disabled_db_id)
            file_data = io.BytesIO()
            downloader = MediaIoBaseDownload(file_data, request)

            done = False
            while not done:
                status, done = downloader.next_chunk()

            file_data.seek(0)

            # Read Excel file
            df = pd.read_excel(file_data, sheet_name='FeatureControl')

            # Update cache
            self._cache = df
            self._cache_timestamp = datetime.now()

            logger.info(f"Successfully loaded {len(df)} features from Google Drive")
            return df

        except Exception as e:
            logger.error(f"Error loading from Google Drive: {e}")
            # Return default features as DataFrame
            return self._create_default_dataframe()

    def _save_to_drive(self, df: pd.DataFrame) -> bool:
        """Save feature configuration to Google Drive Excel sheet"""
        try:
            logger.info("Saving feature configuration to Google Drive...")

            # Convert DataFrame to Excel in memory
            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='FeatureControl', index=False)
            excel_buffer.seek(0)

            # Upload to Google Drive
            media = MediaIoBaseUpload(
                excel_buffer,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )

            # Update the existing file
            updated_file = self.drive_service.files().update(
                fileId=self.disabled_db_id,
                media_body=media
            ).execute()

            # Update cache
            self._cache = df
            self._cache_timestamp = datetime.now()

            logger.info("Successfully saved feature configuration to Google Drive")
            return True

        except Exception as e:
            logger.error(f"Error saving to Google Drive: {e}")
            return False

    def _create_default_dataframe(self) -> pd.DataFrame:
        """Create default DataFrame structure"""
        data = []
        for feature_name, feature_info in self.default_features.items():
            data.append({
                'feature_name': feature_name,
                'feature_display_name': feature_info['name'],
                'commands': feature_info['commands'],
                'enabled': feature_info['enabled'],
                'disabled_reason': '',
                'disabled_by_admin_id': '',
                'disabled_date': '',
                'last_modified': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })

        return pd.DataFrame(data)
    
    def is_feature_enabled(self, feature_name: str) -> bool:
        """Check if a feature is enabled"""
        try:
            df = self._load_from_drive()

            # Find the feature in the DataFrame
            feature_row = df[df['feature_name'] == feature_name]

            if feature_row.empty:
                logger.warning(f"Unknown feature: {feature_name}")
                return True  # Default to enabled for unknown features

            return bool(feature_row.iloc[0]['enabled'])

        except Exception as e:
            logger.error(f"Error checking feature status: {e}")
            # Default to enabled if there's an error
            return True
    
    def enable_feature(self, feature_name: str, admin_id: int) -> tuple[bool, str]:
        """Enable a feature"""
        try:
            df = self._load_from_drive()

            # Find the feature in the DataFrame
            feature_idx = df[df['feature_name'] == feature_name].index

            if feature_idx.empty:
                return False, f"Unknown feature: {feature_name}"

            # Update the feature
            idx = feature_idx[0]
            df.loc[idx, 'enabled'] = True
            df.loc[idx, 'disabled_reason'] = ''
            df.loc[idx, 'disabled_by_admin_id'] = ''
            df.loc[idx, 'disabled_date'] = ''
            df.loc[idx, 'last_modified'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Save to Google Drive
            if self._save_to_drive(df):
                feature_display_name = df.loc[idx, 'feature_display_name']
                return True, f"✅ **{feature_display_name}** has been enabled"
            else:
                return False, "Failed to save configuration to Google Drive"

        except Exception as e:
            logger.error(f"Error enabling feature: {e}")
            return False, f"Error enabling feature: {str(e)}"

    def disable_feature(self, feature_name: str, admin_id: int, reason: str = None) -> tuple[bool, str]:
        """Disable a feature"""
        try:
            df = self._load_from_drive()

            # Find the feature in the DataFrame
            feature_idx = df[df['feature_name'] == feature_name].index

            if feature_idx.empty:
                return False, f"Unknown feature: {feature_name}"

            # Update the feature
            idx = feature_idx[0]
            df.loc[idx, 'enabled'] = False
            df.loc[idx, 'disabled_reason'] = reason or "Disabled by administrator"
            df.loc[idx, 'disabled_by_admin_id'] = str(admin_id)
            df.loc[idx, 'disabled_date'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            df.loc[idx, 'last_modified'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Save to Google Drive
            if self._save_to_drive(df):
                feature_display_name = df.loc[idx, 'feature_display_name']
                return True, f"❌ **{feature_display_name}** has been disabled"
            else:
                return False, "Failed to save configuration to Google Drive"

        except Exception as e:
            logger.error(f"Error disabling feature: {e}")
            return False, f"Error disabling feature: {str(e)}"
    
    def get_feature_status(self, feature_name: str) -> Dict:
        """Get detailed status of a feature"""
        try:
            df = self._load_from_drive()

            # Find the feature in the DataFrame
            feature_row = df[df['feature_name'] == feature_name]

            if feature_row.empty:
                return {'exists': False}

            row = feature_row.iloc[0]
            return {
                'exists': True,
                'name': row['feature_display_name'],
                'commands': row['commands'].split(', ') if isinstance(row['commands'], str) else [row['commands']],
                'enabled': bool(row['enabled']),
                'disabled_reason': row['disabled_reason'] if pd.notna(row['disabled_reason']) else '',
                'disabled_by_admin_id': row['disabled_by_admin_id'] if pd.notna(row['disabled_by_admin_id']) else '',
                'disabled_date': row['disabled_date'] if pd.notna(row['disabled_date']) else '',
                'last_modified': row['last_modified'] if pd.notna(row['last_modified']) else ''
            }

        except Exception as e:
            logger.error(f"Error getting feature status: {e}")
            return {'exists': False, 'error': str(e)}

    def get_all_features_status(self) -> Dict:
        """Get status of all features"""
        try:
            df = self._load_from_drive()
            status = {}

            for _, row in df.iterrows():
                feature_name = row['feature_name']
                status[feature_name] = {
                    'exists': True,
                    'name': row['feature_display_name'],
                    'commands': row['commands'].split(', ') if isinstance(row['commands'], str) else [row['commands']],
                    'enabled': bool(row['enabled']),
                    'disabled_reason': row['disabled_reason'] if pd.notna(row['disabled_reason']) else '',
                    'disabled_by_admin_id': row['disabled_by_admin_id'] if pd.notna(row['disabled_by_admin_id']) else '',
                    'disabled_date': row['disabled_date'] if pd.notna(row['disabled_date']) else '',
                    'last_modified': row['last_modified'] if pd.notna(row['last_modified']) else ''
                }

            return status

        except Exception as e:
            logger.error(f"Error getting all features status: {e}")
            return {}

    def get_disabled_message(self, feature_name: str) -> str:
        """Get user-friendly message for disabled feature"""
        if self.is_feature_enabled(feature_name):
            return None

        feature_info = self.get_feature_status(feature_name)
        if not feature_info.get('exists', False):
            return None

        feature_display_name = feature_info.get('name', feature_name.title())
        reason = feature_info.get('disabled_reason', 'Disabled by administrator')

        return (
            f"🚫 **{feature_display_name} Disabled**\n\n"
            f"This feature has been temporarily disabled.\n\n"
            f"**Reason:** {reason}\n\n"
            f"**What you can do:**\n"
            f"• Contact the administrator to request access\n"
            f"• Use other available bot features\n"
            f"• Check back later - features may be re-enabled\n\n"
            f"Type /help to see available commands."
        )

    def get_available_features(self) -> List[str]:
        """Get list of available feature names"""
        try:
            df = self._load_from_drive()
            return df['feature_name'].tolist()
        except Exception as e:
            logger.error(f"Error getting available features: {e}")
            return list(self.default_features.keys())

# Global instance (lazy initialization to avoid startup errors)
_feature_controller = None

def get_feature_controller():
    """Get or create the global feature controller instance"""
    global _feature_controller
    if _feature_controller is None:
        try:
            _feature_controller = FeatureController()
        except Exception as e:
            logger.error(f"Failed to initialize feature controller: {e}")
            # Return a dummy controller that always allows features
            class DummyController:
                def is_feature_enabled(self, feature_name: str) -> bool:
                    return True
                def get_disabled_message(self, feature_name: str) -> Optional[str]:
                    return None
            _feature_controller = DummyController()
    return _feature_controller

def is_feature_enabled(feature_name: str) -> bool:
    """Quick function to check if feature is enabled"""
    try:
        return get_feature_controller().is_feature_enabled(feature_name)
    except Exception as e:
        logger.error(f"Error checking feature enabled status: {e}")
        return True  # Default to enabled on error

def get_disabled_message(feature_name: str) -> Optional[str]:
    """Quick function to get disabled message"""
    try:
        return get_feature_controller().get_disabled_message(feature_name)
    except Exception as e:
        logger.error(f"Error getting disabled message: {e}")
        return None  # Default to no message on error
