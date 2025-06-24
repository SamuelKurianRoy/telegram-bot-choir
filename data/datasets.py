# data/datasets.py
# Dataset loading, cleaning, and preprocessing 

import pandas as pd
import io
from googleapiclient.http import MediaIoBaseDownload
from data.drive import get_drive_service
from config import get_config
import re
from datetime import datetime

# Global dataset variables
dfH = dfL = dfC = yr23 = yr24 = yr25 = df = dfTH = dfTD = None

def load_datasets():
    """
    Downloads and loads all datasets from Google Drive. Updates the global
    dataset variables so that the bot uses the latest data.
    Returns all loaded DataFrames.
    """
    global dfH, dfL, dfC, yr23, yr24, yr25, df, dfTH, dfTD
    config = get_config()
    drive_service = get_drive_service()

    # --- Load Index Database (HLCFILE) ---
    request = drive_service.files().export_media(
        fileId=config.HLCFILE_ID,
        mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    file_data = io.BytesIO()
    downloader = MediaIoBaseDownload(file_data, request, chunksize=1024 * 256)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    file_data.seek(0)
    xls = pd.ExcelFile(file_data)
    try:
        dfH = pd.read_excel(xls, sheet_name="Hymn List")
    except Exception:
        dfH = None
    try:
        dfL = pd.read_excel(xls, sheet_name="Lyric List")
    except Exception:
        dfL = None
    try:
        dfC = pd.read_excel(xls, sheet_name="Convention List")
    except Exception:
        dfC = None

    # --- Load Main Excel File (FILE_ID) ---
    request = drive_service.files().get_media(fileId=config.FILE_ID)
    file_data = io.BytesIO()
    downloader = MediaIoBaseDownload(file_data, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    file_data.seek(0)
    xls = pd.ExcelFile(file_data)
    try:
        yr23 = pd.read_excel(xls, sheet_name="2023")
    except Exception:
        yr23 = None
    try:
        yr24 = pd.read_excel(xls, sheet_name="2024")
    except Exception:
        yr24 = None
    try:
        yr25 = pd.read_excel(xls, sheet_name="2025")
    except Exception:
        yr25 = None
    try:
        df = pd.read_excel(xls, sheet_name="Sheet 1")
    except Exception:
        df = None

    # --- Load Tune Database (TFILE_ID) ---
    try:
        request = drive_service.files().export_media(
            fileId=config.TFILE_ID,
            mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        file_data = io.BytesIO()
        downloader = MediaIoBaseDownload(file_data, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        file_data.seek(0)
        xls = pd.ExcelFile(file_data)
        try:
            dfTH = pd.read_excel(xls, sheet_name="Hymn")
        except Exception:
            dfTH = None
        try:
            dfTD = pd.read_excel(xls, sheet_name="Doxology")
        except Exception:
            dfTD = None
    except Exception:
        dfTH = None
        dfTD = None
    return dfH, dfL, dfC, yr23, yr24, yr25, df, dfTH, dfTD

def yrDataPreprocessing():
    """
    Preprocesses the year DataFrames and fills missing values in dfH.
    """
    global yr23, yr24, yr25, df, dfH
    if yr23 is not None:
        yr23.dropna(inplace=True)
        yr23.columns = yr23.iloc[0]
        yr23.drop(index=1, inplace=True)
        yr23.reset_index(drop=True, inplace=True)
        yr23['Date'] = pd.to_datetime(yr23['Date']).dt.date
    if yr24 is not None:
        yr24.dropna(inplace=True)
        yr24.columns = yr24.iloc[0]
        yr24.drop(index=1, inplace=True)
        yr24.reset_index(drop=True, inplace=True)
        yr24['Date'] = pd.to_datetime(yr24['Date']).dt.date
    if yr25 is not None:
        if 'Unnamed: 6' in yr25.columns:
            Themes = yr25['Unnamed: 6']
            yr25.drop('Unnamed: 6', axis=1, inplace=True)
        yr25.dropna(inplace=True)
        yr25.columns = yr25.iloc[0]
        yr25.drop(index=1, inplace=True)
        yr25.reset_index(drop=True, inplace=True)
        yr25['Date'] = pd.to_datetime(yr25['Date']).dt.date
    if dfH is not None:
        if 'Tunes' in dfH.columns:
            dfH['Tunes'] = dfH['Tunes'].fillna("Unknown")
        if 'Page no' in dfH.columns:
            dfH['Page no'] = dfH['Page no'].fillna("0")

def dfcleaning():
    """
    Cleans the main DataFrame df by dropping NaNs and standardizing the date column.
    """
    global df
    if df is not None:
        df.dropna(inplace=True)
        df = df[pd.to_datetime(df['Date'], errors='coerce').notna()]
        df = df[df['Date'].notna()]
        df.reset_index(drop=True, inplace=True)
        df['Date'] = pd.to_datetime(df['Date']).dt.date

def standardize_song_columns():
    """
    Standardizes all song columns in df by removing whitespace.
    """
    global df
    if df is None:
        return None
    standardized_df = df.copy()
    song_columns = [col for col in df.columns if col != 'Date']
    for col in song_columns:
        standardized_df[col] = standardized_df[col].astype(str).apply(lambda x: re.sub(r'\s+', '', x))
    return standardized_df

def Tune_finder_of_known_songs(song):
    """
    Returns the tune(s) for a given hymn number from dfH.
    """
    song = str(song).upper().replace('H-', '').replace('H', '').strip()
    try:
        song = int(song)
    except Exception:
        return "Invalid Number"
    if dfH is not None and 'Tunes' in dfH.columns:
        return dfH['Tunes'][song-1]
    return "Invalid Number"

def Tunenofinder(no):
    """
    Returns the tune index for a given hymn number from dfTH.
    """
    try:
        no = int(no)
    except ValueError:
        return "Index must be an integer."
    if dfTH is not None and 'Hymn no' in dfTH.columns and 'Tune Index' in dfTH.columns:
        result = dfTH[dfTH['Hymn no'] == no]['Tune Index']
        if not result.empty:
            return "\n".join(tune.strip() for tune in result.tolist())
        else:
            return "Tune Index not found."
    else:
        return "Invalid hymn index."

def reload_all_datasets():
    """
    Reloads all datasets and applies preprocessing and cleaning.
    Returns all loaded DataFrames.
    """
    data = load_datasets()
    yrDataPreprocessing()
    dfcleaning()
    return data

def get_all_data():
    """
    Returns all loaded data as a dictionary for easy access.
    """
    return {
        'dfH': dfH,
        'dfL': dfL,
        'dfC': dfC,
        'yr23': yr23,
        'yr24': yr24,
        'yr25': yr25,
        'df': df,
        'dfTH': dfTH,
        'dfTD': dfTD,
    }

# TODO: Add data cleaning and preprocessing functions (e.g., yrDataPreprocessing, dfcleaning) 