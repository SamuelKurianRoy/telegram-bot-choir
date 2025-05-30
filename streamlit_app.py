import streamlit as st
import os
import signal
import time
import sys
from pathlib import Path
from run_bot import start_bot_in_background

# Set page config
st.set_page_config(
    page_title="Railway Choir Bot",
    page_icon="🎶",
    layout="wide"
)

# Initialize session state variables
if "bot_started" not in st.session_state:
    st.session_state["bot_started"] = False

# Define paths
base_dir = Path(__file__).parent
logs_dir = base_dir / "logs"
bot_log_path = logs_dir / "bot_log.txt"
user_log_path = logs_dir / "user_log.txt"

# Create logs directory if it doesn't exist
logs_dir.mkdir(exist_ok=True)

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
    if st.session_state["bot_started"]:
        try:
            os.kill(os.getpid(), signal.SIGINT)
            st.session_state["bot_started"] = False
            return True
        except Exception as e:
            st.error(f"Failed to stop bot: {e}")
    return False

# Main app
st.title("🎶 Railway Choir Bot Control Panel")

# Status and control section
st.header("Bot Status")
col1, col2 = st.columns([1, 3])

with col1:
    status = "🟢 Running" if st.session_state["bot_started"] else "🔴 Stopped"
    st.subheader(status)
    
    if st.session_state["bot_started"]:
        if st.button("Stop Bot", type="primary"):
            if stop_bot():
                st.success("Bot stopped successfully!")
                time.sleep(1)
                st.rerun()
    else:
        if st.button("Start Bot", type="primary"):
            start_bot_in_background()
            st.session_state["bot_started"] = True
            st.success("Bot started successfully!")
            time.sleep(1)
            st.rerun()

with col2:
    st.info(
        "This control panel allows you to manage the Railway Choir Telegram Bot. "
        "Start or stop the bot using the controls on the left."
    )

# Log section
st.header("Logs")
tab1, tab2 = st.tabs(["Bot Log", "User Activity Log"])

with tab1:
    st.subheader("Bot Log (Errors & System Messages)")
    
    # Add search filter
    bot_search = st.text_input("Filter bot logs (case-insensitive):", key="bot_search")
    
    # Add log level filter
    bot_log_level = st.selectbox(
        "Filter by log level:",
        ["All", "INFO", "WARNING", "ERROR", "CRITICAL"],
        key="bot_log_level"
    )
    
    # Get log content
    bot_log_content = get_log_content(bot_log_path, max_lines=500)
    
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
    user_log_content = get_log_content(user_log_path, max_lines=500)
    
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
