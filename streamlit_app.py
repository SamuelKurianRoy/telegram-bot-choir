import streamlit as st
import os
import signal
import time
import sys
import json
import logging
import datetime
from pathlib import Path
from run_bot import start_bot_in_background, stop_bot_in_background, stop_all_bot_instances
from googleapiclient.discovery import build
from google.oauth2 import service_account
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.errors import HttpError
import subprocess
import psutil
import random
import re
from telegram_handlers.utils import get_wordproject_url_from_input, extract_bible_chapter_text, clean_bible_text

# Add at the top of the file
STOP_SIGNAL_FILE = "/tmp/telegram_bot_stop_signal"

# Set page config
st.set_page_config(
    page_title="Railway Choir Bot",
    page_icon="🎶",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        color: #1E88E5;
        text-align: center;
    }
    .sub-header {
        font-size: 1.8rem;
        color: #0D47A1;
    }
    .status-running {
        font-size: 1.5rem;
        color: #4CAF50;
        font-weight: bold;
    }
    .status-stopped {
        font-size: 1.5rem;
        color: #F44336;
        font-weight: bold;
    }
    .info-box {
        background-color: #E3F2FD;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 5px solid #1E88E5;
    }
    .stButton button {
        width: 100%;
    }
    .log-container {
        max-height: 500px;
        overflow-y: auto;
        background-color: #f5f5f5;
        padding: 10px;
        border-radius: 5px;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state variables if they don't exist
if "bot_started" not in st.session_state:
    st.session_state["bot_started"] = False
if "last_started" not in st.session_state:
    st.session_state["last_started"] = None
if "last_stopped" not in st.session_state:
    st.session_state["last_stopped"] = None
if "auto_refresh" not in st.session_state:
    st.session_state["auto_refresh"] = False
if "refresh_interval" not in st.session_state:
    st.session_state["refresh_interval"] = 30
if "logs_initialized" not in st.session_state:
    st.session_state["logs_initialized"] = False

# Bible game session state
if "bible_game_score" not in st.session_state:
    st.session_state["bible_game_score"] = 0
if "bible_game_total" not in st.session_state:
    st.session_state["bible_game_total"] = 0
if "current_question" not in st.session_state:
    st.session_state["current_question"] = None
if "game_difficulty" not in st.session_state:
    st.session_state["game_difficulty"] = "Easy"
if "game_language" not in st.session_state:
    st.session_state["game_language"] = "English"

# Setup logging (using the same configuration as in bot.py)
def setup_logging():
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
    
    st.session_state["logs_initialized"] = True
    return bot_logger, user_logger

# Setup Google Drive service
def setup_google_drive():
    try:
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
        
        # Save the JSON to a temporary file
        KEY_PATH = "/tmp/service_account.json"
        with open(KEY_PATH, "w") as f:
            json.dump(service_account_data, f) 
        
        # Set the GOOGLE_APPLICATION_CREDENTIALS environment variable
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = KEY_PATH
        
        # Authenticate and build the drive service
        creds = service_account.Credentials.from_service_account_file(KEY_PATH, scopes=SCOPES)
        drive_service = build("drive", "v3", credentials=creds)
        
        return drive_service, True, "✅ Google Drive service initialized successfully!"
    except Exception as e:
        return None, False, f"❌ Error initializing Google Drive service: {str(e)}"

# Upload logs to Google Drive
def upload_log_to_google_doc(doc_id, log_file):
    try:
        if not os.path.exists(log_file):
            return False, f"⚠️ Log file {log_file} does not exist."
        
        with open(log_file, "r", encoding="utf-8") as file:
            content = file.read().strip()
        
        if not content:
            return False, f"ℹ️ Log file {log_file} is empty. Skipping upload."
        
        # Setup Google Docs service
        KEY_PATH = "/tmp/service_account.json"
        DOC_SCOPES = ["https://www.googleapis.com/auth/documents"]
        creds = service_account.Credentials.from_service_account_file(KEY_PATH, scopes=DOC_SCOPES)
        docs_service = build("docs", "v1", credentials=creds)
        
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
        
        return True, f"✅ Successfully uploaded {log_file} to Google Doc"
    except HttpError as e:
        return False, f"❌ Failed to upload log due to: {e}"

# Functions
def get_log_content(log_path, max_lines=100):
    """Get the content of a log file"""
    try:
        if os.path.exists(log_path):
            with open(log_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                return "".join(lines[-max_lines:])
        return "Log file not found."
    except Exception as e:
        return f"Error reading log: {str(e)}"

def stop_bot():
    """Stop the bot process"""
    if st.session_state.get("bot_started", False):
        try:
            # Create a stop signal file
            with open(STOP_SIGNAL_FILE, 'w') as f:
                f.write(str(datetime.datetime.now()))
            
            # Call the stop function from run_bot.py
            success = stop_bot_in_background()
            
            # Update session state
            st.session_state["bot_started"] = False
            st.session_state["last_stopped"] = datetime.datetime.now()
            
            # Log the stop event
            bot_logger, _ = setup_logging()
            bot_logger.info("Bot stopped from Streamlit interface")
            
            # Upload logs to Google Drive
            if "BFILE_ID" in st.secrets and "UFILE_ID" in st.secrets:
                upload_log_to_google_doc(st.secrets["BFILE_ID"], "bot_log.txt")
                upload_log_to_google_doc(st.secrets["UFILE_ID"], "user_log.txt")
            
            # Force a rerun to update the UI
            time.sleep(1)
            st.rerun()
            
            return success
        except Exception as e:
            st.error(f"Failed to stop bot: {e}")
    return False

def start_bot():
    """Start the bot"""
    try:
        # First check if there are any existing bot instances and terminate them
        st.info("Stopping any existing bot instances...")
        emergency_stop_bot()
        
        # Initialize logging
        bot_logger, _ = setup_logging()
        bot_logger.info("Starting bot from Streamlit interface")
        
        # Initialize Google Drive service
        st.info("Initializing Google Drive service...")
        drive_service, success, message = setup_google_drive()
        if not success:
            st.error(message)
            return False
        
        # Get log upload interval from session state (default to 60 minutes)
        log_upload_interval = st.session_state.get("log_upload_interval", 60)
        
        # Start the bot
        st.info(f"Starting bot with log upload interval of {log_upload_interval} minutes...")
        success = start_bot_in_background(log_upload_interval)
        if not success:
            st.warning("Failed to start the bot. Check the logs for details.")
            return False
            
        st.session_state["bot_started"] = True
        st.session_state["last_started"] = datetime.datetime.now()
        
        bot_logger.info(f"Bot started successfully with log upload interval of {log_upload_interval} minutes")
        return True
    except Exception as e:
        st.error(f"Failed to start bot: {e}")
        return False

# Add this function to forcefully terminate any running bot instances
def emergency_stop_bot():
    """Forcefully terminate any running bot instances"""
    try:
        # Create a stop signal file
        with open(STOP_SIGNAL_FILE, 'w') as f:
            f.write(str(datetime.datetime.now()))
        
        # Wait a bit for the bot to detect the signal
        time.sleep(2)
        
        # Remove any existing lock file
        lock_file = "/tmp/telegram_bot.lock"
        if os.path.exists(lock_file):
            os.remove(lock_file)
            st.info(f"Removed lock file: {lock_file}")
        
        # Call the stop_all_bot_instances function
        success = stop_all_bot_instances()
        
        # Update session state
        st.session_state["bot_started"] = False
        st.session_state["last_stopped"] = datetime.datetime.now()
        
        # Log the emergency stop
        bot_logger, _ = setup_logging()
        bot_logger.info("Bot forcefully terminated from Streamlit interface")
        
        return success
    except Exception as e:
        st.error(f"Failed to emergency stop bot: {e}")
        return False

def debug_bot_processes():
    """Debug function to list all running Python processes"""
    processes = []
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.info['name'] == 'python' and proc.info['cmdline']:
                cmdline = ' '.join(proc.info['cmdline'])
                processes.append({
                    'pid': proc.pid,
                    'cmdline': cmdline,
                    'is_bot': 'bot.py' in cmdline
                })
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return processes

# Bible Game Data
BIBLE_VERSES = {
    "Easy": [
        {"reference": "John 3:16", "book": "john", "chapter": 3, "verse": 16},
        {"reference": "Genesis 1:1", "book": "genesis", "chapter": 1, "verse": 1},
        {"reference": "Psalm 23:1", "book": "psalms", "chapter": 23, "verse": 1},
        {"reference": "Romans 3:23", "book": "romans", "chapter": 3, "verse": 23},
        {"reference": "Romans 6:23", "book": "romans", "chapter": 6, "verse": 23},
        {"reference": "Ephesians 2:8", "book": "ephesians", "chapter": 2, "verse": 8},
        {"reference": "1 John 1:9", "book": "1 john", "chapter": 1, "verse": 9},
        {"reference": "Matthew 28:19", "book": "matthew", "chapter": 28, "verse": 19},
        {"reference": "Acts 1:8", "book": "acts", "chapter": 1, "verse": 8},
        {"reference": "Philippians 4:13", "book": "philippians", "chapter": 4, "verse": 13},
    ],
    "Medium": [
        {"reference": "Isaiah 53:5", "book": "isaiah", "chapter": 53, "verse": 5},
        {"reference": "Jeremiah 29:11", "book": "jeremiah", "chapter": 29, "verse": 11},
        {"reference": "Proverbs 3:5", "book": "proverbs", "chapter": 3, "verse": 5},
        {"reference": "2 Timothy 3:16", "book": "2 timothy", "chapter": 3, "verse": 16},
        {"reference": "Hebrews 11:1", "book": "hebrews", "chapter": 11, "verse": 1},
        {"reference": "James 1:17", "book": "james", "chapter": 1, "verse": 17},
        {"reference": "1 Peter 5:7", "book": "1 peter", "chapter": 5, "verse": 7},
        {"reference": "Galatians 2:20", "book": "galatians", "chapter": 2, "verse": 20},
        {"reference": "Colossians 3:23", "book": "colossians", "chapter": 3, "verse": 23},
        {"reference": "1 Thessalonians 5:16", "book": "1 thessalonians", "chapter": 5, "verse": 16},
    ],
    "Hard": [
        {"reference": "Habakkuk 2:4", "book": "habakkuk", "chapter": 2, "verse": 4},
        {"reference": "Malachi 3:10", "book": "malachi", "chapter": 3, "verse": 10},
        {"reference": "Zephaniah 3:17", "book": "zephaniah", "chapter": 3, "verse": 17},
        {"reference": "Nahum 1:7", "book": "nahum", "chapter": 1, "verse": 7},
        {"reference": "Micah 6:8", "book": "micah", "chapter": 6, "verse": 8},
        {"reference": "Jonah 2:8", "book": "jonah", "chapter": 2, "verse": 8},
        {"reference": "Obadiah 1:15", "book": "obadiah", "chapter": 1, "verse": 15},
        {"reference": "Amos 5:24", "book": "amos", "chapter": 5, "verse": 24},
        {"reference": "Joel 2:32", "book": "joel", "chapter": 2, "verse": 32},
        {"reference": "Hosea 6:6", "book": "hosea", "chapter": 6, "verse": 6},
    ]
}

def extract_verse_from_text(text, verse_number):
    """Extract a specific verse from cleaned Bible text"""
    lines = text.strip().split('\n')
    for line in lines:
        line = line.strip()
        if line.startswith(f"{verse_number} "):
            return line[len(f"{verse_number} "):].strip()
    return None

def get_bible_verse(book, chapter, verse, language='english'):
    """Fetch a specific Bible verse in the specified language"""
    try:
        # Get the URL for the chapter
        result = get_wordproject_url_from_input(language, f"{book} {chapter}")
        url, _, _, _ = result

        if url.startswith("❌"):
            return None

        # Extract the chapter text
        raw_text = extract_bible_chapter_text(url)
        if raw_text.startswith("❌"):
            return None

        # Determine language code for cleaning
        lang_code = 'kj'  # default English
        if language.lower() in ['malayalam', 'mal']:
            lang_code = 'ml'
        elif language.lower() in ['hindi', 'hin']:
            lang_code = 'in'
        elif language.lower() in ['tamil', 'tam']:
            lang_code = 'tm'
        elif language.lower() in ['telugu', 'tel']:
            lang_code = 'te'
        elif language.lower() in ['chinese', 'zh']:
            lang_code = 'big5'
        elif language.lower() in ['japanese', 'ja']:
            lang_code = 'jp'
        else:
            # For other languages, use the language code as-is
            # The clean_bible_text function will handle generic cleaning
            lang_code = language.lower()

        # Clean the text
        cleaned_text = clean_bible_text(raw_text, lang_code)

        # Extract the specific verse
        verse_text = extract_verse_from_text(cleaned_text, verse)

        if verse_text:
            # Clean up common formatting issues
            verse_text = verse_text.replace('  ', ' ')  # Remove double spaces
            verse_text = verse_text.strip()
            # Fix common word concatenation issues (mainly for English)
            if language.lower() in ['english', 'eng']:
                verse_text = verse_text.replace('Christwhich', 'Christ which')
                verse_text = verse_text.replace('Godand', 'God and')
                verse_text = verse_text.replace('Lordand', 'Lord and')

        return verse_text

    except Exception as e:
        st.error(f"Error fetching verse: {e}")
        return None

def generate_wrong_options(correct_reference, _):
    """Generate 3 wrong options for the multiple choice"""
    all_verses = []
    for diff_level in BIBLE_VERSES.values():
        all_verses.extend(diff_level)

    # Remove the correct answer from options
    wrong_options = [v for v in all_verses if v["reference"] != correct_reference]

    # Select 3 random wrong options
    selected_wrong = random.sample(wrong_options, min(3, len(wrong_options)))
    return [opt["reference"] for opt in selected_wrong]

def create_bible_question(difficulty, language='english'):
    """Create a new Bible question"""
    verses = BIBLE_VERSES[difficulty]
    selected_verse = random.choice(verses)

    # Get the verse text in the specified language
    verse_text = get_bible_verse(selected_verse["book"], selected_verse["chapter"], selected_verse["verse"], language)

    if not verse_text:
        return None

    # Generate options
    wrong_options = generate_wrong_options(selected_verse["reference"], difficulty)
    all_options = [selected_verse["reference"]] + wrong_options
    random.shuffle(all_options)

    return {
        "verse_text": verse_text,
        "correct_answer": selected_verse["reference"],
        "options": all_options,
        "difficulty": difficulty,
        "language": language
    }

# Initialize logging
bot_logger, user_logger = setup_logging()

# Sidebar
with st.sidebar:
    st.image("https://img.icons8.com/color/96/000000/musical-notes.png", width=100)
    st.title("Navigation")
    
    page = st.radio("Go to", ["Dashboard", "Logs", "Settings", "Bible Game", "About"])
    
    st.markdown("---")
    
    # Quick status and controls
    status = "🟢 Running" if st.session_state["bot_started"] else "🔴 Stopped"
    st.markdown(f"### Bot Status: {status}")
    
    if st.session_state["bot_started"]:
        if st.button("Stop Bot", key="sidebar_stop", type="primary"):
            if stop_bot():
                st.success("Bot stopped successfully!")
                time.sleep(1)
                st.rerun()
    else:
        if st.button("Start Bot", key="sidebar_start", type="primary"):
            if start_bot():
                st.success("Bot started successfully!")
                time.sleep(1)
                st.rerun()
    
    # Add Emergency Stop button to sidebar
    st.markdown("---")
    if st.button("🚨 Emergency Stop", key="sidebar_emergency_stop"):
        if emergency_stop_bot():
            st.success("All bot instances forcefully terminated!")
            time.sleep(1)
            st.rerun()
    
    # Environment status
    st.markdown("### Environment")
    
    # Check if Google Drive service is available
    drive_service, drive_success, drive_message = setup_google_drive()
    if drive_success:
        st.success("Google Drive: Connected")
    else:
        st.error("Google Drive: Disconnected")
    
    # Check if logs are properly set up
    if os.path.exists("bot_log.txt") and os.path.exists("user_log.txt"):
        st.success("Logs: Initialized")
    else:
        st.warning("Logs: Not found")

# Main content
if page == "Dashboard":
    st.markdown("<h1 class='main-header'>🎶 Railway Choir Bot Control Panel</h1>", unsafe_allow_html=True)
    
    # Status card
    st.markdown("<h2 class='sub-header'>Bot Status</h2>", unsafe_allow_html=True)
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        if st.session_state["bot_started"]:
            st.markdown("<p class='status-running'>🟢 Running</p>", unsafe_allow_html=True)
            if st.button("Stop Bot", type="primary", key="main_stop"):
                if stop_bot():
                    st.success("Bot stopped successfully!")
                    time.sleep(1)
                    st.rerun()
                    
            if st.session_state["last_started"]:
                st.info(f"Started at: {st.session_state['last_started'].strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            st.markdown("<p class='status-stopped'>🔴 Stopped</p>", unsafe_allow_html=True)
            if st.button("Start Bot", type="primary", key="main_start"):
                if start_bot():
                    st.success("Bot started successfully!")
                    time.sleep(1)
                    st.rerun()
                    
            if st.session_state["last_stopped"]:
                st.info(f"Stopped at: {st.session_state['last_stopped'].strftime('%Y-%m-%d %H:%M:%S')}")
    
    with col2:
        st.markdown(
            "<div class='info-box'>"
            "<h3>Control Panel</h3>"
            "<p>This dashboard allows you to manage the Railway Choir Telegram Bot. "
            "Use the controls to start or stop the bot service.</p>"
            "<p>The bot provides search capabilities for hymns, lyrics, and convention songs "
            "through a Telegram interface.</p>"
            "</div>",
            unsafe_allow_html=True
        )
    
    # Add Emergency Stop button
    st.markdown("<h2 class='sub-header'>Emergency Controls</h2>", unsafe_allow_html=True)
    st.warning("⚠️ Use only if the bot is stuck or multiple instances are running")
    
    if st.button("🚨 Emergency Stop", type="primary", key="emergency_stop"):
        if emergency_stop_bot():
            st.success("All bot instances forcefully terminated!")
            time.sleep(1)
            st.rerun()
    
    # Environment variables status
    st.markdown("<h2 class='sub-header'>Environment Status</h2>", unsafe_allow_html=True)
    
    env_vars = [
        "HLCFILE_ID", "TFILE_ID", "FILE_ID", "TOKEN", 
        "BFILE_ID", "UFILE_ID", "COMFILE_ID", "ADMIN_ID", "AUTHORIZED_USERS"
    ]
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Google Drive Files")
        for var in ["HLCFILE_ID", "TFILE_ID", "FILE_ID", "BFILE_ID", "UFILE_ID", "COMFILE_ID"]:
            if var in st.secrets:
                st.success(f"✅ {var} is configured")
            else:
                st.error(f"❌ {var} is missing")
    
    with col2:
        st.subheader("Bot Configuration")
        for var in ["TOKEN", "ADMIN_ID", "AUTHORIZED_USERS"]:
            if var in st.secrets:
                st.success(f"✅ {var} is configured")
            else:
                st.error(f"❌ {var} is missing")
    
    # Quick stats
    st.markdown("<h2 class='sub-header'>Quick Stats</h2>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric(
            label="Bot Status", 
            value="Online" if st.session_state["bot_started"] else "Offline",
            delta="Active" if st.session_state["bot_started"] else "Inactive",
            delta_color="normal" if st.session_state["bot_started"] else "inverse"
        )
    
    with col2:
        # Count lines in user log to estimate interactions
        user_log = get_log_content("user_log.txt", max_lines=10000)
        interaction_count = len(user_log.split('\n')) if user_log != "Log file not found." else 0
        st.metric(label="User Interactions", value=interaction_count)
    
    with col3:
        # Count errors in bot log
        bot_log = get_log_content("bot_log.txt", max_lines=10000)
        error_count = bot_log.lower().count("error") if bot_log != "Log file not found." else 0
        st.metric(label="Errors Logged", value=error_count, delta=f"{error_count} issues")
    
    # Recent activity
    st.markdown("<h2 class='sub-header'>Recent Activity</h2>", unsafe_allow_html=True)
    
    # Get the most recent user interactions
    user_log_recent = get_log_content("bot_log.txt", max_lines=5)
    if user_log_recent != "Log file not found.":
        st.code(user_log_recent, language="text")
    else:
        st.info("No recent user activity found.")

    # Add debug section
    st.markdown("<h2 class='sub-header'>Debug Information</h2>", unsafe_allow_html=True)
    if st.button("Show Running Python Processes"):
        processes = debug_bot_processes()
        if processes:
            st.write("Running Python processes:")
            for proc in processes:
                st.write(f"PID: {proc['pid']}, Is Bot: {proc['is_bot']}")
                st.code(proc['cmdline'], language="bash")
        else:
            st.write("No Python processes found.")

elif page == "Logs":
    st.markdown("<h1 class='main-header'>Bot Logs</h1>", unsafe_allow_html=True)
    
    # Auto-refresh option
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        st.session_state["auto_refresh"] = st.checkbox("Auto-refresh logs", value=st.session_state["auto_refresh"])
    with col2:
        if st.session_state["auto_refresh"]:
            st.session_state["refresh_interval"] = st.number_input(
                "Refresh interval (seconds)", 
                min_value=5, 
                max_value=300, 
                value=st.session_state["refresh_interval"]
            )
    with col3:
        if st.button("Upload Logs to Google Drive"):
            if "BFILE_ID" in st.secrets and "UFILE_ID" in st.secrets:
                success1, msg1 = upload_log_to_google_doc(st.secrets["BFILE_ID"], "bot_log.txt")
                success2, msg2 = upload_log_to_google_doc(st.secrets["UFILE_ID"], "user_log.txt")
                
                if success1 and success2:
                    st.success("Logs uploaded successfully!")
                else:
                    st.error(f"Error uploading logs: {msg1}, {msg2}")
            else:
                st.error("BFILE_ID or UFILE_ID not configured in secrets")
    
    # Log tabs
    tab1 = st.tabs(["Bot Log"])[0]  # Get the first tab from the list
    # tab1, tab2 = st.tabs(["Bot Log", "User Activity Log"])
    
    with tab1:
        st.subheader("Bot Log (Errors & System Messages)")
        
        # Add search filter
        col1, col2 = st.columns([3, 1])
        with col1:
            bot_search = st.text_input("Filter bot logs (case-insensitive):", key="bot_search")
        with col2:
            bot_log_level = st.selectbox(
                "Filter by log level:",
                ["All", "INFO", "WARNING", "ERROR", "CRITICAL"],
                key="bot_log_level"
            )
        
        # Get log content
        bot_log_content = get_log_content("bot_log.txt", max_lines=500)
        
        # Apply filters
        if bot_search:
            filtered_lines = [line for line in bot_log_content.split('\n') 
                             if bot_search.lower() in line.lower()]
            bot_log_content = '\n'.join(filtered_lines)
        
        if bot_log_level != "All":
            filtered_lines = [line for line in bot_log_content.split('\n') 
                             if f" - {bot_log_level} - " in line]
            bot_log_content = '\n'.join(filtered_lines)
        
        # Display logs
        st.code(bot_log_content, language="text")

    # with tab2:
    #     st.subheader("User Activity Log")
        
    #     # Add search filter
    #     user_search = st.text_input("Filter user logs (case-insensitive):", key="user_search")
        
    #     # Get log content
    #     user_log_content = get_log_content("user_log.txt", max_lines=500)
        
    #     # Apply filters
    #     if user_search:
    #         filtered_lines = [line for line in user_log_content.split('\n') 
    #                          if user_search.lower() in line.lower()]
    #         user_log_content = '\n'.join(filtered_lines)
        
    #     # Display logs
    #     st.code(user_log_content, language="text")

    # Auto-refresh logs
    if st.session_state["bot_started"]:
        if st.button("Refresh Logs"):
            st.rerun()

elif page == "Bible Game":
    st.markdown("<h1 class='main-header'>📖 Bible Verse Game</h1>", unsafe_allow_html=True)

    # Game description
    st.markdown("""
    <div class='info-box'>
        <h3>How to Play</h3>
        <p>Test your Bible knowledge! A verse will be displayed, and you need to guess which Bible reference it's from.</p>
        <p>Choose your language (English or Malayalam), difficulty level, and start playing!</p>
    </div>
    """, unsafe_allow_html=True)

    # Language and difficulty selection
    col1, col2, col3, col4 = st.columns([2, 2, 1, 1])

    with col1:
        language = st.selectbox(
            "Select Language:",
            ["English", "Malayalam"],
            index=["English", "Malayalam"].index(st.session_state["game_language"])
        )
        if language != st.session_state["game_language"]:
            st.session_state["game_language"] = language
            st.session_state["current_question"] = None  # Reset current question

    with col2:
        difficulty = st.selectbox(
            "Select Difficulty:",
            ["Easy", "Medium", "Hard"],
            index=["Easy", "Medium", "Hard"].index(st.session_state["game_difficulty"])
        )
        if difficulty != st.session_state["game_difficulty"]:
            st.session_state["game_difficulty"] = difficulty
            st.session_state["current_question"] = None  # Reset current question

    with col3:
        st.metric("Score", f"{st.session_state['bible_game_score']}/{st.session_state['bible_game_total']}")

    with col4:
        if st.session_state["bible_game_total"] > 0:
            percentage = (st.session_state["bible_game_score"] / st.session_state["bible_game_total"]) * 100
            st.metric("Accuracy", f"{percentage:.1f}%")

    # Game controls
    col1, col2 = st.columns([1, 1])

    with col1:
        if st.button("🎮 New Question", type="primary"):
            with st.spinner("Loading Bible verse..."):
                # Convert language name to lowercase for the function
                lang_code = language.lower()
                question = create_bible_question(difficulty, lang_code)
                if question:
                    st.session_state["current_question"] = question
                    st.rerun()
                else:
                    st.error("Failed to load Bible verse. Please try again.")

    with col2:
        if st.button("🔄 Reset Score"):
            st.session_state["bible_game_score"] = 0
            st.session_state["bible_game_total"] = 0
            st.session_state["current_question"] = None
            st.success("Score reset!")
            st.rerun()

    # Display current question
    if st.session_state["current_question"]:
        question = st.session_state["current_question"]

        st.markdown("---")
        st.markdown(f"### 📜 {question['difficulty']} Level - {question.get('language', 'English').title()}")

        # Display the verse in a nice box
        st.markdown(f"""
        <div style="background-color: #f0f8ff; padding: 20px; border-radius: 10px; border-left: 5px solid #1E88E5; margin: 20px 0;">
            <h4 style="color: #0D47A1; margin-bottom: 15px;">📖 Bible Verse:</h4>
            <p style="font-size: 1.2em; font-style: italic; color: #333; line-height: 1.6;">
                "{question['verse_text']}"
            </p>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("### Which Bible reference is this verse from?")

        # Create answer buttons
        for i, option in enumerate(question["options"]):
            if st.button(f"{chr(65+i)}) {option}", key=f"option_{i}", use_container_width=True):
                st.session_state["bible_game_total"] += 1

                if option == question["correct_answer"]:
                    st.session_state["bible_game_score"] += 1
                    st.success(f"🎉 Correct! The answer is {question['correct_answer']}")
                else:
                    st.error(f"❌ Wrong! The correct answer is {question['correct_answer']}")

                # Clear current question after answering
                st.session_state["current_question"] = None
                time.sleep(2)
                st.rerun()

    else:
        st.markdown("---")
        st.info("👆 Click 'New Question' to start playing!")

    # Game statistics
    if st.session_state["bible_game_total"] > 0:
        st.markdown("---")
        st.markdown("### 📊 Game Statistics")

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Total Questions", st.session_state["bible_game_total"])

        with col2:
            st.metric("Correct Answers", st.session_state["bible_game_score"])

        with col3:
            wrong_answers = st.session_state["bible_game_total"] - st.session_state["bible_game_score"]
            st.metric("Wrong Answers", wrong_answers)

        with col4:
            if st.session_state["bible_game_total"] > 0:
                accuracy = (st.session_state["bible_game_score"] / st.session_state["bible_game_total"]) * 100
                st.metric("Overall Accuracy", f"{accuracy:.1f}%")

elif page == "Settings":
    st.markdown("<h1 class='main-header'>Bot Settings</h1>", unsafe_allow_html=True)
    
    # Log upload settings
    st.subheader("Log Upload Settings")
    
    # Initialize session state for log upload interval if it doesn't exist
    if "log_upload_interval" not in st.session_state:
        st.session_state["log_upload_interval"] = 60  # Default: 60 minutes
    
    # Log upload interval slider
    log_upload_interval = st.slider(
        "Log Upload Interval (minutes)",
        min_value=15,
        max_value=240,
        value=st.session_state["log_upload_interval"],
        step=15,
        help="How often the bot should upload logs to Google Drive"
    )
    
    # Update session state if changed
    if log_upload_interval != st.session_state["log_upload_interval"]:
        st.session_state["log_upload_interval"] = log_upload_interval
        st.success(f"Log upload interval set to {log_upload_interval} minutes")
        st.info("This setting will take effect the next time the bot is started")
    
    # Manual log upload button
    if st.button("Upload Logs Now"):
        if "BFILE_ID" in st.secrets and "UFILE_ID" in st.secrets:
            success1, msg1 = upload_log_to_google_doc(st.secrets["BFILE_ID"], "bot_log.txt")
            success2, msg2 = upload_log_to_google_doc(st.secrets["UFILE_ID"], "user_log.txt")
            
            if success1 and success2:
                st.success("Logs uploaded successfully!")
            else:
                st.error(f"Error uploading logs: {msg1}, {msg2}")
        else:
            st.error("BFILE_ID or UFILE_ID not configured in secrets")

elif page == "About":
    st.markdown("<h1 class='main-header'>About Railway Choir Bot</h1>", unsafe_allow_html=True)

    # Bot information
    st.markdown("## 🎶 Bot Information")
    st.markdown("""
    This control panel allows you to start and stop the Railway Choir Telegram Bot.

    **Bot Features:**
    - Search for hymns, lyrics, and convention songs
    - Get information about when songs were last sung
    - Search by theme or tune
    - View song details and history
    - Bible verse lookup and reading

    **Bot Commands:**
    - `/start` - Start the bot
    - `/help` - Show help information
    - `/search` - Search for songs
    - `/theme` - Filter songs by theme
    - `/tune` - Find tunes by hymn number or tune index
    - `/date` - Show songs sung on a specific date
    - `/bible` - Look up Bible passages
    """)

    # Bible Game information
    st.markdown("## 📖 Bible Game")
    st.markdown("""
    The Bible Game is an interactive feature that helps you learn and memorize Bible verses.

    **Game Features:**
    - **Three Difficulty Levels:**
      - **Easy:** Popular and well-known verses (John 3:16, Genesis 1:1, etc.)
      - **Medium:** Important verses that require more Bible knowledge
      - **Hard:** Lesser-known verses from minor prophets and challenging books

    - **Multiple Choice Format:** Each question provides 4 options to choose from
    - **Score Tracking:** Keep track of your correct answers and accuracy
    - **Real-time Verse Fetching:** Verses are fetched live from WordProject.org
    - **Reset Functionality:** Start fresh anytime with the reset button

    **How It Helps:**
    - Prevents the Streamlit app from sleeping due to inactivity
    - Provides an engaging way to learn Bible verses
    - Tests your knowledge of Bible references
    - Helps memorize important passages
    """)

    # Technical information
    st.markdown("## ⚙️ Technical Details")
    st.markdown("""
    **Bible Verse Source:** WordProject.org
    **Languages Supported:** English and Malayalam
    **Verse Extraction:** Real-time parsing from web content
    **Game Logic:** Random selection with difficulty-based filtering
    """)

    # Credits
    st.markdown("## 👥 Credits")
    st.markdown("""
    - **Bot Development:** Railway Choir Bot Team
    - **Bible Content:** WordProject.org
    - **Framework:** Streamlit + Python Telegram Bot
    - **Hosting:** Railway/Streamlit Cloud
    """)
