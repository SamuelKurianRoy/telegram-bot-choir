# run_bot.py
import subprocess
import sys
import time
import streamlit as st
import os
import signal
import psutil

# Add at the top of the file
STOP_SIGNAL_FILE = "/tmp/telegram_bot_stop_signal"

bot_process = None

def start_bot_in_background(log_upload_interval=60):
    global bot_process

    stop_all_bot_instances()  # Clean up any previous bots

    # Remove any existing stop signal file
    if os.path.exists(STOP_SIGNAL_FILE):
        os.remove(STOP_SIGNAL_FILE)
        print(f"Removed stop signal file: {STOP_SIGNAL_FILE}")

    # Remove any existing lock file
    lock_file = "/tmp/telegram_bot.lock"
    if os.path.exists(lock_file):
        os.remove(lock_file)
        print(f"Removed lock file: {lock_file}")

    # Wait a moment to ensure cleanup is complete
    time.sleep(1)

    # Start the bot as a subprocess
    bot_process = subprocess.Popen([sys.executable, "bot.py"])
    # Optionally, you can pass log_upload_interval as an env var or argument

    # Wait a bit to see if the bot started successfully
    time.sleep(3)

    # Update session state
    st.session_state["bot_started"] = True
    return True

def stop_bot_in_background():
    global bot_process
    # Create a stop signal file
    with open(STOP_SIGNAL_FILE, 'w') as f:
        f.write(str(time.time()))
    # Try to terminate the subprocess if running
    if bot_process is not None:
        bot_process.terminate()
        try:
            bot_process.wait(timeout=10)
        except Exception:
            bot_process.kill()
        bot_process = None
    # Also forcefully kill any remaining bot.py processes
    stop_all_bot_instances()
    st.session_state["bot_started"] = False
    return True

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
