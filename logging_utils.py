# logging_utils.py
# Logging setup and helpers 

import logging
import sys

# Create logger instances
logger = logging.getLogger("telegram_bot")
user_logger = logging.getLogger("user_logger")
downloader_logger = logging.getLogger("downloader_logger")

def setup_loggers():
    """
    Set up and return bot and user loggers with console and file handlers.
    """
    # Bot logger
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(logging.Formatter('%(message)s'))
        logger.addHandler(console_handler)
        # File handler
        file_handler = logging.FileHandler("bot_log.txt", encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
        logger.addHandler(file_handler)

    # User logger
    if not user_logger.handlers:
        user_logger.setLevel(logging.INFO)
        user_logger.propagate = False
        user_handler = logging.FileHandler("user_log.txt", encoding='utf-8')
        user_handler.setFormatter(logging.Formatter("%(asctime)s - %(message)s"))
        user_logger.addHandler(user_handler)
    
    # Downloader logger
    if not downloader_logger.handlers:
        downloader_logger.setLevel(logging.INFO)
        downloader_logger.propagate = False
        downloader_handler = logging.FileHandler("downloader_log.txt", encoding='utf-8')
        downloader_handler.setFormatter(logging.Formatter("%(asctime)s - %(message)s"))
        downloader_logger.addHandler(downloader_handler)

    return logger, user_logger