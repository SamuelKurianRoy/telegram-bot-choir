# data/drive.py
# Google Drive/Docs API functions 

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2 import service_account
import json
import os
from config import get_config
import tempfile
import pandas as pd
import io
from googleapiclient.http import MediaIoBaseDownload
from datetime import datetime
import streamlit as st

# Google Drive/Docs API setup and helpers

def get_drive_service():
    """
    Returns an authenticated Google Drive service instance.
    """
    config = get_config()
    # Always use a cross-platform temp directory for the service account file
    tmp_dir = tempfile.gettempdir()
    key_path = os.path.join(tmp_dir, "service_account.json")
    with open(key_path, "w") as f:
        json.dump(config.service_account_data, f)
    config.KEY_PATH = key_path
    creds = service_account.Credentials.from_service_account_file(
        config.KEY_PATH, scopes=["https://www.googleapis.com/auth/drive"]
    )
    return build("drive", "v3", credentials=creds)

def get_docs_service():
    """
    Returns an authenticated Google Docs service instance.
    """
    config = get_config()
    if not os.path.exists(config.KEY_PATH):
        with open(config.KEY_PATH, "w") as f:
            json.dump(config.service_account_data, f)
    creds = service_account.Credentials.from_service_account_file(
        config.KEY_PATH, scopes=["https://www.googleapis.com/auth/documents"]
    )
    return build("docs", "v1", credentials=creds)

def upload_log_to_google_doc(doc_id: str, log_file: str):
    """
    Uploads a local log file's contents to a Google Docs file.
    Clears the existing content and appends the new content.
    """
    docs_service = get_docs_service()
    if not os.path.exists(log_file):
        print(f"⚠️ Log file {log_file} does not exist.")
        return
    with open(log_file, "r", encoding="utf-8") as file:
        content = file.read().strip()
    if not content:
        print(f"ℹ️ Log file {log_file} is empty. Skipping upload.")
        return
    try:
        doc = docs_service.documents().get(documentId=doc_id).execute()
        end_index = doc.get('body', {}).get('content', [{}])[-1].get('endIndex', 1)
        requests = []
        if end_index > 1:
            requests.append({
                'deleteContentRange': {
                    'range': {
                        'startIndex': 1,
                        'endIndex': end_index - 1
                    }
                }
            })
        requests.append({
            'insertText': {
                'location': {'index': 1},
                'text': content
            }
        })
        docs_service.documents().batchUpdate(
            documentId=doc_id,
            body={'requests': requests}
        ).execute()
        print(f"✅ Successfully uploaded {log_file} to Google Doc")
    except HttpError as e:
        print(f"❌ Failed to log due to: {e}")

def append_download_to_google_doc(yfile_id: str, download_entry: str):
    """
    Appends a download entry directly to a Google Docs file.
    """
    docs_service = get_docs_service()
    try:
        doc = docs_service.documents().get(documentId=yfile_id).execute()
        end_index = doc.get("body").get("content")[-1].get("endIndex", 1)
        requests = [{
            "insertText": {
                "location": {"index": end_index - 1},
                "text": download_entry
            }
        }]
        docs_service.documents().batchUpdate(
            documentId=yfile_id,
            body={"requests": requests}
        ).execute()
        print("✅ Query successful")
    except Exception as e:
        print(f"❌ Failed to Query Youtube: {e}")

# Game Score Database Functions
def load_game_scores():
    """
    Load the Game_Score Excel sheet from Google Drive
    Returns a pandas DataFrame with columns: Date, User_Name, User_id, Score, Difficulty
    """
    try:
        config = get_config()
        drive_service = get_drive_service()

        # Get the Game_Score file ID from config
        game_score_file_id = config.GAME_SCORE
        if not game_score_file_id:
            print("❌ GAME_SCORE file ID not found in secrets")
            return pd.DataFrame(columns=['Date', 'User_Name', 'User_id', 'Score'])

        # Download the Excel file
        request = drive_service.files().export_media(
            fileId=game_score_file_id,
            mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        file_data = io.BytesIO()
        downloader = MediaIoBaseDownload(file_data, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        file_data.seek(0)

        # Read the Excel file
        df = pd.read_excel(file_data)

        # Ensure the required columns exist
        required_columns = ['Date', 'User_Name', 'User_id', 'Score', 'Difficulty']
        for col in required_columns:
            if col not in df.columns:
                df[col] = None if col != 'Difficulty' else 'Easy'  # Default difficulty to Easy for old records

        return df

    except Exception as e:
        print(f"❌ Error loading game scores: {e}")
        return pd.DataFrame(columns=['Date', 'User_Name', 'User_id', 'Score', 'Difficulty'])

def save_game_score(user_name, user_id, score, difficulty="Easy"):
    """
    Save a new game score to the Game_Score Excel sheet
    """
    try:
        # Load existing scores
        df = load_game_scores()

        # Create new entry
        new_entry = {
            'Date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'User_Name': user_name,
            'User_id': user_id,
            'Score': score,
            'Difficulty': difficulty
        }

        # Add new entry to DataFrame
        df = pd.concat([df, pd.DataFrame([new_entry])], ignore_index=True)

        # Upload back to Google Drive
        config = get_config()
        drive_service = get_drive_service()
        game_score_file_id = config.GAME_SCORE

        if not game_score_file_id:
            print("❌ GAME_SCORE file ID not found in secrets")
            return False

        # Convert DataFrame to Excel
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Sheet1')
        output.seek(0)

        # Upload the file
        from googleapiclient.http import MediaIoBaseUpload
        media = MediaIoBaseUpload(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

        drive_service.files().update(
            fileId=game_score_file_id,
            media_body=media
        ).execute()

        # print(f"✅ Game score saved for {user_name} (ID: {user_id}): {score} ({difficulty})")
        return True

    except Exception as e:
        print(f"❌ Error saving game score: {e}")
        return False

# User Database Functions
def load_user_database():
    """
    Load the U_Database Excel sheet from Google Drive
    Returns a pandas DataFrame with columns: user_id, username, name
    """
    try:
        config = get_config()
        drive_service = get_drive_service()

        # Get the U_Database file ID from config
        u_database_file_id = config.U_DATABASE
        if not u_database_file_id:
            print("❌ U_DATABASE file ID not found in secrets")
            return pd.DataFrame(columns=['user_id', 'username', 'name'])

        # Download the Excel file
        request = drive_service.files().export_media(
            fileId=u_database_file_id,
            mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        file_data = io.BytesIO()
        downloader = MediaIoBaseDownload(file_data, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        file_data.seek(0)

        # Read the Excel file
        df = pd.read_excel(file_data)

        # Ensure the required columns exist
        required_columns = ['user_id', 'username', 'name']
        for col in required_columns:
            if col not in df.columns:
                df[col] = None

        return df

    except Exception as e:
        print(f"❌ Error loading user database: {e}")
        return pd.DataFrame(columns=['user_id', 'username', 'name'])

def save_user_to_database(user_id, username, name):
    """
    Save a new user to the U_Database Excel sheet
    """
    try:
        # Load existing users
        df = load_user_database()

        # Check if user already exists
        if user_id in df['user_id'].values:
            # print(f"User {user_id} already exists in database")
            return True

        # Create new entry
        new_entry = {
            'user_id': user_id,
            'username': username,
            'name': name
        }

        # Add new entry to DataFrame
        df = pd.concat([df, pd.DataFrame([new_entry])], ignore_index=True)

        # Upload back to Google Drive
        config = get_config()
        drive_service = get_drive_service()
        u_database_file_id = config.U_DATABASE

        if not u_database_file_id:
            print("❌ U_DATABASE file ID not found in secrets")
            return False

        # Convert DataFrame to Excel
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Sheet1')
        output.seek(0)

        # Upload the file
        from googleapiclient.http import MediaIoBaseUpload
        media = MediaIoBaseUpload(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

        drive_service.files().update(
            fileId=u_database_file_id,
            media_body=media
        ).execute()

        # print(f"✅ User saved to database: {name} (@{username}, ID: {user_id})")
        return True

    except Exception as e:
        print(f"❌ Error saving user to database: {e}")
        return False

def get_all_users():
    """
    Get all users from the database
    Returns a list of dictionaries with user information
    """
    try:
        df = load_user_database()
        users = []
        for _, row in df.iterrows():
            users.append({
                'user_id': row['user_id'],
                'username': row['username'],
                'name': row['name'],
                'display_name': row['name'] if pd.notna(row['name']) and row['name'] else (row['username'] if pd.notna(row['username']) and row['username'] else f"User {row['user_id']}")
            })
        return users
    except Exception as e:
        print(f"❌ Error getting all users: {e}")
        return []

def get_user_best_score(user_id, difficulty=None):
    """
    Get the best score for a specific user, optionally filtered by difficulty
    """
    try:
        df = load_game_scores()
        user_scores = df[df['User_id'] == user_id]

        if difficulty:
            user_scores = user_scores[user_scores['Difficulty'] == difficulty]

        if user_scores.empty:
            return 0

        return user_scores['Score'].max()

    except Exception as e:
        print(f"❌ Error getting user best score: {e}")
        return 0

def get_user_best_scores_all_difficulties(user_id):
    """
    Get the best scores for a user across all difficulties
    """
    try:
        df = load_game_scores()
        user_scores = df[df['User_id'] == user_id]

        if user_scores.empty:
            return {"Easy": 0, "Medium": 0, "Hard": 0}

        best_scores = {}
        for difficulty in ["Easy", "Medium", "Hard"]:
            difficulty_scores = user_scores[user_scores['Difficulty'] == difficulty]
            best_scores[difficulty] = difficulty_scores['Score'].max() if not difficulty_scores.empty else 0

        return best_scores

    except Exception as e:
        print(f"❌ Error getting user best scores: {e}")
        return {"Easy": 0, "Medium": 0, "Hard": 0}

def get_leaderboard(top_n=10, difficulty=None):
    """
    Get the top N scores from all users, optionally filtered by difficulty
    """
    try:
        df = load_game_scores()

        if df.empty:
            return []

        # Filter by difficulty if specified
        if difficulty:
            df = df[df['Difficulty'] == difficulty]

        if df.empty:
            return []

        # Group by user and get their best score for the specified difficulty
        user_best = df.groupby(['User_id', 'User_Name'])['Score'].max().reset_index()

        # Sort by score descending and get top N
        leaderboard = user_best.sort_values('Score', ascending=False).head(top_n)

        return leaderboard.to_dict('records')

    except Exception as e:
        print(f"❌ Error getting leaderboard: {e}")
        return []

def get_combined_leaderboard(top_n=10):
    """
    Get a combined leaderboard showing best scores across all difficulties
    """
    try:
        leaderboards = {}
        for difficulty in ["Easy", "Medium", "Hard"]:
            leaderboards[difficulty] = get_leaderboard(top_n, difficulty)

        return leaderboards

    except Exception as e:
        print(f"❌ Error getting combined leaderboard: {e}")
        return {"Easy": [], "Medium": [], "Hard": []}

# User Database Functions
def load_user_database():
    """
    Load the U_Database Excel sheet from Google Drive
    Returns a pandas DataFrame with columns: user_id, username, name
    """
    try:
        config = get_config()
        drive_service = get_drive_service()

        # Get the U_Database file ID from config
        u_database_file_id = config.U_DATABASE
        if not u_database_file_id:
            print("❌ U_DATABASE file ID not found in secrets")
            return pd.DataFrame(columns=['user_id', 'username', 'name'])

        # Download the Excel file
        request = drive_service.files().export_media(
            fileId=u_database_file_id,
            mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        file_data = io.BytesIO()
        downloader = MediaIoBaseDownload(file_data, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        file_data.seek(0)

        # Read the Excel file
        df = pd.read_excel(file_data)

        # Ensure the required columns exist
        required_columns = ['user_id', 'username', 'name']
        for col in required_columns:
            if col not in df.columns:
                df[col] = None

        return df

    except Exception as e:
        print(f"❌ Error loading user database: {e}")
        return pd.DataFrame(columns=['user_id', 'username', 'name'])

def save_user_database(df):
    """
    Save the user database DataFrame back to Google Drive Excel sheet
    """
    try:
        config = get_config()
        drive_service = get_drive_service()
        u_database_file_id = config.U_DATABASE

        if not u_database_file_id:
            print("❌ U_DATABASE file ID not found in secrets")
            return False

        # Convert DataFrame to Excel
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Sheet1')
        output.seek(0)

        # Upload the file
        from googleapiclient.http import MediaIoBaseUpload
        media = MediaIoBaseUpload(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

        drive_service.files().update(
            fileId=u_database_file_id,
            media_body=media
        ).execute()

        print("✅ User database saved successfully")
        return True

    except Exception as e:
        print(f"❌ Error saving user database: {e}")
        return False

def add_user_to_database(user_id, username, name):
    """
    Add or update user in the U_Database Excel sheet
    Returns True if new user was added, False if existing user was updated
    """
    try:
        # Load existing database
        df = load_user_database()

        # Check if user already exists
        existing_user = df[df['user_id'] == user_id]
        
        if existing_user.empty:
            # Add new user
            new_user = pd.DataFrame({
                'user_id': [user_id],
                'username': [username or 'No username'],
                'name': [name or 'Unknown']
            })
            df = pd.concat([df, new_user], ignore_index=True)
            
            # Save back to Google Drive
            if save_user_database(df):
                print(f"✅ New user added: {name} (@{username}, ID: {user_id})")
                return True
            else:
                print(f"❌ Failed to save new user: {user_id}")
                return False
        else:
            # Update existing user info if changed
            index = existing_user.index[0]
            updated = False
            
            if df.loc[index, 'username'] != (username or 'No username'):
                df.loc[index, 'username'] = username or 'No username'
                updated = True
            
            if df.loc[index, 'name'] != (name or 'Unknown'):
                df.loc[index, 'name'] = name or 'Unknown'
                updated = True
            
            if updated:
                if save_user_database(df):
                    print(f"✅ User updated: {name} (@{username}, ID: {user_id})")
                else:
                    print(f"❌ Failed to update user: {user_id}")
            
            return False  # Existing user

    except Exception as e:
        print(f"❌ Error adding user to database: {e}")
        return False

def get_all_users_from_database():
    """
    Get all users from the U_Database
    Returns list of dictionaries with user info
    """
    try:
        df = load_user_database()
        
        if df.empty:
            return []
        
        # Convert to list of dictionaries
        users = []
        for _, row in df.iterrows():
            users.append({
                'user_id': int(row['user_id']) if pd.notna(row['user_id']) else 0,
                'username': row['username'] if pd.notna(row['username']) else 'No username',
                'name': row['name'] if pd.notna(row['name']) else 'Unknown'
            })
        
        return users

    except Exception as e:
        print(f"❌ Error getting users from database: {e}")
        return []

def get_user_by_id_from_database(user_id):
    """
    Get specific user by ID from the U_Database
    """
    try:
        df = load_user_database()
        user_row = df[df['user_id'] == user_id]
        
        if user_row.empty:
            return None
        
        row = user_row.iloc[0]
        return {
            'user_id': int(row['user_id']) if pd.notna(row['user_id']) else 0,
            'username': row['username'] if pd.notna(row['username']) else 'No username',
            'name': row['name'] if pd.notna(row['name']) else 'Unknown'
        }

    except Exception as e:
        print(f"❌ Error getting user by ID from database: {e}")
        return None
