# run_bot.py
from bot import run_bot
import threading

def start_bot_in_background():
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
