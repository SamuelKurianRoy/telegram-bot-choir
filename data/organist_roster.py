# data/organist_roster.py
# Organist Roster Management - Fetch and display organist assignments

import pandas as pd
import io
from datetime import datetime, date, timedelta
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
from data.drive import get_drive_service
from config import get_config
from logging_utils import setup_loggers

bot_logger, user_logger = setup_loggers()

def get_organist_roster_data():
    """
    Load organist roster data from Google Sheet.
    Reads from the 'Order of Songs' sheet.
    
    Returns:
        DataFrame with columns: 'Song/ Responses', 'Name of The Organist'
        or None if failed
    """
    try:
        config = get_config()
        roster_sheet_id = config.secrets.get("ORGANIST_ROSTER_SHEET_ID")
        
        if not roster_sheet_id:
            user_logger.error("ORGANIST_ROSTER_SHEET_ID not found in secrets")
            return None
        
        drive_service = get_drive_service()
        
        # Download the Excel file
        request = drive_service.files().export_media(
            fileId=roster_sheet_id,
            mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        file_data = io.BytesIO()
        downloader = MediaIoBaseDownload(file_data, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        file_data.seek(0)
        
        # Read the Excel file - specifically the 'Order of Songs' sheet
        df = pd.read_excel(file_data, sheet_name='Order of Songs')
        
        # Ensure required columns exist
        required_columns = ['Song/ Responses', 'Name of The Organist']
        for col in required_columns:
            if col not in df.columns:
                user_logger.error(f"Missing required column: {col}")
                return None
        
        user_logger.info("✅ Organist roster loaded successfully")
        return df
    
    except Exception as e:
        user_logger.error(f"Roster load error: {str(e)[:100]}")
        return None

def get_unique_organists():
    """
    Get list of unique organists from the roster.
    
    Returns:
        list: List of unique organist names (excluding empty/NaN values)
    """
    df = get_organist_roster_data()
    
    if df is None:
        return []
    
    try:
        # Get unique organists, excluding NaN values
        organists = df['Name of The Organist'].dropna().unique().tolist()
        # Remove empty strings
        organists = [org for org in organists if str(org).strip()]
        # Sort alphabetically
        organists.sort()
        
        user_logger.info(f"Found {len(organists)} unique organists")
        return organists
    
    except Exception as e:
        user_logger.error(f"Error getting organists: {str(e)[:50]}")
        return []

def get_songs_by_organist(organist_name: str):
    """
    Get all songs assigned to a specific organist.
    
    Args:
        organist_name: Name of the organist
        
    Returns:
        list: List of songs assigned to the organist
    """
    df = get_organist_roster_data()
    
    if df is None:
        return []
    
    try:
        # Filter songs for the specific organist
        organist_songs = df[df['Name of The Organist'] == organist_name]['Song/ Responses'].tolist()
        # Remove NaN values
        organist_songs = [song for song in organist_songs if pd.notna(song)]
        
        user_logger.info(f"Found {len(organist_songs)} songs for {organist_name}")
        return organist_songs
    
    except Exception as e:
        user_logger.error(f"Error getting songs: {str(e)[:50]}")
        return []

def get_unassigned_songs():
    """
    Get all songs that don't have an organist assigned.
    
    Returns:
        list: List of unassigned songs
    """
    df = get_organist_roster_data()
    
    if df is None:
        return []
    
    try:
        # Filter songs where organist is NaN or empty
        unassigned = df[df['Name of The Organist'].isna() | (df['Name of The Organist'].str.strip() == '')]
        unassigned_songs = unassigned['Song/ Responses'].tolist()
        # Remove NaN values from songs
        unassigned_songs = [song for song in unassigned_songs if pd.notna(song)]
        
        user_logger.info(f"Found {len(unassigned_songs)} unassigned songs")
        return unassigned_songs
    
    except Exception as e:
        user_logger.error(f"Error getting unassigned songs: {str(e)[:50]}")
        return []

def get_roster_summary():
    """
    Get summary statistics about the organist roster.
    
    Returns:
        dict: Summary statistics
    """
    df = get_organist_roster_data()
    
    if df is None:
        return {
            'total_songs': 0,
            'assigned_songs': 0,
            'unassigned_songs': 0,
            'total_organists': 0
        }
    
    try:
        total_songs = len(df[df['Song/ Responses'].notna()])
        assigned_songs = len(df[df['Name of The Organist'].notna() & (df['Name of The Organist'].str.strip() != '')])
        unassigned_songs = total_songs - assigned_songs
        total_organists = len(df['Name of The Organist'].dropna().unique())
        
        return {
            'total_songs': total_songs,
            'assigned_songs': assigned_songs,
            'unassigned_songs': unassigned_songs,
            'total_organists': total_organists
        }
    
    except Exception as e:
        user_logger.error(f"Error getting summary: {str(e)[:50]}")
        return {
            'total_songs': 0,
            'assigned_songs': 0,
            'unassigned_songs': 0,
            'total_organists': 0
        }

def get_full_roster_table():
    """
    Get the complete roster table in order.
    
    Returns:
        list: List of tuples (song_name, organist_name) in original order
    """
    df = get_organist_roster_data()
    
    if df is None:
        return []
    
    try:
        # Get all rows with song names (filter out empty songs)
        roster_table = []
        for _, row in df.iterrows():
            song = row['Song/ Responses']
            organist = row['Name of The Organist']
            
            # Only include rows with song names
            if pd.notna(song) and str(song).strip():
                # Handle empty organist
                if pd.isna(organist) or str(organist).strip() == '':
                    organist_name = "Not Assigned"
                else:
                    organist_name = str(organist).strip()
                
                roster_table.append((str(song).strip(), organist_name))
        
        user_logger.info(f"Retrieved full roster table ({len(roster_table)} entries)")
        return roster_table
    
    except Exception as e:
        user_logger.error(f"Error getting full table: {str(e)[:50]}")
        return []

def get_next_sunday():
    """
    Get the next Sunday date. If today is Sunday, return today.
    
    Returns:
        date: The next Sunday date
    """
    today = date.today()
    # Monday = 0, Sunday = 6
    days_ahead = 6 - today.weekday()
    if days_ahead < 0:  # Today is Sunday
        days_ahead = 0
    elif days_ahead == 0 and today.weekday() != 6:  # Not Sunday
        days_ahead = 7
    
    next_sunday = today + timedelta(days=days_ahead)
    return next_sunday

def get_songs_for_date(target_date):
    """
    Get songs for a specific date from the main database.
    Uses the same logic as the /date command.
    
    Args:
        target_date: date object
        
    Returns:
        list: List of songs for that date (or next available date)
    """
    try:
        from data.datasets import get_all_data
        
        data = get_all_data()
        df = data["df"]
        
        if df is None or df.empty:
            user_logger.error("Main database is empty")
            return []
        
        # Ensure 'Date' column is datetime.date
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce').dt.date
        df.dropna(subset=['Date'], inplace=True)
        
        # Sort dates
        available_dates = sorted(df['Date'].unique())
        
        # Find songs on the target date
        matching_rows = df[df['Date'] == target_date]
        
        if matching_rows.empty:
            # Get the next available date with songs
            next_dates = [d for d in available_dates if d > target_date]
            if not next_dates:
                user_logger.warning(f"No songs found on {target_date} or any later date")
                return []
            next_date = next_dates[0]
            matching_rows = df[df['Date'] == next_date]
            user_logger.info(f"No songs on {target_date}, using next date: {next_date}")
        
        # Get song columns
        song_columns = [col for col in df.columns if col != 'Date']
        songs = []
        
        for _, row in matching_rows.iterrows():
            for col in song_columns:
                song = row[col]
                if pd.notna(song) and str(song).strip() != '':
                    songs.append(str(song).strip())
        
        user_logger.info(f"Retrieved {len(songs)} songs for date")
        return songs
    
    except Exception as e:
        user_logger.error(f"Error getting songs for date: {str(e)[:100]}")
        return []

def update_songs_for_sunday():
    """
    Update the "Songs for Sunday" sheet with songs from today (if Sunday) or next Sunday.
    Only updates the "Songs" column, leaves "Organist" column unchanged.
    
    Returns:
        tuple: (success: bool, message: str, date_used: date)
    """
    try:
        config = get_config()
        roster_sheet_id = config.secrets.get("ORGANIST_ROSTER_SHEET_ID")
        
        if not roster_sheet_id:
            return False, "ORGANIST_ROSTER_SHEET_ID not found in secrets", None
        
        # Get next Sunday date
        sunday_date = get_next_sunday()
        
        # Get songs for that date
        songs = get_songs_for_date(sunday_date)
        
        user_logger.info(f"Retrieved {len(songs)} songs for {sunday_date.strftime('%d/%m/%Y')}")
        
        if not songs:
            return False, f"No songs found for {sunday_date.strftime('%d/%m/%Y')}", sunday_date
        
        drive_service = get_drive_service()
        
        # Download the current Excel file
        request = drive_service.files().export_media(
            fileId=roster_sheet_id,
            mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        file_data = io.BytesIO()
        downloader = MediaIoBaseDownload(file_data, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        file_data.seek(0)
        
        # Read all sheets
        excel_file = pd.ExcelFile(file_data)
        
        # Check if "Songs for Sunday" sheet exists
        if "Songs for Sunday" not in excel_file.sheet_names:
            return False, "'Songs for Sunday' sheet not found", sunday_date
        
        # Read all sheets into memory first
        all_sheets = {}
        for sheet_name in excel_file.sheet_names:
            file_data.seek(0)
            all_sheets[sheet_name] = pd.read_excel(file_data, sheet_name=sheet_name)
        
        user_logger.info(f"Available sheets: {list(all_sheets.keys())}")
        
        df_sunday = all_sheets.get('Songs for Sunday')
        
        if df_sunday is None:
            available_sheets = ', '.join(excel_file.sheet_names)
            return False, f"'Songs for Sunday' sheet not found. Available: {available_sheets}", sunday_date
        
        # Ensure required columns exist
        if 'Songs' not in df_sunday.columns:
            df_sunday['Songs'] = ''
        if 'Organist' not in df_sunday.columns:
            df_sunday['Organist'] = ''
        
        user_logger.info(f"Current 'Songs for Sunday' has {len(df_sunday)} rows")
        user_logger.info(f"Columns: {df_sunday.columns.tolist()}")
        
        # Create new DataFrame with songs
        new_df = pd.DataFrame()
        new_df['Songs'] = songs
        
        # Preserve organist column - pad or truncate as needed
        existing_organists = df_sunday['Organist'].tolist() if len(df_sunday) > 0 else []
        
        # Match the number of organists to the number of songs
        if len(existing_organists) < len(songs):
            # Pad with empty strings
            organists = existing_organists + [''] * (len(songs) - len(existing_organists))
        else:
            # Truncate to match songs
            organists = existing_organists[:len(songs)]
        
        new_df['Organist'] = organists
        
        # Update the sheet in our dictionary
        all_sheets['Songs for Sunday'] = new_df
        
        # Now write back to Excel
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            # Write all sheets in their original order
            for sheet_name in excel_file.sheet_names:
                all_sheets[sheet_name].to_excel(writer, sheet_name=sheet_name, index=False)
        
        output.seek(0)
        
        # Upload the file back
        media = MediaIoBaseUpload(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            resumable=True
        )
        
        drive_service.files().update(
            fileId=roster_sheet_id,
            media_body=media
        ).execute()
        
        user_logger.info(f"✅ Updated Songs for Sunday with {len(songs)} songs for {sunday_date.strftime('%d/%m/%Y')}")
        return True, f"✅ Updated {len(songs)} songs for {sunday_date.strftime('%d/%m/%Y')}", sunday_date
    
    except Exception as e:
        user_logger.error(f"Error updating Sunday songs: {str(e)[:100]}")
        return False, f"Error: {str(e)[:100]}", None
