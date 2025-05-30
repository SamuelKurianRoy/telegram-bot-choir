import streamlit as st
import os
import signal
import time
import sys
import json
import logging
import datetime
from pathlib import Path
from run_bot import start_bot_in_background
from googleapiclient.discovery import build
from google.oauth2 import service_account
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.errors import HttpError
import subprocess
import psutil

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
            # Find and terminate all bot processes
            killed = False
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    # Check if this is a python process running our bot
                    if proc.info['name'] == 'python' and proc.info['cmdline'] and any('bot.py' in cmd for cmd in proc.info['cmdline']):
                        # Skip our own process
                        if proc.pid != os.getpid():
                            st.info(f"Killing bot process with PID {proc.pid}")
                            # Use SIGKILL directly for immediate termination
                            os.kill(proc.pid, signal.SIGKILL)
                            killed = True
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
            
            # Remove lock file if it exists
            lock_file = "/tmp/telegram_bot.lock"
            if os.path.exists(lock_file):
                os.remove(lock_file)
                
            # Update session state
            st.session_state["bot_started"] = False
            st.session_state["last_stopped"] = datetime.datetime.now()
            
            # Log the stop event
            bot_logger, _ = setup_logging()
            bot_logger.info("Bot forcefully stopped from Streamlit interface")
            
            # Upload logs to Google Drive
            if "BFILE_ID" in st.secrets and "UFILE_ID" in st.secrets:
                upload_log_to_google_doc(st.secrets["BFILE_ID"], "bot_log.txt")
                upload_log_to_google_doc(st.secrets["UFILE_ID"], "user_log.txt")
            
            return killed or True  # Return True even if no processes were killed
        except Exception as e:
            st.error(f"Failed to stop bot: {e}")
    return False

def start_bot():
    """Start the bot"""
    try:
        # First check if there are any existing bot instances and terminate them
        emergency_stop_bot()
        
        # Initialize logging
        bot_logger, _ = setup_logging()
        bot_logger.info("Starting bot from Streamlit interface")
        
        # Initialize Google Drive service
        drive_service, success, message = setup_google_drive()
        if not success:
            st.error(message)
            return False
        
        # Start the bot
        success = start_bot_in_background()
        if not success:
            st.warning("Another instance of the bot is already running. Please stop it first.")
            return False
            
        st.session_state["bot_started"] = True
        st.session_state["last_started"] = datetime.datetime.now()
        
        bot_logger.info("Bot started successfully")
        return True
    except Exception as e:
        st.error(f"Failed to start bot: {e}")
        return False

# Add this function to forcefully terminate any running bot instances
def emergency_stop_bot():
    """Forcefully terminate any running bot instances"""
    try:
        # Find all python processes
        killed_processes = 0
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                # Check if this is a python process running our bot
                if proc.info['name'] == 'python' and proc.info['cmdline'] and any('bot.py' in cmd for cmd in proc.info['cmdline']):
                    # Skip our own process
                    if proc.pid != os.getpid():
                        st.warning(f"Killing bot process with PID {proc.pid}")
                        # Use SIGKILL directly
                        os.kill(proc.pid, signal.SIGKILL)
                        killed_processes += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
                    
        # Remove lock file if it exists
        lock_file = "/tmp/telegram_bot.lock"
        if os.path.exists(lock_file):
            os.remove(lock_file)
            
        st.session_state["bot_started"] = False
        st.session_state["last_stopped"] = datetime.datetime.now()
        
        # Log the emergency stop
        bot_logger, _ = setup_logging()
        bot_logger.info("Bot forcefully terminated from Streamlit interface")
        
        if killed_processes > 0:
            return True
        else:
            st.info("No bot processes found to terminate.")
            return True
    except Exception as e:
        st.error(f"Failed to emergency stop bot: {e}")
        return False

# Initialize logging
bot_logger, user_logger = setup_logging()

# Sidebar
with st.sidebar:
    st.image("https://img.icons8.com/color/96/000000/musical-notes.png", width=100)
    st.title("Navigation")
    
    page = st.radio("Go to", ["Dashboard", "Logs", "Settings", "About"])
    
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
    user_log_recent = get_log_content("user_log.txt", max_lines=5)
    if user_log_recent != "Log file not found.":
        st.code(user_log_recent, language="text")
    else:
        st.info("No recent user activity found.")

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
    tab1, tab2 = st.tabs(["Bot Log", "User Activity Log"])
    
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

    with tab2:
        st.subheader("User Activity Log")
        
        # Add search filter
        user_search = st.text_input("Filter user logs (case-insensitive):", key="user_search")
        
        # Get log content
        user_log_content = get_log_content("user_log.txt", max_lines=500)
        
        # Apply filters
        if user_search:
            filtered_lines = [line for line in user_log_content.split('\n') 
                             if user_search.lower() in line.lower()]
            user_log_content = '\n'.join(filtered_lines)
        
        # Display logs
        st.code(user_log_content, language="text")

    # Auto-refresh logs
    if st.session_state["bot_started"]:
        if st.button("Refresh Logs"):
            st.rerun()

# Bot information
st.header("Bot Information")
st.markdown("""
This control panel allows you to start and stop the Railway Choir Telegram Bot.

**Features:**
- Search for hymns, lyrics, and convention songs
- Get information about when songs were last sung
- Search by theme or tune
- View song details and history

**Commands:**
- `/start` - Start the bot
- `/help` - Show help information
- `/search` - Search for songs
- `/theme` - Filter songs by theme
- `/tune` - Find tunes by hymn number or tune index
- `/date` - Show songs sung on a specific date"""
 )
st.write("❌ The Telegram bot is not running.")
