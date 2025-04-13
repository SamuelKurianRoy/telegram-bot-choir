from concurrent.futures import ThreadPoolExecutor
from googleapiclient.http import MediaIoBaseDownload
import io
import pandas as pd
from googleapiclient.discovery import build
from google.oauth2 import service_account
import json
import logging
from telegram.ext import Application, CommandHandler, ConversationHandler, MessageHandler, filters, CallbackContext, ContextTypes
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
import re
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import pandas as pd
from indicnlp.tokenize import indic_tokenize
import time
import sys
from datetime import datetime, date
import streamlit as st
import os
import asyncio
import threading

# Ensure an event loop exists for the current thread
try:
    asyncio.get_running_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

 
 
try :
 
 # Check for missing environment variables
 lines = [st.secrets[f"l{i}"] for i in range(1, 29)]
 private_key = "\n".join(lines)
 
 service_account_data = {
     "type": st.secrets["type"],
     "project_id": st.secrets["project_id"],
     "private_key_id": st.secrets["private_key_id"],
     "private_key": private_key,
     "client_email": st.secrets["client_email"],
     "client_id": st.secrets["client_id"],
     "auth_uri": st.secrets["auth_uri"],
     "token_uri": st.secrets["token_uri"],
     "auth_provider_x509_cert_url": st.secrets["auth_provider_x509_cert_url"],
     "client_x509_cert_url": st.secrets["client_x509_cert_url"],
     "universe_domain": st.secrets["universe_domain"],
 }
 
 # Set the file IDs from environment variables
 HLCFILE_ID = st.secrets["HLCFILE_ID"]
 TFILE_ID = st.secrets["TFILE_ID"]
 FILE_ID = st.secrets["FILE_ID"]
 TOKEN = st.secrets["TOKEN"]
 
 SCOPES = ["https://www.googleapis.com/auth/drive"]
 
 print("✅ Environment variables loaded successfully!")
 
 # Save the JSON to a temporary file
 KEY_PATH = "/tmp/service_account.json"
 with open(KEY_PATH, "w") as f:
    json.dump(service_account_data, f) 
 # Set the GOOGLE_APPLICATION_CREDENTIALS environment variable
 os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = KEY_PATH
 
 # Enable logging
 # --- Bot/System logger setup ---
 # --- Bot Logger setup ---
 # --- Bot Logger setup with handler check for Streamlit re-runs ---
 bot_logger = logging.getLogger("telegram_bot")
 if not bot_logger.handlers:
    bot_logger.setLevel(logging.INFO)
  
    # Console handler (safe & simple)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter('%(message)s'))
    bot_logger.addHandler(console_handler)
    
    # File handler for bot logs with UTF-8 (emoji support)
    file_handler = logging.FileHandler("bot_log.txt", encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
    bot_logger.addHandler(file_handler)

 
 # --- User Interaction logger setup ---
 # --- User Interaction logger setup with handler check ---
 user_logger = logging.getLogger("user_logger")
 if not user_logger.handlers:
    user_logger.setLevel(logging.INFO)
    user_logger.propagate = False

    user_handler = logging.FileHandler("user_log.txt", encoding='utf-8')
    user_handler.setFormatter(logging.Formatter("%(asctime)s - %(message)s"))
    user_logger.addHandler(user_handler)

 
 # Optional: suppress noisy loggers
 logging.getLogger("httpx").setLevel(logging.WARNING)
  
 # Authenticate and build the drive service
 creds = service_account.Credentials.from_service_account_file(KEY_PATH, scopes=SCOPES)
 drive_service = build("drive", "v3", credentials=creds)
 
 dfH = None   # Hymn List
 dfL = None   # Lyric List
 dfC = None   # Convention List
 yr23 = None  # 2023 dataset
 yr24 = None  # 2024 dataset
 yr25 = None  # 2025 dataset
 df   = None  # "Sheet 1" from the main file
 dfTH = None  # Hymn sheet from Tune Database
 dfTD = None  # Doxology sheet from Tune Database

 def robust_download(downloader, max_retries=5):
     retries = 0
     done = False
     while not done and retries < max_retries:
         try:
             # Log the attempt
             print(f"Attempt {retries + 1}/{max_retries}: Downloading next chunk...")
             _, done = downloader.next_chunk()
             print("Chunk downloaded successfully.")
         except Exception as e:
             retries += 1
             bot_logger.error(f"Error on attempt {retries}/{max_retries}: {e}")
             time.sleep(2 ** retries)  # Exponential backoff
     if not done:
         raise TimeoutError("Download did not complete after multiple retries.")
 

 def load_datasets():
    """
    Downloads and loads all datasets from Google Drive. Updates the global
    dataset variables so that the bot uses the latest data.
    """
    global dfH, dfL, dfC, yr23, yr24, yr25, df, dfTH, dfTD

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
        # Load the sheets from the Index Database
        try:
            dfH = pd.read_excel(file_data, sheet_name="Hymn List")
            print("✅ Successfully loaded 'Hymn List'.")
        except ValueError:
            logging.warning("Sheet 'Hymn List' not found in Index Database.")
        try:
            dfL = pd.read_excel(file_data, sheet_name="Lyric List")
            print("✅ Successfully loaded 'Lyric List'.")
        except ValueError:
            logging.warning("Sheet 'Lyric List' not found in Index Database.")
        try:
            dfC = pd.read_excel(file_data, sheet_name="Convention List")
            print("✅ Successfully loaded 'Convention List'.")
        except ValueError:
            logging.warning("Sheet 'Convention List' not found in Index Database.")
    except Exception as e:
        raise Exception(f"Error loading Index Database: {e}")
        
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
            print(f"✅ Successfully loaded '{sheet}'.")
        except ValueError:
            logging.error(f"❌ Sheet '{sheet}' not found.")
    yr23, yr24, yr25, df = sheets["2023"], sheets["2024"], sheets["2025"], sheets["Sheet 1"]
    
    # --- Load Tune Database ---
    TFILE_ID = st.secrets["TFILE_ID"]
    if not TFILE_ID:
        logging.error("❌ TFILE_ID is missing from environment variables.")
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
                print(f"Tune Database Download: {int(status.progress() * 100)}%")
            file_data.seek(0)
            
            try:
                dfTH = pd.read_excel(file_data, sheet_name="Hymn")
                print("✅ Successfully loaded 'Hymn' sheet from Tune Database.")
            except ValueError:
                logging.warning("⚠️ Sheet 'Hymn' not found in Tune Database.")
            try:
                dfTD = pd.read_excel(file_data, sheet_name="Doxology")
                print("✅ Successfully loaded 'Doxology' sheet from Tune Database.")
            except ValueError:
                logging.warning("⚠️ Sheet 'Doxology' not found in Tune Database.")
        except Exception as e:
            raise Exception(f"Failed to load Tune Database: {e}")
    return  dfH, dfL, dfC, yr23, yr24, yr25, df,dfTH, dfTD
    
 
 dfH, dfL, dfC, yr23, yr24, yr25, df,dfTH, dfTD = load_datasets()
 
 def yrDataPreprocessing():
 
    yr23.dropna(inplace=True)
    yr23.columns = yr23.iloc[0]
    yr23.drop(index=1,inplace=True)
    yr23.reset_index(drop=True,inplace=True)
    yr23['Date'] = pd.to_datetime(yr23['Date']).dt.date
 
    yr24.dropna(inplace=True)
    yr24.columns = yr24.iloc[0]
    yr24.drop(index=1,inplace=True)
    yr24.reset_index(drop=True,inplace=True)
    yr24['Date'] = pd.to_datetime(yr24['Date']).dt.date
 
    Themes= yr25['Unnamed: 6']
    yr25.drop('Unnamed: 6',axis=1,inplace=True)
    yr25.dropna(inplace=True)
    yr25.columns = yr25.iloc[0]
    yr25.drop(index=1,inplace=True)
    yr25.reset_index(drop=True,inplace=True)
    yr25['Date'] = pd.to_datetime(yr25['Date']).dt.date
 
 
 yrDataPreprocessing()
 
 
 df.dropna(inplace=True)
 df.shape
 df= df[pd.to_datetime(df['Date'],errors='coerce').notna()]
 df = df[df['Date'].notna()]
 df.reset_index(drop=True,inplace=True)
 df['Date'] = pd.to_datetime(df['Date']).dt.date
 
 def standardize_song_columns(df):
     standardized_df = df.copy()
     song_columns = [col for col in df.columns if col != 'Date']
     
     for col in song_columns:
         standardized_df[col] = standardized_df[col].astype(str).apply(lambda x: re.sub(r'\s+', '', x))
     
     return standardized_df
 df = standardize_song_columns(df)
 
 
 
 
 def standardize_hlc_value(value):
     
     # Replace multiple consecutive hyphens with a single hyphen
     value = re.sub(r'-+', '-', value)
     # Remove spaces around the hyphen and strip extra spaces
     value = re.sub(r'\s*-+\s*', '-', value).strip()
     return value
 
     
 
 
 def ChoirVocabulary():
    def HymnVocabulary():
        # Extract hymns from the '1st Song', '2nd Song', '3rd Song', '4th Song', and '5th Song' columns
        hymns = []
        for column in ['1st Song', '2nd Song', '3rd Song', '4th Song', '5th Song']:
            try:
                # Drop original NaNs and convert the column to strings
                col_data = df[column].dropna().astype(str)
                # Filter rows that contain 'H'
                filtered = col_data[col_data.str.contains('H')]
                # Extract the first group of digits
                extracted = filtered.str.extract(r'(\d+)')[0]
                # Drop any NaN values resulting from extraction
                valid_numbers = extracted.dropna()
                # Convert the extracted digits to integers and add them to the list
                if not valid_numbers.empty:
                    hymns += valid_numbers.astype(int).tolist()
            except Exception as e:
                # Optionally log the error (e.g., print(e)) and continue processing.
                continue

        # Create a Pandas Series with the hymn numbers
        Hymn = pd.Series(hymns, name='Hymn no')
        # Get unique hymn numbers and sort them
        unique_sorted_hymn = pd.Series(Hymn.unique(), name='Hymn').sort_values().reset_index(drop=True)
        return unique_sorted_hymn

    def LyricVocabulary():
        # Extract lyric hymns from the '1st Song', '2nd Song', '3rd Song', '4th Song', and '5th Song' columns
        lyric = []
        for column in ['1st Song', '2nd Song', '3rd Song', '4th Song', '5th Song']:
            try:
                col_data = df[column].dropna().astype(str)
                filtered = col_data[col_data.str.contains('L')]
                extracted = filtered.str.extract(r'(\d+)')[0]
                valid_numbers = extracted.dropna()
                if not valid_numbers.empty:
                    lyric += valid_numbers.astype(int).tolist()
            except Exception as e:
                continue

        Lyric = pd.Series(lyric, name='Lyric no')
        lyric_unique_sorted = pd.Series(Lyric.unique(), name="Lyric").sort_values().reset_index(drop=True)
        return lyric_unique_sorted

    def ConventionVocabulary():
        # Extract convention hymns from the '1st Song', '2nd Song', '3rd Song', '4th Song', and '5th Song' columns
        convention = []
        for column in ['1st Song', '2nd Song', '3rd Song', '4th Song', '5th Song']:
            try:
                col_data = df[column].dropna().astype(str)
                filtered = col_data[col_data.str.contains('C')]
                extracted = filtered.str.extract(r'(\d+)')[0]
                valid_numbers = extracted.dropna()
                if not valid_numbers.empty:
                    convention += valid_numbers.astype(int).tolist()
            except Exception as e:
                continue

        Convention = pd.Series(convention, name='Convention no')
        convention_unique_sorted = pd.Series(Convention.unique(), name='Convention').sort_values().reset_index(drop=True)
        return convention_unique_sorted

    def Vocabulary():
        # Create a DataFrame called vocabulary with these three series.
        # Convert numbers to strings for consistency in the vocabulary DataFrame.
        vocabulary = pd.DataFrame({
            'Hymn no': unique_sorted_hymn.astype("string"),
            'Lyric no': lyric_unique_sorted.astype("string"),
            'Convention no': convention_unique_sorted.astype("string")
        })
        vocabulary = vocabulary.fillna('')
        return vocabulary

    unique_sorted_hymn = HymnVocabulary()
    lyric_unique_sorted = LyricVocabulary()
    convention_unique_sorted = ConventionVocabulary()
    vocabulary = Vocabulary()
    return vocabulary, unique_sorted_hymn, lyric_unique_sorted, convention_unique_sorted

 

 Vocabulary, Hymn_Vocabulary, Lyric_Vocabulary, Convention_Vocabulary = ChoirVocabulary()
 VOCABULARY_CATEGORIES = {
     "Full Vocabulary": Vocabulary,
     "Hymn Vocabulary": Hymn_Vocabulary,
     "Lyric Vocabulary": Lyric_Vocabulary,
     "Convention Vocabulary": Convention_Vocabulary,
 }
 
 
 
 # Malayalam tokenizer using indic-nlp-library
 def malayalam_tokenizer(text):
     return indic_tokenize.trivial_tokenize(text, lang='ml')
 
 # TF-IDF Vectorizer setup for Hymn and Lyric
 vectorizer_hymn = TfidfVectorizer(analyzer='word', tokenizer=malayalam_tokenizer, token_pattern=None)
 tfidf_matrix_hymn = vectorizer_hymn.fit_transform(dfH['Hymn Index'])
 
 vectorizer_lyric = TfidfVectorizer(analyzer='word', tokenizer=malayalam_tokenizer, token_pattern=None)
 tfidf_matrix_lyric = vectorizer_lyric.fit_transform(dfL['Lyric Index'])
 
 vectorizer_convention = TfidfVectorizer(analyzer='word', tokenizer=malayalam_tokenizer, token_pattern=None)
 tfidf_matrix_convention = vectorizer_convention.fit_transform(dfC['Convention Index'])
 


 def find_best_match(query, category="hymn", top_n=5):
    """
    Returns the top N best matching items (Hymn no / Lyric no / Convention no) for a given query,
    skipping entries with 0 as the number.
    
    :param query: Input text
    :param category: "hymn", "lyric", or "convention"
    :param top_n: Number of top matches to return
    :return: Tuple of (list of tuples, column label). Each tuple is (number, similarity, context)
    """
    if not query.strip():
        return "Query is empty. Please provide search text."
    
    category = category.lower().strip()
    category_map = {
        "hymn": {
            "vectorizer": vectorizer_hymn,
            "tfidf": tfidf_matrix_hymn,
            "data": dfH,
            "column": "Hymn no",
            "context": "Title" if "Title" in dfH.columns else None
        },
        "lyric": {
            "vectorizer": vectorizer_lyric,
            "tfidf": tfidf_matrix_lyric,
            "data": dfL,
            "column": "Lyric no",
            "context": "Line" if "Line" in dfL.columns else None
        },
        "convention": {
            "vectorizer": vectorizer_convention,
            "tfidf": tfidf_matrix_convention,
            "data": dfC,
            "column": "Convention no",
            "context": "Title" if "Title" in dfC.columns else None
        }
    }

    if category not in category_map:
        return f"Invalid category '{category}'. Choose from hymn, lyric, or convention."
    
    config = category_map[category]
    
    # Convert the query into its vector representation
    query_vec = config["vectorizer"].transform([query])
    similarities = cosine_similarity(query_vec, config["tfidf"]).flatten()

    if similarities.max() == 0:
        return "No match found. Try a different query."
    
    # Sort indices in descending order of similarity
    top_indices = similarities.argsort()[::-1]
    results = []
    
    for idx in top_indices:
        number = config["data"].iloc[idx][config["column"]]
        if int(number) == 0:
            continue  # Skip invalid or zero entries
        
        similarity = round(float(similarities[idx]), 3)
        context = (
            str(config["data"].iloc[idx][config["context"]])
            if config["context"] and pd.notna(config["data"].iloc[idx][config["context"]])
            else None
        )
        results.append((int(number), similarity, context))
        if len(results) == top_n:
            break

    return results, config["column"]

 def song_search_index():
    """
    Interactively gets a search query and category from the user and then prints the top 5 matches.
    """
    try:
        user_query = input("Enter search text: ").strip()
        category = input("Search in (hymn/lyric/convention)? ").strip().lower()

        result = find_best_match(user_query, category)
        if isinstance(result, str):
            print(result)
            return
        
        matches, column_label = result
        # Clean the label, e.g., "Hymn no" becomes "Hymn"
        label_clean = column_label.replace(" no", "").capitalize()
        
        print(f"\nTop {len(matches)} matches for '{user_query}' in {category}:\n")
        for i, (num, score, context) in enumerate(matches, 1):
            line = f"{i}. {label_clean} {num} (Similarity: {score:.3f})"
            if context and context.strip().lower() != "none":
                line += f" — {context.strip()}"
            print(line)
    
    except Exception as e:
        print(f"An error occurred: {e}")

 
 
 def search_index(no, option):
     """
     Returns the index (number) from the corresponding DataFrame given the number and option.
     :param no: The one-based index number.
     :param option: "hymn" or "lyric".
     :return: The corresponding number or an error message.
     """
     try:
         no = int(no)
     except ValueError:
         return "Index must be an integer."
     
     if option == 'hymn':
         if no < 1 or no > len(dfH):
             return "Invalid hymn index."
         return dfH['Hymn Index'].iloc[no - 1]
     elif option == 'lyric':
         if no < 1 or no > len(dfL):
             return "Invalid lyric index."
         return dfL['Lyric Index'].iloc[no - 1]
     elif option == 'convention':
         if no < 1 or no > len(dfC):
             return "Invalid convention index."
         return dfC['Convention Index'].iloc[no - 1]
     else:
         return "Invalid option. Use 'hymn' or 'lyric'."
      
 
 
 def isVocabulary(Songs):
    songs_std = standardize_hlc_value(Songs)
    song = songs_std
    
    # Mapping prefixes to the corresponding column names
    prefix_mapping = {
        "H": "Hymn no",
        "L": "Lyric no",
        "C": "Convention no"
    }
    
    # Iterate over the possible prefixes
    for prefix, col in prefix_mapping.items():
        if song.startswith(prefix):
            # Remove prefix and any dashes/spaces, then convert to int
            number_str = song.replace(prefix, '').replace("-", '').strip()
            try:
                song_number = int(number_str)
            except ValueError:
                return f"Invalid song number: {song}"
            
            # Convert the target column values to integers,
            # filtering out values that are not valid numbers or are zeros.
            def to_int(x):
                x = x.strip()
                return int(x) if x.isdigit() and int(x) != 0 else None
            
            valid_numbers = Vocabulary[col].dropna().apply(to_int)
            valid_numbers = valid_numbers.dropna()  # Remove any None values
            
            # Check if the standardized song number is in the column
            if song_number in valid_numbers.values:
                return f"{songs_std}: {IndexFinder(songs_std)} is in the choir Vocabulary"
            else:
                return f"The Song: {Songs} was not found in the choir vocabulary"
    
    # If no valid prefix is found
    return "Invalid Response"

 def Datefinder(songs, category=None, first=False):
    First=first
    Song = standardize_hlc_value(songs)
    Found = False
    formatted_date = []
    for i in range(len(df) - 1, -1, -1):
        if Song in df.iloc[i].tolist():
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


 
   
 def IndexFinder(Song):
     song = standardize_hlc_value(Song)
     if song.startswith("H"):
         song = song.replace('H','').strip().replace("-", "")
         song = int(song)
         return dfH['Hymn Index'][song-1]
     elif song.startswith("L"):
         song = song.replace('L','').strip().replace("-", "")
         song = int(song)
         return dfL['Lyric Index'][song-1]
     elif song.startswith("C"):
         song = song.replace('C','').strip().replace("-", "")
         song = int(song)
         return dfC['Convention Index'][song-1]
     else:
         return "Invalid Number"
     
 
 def filter_hymns_by_theme(data, theme):
     """
     Filters the DataFrame for rows where the "Themes" column contains the given theme.
     """
     filtered = data[data["Themes"].str.contains(theme, case=False, na=False)]
     return filtered
 
 def hymn_filter_search(df):
     """
     Prompts the user for a theme, filters the DataFrame, and checks which hymns
     are in the Hymn_Vocabulary Series.
     Returns two lists: hymns in vocabulary and hymns not in vocabulary.
     """
     theme_input = input("Enter a theme to filter hymns: ").strip()
     filtered_df = filter_hymns_by_theme(df, theme_input)
 
     filtered_indf = []
     filtered_notindf = []
 
     if filtered_df.empty:
         print(f"No hymns found for theme: {theme_input}")
     else:
         for i in range(len(filtered_df)):
             hymn_no = filtered_df['Hymn no'].iloc[i]
             if hymn_no in Hymn_Vocabulary.values:
                 filtered_indf.append(hymn_no)
             else:
                 filtered_notindf.append(hymn_no)
 
     return filtered_indf, filtered_notindf
 
 
 def get_songs_by_date(input_date):
    """
    Accepts:
    - 'DD/MM/YYYY', 'DD-MM-YYYY'
    - 'DD/MM/YY', 'DD-MM-YY'
    - 'DD/MM', 'DD-MM'
    - 'DD' (uses current month and year)

    If no songs found on the given date, returns next available date with songs.
    """
    today = date.today()
    current_year = today.year      # <--- No hardcoding here!
    current_month = today.month

    # Normalize input: replace '-' with '/' for easier parsing
    if isinstance(input_date, str):
        input_date = input_date.replace('-', '/').strip()
        parts = input_date.split('/')

        try:
            if len(parts) == 3:
                input_date = pd.to_datetime(input_date, dayfirst=True).date()
            elif len(parts) == 2:
                day, month = map(int, parts)
                input_date = date(current_year, month, day)
            elif len(parts) == 1:
                day = int(parts[0])
                input_date = date(current_year, current_month, day)
            else:
                return "Invalid date format. Use DD, DD/MM, DD/MM/YY, or DD/MM/YYYY."
        except Exception as e:
            return f"Date parsing error: {e}"

    # Continue with rest of logic...
    # (Same as in the previous version of the function)


    # Ensure 'Date' column is datetime.date
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce').dt.date
    df.dropna(subset=['Date'], inplace=True)

    # Sort dates
    available_dates = sorted(df['Date'].unique())

    # Find songs on the input date
    matching_rows = df[df['Date'] == input_date]

    if matching_rows.empty:
        # Get the next available date with songs
        next_dates = [d for d in available_dates if d > input_date]
        if not next_dates:
            return f"No songs found on {input_date.strftime('%d/%m/%Y')} or any later date."
        next_date = next_dates[0]
        matching_rows = df[df['Date'] == next_date]
        message = f"No songs found on {input_date.strftime('%d/%m/%Y')}. Showing songs from next available date: {next_date.strftime('%d/%m/%Y')}"
    else:
        next_date = input_date
        message = f"Songs sung on {next_date.strftime('%d/%m/%Y')}"

    # Get song columns
    song_columns = [col for col in df.columns if col != 'Date']
    songs = []

    for _, row in matching_rows.iterrows():
        for col in song_columns:
            song = row[col]
            if pd.notna(song) and str(song).strip() != '':
                songs.append(song.strip())

    return {
        "date": next_date.strftime('%d/%m/%Y'),
        "message": message,
        "songs": songs
    }
 
 def Tunenofinder(no):
    try:
        no = int(no)
    except ValueError:
        return "Index must be an integer."
    
    if no < 1 or no > len(dfH):
        return "Invalid hymn index."
    
    result = dfTH[dfTH['Hymn no'] == no]['Tune Index']
    
    if not result.empty:
        # Strip whitespace from each tune name and join them on newline characters
        return "\n".join(tune.strip() for tune in result.tolist())
    else:
        return "Tune Index not found."

     
 print("Reached Telegram Bot code")
 #Telegram bot
 
 # Log messages from users
 async def log_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
     user = update.effective_user
     msg = update.message.text
     user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) sent /start")
     await update.message.reply_text("Message received!")

 async def is_authorized(update: Update) -> bool:
    """Check if the user is authorized to interact with the bot."""
    user_id = update.effective_user.id
    # List of authorized user IDs from the environment variable
    authorized_users_str = st.secrets["AUTHORIZED_USERS"]
    
    if authorized_users_str is not None:
        authorized_users = list(map(int, authorized_users_str.split(',')))
    else:
        authorized_users = []
    
    # If the user is not authorized, reply and return False
    if user_id not in authorized_users:
        await update.message.reply_text("🚫 You are not authorized to access this feature of the bot. \n Please contact the bot administrator for more information")
        return False
    
    return True
 
 async def start(update: Update, context: CallbackContext) -> None:
     user = update.effective_user
     user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) sent /start")
     """Handles the /start command."""
     welcome_text = (
    "🎵 *Welcome to the Choir Song Bot!*\n\n"
    "Use **/check**  to check if a song is in the vocabulary interactively. The bot will first ask whether to search by hymn, lyric, or convention, then prompt you for the song number.\n\n"
    "Use **/last**  to find when a song was last sung interactively. The bot will prompt you to choose the category (hymn, lyric, or convention) and then ask for the song number.\n\n"
    "Use **/search**  to search for a hymn, lyric, or convention. You can choose to search by text or by index:\n"
    "   - *Text Search:*  Provide the category and search text.\n"
    "   - *Index Search:*  Provide the category and the index number.\n\n"
    "Use **/help**  to know more about all available commands."
)

     await update.message.reply_text(welcome_text, parse_mode="Markdown")
 
 async def help_command(update: Update, context: CallbackContext) -> None:
     user = update.effective_user
     user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) asked for /help")
 
     help_text = (
    "🎵 *Choir Song Bot Help*\n\n"
    "Here are the available commands and how to use them:\n\n"
    "• **/start**\n"
    "  - *Description:* Starts the bot and shows the welcome message with basic instructions.\n"
    "  - *Example:* Simply type `/start`.\n\n"
    "• **/check**\n"
    "  - *Description:* Interactively checks if a song is in the vocabulary. You will first choose whether to search by hymn, lyric, or convention, then provide the song number.\n"
    "  - *Example:* Type `/check` and follow the prompts (e.g. choose *Hymn*, then enter `27` for song H-27).\n\n"
    "• **/last**\n"
    "  - *Description:* Interactively finds out when a song was last sung. The bot will prompt you to choose whether to search by hymn, lyric, or convention, and then ask for the song number.\n"
    "  - *Example:* Type `/last` and follow the prompts (e.g. choose *Hymn*, then enter `27` for song H-27).\n\n"
    "• **/search**\n"
    "  - *Description:* Interactive search for songs.\n"
    "  - *Options:*\n"
    "     - _By Index:_ Search by entering a line from a hymn, lyric, or convention.\n"
    "     - _By Number:_ Search by entering an index number.\n"
    "  - *Example:* Type `/search` and follow the prompts.\n\n"
    "• **/theme**\n"
    "  - *Description:* Initiates an interactive theme filter. You will be presented with a list of unique themes (collected from all comma-separated entries in the database), and you can select or type a theme to display the hymns related to it.\n"
    "  - *Example:* Type `/theme` and choose from the displayed themes, or type a custom theme like `Additional Hymns`.\n\n"
    "• **/date**\n"
    "  - *Description:* Shows the songs sung on a specific date or the next available date if none found. Accepts various date formats.\n"
    "  - *Examples:*\n"
    "     - `/date 05/04/2024`\n"
    "     - `/date 5/4`\n"
    "     - `/date 5`\n\n"
    "• **/vocabulary**\n"
    "  - *Description:* Starts the vocabulary export conversation.\n"
    "  - *Example:* Type `/vocabulary` and follow the instructions.\n\n"
    "• **/comment**\n"
    "  - *Description:* Allows you to submit comments, recommendations, or feedback directly to the bot administrator.\n"
    "  - *Example:* Type `/comment Your message here` and the bot will forward it to the administrator for review.\n\n"
    "• **/cancel**\n"
    "  - *Description:* Cancels the current operation.\n"
    "  - *Example:* If you are in a conversation, type `/cancel` to stop it.\n\n"
    "If you need further assistance, feel free to ask!"
)



 
     await update.message.reply_text(help_text, parse_mode="Markdown")
 
 
 
 
  # Conversation states
 SELECT_TYPE, ENTER_SONG = range(2)
 
 # Start /check conversation
 async def check_song_start(update: Update, context: CallbackContext) -> int:
     reply_keyboard = [["Hymn", "Lyric", "Convention"]]
     await update.message.reply_text(
         "Please choose the category:",
         reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True)
     )
     return SELECT_TYPE
 
 # Handle category selection
 async def check_song_type(update: Update, context: CallbackContext) -> int:
     song_type = update.message.text.strip().lower()
 
     if song_type not in ["hymn", "lyric", "convention"]:
         await update.message.reply_text("❌ Invalid choice. Please choose Hymn, Lyric, or Convention.")
         return SELECT_TYPE
 
     context.user_data["song_type"] = song_type[0].upper()  # Store 'H', 'L', or 'C'
 
     await update.message.reply_text(f"Please enter the {song_type} number (e.g. 27):", reply_markup=ReplyKeyboardRemove())
     return ENTER_SONG
 
 # Handle song number input
 async def check_song_number(update: Update, context: CallbackContext) -> int:
     song_number = update.message.text.strip()
     song_type = context.user_data.get("song_type")
 
     if not song_number.isdigit():
         await update.message.reply_text("❌ Please enter a valid number (e.g. 27).")
         return ENTER_SONG
 
     full_song = f"{song_type}-{song_number}"
     result = isVocabulary(full_song)
 
     await update.message.reply_text(result)
     return ConversationHandler.END

  
  #/last
 SELECT_LAST_TYPE, ENTER_LAST_SONG, ASK_SHOW_ALL = range(3)

 async def last_sung_start(update: Update, context: CallbackContext) -> int:
    reply_keyboard = [["Hymn", "Lyric", "Convention"]]
    await update.message.reply_text(
        "Please choose the category:",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return SELECT_LAST_TYPE

 async def last_sung_type(update: Update, context: CallbackContext) -> int:
    category = update.message.text.strip().lower()
    if category not in ["hymn", "lyric", "convention"]:
        await update.message.reply_text("❌ Invalid choice. Please choose Hymn, Lyric, or Convention.")
        return SELECT_LAST_TYPE

    # Store the first letter in uppercase ("H", "L", or "C")
    context.user_data["last_category"] = category[0].upper()
    await update.message.reply_text(
        f"Please enter the {category} number (e.g. 27):", reply_markup=ReplyKeyboardRemove()
    )
    return ENTER_LAST_SONG
 
 async def last_sung_number(update: Update, context: CallbackContext) -> int:
    song_number = update.message.text.strip()
    if not song_number.isdigit():
        await update.message.reply_text("❌ Please enter a valid number (e.g. 27).")
        return ENTER_LAST_SONG

    category = context.user_data.get("last_category")
    full_song = f"{category}-{song_number}"
    context.user_data["last_song"] = full_song

    # Get the last sung date (first occurrence only)
    result = Datefinder(full_song, category, first=True)
    await update.message.reply_text(result)

    # Provide a reply keyboard with Yes/No options
    reply_keyboard = [["Yes", "No"]]
    await update.message.reply_text(
        "Would you like to see all the dates on which this song was sung?",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return ASK_SHOW_ALL

 
 async def last_sung_show_all(update: Update, context: CallbackContext) -> int:
    reply = update.message.text.strip().lower()
    if reply == "yes":
        category = context.user_data.get("last_category")
        full_song = context.user_data.get("last_song")
        result = Datefinder(full_song, category, first=False)
        await update.message.reply_text(result, reply_markup=ReplyKeyboardRemove())
    else:
        await update.message.reply_text("(❁´◡`❁)", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END
 


 # Telegram command handler for /tune command

 async def tune_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Check if the user is authorized
    if not await is_authorized(update):
        return

    # Log the received command (optional)
    user = update.effective_user
    user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) sent /tune")

    # Check if the hymn number was provided as an argument
    if not context.args:
        await update.message.reply_text("Please provide a hymn number. For example: /tune 75")
        return

    hymn_no = context.args[0]

    # Get the tune index using your function
    tune_result = Tunenofinder(hymn_no)

    # Reply to the user with the output
    await update.message.reply_text(tune_result)


 
 
 #/search command
 SEARCH_METHOD, INDEX_CATEGORY, INDEX_TEXT, NUMBER_CATEGORY, NUMBER_INPUT = range(5)
 
 # --- Entry point ---
 async def search_start(update: Update, context: CallbackContext) -> int:
     user = update.effective_user
     user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) started /search")
 
     keyboard = [["By Index", "By Number"]]
     reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
     await update.message.reply_text("How would you like to search?", reply_markup=reply_markup)
     return SEARCH_METHOD
 
 # --- Choose method: By Index or By Number ---
 async def search_method_choice(update: Update, context: CallbackContext) -> int:
     method = update.message.text.strip().lower()
     user = update.effective_user
 
     if method == "by index":
         user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) chose to search by index (text query)")
         keyboard = [["Hymn", "Lyric", "Convention"]]
         reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
         await update.message.reply_text("Please select the category for your text search:", reply_markup=reply_markup)
         return INDEX_CATEGORY
 
     elif method == "by number":
         user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) chose to search by number (index)")
         keyboard = [["Hymn", "Lyric", "Convention"]]
         reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
         await update.message.reply_text("Please select the category:", reply_markup=reply_markup)
         return NUMBER_CATEGORY
 
     else:
         await update.message.reply_text("Invalid choice. Please choose 'By Index' or 'By Number'.")
         return SEARCH_METHOD
 
 # --- For 'By Index': Choose category ---
 async def search_index_category(update: Update, context: CallbackContext) -> int:
     category = update.message.text.strip().lower()
 
     if category not in ["hymn", "lyric", "convention"]:
         await update.message.reply_text("Invalid choice. Please select either 'Hymn', 'Lyric' or 'Convention'.")
         return INDEX_CATEGORY
 
     context.user_data["index_search_category"] = category
     await update.message.reply_text("Now, please type your search text:", reply_markup=ReplyKeyboardRemove())
     return INDEX_TEXT
 
 # --- For 'By Index': Enter search text ---
 async def search_by_index(update: Update, context: CallbackContext) -> int:
    user = update.effective_user
    category = context.user_data.get("index_search_category")
    query = update.message.text.strip()

    result = find_best_match(query, category)

    # If result is an error message (string), return it directly
    if isinstance(result, str):
        await update.message.reply_text(result)
        return ConversationHandler.END

    matches, column_label = result

    # Map category to prefix
    prefix_map = {
        "hymn": "H-",
        "lyric": "L-",
        "convention": "C-"
    }

    label_clean = category.capitalize()
    prefix = prefix_map.get(category, "")

    # Optional: Filter out zero similarity matches (if desired)
    # matches = [m for m in matches if m[1] > 0]

    reply_lines = [f"Top {len(matches)} matches for '{query}' in {category}:\n"]
    for i, (num, score, context_text) in enumerate(matches, 1):
        line = f"{i}. {prefix}{num}: {IndexFinder(f'{prefix}{num}')} (Similarity: {score:.3f})"
        if context_text and str(context_text).strip().lower() != "none":
            line += f" — {context_text.strip()}"
        reply_lines.append(line)

    reply = "\n".join(reply_lines)
    await update.message.reply_text(reply)

    user_logger.info(
        f"{user.full_name} (@{user.username}, ID: {user.id}) searched by index: {query} in {category}"
    )
    return ConversationHandler.END


 
 # --- For 'By Number': Choose category ---
 async def search_number_category(update: Update, context: CallbackContext) -> int:
     category = update.message.text.strip().lower()
 
     if category not in ["hymn", "lyric", "convention"]:
         await update.message.reply_text("Invalid choice. Please select either 'Hymn', 'Lyric' or 'Convention'.")
         return NUMBER_CATEGORY
 
     context.user_data["number_search_category"] = category
     await update.message.reply_text("Please enter the index number:", reply_markup=ReplyKeyboardRemove())
     return NUMBER_INPUT
 
 # --- For 'By Number': Enter index number ---
 async def search_by_number(update: Update, context: CallbackContext) -> int:
     user = update.effective_user
     category = context.user_data.get("number_search_category")
     text = update.message.text.strip()
 
     try:
         index_num = int(text)
     except ValueError:
         await update.message.reply_text("Index must be an integer. Please enter a valid index number:")
         return NUMBER_INPUT
 
     result = search_index(index_num, category)
     await update.message.reply_text(f"Search result of {category[0].upper()}-{index_num}: {result}")
     user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) searched by number: {index_num} in {category}")
     return ConversationHandler.END
 
 
 
 
 # Step 1: Start vocabulary conversation
 CATEGORY_SELECTION, EXPORT_CONFIRMATION = range(2)
 async def start_vocabulary(update: Update, context: CallbackContext) -> int:
    user = update.effective_user

    if not await is_authorized(update):
        user_logger.warning(f"Unauthorized access attempt by {user.full_name} (@{user.username}, ID: {user.id})")
        return ConversationHandler.END

    user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) started /vocabulary")

    keyboard = [
        ["Full Vocabulary", "Hymn Vocabulary"],
        ["Lyric Vocabulary", "Convention Vocabulary"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
    await update.message.reply_text(
        "📚 Please choose a vocabulary category:", reply_markup=reply_markup
    )
    return CATEGORY_SELECTION

 # Step 2: Process category selection and show preview
 async def category_selection(update: Update, context: CallbackContext) -> int:
     user_choice = update.message.text.strip()
     if user_choice not in VOCABULARY_CATEGORIES:
         await update.message.reply_text("⚠️ Invalid choice. Please use /vocabulary again.")
         return CATEGORY_SELECTION
 
     data = VOCABULARY_CATEGORIES[user_choice]
 
     # Convert Series to DataFrame if needed
     
     # If it's a Series, convert it to a DataFrame for consistency.
     if isinstance(data, pd.Series):
         data = data.to_frame(name=user_choice)
     # For "Full Vocabulary", remove rows where all values are zero.
     if user_choice == "Full Vocabulary":
         data = data[(data != 0).any(axis=1)]
     else:
         # For Series-based vocabularies, remove rows where the value is zero.
         data = data[data[user_choice] != 0]
 
     # Store the cleaned data and filename in user_data.
     context.user_data["export_data"] = data
     context.user_data["export_filename"] = f"{user_choice}.xlsx"
 
     # Show a preview (first 10 rows) of the data.
     preview_text = f"📋 {user_choice} Preview:\n" + data.head(10).to_string(index=False)
     await update.message.reply_text(preview_text)
 
     # Ask if the user wants to export the data as Excel
     
 
 
     # Ask the user if they want to export the data.
     keyboard = [["Yes", "No"]]
     reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
     await update.message.reply_text("📂 Would you like to export this as an Excel file?", reply_markup=reply_markup)
     return EXPORT_CONFIRMATION
 
 # Step 3: Handle the export confirmation.
 async def export_confirmation(update: Update, context: CallbackContext) -> int:
     user = update.effective_user
     response = update.message.text.strip().lower()
     if response == "yes":
         if "export_data" in context.user_data:
             data = context.user_data["export_data"]
             filename = context.user_data["export_filename"]
 
             # Convert the DataFrame to an in-memory Excel file.
             output = io.BytesIO()
             with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                 data.to_excel(writer, sheet_name="Vocabulary", index=False)
             output.seek(0)  # Reset the pointer to the beginning of the file
 
             await update.message.reply_document(
                 document=output,
                 filename=filename,
                 caption="📂 Here is your vocabulary data in Excel format."
             )
             user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) exported vocabulary as Excel.")
         else:
             await update.message.reply_text("⚠️ No data found for export.")
             user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) attempted to export but no data was found.")
     elif response == "no":
         if "export_data" in context.user_data:
             data = context.user_data["export_data"]
             full_vocab = data.to_string(index=False)
             # Send the full vocabulary as text (using Markdown formatting for a code block)
             await update.message.reply_text(
                 f"Here is the full vocabulary:\n```\n{full_vocab}\n```",
                 parse_mode="Markdown",
                 reply_markup=ReplyKeyboardRemove()
             )
             user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) viewed vocabulary as text.")
         else:
             await update.message.reply_text("⚠️ No data found.")
             user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) attempted to view text but no data was found.")
     else:
         await update.message.reply_text("⚠️ Invalid choice. Please reply with 'Yes' or 'No'.")
         return EXPORT_CONFIRMATION
 
     return ConversationHandler.END
 
#/theme

# Define unique conversation states:
 THEME_SELECTION = 1
 YEAR_FILTER = 2

# Step 1: List available unique themes and prompt user
 async def filter_theme(update: Update, context: CallbackContext) -> int:
    """
    Lists available unique themes and prompts the user to choose.
    Splits comma-separated themes and flattens the list.
    """
    user = update.effective_user
    user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) sent /theme")

    # Get unique themes from the DataFrame, splitting by comma if necessary
    all_themes = dfH["Themes"].dropna().str.split(",").explode().str.strip().unique()
    themes = sorted(all_themes)

    # Build keyboard layout (2 themes per row)
    keyboard = [themes[i:i+2] for i in range(0, len(themes), 2)]
    
    await update.message.reply_text(
        "🎯 *Available Themes:*\nPlease select or type one of the themes below:",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    )

    return THEME_SELECTION

# Step 2: Process the theme selection
 async def handle_theme_selection(update: Update, context: CallbackContext) -> int:
    """
    Handles the user's theme selection by filtering the hymns,
    displays them grouped as known/unknown, and then asks
    if the user wants to filter by year.
    """
    theme_input = update.message.text.strip()
    # Save theme in user_data for later
    context.user_data["theme_input"] = theme_input

    filtered_df = filter_hymns_by_theme(dfH, theme_input)

    if filtered_df.empty:
        await update.message.reply_text(
            f"😕 No hymns found for theme: *{theme_input}*",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END

    # Instead of storing formatted strings, store raw hymn numbers.
    known_hymns = []
    unknown_hymns = []

    for _, row in filtered_df.iterrows():
        hymn_no = row["Hymn no"]
        if hymn_no in Hymn_Vocabulary.values:
            known_hymns.append(hymn_no)
        else:
            unknown_hymns.append(hymn_no)

    # Build display lines for known and unknown hymns
    display_known = [f"H-{h} - {dfH[dfH['Hymn no'] == h]['Hymn Index'].values[0]}" for h in known_hymns]
    display_unknown = [f"H-{h} - {dfH[dfH['Hymn no'] == h]['Hymn Index'].values[0]}" for h in unknown_hymns]

    message_parts = [f"🎼 *Hymns related to theme:* `{theme_input}`\n"]

    if display_known:
        message_parts.append("✅ *Choir Knows:*\n" + "\n".join(display_known))
    else:
        message_parts.append("❌ *No known hymns found in this theme.*")

    if display_unknown:
        message_parts.append("\n❌ *Choir Doesn't Know:*\n" + "\n".join(display_unknown) +
                             "\n\n*Note:* A known song may appear here if not sung in the past 3 years.")
    else:
        message_parts.append("\n🎉 *Choir knows all hymns in this theme!*")

    await update.message.reply_text(
        "\n\n".join(message_parts),
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove()
    )

    # Store the raw hymn numbers for later processing in year filtering
    context.user_data["known_hymns"] = known_hymns
    context.user_data["unknown_hymns"] = unknown_hymns

    # Ask the user if they want to filter by year
    await update.message.reply_text(
        "📅 Do you want to filter these hymns to see Songs Sung this year?",
        reply_markup=ReplyKeyboardMarkup([["Yes", "No"]], one_time_keyboard=True, resize_keyboard=True)
    )
    return YEAR_FILTER

# Step 3: Ask the user if they want year filtering
 async def handle_year_filter(update: Update, context: CallbackContext) -> int:
    reply = update.message.text.strip().lower()
    if reply != "yes":
        await update.message.reply_text("Okay! No year filtering applied.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    s_year = datetime.now().year  # Automatically get current year

    def get_last_sung_date(hymn_code):
        result = Datefinder(songs=hymn_code, first=True)
        if result and len(result) >= 10:
            try:
                return datetime.strptime(result[-10:], "%d/%m/%Y")
            except:
                return None
        return None

    # Group by year: Expect hymn_list to contain raw hymn numbers.
    def group_by_year(hymn_list):
        sung, not_sung = [], []
        for h in hymn_list:
            hymn_code = f"H-{h}"
            date_obj = get_last_sung_date(hymn_code)
            # Retrieve hymn index from DataFrame
            index = dfH[dfH['Hymn no'] == h]['Hymn Index'].values[0]
            if date_obj and date_obj.year == s_year:
                sung.append(f"{hymn_code} - {index}")
            else:
                not_sung.append(f"{hymn_code} - {index}")
        return sung, not_sung

    # Retrieve stored hymn numbers and theme from user_data
    known = context.user_data.get("known_hymns", [])
    unknown = context.user_data.get("unknown_hymns", [])
    theme = context.user_data.get("theme_input", "")

    sung_known, not_sung_known = group_by_year(known)
    # For unknown hymns, only the "not sung" part is needed.
    not_sung_unknown = group_by_year(unknown)[1]

    message_parts = [f"📅 *Theme:* `{theme}` – *Year:* {s_year}"]

    if sung_known:
        message_parts.append("\n✅ *Songs that were Sung:*\n" + "\n".join(sung_known))
    if not_sung_known:
        message_parts.append("\n❌ *Songs that were Not Sung:*\n" + "\n".join(not_sung_known))
    if not_sung_unknown:
        message_parts.append("\n🚫 *Songs Choir Doesn't Know:*\n" + "\n".join(not_sung_unknown))

    await update.message.reply_text("\n\n".join(message_parts), parse_mode="Markdown")
    return ConversationHandler.END

# Fallback handler
 async def cancel(update: Update, context: CallbackContext) -> int:
    user = update.effective_user
    user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) sent /cancel")
    await update.message.reply_text("Operation canceled.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

 
 #/date
 async def date_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        input_date = " ".join(context.args)
        result = get_songs_by_date(input_date)
        
        if isinstance(result, dict):
            songs_text = "\n".join(f"{i+1}. {s}" for i, s in enumerate(result["songs"]))
            response = f"{result['message']}:\n\n{songs_text}"
        else:
            response = result  # This will be the error message from get_songs_by_date
    else:
        response = "Please provide a date. Usage: `/date DD/MM/YYYY`, `/date DD/MM`, or `/date DD`"

    await update.message.reply_text(response, parse_mode='Markdown')


 COMMENT = 1

# Step 1: Command to start commenting
 async def start_comment(update: Update, context: CallbackContext) -> int:
    user = update.effective_user
    user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) started commenting.")
    
    # Ask user to provide their comment
    await update.message.reply_text(
        "Please type your comment, recommendation, or thoughts below. You can also type /cancel to exit."
    )
    return COMMENT

# Step 2: Process the comment
 async def process_comment(update: Update, context: CallbackContext) -> int:
    user = update.effective_user
    comment = update.message.text.strip()
    
    # Load the admin's user ID from environment variables
    admin_id = st.secrets("ADMIN_ID")  # Ensure this is set in your environment variables
    
    if admin_id:
        try:
            admin_id = int(admin_id)  # Convert the admin ID to an integer
            # Send the comment to the admin via a private message
            await context.bot.send_message(admin_id, f"New comment from {user.full_name} (@{user.username}, ID: {user.id}):\n\n{comment}")
        except ValueError:
            user_logger.error("Invalid admin ID in environment variables.")
    
    # Save the comment to a file (comments.txt)
    with open("comments.txt", "a", encoding="utf-8") as file:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        file.write(f"{timestamp} - {user.full_name} (@{user.username}, ID: {user.id}) said:\n{comment}\n\n")
    
    # Confirm to the user that their comment has been received
    await update.message.reply_text("Thank you for your feedback! We appreciate your thoughts.")
    user_logger.info(f"Comment from {user.full_name} (@{user.username}, ID: {user.id}): {comment}")
    
    return ConversationHandler.END
 async def refresh_command(update: Update, context: CallbackContext) -> None:
    """
    This command is restricted to the admin and calls load_datasets() to
    refresh all datasets.
    """
    admin_id_str = st.secrets("ADMIN_ID")
    if not admin_id_str:
        await update.message.reply_text("ADMIN_ID environment variable is not set.")
        return
    try:
        admin_id = int(admin_id_str)
    except ValueError:
        await update.message.reply_text("ADMIN_ID environment variable is invalid.")
        return
    
    user = update.effective_user
    if user.id != admin_id:
        await update.message.reply_text("You are not authorized to use this command.")
        return

    try:
        global dfH, dfL, dfC, yr23, yr24, yr25, df,dfTH, dfTD
        dfH, dfL, dfC, yr23, yr24, yr25, df,dfTH, dfTD = load_datasets()  # Refresh all datasets
        await update.message.reply_text("Datasets reloaded successfully!")
    except Exception as e:
        await update.message.reply_text(f"Error reloading datasets: {e}")
        logging.error(f"Error in /refresh command: {e}")

# Step 3: Handle /cancel if the user wants to exit
 async def cancel_comment(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text("Comment process has been canceled.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END
 
 
 
 
 async def main():
     """Starts the bot and registers command handlers."""
     app = Application.builder().token(TOKEN).build()
 
     conv_handler = ConversationHandler(
         entry_points=[CommandHandler("vocabulary", start_vocabulary)],
         states={
             CATEGORY_SELECTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, category_selection)],
             EXPORT_CONFIRMATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, export_confirmation)],
         },
         fallbacks=[CommandHandler("cancel", cancel)]
     )
 
     search_conv_handler = ConversationHandler(
     entry_points=[CommandHandler("search", search_start)],
     states={
         SEARCH_METHOD: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_method_choice)],
         INDEX_CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_index_category)],
         INDEX_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_by_index)],
         NUMBER_CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_number_category)],
         NUMBER_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_by_number)],
     },
     fallbacks=[CommandHandler("cancel", cancel)],
 )
     theme_handler = ConversationHandler(
    entry_points=[CommandHandler("theme", filter_theme)],
    states={
    THEME_SELECTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_theme_selection)],
    YEAR_FILTER: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_year_filter)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)
     
     check_conv = ConversationHandler(
    entry_points=[CommandHandler("check", check_song_start)],
    states={
        SELECT_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, check_song_type)],
        ENTER_SONG: [MessageHandler(filters.TEXT & ~filters.COMMAND, check_song_number)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)
     
     last_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("last", last_sung_start)],
    states={
        SELECT_LAST_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, last_sung_type)],
        ENTER_LAST_SONG: [MessageHandler(filters.TEXT & ~filters.COMMAND, last_sung_number)],
        ASK_SHOW_ALL: [MessageHandler(filters.TEXT & ~filters.COMMAND, last_sung_show_all)],
    },
    fallbacks=[CommandHandler("cancel", cancel)]
)
     comment_handler = ConversationHandler(
    entry_points=[CommandHandler('comment', start_comment)],
    states={
        COMMENT: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, process_comment)
        ]
    },
    fallbacks=[CommandHandler('cancel', cancel_comment)]
)
 
 
 
 
     app.add_handler(CommandHandler("start", start))
     app.add_handler(CommandHandler("help", help_command))
     app.add_handler(CommandHandler("date", date_command))
     app.add_handler(CommandHandler("refresh", refresh_command))
     app.add_handler(CommandHandler("tuneno", tune_command))
     app.add_handler(last_conv_handler)
     app.add_handler(check_conv)
     app.add_handler(theme_handler)
     app.add_handler(search_conv_handler)
     app.add_handler(conv_handler)
     app.add_handler(comment_handler)
     
 
     user_logger.info("🤖 Bot is running...")
     await app.run_polling()
 
 if __name__ == "__main__":
     asyncio.run(main()) 
 def start_bot_in_thread():
    """Starts the bot in a background thread."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)  # Set the event loop for this thread
    loop.run_until_complete(main())  # Run the bot

 def run_bot():
    """Starts the bot in a new thread."""
    bot_thread = threading.Thread(target=start_bot_in_thread)
    bot_thread.daemon = True  # Ensure the thread exits when the program ends
    bot_thread.start()
    
 
except KeyboardInterrupt:
    print("\n🛑 Bot stopped manually by user (Ctrl + C).")
    bot_logger.info(f"\nBot was stoped by the user\n\n")
    sys.exit(0)
except Exception as e:
    print(f"\n❌ An unexpected error occurred: {e}")
    bot_logger.error(f"\n❌ An unexpected error occurred: {e}")
    bot_logger.info("\n")
    sys.exit(1) 
 