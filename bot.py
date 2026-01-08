# Debugging: Check if python-telegram-bot is installed and print confirmation
try:
    import telegram
    print("python-telegram-bot version:", getattr(telegram, '__version__', 'unknown'))
    from telegram.ext import Application, CommandHandler, ConversationHandler, MessageHandler, filters, CallbackQueryHandler
except ImportError as e:
    print(f"[DEBUG] ImportError: {e}")
    raise

try:
    from config import get_config
    from data.datasets import reload_all_datasets, get_all_data, Tune_finder_of_known_songs, Tunenofinder, load_datasets
    from data.vocabulary import ChoirVocabulary
    from utils.search import setup_search
    from telegram_handlers.handlers import (
        start, help_command, refresh_command, cancel, dns_test_command,
        check_song_start, last_sung_start, check_song_input, ENTER_SONG,
        last_sung_input, ENTER_LAST_SONG,
        date_start, date_input, ASK_DATE, last_show_all_dates_callback,
        bible_start, bible_input_handler, bible_confirm_handler, BIBLE_INPUT, BIBLE_CONFIRM,
        admin_list_commands, admin_save_database, admin_list_users,
        admin_view_authorized_users, admin_add_authorized_user, admin_remove_authorized_user,
        admin_reply_start, admin_reply_select_user, admin_reply_send_message, REPLY_SELECT_USER, REPLY_ENTER_MESSAGE, admin_reply_legacy,
        admin_disable_feature, admin_enable_feature, admin_feature_status,
        admin_restrict_access, admin_unrestrict_access, admin_debug_features, admin_add_missing_features, admin_restore_all_features,
        admin_check_ai_model, admin_switch_ai_model, admin_test_ai_model,
        ai_message_handler
    )
    from telegram_handlers.conversations import (
        SEARCH_METHOD, INDEX_CATEGORY, INDEX_TEXT, NUMBER_CATEGORY, NUMBER_INPUT,
        search_start, search_method_choice, search_index_category, search_by_index, search_number_category, search_by_number,
        tune_command, choose_method, get_input, CHOOSE_METHOD, GET_INPUT,
        notation, notation_code_input, NOTATION_TYPE,
        theme_type_choice, handle_theme_type, handle_theme_selection, handle_year_filter, handle_theme_typo_confirm, THEME_TYPE, THEME_SELECTION, YEAR_FILTER, TYPO_CONFIRM,
        start_vocabulary, category_selection, CATEGORY_SELECTION,
        download_start, download_url_input, download_playlist_choice, download_quality_selection, ENTER_URL, PLAYLIST_CHOICE, SELECT_QUALITY,
        start_comment, process_comment, COMMENT, cancel_comment, reply_to_user, REPLY, send_reply_to_user, handle_notation_callback, handle_song_code,
        bible_game_start, bible_game_language_handler, bible_game_difficulty_handler, bible_game_question_handler, BIBLE_GAME_LANGUAGE, BIBLE_GAME_DIFFICULTY, BIBLE_GAME_QUESTION,
        initialize_theme_components,
        organist_roster_start, organist_selection, cancel_organist, ORGANIST_SELECTION,
        update_sunday_songs,
        update_date_songs,
        assign_songs_start, assign_song_selected, assign_organist_selected, assign_continue_or_done, cancel_assign_songs, ASSIGN_SONG_SELECT, ASSIGN_ORGANIST_SELECT,
        unused_songs_start, unused_duration_selected, unused_category_selected, cancel_unused_songs, UNUSED_DURATION_SELECT, UNUSED_CATEGORY_SELECT
    )
    from telegram_handlers.preferences import (
        setting_start, setting_menu_handler, bible_language_handler, game_language_handler,
        search_limit_handler, download_preference_handler, download_quality_handler, tune_display_handler, cancel_settings,
        SETTING_MENU, BIBLE_LANGUAGE_CHOICE, GAME_LANGUAGE_CHOICE, SEARCH_LIMIT_INPUT, DOWNLOAD_PREFERENCE_CHOICE, DOWNLOAD_QUALITY_CHOICE, TUNE_DISPLAY_CHOICE
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
app = Application.builder().token(config.TOKEN).build()

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
    entry_points=[CallbackQueryHandler(reply_to_user, pattern="^reply_")],
    states={
        REPLY: [MessageHandler(filters.TEXT & ~filters.COMMAND, send_reply_to_user)]
    },
    fallbacks=[CommandHandler("cancel", cancel)]
)

# Enhanced admin reply conversation handler
admin_reply_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("reply", admin_reply_start)],
    states={
        REPLY_SELECT_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_reply_select_user)],
        REPLY_ENTER_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_reply_send_message)],
    },
    fallbacks=[CommandHandler("cancel", cancel)]
)

     # Download conversation handler
download_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("download", download_start)],
    states={
        ENTER_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, download_url_input)],
        PLAYLIST_CHOICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, download_playlist_choice)],
        SELECT_QUALITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, download_quality_selection)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
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

# Register the settings conversation handler
settings_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("setting", setting_start)],
    states={
        SETTING_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, setting_menu_handler)],
        BIBLE_LANGUAGE_CHOICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, bible_language_handler)],
        GAME_LANGUAGE_CHOICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, game_language_handler)],
        SEARCH_LIMIT_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_limit_handler)],
        DOWNLOAD_PREFERENCE_CHOICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, download_preference_handler)],
        DOWNLOAD_QUALITY_CHOICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, download_quality_handler)],
        TUNE_DISPLAY_CHOICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, tune_display_handler)],
    },
    fallbacks=[CommandHandler("cancel", cancel_settings)],
)

# Register the organist roster conversation handler
organist_roster_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("organist", organist_roster_start)],
    states={
        ORGANIST_SELECTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, organist_selection)],
    },
    fallbacks=[CommandHandler("cancel", cancel_organist)],
)

# Register the assign songs conversation handler
assign_songs_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("assignsongs", assign_songs_start)],
    states={
        ASSIGN_SONG_SELECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, assign_song_selected)],
        ASSIGN_ORGANIST_SELECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, assign_organist_selected)],
    },
    fallbacks=[CommandHandler("cancel", cancel_assign_songs)],
)

# Register the unused songs conversation handler
unused_songs_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("unused", unused_songs_start)],
    states={
        UNUSED_DURATION_SELECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, unused_duration_selected)],
        UNUSED_CATEGORY_SELECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, unused_category_selected)],
    },
    fallbacks=[CommandHandler("cancel", cancel_unused_songs)],
)

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_command))
app.add_handler(bible_conv_handler)
app.add_handler(bible_game_conv_handler)
app.add_handler(settings_conv_handler)
app.add_handler(date_conv_handler)
app.add_handler(CommandHandler("refresh", refresh_command))
app.add_handler(CommandHandler("dnstest", dns_test_command))
app.add_handler(admin_reply_conv_handler)
app.add_handler(CommandHandler("reply_legacy", admin_reply_legacy))
# User database admin commands
app.add_handler(CommandHandler("admin_save_db", admin_save_database))

# Authorized users management commands
app.add_handler(CommandHandler("users", admin_list_users))
app.add_handler(CommandHandler("view_authorized_users", admin_view_authorized_users))
app.add_handler(CommandHandler("add_authorized_user", admin_add_authorized_user))
app.add_handler(CommandHandler("remove_authorized_user", admin_remove_authorized_user))
app.add_handler(CommandHandler("list", admin_list_commands))

# Feature control admin commands
app.add_handler(CommandHandler("disable", admin_disable_feature))
app.add_handler(CommandHandler("enable", admin_enable_feature))
app.add_handler(CommandHandler("feature_status", admin_feature_status))

# Access restriction admin commands
app.add_handler(CommandHandler("restrict_access", admin_restrict_access))
app.add_handler(CommandHandler("unrestrict_access", admin_unrestrict_access))

# Debug admin commands
app.add_handler(CommandHandler("debug_features", admin_debug_features))
app.add_handler(CommandHandler("add_missing_features", admin_add_missing_features))
app.add_handler(CommandHandler("restore_all_features", admin_restore_all_features))

# AI model status command
app.add_handler(CommandHandler("model", admin_check_ai_model))
app.add_handler(CommandHandler("switchmodel", admin_switch_ai_model))
app.add_handler(CommandHandler("testmodel", admin_test_ai_model))
app.add_handler(CallbackQueryHandler(handle_notation_callback, pattern="^notation:"))

app.add_handler(tune_conv_handler)
app.add_handler(last_conv_handler)
app.add_handler(check_conv_handler)
app.add_handler(theme_handler)
app.add_handler(search_conv_handler)
app.add_handler(conv_handler)
app.add_handler(comment_handler)
app.add_handler(reply_conv_handler)
app.add_handler(download_conv_handler)
app.add_handler(notation_conv_handler)
app.add_handler(organist_roster_conv_handler)
app.add_handler(assign_songs_conv_handler)
app.add_handler(unused_songs_conv_handler)
app.add_handler(CommandHandler("updatesunday", update_sunday_songs))
app.add_handler(CommandHandler("updatedate", update_date_songs))
app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^[HhLlCc\s-]*\d+$"), handle_song_code))

# AI Message Handler - Must be LAST to catch all unhandled text messages
# This allows AI to interpret natural language queries
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ai_message_handler))

# Register the callback handler for 'Show all dates' button in /last
app.add_handler(CallbackQueryHandler(last_show_all_dates_callback, pattern="^showalldates:"))

# Register enhanced search notation callback handlers
from utils.enhanced_search import handle_find_notation_callback, handle_notation_confirmation, handle_tune_confirmation, handle_tune_wrong, handle_back_to_tune, handle_provide_page_number
app.add_handler(CallbackQueryHandler(handle_find_notation_callback, pattern="^find_notation:"))
app.add_handler(CallbackQueryHandler(handle_notation_confirmation, pattern="^notation_confirm:"))
app.add_handler(CallbackQueryHandler(handle_notation_confirmation, pattern="^notation_reject:"))
app.add_handler(CallbackQueryHandler(handle_tune_confirmation, pattern="^confirm:"))
app.add_handler(CallbackQueryHandler(handle_tune_wrong, pattern="^wrong:"))
app.add_handler(CallbackQueryHandler(handle_provide_page_number, pattern="^provide_page:"))
app.add_handler(CallbackQueryHandler(handle_back_to_tune, pattern="^back_to_tune$"))

bot_should_run = True

async def main():
    print("About to call app.run_polling() [async]")
    await app.run_polling()
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

    # Initialize heavy theme components during startup
    print("🚀 Initializing theme components...")
    initialize_theme_components()
    
    # Initialize AI assistant
    print("🤖 Initializing AI assistant (Gemini)...")
    try:
        from utils.ai_assistant import initialize_gemini
        if initialize_gemini():
            print("✅ AI assistant ready")
        else:
            print("⚠️ AI assistant disabled (no API key or error)")
    except Exception as e:
        print(f"⚠️ Could not initialize AI: {str(e)[:100]}")
    
    # Load organist roster data at startup
    print("📋 Loading organist roster data...")
    try:
        from data.organist_roster import load_organist_roster_data
        roster_df = load_organist_roster_data()
        if roster_df is not None:
            print(f"✅ Organist roster loaded ({len(roster_df)} entries)")
        else:
            print("⚠️ Could not load organist roster data")
    except Exception as e:
        print(f"⚠️ Error loading organist roster: {str(e)[:100]}")
    
    # Auto-update Sunday songs on bot startup
    print("📅 Auto-updating Songs for Sunday...")
    try:
        from data.organist_roster import update_songs_for_sunday
        success, message, date_used = update_songs_for_sunday()
        if success:
            print(f"✅ {message}")
        else:
            print(f"⚠️ Sunday update: {message}")
    except Exception as e:
        print(f"⚠️ Could not auto-update Sunday songs: {str(e)[:100]}")

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
