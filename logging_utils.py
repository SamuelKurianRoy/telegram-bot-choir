# logging_utils.py
# Logging setup and helpers 

import logging
import sys

def setup_loggers():
    """
    Set up and return bot and user loggers with console and file handlers.
    """
    # Bot logger
    bot_logger = logging.getLogger("telegram_bot")
    if not bot_logger.handlers:
        bot_logger.setLevel(logging.INFO)
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(logging.Formatter('%(message)s'))
        bot_logger.addHandler(console_handler)
        # File handler
        file_handler = logging.FileHandler("bot_log.txt", encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
        bot_logger.addHandler(file_handler)
    # User logger
    user_logger = logging.getLogger("user_logger")
    if not user_logger.handlers:
        user_logger.setLevel(logging.INFO)
        user_logger.propagate = False
        user_handler = logging.FileHandler("user_log.txt", encoding='utf-8')
        user_handler.setFormatter(logging.Formatter("%(asctime)s - %(message)s"))
        user_logger.addHandler(user_handler)
    return bot_logger, user_logger 