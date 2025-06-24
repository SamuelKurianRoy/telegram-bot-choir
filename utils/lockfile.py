# utils/lockfile.py
# Lock file and stop signal logic

import os
import sys

LOCK_FILE = "/tmp/telegram_bot.lock"
STOP_SIGNAL_FILE = "/tmp/telegram_bot_stop_signal"

def acquire_lock():
    """
    Try to acquire a lock file to ensure only one bot instance runs.
    """
    try:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
        with open(LOCK_FILE, 'w') as f:
            f.write(str(os.getpid()))
        return True
    except Exception as e:
        print(f"Error acquiring lock: {e}")
        return False

def release_lock():
    """
    Release the lock file.
    """
    try:
        if os.path.exists(LOCK_FILE):
            with open(LOCK_FILE, 'r') as f:
                pid = f.read().strip()
                if pid == str(os.getpid()):
                    os.remove(LOCK_FILE)
                    return True
        return False
    except Exception as e:
        print(f"Error releasing lock: {e}")
        return False

def check_stop_signal():
    """
    Check if a stop signal file exists.
    """
    return os.path.exists(STOP_SIGNAL_FILE)

# TODO: Add more lock/stop helpers as needed 