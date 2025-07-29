# data/udb.py
# User database management functions for Google Drive/Sheets

import pandas as pd
import io
import os
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.errors import HttpError
from data.drive import get_drive_service
from config import get_config
from datetime import datetime
import logging

# Global user database variable
user_db = None

def load_user_database():
    """
    Downloads and loads the user database from Google Drive.
    Updates the global user_db variable.
    Returns the loaded DataFrame.
    """
    global user_db
    config = get_config()
    drive_service = get_drive_service()
    
    try:
        if not config.U_DATABASE:
            print("❌ U_DATABASE file ID not found in secrets")
            return create_empty_user_database()
        
        print(f"Loading user database from Google Drive (ID: {config.U_DATABASE})")
        
        # Download the Excel file from Google Drive
        request = drive_service.files().export_media(
            fileId=config.U_DATABASE,
            mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        file_data = io.BytesIO()
        downloader = MediaIoBaseDownload(file_data, request)
        
        done = False
        while not done:
            _, done = downloader.next_chunk()
        
        file_data.seek(0)
        
        # Read the Excel file
        try:
            user_db = pd.read_excel(file_data)
            print(f"✅ Successfully loaded user database with {len(user_db)} records")
        except Exception as e:
            print(f"❌ Error reading Excel file: {e}")
            user_db = create_empty_user_database()
        
        # Ensure required columns exist
        user_db = ensure_user_database_structure(user_db)
        
        return user_db
        
    except HttpError as e:
        print(f"❌ Google Drive API error loading user database: {e}")
        user_db = create_empty_user_database()
        return user_db
    except Exception as e:
        print(f"❌ Error loading user database: {e}")
        user_db = create_empty_user_database()
        return user_db

def create_empty_user_database():
    """
    Creates an empty user database DataFrame with the required structure.
    Matches your existing Excel sheet: user_id, username, name
    """
    return pd.DataFrame(columns=[
        'user_id',           # Telegram user ID (unique identifier)
        'username',          # Telegram username (@username)
        'name',              # User's display name
        'last_seen',         # Date of last interaction
        'is_authorized',     # Whether user is in authorized list
        'is_admin',          # Whether user is admin
        'status',            # User status (active, blocked, etc.)
        'notes'              # Admin notes about user
    ])

def ensure_user_database_structure(df):
    """
    Ensures the user database has all required columns with proper data types.
    Preserves existing columns: user_id, username, name
    """
    required_columns = {
        'user_id': 'int64',
        'username': 'object',
        'name': 'object',
        'last_seen': 'object',
        'is_authorized': 'bool',
        'is_admin': 'bool',
        'status': 'object',
        'notes': 'object'
    }
    
    # Add missing columns with default values
    for col, dtype in required_columns.items():
        if col not in df.columns:
            if dtype == 'int64':
                df[col] = 0
            elif dtype == 'bool':
                df[col] = False
            else:
                df[col] = ''
    
    # Set default values for existing but empty columns
    df['is_authorized'] = df['is_authorized'].fillna(False).astype('bool')
    df['is_admin'] = df['is_admin'].fillna(False).astype('bool')
    df['status'] = df['status'].fillna('active')
    df['notes'] = df['notes'].fillna('')
    
    return df

def get_user_database():
    """
    Returns the current user database. Loads it if not already loaded.
    """
    global user_db
    if user_db is None:
        user_db = load_user_database()
    return user_db

def get_user_by_id(user_id):
    """
    Retrieves a user record by Telegram user ID.
    Returns the user record as a pandas Series, or None if not found.
    """
    db = get_user_database()
    user_records = db[db['user_id'] == user_id]
    
    if not user_records.empty:
        return user_records.iloc[0]
    return None

def user_exists(user_id):
    """
    Checks if a user exists in the database.
    """
    return get_user_by_id(user_id) is not None

def add_or_update_user(user_data):
    """
    Adds a new user or updates an existing user in the database.
    
    Args:
        user_data (dict): Dictionary containing user information
    
    Returns:
        bool: True if successful, False otherwise
    """
    global user_db
    db = get_user_database()
    
    try:
        user_id = user_data['user_id']
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Check if user exists
        existing_user_idx = db[db['user_id'] == user_id].index
        
        if not existing_user_idx.empty:
            # Update existing user
            idx = existing_user_idx[0]
            
            # Update fields that might change
            db.at[idx, 'username'] = user_data.get('username', db.at[idx, 'username'])
            db.at[idx, 'name'] = user_data.get('name', db.at[idx, 'name'])
            db.at[idx, 'last_seen'] = current_time
            
            print(f"✅ Updated user {user_id} in database")
            
        else:
            # Add new user
            config = get_config()
            new_user = {
                'user_id': user_id,
                'username': user_data.get('username', ''),
                'name': user_data.get('name', ''),
                'last_seen': current_time,
                'is_authorized': user_id in config.AUTHORIZED_USERS,
                'is_admin': user_id == config.ADMIN_ID,
                'status': 'active',
                'notes': ''
            }
            
            # Add new row to database
            user_db = pd.concat([db, pd.DataFrame([new_user])], ignore_index=True)
            print(f"✅ Added new user {user_id} to database")
        
        return True
        
    except Exception as e:
        print(f"❌ Error adding/updating user {user_data.get('user_id', 'unknown')}: {e}")
        return False

def get_user_stats():
    """
    Returns basic statistics about the user database.
    """
    db = get_user_database()
    
    if db.empty:
        return {
            'total_users': 0,
            'authorized_users': 0,
            'admin_users': 0,
            'active_users': 0
        }
    
    return {
        'total_users': len(db),
        'authorized_users': len(db[db['is_authorized'] == True]),
        'admin_users': len(db[db['is_admin'] == True]),
        'active_users': len(db[db['status'] == 'active'])
    }

def track_user_interaction(telegram_user):
    """
    Helper function to track user interactions from Telegram updates.
    
    Args:
        telegram_user: Telegram User object from update.effective_user
    
    Returns:
        bool: True if tracking was successful
    """
    try:
        # Extract user information from Telegram User object
        user_data = {
            'user_id': telegram_user.id,
            'username': telegram_user.username or '',
            'name': telegram_user.full_name or f"{telegram_user.first_name or ''} {telegram_user.last_name or ''}".strip(),
        }
        
        # Add or update user in database
        return add_or_update_user(user_data)
        
    except Exception as e:
        print(f"❌ Error tracking user interaction: {e}")
        return False

def get_user_summary(user_id):
    """
    Get a formatted summary of a user's information.
    
    Args:
        user_id: Telegram user ID
    
    Returns:
        str: Formatted user summary or error message
    """
    try:
        user = get_user_by_id(user_id)
        if user is None:
            return f"❌ User {user_id} not found in database"
        
        summary = f"""
👤 **User Information**
• **ID:** {user['user_id']}
• **Username:** @{user['username'] if user['username'] else 'Not set'}
• **Name:** {user['name']}
• **Last Seen:** {user.get('last_seen', 'Unknown')}
• **Authorized:** {'✅ Yes' if user.get('is_authorized', False) else '❌ No'}
• **Admin:** {'✅ Yes' if user.get('is_admin', False) else '❌ No'}
• **Status:** {user.get('status', 'Unknown')}
"""
        if user.get('notes'):
            summary += f"• **Notes:** {user['notes']}\n"
        
        return summary.strip()
        
    except Exception as e:
        return f"❌ Error getting user summary: {e}"

def update_google_sheet_structure():
    """
    Updates the Google Sheet to include all required columns.
    This will add missing columns to your existing sheet.
    """
    try:
        from googleapiclient.discovery import build
        from google.oauth2 import service_account
        import tempfile
        import json
        
        config = get_config()
        
        # Setup Google Sheets API
        tmp_dir = tempfile.gettempdir()
        key_path = os.path.join(tmp_dir, "service_account.json")
        with open(key_path, "w") as f:
            json.dump(config.service_account_data, f)
        
        creds = service_account.Credentials.from_service_account_file(
            key_path, scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        sheets_service = build("sheets", "v4", credentials=creds)
        
        # Get current sheet data
        sheet = sheets_service.spreadsheets()
        result = sheet.values().get(
            spreadsheetId=config.U_DATABASE,
            range="A1:Z1"  # Get first row to check current headers
        ).execute()
        
        current_headers = result.get('values', [[]])[0] if result.get('values') else []
        print(f"Current headers: {current_headers}")
        
        # Define required headers
        required_headers = [
            'user_id', 'username', 'name', 'last_seen', 
            'is_authorized', 'is_admin', 'status', 'notes'
        ]
        
        # Check which headers are missing
        missing_headers = [h for h in required_headers if h not in current_headers]
        
        if not missing_headers:
            print("✅ All required columns already exist in the sheet")
            return True
        
        print(f"Missing headers: {missing_headers}")
        
        # Update headers row
        new_headers = current_headers + missing_headers
        
        # Clear and update the first row
        sheet.values().update(
            spreadsheetId=config.U_DATABASE,
            range="A1:Z1",
            valueInputOption="RAW",
            body={"values": [new_headers]}
        ).execute()
        
        print(f"✅ Successfully added columns: {missing_headers}")
        print(f"✅ Sheet now has headers: {new_headers}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error updating Google Sheet structure: {e}")
        return False

def save_user_database():
    """
    Saves the current user database back to Google Drive.
    This function will be implemented based on your requirements.
    """
    # TODO: Implement saving functionality
    # This will require uploading the DataFrame back to Google Drive
    print("💾 Save user database functionality - to be implemented")
    pass
