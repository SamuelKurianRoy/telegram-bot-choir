# run_bot.py
from bot import run_bot, stop_bot as bot_stop
import threading
import time
import streamlit as st
import os
import signal
import psutil

# Add at the top of the file
STOP_SIGNAL_FILE = "/tmp/telegram_bot_stop_signal"

# Global flag to control the bot thread
bot_running = False
bot_thread = None

def start_bot_in_background(log_upload_interval=60):
    global bot_running, bot_thread
    
    # First, make sure no other instances are running
    stop_all_bot_instances()
    
    # Remove any existing stop signal file
    if os.path.exists(STOP_SIGNAL_FILE):
        os.remove(STOP_SIGNAL_FILE)
    
    # Remove any existing lock file
    lock_file = "/tmp/telegram_bot.lock"
    if os.path.exists(lock_file):
        os.remove(lock_file)
    
    # Wait a moment to ensure cleanup is complete
    time.sleep(1)
    
    # Set the flag to True
    bot_running = True
    
    # Create and start the thread
    bot_thread = threading.Thread(
        target=run_bot_wrapper, 
        args=(log_upload_interval,),
        daemon=True
    )
    bot_thread.start()
    
    # Wait a bit to see if the bot started successfully
    time.sleep(3)
    
    # Check if the bot is still running
    if not bot_running:
        # Bot failed to start
        st.session_state["bot_started"] = False
        return False
    
    # Update session state
    st.session_state["bot_started"] = True
    return True

def run_bot_wrapper(log_upload_interval=60):
    global bot_running
    
    # Set environment variable for log upload interval
    os.environ["LOG_UPLOAD_INTERVAL"] = str(log_upload_interval * 60)  # Convert minutes to seconds
    
    try:
        print("Starting bot...")
        success = run_bot()
        if not success:
            print("Bot failed to start or was stopped")
            bot_running = False
            st.session_state["bot_started"] = False
    except Exception as e:
        print(f"Error running bot: {e}")
        bot_running = False
        st.session_state["bot_started"] = False

def stop_bot_in_background():
    global bot_running, bot_thread
    
    # Create a stop signal file
    with open(STOP_SIGNAL_FILE, 'w') as f:
        f.write(str(time.time()))
    
    # Call the bot's stop function
    try:
        success = bot_stop()
    except Exception as e:
        print(f"Error in bot_stop: {e}")
        success = False
    
    # Wait a bit for the bot to stop
    time.sleep(3)
    
    # Then forcefully terminate any running bot processes
    killed = stop_all_bot_instances()
    
    # Update flags
    bot_running = False
    st.session_state["bot_started"] = False
    
    return success or killed

def stop_all_bot_instances():
    """Stop all running bot instances"""
    try:
        # Create a stop signal file
        with open(STOP_SIGNAL_FILE, 'w') as f:
            f.write(str(time.time()))
        
        # Wait a bit for the bot to detect the signal
        time.sleep(2)
        
        # Remove any existing lock file
        lock_file = "/tmp/telegram_bot.lock"
        if os.path.exists(lock_file):
            os.remove(lock_file)
        
        # Now forcefully kill any remaining processes
        killed = False
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if proc.info['name'] == 'python' and proc.info['cmdline']:
                    cmdline = ' '.join(proc.info['cmdline'])
                    if 'bot.py' in cmdline and proc.pid != os.getpid():
                        print(f"Killing bot process with PID {proc.pid}")
                        try:
                            os.kill(proc.pid, signal.SIGKILL)
                            killed = True
                        except Exception as e:
                            print(f"Failed to kill process {proc.pid}: {e}")
            except Exception as e:
                continue
        
        # Wait a moment to ensure processes are terminated
        time.sleep(1)
        
        return killed or True
    except Exception as e:
        print(f"Error stopping bot instances: {e}")
        return False
