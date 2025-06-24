# Debugging: Check if python-telegram-bot is installed and print version
try:
    import telegram
    print(f"python-telegram-bot version: {telegram.__version__}")
    from telegram.ext import Application, CommandHandler, ConversationHandler, MessageHandler, filters, CallbackQueryHandler
except ImportError as e:
    print(f"[DEBUG] ImportError: {e}")
    raise

try:
    from config import get_config
    from data.datasets import reload_all_datasets, get_all_data, Tune_finder_of_known_songs, Tunenofinder
    from data.vocabulary import ChoirVocabulary
    from utils.search import setup_search
    from telegram.handlers import start, help_command, refresh_command, admin_reply, cancel
    from telegram.conversations import (
        check_song_start, check_song_input, ENTER_SONG,
        last_sung_start, last_sung_input, last_sung_show_all, ENTER_LAST_SONG, ASK_SHOW_ALL,
        search_start, search_method_choice, search_index_category, search_by_index, search_number_category, search_by_number,
        tune_command, choose_method, get_input, CHOOSE_METHOD, GET_INPUT,
        start_notation, receive_hymn_number, ASK_HYMN_NO,
        filter_theme, handle_theme_selection, handle_year_filter, THEME_SELECTION, YEAR_FILTER,
        start_vocabulary, category_selection, CATEGORY_SELECTION,
        download_start, download_url_input, download_quality_selection, ENTER_URL, SELECT_QUALITY,
        start_comment, process_comment, COMMENT
    )
except ImportError as e:
    print(f"[DEBUG] ImportError during project imports: {e}")
    raise

import os
from utils.lockfile import acquire_lock, release_lock, LOCK_FILE, STOP_SIGNAL_FILE
import time
from datetime import datetime

# === Load Data and Initialize Global State ===
config = get_config()
data = reload_all_datasets()
dfH = data['dfH']
dfL = data['dfL']
dfC = data['dfC']
df = data['df']
dfTH = data['dfTH']
dfTD = data['dfTD']
# Build vocabulary
Vocabulary, Hymn_Vocabulary, Lyric_Vocabulary, Convention_Vocabulary = ChoirVocabulary(df, dfH, dfL, dfC)
# Setup search
setup_search(dfH, dfL, dfC)

# === Telegram Application Setup ===
app = Application.builder().token(config.TOKEN).build()

# --- Register Modularized Handlers ---
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_command))
app.add_handler(CommandHandler("refresh", refresh_command))
app.add_handler(CommandHandler("reply", admin_reply))
app.add_handler(CommandHandler("cancel", cancel))

check_conv = ConversationHandler(
    entry_points=[CommandHandler('check', check_song_start)],
    states={
        ENTER_SONG: [MessageHandler(filters.TEXT & ~filters.COMMAND, check_song_input)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)
app.add_handler(check_conv)

last_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("last", last_sung_start)],
    states={
        ENTER_LAST_SONG: [MessageHandler(filters.TEXT & ~filters.COMMAND, last_sung_input)],
        ASK_SHOW_ALL: [MessageHandler(filters.TEXT & ~filters.COMMAND, last_sung_show_all)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)
app.add_handler(last_conv_handler)

search_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("search", search_start)],
    states={
        0: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_method_choice)],
        1: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_index_category)],
        2: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_by_index)],
        3: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_number_category)],
        4: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_by_number)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)
app.add_handler(search_conv_handler)

tune_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("tune", tune_command)],
    states={
        CHOOSE_METHOD: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_method)],
        GET_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_input)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)
app.add_handler(tune_conv_handler)

notation_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("notation", start_notation)],
    states={
        ASK_HYMN_NO: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_hymn_number)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)
app.add_handler(notation_conv_handler)

theme_handler = ConversationHandler(
    entry_points=[CommandHandler("theme", filter_theme)],
    states={
        THEME_SELECTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_theme_selection)],
        YEAR_FILTER: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_year_filter)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)
app.add_handler(theme_handler)

vocab_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("vocabulary", start_vocabulary)],
    states={
        CATEGORY_SELECTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, category_selection)]
    },
    fallbacks=[CommandHandler("cancel", cancel)]
)
app.add_handler(vocab_conv_handler)

download_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("download", download_start)],
    states={
        ENTER_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, download_url_input)],
        SELECT_QUALITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, download_quality_selection)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)
app.add_handler(download_conv_handler)

comment_handler = ConversationHandler(
    entry_points=[CommandHandler('comment', start_comment)],
    states={
        COMMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_comment)]
    },
    fallbacks=[CommandHandler('cancel', cancel)]
)
app.add_handler(comment_handler)

bot_should_run = True

def run_bot():
    """Starts the bot with lock and stop signal logic."""
    global bot_should_run
    print("=== BOT STARTUP DEBUG INFO ===")
    print(f"Bot PID: {os.getpid()}")
    print(f"Lock file exists: {os.path.exists(LOCK_FILE)}")
    print(f"Stop signal file exists: {os.path.exists(STOP_SIGNAL_FILE)}")
    print("=============================")
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
        print("Starting main bot function...")
        app.run_polling()
        print("Bot stopped normally")
        return True
    except KeyboardInterrupt:
        print("\nBot was stopped by the user")
        return True
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")
        return False
    finally:
        print("Releasing lock...")
        release_lock()

def stop_bot():
    """Stops the bot gracefully by creating a stop signal file and releasing the lock."""
    global bot_should_run
    bot_should_run = False
    with open(STOP_SIGNAL_FILE, 'w') as f:
        f.write(str(datetime.now()))
    release_lock()
    return True
