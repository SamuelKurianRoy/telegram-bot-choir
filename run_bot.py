# run_bot.py
from bot import run_bot, stop_bot as bot_stop
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
    bot_thread = threading.Thread(target=run_bot_wrapper, daemon=True)
    bot_thread.start()
    
    # Wait a bit to see if the bot started successfully
    time.sleep(2)
    
    # Check if the bot is still running
    if not bot_running:
        # Bot failed to start
        st.session_state["bot_started"] = False
        return False
    
    # Update session state
    st.session_state["bot_started"] = True
    return True

def run_bot_wrapper():
    global bot_running
    success = run_bot()
    if not success:
        bot_running = False
        st.session_state["bot_started"] = False

def stop_bot_in_background():
    global bot_running
    
    # Call the bot's stop function
    success = bot_stop()
    
    # Update flags
    bot_running = False
    st.session_state["bot_started"] = False
    
    return success
