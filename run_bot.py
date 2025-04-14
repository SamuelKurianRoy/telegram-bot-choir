# run_bot.py
from bot import run_bot
import threading

def start_bot_in_background():
    thread = threading.Thread(target=run_bot, daemon=True)
    thread.start()
