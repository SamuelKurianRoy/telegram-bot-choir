# Debugging: Check if python-telegram-bot is installed and print confirmation
try:
    import telegram
    print("python-telegram-bot version:", getattr(telegram, '__version__', 'unknown'))
    from telegram.ext import Application, CommandHandler, ConversationHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes
except ImportError as e:
    print(f"[DEBUG] ImportError: {e}")
    raise

try:
    from config import get_config
    from data.datasets import reload_all_datasets, get_all_data, Tune_finder_of_known_songs, Tunenofinder, load_datasets
    from data.vocabulary import ChoirVocabulary
    from utils.search import setup_search
    from telegram_handlers.handlers import (
        start, help_command, refresh_command, admin_reply, cancel, 
        check_song_start, last_sung_start, check_song_input, ENTER_SONG, 
        last_sung_input, ENTER_LAST_SONG, 
        date_start, date_input, ASK_DATE, last_show_all_dates_callback,
        bible_start, bible_input_handler, bible_confirm_handler, BIBLE_INPUT, BIBLE_CONFIRM
    )
    from telegram_handlers.conversations import (
        SEARCH_METHOD, INDEX_CATEGORY, INDEX_TEXT, NUMBER_CATEGORY, NUMBER_INPUT,
        search_start, search_method_choice, search_index_category, search_by_index, search_number_category, search_by_number,
        tune_command, choose_method, get_input, CHOOSE_METHOD, GET_INPUT,
        notation, notation_code_input, NOTATION_TYPE,
        theme_type_choice, handle_theme_type, handle_theme_selection, handle_year_filter, handle_theme_typo_confirm, THEME_TYPE, THEME_SELECTION, YEAR_FILTER, TYPO_CONFIRM,
        start_vocabulary, category_selection, CATEGORY_SELECTION,
        download_start, download_url_input, download_quality_selection, ENTER_URL, SELECT_QUALITY,
        start_comment, process_comment, COMMENT, cancel_comment, reply_to_user, REPLY, send_reply_to_user, handle_notation_callback, handle_song_code,
        handle_admin_reply_selection, handle_admin_reply_message, ADMIN_REPLY_MESSAGE, cancel_download,
        bible_game_start, bible_game_language_handler, bible_game_difficulty_handler, bible_game_question_handler, BIBLE_GAME_LANGUAGE, BIBLE_GAME_DIFFICULTY, BIBLE_GAME_QUESTION
    )
except ImportError as e:
    print(f"[DEBUG] ImportError during project imports: {e}")
    raise

import os
from utils.lockfile import acquire_lock, release_lock, LOCK_FILE, STOP_SIGNAL_FILE
import time
from datetime import datetime
import asyncio
import nest_asyncio
nest_asyncio.apply()

# === Load Data and Initialize Global State ===
load_datasets()
config = get_config()
dfH, dfL, dfC, yr23, yr24, yr25, df, dfTH, dfTD = reload_all_datasets()
# Build vocabulary
Vocabulary, Hymn_Vocabulary, Lyric_Vocabulary, Convention_Vocabulary = ChoirVocabulary(df, dfH, dfL, dfC)
# Setup search
setup_search(dfH, dfL, dfC)

# === Telegram Application Setup ===
app = Application.builder().token(config.TOKEN).connect_timeout(30).read_timeout(30).write_timeout(30).build()

# --- Register Modularized Handlers ---
async def shutdown(app):
         """Shutdown the bot gracefully"""
         app.stop()
         
     # Register handlers
conv_handler = ConversationHandler(
         entry_points=[CommandHandler("vocabulary", start_vocabulary)],
         states={
             CATEGORY_SELECTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, category_selection)]
         },
         fallbacks=[CommandHandler("cancel", cancel)]
     )

search_conv_handler = ConversationHandler(
     entry_points=[CommandHandler("search", search_start)],
     states={
         SEARCH_METHOD: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_method_choice)],
         INDEX_CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_index_category)],
         INDEX_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_by_index)],
         NUMBER_CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_number_category)],
         NUMBER_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_by_number)],
     },
     fallbacks=[CommandHandler("cancel", cancel)],
     )
theme_handler = ConversationHandler(
    entry_points=[CommandHandler("theme", theme_type_choice)],
    states={
        THEME_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_theme_type)],
        THEME_SELECTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_theme_selection)],
        TYPO_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_theme_typo_confirm)],
        YEAR_FILTER: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_year_filter)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)
     
# Register the new check conversation handler
check_conv_handler = ConversationHandler(
    entry_points=[CommandHandler('check', check_song_start)],
    states={
        ENTER_SONG: [MessageHandler(filters.TEXT & ~filters.COMMAND, check_song_input)],
    },
    fallbacks=[CommandHandler('cancel', cancel)],
)

# Register the new last conversation handler
last_conv_handler = ConversationHandler(
    entry_points=[CommandHandler('last', last_sung_start)],
    states={
        ENTER_LAST_SONG: [MessageHandler(filters.TEXT & ~filters.COMMAND, last_sung_input)],
    },
    fallbacks=[CommandHandler('cancel', cancel)],
)

comment_handler = ConversationHandler(
    entry_points=[CommandHandler('comment', start_comment)],
    states={
        COMMENT: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, process_comment)
        ]
    },
    fallbacks=[CommandHandler('cancel', cancel_comment)]
)
tune_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("tune", tune_command)],
    states={
        CHOOSE_METHOD: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_method)],
        GET_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_input)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)
     
reply_conv_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(reply_to_user, pattern="^reply_[0-9]+$")],
    states={
        REPLY: [MessageHandler(filters.TEXT & ~filters.COMMAND, send_reply_to_user)]
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    per_message=False,
    per_chat=True,
    per_user=True
)

# Admin reply conversation handler
admin_reply_conv_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(handle_admin_reply_selection, pattern="^reply_(all|user_|more).*")],
    states={
        ADMIN_REPLY_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_admin_reply_message)]
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    per_message=False,
    per_chat=True,
    per_user=True
)

     # Download conversation handler
download_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("download", download_start)],
    states={
        ENTER_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, download_url_input)],
        SELECT_QUALITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, download_quality_selection)],
    },
    fallbacks=[CommandHandler("cancel", cancel_download)],
    per_message=False,
    per_chat=True,
    per_user=True
)
notation_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("notation", notation)],
    states={
        NOTATION_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, notation_code_input)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)

# Register the new date conversation handler
date_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("date", date_start)],
    states={
        ASK_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, date_input)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)

# Register the simplified Bible conversation handler
bible_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("bible", bible_start)],
    states={
        BIBLE_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, bible_input_handler)],
        BIBLE_CONFIRM: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, bible_confirm_handler),
            CallbackQueryHandler(bible_confirm_handler, pattern="^bible_confirm_")
        ],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    per_message=False,
    per_chat=True,
    per_user=True
)

# Register the Bible game conversation handler
bible_game_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("games", bible_game_start)],
    states={
        BIBLE_GAME_LANGUAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, bible_game_language_handler)],
        BIBLE_GAME_DIFFICULTY: [MessageHandler(filters.TEXT & ~filters.COMMAND, bible_game_difficulty_handler)],
        BIBLE_GAME_QUESTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, bible_game_question_handler)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_command))
app.add_handler(bible_conv_handler)
app.add_handler(bible_game_conv_handler)
app.add_handler(date_conv_handler)
app.add_handler(CommandHandler("refresh", refresh_command))
app.add_handler(CommandHandler("reply", admin_reply))
app.add_handler(CallbackQueryHandler(handle_notation_callback, pattern="^notation:"))

app.add_handler(tune_conv_handler)
app.add_handler(last_conv_handler)
app.add_handler(check_conv_handler)
app.add_handler(theme_handler)
app.add_handler(search_conv_handler)
app.add_handler(conv_handler)
app.add_handler(comment_handler)
app.add_handler(reply_conv_handler)
app.add_handler(admin_reply_conv_handler)
app.add_handler(download_conv_handler)
app.add_handler(notation_conv_handler)
app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^[HhLlCc\s-]*\d+$"), handle_song_code))

# Register the callback handler for 'Show all dates' button in /last
app.add_handler(CallbackQueryHandler(last_show_all_dates_callback, pattern="^showalldates:"))

# Add error handler
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a telegram message to notify the developer."""
    bot_logger.error(f"Exception while handling an update: {context.error}")

    # Try to send a user-friendly message if possible
    if update and hasattr(update, 'effective_message') and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "⚠️ Sorry, something went wrong. Please try again later."
            )
        except Exception as e:
            bot_logger.error(f"Failed to send error message to user: {e}")

app.add_error_handler(error_handler)

bot_should_run = True

async def main():
    print("About to call app.run_polling() [async]")
    try:
        await app.run_polling(
            poll_interval=1.0,
            timeout=10,
            bootstrap_retries=5,
            read_timeout=30,
            write_timeout=30,
            connect_timeout=30,
            pool_timeout=30
        )
    except Exception as e:
        bot_logger.error(f"Error in main polling loop: {e}")
        raise
    print("Returned from app.run_polling() [async]")

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
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            # If there's already a running loop, schedule main() as a task
            import threading
            # Only create a task if we're in the main thread of the event loop
            if threading.current_thread() is threading.main_thread():
                loop.create_task(main())
            else:
                # In a background thread, use run_until_complete
                fut = asyncio.run_coroutine_threadsafe(main(), loop)
                fut.result()  # Wait for completion
        else:
            asyncio.run(main())
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

if __name__ == "__main__":
    run_bot()
