# data/organist_roster.py
# Organist Roster Management - Fetch and display organist assignments

import pandas as pd
import io
from googleapiclient.http import MediaIoBaseDownload
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
