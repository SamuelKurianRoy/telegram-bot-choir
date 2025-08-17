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
pending_saves = False  # Flag to track if there are unsaved changes

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
        
        # print(f"Loading user database from Google Drive (ID: {config.U_DATABASE})")
        
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
        'notes',             # Admin notes about user
        # User Preferences
        'bible_language',    # Default Bible language (malayalam/english)
        'game_language',     # Default Bible game language (malayalam/english)
        'search_results_limit',  # Number of search results to show
        'download_preference',   # Default download behavior (single/ask)
        'download_quality',  # Default download quality (high/medium/low/ask)
        'theme_preference',  # UI theme preference (if applicable)
        'show_tunes_in_date' # Whether to show tunes in /date command results (true/false)
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
        'notes': 'object',
        # User Preferences
        'bible_language': 'object',
        'game_language': 'object',
        'search_results_limit': 'int64',
        'download_preference': 'object',
        'download_quality': 'object',
        'theme_preference': 'object',
        'show_tunes_in_date': 'bool'
    }
    
    # Add missing columns with default values
    for col, dtype in required_columns.items():
        if col not in df.columns:
            if dtype == 'int64':
                if col == 'search_results_limit':
                    df[col] = 10  # Default search results limit
                else:
                    df[col] = 0
            elif dtype == 'bool':
                if col == 'show_tunes_in_date':
                    df[col] = True  # Default to showing tunes
                else:
                    df[col] = False
            else:
                if col == 'bible_language':
                    df[col] = 'malayalam'  # Default Bible language
                elif col == 'game_language':
                    df[col] = 'english'  # Default Bible game language
                elif col == 'download_preference':
                    df[col] = 'single'  # Default download behavior (single video)
                elif col == 'download_quality':
                    df[col] = 'ask'  # Default download quality (ask every time)
                elif col == 'theme_preference':
                    df[col] = 'default'
                else:
                    df[col] = ''

    # Set default values for existing but empty columns
    df['is_authorized'] = df['is_authorized'].fillna(False).astype('bool')
    df['is_admin'] = df['is_admin'].fillna(False).astype('bool')
    df['status'] = df['status'].fillna('active')
    df['notes'] = df['notes'].fillna('')

    # Set default values for preference columns
    df['bible_language'] = df['bible_language'].fillna('malayalam')
    df['game_language'] = df['game_language'].fillna('english')
    df['search_results_limit'] = df['search_results_limit'].fillna(10).astype('int64')
    df['download_preference'] = df['download_preference'].fillna('single')
    df['download_quality'] = df['download_quality'].fillna('ask')
    df['theme_preference'] = df['theme_preference'].fillna('default')
    df['show_tunes_in_date'] = df['show_tunes_in_date'].fillna(True).astype('bool')
    
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

def mark_pending_save():
    """
    Mark that there are pending changes to save.
    """
    global pending_saves
    pending_saves = True

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

            # print(f"✅ Updated {user_id} in database")

            # Mark as needing save but don't save immediately for performance
            mark_pending_save()
            
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
                'notes': '',
                # Default preferences for new users
                'bible_language': 'malayalam',
                'game_language': 'english',
                'search_results_limit': 10,
                'download_preference': 'single',
                'download_quality': 'ask',
                'theme_preference': 'default'
            }
            
            # Add new row to database
            user_db = pd.concat([db, pd.DataFrame([new_user])], ignore_index=True)
            # print(f"✅ Added {user_id} to database")

        # Mark as needing save but don't save immediately for performance
        mark_pending_save()

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

def track_user_fast(telegram_user):
    """
    Fast user tracking that doesn't load the full database.
    Only checks if user exists and updates last_seen if needed.

    Args:
        telegram_user: Telegram User object from update.effective_user

    Returns:
        tuple: (is_new_user, tracking_success)
    """
    try:
        user_id = telegram_user.id

        # Quick check if user exists without loading full database
        existing_user = get_user_by_id(user_id)
        is_new_user = existing_user is None

        if is_new_user:
            # Only for new users, do the full tracking
            success = track_user_interaction(telegram_user)
            return (True, success)
        else:
            # For existing users, just update last_seen quickly
            global user_db
            db = get_user_database()
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Update last_seen for existing user
            user_idx = db[db['user_id'] == user_id].index
            if not user_idx.empty:
                db.at[user_idx[0], 'last_seen'] = current_time
                mark_pending_save()
                # print(f"✅ Updated {user_id}")

            return (False, True)

    except Exception as e:
        print(f"❌ Error in fast user tracking: {e}")
        return (False, False)

def save_if_pending():
    """
    Save database only if there are pending changes.
    This can be called periodically or manually.
    """
    global pending_saves
    if pending_saves:
        success = save_user_database()
        if success:
            pending_saves = False
            print("✅ Pending database changes saved")
        return success
    return True  # No changes to save

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

def get_user_preference(user_id, preference_name, default_value=None):
    """
    Get a specific preference value for a user.

    Args:
        user_id: Telegram user ID
        preference_name: Name of the preference column
        default_value: Default value if preference not found

    Returns:
        The preference value or default_value
    """
    try:
        user = get_user_by_id(user_id)
        if user is None:
            return default_value

        if preference_name in user.index:
            value = user[preference_name]
            # Handle NaN values
            if pd.isna(value):
                return default_value
            return value

        return default_value

    except Exception as e:
        print(f"❌ Error getting user preference {preference_name} for {user_id}: {e}")
        return default_value

def update_user_preference(user_id, preference_name, preference_value):
    """
    Update a specific preference for a user.

    Args:
        user_id: Telegram user ID
        preference_name: Name of the preference column
        preference_value: New preference value

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        global user_db
        db = get_user_database()

        # Find user
        user_idx = db[db['user_id'] == user_id].index
        if user_idx.empty:
            # User doesn't exist, create them first
            user_data = {'user_id': user_id}
            if not add_or_update_user(user_data):
                return False
            # Reload database and find user again
            db = get_user_database()
            user_idx = db[db['user_id'] == user_id].index

        if not user_idx.empty:
            idx = user_idx[0]
            db.at[idx, preference_name] = preference_value
            mark_pending_save()
            print(f"✅ Updated {preference_name} = {preference_value} for user {user_id}")
            return True

        return False

    except Exception as e:
        print(f"❌ Error updating user preference {preference_name} for {user_id}: {e}")
        return False

def get_user_bible_language(user_id):
    """
    Get the user's preferred Bible language.

    Args:
        user_id: Telegram user ID

    Returns:
        str: 'malayalam' or 'english' (default: 'malayalam')
    """
    return get_user_preference(user_id, 'bible_language', 'malayalam')

def update_user_bible_language(user_id, language):
    """
    Update the user's preferred Bible language.

    Args:
        user_id: Telegram user ID
        language: 'malayalam' or 'english'

    Returns:
        bool: True if successful, False otherwise
    """
    if language.lower() not in ['malayalam', 'english']:
        return False

    return update_user_preference(user_id, 'bible_language', language.lower())

def get_user_game_language(user_id):
    """
    Get the user's preferred Bible game language.

    Args:
        user_id: Telegram user ID

    Returns:
        str: 'malayalam' or 'english' (default: 'english')
    """
    return get_user_preference(user_id, 'game_language', 'english')

def update_user_game_language(user_id, language):
    """
    Update the user's preferred Bible game language.

    Args:
        user_id: Telegram user ID
        language: 'malayalam' or 'english'

    Returns:
        bool: True if successful, False otherwise
    """
    if language.lower() not in ['malayalam', 'english']:
        return False

    return update_user_preference(user_id, 'game_language', language.lower())

def get_user_download_preference(user_id):
    """
    Get the user's preferred download behavior.

    Args:
        user_id: Telegram user ID

    Returns:
        str: 'single' or 'ask' (default: 'single')
    """
    return get_user_preference(user_id, 'download_preference', 'single')

def update_user_download_preference(user_id, preference):
    """
    Update the user's preferred download behavior.

    Args:
        user_id: Telegram user ID
        preference: 'single' or 'ask'

    Returns:
        bool: True if successful, False otherwise
    """
    if preference.lower() not in ['single', 'ask']:
        return False

    return update_user_preference(user_id, 'download_preference', preference.lower())

def get_user_download_quality(user_id):
    """
    Get the user's preferred download quality.

    Args:
        user_id: Telegram user ID

    Returns:
        str: 'high', 'medium', 'low', or 'ask' (default: 'ask')
    """
    return get_user_preference(user_id, 'download_quality', 'ask')

def update_user_download_quality(user_id, quality):
    """
    Update the user's preferred download quality.

    Args:
        user_id: Telegram user ID
        quality: 'high', 'medium', 'low', or 'ask'

    Returns:
        bool: True if successful, False otherwise
    """
    if quality.lower() not in ['high', 'medium', 'low', 'ask']:
        return False

    return update_user_preference(user_id, 'download_quality', quality.lower())

def get_user_show_tunes_in_date(user_id):
    """
    Get the user's preference for showing tunes in /date command results.

    Args:
        user_id: Telegram user ID

    Returns:
        bool: True to show tunes, False to hide them (default: True)
    """
    return get_user_preference(user_id, 'show_tunes_in_date', True)

def update_user_show_tunes_in_date(user_id, show_tunes):
    """
    Update the user's preference for showing tunes in /date command results.

    Args:
        user_id: Telegram user ID
        show_tunes: True to show tunes, False to hide them

    Returns:
        bool: True if successful, False otherwise
    """
    if not isinstance(show_tunes, bool):
        return False

    return update_user_preference(user_id, 'show_tunes_in_date', show_tunes)

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
        # print(f"Current headers: {current_headers}")
        
        # Define required headers
        required_headers = [
            'user_id', 'username', 'name', 'last_seen',
            'is_authorized', 'is_admin', 'status', 'notes',
            'bible_language', 'game_language', 'search_results_limit', 'download_preference', 'download_quality', 'theme_preference', 'show_tunes_in_date'
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
        
        # print(f"✅ Successfully added columns: {missing_headers}")
        # print(f"✅ Sheet now has headers: {new_headers}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error updating Google Sheet structure: {e}")
        return False

def save_user_database():
    """
    Saves the current user database back to Google Drive/Sheets.
    Updates the Google Sheet with the current database content.
    """
    try:
        from googleapiclient.discovery import build
        from google.oauth2 import service_account
        import tempfile
        import json

        global user_db
        if user_db is None or user_db.empty:
            print("❌ No u_database to save")
            return False

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

        # Prepare data for Google Sheets
        # Convert DataFrame to list of lists (including headers)
        headers = list(user_db.columns)
        data_rows = user_db.values.tolist()

        # Convert any NaN values to empty strings and ensure proper data types
        for i, row in enumerate(data_rows):
            for j, cell in enumerate(row):
                if pd.isna(cell):
                    data_rows[i][j] = ''
                elif isinstance(cell, bool):
                    data_rows[i][j] = str(cell).upper()  # TRUE/FALSE for Google Sheets
                else:
                    data_rows[i][j] = str(cell)

        # Combine headers and data
        all_data = [headers] + data_rows

        # Clear the sheet and write new data
        sheet = sheets_service.spreadsheets()

        # Clear existing content
        sheet.values().clear(
            spreadsheetId=config.U_DATABASE,
            range="A:Z"
        ).execute()

        # Write new data
        sheet.values().update(
            spreadsheetId=config.U_DATABASE,
            range="A1",
            valueInputOption="RAW",
            body={"values": all_data}
        ).execute()

        print(f"✅ Successfully saved {len(data_rows)} user records to Google Sheet")
        return True

    except Exception as e:
        print(f"❌ Error saving user database: {e}")
        return False
