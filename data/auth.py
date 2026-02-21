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
                user_logger.error(f"Authentication configuration error")
                return None
        
        # Update cache
        _bot_users_cache['data'] = df
        _bot_users_cache['last_loaded'] = datetime.now()
        
        user_logger.info("✅ Authentication initialized")
        return df
    
    except Exception as e:
        user_logger.error(f"Authentication error: {str(e)[:50]}")
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
            user_logger.error("Configuration error")
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
        
        user_logger.info("✅ Authentication data saved")
        return True
    
    except Exception as e:
        user_logger.error(f"Save error: {str(e)[:50]}")
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
            user_logger.error(f"Parse error: {str(e)[:50]}")
    
    # Fallback to BOT_USERS from secrets/environment
    user_logger.info("⚠️ Using fallback authentication")
    
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
            user_logger.error(f"Parse error: {str(e)[:50]}")
    
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
            user_logger.error(f"Parse error: {str(e)[:50]}")
    
    # Return empty dict if nothing works
    user_logger.warning("⚠️ No authentication configured")
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
            user_logger.info(f"Password changed: {username}")
            return True, "✅ Password changed successfully!"
        else:
            return False, "❌ Failed to save. Please try again."
    
    except Exception as e:
        user_logger.error(f"Password change error: {str(e)[:50]}")
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
            user_logger.info(f"Added user: {username}")
            return True, f"✅ Successfully added user '{username}'."
        else:
            return False, "❌ Failed to save. Please try again."
    
    except Exception as e:
        user_logger.error(f"Add user error: {str(e)[:50]}")
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
                user_logger.error(f"Configuration error")
                return None
        
        # Update cache
        _telegram_auth_cache['data'] = df
        _telegram_auth_cache['last_loaded'] = datetime.now()
        
        user_logger.info("✅ Telegram authorization initialized")
        return df
    
    except Exception as e:
        user_logger.error(f"Authorization error: {str(e)[:50]}")
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
            user_logger.error(f"Parse error: {str(e)[:50]}")
    
    # Fallback to secrets
    user_logger.info("⚠️ Using fallback authorization")
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
        user_logger.error(f"Stats error: {str(e)[:50]}")
    
    try:
        if bot_users_df is not None:
            stats['bot_users']['total_users'] = len(bot_users_df)
            stats['bot_users']['active_users'] = len(bot_users_df[bot_users_df['is_active'] == True])
            stats['bot_users']['inactive_users'] = len(bot_users_df[bot_users_df['is_active'] == False])
    except Exception as e:
        user_logger.error(f"Stats error: {str(e)[:50]}")
    
    return stats

# ========================================
# FORGOT PASSWORD FUNCTIONALITY
# ========================================

import random
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Dictionary of Bible verses with their text
BIBLE_VERSE_PASSWORDS = {
    "John 3:16": "For God so loved the world that he gave his one and only Son, that whoever believes in him shall not perish but have eternal life.",
    "Genesis 1:1": "In the beginning God created the heavens and the earth.",
    "Psalm 23:1": "The Lord is my shepherd, I lack nothing.",
    "Proverbs 3:5": "Trust in the Lord with all your heart and lean not on your own understanding.",
    "Romans 8:28": "And we know that in all things God works for the good of those who love him, who have been called according to his purpose.",
    "Philippians 4:13": "I can do all things through Christ who strengthens me.",
    "Isaiah 41:10": "So do not fear, for I am with you; do not be dismayed, for I am your God.",
    "Jeremiah 29:11": "For I know the plans I have for you, declares the Lord, plans to prosper you and not to harm you, plans to give you hope and a future.",
    "Matthew 6:33": "But seek first his kingdom and his righteousness, and all these things will be given to you as well.",
    "John 14:6": "Jesus answered, 'I am the way and the truth and the life. No one comes to the Father except through me.'",
    "Psalm 46:1": "God is our refuge and strength, an ever-present help in trouble.",
    "Romans 12:2": "Do not conform to the pattern of this world, but be transformed by the renewing of your mind.",
    "2 Timothy 1:7": "For God has not given us a spirit of fear, but of power and of love and of a sound mind.",
    "James 1:5": "If any of you lacks wisdom, you should ask God, who gives generously to all without finding fault, and it will be given to you.",
    "1 John 4:19": "We love because he first loved us.",
    "Psalm 121:1": "I lift up my eyes to the mountains—where does my help come from?",
    "Matthew 28:20": "And surely I am with you always, to the very end of the age.",
    "Galatians 5:22": "But the fruit of the Spirit is love, joy, peace, forbearance, kindness, goodness, faithfulness.",
    "Ephesians 2:8": "For it is by grace you have been saved, through faith—and this is not from yourselves, it is the gift of God.",
    "Hebrews 11:1": "Now faith is confidence in what we hope for and assurance about what we do not see.",
    "1 Corinthians 13:13": "And now these three remain: faith, hope and love. But the greatest of these is love.",
    "Psalm 37:4": "Take delight in the Lord, and he will give you the desires of your heart.",
    "Proverbs 16:3": "Commit to the Lord whatever you do, and he will establish your plans.",
    "Isaiah 40:31": "But those who hope in the Lord will renew their strength. They will soar on wings like eagles.",
    "Romans 5:8": "But God demonstrates his own love for us in this: While we were still sinners, Christ died for us.",
    "John 1:1": "In the beginning was the Word, and the Word was with God, and the Word was God.",
    "Psalm 91:1": "Whoever dwells in the shelter of the Most High will rest in the shadow of the Almighty.",
    "Matthew 11:28": "Come to me, all you who are weary and burdened, and I will give you rest."
}

def _generate_temp_password():
    """Generate a random Bible verse-based temporary password"""
    return random.choice(list(BIBLE_VERSE_PASSWORDS.keys()))

def _get_verse_text(verse_reference: str) -> str:
    """Get the text for a Bible verse reference"""
    return BIBLE_VERSE_PASSWORDS.get(verse_reference, "")

def get_user_email(username: str) -> str:
    """
    Get email address for a user from Google Sheet.
    
    Args:
        username: Username to look up
        
    Returns:
        str: Email address or None if not found
    """
    df = load_bot_users_from_sheet()
    
    if df is None:
        return None
    
    try:
        user_row = df[df['username'] == username]
        if user_row.empty:
            return None
        
        # Check if email column exists
        if 'email' not in df.columns:
            user_logger.error("Email column not found in sheet")
            return None
        
        email = user_row.iloc[0]['email']
        return email if pd.notna(email) else None
    
    except Exception as e:
        user_logger.error(f"Error getting email: {str(e)[:50]}")
        return None

def get_username_from_email(email: str) -> str:
    """
    Get username for an email address from Google Sheet.
    Used for Google OAuth authentication.
    
    Args:
        email: Email address to look up
        
    Returns:
        str: Username or None if not found
    """
    df = load_bot_users_from_sheet()
    
    if df is None:
        return None
    
    try:
        # Check if email column exists
        if 'email' not in df.columns:
            user_logger.error("Email column not found in sheet")
            return None
        
        # Find user with matching email (case-insensitive)
        user_row = df[df['email'].str.lower() == email.lower()]
        if user_row.empty:
            return None
        
        # Check if user is active
        if 'is_active' in df.columns and not user_row.iloc[0]['is_active']:
            return None
        
        username = user_row.iloc[0]['username']
        return username if pd.notna(username) else None
    
    except Exception as e:
        user_logger.error(f"Error getting username from email: {str(e)[:50]}")
        return None

def get_all_authorized_emails() -> list:
    """
    Get all authorized email addresses from the BotUsers sheet.
    Used for Google OAuth validation.
    
    Returns:
        list: List of authorized email addresses
    """
    df = load_bot_users_from_sheet()
    
    if df is None:
        return []
    
    try:
        # Check if email column exists
        if 'email' not in df.columns:
            return []
        
        # Filter active users if is_active column exists
        if 'is_active' in df.columns:
            df = df[df['is_active'] == True]
        
        # Get all non-null emails and convert to lowercase
        emails = df['email'].dropna().str.lower().tolist()
        return emails
    
    except Exception as e:
        user_logger.error(f"Error getting authorized emails: {str(e)[:50]}")
        return []

def send_password_reset_email(to_email: str, username: str, temp_password: str) -> bool:
    """
    Send password reset email to user.
    
    Args:
        to_email: Recipient email address
        username: Username for the account
        temp_password: Temporary password
        
    Returns:
        bool: True if email sent successfully
    """
    try:
        config = get_config()
        
        # Get email configuration from secrets
        smtp_server = config.secrets.get("SMTP_SERVER", "smtp.gmail.com")
        smtp_port = config.secrets.get("SMTP_PORT", 587)
        sender_email = config.secrets.get("SENDER_EMAIL")
        sender_password = config.secrets.get("SENDER_PASSWORD")
        
        if not sender_email or not sender_password:
            user_logger.error("Email configuration missing")
            return False
        
        # Create message
        message = MIMEMultipart("alternative")
        message["Subject"] = "Choir Bot - Password Reset"
        message["From"] = sender_email
        message["To"] = to_email
        
        # Get the verse text
        verse_text = _get_verse_text(temp_password)
        
        # Create HTML content
        html = f"""
        <html>
          <body>
            <h2>🎶 Choir Bot Password Reset</h2>
            <p>Hello <strong>{username}</strong>,</p>
            <p>You requested a password reset for your Choir Bot Control Panel account.</p>
            <p>Your temporary password is:</p>
            <h3 style="color: #4CAF50; background-color: #f0f0f0; padding: 10px; display: inline-block;">
                {temp_password}
            </h3>
            <p><strong>Important:</strong></p>
            <ul>
                <li>This is a temporary password based on a Bible verse reference</li>
                <li>Please log in and change your password immediately</li>
                <li>Go to "Change Password" page after logging in</li>
            </ul>
            <div style="background-color: #f9f9f9; border-left: 4px solid #4CAF50; padding: 15px; margin: 20px 0;">
                <p style="margin: 0; color: #555;">
                    <strong>📖 Did you know what {temp_password} says?</strong><br>
                    <em>"{verse_text}"</em><br><br>
                    <strong>😊 Have a nice day!</strong>
                </p>
            </div>
            <p>If you did not request this password reset, please contact your administrator immediately.</p>
            <hr>
            <p style="color: #888; font-size: 12px;">This is an automated message from Choir Bot Control Panel.</p>
          </body>
        </html>
        """
        
        text = f"""
        Choir Bot Password Reset
        
        Hello {username},
        
        You requested a password reset for your Choir Bot Control Panel account.
        
        Your temporary password is: {temp_password}
        
        Important:
        - This is a temporary password based on a Bible verse reference
        - Please log in and change your password immediately
        - Go to "Change Password" page after logging in
        
        📖 Did you know what {temp_password} says?
        "{verse_text}"
        
        😊 Have a nice day!
        
        If you did not request this password reset, please contact your administrator immediately.
        
        ---
        This is an automated message from Choir Bot Control Panel.
        """
        
        # Attach both plain text and HTML versions
        part1 = MIMEText(text, "plain")
        part2 = MIMEText(html, "html")
        message.attach(part1)
        message.attach(part2)
        
        # Send email
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, to_email, message.as_string())
        
        user_logger.info(f"Password reset email sent: {username}")
        return True
    
    except Exception as e:
        user_logger.error(f"Email send error: {str(e)[:50]}")
        return False

def reset_password_for_user(username: str) -> tuple:
    """
    Reset user password to a random Bible verse and send email.
    
    Args:
        username: Username to reset password for
        
    Returns:
        tuple: (success: bool, message: str)
    """
    # Load user data
    df = load_bot_users_from_sheet()
    
    if df is None:
        return False, "❌ Authentication system unavailable. Please try again later."
    
    try:
        # Find user
        user_idx = df[df['username'] == username].index
        if user_idx.empty:
            return False, "❌ Username not found."
        
        user_idx = user_idx[0]
        
        # Check if user is active
        if not df.loc[user_idx, 'is_active']:
            return False, "❌ Account inactive. Contact administrator."
        
        # Get user email
        email = get_user_email(username)
        if not email:
            return False, "❌ No email address on file. Contact administrator."
        
        # Generate temporary password
        temp_password = _generate_temp_password()
        
        # Update password in sheet
        new_password_hash = _hash_password(temp_password)
        df.loc[user_idx, 'password_hash'] = new_password_hash
        df.loc[user_idx, 'last_updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Save to sheet
        if not save_bot_users_to_sheet(df):
            return False, "❌ Failed to reset password. Please try again."
        
        # Send email
        if send_password_reset_email(email, username, temp_password):
            user_logger.info(f"Password reset: {username}")
            return True, f"✅ Password reset successful! Check your email at {email[:3]}***@{email.split('@')[1] if '@' in email else '***'}"
        else:
            return False, "❌ Password updated but failed to send email. Please contact administrator."
    
    except Exception as e:
        user_logger.error(f"Password reset error: {str(e)[:50]}")
        return False, "❌ An error occurred. Please try again later."
