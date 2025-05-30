# run_bot.py
from bot import run_bot
import threading
import time
import streamlit as st

# Global flag to control the bot thread
bot_running = False
bot_thread = None

def start_bot_in_background():
    global bot_running, bot_thread
    
    # Set the flag to True
    bot_running = True
    
    # Create and start the thread
    bot_thread = threading.Thread(target=run_bot_with_check, daemon=True)
    bot_thread.start()

def run_bot_with_check():
    global bot_running
    # This function will be called in a separate thread
    # It will check the bot_running flag periodically
    
    # Start the bot
    try:
        run_bot()
    except Exception as e:
        print(f"Bot error: {e}")
        bot_running = False
        st.session_state["bot_started"] = False
