# This is a file rename operation, not a code edit. The contents of bot.py should be moved to main_bot.py, and bot.py should be deleted. 

import os
import asyncio
from datetime import datetime
from bot.logging_utils import setup_bot_logger, setup_user_logger
from bot.config import TOKEN, ADMIN_ID, AUTHORIZED_USERS
from telegram.ext import Application
from bot.handlers import register_handlers

# Add any required global variables and helpers
bot_should_run = True
STOP_SIGNAL_FILE = "/tmp/telegram_bot_stop_signal"

def acquire_lock():
    # Dummy lock implementation for now
    return True

def release_lock():
    # Dummy release implementation for now
    pass

def debug_bot_status():
    print("Debug: Bot status check")

def main():
    print("Starting Railway Choir Telegram Bot...")
    # Set up logging
    bot_logger = setup_bot_logger()
    user_logger = setup_user_logger()
    bot_logger.info("Bot is starting up...")

    # Create the Application
    application = Application.builder().token(TOKEN).build()

    # Register handlers
    dependencies = {
        'user_logger': user_logger,
        'ADMIN_ID': ADMIN_ID,
        'authorized_users': AUTHORIZED_USERS,
    }
    register_handlers(application, dependencies)

    # Start polling (blocking call)
    bot_logger.info("Bot is running. Waiting for messages...")
    application.run_polling()

# --- Inserted from user ---
def run_bot():
    """Starts the bot."""
    global bot_should_run
    # Debug information
    print("=== BOT STARTUP DEBUG INFO ===")
    debug_bot_status()
    print("=============================")
    # Reset the flag when starting
    bot_should_run = True
    # Remove any existing stop signal file
    if os.path.exists(STOP_SIGNAL_FILE):
        os.remove(STOP_SIGNAL_FILE)
        print(f"Removed stop signal file: {STOP_SIGNAL_FILE}")
    # Try to acquire the lock
    print("Attempting to acquire lock...")
    if not acquire_lock():
        print("Another instance of the bot is already running. Aborting.")
        return False
    print(f"Bot starting with PID {os.getpid()}")
    try:
        # Run the bot in the current thread
        print("Starting main bot function...")
        main()
        print("Bot stopped normally")
        return True
    except KeyboardInterrupt:
        print("\nBot was stopped by the user")
        return True
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")
        return False
    finally:
        # Release the lock
        print("Releasing lock...")
        release_lock()

def stop_bot():
    """Stops the bot gracefully by creating a stop signal file."""
    global bot_should_run
    bot_should_run = False
    # Create a stop signal file
    with open(STOP_SIGNAL_FILE, 'w') as f:
        f.write(str(datetime.now()))
    # Dummy logger for now
    print("Bot stop requested")
    # Release the lock
    release_lock()
    return True 