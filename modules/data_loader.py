from googleapiclient.discovery import build
from google.oauth2 import service_account
from googleapiclient.http import MediaIoBaseDownload
import pandas as pd
import io
import logging
import os
import streamlit as st

class DataLoader:
    def __init__(self, key_path):
        self.KEY_PATH = key_path
        self.SCOPES = ["https://www.googleapis.com/auth/drive"]
        self.drive_service = self._build_drive_service()
        
        # Initialize dataframes as None
        self.dfH = None   # Hymn List
        self.dfL = None   # Lyric List
        self.dfC = None   # Convention List
        self.yr23 = None  # 2023 dataset
        self.yr24 = None  # 2024 dataset
        self.yr25 = None  # 2025 dataset
        self.df = None    # "Sheet 1" from the main file
        self.dfTH = None  # Hymn sheet from Tune Database
        self.dfTD = None  # Doxology sheet from Tune Database

    def _build_drive_service(self):
        creds = service_account.Credentials.from_service_account_file(self.KEY_PATH, scopes=self.SCOPES)
        return build("drive", "v3", credentials=creds)

    def robust_download(self, downloader, max_retries=5):
        retries = 0
        done = False
        while not done and retries < max_retries:
            try:
                print(f"Attempt {retries + 1}/{max_retries}: Downloading next chunk...")
                _, done = downloader.next_chunk()
                print("Chunk downloaded successfully.")
            except Exception as e:
                retries += 1
                logging.error(f"Error on attempt {retries}/{max_retries}: {e}")
                time.sleep(2 ** retries)  # Exponential backoff
        if not done:
            raise TimeoutError("Download did not complete after multiple retries.")

    def load_datasets(self):
        """Downloads and loads all datasets from Google Drive."""
        
        # Load Index Database
        self._load_index_database()
        
        # Load Main Excel File
        self._load_main_excel_file()
        
        # Load Tune Database
        self._load_tune_database()
        
        return (self.dfH, self.dfL, self.dfC, self.yr23, self.yr24, 
                self.yr25, self.df, self.dfTH, self.dfTD)

    def _load_index_database(self):
        HLCFILE_ID = st.secrets["HLCFILE_ID"]
        if not HLCFILE_ID:
            raise ValueError("HLCFILE_ID is missing from environment variables.")
        
        request = self.drive_service.files().export_media(
            fileId=HLCFILE_ID,
            mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        file_data = io.BytesIO()
        downloader = MediaIoBaseDownload(file_data, request, chunksize=1024 * 256)
        self.robust_download(downloader)
        file_data.seek(0)
        
        try:
            self.dfH = pd.read_excel(file_data, sheet_name="Hymn List")
            print("✅ Successfully loaded 'Hymn List'.")
        except ValueError:
            logging.warning("Sheet 'Hymn List' not found in Index Database.")
            
        try:
            self.dfL = pd.read_excel(file_data, sheet_name="Lyric List")
            print("✅ Successfully loaded 'Lyric List'.")
        except ValueError:
            logging.warning("Sheet 'Lyric List' not found in Index Database.")
            
        try:
            self.dfC = pd.read_excel(file_data, sheet_name="Convention List")
            print("✅ Successfully loaded 'Convention List'.")
        except ValueError:
            logging.warning("Sheet 'Convention List' not found in Index Database.")

    def _load_main_excel_file(self):
        FILE_ID = st.secrets["FILE_ID"]
        request = self.drive_service.files().get_media(fileId=FILE_ID)
        file_data = io.BytesIO()
        downloader = MediaIoBaseDownload(file_data, request)
        self.robust_download(downloader)
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
                print(f"✅ Successfully loaded '{sheet}'.")
            except ValueError:
                logging.error(f"❌ Sheet '{sheet}' not found.")
        
        self.yr23, self.yr24, self.yr25, self.df = (
            sheets["2023"], sheets["2024"], sheets["2025"], sheets["Sheet 1"]
        )

    def _load_tune_database(self):
        TFILE_ID = st.secrets["TFILE_ID"]
        if not TFILE_ID:
            logging.error("❌ TFILE_ID is missing from environment variables.")
            return
            
        try:
            request = self.drive_service.files().export_media(
                fileId=TFILE_ID,
                mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            file_data = io.BytesIO()
            downloader = MediaIoBaseDownload(file_data, request)
            self.robust_download(downloader)
            file_data.seek(0)
            
            try:
                self.dfTH = pd.read_excel(file_data, sheet_name="Hymn")
                print("✅ Successfully loaded 'Hymn' sheet from Tune Database.")
            except ValueError:
                logging.warning("⚠️ Sheet 'Hymn' not found in Tune Database.")
            try:
                self.dfTD = pd.read_excel(file_data, sheet_name="Doxology")
                print("✅ Successfully loaded 'Doxology' sheet from Tune Database.")
            except ValueError:
                logging.warning("⚠️ Sheet 'Doxology' not found in Tune Database.")
        except Exception as e:
            raise Exception(f"Failed to load Tune Database: {e}")

    def preprocess_year_data(self):
        """Preprocesses the year datasets."""
        if self.yr23 is not None:
            self.yr23.dropna(inplace=True)
            self.yr23.columns = self.yr23.iloc[0]
            self.yr23.drop(index=1, inplace=True)
            self.yr23.reset_index(drop=True, inplace=True)
            self.yr23['Date'] = pd.to_datetime(self.yr23['Date']).dt.date

        if self.yr24 is not None:
            self.yr24.dropna(inplace=True)
            self.yr24.columns = self.yr24.iloc[0]
            self.yr24.drop(index=1, inplace=True)
            self.yr24.reset_index(drop=True, inplace=True)
            self.yr24['Date'] = pd.to_datetime(self.yr24['Date']).dt.date

        if self.yr25 is not None:
            Themes = self.yr25['Unnamed: 6']
            self.yr25.drop('Unnamed: 6', axis=1, inplace=True)
            self.yr25.dropna(inplace=True)
            self.yr25.columns = self.yr25.iloc[0]
            self.yr25.drop(index=1, inplace=True)
            self.yr25.reset_index(drop=True, inplace=True)
            self.yr25['Date'] = pd.to_datetime(self.yr25['Date']).dt.date

        if self.dfH is not None:
            self.dfH['Tunes'] = self.dfH['Tunes'].fillna("Unknown")
        if self.dfTH is not None:
            self.dfTH['Page no'] = self.dfTH['Page no'].fillna("0")

    def clean_main_data(self):
        """Cleans the main dataframe."""
        if self.df is not None:
            self.df.dropna(inplace=True)
            self.df = self.df[pd.to_datetime(self.df['Date'], errors='coerce').notna()]
            self.df = self.df[self.df['Date'].notna()]
            self.df.reset_index(drop=True, inplace=True)
            self.df['Date'] = pd.to_datetime(self.df['Date']).dt.date
