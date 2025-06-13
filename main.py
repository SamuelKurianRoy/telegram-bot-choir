"""
Main entry point for the Telegram bot application.
This file sets up the bot using the modularized components.
"""

import os
import json
import logging
from modules.bot import main as bot_main

if __name__ == "__main__":
    # Setup basic logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)
    
    try:
        bot_main()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot stopped due to error: {e}")
    finally:
        # Clean up any temporary files
        temp_files = [
            "/tmp/telegram_bot.lock",
            "/tmp/telegram_bot_stop_signal",
            "/tmp/service_account.json"
        ]
        for file in temp_files:
            if os.path.exists(file):
                try:
                    os.remove(file)
                    logger.info(f"Cleaned up {file}")
                except Exception as e:
                    logger.error(f"Error cleaning up {file}: {e}")
