import pandas as pd
import io
import logging
from googleapiclient.http import MediaIoBaseDownload


def load_datasets(drive_service, st):
    """
    Downloads and loads all datasets from Google Drive. Updates the global
    dataset variables so that the bot uses the latest data.
    Returns: dfH, dfL, dfC, yr23, yr24, yr25, df, dfTH, dfTD
    """
    # --- Load Index Database (HLCFILE) ---
    HLCFILE_ID = st.secrets["HLCFILE_ID"]
    if not HLCFILE_ID:
        raise ValueError("HLCFILE_ID is missing from environment variables.")
    request = drive_service.files().export_media(
        fileId=HLCFILE_ID,
        mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    file_data = io.BytesIO()
    downloader = MediaIoBaseDownload(file_data, request, chunksize=1024 * 256)
    done = False
    while not done:
        status, done = downloader.next_chunk()
        logging.info(f"Index Database Download: {int(status.progress() * 100)}%")
    file_data.seek(0)
    try:
        dfH = pd.read_excel(file_data, sheet_name="Hymn List")
    except ValueError:
        dfH = None
        logging.warning("Sheet 'Hymn List' not found in Index Database.")
    try:
        dfL = pd.read_excel(file_data, sheet_name="Lyric List")
    except ValueError:
        dfL = None
        logging.warning("Sheet 'Lyric List' not found in Index Database.")
    try:
        dfC = pd.read_excel(file_data, sheet_name="Convention List")
    except ValueError:
        dfC = None
        logging.warning("Sheet 'Convention List' not found in Index Database.")

    # --- Load Main Excel File ---
    FILE_ID = st.secrets["FILE_ID"]
    request = drive_service.files().get_media(fileId=FILE_ID)
    file_data = io.BytesIO()
    downloader = MediaIoBaseDownload(file_data, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    file_data.seek(0)
    try:
        xls = pd.ExcelFile(file_data)
        logging.info("Main Excel file loaded successfully.")
    except Exception as e:
        raise Exception(f"Failed to load Excel file: {e}")
    sheets = {"2023": None, "2024": None, "2025": None, "Sheet 1": None}
    for sheet in sheets:
        try:
            sheets[sheet] = pd.read_excel(xls, sheet_name=sheet)
        except ValueError:
            logging.error(f"❌ Sheet '{sheet}' not found.")
    yr23, yr24, yr25, df = sheets["2023"], sheets["2024"], sheets["2025"], sheets["Sheet 1"]

    # --- Load Tune Database ---
    TFILE_ID = st.secrets["TFILE_ID"]
    if not TFILE_ID:
        logging.error("❌ TFILE_ID is missing from environment variables.")
        dfTH, dfTD = None, None
    else:
        try:
            request = drive_service.files().export_media(
                fileId=TFILE_ID,
                mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            file_data = io.BytesIO()
            downloader = MediaIoBaseDownload(file_data, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
                logging.info(f"Tune Database Download: {int(status.progress() * 100)}%")
            file_data.seek(0)
            try:
                dfTH = pd.read_excel(file_data, sheet_name="Hymn")
            except ValueError:
                dfTH = None
                logging.warning("Sheet 'Hymn' not found in Tune Database.")
            try:
                dfTD = pd.read_excel(file_data, sheet_name="Doxology")
            except ValueError:
                dfTD = None
                logging.warning("Sheet 'Doxology' not found in Tune Database.")
        except Exception as e:
            raise Exception(f"Failed to load Tune Database: {e}")
    return dfH, dfL, dfC, yr23, yr24, yr25, df, dfTH, dfTD


def yrDataPreprocessing(yr23, yr24, yr25, dfH, dfTH):
    """
    Preprocesses the year datasets and updates columns/formats in place.
    """
    yr23.dropna(inplace=True)
    yr23.columns = yr23.iloc[0]
    yr23.drop(index=1, inplace=True)
    yr23.reset_index(drop=True, inplace=True)
    yr23['Date'] = pd.to_datetime(yr23['Date']).dt.date

    yr24.dropna(inplace=True)
    yr24.columns = yr24.iloc[0]
    yr24.drop(index=1, inplace=True)
    yr24.reset_index(drop=True, inplace=True)
    yr24['Date'] = pd.to_datetime(yr24['Date']).dt.date

    Themes = yr25['Unnamed: 6']
    yr25.drop('Unnamed: 6', axis=1, inplace=True)
    yr25.dropna(inplace=True)
    yr25.columns = yr25.iloc[0]
    yr25.drop(index=1, inplace=True)
    yr25.reset_index(drop=True, inplace=True)
    yr25['Date'] = pd.to_datetime(yr25['Date']).dt.date

    dfH['Tunes'] = dfH['Tunes'].fillna("Unknown")
    dfTH['Page no'] = dfTH['Page no'].fillna("0")


def dfcleaning(df):
    """
    Cleans the main DataFrame by dropping NaNs and ensuring date columns are correct.
    """
    df.dropna(inplace=True)
    df = df[pd.to_datetime(df['Date'], errors='coerce').notna()]
    df = df[df['Date'].notna()]
    df.reset_index(drop=True, inplace=True)
    df['Date'] = pd.to_datetime(df['Date']).dt.date
    return df


def standardize_song_columns(df):
    """
    Standardizes song columns by removing whitespace and converting to string.
    """
    standardized_df = df.copy()
    song_columns = [col for col in df.columns if col != 'Date']
    for col in song_columns:
        standardized_df[col] = standardized_df[col].astype(str).apply(lambda x: x.replace(' ', ''))
    return standardized_df 