# data/auth.py
# Google Sheet-based authentication with fallback to secrets
# Supports both:
# 1. Telegram user authorization (user_id based)
# 2. Bot/Streamlit control panel authentication (username/password based)

import pandas as pd
import io
import hashlib
import streamlit as st
import json
import os
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
from data.drive import get_drive_service
from config import get_config
from logging_utils import setup_loggers
from datetime import datetime

bot_logger, user_logger = setup_loggers()

# Cache for Telegram user auth data
_telegram_auth_cache = {
    'data': None,
    'last_loaded': None,
    'cache_duration': 300  # Cache for 5 minutes
}

# Cache for bot users (Streamlit control panel)
_bot_users_cache = {
    'data': None,
    'last_loaded': None,
    'cache_duration': 300  # Cache for 5 minutes
}

def _hash_password(password: str) -> str:
    """
    Hash a password using SHA256.
    
    Args:
        password: Plain text password
        
    Returns:
        Hashed password string
    """
    return hashlib.sha256(password.encode()).hexdigest()

def _check_cache_validity(cache_dict):
    """Check if cached data is still valid"""
    if cache_dict['data'] is None or cache_dict['last_loaded'] is None:
        return False
    
    from datetime import datetime, timedelta
    time_since_load = (datetime.now() - cache_dict['last_loaded']).total_seconds()
    return time_since_load < cache_dict['cache_duration']


# ========================================
# BOT USERS (Streamlit Control Panel) 
# ========================================

def load_bot_users_from_sheet():
    """
    Load bot users (for Streamlit control panel) from Google Sheet.
    Expected columns: username, password_hash, is_active, last_updated
    
    Returns:
        DataFrame with bot user data or None if failed
    """
    try:
        config = get_config()
        bot_auth_sheet_id = config.secrets.get("BOT_AUTH_SHEET_ID")
        
        if not bot_auth_sheet_id:
            return None
        
        drive_service = get_drive_service()
        
        # Download the Excel file
        request = drive_service.files().export_media(
            fileId=bot_auth_sheet_id,
            mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        file_data = io.BytesIO()
        downloader = MediaIoBaseDownload(file_data, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        file_data.seek(0)
        
        # Read the Excel file
        df = pd.read_excel(file_data, sheet_name='BotUsers')
        
        # Ensure required columns exist
        required_columns = ['username', 'password_hash', 'is_active']
        for col in required_columns:
            if col not in df.columns:
                bot_logger.error(f"Authentication configuration error")
                return None
        
        # Update cache
        _bot_users_cache['data'] = df
        _bot_users_cache['last_loaded'] = datetime.now()
        
        bot_logger.info("✅ Authentication initialized")
        return df
    
    except Exception as e:
        bot_logger.error(f"Authentication error: {str(e)[:50]}")
        return None

def save_bot_users_to_sheet(df):
    """
    Save bot user data back to Google Sheet.
    
    Args:
        df: DataFrame with bot user data
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        config = get_config()
        bot_auth_sheet_id = config.secrets.get("BOT_AUTH_SHEET_ID")
        
        if not bot_auth_sheet_id:
            bot_logger.error("Configuration error")
            return False
        
        drive_service = get_drive_service()
        
        # Convert DataFrame to Excel
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='BotUsers')
        output.seek(0)
        
        # Upload the file
        media = MediaIoBaseUpload(
            output, 
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            resumable=True
        )
        
        drive_service.files().update(
            fileId=bot_auth_sheet_id,
            media_body=media
        ).execute()
        
        # Update cache
        _bot_users_cache['data'] = df
        _bot_users_cache['last_loaded'] = datetime.now()
        
        bot_logger.info("✅ Authentication data saved")
        return True
    
    except Exception as e:
        bot_logger.error(f"Save error: {str(e)[:50]}")
        return False

def get_bot_users():
    """
    Get bot users for Streamlit control panel.
    Tries Google Sheet first, falls back to BOT_USERS in secrets (JSON format).
    
    Returns:
        dict: Dictionary of {username: password} pairs
    """
    # Check cache first
    if _check_cache_validity(_bot_users_cache):
        df = _bot_users_cache['data']
        if df is not None:
            active_users = df[df['is_active'] == True]
            return dict(zip(active_users['username'], active_users['password_hash']))
    
    # Try to load from Google Sheet
    df = load_bot_users_from_sheet()
    if df is not None:
        try:
            active_users = df[df['is_active'] == True]
            # Return dict of username: password_hash
            return dict(zip(active_users['username'], active_users['password_hash']))
        except Exception as e:
            bot_logger.error(f"Parse error: {str(e)[:50]}")
    
    # Fallback to BOT_USERS from secrets/environment
    bot_logger.info("⚠️ Using fallback authentication")
    
    # Try environment variable first
    bot_users_json = os.getenv("BOT_USERS")
    if bot_users_json:
        try:
            users_dict = json.loads(bot_users_json)
            # Hash the passwords if they're not already hashed (check length)
            for username, password in users_dict.items():
                if len(password) != 64:  # SHA256 hash is 64 characters
                    users_dict[username] = _hash_password(password)
            return users_dict
        except json.JSONDecodeError as e:
            bot_logger.error(f"Parse error: {str(e)[:50]}")
    
    # Try secrets.toml
    config = get_config()
    bot_users_str = config.secrets.get("BOT_USERS")
    if bot_users_str:
        try:
            users_dict = json.loads(bot_users_str)
            # Hash the passwords if they're not already hashed
            for username, password in users_dict.items():
                if len(password) != 64:  # SHA256 hash is 64 characters
                    users_dict[username] = _hash_password(password)
            return users_dict
        except json.JSONDecodeError as e:
            bot_logger.error(f"Parse error: {str(e)[:50]}")
    
    # Return empty dict if nothing works
    bot_logger.warning("⚠️ No authentication configured")
    return {}

def verify_bot_user(username: str, password: str) -> bool:
    """
    Verify a bot user's credentials (for Streamlit control panel).
    
    Args:
        username: Bot user username
        password: Plain text password to verify
        
    Returns:
        bool: True if credentials are correct and user is active
    """
    bot_users = get_bot_users()
    
    if username not in bot_users:
        return False
    
    stored_hash = bot_users[username]
    password_hash = _hash_password(password)
    
    return password_hash == stored_hash

def change_bot_user_password(username: str, old_password: str, new_password: str) -> tuple:
    """
    Change a bot user's password.
    
    Args:
        username: Bot user username
        old_password: Current password (for verification)
        new_password: New password to set
        
    Returns:
        tuple: (success: bool, message: str)
    """
    # Load current bot user data
    df = load_bot_users_from_sheet()
    
    if df is None:
        return False, "❌ Authentication system unavailable. Please try again later."
    
    try:
        # Find user
        user_idx = df[df['username'] == username].index
        if user_idx.empty:
            return False, "❌ User not found."
        
        user_idx = user_idx[0]
        
        # Verify old password
        stored_hash = df.loc[user_idx, 'password_hash']
        old_password_hash = _hash_password(old_password)
        
        if stored_hash != old_password_hash:
            return False, "❌ Current password is incorrect."
        
        # Check if user is active
        if not df.loc[user_idx, 'is_active']:
            return False, "❌ Account inactive. Contact administrator."
        
        # Validate new password
        if len(new_password) < 6:
            return False, "❌ New password must be at least 6 characters long."
        
        if new_password == old_password:
            return False, "❌ New password must be different from the current password."
        
        # Update password
        new_password_hash = _hash_password(new_password)
        df.loc[user_idx, 'password_hash'] = new_password_hash
        df.loc[user_idx, 'last_updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Save to sheet
        if save_bot_users_to_sheet(df):
            bot_logger.info(f"Password changed: {username}")
            return True, "✅ Password changed successfully!"
        else:
            return False, "❌ Failed to save. Please try again."
    
    except Exception as e:
        bot_logger.error(f"Password change error: {str(e)[:50]}")
        return False, "❌ An error occurred. Please try again later."

def add_bot_user(username: str, initial_password: str, is_active: bool = True) -> tuple:
    """
    Add a new bot user to the authentication system.
    
    Args:
        username: Bot username
        initial_password: Initial password (will be hashed)
        is_active: Whether user should be active
        
    Returns:
        tuple: (success: bool, message: str)
    """
    df = load_bot_users_from_sheet()
    
    if df is None:
        # Create new DataFrame if sheet doesn't exist
        df = pd.DataFrame(columns=['username', 'password_hash', 'is_active', 'created_at', 'last_updated'])
    
    try:
        # Check if user already exists
        if username in df['username'].values:
            return False, f"❌ User '{username}' already exists."
        
        # Create new user entry
        new_user = {
            'username': username,
            'password_hash': _hash_password(initial_password),
            'is_active': is_active,
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        # Add to DataFrame
        df = pd.concat([df, pd.DataFrame([new_user])], ignore_index=True)
        
        # Save to sheet
        if save_bot_users_to_sheet(df):
            bot_logger.info(f"Added user: {username}")
            return True, f"✅ Successfully added user '{username}'."
        else:
            return False, "❌ Failed to save. Please try again."
    
    except Exception as e:
        bot_logger.error(f"Add user error: {str(e)[:50]}")
        return False, "❌ An error occurred. Please try again later."


# ========================================
# TELEGRAM USER AUTHORIZATION
# ========================================

def load_telegram_auth_from_sheet():
    """
    Load Telegram user authorization from Google Sheet.
    Expected columns: user_id, username, is_active
    
    Returns:
        DataFrame with auth data or None if failed
    """
    try:
        config = get_config()
        telegram_auth_sheet_id = config.secrets.get("TELEGRAM_AUTH_SHEET_ID")
        
        if not telegram_auth_sheet_id:
            return None
        
        drive_service = get_drive_service()
        
        # Download the Excel file
        request = drive_service.files().export_media(
            fileId=telegram_auth_sheet_id,
            mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        file_data = io.BytesIO()
        downloader = MediaIoBaseDownload(file_data, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        file_data.seek(0)
        
        # Read the Excel file
        df = pd.read_excel(file_data, sheet_name='TelegramUsers')
        
        # Ensure required columns exist
        required_columns = ['user_id', 'is_active']
        for col in required_columns:
            if col not in df.columns:
                bot_logger.error(f"Configuration error")
                return None
        
        # Update cache
        _telegram_auth_cache['data'] = df
        _telegram_auth_cache['last_loaded'] = datetime.now()
        
        bot_logger.info("✅ Telegram authorization initialized")
        return df
    
    except Exception as e:
        bot_logger.error(f"Authorization error: {str(e)[:50]}")
        return None

def get_authorized_users():
    """
    Get list of authorized Telegram user IDs.
    Tries Google Sheet first, falls back to AUTHORIZED_USERS in secrets.
    
    Returns:
        list: List of authorized user IDs
    """
    # Check cache first
    if _check_cache_validity(_telegram_auth_cache):
        df = _telegram_auth_cache['data']
        if df is not None:
            active_users = df[df['is_active'] == True]['user_id'].tolist()
            return [int(uid) for uid in active_users]
    
    # Try to load from Google Sheet
    df = load_telegram_auth_from_sheet()
    if df is not None:
        try:
            active_users = df[df['is_active'] == True]['user_id'].tolist()
            return [int(uid) for uid in active_users]
        except Exception as e:
            bot_logger.error(f"Parse error: {str(e)[:50]}")
    
    # Fallback to secrets
    bot_logger.info("⚠️ Using fallback authorization")
    config = get_config()
    return config.AUTHORIZED_USERS

def refresh_auth_cache():
    """Force refresh of all auth caches"""
    global _telegram_auth_cache, _bot_users_cache
    _telegram_auth_cache['data'] = None
    _telegram_auth_cache['last_loaded'] = None
    _bot_users_cache['data'] = None
    _bot_users_cache['last_loaded'] = None
    
    # Try to load both
    telegram_success = load_telegram_auth_from_sheet() is not None
    bot_users_success = load_bot_users_from_sheet() is not None
    
    return telegram_success or bot_users_success

def get_auth_stats():
    """
    Get statistics about both authentication systems.
    
    Returns:
        dict: Statistics about users
    """
    telegram_df = load_telegram_auth_from_sheet()
    bot_users_df = load_bot_users_from_sheet()
    
    stats = {
        'telegram_auth': {
            'using_sheet': telegram_df is not None,
            'total_users': 0,
            'active_users': 0,
            'inactive_users': 0
        },
        'bot_users': {
            'using_sheet': bot_users_df is not None,
            'total_users': 0,
            'active_users': 0,
            'inactive_users': 0
        }
    }
    
    try:
        if telegram_df is not None:
            stats['telegram_auth']['total_users'] = len(telegram_df)
            stats['telegram_auth']['active_users'] = len(telegram_df[telegram_df['is_active'] == True])
            stats['telegram_auth']['inactive_users'] = len(telegram_df[telegram_df['is_active'] == False])
    except Exception as e:
        bot_logger.error(f"Stats error: {str(e)[:50]}")
    
    try:
        if bot_users_df is not None:
            stats['bot_users']['total_users'] = len(bot_users_df)
            stats['bot_users']['active_users'] = len(bot_users_df[bot_users_df['is_active'] == True])
            stats['bot_users']['inactive_users'] = len(bot_users_df[bot_users_df['is_active'] == False])
    except Exception as e:
        bot_logger.error(f"Stats error: {str(e)[:50]}")
    
    return stats
