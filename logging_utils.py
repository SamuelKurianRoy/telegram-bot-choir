# logging_utils.py
# Logging setup and helpers 

import logging
import sys
from typing import Tuple

# Configure root logger
logging.basicConfig(level=logging.INFO)

# Create logger instances
logger = logging.getLogger("telegram_bot")
user_logger = logging.getLogger("user_logger")
downloader_logger = logging.getLogger("downloader_logger")

# Ensure loggers don't propagate to avoid duplicate logs
logger.propagate = False
user_logger.propagate = False
downloader_logger.propagate = False

def setup_loggers() -> Tuple[logging.Logger, logging.Logger]:
    """
    Set up and return bot and user loggers with console and file handlers.
    Configures three loggers:
    - telegram_bot (main logger)
    - user_logger (for user actions)
    - downloader_logger (for download operations)
    """
    def clear_handlers(logger_instance):
        """Helper to safely clear existing handlers"""
        while logger_instance.handlers:
            logger_instance.removeHandler(logger_instance.handlers[0])

    # Bot logger setup
    clear_handlers(logger)
    logger.setLevel(logging.INFO)
    
    # Console handler for main logger
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter('%(message)s'))
    logger.addHandler(console_handler)
    
    # File handler for main logger
    file_handler = logging.FileHandler("bot_log.txt", encoding='utf-8', mode='a')
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(file_handler)

    # User logger setup
    clear_handlers(user_logger)
    user_logger.setLevel(logging.INFO)
    user_handler = logging.FileHandler("user_log.txt", encoding='utf-8', mode='a')
    user_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    user_logger.addHandler(user_handler)
    
    # Downloader logger setup
    clear_handlers(downloader_logger)
    downloader_logger.setLevel(logging.INFO)
    
    # Console handler for downloader (for debugging)
    downloader_console = logging.StreamHandler(sys.stdout)
    downloader_console.setLevel(logging.INFO)
    downloader_console.setFormatter(logging.Formatter('🔽 %(message)s'))
    downloader_logger.addHandler(downloader_console)
    
    # File handler for downloader
    downloader_file = logging.FileHandler("downloader_log.txt", encoding='utf-8', mode='a')
    downloader_file.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    downloader_logger.addHandler(downloader_file)

    return logger, user_logger