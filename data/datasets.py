# data/datasets.py
# Dataset loading, cleaning, and preprocessing 

import pandas as pd
import io
from googleapiclient.http import MediaIoBaseDownload
from data.drive import get_drive_service
from config import get_config
import re
from datetime import datetime
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# Global dataset variables
dfH = dfL = dfC = df = dfTH = dfTD = None
year_data = {}  # Dictionary to hold year dataframes dynamically {2023: df23, 2024: df24, ...}

def load_datasets():
    """
    Downloads and loads all datasets from Google Drive. Updates the global
    dataset variables so that the bot uses the latest data.
    Returns all loaded DataFrames.
    """
    global dfH, dfL, dfC, df, dfTH, dfTD, year_data
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
    
    # --- Load Year DataFrames (dynamically from 2023 to current year) ---
    year_data.clear()  # Clear previous year data
    current_year = datetime.now().year
    
    for year in range(2023, current_year + 1):
        sheet_name = str(year)
        try:
            year_data[year] = pd.read_excel(xls, sheet_name=sheet_name)
        except Exception as e:
            print(f"Warning: Could not load sheet '{sheet_name}': {e}")
            year_data[year] = None
    
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
    return dfH, dfL, dfC, year_data, df, dfTH, dfTD

def yrDataPreprocessing():
    """
    Preprocesses the year DataFrames and fills missing values in dfH.
    """
    global year_data, df, dfH
    
    # Process each year's dataframe dynamically
    for year, year_df in year_data.items():
        if year_df is not None:
            year_df.dropna(inplace=True)
            
            # Check if dataframe is empty after dropping NaN values
            if year_df.empty:
                print(f"Warning: Year {year} sheet is empty after dropping NaN values")
                year_data[year] = None
                continue
            
            year_df.columns = year_df.iloc[0]
            year_df.drop(year_df.index[0], inplace=True)  # Drop first row by position, not by label
            year_df.reset_index(drop=True, inplace=True)
            year_df['Date'] = pd.to_datetime(year_df['Date']).dt.date
            year_data[year] = year_df  # Update the dict with preprocessed data
    
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
    Standardizes all song columns in df by removing whitespace and updating global df.
    """
    global df
    if df is None:
        return None
    song_columns = [col for col in df.columns if col != 'Date']
    for col in song_columns:
        df[col] = df[col].astype(str).apply(lambda x: re.sub(r'\s+', '', x))
    return df

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
    data_dict = {
        'dfH': dfH,
        'dfL': dfL,
        'dfC': dfC,
        'df': df,
        'dfTH': dfTH,
        'dfTD': dfTD,
    }
    # Add all year data dynamically
    for year, year_df in year_data.items():
        data_dict[f'yr{year}'] = year_df
    
    return data_dict

def get_year_df(year):
    """
    Get a specific year's dataframe.
    Args:
        year (int): The year to retrieve (e.g., 2023, 2024, 2026)
    Returns:
        DataFrame or None: The year's dataframe if it exists, None otherwise
    """
    return year_data.get(year)

def get_available_years():
    """
    Get a list of all available years in the dataset.
    Returns:
        list: Sorted list of available years
    """
    return sorted([year for year, df in year_data.items() if df is not None])

def standardize_hlc_value(value):
    value = str(value).upper().strip()
    value = re.sub(r'^([HLC])\s*[-]?\s*(\d+)$', r'\1-\2', value)
    value = re.sub(r'-+', '-', value)
    value = re.sub(r'\s*-\s*', '-', value)
    return value

def IndexFinder(Song):
    try:
        song = standardize_hlc_value(Song)
        global dfH, dfL, dfC

        # Handle empty or invalid input
        if not song or len(song) < 2:
            return "Invalid Number"
        
        # Check for "nil" in the input (case-insensitive)
        if 'NIL' in song.upper() or song.upper() == 'NIL':
            return ""

        if song.startswith("H"):
            song_num = song.replace('H','').strip().replace("-", "")
            if not song_num or song_num.upper() == 'NIL':  # Check if empty or nil after processing
                return ""
            song_num = int(song_num)
            if dfH is not None and 0 < song_num <= len(dfH):
                return dfH['Hymn Index'][song_num-1]
            return "Invalid Number"
        elif song.startswith("L"):
            song_num = song.replace('L','').strip().replace("-", "")
            if not song_num or song_num.upper() == 'NIL':  # Check if empty or nil after processing
                return ""
            song_num = int(song_num)
            if dfL is not None and 0 < song_num <= len(dfL):
                return dfL['Lyric Index'][song_num-1]
            return "Invalid Number"
        elif song.startswith("C"):
            song_num = song.replace('C','').strip().replace("-", "")
            if not song_num or song_num.upper() == 'NIL':  # Check if empty or nil after processing
                return ""
            song_num = int(song_num)
            if dfC is not None and 0 < song_num <= len(dfC):
                return dfC['Convention Index'][song_num-1]
            return "Invalid Number"
        else:
            return "Invalid Number"
    except (ValueError, IndexError, TypeError):
        return "Invalid Number"

def Datefinder(songs, category=None, first=False):
    global df
    First=first
    Song = standardize_hlc_value(songs)
    Found = False
    formatted_date = []
    for i in range(len(df) - 1, -1, -1):
        # Standardize each cell value in the row before comparison
        row_values = [standardize_hlc_value(str(val)) for val in df.iloc[i].tolist()]
        if Song in row_values:
            Found = True
            date_val = df['Date'].iloc[i]
            formatted_date.append(date_val.strftime("%d/%m/%Y"))
            if First:
                break
    if Found and First:
         return f"{Song}: {IndexFinder(Song)} was last sung on: {formatted_date[0]}"
    elif Found:
        dates_string = ''.join(f"{i}\n" for i in formatted_date)
        return f"{Song}: {IndexFinder(Song)} was sung on: \n{dates_string}"
    else:
         return f"The Song {Song} was not Sang in the past years since 2022"

def Hymn_Tune_no_Finder(dfTH, tune_query, top_n=10):
    # if dfTH is None or dfTH.empty:
    #     return pd.DataFrame(columns=['Hymn no', 'Tune Index', 'Similarity'])
    # Preprocess: lowercase all entries
    dfTH = dfTH.copy()
    dfTH['Tune Index'] = dfTH['Tune Index'].astype(str).str.lower()
    tune_query = tune_query.lower()

    # Combine all tune names into a list and add the query
    tune_list = dfTH['Tune Index'].tolist()
    all_tunes = tune_list + [tune_query]

    # Use character n-grams (for partial and fuzzy matching)
    vectorizer = TfidfVectorizer(analyzer='char_wb', ngram_range=(2, 4))
    tfidf_matrix = vectorizer.fit_transform(all_tunes)

    # Compute cosine similarity
    cosine_sim = cosine_similarity(tfidf_matrix[-1], tfidf_matrix[:-1]).flatten()

    # Get top N indices
    top_indices = cosine_sim.argsort()[::-1][:top_n]

    # Build results DataFrame
    results = dfTH.iloc[top_indices][['Hymn no', 'Tune Index']].copy()
    results['Similarity'] = cosine_sim[top_indices]

    return results.reset_index(drop=True)

def save_lyric_list_to_drive(dfL_updated: pd.DataFrame) -> bool:
    """
    Save the updated Lyric List back to Google Drive.
    Updates only the "Lyric List" sheet in the HLCFILE.
    
    Args:
        dfL_updated: Updated Lyric List DataFrame
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
        import tempfile
        
        config = get_config()
        drive_service = get_drive_service()
        
        # Download the entire HLCFILE
        request = drive_service.files().export_media(
            fileId=config.HLCFILE_ID,
            mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        file_data = io.BytesIO()
        downloader = MediaIoBaseDownload(file_data, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        file_data.seek(0)
        
        # Load all sheets
        with pd.ExcelFile(file_data) as xls:
            all_sheets = {}
            for sheet_name in xls.sheet_names:
                all_sheets[sheet_name] = pd.read_excel(xls, sheet_name=sheet_name)
        
        # Update the Lyric List sheet
        all_sheets["Lyric List"] = dfL_updated
        
        # Write to temporary file
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.xlsx', delete=False) as tmp_file:
            tmp_path = tmp_file.name
            with pd.ExcelWriter(tmp_path, engine='openpyxl') as writer:
                for sheet_name, df in all_sheets.items():
                    df.to_excel(writer, sheet_name=sheet_name, index=False)
        
        # Upload back to Google Drive
        media = MediaFileUpload(tmp_path, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        drive_service.files().update(
            fileId=config.HLCFILE_ID,
            media_body=media
        ).execute()
        
        # Clean up temp file
        import os
        os.unlink(tmp_path)
        
        # Update global dfL
        global dfL
        dfL = dfL_updated
        
        print(f"✅ Successfully saved Lyric List to Google Drive")
        return True
        
    except Exception as e:
        print(f"❌ Error saving Lyric List: {e}")
        import traceback
        traceback.print_exc()
        return False

# TODO: Add data cleaning and preprocessing functions (e.g., yrDataPreprocessing, dfcleaning) 