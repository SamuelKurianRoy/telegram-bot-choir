import asyncio
import logging
import json
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ConversationHandler, MessageHandler, filters, CallbackContext, ContextTypes, CallbackQueryHandler
from telegram.constants import ParseMode
import os
import streamlit as st
from datetime import datetime
import pandas as pd

# Import our custom modules
from .data_loader import DataLoader
from .search import SearchEngine
from .utils import Utils

# Global variables for controlling bot state
bot_should_run = True
LOCK_FILE = "/tmp/telegram_bot.lock"
STOP_SIGNAL_FILE = "/tmp/telegram_bot_stop_signal"

class TelegramBot:
    def __init__(self):
        # Initialize logger
        self.setup_logging()
        
        # Load environment variables and setup services
        self.setup_environment()
        
        # Initialize data loader and load datasets
        self.data_loader = DataLoader(self.KEY_PATH)
        self.load_data()
        
        # Initialize search engine
        self.search_engine = SearchEngine(self.dfH, self.dfL, self.dfC)
        
        # Initialize utils
        self.utils = Utils()
        
        # Create vocabulary
        self.create_vocabulary()

    def setup_logging(self):
        """Setup logging configuration."""
        # Bot logger setup
        self.bot_logger = logging.getLogger("telegram_bot")
        if not self.bot_logger.handlers:
            self.bot_logger.setLevel(logging.INFO)
            
            # Console handler
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(logging.Formatter('%(message)s'))
            self.bot_logger.addHandler(console_handler)
            
            # File handler
            file_handler = logging.FileHandler("bot_log.txt", mode='w', encoding='utf-8')
            file_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
            self.bot_logger.addHandler(file_handler)
        
        # User logger setup
        self.user_logger = logging.getLogger("user_logger")
        if not self.user_logger.handlers:
            self.user_logger.setLevel(logging.INFO)
            self.user_logger.propagate = False
            
            user_handler = logging.FileHandler("user_log.txt", encoding='utf-8')
            user_handler.setFormatter(logging.Formatter("%(asctime)s - %(message)s"))
            self.user_logger.addHandler(user_handler)

    def setup_environment(self):
        """Setup environment variables and create service account file."""
        # Get service account info from Streamlit secrets
        self.service_account_data = {
            "type": st.secrets["type"],
            "project_id": st.secrets["project_id"],
            "private_key_id": st.secrets["private_key_id"],
            "private_key": "\n".join(st.secrets[f"l{i}"] for i in range(1, 29)),
            "client_email": st.secrets["client_email"],
            "client_id": st.secrets["client_id"],
            "auth_uri": st.secrets["auth_uri"],
            "token_uri": st.secrets["token_uri"],
            "auth_provider_x509_cert_url": st.secrets["auth_provider_x509_cert_url"],
            "client_x509_cert_url": st.secrets["client_x509_cert_url"],
            "universe_domain": st.secrets["universe_domain"],
        }
        
        # Save service account info to file
        self.KEY_PATH = "/tmp/service_account.json"
        with open(self.KEY_PATH, "w") as f:
            json.dump(self.service_account_data, f)
        
        # Set environment variable
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = self.KEY_PATH
        
        # Get bot token
        self.TOKEN = st.secrets["TOKEN"]

    def load_data(self):
        """Load all necessary datasets."""
        (self.dfH, self.dfL, self.dfC, self.yr23, self.yr24, 
         self.yr25, self.df, self.dfTH, self.dfTD) = self.data_loader.load_datasets()
        
        # Preprocess data
        self.data_loader.preprocess_year_data()
        self.data_loader.clean_main_data()

    def create_vocabulary(self):
        """Create vocabulary from the data."""
        # Implementation of vocabulary creation
        pass  # TODO: Implement vocabulary creation

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /start command."""
        welcome_message = (
            "Welcome to the Choir Bot! 🎵\n\n"
            "Here are some commands you can use:\n"
            "/search - Search for hymns\n"
            "/help - Get help with commands\n"
            "/today - See today's songs"
        )
        await update.message.reply_text(welcome_message)

    def run(self):
        """Run the bot."""
        application = Application.builder().token(self.TOKEN).build()
        
        # Add handlers
        application.add_handler(CommandHandler("start", self.start))
        # Add more handlers here
        
        # Start the bot
        application.run_polling()

    @staticmethod
    def acquire_lock():
        """Try to acquire a lock file to ensure only one bot instance runs."""
        try:
            if os.path.exists(LOCK_FILE):
                os.remove(LOCK_FILE)
            
            with open(LOCK_FILE, 'w') as f:
                f.write(str(os.getpid()))
            
            print(f"Lock acquired for PID {os.getpid()}")
            return True
        except Exception as e:
            print(f"Error acquiring lock: {e}")
            return False

    @staticmethod
    def release_lock():
        """Release the lock file."""
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

def main():
    """Main function to run the bot."""
    if TelegramBot.acquire_lock():
        try:
            bot = TelegramBot()
            bot.run()
        finally:
            TelegramBot.release_lock()
    else:
        print("Another instance of the bot is already running.")
