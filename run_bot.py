# run_bot.py
from bot import run_bot, stop_bot as bot_stop
import threading
import time
import streamlit as st
import os
import signal
import psutil

# Global flag to control the bot thread
bot_running = False
bot_thread = None

def start_bot_in_background():
    global bot_running, bot_thread
    
    # First, make sure no other instances are running
    stop_all_bot_instances()
    
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
    
    # Also terminate any running bot processes
    stop_all_bot_instances()
    
    # Update flags
    bot_running = False
    st.session_state["bot_started"] = False
    
    return success

def stop_all_bot_instances():
    """Stop all running bot instances"""
    try:
        # Find all python processes
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            # Check if this is a python process running our bot
            if proc.info['name'] == 'python' and proc.info['cmdline'] and any('bot.py' in cmd for cmd in proc.info['cmdline']):
                # Skip our own process
                if proc.pid != os.getpid():
                    try:
                        proc.terminate()
                        proc.wait(timeout=3)
                        if proc.is_running():
                            proc.kill()
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        continue
        
        # Remove lock file if it exists
        lock_file = "/tmp/telegram_bot.lock"
        if os.path.exists(lock_file):
            os.remove(lock_file)
            
        return True
    except Exception as e:
        print(f"Error stopping bot instances: {e}")
        return False
