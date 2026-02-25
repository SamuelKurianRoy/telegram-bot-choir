#!/usr/bin/env python3
"""
AI Model Assignment Configuration
Manages which AI models are assigned to different user types
"""

import pandas as pd
import logging
import streamlit as st
from typing import Dict, Optional, Tuple
from datetime import datetime
import io
from data.drive import get_drive_service
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload

logger = logging.getLogger(__name__)

class AIModelConfig:
    """Manages AI model assignments for different user types"""

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

        # Default model assignments
        self.default_assignments = {
            'admin': 'gemini',        # Admins get Gemini (best, paid)
            'authorized': 'groq',     # Authorized users get Groq (good, free)
            'normal': 'sarvam'        # Normal users get Sarvam (basic, indian AI)
        }
        
        # Available models
        self.available_models = {
            'gemini': {
                'name': 'Google Gemini',
                'description': 'Advanced AI with best understanding',
                'cost': 'Paid (primary)',
                'quality': 'Excellent'
            },
            'groq': {
                'name': 'Groq (Llama)',
                'description': 'Fast and capable free AI',
                'cost': 'Free',
                'quality': 'Very Good'
            },
            'sarvam': {
                'name': 'Sarvam AI',
                'description': 'Indian AI with Hindi support',
                'cost': 'Free',
                'quality': 'Good'
            }
        }
    
    def _load_from_drive(self) -> pd.DataFrame:
        """Load AI model configuration from Google Drive Excel sheet"""
        try:
            # Check cache first
            if self._cache is not None and self._cache_timestamp is not None:
                cache_age = (datetime.now() - self._cache_timestamp).total_seconds()
                if cache_age < self.cache_timeout:
                    logger.debug("Using cached AI model config data")
                    return self._cache

            logger.info("Loading AI model configuration from Google Drive...")

            # Download from Google Drive
            request = self.drive_service.files().export_media(
                fileId=self.disabled_db_id,
                mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            file_data = io.BytesIO()
            downloader = MediaIoBaseDownload(file_data, request)

            done = False
            while not done:
                status, done = downloader.next_chunk()

            file_data.seek(0)
            df_dict = pd.read_excel(file_data, sheet_name=None)  # Read all sheets

            # Get AIModelConfig sheet if it exists
            if 'AIModelConfig' in df_dict:
                df = df_dict['AIModelConfig']
                logger.info(f"Successfully loaded AI model config with {len(df)} assignments")
            else:
                # Create default if sheet doesn't exist
                logger.info("AIModelConfig sheet not found, creating default")
                df = self._create_default_dataframe()

            # Update cache
            self._cache = df
            self._cache_timestamp = datetime.now()

            return df

        except Exception as e:
            logger.error(f"Error loading AI model config from Google Drive: {e}")
            # Return default assignments as DataFrame
            return self._create_default_dataframe()

    def _save_to_drive(self, df: pd.DataFrame) -> bool:
        """Save AI model configuration to Google Drive Excel sheet"""
        try:
            logger.info("Saving AI model configuration to Google Drive...")

            # First, load all existing sheets
            request = self.drive_service.files().export_media(
                fileId=self.disabled_db_id,
                mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            file_data = io.BytesIO()
            downloader = MediaIoBaseDownload(file_data, request)

            done = False
            while not done:
                status, done = downloader.next_chunk()

            file_data.seek(0)
            existing_sheets = pd.read_excel(file_data, sheet_name=None)

            # Update the AIModelConfig sheet
            existing_sheets['AIModelConfig'] = df

            # Write all sheets back
            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                for sheet_name, sheet_df in existing_sheets.items():
                    sheet_df.to_excel(writer, sheet_name=sheet_name, index=False)
            excel_buffer.seek(0)

            # Upload to Google Drive
            media = MediaIoBaseUpload(
                excel_buffer,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )

            # Update the existing file
            self.drive_service.files().update(
                fileId=self.disabled_db_id,
                media_body=media
            ).execute()

            # Update cache
            self._cache = df
            self._cache_timestamp = datetime.now()

            logger.info("Successfully saved AI model configuration to Google Drive")
            return True

        except Exception as e:
            logger.error(f"Error saving AI model config to Google Drive: {e}")
            return False

    def _create_default_dataframe(self) -> pd.DataFrame:
        """Create default DataFrame structure for AI model assignments"""
        data = []
        for user_type, model in self.default_assignments.items():
            data.append({
                'user_type': user_type,
                'assigned_model': model,
                'last_modified': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'modified_by_admin_id': '',
                'notes': f'Default assignment for {user_type} users'
            })

        return pd.DataFrame(data)
    
    def get_model_for_user_type(self, user_type: str) -> str:
        """Get the assigned AI model for a user type
        
        Args:
            user_type: 'admin', 'authorized', or 'normal'
            
        Returns:
            Model name: 'gemini', 'groq', or 'sarvam'
        """
        try:
            df = self._load_from_drive()

            # Find the user type in the DataFrame
            user_type_row = df[df['user_type'] == user_type]

            if user_type_row.empty:
                logger.warning(f"User type '{user_type}' not found, using default")
                return self.default_assignments.get(user_type, 'sarvam')

            return str(user_type_row.iloc[0]['assigned_model'])

        except Exception as e:
            logger.error(f"Error getting model for user type: {e}")
            return self.default_assignments.get(user_type, 'sarvam')
    
    def set_model_for_user_type(self, user_type: str, model: str, admin_id: int) -> Tuple[bool, str]:
        """Set the AI model for a user type
        
        Args:
            user_type: 'admin', 'authorized', or 'normal'
            model: 'gemini', 'groq', or 'sarvam'
            admin_id: ID of the admin making the change
            
        Returns:
            (success: bool, message: str)
        """
        try:
            # Validate inputs
            if user_type not in ['admin', 'authorized', 'normal']:
                return False, f"Invalid user type: {user_type}. Must be 'admin', 'authorized', or 'normal'"
            
            if model not in ['gemini', 'groq', 'sarvam']:
                return False, f"Invalid model: {model}. Must be 'gemini', 'groq', or 'sarvam'"

            df = self._load_from_drive()

            # Find the user type in the DataFrame
            user_type_idx = df[df['user_type'] == user_type].index

            if user_type_idx.empty:
                # Add new row if user type doesn't exist
                new_row = pd.DataFrame([{
                    'user_type': user_type,
                    'assigned_model': model,
                    'last_modified': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'modified_by_admin_id': str(admin_id),
                    'notes': f'Assigned by admin {admin_id}'
                }])
                df = pd.concat([df, new_row], ignore_index=True)
            else:
                # Update existing row
                idx = user_type_idx[0]
                df.loc[idx, 'assigned_model'] = model
                df.loc[idx, 'last_modified'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                df.loc[idx, 'modified_by_admin_id'] = str(admin_id)
                df.loc[idx, 'notes'] = f'Changed to {model} by admin {admin_id}'

            # Save to Google Drive
            if self._save_to_drive(df):
                model_info = self.available_models.get(model, {})
                model_name = model_info.get('name', model)
                return True, f"✅ {user_type.title()} users will now use **{model_name}**"
            else:
                return False, "Failed to save configuration to Google Drive"

        except Exception as e:
            logger.error(f"Error setting model for user type: {e}")
            return False, f"Error: {str(e)}"
    
    def get_all_assignments(self) -> Dict:
        """Get all current model assignments"""
        try:
            df = self._load_from_drive()
            assignments = {}

            for _, row in df.iterrows():
                user_type = row['user_type']
                assignments[user_type] = {
                    'model': row['assigned_model'],
                    'last_modified': row.get('last_modified', ''),
                    'modified_by': row.get('modified_by_admin_id', ''),
                    'notes': row.get('notes', '')
                }

            # Ensure all user types are present
            for user_type in ['admin', 'authorized', 'normal']:
                if user_type not in assignments:
                    assignments[user_type] = {
                        'model': self.default_assignments[user_type],
                        'last_modified': 'Default',
                        'modified_by': 'System',
                        'notes': 'Default assignment'
                    }

            return assignments

        except Exception as e:
            logger.error(f"Error getting all assignments: {e}")
            return {
                user_type: {
                    'model': model,
                    'last_modified': 'Default',
                    'modified_by': 'System',
                    'notes': 'Default assignment'
                }
                for user_type, model in self.default_assignments.items()
            }
    
    def get_model_info(self, model: str) -> Dict:
        """Get information about a specific AI model"""
        return self.available_models.get(model, {
            'name': model,
            'description': 'Unknown model',
            'cost': 'Unknown',
            'quality': 'Unknown'
        })


# Global instance
_ai_model_config = None

def get_ai_model_config() -> AIModelConfig:
    """Get or create the global AI model config instance"""
    global _ai_model_config
    if _ai_model_config is None:
        try:
            _ai_model_config = AIModelConfig()
        except Exception as e:
            logger.error(f"Failed to initialize AI model config: {e}")
            # Return a dummy config that uses defaults
            class DummyConfig:
                def get_model_for_user_type(self, user_type: str) -> str:
                    defaults = {'admin': 'gemini', 'authorized': 'groq', 'normal': 'sarvam'}
                    return defaults.get(user_type, 'sarvam')
            _ai_model_config = DummyConfig()
    return _ai_model_config

def get_model_for_user(user_id: int) -> str:
    """Get the AI model that should be used for a specific user
    
    Args:
        user_id: Telegram user ID
        
    Returns:
        Model name: 'gemini', 'groq', or 'sarvam'
    """
    try:
        from data.udb import is_admin, is_user_authorized
        
        config = get_ai_model_config()
        
        # Determine user type
        if is_admin(user_id):
            user_type = 'admin'
        elif is_user_authorized(user_id):
            user_type = 'authorized'
        else:
            user_type = 'normal'
        
        model = config.get_model_for_user_type(user_type)
        logger.info(f"User {user_id} ({user_type}) will use {model}")
        return model
        
    except Exception as e:
        logger.error(f"Error getting model for user {user_id}: {e}")
        return 'sarvam'  # Default to most restrictive
