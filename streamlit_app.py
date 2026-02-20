import streamlit as st
import os
import signal
import time
import sys
import json
import logging
import datetime
from zoneinfo import ZoneInfo
import hashlib
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

# Import Google OAuth module
try:
    import google_oauth
    GOOGLE_OAUTH_AVAILABLE = True
except ImportError:
    GOOGLE_OAUTH_AVAILABLE = False

# Add at the top of the file
STOP_SIGNAL_FILE = "/tmp/telegram_bot_stop_signal"

# Multi-user authentication system
# Default users (can be overridden via environment variables)
DEFAULT_USERS = {
    "admin": "AdminPass2024!",
    "choir_leader": "ChoirLead123!",
    "music_director": "MusicDir456!",
    "organist": "Organist789!",
    "secretary": "Secretary012!",
    "assistant": "Assistant345!",
    "guest": "GuestUser678!"
}

# Helper function to convert timestamp to IST
def convert_to_ist(timestamp_str):
    """Convert ISO timestamp to IST (Indian Standard Time)"""
    try:
        # Parse the ISO timestamp (assumes UTC if no timezone info)
        dt = datetime.datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))

        # If no timezone info, assume UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo('UTC'))

        # Convert to IST
        ist_dt = dt.astimezone(ZoneInfo('Asia/Kolkata'))

        # Return formatted string
        return ist_dt.strftime('%Y-%m-%d %H:%M:%S IST')
    except Exception as e:
        # Fallback to original timestamp if conversion fails
        return timestamp_str

# Load users from Google Sheet or environment variable
def load_users():
    """Load user credentials from Google Sheet, environment, or use defaults"""
    try:
        # Try to load from Google Sheet first (new method)
        from data.auth import get_bot_users
        bot_users = get_bot_users()
        if bot_users:
            return bot_users
    except Exception as e:
        pass  # Silently handle errors
    
    # Fallback to environment variable (old method)
    import json
    users_json = os.getenv("BOT_USERS")
    if users_json:
        try:
            return json.loads(users_json)
        except json.JSONDecodeError:
            st.error("❌ Invalid BOT_USERS environment variable format")
            return DEFAULT_USERS

    # Use default users as last resort
    return DEFAULT_USERS

BOT_USERS = load_users()

# Bot operation logging system
BOT_LOG_FILE = "bot_operations.json"

def load_bot_log():
    """Load bot operation log from file"""
    if os.path.exists(BOT_LOG_FILE):
        try:
            with open(BOT_LOG_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {"operations": [], "current_status": {"running": False, "started_by": None, "started_at": None}}
    return {"operations": [], "current_status": {"running": False, "started_by": None, "started_at": None}}

def save_bot_log(log_data):
    """Save bot operation log to file"""
    try:
        with open(BOT_LOG_FILE, 'w') as f:
            json.dump(log_data, f, indent=2)
    except Exception as e:
        st.error(f"❌ Failed to save bot log: {e}")

def log_bot_operation(user, action, success=True, details=None):
    """Log a bot operation (start/stop) and sync to Google Sheets"""
    log_data = load_bot_log()

    operation = {
        "timestamp": datetime.datetime.now().isoformat(),
        "user": user,
        "action": action,  # "start" or "stop"
        "success": success,
        "details": details or ""
    }

    log_data["operations"].append(operation)

    # Update current status
    if success:
        if action == "start":
            log_data["current_status"] = {
                "running": True,
                "started_by": user,
                "started_at": operation["timestamp"]
            }
        elif action == "stop":
            log_data["current_status"] = {
                "running": False,
                "started_by": None,
                "started_at": None
            }

    # Keep only last 100 operations to prevent file from growing too large
    if len(log_data["operations"]) > 100:
        log_data["operations"] = log_data["operations"][-100:]

    save_bot_log(log_data)

    # Sync to Google Sheets if successful operation
    if success:
        sync_operation_to_google_sheet(operation)

    return operation

def get_bot_status():
    """Get current bot status from log"""
    log_data = load_bot_log()
    return log_data["current_status"]

def get_recent_operations(limit=10):
    """Get recent bot operations"""
    log_data = load_bot_log()
    return log_data["operations"][-limit:] if log_data["operations"] else []

def check_google_sheets_credentials():
    """Check if all required Google Sheets credentials are available"""
    required_keys = [
        "BOT_OPERATIONS_SHEET_ID",
        "type", "project_id", "private_key_id",
        "client_email", "client_id", "auth_uri", "token_uri",
        "auth_provider_x509_cert_url", "client_x509_cert_url"
    ]

    missing_keys = []
    for key in required_keys:
        if key not in st.secrets:
            missing_keys.append(key)

    # Check if private key is available (either as single key or split lines)
    has_private_key = False
    
    # First, try the new single private_key method
    try:
        if "private_key" in st.secrets and st.secrets.get("private_key"):
            has_private_key = True
    except (KeyError, AttributeError):
        pass
    
    # If not found, try the old line-by-line method
    if not has_private_key:
        try:
            private_key_lines = [st.secrets.get(f"l{i}") for i in range(1, 29)]
            if any(private_key_lines):
                has_private_key = True
        except (KeyError, AttributeError):
            pass
    
    if not has_private_key:
        missing_keys.append("private_key (or l1-l28 lines)")

    return len(missing_keys) == 0, missing_keys

def sync_operation_to_google_sheet(operation):
    """Sync a single operation to Google Sheets"""
    try:
        # Check if all required credentials are available
        credentials_available, missing_keys = check_google_sheets_credentials()
        if not credentials_available:
            print(f"Google Sheets sync skipped - missing keys: {missing_keys}")
            return False

        # Load private key (try direct method first, fallback to line-by-line)
        try:
            private_key = st.secrets.get("private_key")
        except (KeyError, AttributeError):
            private_key = None
        
        if not private_key:
            try:
                lines = [st.secrets.get(f"l{i}") for i in range(1, 29)]
                private_key = "\n".join([l for l in lines if l])
            except (KeyError, AttributeError):
                private_key = ""

        # Setup Google Sheets service
        credentials_info = {
            "type": st.secrets["type"],
            "project_id": st.secrets["project_id"],
            "private_key_id": st.secrets["private_key_id"],
            "private_key": private_key,
            "client_email": st.secrets["client_email"],
            "client_id": st.secrets["client_id"],
            "auth_uri": st.secrets["auth_uri"],
            "token_uri": st.secrets["token_uri"],
            "auth_provider_x509_cert_url": st.secrets["auth_provider_x509_cert_url"],
            "client_x509_cert_url": st.secrets["client_x509_cert_url"]
        }

        credentials = service_account.Credentials.from_service_account_info(credentials_info)
        service = build('sheets', 'v4', credentials=credentials)

        # Prepare the data row
        timestamp = datetime.datetime.fromisoformat(operation["timestamp"]).strftime('%Y-%m-%d %H:%M:%S')
        user = operation["user"]
        status = operation["action"].title()  # "Start" or "Stop"

        # Data to append
        values = [[user, timestamp, status]]

        # Append to the sheet
        sheet_id = st.secrets["BOT_OPERATIONS_SHEET_ID"]
        range_name = "Sheet1!A:C"  # Assuming columns A, B, C for User, Time, Status

        body = {
            'values': values
        }

        result = service.spreadsheets().values().append(
            spreadsheetId=sheet_id,
            range=range_name,
            valueInputOption='RAW',
            body=body
        ).execute()

        return True

    except Exception as e:
        print(f"Failed to sync to Google Sheets: {e}")
        return False

def sync_all_operations_to_google_sheet():
    """Sync all operations to Google Sheets (one-time setup)"""
    try:
        # Check if all required credentials are available
        credentials_available, missing_keys = check_google_sheets_credentials()
        if not credentials_available:
            st.error(f"❌ Missing Google Sheets credentials: {', '.join(missing_keys)}")
            st.info("💡 Please add all required Google service account credentials to your Streamlit secrets")
            return False

        # Reconstruct private key from split lines (same as existing codebase)
        lines = [st.secrets.get(f"l{i}") for i in range(1, 29)]
        private_key = "\n".join([l for l in lines if l])

        # Setup Google Sheets service
        credentials_info = {
            "type": st.secrets["type"],
            "project_id": st.secrets["project_id"],
            "private_key_id": st.secrets["private_key_id"],
            "private_key": private_key,
            "client_email": st.secrets["client_email"],
            "client_id": st.secrets["client_id"],
            "auth_uri": st.secrets["auth_uri"],
            "token_uri": st.secrets["token_uri"],
            "auth_provider_x509_cert_url": st.secrets["auth_provider_x509_cert_url"],
            "client_x509_cert_url": st.secrets["client_x509_cert_url"]
        }

        credentials = service_account.Credentials.from_service_account_info(credentials_info)
        service = build('sheets', 'v4', credentials=credentials)

        # Get all operations
        log_data = load_bot_log()
        operations = log_data["operations"]

        if not operations:
            st.info("No operations to sync")
            return True

        # Prepare header and data
        header = [["User", "Time", "Status"]]
        data_rows = []

        for op in operations:
            timestamp = datetime.datetime.fromisoformat(op["timestamp"]).strftime('%Y-%m-%d %H:%M:%S')
            user = op["user"]
            status = op["action"].title()
            data_rows.append([user, timestamp, status])

        # Clear existing data and add header + data
        sheet_id = st.secrets["BOT_OPERATIONS_SHEET_ID"]

        # Clear the sheet first
        service.spreadsheets().values().clear(
            spreadsheetId=sheet_id,
            range="Sheet1!A:C"
        ).execute()

        # Add header and data
        all_data = header + data_rows
        body = {
            'values': all_data
        }

        result = service.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range="Sheet1!A1",
            valueInputOption='RAW',
            body=body
        ).execute()

        st.success(f"✅ Synced {len(data_rows)} operations to Google Sheets")
        return True

    except Exception as e:
        st.error(f"❌ Failed to sync to Google Sheets: {e}")
        return False

# Disable file watching to avoid inotify limits
os.environ["STREAMLIT_SERVER_FILE_WATCHER_TYPE"] = "none"

# Authentication functions
def check_password():
    """Returns True if the user has entered the correct username and password."""

    # Session timeout (30 minutes)
    SESSION_TIMEOUT = 30 * 60  # 30 minutes in seconds
    
    # Handle Google OAuth callback if available
    if GOOGLE_OAUTH_AVAILABLE:
        if google_oauth.handle_oauth_callback():
            return True

    def credentials_entered():
        """Checks whether username and password entered by the user are correct."""
        import hashlib
        
        username = st.session_state.get("username", "").strip()
        password = st.session_state.get("password", "")

        if username in BOT_USERS:
            # Hash the entered password
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            stored_hash = BOT_USERS[username]
            
            # Check if stored value is already hashed (64 characters) or plain text
            if len(stored_hash) == 64:  # SHA256 hash
                is_correct = stored_hash == password_hash
            else:  # Plain text (legacy support)
                is_correct = stored_hash == password
            
            if is_correct:
                st.session_state["password_correct"] = True
                st.session_state["current_user"] = username
                st.session_state["login_time"] = time.time()
                # Clear credentials from session state
                if "username" in st.session_state:
                    del st.session_state["username"]
                if "password" in st.session_state:
                    del st.session_state["password"]
                return
        
        st.session_state["password_correct"] = False
        st.session_state["login_error"] = True

    # Check session timeout
    if "login_time" in st.session_state:
        if time.time() - st.session_state["login_time"] > SESSION_TIMEOUT:
            st.session_state["password_correct"] = False
            if "login_time" in st.session_state:
                del st.session_state["login_time"]
            if "current_user" in st.session_state:
                del st.session_state["current_user"]
            st.warning("⏰ Session expired. Please login again.")

    if "password_correct" not in st.session_state:
        # First run, show login or password reset form
        
        # Show Password Reset Form if requested
        if st.session_state.get("show_forgot_password"):
            # st.markdown("<div class='glass-container'>", unsafe_allow_html=True)
            st.markdown("<div class='reset-title'>🔓 Password Reset</div>", unsafe_allow_html=True)
            st.markdown("<p style='color: white; text-align: center; margin-bottom: 2rem;'>Enter your username to receive a temporary password via email.</p>", unsafe_allow_html=True)
            
            st.markdown("<div class='field-label'>👤 Username</div>", unsafe_allow_html=True)
            reset_username = st.text_input(
                "Username",
                key="reset_username",
                placeholder="Enter your username...",
                label_visibility="collapsed"
            )
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("📧 Send Reset Email", type="primary", use_container_width=True):
                    if reset_username:
                        from data.auth import reset_password_for_user
                        success, message = reset_password_for_user(reset_username)
                        if success:
                            st.success(message)
                            st.info("💡 Check your email for the temporary password. You can change it after logging in.")
                            time.sleep(3)
                            st.session_state["show_forgot_password"] = False
                            st.rerun()
                        else:
                            st.error(message)
                    else:
                        st.warning("⚠️ Please enter your username.")
            
            with col2:
                if st.button("🔙 Back to Login", use_container_width=True):
                    st.session_state["show_forgot_password"] = False
                    st.rerun()
            # st.markdown("</div>", unsafe_allow_html=True)
        
        else:
            # Show Login Form - Centered
            st.markdown("<div class='login-container'>", unsafe_allow_html=True)
            st.markdown("<div class='login-title'>Sign In</div>", unsafe_allow_html=True)
            
            # Username field
            st.markdown("<div class='input-label'>Username</div>", unsafe_allow_html=True)
            st.text_input(
                "Username",
                key="username",
                placeholder="Enter your username",
                label_visibility="collapsed"
            )
            
            # Password field
            st.markdown("<div class='input-label'>Password</div>", unsafe_allow_html=True)
            st.text_input(
                "Password",
                type="password",
                key="password",
                placeholder="Enter your password",
                label_visibility="collapsed"
            )

            # Login button
            if st.button("Sign In", type="primary", use_container_width=True, key="signin_btn"):
                credentials_entered()
                if st.session_state.get("password_correct"):
                    st.success(f"Welcome, {st.session_state['current_user']}!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("Login failed. Please check your credentials.")
            
            # Forgot password link
            st.markdown("<div class='forgot-password-link'><a href='#' onclick='return false;'>Forgot Password?</a></div>", unsafe_allow_html=True)
            if st.button("Forgot Password?", key="forgot_link", use_container_width=True):
                st.session_state["show_forgot_password"] = True
                st.rerun()
            
            # Google Sign In option
            if GOOGLE_OAUTH_AVAILABLE:
                st.markdown("<div class='divider-text'>Or</div>", unsafe_allow_html=True)
                google_oauth.render_google_signin_button()

            if st.session_state.get("login_error"):
                st.error("❌ Invalid username or password. Please try again.")
                st.session_state["login_error"] = False
            
            st.markdown("</div>", unsafe_allow_html=True)

        return False
    elif not st.session_state["password_correct"]:
        # Credentials not correct, show login or password reset form
        
        # Show Password Reset Form if requested
        if st.session_state.get("show_forgot_password"):
            # st.markdown("<div class='glass-container'>", unsafe_allow_html=True)
            st.markdown("<div class='reset-title'>🔓 Password Reset</div>", unsafe_allow_html=True)
            st.markdown("<p style='color: white; text-align: center; margin-bottom: 2rem;'>Enter your username to receive a temporary password via email.</p>", unsafe_allow_html=True)
            
            st.markdown("<div class='field-label'>👤 Username</div>", unsafe_allow_html=True)
            reset_username = st.text_input(
                "Username",
                key="reset_username2",
                placeholder="Enter your username...",
                label_visibility="collapsed"
            )
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("📧 Send Reset Email", key="send_reset2", type="primary", use_container_width=True):
                    if reset_username:
                        from data.auth import reset_password_for_user
                        success, message = reset_password_for_user(reset_username)
                        if success:
                            st.success(message)
                            st.info("💡 Check your email for the temporary password. You can change it after logging in.")
                            time.sleep(3)
                            st.session_state["show_forgot_password"] = False
                            st.rerun()
                        else:
                            st.error(message)
                    else:
                        st.warning("⚠️ Please enter your username.")
            
            with col2:
                if st.button("🔙 Back to Login", key="cancel_reset2", use_container_width=True):
                    st.session_state["show_forgot_password"] = False
                    st.rerun()
            # st.markdown("</div>", unsafe_allow_html=True)
        
        else:
            # Show Login Form - Centered
            st.markdown("<div class='login-container'>", unsafe_allow_html=True)
            st.markdown("<div class='login-title'>Sign In</div>", unsafe_allow_html=True)
            
            # Username field
            st.markdown("<div class='input-label'>Username</div>", unsafe_allow_html=True)
            st.text_input(
                "Username",
                key="username",
                placeholder="Enter your username",
                label_visibility="collapsed"
            )
            
            # Password field
            st.markdown("<div class='input-label'>Password</div>", unsafe_allow_html=True)
            st.text_input(
                "Password",
                type="password",
                key="password",
                placeholder="Enter your password",
                label_visibility="collapsed"
            )

            # Login button
            if st.button("Sign In", type="primary", use_container_width=True, key="signin_btn2"):
                credentials_entered()
                if st.session_state.get("password_correct"):
                    st.success(f"✅ Welcome, {st.session_state['current_user']}!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("❌ Login failed. Please check your credentials.")
            
            # Forgot password link
            st.markdown("<div class='forgot-password-link'><a href='#' onclick='return false;'>Forgot Password?</a></div>", unsafe_allow_html=True)
            if st.button("Forgot Password?", key="forgot_link2", use_container_width=True):
                st.session_state["show_forgot_password"] = True
                st.rerun()
            
            # Google Sign In option
            if GOOGLE_OAUTH_AVAILABLE:
                st.markdown("<div class='divider-text'>Or</div>", unsafe_allow_html=True)
                google_oauth.render_google_signin_button()

            st.error("❌ Invalid username or password. Please try again.")
            st.markdown("</div>", unsafe_allow_html=True)
        return False
    else:
        # Credentials correct
        return True

# Set page config
st.set_page_config(
    page_title="Choir Bot",
    page_icon="🎶",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Load and encode background image
import base64
def get_base64_image(image_path):
    """Convert image to base64 for embedding in CSS"""
    try:
        with open(image_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode()
    except Exception as e:
        return None

# Get background image
bg_image = get_base64_image("Chruch.jpg")

# Custom CSS with background image
bg_style = ""
if bg_image:
    bg_style = f"""
    .stApp {{
        background: linear-gradient(rgba(0, 0, 0, 0.3), rgba(0, 0, 0, 0.3)), 
                    url(data:image/jpeg;base64,{bg_image});
        background-size: cover;
        background-position: center;
        background-repeat: no-repeat;
        background-attachment: fixed;
    }}
    """

st.markdown(f"""
<style>
    {bg_style}
    /* Hide Streamlit header and toolbar completely */
    header {{
        visibility: hidden !important;
        display: none !important;
        height: 0 !important;
    }}
    #MainMenu {{
        visibility: hidden !important;
        display: none !important;
    }}
    footer {{
        visibility: hidden !important;
        display: none !important;
    }}
    .stDeployButton {{
        visibility: hidden !important;
        display: none !important;
    }}
    [data-testid="stHeader"] {{
        display: none !important;
        visibility: hidden !important;
        height: 0 !important;
    }}
    [data-testid="stToolbar"] {{
        display: none !important;
        visibility: hidden !important;
    }}
    [data-testid="stDecoration"] {{
        display: none !important;
        visibility: hidden !important;
    }}
    [data-testid="stStatusWidget"] {{
        display: none !important;
        visibility: hidden !important;
    }}
    /* Remove top padding caused by header */
    .stApp {{
        padding-top: 0 !important;
        margin-top: 0 !important;
    }}
    .stApp > header {{
        background-color: transparent !important;
        display: none !important;
    }}
    div[data-testid="stAppViewContainer"] {{
        padding-top: 0 !important;
        margin-top: 0 !important;
    }}
    .appview-container {{
        padding-top: 0 !important;
        margin-top: 0 !important;
    }}
    section[data-testid="stSidebar"] > div {{
        padding-top: 2rem !important;
    }}
    .block-container {{
        padding-top: 2rem !important;
        padding-bottom: 0 !important;
    }}
    /* Hide empty alert/info boxes */
    .stAlert:empty {{
        display: none !important;
    }}
    div[data-testid="stMarkdownContainer"]:empty {{
        display: none !important;
    }}
    /* Remove extra spacing from first element */
    .block-container > div:first-child {{
        margin-top: 0 !important;
        padding-top: 0 !important;
    }}
    .main-header {{
        font-size: 2.5rem;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        text-align: center;
        font-weight: 800;
        letter-spacing: -0.5px;
        margin-bottom: 0.5rem;
    }}
    /* .glass-container {{
        background: rgba(255, 255, 255, 0.15);
        border-radius: 20px;
        border: 1px solid rgba(255, 255, 255, 0.3);
        box-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.37);
        padding: 3rem 2.5rem;
        max-width: 650px;
        margin: 2rem auto;
    }} */
    /* Centered login container */
    .login-container {{
        max-width: 420px;
        margin: 2rem auto;
        padding: 3rem 2.5rem;
        background: rgba(255, 255, 255, 0.95);
        border-radius: 16px;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
    }}
    .login-title {{
        font-size: 2rem;
        font-weight: 700;
        color: #1a1a1a;
        text-align: center;
        margin-bottom: 2rem;
        letter-spacing: -0.5px;
    }}
    .input-label {{
        font-size: 0.9rem;
        font-weight: 600;
        color: #1a1a1a;
        margin-bottom: 0.5rem;
        margin-top: 1rem;
        display: block;
    }}
    .stTextInput input {{
        background-color: #ffffff !important;
        border: 1.5px solid #d1d5db !important;
        border-radius: 8px !important;
        color: #1a1a1a !important;
        font-size: 1rem !important;
        padding: 0.75rem 1rem !important;
        font-weight: 400 !important;
        box-shadow: none !important;
        transition: all 0.2s ease !important;
        width: 100% !important;
    }}
    .stTextInput input:focus {{
        background-color: #ffffff !important;
        border: 1.5px solid #667eea !important;
        box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1) !important;
        outline: none !important;
    }}
    .stTextInput input::placeholder {{
        color: #9ca3af !important;
        font-weight: 400 !important;
    }}
    .stButton button {{
        width: 100%;
        background-color: #f3f4f6 !important;
        border: 1px solid #d1d5db !important;
        color: #1a1a1a !important;
        font-size: 0.95rem !important;
        padding: 0.65rem 1.2rem !important;
        border-radius: 8px !important;
        font-weight: 500 !important;
        transition: all 0.2s ease !important;
        margin-top: 0.5rem !important;
    }}
    .stButton button:hover {{
        background-color: #e5e7eb !important;
    }}
    .stButton button[kind="primary"] {{
        background-color: #667eea !important;
        color: white !important;
        border: none !important;
        font-size: 1rem !important;
        padding: 0.75rem 1.2rem !important;
        font-weight: 600 !important;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1) !important;
        margin-top: 1.5rem !important;
    }}
    .stButton button[kind="primary"]:hover {{
        background-color: #5568d3 !important;
    }}
    .forgot-password-link {{
        text-align: center;
        margin-top: 1rem;
        display: none;
    }}
    .forgot-password-link a {{
        color: #667eea;
        text-decoration: none;
        font-size: 0.9rem;
        font-weight: 500;
    }}
    .divider-text {{
        text-align: center;
        margin: 1.5rem 0;
        color: #6b7280;
        font-size: 0.9rem;
        font-weight: 500;
    }}
    .field-label {{
        font-size: 0.95rem;
        font-weight: 600;
        color: #ffffff;
        text-shadow: 0 2px 4px rgba(0, 0, 0, 0.3);
        margin-bottom: 0.5rem;
        letter-spacing: 0.3px;
    }}
    .reset-title {{
        font-size: 1.8rem;
        font-weight: 700;
        color: #ffffff;
        text-shadow: 0 2px 8px rgba(0, 0, 0, 0.4);
        margin-bottom: 1rem;
        text-align: center;
    }}
    .sub-header {{
        font-size: 1.8rem;
        color: #0D47A1;
    }}
    .status-running {{
        font-size: 1.5rem;
        color: #4CAF50;
        font-weight: bold;
    }}
    .status-stopped {{
        font-size: 1.5rem;
        color: #F44336;
        font-weight: bold;
    }}
    .info-box {{
        background-color: rgba(227, 242, 253, 0.85);
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 5px solid #1E88E5;
    }}
    .stLinkButton a {{
        background-color: rgba(255, 255, 255, 0.4) !important;
        border: 1px solid rgba(255, 255, 255, 0.5) !important;
    }}
    /* Style alert boxes inside glass container */
    .stAlert {{
        background-color: rgba(255, 255, 255, 0.3) !important;
        border: 1px solid rgba(255, 255, 255, 0.4) !important;
    }}
    /* Style horizontal dividers */
    hr {{
        border-color: rgba(255, 255, 255, 0.3) !important;
    }}
    .log-container {{
        max-height: 500px;
        overflow-y: auto;
        background-color: rgba(245, 245, 245, 0.85);
        padding: 10px;
        border-radius: 5px;
    }}
    [data-testid="stSidebar"] {{
        background-color: rgba(255, 255, 255, 0.95);
    }}
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
        # Load private key (try direct method first, fallback to line-by-line)
        try:
            private_key = st.secrets.get("private_key")
        except (KeyError, AttributeError):
            private_key = None
        
        if not private_key:
            try:
                lines = [st.secrets[f"l{i}"] for i in range(1, 29)]
                private_key = "\n".join(lines)
            except (KeyError, AttributeError):
                private_key = ""
        
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
    """Stop the bot process with logging - works from any session/tab"""
    current_user = st.session_state.get("current_user", "Unknown")

    # Check if bot is actually running according to our log
    bot_status = get_bot_status()
    if not bot_status["running"]:
        st.warning("⚠️ Bot is not currently running according to our records.")
        return False

    try:
        # Create a stop signal file
        with open(STOP_SIGNAL_FILE, 'w') as f:
            f.write(str(datetime.datetime.now()))

        # Call the stop function from run_bot.py
        success = stop_bot_in_background()

        # Update session state (if it exists)
        if "bot_started" in st.session_state:
            st.session_state["bot_started"] = False
        st.session_state["last_stopped"] = datetime.datetime.now()

        # Log the stop event
        bot_logger, _ = setup_logging()
        bot_logger.info(f"Bot stopped from Streamlit interface by user: {current_user}")

        if success:
            st.success(f"✅ Bot stopped successfully by **{current_user}**")

            # Log the successful stop operation
            log_bot_operation(current_user, "stop", success=True,
                            details="Bot stopped normally")
        else:
            st.warning("⚠️ Bot stop command sent, but success not confirmed")

            # Log the potentially failed stop operation
            log_bot_operation(current_user, "stop", success=False,
                            details="Bot stop command sent but success not confirmed")

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

        # Log the failed stop operation
        log_bot_operation(current_user, "stop", success=False,
                        details=f"Exception: {str(e)}")
        return False

def start_bot():
    """Start the bot with logging and status checking"""
    current_user = st.session_state.get("current_user", "Unknown")

    # Check if bot is already running according to our log
    bot_status = get_bot_status()
    if bot_status["running"]:
        started_by = bot_status["started_by"]
        started_at_ist = convert_to_ist(bot_status["started_at"])

        if started_by == current_user:
            st.warning(f"⚠️ Bot is already running! You started it at {started_at_ist}")
        else:
            st.error(f"❌ Bot is already running! Started by **{started_by}** at {started_at_ist}")
            st.info("💡 Please coordinate with the other user or use the Emergency Stop if needed.")

        return False

    try:
        # First check if there are any existing bot instances and terminate them
        st.info("Checking for existing bot instances...")
        emergency_stop_bot()

        # Initialize logging
        bot_logger, _ = setup_logging()
        bot_logger.info(f"Starting bot from Streamlit interface by user: {current_user}")

        # Initialize Google Drive service
        st.info("Initializing Google Drive service...")
        drive_service, success, message = setup_google_drive()
        if not success:
            st.error(message)
            # Log the failed start operation
            log_bot_operation(current_user, "start", success=False,
                            details=f"Google Drive initialization failed: {message}")
            return False

        # Get log upload interval from session state (default to 60 minutes)
        log_upload_interval = st.session_state.get("log_upload_interval", 60)

        # Start the bot
        st.info(f"Starting bot with log upload interval of {log_upload_interval} minutes...")
        success = start_bot_in_background(log_upload_interval)
        if not success:
            st.warning("Failed to start the bot. Check the logs for details.")
            # Log the failed start operation
            log_bot_operation(current_user, "start", success=False,
                            details="Bot background process failed to start")
            return False

        st.session_state["bot_started"] = True
        st.session_state["last_started"] = datetime.datetime.now()

        st.success(f"✅ Bot started successfully by **{current_user}**")
        bot_logger.info(f"Bot started successfully with log upload interval of {log_upload_interval} minutes by user: {current_user}")

        # Log the successful start operation
        log_bot_operation(current_user, "start", success=True,
                        details=f"Bot started with log upload interval of {log_upload_interval} minutes")

        return True
    except Exception as e:
        st.error(f"Failed to start bot: {e}")

        # Log the failed start operation
        log_bot_operation(current_user, "start", success=False,
                        details=f"Exception: {str(e)}")

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

# Add a debug option to reset authentication (remove this in production)
if st.query_params.get("reset_auth") == "true":
    for key in ["password_correct", "login_time"]:
        if key in st.session_state:
            del st.session_state[key]
    st.info("🔄 Authentication reset. Please refresh the page.")
    st.stop()

# Check authentication before showing main content
if not check_password():
    # Force stop execution if not authenticated
    st.stop()

# Add a header to confirm authentication worked
current_user = st.session_state.get("current_user", "Unknown")
st.markdown(f"✅ **Welcome, {current_user.title()}!** - You have access to bot controls")

# Show user info and logout option in sidebar after authentication
with st.sidebar:
    st.markdown("---")
    # Show current user
    st.markdown(f"👤 **User:** {current_user.title()}")

    # Show session info
    if "login_time" in st.session_state:
        session_duration = int(time.time() - st.session_state["login_time"])
        session_remaining = max(0, 30*60 - session_duration)  # 30 min timeout
        st.markdown(f"🔐 **Session:** {session_remaining//60}m {session_remaining%60}s left")

    if st.button("🔓 Logout", help="Logout and require authentication again"):
        # Clear all authentication-related session state
        for key in ["password_correct", "login_time", "current_user"]:
            if key in st.session_state:
                del st.session_state[key]
        st.success("👋 Logged out successfully!")
        time.sleep(1)
        st.rerun()
    st.markdown("---")

# Sidebar
with st.sidebar:
    st.image("https://img.icons8.com/color/96/000000/musical-notes.png", width=100)
    st.title("Navigation")
    
    page = st.radio("Go to", ["Dashboard", "Logs", "Settings", "Change Password", "Bible Game", "About"])
    
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
    # Enhanced Status card with logging information
    st.markdown("<h2 class='sub-header'>Bot Status & Control</h2>", unsafe_allow_html=True)

    # Get current bot status from log
    bot_status = get_bot_status()

    col1, col2 = st.columns([1, 2])

    with col1:
        # Show status from our logging system
        if bot_status["running"]:
            st.markdown("<p class='status-running'>🟢 Running</p>", unsafe_allow_html=True)
            started_by = bot_status["started_by"]
            started_at_ist = convert_to_ist(bot_status["started_at"])
            st.info(f"👤 Started by: **{started_by}**")
            st.info(f"⏰ Started at: {started_at_ist}")

            if st.button("Stop Bot", type="primary", key="main_stop"):
                if stop_bot():
                    st.success("Bot stopped successfully!")
                    time.sleep(1)
                    st.rerun()
        else:
            st.markdown("<p class='status-stopped'>🔴 Stopped</p>", unsafe_allow_html=True)
            st.info("Bot is currently not running")

            if st.button("Start Bot", type="primary", key="main_start"):
                if start_bot():
                    st.success("Bot started successfully!")
                    time.sleep(1)
                    st.rerun()

    with col2:
        st.markdown(
            "<div class='info-box'>"
            "<h3>Multi-User Control Panel</h3>"
            "<p>This dashboard allows authorized users to manage the Choir Telegram Bot. "
            "The system tracks who starts and stops the bot to prevent conflicts.</p>"
            "<p>The bot provides search capabilities for hymns, lyrics, and convention songs "
            "through a Telegram interface.</p>"
            "<p><strong>Security Features:</strong></p>"
            "<ul>"
            "<li>👤 User authentication and tracking</li>"
            "<li>📝 Operation logging and history</li>"
            "<li>🚫 Prevention of multiple bot instances</li>"
            "<li>⚠️ Emergency stop capabilities</li>"
            "</ul>"
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

elif page == "Change Password":
    st.markdown("<h1 class='main-header'>🔐 Change Password</h1>", unsafe_allow_html=True)
    
    st.info("Change your Streamlit control panel password. This password is used to access this dashboard.")
    
    current_user = st.session_state.get("current_user", "Unknown")
    
    with st.form("change_password_form"):
        st.markdown(f"**Username:** {current_user}")
        st.markdown("---")
        
        old_password = st.text_input("🔑 Current Password", type="password", help="Enter your current password")
        new_password = st.text_input("🔐 New Password", type="password", help="Enter your new password (minimum 6 characters)")
        confirm_password = st.text_input("🔐 Confirm New Password", type="password", help="Re-enter your new password")
        
        submit_button = st.form_submit_button("Change Password", type="primary", use_container_width=True)
    
    if submit_button:
        # Validation
        if not old_password or not new_password or not confirm_password:
            st.error("❌ All fields are required!")
        elif new_password != confirm_password:
            st.error("❌ New passwords don't match!")
        elif len(new_password) < 6:
            st.error("❌ New password must be at least 6 characters long!")
        elif old_password == new_password:
            st.error("❌ New password must be different from current password!")
        else:
            # Attempt to change password
            try:
                from data.auth import change_bot_user_password
                success, message = change_bot_user_password(current_user, old_password, new_password)
                
                if success:
                    st.success(message)
                    st.success("✅ Please log in again with your new password.")
                    st.balloons()
                    
                    # Log out user
                    time.sleep(2)
                    for key in ["password_correct", "login_time", "current_user"]:
                        if key in st.session_state:
                            del st.session_state[key]
                    st.rerun()
                else:
                    st.error(message)
            except Exception as e:
                st.error(f"❌ Error changing password: {str(e)}")
                st.info("💡 Tip: Make sure Google Sheet authentication is set up correctly. Check AUTH_SETUP_GUIDE.md for details.")
    
    st.markdown("---")
    st.markdown("### 💡 Password Tips")
    st.markdown("""
    - Use at least 6 characters
    - Mix letters, numbers, and symbols
    - Don't reuse passwords from other sites
    - Change your password regularly
    - Keep your password secure and don't share it
    """)

elif page == "About":
    st.markdown("<h1 class='main-header'>About Choir Bot</h1>", unsafe_allow_html=True)

    # Bot information
    st.markdown("## 🎶 Bot Information")
    st.markdown("""
    This control panel allows you to start and stop the Choir Telegram Bot.

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
    - **Bot Development:** Samuel Kurian Roy
    - **Bible Content:** WordProject.org
    - **Framework:** Streamlit + Python Telegram Bot
    - **Hosting:** Streamlit Cloud
    """)
