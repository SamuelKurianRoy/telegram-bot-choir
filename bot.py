from concurrent.futures import ThreadPoolExecutor
from googleapiclient.http import MediaIoBaseDownload
import io
import pandas as pd
from googleapiclient.discovery import build
from google.oauth2 import service_account
import json
import logging
from telegram.ext import Application, CommandHandler, ConversationHandler, MessageHandler, filters, CallbackContext, ContextTypes , CallbackQueryHandler
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove , InlineKeyboardButton, InlineKeyboardMarkup
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
from googleapiclient.errors import HttpError
from telegram.constants import ParseMode
from Modules.choir import *

# Import audio downloader
try:
    from downloader import AudioDownloader
    DOWNLOADER_AVAILABLE = True
except ImportError:
    DOWNLOADER_AVAILABLE = False
    print("⚠️ Audio downloader not available. Install yt-dlp and spotdl to enable /download command.")

# Add a global variable to control the bot's running state
bot_should_run = True

# Global lock file path
LOCK_FILE = "/tmp/telegram_bot.lock"

# Add at the top of the file
STOP_SIGNAL_FILE = "/tmp/telegram_bot_stop_signal"

def acquire_lock():
    """Try to acquire a lock file to ensure only one bot instance runs."""
    try:
        # First, remove any existing lock file
        if os.path.exists(LOCK_FILE):
            print(f"Removing existing lock file: {LOCK_FILE}")
            os.remove(LOCK_FILE)
        
        # Create the lock file with our PID
        with open(LOCK_FILE, 'w') as f:
            f.write(str(os.getpid()))
        
        print(f"Lock acquired for PID {os.getpid()}")
        return True
    except Exception as e:
        print(f"Error acquiring lock: {e}")
        return False

def release_lock():
    """Release the lock file."""
    try:
        if os.path.exists(LOCK_FILE):
            # Read the PID from the file
            with open(LOCK_FILE, 'r') as f:
                pid = f.read().strip()
                
                # Only delete the file if it contains our PID
                if pid == str(os.getpid()):
                    os.remove(LOCK_FILE)
                    return True
        return False
    except Exception as e:
        print(f"Error releasing lock: {e}")
        return False

def run_bot():
    """Starts the bot."""
    global bot_should_run
    
    # Debug information
    print("=== BOT STARTUP DEBUG INFO ===")
    debug_bot_status()
    print("=============================")
    
    # Reset the flag when starting
    bot_should_run = True
    
    # Remove any existing stop signal file
    if os.path.exists(STOP_SIGNAL_FILE):
        os.remove(STOP_SIGNAL_FILE)
        print(f"Removed stop signal file: {STOP_SIGNAL_FILE}")
    
    # Try to acquire the lock
    print("Attempting to acquire lock...")
    if not acquire_lock():
        print("Another instance of the bot is already running. Aborting.")
        return False
    
    print(f"Bot starting with PID {os.getpid()}")
    
    try:
        # Run the bot in the current thread
        print("Starting main bot function...")
        asyncio.run(main())
        print("Bot stopped normally")
        return True
    except KeyboardInterrupt:
        print("\nBot was stopped by the user")
        return True
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")
        return False
    finally:
        # Release the lock
        print("Releasing lock...")
        release_lock()

def stop_bot():
    """Stops the bot gracefully by creating a stop signal file."""
    global bot_should_run
    bot_should_run = False
    
    # Create a stop signal file
    with open(STOP_SIGNAL_FILE, 'w') as f:
        f.write(str(datetime.now()))
    
    bot_logger.info("Bot stop requested")
    # Release the lock
    release_lock()
    return True

# Add this function to check for stop signal
def check_stop_signal():
    """Check if a stop signal file exists."""
    return os.path.exists(STOP_SIGNAL_FILE)

# Ensure an event loop exists for the current thread
try:
    asyncio.get_running_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

def debug_bot_status():
    """Print debug information about the bot's status."""
    print(f"Bot PID: {os.getpid()}")
    print(f"Lock file exists: {os.path.exists(LOCK_FILE)}")
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE, 'r') as f:
                pid = f.read().strip()
                print(f"Lock file PID: {pid}")
                try:
                    os.kill(int(pid), 0)
                    print(f"Process with PID {pid} exists")
                except (ValueError, ProcessLookupError):
                    print(f"Process with PID {pid} does not exist")
                except Exception as e:
                    print(f"Error checking process: {e}")
        except Exception as e:
            print(f"Error reading lock file: {e}")
    print(f"Stop signal file exists: {os.path.exists(STOP_SIGNAL_FILE)}")
    return True



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
    
    # File handler for bot logs with UTF-8 (emoji support) - overwrite each time
    file_handler = logging.FileHandler("bot_log.txt", mode='w', encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
    bot_logger.addHandler(file_handler)

 
 # --- User Interaction logger setup ---
 # --- User Interaction logger setup with handler check ---
 user_logger = logging.getLogger("user_logger")
 if not user_logger.handlers:
    user_logger.setLevel(logging.INFO)
    user_logger.propagate = False

    # Use default append mode to keep all user interactions across bot restarts
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

    global yr23, yr24, yr25, df, dfH
 
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

    dfH['Tunes'] = dfH['Tunes'].fillna("Unknown")
    dfTH['Page no'] = dfTH['Page no'].fillna("0")

 
 def dfcleaning():
  global df
  df.dropna(inplace=True)
  df.shape
  df= df[pd.to_datetime(df['Date'],errors='coerce').notna()]
  df = df[df['Date'].notna()]
  df.reset_index(drop=True,inplace=True)
  df['Date'] = pd.to_datetime(df['Date']).dt.date
 
 
 
 def standardize_song_columns():
     global df
     standardized_df = df.copy()
     song_columns = [col for col in df.columns if col != 'Date']
     
     for col in song_columns:
         standardized_df[col] = standardized_df[col].astype(str).apply(lambda x: re.sub(r'\s+', '', x))
     
     return standardized_df
 
 yrDataPreprocessing()
 dfcleaning()
 df = standardize_song_columns()
 
 BFILE_ID = st.secrets["BFILE_ID"]
 UFILE_ID = st.secrets["UFILE_ID"]
 YFILE_ID = st.secrets["YFILE_ID"]  # For download logs
 creds = service_account.Credentials.from_service_account_file(KEY_PATH, scopes=SCOPES)
 docs_service = build("docs", "v1", credentials=creds)
 print("reached before log")
 

# Initialize logger
 logging.basicConfig(level=logging.INFO)
 logger = logging.getLogger(__name__) 
 DOC_SCOPES = ["https://www.googleapis.com/auth/documents"]
 creds = service_account.Credentials.from_service_account_file(KEY_PATH, scopes=DOC_SCOPES)
 docs_service = build("docs", "v1", credentials=creds)

 def upload_log_to_google_doc(doc_id: str, log_file: str):
    """
    Uploads a local log file's contents to a Google Docs file.
    Clears the existing content and appends the new content.

    Parameters:
        doc_id (str): Google Docs file ID (e.g. COMFILE_ID, BFILE_ID, etc.)
        log_file (str): Path to the local log file (e.g. 'bot_log.txt')
    """
    if not os.path.exists(log_file):
        logger.warning(f"⚠️ Log file {log_file} does not exist.")
        return

    with open(log_file, "r", encoding="utf-8") as file:
        content = file.read().strip()

    if not content:
        logger.info(f"ℹ️ Log file {log_file} is empty. Skipping upload.")
        return

    try:
        # Step 1: Get the document content to find its current length
        doc = docs_service.documents().get(documentId=doc_id).execute()
        end_index = doc.get('body', {}).get('content', [{}])[-1].get('endIndex', 1)

        # Step 2: Clear the document (if it has any content)
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

        # Step 3: Insert new content
        requests.append({
            'insertText': {
                'location': {
                    'index': 1
                },
                'text': content
            }
        })

        # Step 4: Execute batch update
        docs_service.documents().batchUpdate(
            documentId=doc_id,
            body={'requests': requests}
        ).execute()

        logger.info(f"✅ Successfully uploaded {log_file} to Google Doc ({doc_id})")
        print("log Files Loaded")

    except HttpError as e:
        logger.error(f"❌ Failed to log due to: {e}")





 upload_log_to_google_doc(st.secrets["BFILE_ID"], "bot_log.txt")
 upload_log_to_google_doc(st.secrets["UFILE_ID"], "user_log.txt")

 # Also upload downloader log if it exists
 if os.path.exists("downloader_log.txt"):
     upload_log_to_google_doc(st.secrets["BFILE_ID"], "downloader_log.txt")

 # Function to append download entries to Google Doc (similar to comment function)
 def append_download_to_google_doc(yfile_id: str, download_entry: str):
    """
    Appends a download entry directly to a Google Docs file.
    Similar to how comments are handled.

    Parameters:
        yfile_id (str): Google Docs file ID for download logs
        download_entry (str): The download entry to append
    """
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

        print("✅ Download entry appended to Google Doc.")
    except Exception as e:
        logging.error(f"❌ Failed to append download entry to Google Doc ({yfile_id}): {e}")

 
 
 Vocabulary, Hymn_Vocabulary, Lyric_Vocabulary, Convention_Vocabulary = ChoirVocabulary()

 VOCABULARY_INDEXES = {
    "Hymn Indexes": apply_index_finder(Hymn_Vocabulary, "H"),
    "Lyric Indexes": apply_index_finder(Lyric_Vocabulary, "L"),
    "Convention Indexes": apply_index_finder(Convention_Vocabulary, "C"),
}
 # Add new columns for indexes to the vocabulary DataFrame
 Vocabulary["Hymn Index"] = VOCABULARY_INDEXES["Hymn Indexes"]
 Vocabulary["Hymn Tune"] = (
    "H-" + Vocabulary["Hymn no"].astype(str)
).apply(Tune_finder_of_known_songs)
 Vocabulary["Lyric Index"] = VOCABULARY_INDEXES["Lyric Indexes"]
 Vocabulary["Convention Index"] = VOCABULARY_INDEXES["Convention Indexes"]
 Vocabulary["Lyric Index"]  = Vocabulary["Lyric Index"].fillna('')
 Vocabulary["Convention Index"] = Vocabulary["Convention Index"].fillna('')
 # Reorder the columns as desired
 Vocabulary = Vocabulary[[
    "Hymn no", "Hymn Index", "Hymn Tune",
    "Lyric no", "Lyric Index",
    "Convention no", "Convention Index"
]]
 Hymn_Vocabulary = pd.DataFrame(Hymn_Vocabulary)
 Lyric_Vocabulary = pd.DataFrame(Lyric_Vocabulary)
 Convention_Vocabulary = pd.DataFrame(Convention_Vocabulary)
 Hymn_Vocabulary["Hymn Index"] = VOCABULARY_INDEXES["Hymn Indexes"]
 Hymn_Vocabulary["Hymn Tune"] = (
    "H-" + Vocabulary["Hymn no"].astype(str)
).apply(Tune_finder_of_known_songs)
 Lyric_Vocabulary["Lyric Index"] = VOCABULARY_INDEXES["Lyric Indexes"]
 Convention_Vocabulary["Convention Index"] = VOCABULARY_INDEXES["Convention Indexes"]

 VOCABULARY_CATEGORIES = {
     "Full Vocabulary": Vocabulary,
     "Hymn Vocabulary": Hymn_Vocabulary,
     "Lyric Vocabulary": Lyric_Vocabulary,
     "Convention Vocabulary": Convention_Vocabulary,
 }
 
 vectorizer_hymn = TfidfVectorizer(analyzer='char_wb', ngram_range=(3, 5))
 tfidf_matrix_hymn = vectorizer_hymn.fit_transform(dfH['Hymn Index'].fillna(''))
 
 # Lyric
 vectorizer_lyric = TfidfVectorizer(analyzer='char_wb', ngram_range=(3, 5))
 tfidf_matrix_lyric = vectorizer_lyric.fit_transform(dfL['Lyric Index'].fillna(''))
 
 # Convention
 vectorizer_convention = TfidfVectorizer(analyzer='char_wb', ngram_range=(3, 5))
 tfidf_matrix_convention = vectorizer_convention.fit_transform(dfC['Convention Index'].fillna(''))
 
 
 print("Reached Telegram Bot code")
 

 #Telegram bot
 authorized_users_str = st.secrets["AUTHORIZED_USERS"]
 authorized_users = list(map(int, authorized_users_str.split(','))) if authorized_users_str else []
 
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
 
 ADMIN_ID = int(st.secrets["ADMIN_ID"])

 async def start(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) sent /start")

    # Check authorization
    authorized_users_str = st.secrets["AUTHORIZED_USERS"]
    authorized_users = list(map(int, authorized_users_str.split(','))) if authorized_users_str else []

    if user.id not in authorized_users:
        # Notify admin but do NOT block user
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                f"⚠️ <b>Unauthorized user accessed /start</b>\n\n"
                f"<b>Name:</b> {user.full_name}\n"
                f"<b>Username:</b> @{user.username}\n"
                f"<b>User ID:</b> <code>{user.id}</code>"
            ),
            parse_mode="HTML"
        )

    # Proceed with regular welcome message
    welcome_text = (f"Hello {user.full_name if user.full_name else user.username}\n\n"
    "🎵 <b>Welcome to the Choir Bot!</b>\n\n"
    "This bot helps you quickly find details about choir songs!\n"
    "Simply type a song like <b>H-27</b>, <b>L-5</b>, or <b>C-12</b> and get instant info, including the last sung date.\n\n"
    "Use <b>/help</b> to explore all commands."
)

    await update.message.reply_text(welcome_text, parse_mode="HTML")


 
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
    "  - *Description:* Check if a song exists in the vocabulary or not. After typing the command, enter the song in the format H-27 (Hymn), L-14 (Lyric), or C-5 (Convention).\n"
    "  - *Example:* Type `/check`, then enter a song like `H-27`.\n\n"
    "• **/last**\n"
    "  - *Description:* Find out when a song was last sung. After typing the command, enter the song like H-27 (Hymn), L-14 (Lyric), or C-5 (Convention). You'll also have the option to view all the dates it was sung.\n"
    "  - *Example:* Type `/last`, then enter a song like `H-27`.\n\n"
    "• **/search**\n"
    "  - *Description:* Interactive search for songs.\n"
    "  - *Options:*\n"
    "     - _By Index:_ Search by entering a line from a hymn, lyric, or convention.\n"
    "     - _By Number:_ Search by entering an index number.\n"
    "  - *Example:* Type `/search` and follow the prompts.\n\n"
    "• **/tune**\n"
    "  - *Description:* Interactively find tunes by hymn number or tune index.\n"
    "  - *Options:*\n"
    "     - _By Hymn Number:_ Returns the tune(s) for a specific hymn number.\n"
    "     - _By Tune Index:_ Provides the top matching hymns using fuzzy matching on tune names.\n"
    "  - *Example:* Type `/tune` and choose either *Hymn Number* or *Tune Index*, then enter your query (e.g. `Whit` or `29`).\n\n"
    "• **/theme**\n"
    "  - *Description:* Initiates an interactive theme filter. You will be presented with a list of unique themes (collected from all comma-separated entries in the database), and you can select or type a theme to display the hymns related to it.\n"
    "  - *Example:* Type `/theme` and choose from the displayed themes, or type a custom theme like `Additional Hymns`.\n\n"
    "• **/date**\n"
    "  - *Description:* Shows the songs sung on a specific date or the next available date if none found. Accepts various date formats.\n"
    "  - *Examples:*\n"
    "     - `/date 05/04/2024`\n\n"
    "• **/vocabulary**\n"
    "  - *Description:* Starts the vocabulary export conversation.\n"
    "  - *Example:* Type `/vocabulary` and follow the instructions.\n\n"
    "• **/download**\n"
    "  - *Description:* Download audio from YouTube, Spotify, or SoundCloud links. The bot will extract the audio and send it to you as an MP3 file.\n"
    "  - *Supported platforms:* YouTube, Spotify, SoundCloud\n"
    "  - *Example:* Type `/download`, then paste a YouTube or Spotify link, and select your preferred audio quality.\n\n"
    "• **/comment**\n"
    "  - *Description:* Allows you to submit comments, recommendations, or feedback directly to the bot administrator.\n"
    "  - *Example:* Type `/comment Your message here` and the bot will forward it to the administrator for review.\n\n"
    "• **/cancel**\n"
    "  - *Description:* Cancels the current operation.\n"
    "  - *Example:* If you are in a conversation, type `/cancel` to stop it.\n\n"
    "If you need further assistance, feel free to ask!"
)





 
     await update.message.reply_text(help_text, parse_mode="Markdown")
 
 
 
 
#/check

 ADMIN_ID = int(st.secrets["ADMIN_ID"])
 ENTER_SONG = 0  # Ensure this is defined somewhere globally

 async def check_song_start(update: Update, context: CallbackContext) -> int:
    user = update.effective_user

    if not await is_authorized(update):
        user_logger.warning(f"Unauthorized access attempt to /checksong by {user.full_name} (@{user.username}, ID: {user.id})")

        # Notify the admin
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                f"🚨 <b>Unauthorized user accessed /checksong</b>\n\n"
                f"<b>Name:</b> {user.full_name}\n"
                f"<b>Username:</b> @{user.username}\n"
                f"<b>User ID:</b> <code>{user.id}</code>"
            ),
            parse_mode="HTML"
        )

    await update.message.reply_text(
        "🎵 Please enter the song (e.g. H-27, L-14, C-5):",
        reply_markup=ReplyKeyboardRemove()
    )
    return ENTER_SONG


 
 # Handle song input
 async def check_song_input(update: Update, context: CallbackContext) -> int:
    user_input = update.message.text.strip().upper()
    user_input = standardize_hlc_value(user_input)

    # Basic format check
    if not user_input or '-' not in user_input:
        await update.message.reply_text(
            "❌ Invalid format. Please use format like H-27.",
            reply_markup=ReplyKeyboardRemove()
        )
        return ENTER_SONG

    song_type, _, song_number = user_input.partition('-')

    if song_type not in ['H', 'L', 'C'] or not song_number.isdigit():
        await update.message.reply_text(
            "❌ Invalid input. Use H-, L-, or C- followed by a number (e.g. H-27).",
            reply_markup=ReplyKeyboardRemove()
        )
        return ENTER_SONG

    # Generate your result string (may contain a fliphtml URL as HTML link)
    result = isVocabulary(user_input)

    # Send back the result with HTML parsing and no link preview
    await update.message.reply_text(
        result,
        parse_mode="HTML",  # <-- Required for clickable links
        disable_web_page_preview=True,
        reply_markup=ReplyKeyboardRemove()
    )

    return ConversationHandler.END


  
#/last

 # States
 ENTER_LAST_SONG, ASK_SHOW_ALL = range(2)

# Download command states
 ENTER_URL, SELECT_QUALITY = range(2, 4)
 
 # /last entry point
 async def last_sung_start(update: Update, context: CallbackContext) -> int:
     await update.message.reply_text(
         "🎼 Please enter the song (e.g. H-27, L-14, C-5):",
         reply_markup=ReplyKeyboardRemove()
     )
     return ENTER_LAST_SONG
 
 # Handle song input
 async def last_sung_input(update: Update, context: CallbackContext) -> int:
     user_input = update.message.text.strip().upper()
     user_input = standardize_hlc_value(user_input)
 
     if not user_input or '-' not in user_input:
         await update.message.reply_text("❌ Invalid format. Please use format like H-27.")
         return ENTER_LAST_SONG
 
     song_type, _, song_number = user_input.partition('-')
 
     if song_type not in ['H', 'L', 'C'] or not song_number.isdigit():
         await update.message.reply_text("❌ Invalid code. Use H-, L-, or C- followed by a number (e.g. H-27).")
         return ENTER_LAST_SONG
 
     full_song = f"{song_type}-{song_number}"
     context.user_data["last_category"] = song_type
     context.user_data["last_song"] = full_song
 
     # Get last sung date
     result = Datefinder(full_song, song_type, first=True)
     await update.message.reply_text(result)
 
     # Ask if user wants all dates
     reply_keyboard = [["Yes", "No"]]
     await update.message.reply_text(
         "Would you like to see all the dates on which this song was sung?",
         reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True)
     )
     return ASK_SHOW_ALL
 
 # Handle "show all dates?" step
 async def last_sung_show_all(update: Update, context: CallbackContext) -> int:
     reply = update.message.text.strip().lower()
     category = context.user_data.get("last_category")
     full_song = context.user_data.get("last_song")
 
     if reply == "yes":
         result = Datefinder(full_song, category, first=False)
         await update.message.reply_text(result, reply_markup=ReplyKeyboardRemove())
     else:
         await update.message.reply_text(
             "May the music stay in your heart 🎵\n(❁´◡`❁)\n<b><i>S.D.G</i></b>",
             parse_mode="HTML",
             reply_markup=ReplyKeyboardRemove()
         )
 
     return ConversationHandler.END


# /download command handlers
 async def download_start(update: Update, context: CallbackContext) -> int:
    """Start the download conversation"""
    user = update.effective_user
    user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) used /download")

    if not DOWNLOADER_AVAILABLE:
        await update.message.reply_text(
            "❌ Audio download feature is not available. Please contact the administrator.",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END

    if not await is_authorized(update):
        user_logger.warning(f"Unauthorized access attempt to /download by {user.full_name} (@{user.username}, ID: {user.id})")
        return ConversationHandler.END

    await update.message.reply_text(
        "🎵 *Audio Downloader*\n\n"
        "Please send me a YouTube or Spotify link to download the audio.\n\n"
        "*Supported platforms:*\n"
        "• YouTube (youtube.com, youtu.be)\n"
        "• Spotify (spotify.com)\n"
        "• SoundCloud (soundcloud.com)\n\n"
        "Just paste the link and I'll download the audio for you!",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove()
    )
    return ENTER_URL

 async def download_url_input(update: Update, context: CallbackContext) -> int:
    """Handle URL input for download"""
    user_input = update.message.text.strip()
    user = update.effective_user

    # Initialize downloader
    downloader = AudioDownloader()

    # Check if URL is supported
    if not downloader.is_supported_url(user_input):
        await update.message.reply_text(
            "❌ This URL is not supported. Please send a YouTube, Spotify, or SoundCloud link.",
            reply_markup=ReplyKeyboardRemove()
        )
        return ENTER_URL

    # Store URL in context
    context.user_data["download_url"] = user_input
    context.user_data["platform"] = downloader.detect_platform(user_input)

    # Show quality selection
    quality_keyboard = [
        ["🔥 High Quality (320kbps)", "🎵 Medium Quality (192kbps)"],
        ["💾 Low Quality (128kbps)", "❌ Cancel"]
    ]

    await update.message.reply_text(
        f"🎯 *{context.user_data['platform']} link detected!*\n\n"
        "Please select the audio quality:",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(quality_keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return SELECT_QUALITY

 async def download_quality_selection(update: Update, context: CallbackContext) -> int:
    """Handle quality selection and start download"""
    quality_text = update.message.text.strip()
    user = update.effective_user

    # Map quality selection
    quality_map = {
        "🔥 High Quality (320kbps)": "high",
        "🎵 Medium Quality (192kbps)": "medium",
        "💾 Low Quality (128kbps)": "low"
    }

    if quality_text == "❌ Cancel":
        await update.message.reply_text(
            "❌ Download cancelled.",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END

    if quality_text not in quality_map:
        await update.message.reply_text(
            "❌ Invalid selection. Please choose a quality option.",
            reply_markup=ReplyKeyboardMarkup([
                ["🔥 High Quality (320kbps)", "🎵 Medium Quality (192kbps)"],
                ["💾 Low Quality (128kbps)", "❌ Cancel"]
            ], one_time_keyboard=True, resize_keyboard=True)
        )
        return SELECT_QUALITY

    quality = quality_map[quality_text]
    url = context.user_data.get("download_url")
    platform = context.user_data.get("platform")

    # Start download process
    await update.message.reply_text(
        f"🎵 Starting download from {platform}...\n"
        f"Quality: {quality_text}\n\n"
        "This may take a few minutes. Please wait...",
        reply_markup=ReplyKeyboardRemove()
    )

    try:
        # Log download request to Google Doc (similar to comment function)
        yfile_id = st.secrets["YFILE_ID"]
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        chat_id = update.effective_chat.id

        download_request_entry = f"{timestamp} - {user.full_name} (@{user.username}, ID: {user.id}, ChatID: {chat_id}) requested download:\nPlatform: {platform} | Quality: {quality} | URL: {url}\n\n"

        if yfile_id:
            append_download_to_google_doc(yfile_id, download_request_entry)

        # Initialize downloader
        downloader = AudioDownloader()

        # Download the audio
        result = await downloader.download_audio(url, quality)

        if result is None:
            # Log failed download to Google Doc
            download_failed_entry = f"{timestamp} - DOWNLOAD FAILED for {user.full_name} (@{user.username}, ID: {user.id}):\nPlatform: {platform} | Quality: {quality} | URL: {url}\n\n"

            if yfile_id:
                append_download_to_google_doc(yfile_id, download_failed_entry)

            await update.message.reply_text(
                "❌ Download failed. Please try again or contact the administrator."
            )
            return ConversationHandler.END

        file_path, file_info = result

        # Send the audio file
        await update.message.reply_text(
            f"✅ Download completed!\n\n"
            f"🎵 *{file_info['title']}*\n"
            f"👤 *Artist:* {file_info['artist']}\n"
            f"📱 *Platform:* {file_info['platform']}\n"
            f"📊 *Size:* {file_info['size_mb']:.1f} MB\n\n"
            "Sending file...",
            parse_mode="Markdown"
        )

        # Send the audio file
        with open(file_path, 'rb') as audio_file:
            await update.message.reply_audio(
                audio=audio_file,
                title=file_info['title'],
                performer=file_info['artist'],
                duration=file_info.get('duration', 0)
            )

        # Log successful download
        user_logger.info(f"Download completed for {user.full_name} ({user.id}): {file_info['title']}")

        # Log successful download to Google Doc
        download_success_entry = f"{timestamp} - DOWNLOAD SUCCESS for {user.full_name} (@{user.username}, ID: {user.id}):\nTitle: {file_info['title']} | Artist: {file_info['artist']} | Platform: {file_info['platform']} | Size: {file_info['size_mb']:.1f}MB | Quality: {quality}\nURL: {url}\n\n"

        if yfile_id:
            append_download_to_google_doc(yfile_id, download_success_entry)

        # Clean up the file
        downloader.cleanup_file(file_path)

        await update.message.reply_text(
            "🎉 Audio sent successfully!\n\n"
            "Send another link to download more audio, or use /cancel to stop."
        )

        return ENTER_URL  # Allow user to download another file

    except Exception as e:
        bot_logger.error(f"Download error for user {user.id}: {e}")

        # Log error to Google Doc
        download_error_entry = f"{timestamp} - DOWNLOAD ERROR for {user.full_name} (@{user.username}, ID: {user.id}):\nPlatform: {platform} | Quality: {quality} | Error: {str(e)}\nURL: {url}\n\n"

        if yfile_id:
            append_download_to_google_doc(yfile_id, download_error_entry)

        await update.message.reply_text(
            "❌ An error occurred during download. Please try again later."
        )
        return ConversationHandler.END


 # Telegram command handler for /tune command

 # States for ConversationHandler
 CHOOSE_METHOD, GET_INPUT = range(2)
 
 # Store user input temporarily
 user_input_method = {}
 
 # Start the tune command conversation
 async def tune_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) sent /tune")

    # Ask user how they want to search
    reply_keyboard = [["Hymn Number", "Tune Name"]]
    await update.message.reply_text(
        "How would you like to search?",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True),
    )
    return CHOOSE_METHOD

 
 # Handle the choice
 async def choose_method(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
     choice = update.message.text.lower()
     user_input_method[update.effective_user.id] = choice
 
     if choice == "hymn number":
         await update.message.reply_text("Please enter the hymn number:")
     elif choice == "tune name":
         await update.message.reply_text("Please enter the tune name (or part of it):")
     else:
         await update.message.reply_text("Invalid choice. Please type /tune to start over.")
         return ConversationHandler.END
 
     return GET_INPUT
 
 # Handle the actual search
 async def get_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
     user_id = update.effective_user.id
     method = user_input_method.get(user_id)
     user_input = update.message.text.strip()
 
     if method == "hymn number":
         result = Tunenofinder(user_input)  # Your existing hymn number search
     elif method == "tune name":
         result_df = Hymn_Tune_no_Finder(dfTH, user_input, top_n=10)
         result = "Top matching hymns:\n" + "\n".join(
             f"H-{int(row['Hymn no'])}: Tune: {row['Tune Index']}, \t \t Similarity: {row['Similarity']:.2f}"
             for _, row in result_df.iterrows()
         )
     else:
         result = "Something went wrong. Please try again with /tune."
 
     await update.message.reply_text(result)
     return ConversationHandler.END


 
 
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
     tune= f"\nTunes: {Tunenofinder(index_num)}" if category == 'hymn' else ''
     await update.message.reply_text(f"Search result of {category[0].upper()}-{index_num} : {result}{tune}")
     user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) searched by number: {index_num} in {category}")
     return ConversationHandler.END
 
 
 CATEGORY_SELECTION, EXPORT_CONFIRMATION = range(2)
 ADMIN_ID = int(st.secrets["ADMIN_ID"])

 async def start_vocabulary(update: Update, context: CallbackContext) -> int:
    user = update.effective_user

    if user.id not in authorized_users: # Notify admin about unauthorized access /vocabulary
     await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=(
            f"📢 <b>User accessed /vocabulary</b>\n\n"
            f"<b>Name:</b> {user.full_name}\n"
            f"<b>Username:</b> @{user.username}\n"
            f"<b>User ID:</b> <code>{user.id}</code>"
        ),
        parse_mode="HTML"
    )

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
    user = update.effective_user
    user_choice = update.message.text.strip()

    if user_choice not in VOCABULARY_CATEGORIES:
        await update.message.reply_text("⚠️ Invalid choice. Please use /vocabulary again.")
        return CATEGORY_SELECTION

    data = VOCABULARY_CATEGORIES[user_choice]

    # Clean up the data
    if isinstance(data, pd.Series):
        data = data.to_frame(name="Value")
        data = data[data["Value"].astype(str).str.strip() != '']
    elif user_choice == "Full Vocabulary":
        data = data[(data != 0).any(axis=1)]

    # Create and send the Excel file directly
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        data.to_excel(writer, sheet_name="Vocabulary", index=False)
    output.seek(0)

    filename = f"{user_choice}.xlsx"
    await update.message.reply_document(
        document=output,
        filename=filename,
        caption=f"📂 Here is your '{user_choice}' vocabulary in Excel format.",
        reply_markup=ReplyKeyboardRemove()
    )

    user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) downloaded vocabulary: {user_choice}.")
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

 # Helper function to send long messages in chunks
 async def send_long_message(update, message_parts, parse_mode="Markdown", max_length=3500):
    """
    Sends a message, splitting it into multiple messages if it's too long.
    """
    full_message = "\n\n".join(message_parts)

    if len(full_message) <= max_length:
        await update.message.reply_text(
            full_message,
            parse_mode=parse_mode,
            reply_markup=ReplyKeyboardRemove()
        )
    else:
        # Split into chunks
        current_chunk = ""
        for part in message_parts:
            if len(current_chunk + "\n\n" + part) <= max_length:
                if current_chunk:
                    current_chunk += "\n\n" + part
                else:
                    current_chunk = part
            else:
                # Send current chunk
                if current_chunk:
                    await update.message.reply_text(
                        current_chunk,
                        parse_mode=parse_mode,
                        reply_markup=ReplyKeyboardRemove()
                    )
                current_chunk = part

        # Send remaining chunk
        if current_chunk:
            await update.message.reply_text(
                current_chunk,
                parse_mode=parse_mode,
                reply_markup=ReplyKeyboardRemove()
            )

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

    # Build display lines for known and unknown hymns (show ALL, no limits)
    display_known = [f"H-{h} - {dfH[dfH['Hymn no'] == h]['Hymn Index'].values[0]} - {dfH[dfH['Hymn no'] == h]['Tunes'].values[0]}" for h in known_hymns]
    display_unknown = [f"H-{h} - {dfH[dfH['Hymn no'] == h]['Hymn Index'].values[0]}" for h in unknown_hymns]

    message_parts = [f"🎼 *Hymns related to theme:* `{theme_input}`"]

    if display_known:
        message_parts.append(f"✅ *Choir Knows ({len(known_hymns)} total):*\n" + "\n".join(display_known))
    else:
        message_parts.append("❌ *No known hymns found in this theme.*")

    if display_unknown:
        message_parts.append(f"❌ *Choir Doesn't Know ({len(unknown_hymns)} total):*\n" + "\n".join(display_unknown) +
                             "\n\n*Note:* A known song may appear here if not sung in the past 3 years.")
    else:
        message_parts.append("🎉 *Choir knows all hymns in this theme!*")

    # Use the helper function to send the message (will split automatically if too long)
    await send_long_message(update, message_parts)

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
            tune = dfH[dfH['Hymn no'] == h]['Tunes'].values[0]
            if date_obj and date_obj.year == s_year:
                sung.append(f"{hymn_code} - {index}  -{tune}")
            else:
                not_sung.append(f"{hymn_code} - {index} -{tune}")
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
        message_parts.append(f"✅ *Songs that were Sung ({len(sung_known)} total):*\n" + "\n".join(sung_known))

    if not_sung_known:
        message_parts.append(f"❌ *Songs that were Not Sung ({len(not_sung_known)} total):*\n" + "\n".join(not_sung_known))

    if not_sung_unknown:
        message_parts.append(f"🚫 *Songs Choir Doesn't Know ({len(not_sung_unknown)} total):*\n" + "\n".join(not_sung_unknown))

    # Use the helper function to send the message (will split automatically if too long)
    await send_long_message(update, message_parts)
    return ConversationHandler.END

# Add this function to periodically upload logs
 async def periodic_log_upload():
    """Periodically upload logs to Google Drive."""
    # Get interval from environment variable or use default (1 hour)
    try:
        interval_seconds = int(os.environ.get("LOG_UPLOAD_INTERVAL", 3600))
    except ValueError:
        interval_seconds = 3600  # Default to 1 hour if not a valid integer

    minutes = interval_seconds // 60
    bot_logger.info(f"Periodic log upload scheduled every {minutes} minutes")

    while True:
        try:
            # Wait for the specified interval
            await asyncio.sleep(interval_seconds)

            # Check if we should still be running
            if not bot_should_run or check_stop_signal():
                break

            # Log the upload attempt
            bot_logger.info(f"Performing scheduled log upload (every {minutes} minutes)")

            # Upload logs to Google Drive
            try:
                upload_log_to_google_doc(st.secrets["BFILE_ID"], "bot_log.txt")
                upload_log_to_google_doc(st.secrets["UFILE_ID"], "user_log.txt")

                # Also upload downloader log if it exists
                if os.path.exists("downloader_log.txt"):
                    upload_log_to_google_doc(st.secrets["BFILE_ID"], "downloader_log.txt")
                    bot_logger.info("Downloader log uploaded to BFILE_ID")

                # Note: Download logs are directly appended to YFILE_ID Google Doc, no file upload needed
                bot_logger.info("Scheduled log upload completed successfully")
            except Exception as e:
                bot_logger.error(f"Scheduled log upload failed: {e}")

        except asyncio.CancelledError:
            # Task was cancelled
            break
        except Exception as e:
            bot_logger.error(f"Error in periodic log upload task: {e}")
            # Wait a bit before retrying
            await asyncio.sleep(60)

# Modify the main function to check for stop signal
 async def main():
    """Starts the bot and registers command handlers."""
    global bot_should_run
    
    # Create the Application
    app = Application.builder().token(TOKEN).build()
    
    # Register handlers
    # ... (existing handlers)
    
    # Add a check for the stop signal file
    async def check_should_run():
        while True:
            if check_stop_signal() or not bot_should_run:
                print("Stop signal detected, shutting down bot...")
                bot_logger.info("Stop signal detected, shutting down bot...")
                await app.stop()
                break
            await asyncio.sleep(1)

    # Start the check_should_run task
    asyncio.create_task(check_should_run())

    # Start the periodic log upload task (every 1 hour)
    log_upload_task = asyncio.create_task(periodic_log_upload())

    # Log startup
    user_logger.info("🤖 Bot is running...")

    try:
        # Start the bot with custom stop signals
        await app.run_polling(stop_signals=None)
    finally:
        # Cancel the periodic log upload task when the bot stops
        log_upload_task.cancel()
        try:
            await log_upload_task
        except asyncio.CancelledError:
            pass

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
         songs_text = "\n".join(
        f"{i + 1}. {s} - {IndexFinder(s)}" for i, s in enumerate(result["songs"])
    )
         response = f"{result['message']}:\n\n{songs_text}"

        else:
            response = result  # This will be the error message from get_songs_by_date
    else:
        response = "Please provide a date. Usage: `/date DD/MM/YYYY`, `/date DD/MM`, or `/date DD`"

    await update.message.reply_text(response, parse_mode='Markdown')



 #Song Info Function
 async def handle_song_code(update: Update, context: CallbackContext) -> None:
    user_input_raw = update.message.text
    user_input = standardize_hlc_value(user_input_raw)
    song_type, _, song_number = user_input.partition('-')

    # Validate basic format again if needed
    if song_type not in ['H', 'L', 'C'] or not song_number.isdigit():
        return  # Ignore bad formats silently

    response_parts = []

    # Get Name/Index info
    song_info = isVocabulary(user_input)
    if 'not found' not in song_info:
        response_parts.append(f"🎵 <b>Song Info:</b> {song_info}")
        last_sung = Datefinder(user_input, song_type, first=True)
        response_parts.append(f"🗓️ <b>Last Sung:</b> {last_sung}")
    else:
        response_parts.append(f"Choir doesn't know {f'{user_input}: {IndexFinder(user_input)}'}")


    # Send the reply
    await update.message.reply_text(
    "\n".join(response_parts),
    parse_mode="HTML", disable_web_page_preview=True
)
# Add a new function to run the bot asynchronously
 async def run_bot_async():
    """Runs the bot asynchronously."""
    try:
        await main()
    except Exception as e:
        bot_logger.error(f"Error in bot: {e}")
        global bot_should_run
        bot_should_run = False

# Add a function to stop the bot
 def stop_bot():
    """Stops the bot gracefully."""
    global bot_should_run
    bot_should_run = False
    bot_logger.info("Bot stop requested")
    return True
    



 #/comment

 COMMENT, REPLY = range(2)

# Step 1: Command to start commenting
 async def start_comment(update: Update, context: CallbackContext) -> int:
    user = update.effective_user
    user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) started commenting.")
    
    # Ask user to provide their comment
    await update.message.reply_text(
        "Please type your comment, recommendation, or thoughts below. You can also type /cancel to exit."
    )
    return COMMENT
 



 async def process_comment(update: Update, context: CallbackContext) -> int:
    user = update.effective_user
    comment = update.message.text.strip()

    admin_id = st.secrets["ADMIN_ID"]
    comfile_id = st.secrets["COMFILE_ID"]  # Google Doc ID to store comments

    # Build the full comment message
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    user_id = user.id
    chat_id = update.effective_chat.id
    comment_entry = f"{timestamp} - {user.full_name} (@{user.username}, ID: {user.id}, ChatID: {chat_id}) said:\n{comment}\n\n"

    # Send comment to admin with an inline button
    if admin_id:
        try:
            admin_id = int(admin_id)

            # Creating an inline button for replying
            reply_button = InlineKeyboardButton(
                text="Reply to User",
                callback_data=f"reply_{chat_id}"  # Encodes the chat_id in callback_data
            )
            reply_markup = InlineKeyboardMarkup([[reply_button]])

            # Send message with the inline button
            await context.bot.send_message(
                admin_id,
                f"📝 New comment from User:\n\n"
                f"{comment}\n\n"
                f"👉 Click the button below to reply to this user.",
                reply_markup=reply_markup
            )
        except ValueError:
            logging.error("Invalid admin ID in environment variables.")

    # Append comment to Google Doc
    try:
        doc = docs_service.documents().get(documentId=comfile_id).execute()
        end_index = doc.get("body").get("content")[-1].get("endIndex", 1)

        requests = [{
            "insertText": {
                "location": {"index": end_index - 1},
                "text": comment_entry
            }
        }]

        docs_service.documents().batchUpdate(
            documentId=comfile_id,
            body={"requests": requests}
        ).execute()

        print("✅ Comment appended to Google Doc.")
    except Exception as e:
        logging.error(f"❌ Failed to append comment to Google Doc ({comfile_id}): {e}")

    # Confirm to the user
    await update.message.reply_text("✅ Thank you for your feedback! We appreciate your thoughts.")

    # Log user's comment
    user_logger.info(f"Comment from {user.full_name} (@{user.username}, ID: {user.id}): {comment}")

    return ConversationHandler.END


 # Function to handle the reply action when button is clicked
 async def reply_to_user(update: Update, context: CallbackContext) -> int:
    """Sends the actual reply to the user."""
    query = update.callback_query
    await query.answer()

    data = query.data
    target_user_id = int(data.split("_")[1])

    context.user_data["target_user_id"] = target_user_id

    await query.message.reply_text(
        f"✏️ Type your reply to the User",
        parse_mode=ParseMode.HTML
    )

    return REPLY
 


 
 async def send_reply_to_user(update: Update, context: CallbackContext) -> int:
    """Handles sending the admin's reply after they type the message."""
    user_message = update.message.text
    target_user_id = context.user_data.get("target_user_id")

    if not target_user_id:
        await update.message.reply_text("❌ No target user found to send the reply.")
        return ConversationHandler.END

    try:
        await context.bot.send_message(
            chat_id=target_user_id,
            text=f"💬 Admin's reply:\n\n{user_message}",
            parse_mode=ParseMode.HTML
        )
        await update.message.reply_text("✅ Your reply has been sent to the user.")
    except Exception as e:
        logging.error(f"❌ Failed to send reply: {e}")
        await update.message.reply_text(f"❌ Failed to send reply: {e}")

    return ConversationHandler.END


 # Admin reply function (keeps your original implementation)
 async def admin_reply(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    admin_id = int(st.secrets["ADMIN_ID"])

    if user.id != admin_id:
        await update.message.reply_text("❌ You are not authorized to use this command.")
        return

    try:
        args = context.args
        if len(args) < 2:
            await update.message.reply_text("Usage: /reply <user_id> <your message>")
            return

        target_user_id = int(args[0])
        reply_message = " ".join(args[1:])

        await context.bot.send_message(
            chat_id=target_user_id,
            text=f"💬 Admin's reply:\n\n{reply_message}",
            parse_mode=ParseMode.HTML
        )

        await update.message.reply_text(f"✅ Reply sent to user {target_user_id}.")
    except Exception as e:
        logging.error(f"❌ Failed to send reply: {e}")
        await update.message.reply_text(f"❌ Failed to send reply: {e}")



 async def refresh_command(update: Update, context: CallbackContext) -> None:
    """
    This command is restricted to the admin and calls load_datasets() to
    refresh all datasets.
    """
    admin_id_str = st.secrets["ADMIN_ID"]
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
        yrDataPreprocessing()
        dfcleaning()
        df = standardize_song_columns()
        try:
         upload_log_to_google_doc(st.secrets["BFILE_ID"], "bot_log.txt")
         upload_log_to_google_doc(st.secrets["UFILE_ID"], "user_log.txt")
         # Also upload downloader log if it exists
         if os.path.exists("downloader_log.txt"):
             upload_log_to_google_doc(st.secrets["BFILE_ID"], "downloader_log.txt")
         # Note: Download logs are directly appended to YFILE_ID Google Doc, no file upload needed
        except Exception as e:
         print(f"Couldn't save log files due to Error: {e}")
        await update.message.reply_text("Datasets reloaded successfully!")
    except Exception as e:
        await update.message.reply_text(f"Error reloading datasets: {e}")
        logging.error(f"Error in /refresh command: {e}")
        try:
         upload_log_to_google_doc(st.secrets["BFILE_ID"], "bot_log.txt")
         upload_log_to_google_doc(st.secrets["UFILE_ID"], "user_log.txt")
         # Note: Download logs are directly appended to YFILE_ID Google Doc, no file upload needed
        except Exception as e:
         print(f"Couldn't save log files due to Error: {e}")

# Step 3: Handle /cancel if the user wants to exit
 async def cancel_comment(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text("Comment process has been canceled.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END
 
 
 
 
 async def main():
     """Starts the bot and registers command handlers."""
     global bot_should_run
    
     # Create the Application
     app = Application.builder().token(TOKEN).build()
    
     # Add a shutdown handler
     async def shutdown(app):
         """Shutdown the bot gracefully"""
         app.stop()
         
     # Register handlers
     conv_handler = ConversationHandler(
         entry_points=[CommandHandler("vocabulary", start_vocabulary)],
         states={
             CATEGORY_SELECTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, category_selection)]
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
    entry_points=[CommandHandler('check', check_song_start)],
    states={
        ENTER_SONG: [MessageHandler(filters.TEXT & ~filters.COMMAND, check_song_input)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)

     
     last_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("last", last_sung_start)],
    states={
        ENTER_LAST_SONG: [MessageHandler(filters.TEXT & ~filters.COMMAND, last_sung_input)],
        ASK_SHOW_ALL: [MessageHandler(filters.TEXT & ~filters.COMMAND, last_sung_show_all)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
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
     tune_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("tune", tune_command)],
    states={
        CHOOSE_METHOD: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_method)],
        GET_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_input)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)
     
     reply_conv_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(reply_to_user, pattern="^reply_")],
    states={
        REPLY: [MessageHandler(filters.TEXT & ~filters.COMMAND, send_reply_to_user)]
    },
    fallbacks=[CommandHandler("cancel", cancel)]
)

     # Download conversation handler
     download_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("download", download_start)],
    states={
        ENTER_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, download_url_input)],
        SELECT_QUALITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, download_quality_selection)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)
 
 
 
     app.add_handler(CommandHandler("start", start))
     app.add_handler(CommandHandler("help", help_command))
     app.add_handler(CommandHandler("date", date_command))
     app.add_handler(CommandHandler("refresh", refresh_command))
     app.add_handler(CommandHandler("reply", admin_reply))

     app.add_handler(tune_conv_handler)
     app.add_handler(last_conv_handler)
     app.add_handler(check_conv)
     app.add_handler(theme_handler)
     app.add_handler(search_conv_handler)
     app.add_handler(conv_handler)
     app.add_handler(comment_handler)
     app.add_handler(reply_conv_handler)
     app.add_handler(download_conv_handler)

     app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^[HhLlCc\s-]*\d+$"), handle_song_code))

     # Add a check for the bot_should_run flag
     async def check_should_run():
         while True:
             if not bot_should_run:
                 await shutdown(app)
                 break
             await asyncio.sleep(1)
     
     # Start the check_should_run task
     asyncio.create_task(check_should_run())
     
     # Log startup
     user_logger.info("🤖 Bot is running...")
     
     # Start the bot with custom stop signals
     await app.run_polling(stop_signals=None)

 
#  def start_bot_in_thread():
#     """Starts the bot in a background thread."""
#     loop = asyncio.new_event_loop()
#     asyncio.set_event_loop(loop)  # Set the event loop for this thread
#     loop.run_until_complete(main())  # Run the bot

#  def run_bot():
#     """Starts the bot in a new thread."""
#     bot_thread = threading.Thread(target=start_bot_in_thread)
#     bot_thread.daemon = True  # Ensure the thread exits when the program ends
#     bot_thread.start()

 import asyncio
 import nest_asyncio
 
 nest_asyncio.apply()  # patch asyncio to allow nested event loops
 
 def run_bot():
    return asyncio.run(run_bot_async())



    
except KeyboardInterrupt:
    print("\n🛑 Bot stopped manually by user (Ctrl + C).")
    bot_logger.info(f"\nBot was stoped by the user\n\n")
    try:
        upload_log_to_google_doc(st.secrets["BFILE_ID"], "bot_log.txt")
        upload_log_to_google_doc(st.secrets["UFILE_ID"], "user_log.txt")
        # Note: Download logs are directly appended to YFILE_ID Google Doc, no file upload needed
        sys.exit(0)
    except Exception as e:
        print(f"Couldn't save log files due to Error: {e}")
        sys.exit(0)
except Exception as e:
    print(f"\n❌ An unexpected error occurred: {e}")
    bot_logger.error(f"\n❌ An unexpected error occurred: {e}")
    bot_logger.info("\n")
    try:
        upload_log_to_google_doc(st.secrets["BFILE_ID"], "bot_log.txt")
        upload_log_to_google_doc(st.secrets["UFILE_ID"], "user_log.txt")
        # Note: Download logs are directly appended to YFILE_ID Google Doc, no file upload needed
        sys.exit(1)
    except Exception as e:
        print(f"Couldn't save log files due to Error: {e}")
        sys.exit(1) 
