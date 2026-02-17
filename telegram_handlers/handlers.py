# telegram/handlers.py
# Telegram command/callback handlers

import streamlit as st
from telegram import Update, ReplyKeyboardRemove, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext, ConversationHandler, ContextTypes, CallbackQueryHandler
from config import get_config
from logging_utils import setup_loggers
from data.datasets import load_datasets, yrDataPreprocessing, dfcleaning, standardize_song_columns, get_all_data, Tune_finder_of_known_songs, Datefinder, IndexFinder
from data.drive import upload_log_to_google_doc
from data.vocabulary import standardize_hlc_value, isVocabulary, ChoirVocabulary
from data.udb import track_user_interaction, user_exists, get_user_by_id, save_user_database, track_user_fast, save_if_pending, get_user_bible_language, get_user_show_tunes_in_date
from telegram_handlers.utils import get_wordproject_url_from_input, extract_bible_chapter_text, clean_bible_text
import pandas as pd
from datetime import date, timezone, timedelta
import asyncio
import re

# Add this near the top of the file, with other state constants if present
ENTER_SONG = 0

bot_logger, user_logger = setup_loggers()

# --- Command Handlers ---

authorized_users_str = st.secrets["AUTHORIZED_USERS"]
authorized_users = list(map(int, authorized_users_str.split(','))) if authorized_users_str else []

# Log messages from users
async def log_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.message.text
    user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) sent /start")
    await update.message.reply_text("Message received!")

#Authorization
async def is_authorized(update: Update) -> bool:
   """Check if the user is authorized to interact with the bot."""
   user_id = update.effective_user.id
   # List of authorized user IDs from the environment variable
   authorized_users_str = st.secrets["AUTHORIZED_USERS"]
   
   if authorized_users_str is not None:
       authorized_users = list(map(int, authorized_users_str.split(',')))
   else:
       authorized_users = []
   
   # If the user is not authorized, reply and return False
   if user_id not in authorized_users:
       await update.message.reply_text("🚫 You are not authorized to access this feature of the bot. \n Please contact the bot administrator for more information")
       return False
   
   return True

ADMIN_ID = int(st.secrets["ADMIN_ID"])

#Start
async def start(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) sent /start")

    # === FAST USER DATABASE TRACKING ===
    try:
        # Use fast tracking to avoid delays
        is_new_user, tracking_success = track_user_fast(user)

        if tracking_success:
            if is_new_user:
                user_logger.info(f"Added new user {user.id} to database")
                
                # For new users, immediately save to Database
                try:
                    from data.udb import save_user_database
                    save_success = save_user_database()
                    if save_success:
                        user_logger.info(f"Successfully saved new user {user.id} to Database")
                    else:
                        user_logger.warning(f"Failed to save new user {user.id} to Database")
                except Exception as save_error:
                    user_logger.error(f"Error saving new user {user.id} to Database: {save_error}")

                # Notify admin about new user (async, don't wait)
                asyncio.create_task(context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=(
                        f"👤 <b>New User</b>\n\n"
                        # f"<b>Name:</b> {user.full_name}\n"
                        f"<b>Username:</b> @{user.username if user.username else 'Not set'}\n"
                        # f"<b>User ID:</b> <code>{user.id}</code>\n"
                        f"<b>Status:</b> {'✅ Authorized' if str(user.id) in st.secrets.get('AUTHORIZED_USERS', '').split(',') else '❌ Not Authorized'}"
                    ),
                    parse_mode="HTML"
                ))
            else:
                user_logger.info(f"Updated existing user {user.id} in database")
        else:
            user_logger.error(f"Failed to track user {user.id}")

    except Exception as e:
        user_logger.error(f"Error tracking user {user.id}: {e}")
        # Continue with bot functionality even if database tracking fails

    # Check authorization
    authorized_users_str = st.secrets["AUTHORIZED_USERS"]
    authorized_users = list(map(int, authorized_users_str.split(','))) if authorized_users_str else []

    if user.id not in authorized_users:
        # Notify admin about unauthorized access (only if not already notified above)
        if not is_new_user:  # Only notify if this is an existing user accessing
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=(
                    f"⚠️ <b>Unauthorized user accessed /start</b>\n\n"
                    f"<b>Name:</b> {user.full_name}\n"
                    f"<b>Username:</b> @{user.username}\n"
                    f"<b>User ID:</b> <code>{user.id}</code>"
                ),
                parse_mode="HTML"
            )

    # Proceed with regular welcome message
    welcome_text = (f"Hello {user.full_name if user.full_name else user.username}\n\n"
    "🎵 <b>Welcome to the Choir Bot!</b>\n\n"
    "This bot helps you quickly find details about choir songs!\n"
    "Simply type a song like <b>H-27</b>, <b>L-5</b>, or <b>C-12</b> and get instant info, including the last sung date.\n\n"
    "Use <b>/help</b> to explore all commands."
)

    await update.message.reply_text(welcome_text, parse_mode="HTML")

#Help
async def help_command(update: Update, context: CallbackContext) -> None:
     user = update.effective_user
     user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) asked for /help")

     # Split help into multiple messages to avoid Telegram's 4096 character limit
     help_part1 = (
        "🎵 *Choir Song Bot Help* (Part 1/3)\n\n"
        "Here are the available commands and how to use them:\n\n"
        "• **/start**\n"
        "  - *Description:* Starts the bot and shows the welcome message with basic instructions.\n"
        "  - *Example:* Simply type `/start`.\n\n"
        "• **/check**\n"
        "  - *Description:* Check if a song exists in the vocabulary or not. After typing the command, enter the song in the format H-27 (Hymn), L-14 (Lyric), or C-5 (Convention).\n"
        "  - *Example:* Type `/check`, then enter a song like `H-27`.\n\n"
        "• **/last**\n"
        "  - *Description:* Find out when a song was last sung. After typing the command, enter the song like H-27 (Hymn), L-14 (Lyric), or C-5 (Convention). You'll also have the option to view all the dates it was sung.\n"
        "  - *Example:* Type `/last`, then enter a song like `H-27`.\n\n"
        "• **/search**\n"
        "  - *Description:* Interactive search for songs.\n"
        "  - *Options:*\n"
        "     - _By Index:_ Search by entering a line from a hymn, lyric, or convention.\n"
        "     - _By Number:_ Search by entering an index number.\n"
        "  - *Example:* Type `/search` and follow the prompts.\n\n"
        "• **/tune**\n"
        "  - *Description:* Interactively find tunes by hymn number or tune index.\n"
        "  - *Options:*\n"
        "     - _By Hymn Number:_ Returns the tune(s) for a specific hymn number.\n"
        "     - _By Tune Index:_ Provides the top matching hymns using fuzzy matching on tune names.\n"
        "  - *Example:* Type `/tune` and choose either *Hymn Number* or *Tune Index*, then enter your query (e.g. `Whit` or `29`)."
    )

     help_part2 = (
        "🎵 *Choir Song Bot Help* (Part 2/3)\n\n"
        "• **/notation**\n"
        "  - *Description:* Interactive notation lookup. Start by typing `/notation`, and the bot will ask you for a hymn or lyric number (e.g. `H-86` or `L-222`). You can enter multiple hymn or lyric numbers one after another, and for hymns, select a tune to view the notation. Type `/cancel` to stop.\n"
        "  - *Example:* Type `/notation`, then enter a hymn number like `H-86` or a lyric number like `L-222`, and follow the prompts.\n\n"
        "• **/theme**\n"
        "  - *Description:* Initiates an interactive theme filter. You will be presented with a list of unique themes (collected from all comma-separated entries in the database), and you can select or type a theme to display the hymns related to it.\n"
        "  - *Example:* Type `/theme` and choose from the displayed themes, or type a custom theme like `Additional Hymns`.\n\n"
        "• **/date**\n"
        "  - *Description:* Interactive date lookup. Start by typing `/date`, and the bot will ask you to enter a date (DD/MM/YYYY, DD/MM, or DD). You can enter multiple dates one after another to see the songs sung on those dates, until you type `/cancel` to stop.\n"
        "  - *Example:* Type `/date`, then enter a date like `05/04/2024`, and keep entering dates as needed.\n\n"
        "• **/midi**\n"
        "  - *Description:* Convert MIDI files to Synthesia-style piano videos with falling notes animation. Send a MIDI file (.mid or .midi) and receive a beautiful visualization video with audio.\n"
        "  - *Features:* Automatic pitch detection, 3D keyboard animation, color-coded notes, generates video with synchronized audio\n"
        "  - *Example:* Type `/midi` for instructions, then upload a MIDI file to convert it.\n\n"
        "• **/bible**\n"
        "  - *Description:* Interactive Bible passage lookup. Get Bible text directly in the chat with support for multiple languages. Malayalam is used by default.\n"
        "  - *Options:*\n"
        "     - _Direct:_ Type `/bible Gen 10` or `/bible John 3:16 english`\n"
        "     - _Interactive:_ Type `/bible` and follow prompts for book, chapter, and language\n"
        "  - *Supported Languages:* Malayalam (default), English, Hindi, Tamil, Telugu, and many more\n"
        "  - *Example:* Type `/bible` then enter `Gen 3:3` or `John 3:16 english`"
    )

     help_part3 = (
        "🎵 *Choir Song Bot Help* (Part 3/3)\n\n"
        "• **/games**\n"
        "  - *Description:* Play an interactive Bible verse guessing game! Test your knowledge by identifying Bible references from verses. Choose from Easy, Medium, or Hard difficulty levels.\n"
        "  - *Features:* Two languages (English & Malayalam), score tracking, separate leaderboards by difficulty, real-time verse fetching\n"
        "  - *Example:* Type `/games` and follow the prompts to select language and difficulty.\n\n"
        "• **/rooster**\n"
        "  - *Description:* View organist assignments for songs. See which songs are assigned to each organist or view unassigned songs.\n"
        "  - *Example:* Type `/rooster`, select an organist from the list, or choose 'Unassigned Songs' to see songs without an organist.\n\n"
        "• **/updatesunday**\n"
        "  - *Description:* Update the 'Songs for Sunday' sheet with songs from the next available date in the database.\n"
        "  - *Example:* Type `/updatesunday` to automatically populate the sheet with songs from the next scheduled date.\n\n"
        "• **/updatedate**\n"
        "  - *Description:* Update the 'Songs for Sunday' sheet with songs from a specific date or nearest available date.\n"
        "  - *Example:* Type `/updatedate 25/12/2025` or `/updatedate today` to populate the sheet with songs for that date.\n\n"
        "• **/assignsongs**\n"
        "  - *Description:* Assign Sunday songs to organists. Shows songs from 'Songs for Sunday' sheet as buttons. Select a song, then choose an organist to assign it to.\n"
        "  - *Example:* Type `/assignsongs`, select a song like 'H-44', then choose an organist from the list.\n\n"
        "• **/unused**\n"
        "  - *Description:* Find songs that haven't been sung in a specific time period. Filter by hymns, lyrics, or conventions, and choose durations like 3 months, 6 months, this year, or 1 year.\n"
        "  - *Example:* Type `/unused`, select a duration like '3 Months', then choose a category like 'Hymns'.\n\n"
        "• **/upload**\n"
        "  - *Description:* Upload and contribute sheet music files to the collection. Supports PDF, images (JPG, PNG), DOC, and DOCX formats.\n"
        "  - *Example:* Type `/upload`, send your file, provide a filename and description when prompted.\n\n"
        "• **/vocabulary**\n"
        "  - *Description:* Starts the vocabulary export conversation.\n"
        "  - *Example:* Type `/vocabulary` and follow the instructions.\n\n"
        "• **/download**\n"
        "  - *Description:* Download audio from YouTube, or Spotify links. The bot will extract the audio and send it to you as an MP3 file.\n"
        "  - *Supported platforms:* YouTube, Spotify\n"
        "  - *Example:* Type `/download`, then paste a YouTube or Spotify link, and select your preferred audio quality.\n\n"
        "• **/comment**\n"
        "  - *Description:* Allows you to submit comments, recommendations, or feedback directly to the bot administrator.\n"
        "  - *Example:* Type `/comment Your message here` and the bot will forward it to the administrator for review.\n\n"
        "• **/setting**\n"
        "  - *Description:* Manage your personal settings including default Bible language, game language, and search results limit.\n"
        "  - *Example:* Type `/setting` to access your settings menu.\n\n"
        "• **/syncstatus** _(Admin Only)_\n"
        "  - *Description:* Check the status of automatic dataset synchronization. Shows when files were last synced from Google Drive.\n"
        "  - *Note:* The bot now automatically detects and syncs changes from Drive!\n"
        "  - *Example:* Type `/syncstatus` to see sync status.\n\n"
        "• **/syncinfo** _(Admin Only)_\n"
        "  - *Description:* Detailed sync system information including detection mode (instant/polling), API usage statistics, and performance metrics.\n"
        "  - *Example:* Type `/syncinfo` for comprehensive sync analytics.\n\n"
        "• **/forcesync** _(Admin Only)_\n"
        "  - *Description:* Manually trigger a dataset sync from Google Drive.\n"
        "  - *Example:* Type `/forcesync` to immediately reload all datasets.\n\n"
        "• **/cancel**\n"
        "  - *Description:* Cancels the current operation.\n"
        "  - *Example:* If you are in a conversation, type `/cancel` to stop it.\n\n"
        "🔄 *Auto-Sync:* The bot automatically detects changes to Excel/Sheets on Drive and updates data within 2 minutes - no manual refresh needed!\n\n"
        "If you need further assistance, feel free to ask!"
    )

     # Send the help messages in sequence
     await update.message.reply_text(help_part1, parse_mode="Markdown")
     await update.message.reply_text(help_part2, parse_mode="Markdown")
     await update.message.reply_text(help_part3, parse_mode="Markdown")

#Refresh
 
async def refresh_command(update: Update, context: CallbackContext) -> None:
    # Move imports here to avoid circular import
    import telegram_handlers.conversations as conversations
    from telegram_handlers.conversations import fetch_lyrics_file_map, LYRICS_FOLDER_URL
    from data.udb import save_if_pending, load_user_database

    user = update.effective_user
    config = get_config()

    # Check if refresh feature is enabled and user has access
    try:
        from data.feature_control import can_user_access_feature

        can_access, error_message = can_user_access_feature('refresh', user.id)
        if not can_access:
            await update.message.reply_text(
                error_message,
                parse_mode="Markdown"
            )
            user_logger.info(f"Refresh access blocked for {user.full_name} ({user.id}) - {error_message[:50]}...")
            return
    except Exception as feature_check_error:
        bot_logger.error(f"Error checking refresh feature access: {feature_check_error}")
        # Fall back to admin-only check if feature check fails
        admin_id = config.ADMIN_ID
        if user.id != admin_id:
            await update.message.reply_text(
                "🚫 **Access Denied**\n\n"
                "The `/refresh` command is restricted to administrators only.\n\n"
                "This command reloads all bot data and should only be used by admins.",
                parse_mode="Markdown"
            )
            user_logger.warning(f"Unauthorized /refresh attempt by {user.full_name} (@{user.username}, ID: {user.id})")
            return

    user_logger.info(f"User {user.full_name} (@{user.username}, ID: {user.id}) used /refresh")

    # Store message IDs to delete later
    progress_messages = []

    # Starting message
    msg1 = await update.message.reply_text("🔄 Starting refresh process...")
    progress_messages.append(msg1.message_id)

    try:
        # Save any pending user database changes before refresh
        msg2 = await update.message.reply_text("💾 Saving pending database changes...")
        progress_messages.append(msg2.message_id)
        save_success = save_if_pending()
        if save_success:
            user_logger.info("User database changes saved during refresh")

        # Reload datasets
        msg3 = await update.message.reply_text("📊 Reloading datasets...")
        progress_messages.append(msg3.message_id)
        dfH, dfL, dfC, year_data, df, dfTH, dfTD = load_datasets()
        yrDataPreprocessing()
        dfcleaning()
        standardize_song_columns()  # Now modifies global df in-place

        # Refresh lyrics_file_map
        msg4 = await update.message.reply_text("🎵 Refreshing lyrics file map...")
        progress_messages.append(msg4.message_id)
        conversations.lyrics_file_map = fetch_lyrics_file_map(LYRICS_FOLDER_URL)

        # Reload user database to get latest changes from Google Drive
        msg5 = await update.message.reply_text("👥 Reloading database...")
        progress_messages.append(msg5.message_id)
        global user_db
        from data.udb import user_db
        user_db = None  # Clear cache
        load_user_database()  # Reload from Google Drive

        # Clear theme caches to ensure fresh data
        msg6 = await update.message.reply_text("🎯 Refreshing theme components...")
        progress_messages.append(msg6.message_id)
        conversations._vocabulary_cache = None  # Clear vocabulary cache
        conversations._theme_embeddings.clear()  # Clear theme embeddings
        conversations._theme_texts.clear()  # Clear theme texts
        # Re-initialize theme components with fresh data
        conversations.initialize_theme_components()
        
        # Reload organist roster data
        msg6a = await update.message.reply_text("📋 Reloading organist roster...")
        progress_messages.append(msg6a.message_id)
        from data.organist_roster import reload_organist_roster
        roster_reloaded = reload_organist_roster()
        if roster_reloaded:
            user_logger.info("Organist roster reloaded successfully")
        else:
            user_logger.warning("Could not reload organist roster")

        # Upload logs
        msg7 = await update.message.reply_text("📝 .......")
        progress_messages.append(msg7.message_id)
        upload_log_to_google_doc(config.BFILE_ID, "bot_log.txt")
        upload_log_to_google_doc(config.UFILE_ID, "user_log.txt")

        # Send final success message
        await update.message.reply_text("✅ All components refreshed successfully!")

        # Delete all progress messages
        for msg_id in progress_messages:
            try:
                await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=msg_id)
            except Exception as delete_error:
                # Ignore deletion errors (message might already be deleted or too old)
                user_logger.warning(f"Could not delete progress message {msg_id}: {delete_error}")

    except Exception as e:
        # Send error message
        await update.message.reply_text(f"❌ Error during refresh: {e}")
        user_logger.error(f"Refresh command error: {e}")

        # Still try to clean up progress messages on error
        for msg_id in progress_messages:
            try:
                await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=msg_id)
            except Exception as delete_error:
                user_logger.warning(f"Could not delete progress message {msg_id}: {delete_error}")

# Auto-Sync Status Command (Admin Only)
async def sync_status_command(update: Update, context: CallbackContext) -> None:
    """Check the status of the automatic sync system"""
    user = update.effective_user
    config = get_config()
    
    # Check if user is admin
    if user.id != config.ADMIN_ID:
        await update.message.reply_text(
            "🚫 **Access Denied**\n\n"
            "The `/syncstatus` command is restricted to administrators only.",
            parse_mode="Markdown"
        )
        return
    
    user_logger.info(f"Admin {user.full_name} checked sync status")
    
    try:
        from data.sync_manager import get_sync_status
        from datetime import datetime
        
        status = get_sync_status()
        
        # Determine mode
        mode = status.get('mode', 'polling')
        if mode == 'hybrid':
            mode_emoji = "⚡"
            mode_text = f"{mode_emoji} Hybrid Mode (Webhooks + Polling)"
        else:
            mode_emoji = "🔄"
            mode_text = f"{mode_emoji} Polling Mode"
        
        # Format the status message
        running_status = "🟢 Running" if status['running'] else "🔴 Stopped"
        monitored_count = status['monitored_files']
        
        status_text = (
            f"📊 **Auto-Sync Status**\n\n"
            f"**Status:** {running_status}\n"
            f"**Mode:** {mode_text}\n"
            f"**Monitored Files:** {monitored_count}\n"
        )
        
        # Show webhook info if in hybrid mode
        if mode == 'hybrid':
            webhook_count = status.get('active_webhooks', 0)
            status_text += f"**Active Webhooks:** {webhook_count} (instant detection)\n"
            status_text += f"**Polling Fallback:** Every {status.get('polling_interval', 'N/A')}s\n"
        else:
            status_text += f"**Check Interval:** Every {status.get('polling_interval', 'N/A')}s\n"
        
        status_text += "\n"
        
        # Show last sync times if available
        if status['last_sync_times']:
            status_text += "**Last Syncs:**\n"
            for file_name, sync_time in status['last_sync_times'].items():
                try:
                    sync_dt = datetime.fromisoformat(sync_time)
                    time_str = sync_dt.strftime("%Y-%m-%d %H:%M:%S")
                except:
                    time_str = sync_time
                status_text += f"  • {file_name}: {time_str}\n"
        else:
            status_text += "_No syncs have occurred yet_\n"
        
        # Show which files are currently syncing
        syncing = [f for f, is_syncing in status['sync_in_progress'].items() if is_syncing]
        if syncing:
            status_text += f"\n⏳ **Currently Syncing:** {', '.join(syncing)}\n"
        
        await update.message.reply_text(status_text, parse_mode="Markdown")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error getting sync status: {e}")
        user_logger.error(f"Sync status command error: {e}")


async def force_sync_command(update: Update, context: CallbackContext) -> None:
    """Manually trigger a dataset sync"""
    user = update.effective_user
    config = get_config()
    
    # Check if user is admin
    if user.id != config.ADMIN_ID:
        await update.message.reply_text(
            "🚫 **Access Denied**\n\n"
            "The `/forcesync` command is restricted to administrators only.",
            parse_mode="Markdown"
        )
        return
    
    user_logger.info(f"Admin {user.full_name} triggered manual sync")
    
    try:
        from data.sync_manager import force_manual_sync
        
        msg = await update.message.reply_text("🔄 Triggering manual sync of all datasets...")
        
        force_manual_sync()
        
        await msg.edit_text(
            "✅ **Manual Sync Triggered**\n\n"
            "The datasets are being reloaded in the background.\n"
            "Use `/syncstatus` to check progress.",
            parse_mode="Markdown"
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error triggering sync: {e}")
        user_logger.error(f"Force sync command error: {e}")


async def sync_info_command(update: Update, context: CallbackContext) -> None:
    """Show detailed sync system information including mode, API usage, and statistics"""
    user = update.effective_user
    config = get_config()
    
    # Check if user is admin
    if user.id != config.ADMIN_ID:
        await update.message.reply_text(
            "🚫 **Access Denied**\n\n"
            "The `/syncinfo` command is restricted to administrators only.",
            parse_mode="Markdown"
        )
        return
    
    user_logger.info(f"Admin {user.full_name} requested detailed sync info")
    
    try:
        from data.sync_manager import get_sync_status
        from datetime import datetime
        
        status = get_sync_status()
        
        # Determine mode and create status header
        mode = status.get('mode', 'polling')
        monitored = status['monitored_files']
        interval = status.get('polling_interval', 120)
        
        if mode == 'hybrid':
            mode_icon = "⚡"
            mode_name = "Hybrid Mode"
            mode_desc = "Webhooks (instant) + Polling (fallback)"
            detection_time = "< 1 second (webhook) or < 10s (polling)"
        else:
            mode_icon = "🔄"
            mode_name = "Polling Mode"
            mode_desc = "Periodic checking only"
            detection_time = f"< {interval} seconds"
        
        # Calculate API usage
        checks_per_day = (24 * 60 * 60) // interval
        calls_per_day = checks_per_day * monitored
        google_daily_limit = 1_000_000_000
        percentage = (calls_per_day / google_daily_limit) * 100
        
        # Build comprehensive info message
        info_text = (
            f"{mode_icon} **Sync System Information**\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"**📡 Detection Mode**\n"
            f"• Mode: {mode_name}\n"
            f"• Description: {mode_desc}\n"
            f"• Detection Speed: {detection_time}\n\n"
        )
        
        # Webhook information (if hybrid mode)
        if mode == 'hybrid':
            webhook_count = status.get('active_webhooks', 0)
            webhook_files = status.get('webhook_files', [])
            info_text += (
                f"**🔔 Webhook Status**\n"
                f"• Active Webhooks: {webhook_count}/{monitored}\n"
                f"• Status: {'✅ Operational' if webhook_count > 0 else '⚠️ Degraded'}\n"
                f"• Renewal: Every 24 hours (automatic)\n\n"
            )
            
            # Last webhook events
            last_events = status.get('last_webhook_events', {})
            if last_events:
                info_text += f"**📥 Recent Webhook Events**\n"
                for file_id, timestamp in list(last_events.items())[:3]:
                    try:
                        dt = datetime.fromisoformat(timestamp)
                        # Convert to IST (UTC+5:30)
                        ist = timezone(timedelta(hours=5, minutes=30))
                        dt_ist = dt.astimezone(ist)
                        time_str = dt_ist.strftime("%H:%M:%S")
                        info_text += f"• {file_id[:8]}... at {time_str}\n"
                    except:
                        pass
                info_text += "\n"
        
        # Polling information
        info_text += (
            f"**🔄 Polling Status**\n"
            f"• Interval: Every {interval} seconds\n"
            f"• Files Monitored: {monitored}\n"
            f"• Checks Per Hour: {checks_per_day // 24:,}\n"
            f"• Role: {'Fallback safety net' if mode == 'hybrid' else 'Primary detection'}\n\n"
        )
        
        # API Usage Statistics
        info_text += (
            f"**📊 API Usage (24 Hours)**\n"
            f"• API Calls: {calls_per_day:,}/day\n"
            f"• Google Limit: {google_daily_limit:,}/day\n"
            f"• Usage: {percentage:.6f}%\n"
            f"• Status: {'🟢 Excellent' if percentage < 0.01 else '🟡 Good' if percentage < 1 else '🟠 High'}\n"
            f"• Headroom: {((google_daily_limit - calls_per_day) / google_daily_limit * 100):.4f}%\n\n"
        )
        
        # Cost analysis
        bots_before_limit = google_daily_limit // calls_per_day
        years_sustainable = google_daily_limit / calls_per_day / 365
        
        info_text += (
            f"**💰 Cost & Sustainability**\n"
            f"• Cost: $0 (free tier)\n"
            f"• Bots Sustainable: {bots_before_limit:,}\n"
            f"• Years at Current Rate: {years_sustainable:.0f}\n\n"
        )
        
        # Last sync times
        if status['last_sync_times']:
            info_text += f"**🕐 Last Syncs (IST)**\n"
            for file_name, sync_time in list(status['last_sync_times'].items())[:5]:
                try:
                    sync_dt = datetime.fromisoformat(sync_time)
                    # Convert to IST (UTC+5:30)
                    ist = timezone(timedelta(hours=5, minutes=30))
                    sync_dt_ist = sync_dt.astimezone(ist)
                    time_str = sync_dt_ist.strftime("%Y-%m-%d %H:%M:%S")
                    info_text += f"• {file_name}: {time_str}\n"
                except:
                    info_text += f"• {file_name}: {sync_time}\n"
            info_text += "\n"
        
        # Performance summary
        info_text += (
            f"**⚡ Performance**\n"
            f"• Memory: ~1MB (cache files)\n"
            f"• CPU: Negligible (~0%)\n"
            f"• Network: ~{monitored * 5}KB per check\n\n"
        )
        
        # Quick recommendations
        info_text += f"**💡 Quick Actions**\n"
        if mode == 'polling' and interval > 10:
            info_text += f"• `/forcesync` - Manual sync\n"
            info_text += f"• Set `AUTO_SYNC_INTERVAL=10` for faster detection\n"
        elif mode == 'polling':
            info_text += f"• `/forcesync` - Manual sync\n"
            info_text += f"• Configure `WEBHOOK_URL` for instant detection\n"
        else:
            info_text += f"• `/forcesync` - Force immediate sync\n"
            info_text += f"• System operating optimally\n"
        
        info_text += f"\n━━━━━━━━━━━━━━━━━━━━━━"
        
        await update.message.reply_text(info_text, parse_mode="Markdown")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error getting sync info: {e}")
        user_logger.error(f"Sync info command error: {e}")


# DNS Testing Command (Admin Only)
async def dns_test_command(update: Update, context: CallbackContext) -> None:
    """Test DNS resolution in the current environment (Admin only)"""
    user = update.effective_user
    config = get_config()

    # Check if user is admin
    admin_id = config.ADMIN_ID
    if user.id != admin_id:
        await update.message.reply_text(
            "🚫 **Access Denied**\n\n"
            "The `/dnstest` command is restricted to administrators only.",
            parse_mode="Markdown"
        )
        user_logger.warning(f"Unauthorized /dnstest attempt by {user.full_name} (@{user.username}, ID: {user.id})")
        return

    user_logger.info(f"Admin {user.full_name} (@{user.username}, ID: {user.id}) used /dnstest")

    # Send initial message
    test_msg = await update.message.reply_text("🧪 **DNS Testing Started**\n\nRunning DNS resolution tests...", parse_mode="Markdown")

    try:
        # Try to import and run the DNS test
        try:
            import sys
            from pathlib import Path

            # Add the project root to Python path to ensure imports work
            project_root = Path(__file__).parent.parent
            if str(project_root) not in sys.path:
                sys.path.insert(0, str(project_root))

            from cloud_dns_test import sync_test_cloud_dns
            results = sync_test_cloud_dns()

        except ImportError as import_error:
            # If import fails, run inline DNS test
            user_logger.warning(f"Could not import cloud_dns_test: {import_error}")
            await test_msg.edit_text("🔧 Running inline DNS test...", parse_mode="Markdown")

            import socket
            import time

            results = {}

            # Test basic connectivity
            try:
                socket.setdefaulttimeout(5)
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                result = sock.connect_ex(('8.8.8.8', 53))
                sock.close()
                results['basic_connectivity'] = result == 0
            except Exception:
                results['basic_connectivity'] = False

            # Test YouTube DNS resolution
            youtube_domains = ['www.youtube.com', 'youtu.be']
            dns_results = []

            for domain in youtube_domains:
                try:
                    socket.setdefaulttimeout(10)
                    ip = socket.gethostbyname(domain)
                    dns_results.append(True)
                except Exception:
                    dns_results.append(False)

            results['dns_resolution'] = any(dns_results)
            results['dns_success_rate'] = sum(dns_results) / len(dns_results) * 100

        # Format results
        result_text = "🧪 **DNS Test Results**\n\n"
        result_text += f"**Environment:** Streamlit Cloud\n"
        result_text += f"**Basic Connectivity:** {'✅ PASS' if results.get('basic_connectivity', False) else '❌ FAIL'}\n"
        result_text += f"**DNS Resolution:** {'✅ PASS' if results.get('dns_resolution', False) else '❌ FAIL'}"

        if 'dns_success_rate' in results:
            result_text += f" ({results['dns_success_rate']:.0f}%)"

        if 'direct_ip' in results:
            result_text += f"\n**Direct IP Access:** {'✅ PASS' if results['direct_ip'] else '❌ FAIL'}"
            if 'ip_success_rate' in results:
                result_text += f" ({results['ip_success_rate']:.0f}%)"

        # Overall assessment
        if results.get('dns_resolution', False):
            result_text += "\n\n🎉 **DNS resolution is working!** Downloads should be possible."
        else:
            result_text += "\n\n❌ **DNS resolution is failing.** This explains why downloads are not working."
            result_text += "\n\n**Recommendation:** Consider alternative hosting or proxy solutions."

        await test_msg.edit_text(result_text, parse_mode="Markdown")

    except Exception as e:
        error_text = f"❌ **DNS Test Failed**\n\nError running DNS test: {str(e)[:200]}{'...' if len(str(e)) > 200 else ''}"
        await test_msg.edit_text(error_text, parse_mode="Markdown")
        user_logger.error(f"DNS test error: {e}")

# Enhanced Admin Reply System

# Conversation states for reply
REPLY_SELECT_USER, REPLY_ENTER_MESSAGE = range(2000, 2002)

async def admin_reply_start(update: Update, context: CallbackContext) -> int:
    """Start the enhanced reply conversation"""
    user = update.effective_user
    config = get_config()
    admin_id = config.ADMIN_ID

    if user.id != admin_id:
        await update.message.reply_text("❌ You are not authorized to use this command.")
        return ConversationHandler.END

    try:
        # Get all users from database
        from data.udb import get_user_database
        user_db = get_user_database()

        if user_db is None or user_db.empty:
            await update.message.reply_text("❌ No users found in database.")
            return ConversationHandler.END

        # Create user list with names
        user_options = []
        user_data = {}

        # Add "All Users" option first
        user_options.append("📢 All Users")

        # Add individual users
        for _, row in user_db.iterrows():
            user_id = row['user_id']
            name = row.get('name', 'Unknown')
            username = row.get('username', '')

            # Create display name
            if name and name.strip():
                display_name = name.strip()
            elif username and username.strip():
                display_name = f"@{username.strip()}"
            else:
                display_name = f"User {user_id}"

            user_options.append(display_name)
            user_data[display_name] = {
                'user_id': user_id,
                'name': name,
                'username': username
            }

        # Store user data in context
        context.user_data['reply_user_data'] = user_data

        # Create keyboard with user options (2 per row)
        keyboard = []
        for i in range(0, len(user_options), 2):
            row = user_options[i:i+2]
            keyboard.append(row)

        # Add cancel button
        keyboard.append(["❌ Cancel"])

        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)

        await update.message.reply_text(
            "👥 **Select a user to reply to:**\n\n"
            "• Choose '📢 All Users' to broadcast to everyone\n"
            "• Choose a specific user to send a private reply\n"
            "• Choose '❌ Cancel' to abort",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )

        user_logger.info(f"Admin {user.id} started enhanced reply process")
        return REPLY_SELECT_USER

    except Exception as e:
        await update.message.reply_text(f"❌ Error loading users: {str(e)}")
        user_logger.error(f"Error in admin_reply_start: {e}")
        return ConversationHandler.END

async def admin_reply_select_user(update: Update, context: CallbackContext) -> int:
    """Handle user selection for reply"""
    selected_option = update.message.text.strip()

    if selected_option == "❌ Cancel":
        await update.message.reply_text(
            "❌ Reply cancelled.",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END

    if selected_option == "📢 All Users":
        context.user_data['reply_target'] = 'all'
        await update.message.reply_text(
            "📢 **Broadcasting to all users**\n\n"
            "Please enter your message to send to all bot users:",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode="Markdown"
        )
    else:
        # Individual user selected
        user_data = context.user_data.get('reply_user_data', {})

        if selected_option not in user_data:
            await update.message.reply_text(
                "❌ Invalid selection. Please choose from the list.",
                reply_markup=ReplyKeyboardRemove()
            )
            return ConversationHandler.END

        selected_user = user_data[selected_option]
        context.user_data['reply_target'] = selected_user

        await update.message.reply_text(
            f"💬 **Replying to: {selected_option}**\n\n"
            # f"User ID: `{selected_user['user_id']}`\n\n"
            "Please enter your message:",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode="Markdown"
        )

    return REPLY_ENTER_MESSAGE

async def admin_reply_send_message(update: Update, context: CallbackContext) -> int:
    """Send the reply message"""
    message_text = update.message.text.strip()

    if not message_text:
        await update.message.reply_text("❌ Message cannot be empty. Please enter your message:")
        return REPLY_ENTER_MESSAGE

    reply_target = context.user_data.get('reply_target')

    if not reply_target:
        await update.message.reply_text("❌ Error: No target selected.")
        return ConversationHandler.END

    try:
        if reply_target == 'all':
            # Broadcast to all users
            from data.udb import get_user_database
            user_db = get_user_database()

            sent_count = 0
            failed_count = 0

            await update.message.reply_text("📢 Broadcasting message to all users...")

            for _, row in user_db.iterrows():
                target_user_id = row['user_id']
                try:
                    await context.bot.send_message(
                        chat_id=target_user_id,
                        text=f"💬 **Admin:**\n\n{message_text}",
                        parse_mode="Markdown"
                    )
                    sent_count += 1
                except Exception as send_error:
                    failed_count += 1
                    user_logger.warning(f"Failed to send broadcast to user {target_user_id}: {send_error}")

            await update.message.reply_text(
                f"✅ **Broadcast completed!**\n\n"
                f"📤 Sent to: {sent_count} users\n"
                f"❌ Failed: {failed_count} users",
                parse_mode="Markdown"
            )

            user_logger.info(f"Admin broadcast: {sent_count} sent, {failed_count} failed")

        else:
            # Send to individual user
            target_user_id = reply_target['user_id']
            target_name = reply_target.get('name', f"User {target_user_id}")

            await context.bot.send_message(
                chat_id=target_user_id,
                text=f"💬 **Admin:**\n\n{message_text}",
                parse_mode="Markdown"
            )

            await update.message.reply_text(
                f"✅ **Message sent successfully!**\n\n"
                f"👤 To: {target_name}\n"
                f"📤 Message: {message_text[:50]}{'...' if len(message_text) > 50 else ''}",
                parse_mode="Markdown"
            )

            user_logger.info(f"Admin reply sent to user {target_user_id}")

    except Exception as e:
        await update.message.reply_text(f"❌ Error sending message: {str(e)}")
        user_logger.error(f"Error in admin_reply_send_message: {e}")

    # Clean up context data
    context.user_data.pop('reply_target', None)
    context.user_data.pop('reply_user_data', None)

    return ConversationHandler.END

# Legacy admin reply for backward compatibility
async def admin_reply_legacy(update: Update, context: CallbackContext) -> None:
    """Legacy admin reply command (kept for backward compatibility)"""
    user = update.effective_user
    config = get_config()
    admin_id = config.ADMIN_ID
    if user.id != admin_id:
        await update.message.reply_text("❌ You are not authorized to use this command.")
        return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Usage: /reply <user_id> <your message>")
        return
    target_user_id = int(args[0])
    reply_message = " ".join(args[1:])
    await context.bot.send_message(
        chat_id=target_user_id,
        text=f"💬 Admin's reply:\n\n{reply_message}",
        parse_mode="HTML"
    )
    await update.message.reply_text(f"✅ Reply sent to user {target_user_id}.")

#Cancel

async def cancel(update: Update, context: CallbackContext) -> int:
    user = update.effective_user
    user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) sent /cancel")
    await update.message.reply_text("Operation canceled.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# Fix state definition for date conversation
ASK_DATE = 1000

# Conversation handler for /date
async def date_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    # Check if date feature is enabled and user has access
    try:
        from data.feature_control import can_user_access_feature

        can_access, error_message = can_user_access_feature('date', user.id)
        if not can_access:
            await update.message.reply_text(
                error_message,
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardRemove()
            )
            user_logger.info(f"Date access blocked for {user.first_name} ({user.id}) - {error_message[:50]}...")
            return ConversationHandler.END
    except Exception as feature_check_error:
        user_logger.error(f"Error checking date feature access: {feature_check_error}")
        # Continue with normal flow if feature check fails

    await update.message.reply_text(
        "📅 Please enter a date (DD/MM/YYYY, DD/MM, or DD):",
        reply_markup=ReplyKeyboardRemove()
    )
    return ASK_DATE

async def date_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    # Check if AI provided input
    if 'ai_date_input' in context.user_data:
        input_date = context.user_data.pop('ai_date_input').strip()
    else:
        input_date = update.message.text.strip()
    
    result = get_songs_by_date(input_date)

    if isinstance(result, dict):
        # Check user's preference for showing tunes
        show_tunes = get_user_show_tunes_in_date(user.id)

        # Split into two messages as requested
        # First message: Just the status message without the colon
        first_message = result['message'].rstrip(':')
        await update.message.reply_text(first_message, parse_mode='Markdown')

        # Second message: Date and songs list
        # Filter out any empty or invalid songs
        valid_songs = [s for s in result["songs"] if s and str(s).strip()]

        if show_tunes:
            # Show tunes for hymns, filter out entries with empty IndexFinder results
            songs_with_indices = [(s, IndexFinder(s)) for s in valid_songs]
            songs_list = [
                f"{i + 1}. {s} - {idx}{get_tune_info(s)}" 
                for i, (s, idx) in enumerate(songs_with_indices) if idx
            ]
            songs_text = "\n".join(songs_list)
        else:
            # Don't show tunes, filter out entries with empty IndexFinder results
            songs_with_indices = [(s, IndexFinder(s)) for s in valid_songs]
            songs_list = [
                f"{i + 1}. {s} - {idx}" 
                for i, (s, idx) in enumerate(songs_with_indices) if idx
            ]
            songs_text = "\n".join(songs_list)

        second_message = f"{result['date']}:\n\n{songs_text}"
        await update.message.reply_text(second_message, parse_mode='Markdown')
    else:
        # For error messages, send as single message
        await update.message.reply_text(result, parse_mode='Markdown')

    await update.message.reply_text(
        "You can enter another date, or type /cancel to stop.",
        reply_markup=ReplyKeyboardRemove()
    )
    return ASK_DATE

# Conversation handler for /check
async def check_song_start(update: Update, context: CallbackContext) -> int:
    user = update.effective_user

    # Check if check feature is enabled and user has access
    try:
        from data.feature_control import can_user_access_feature

        can_access, error_message = can_user_access_feature('check', user.id)
        if not can_access:
            await update.message.reply_text(
                error_message,
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardRemove()
            )
            user_logger.info(f"Check access blocked for {user.first_name} ({user.id}) - {error_message[:50]}...")
            return ConversationHandler.END
    except Exception as feature_check_error:
        user_logger.error(f"Error checking check feature access: {feature_check_error}")
        # Continue with normal flow if feature check fails

    await update.message.reply_text(
        "🔎 Please enter a song code (e.g. H-27, L-14, or C-5):",
        reply_markup=ReplyKeyboardRemove()
    )
    return ENTER_SONG

async def check_song_input(update: Update, context: CallbackContext) -> int:
    # Check if AI provided input
    if 'ai_song_input' in context.user_data:
        user_input = context.user_data.pop('ai_song_input').strip().upper()
    else:
        user_input = update.message.text.strip().upper()
    
    user_input = standardize_hlc_value(user_input)

    # Basic format check
    if not user_input or '-' not in user_input:
        await update.message.reply_text(
            "❌ Invalid format. Please use format like H-27.",
            reply_markup=ReplyKeyboardRemove()
        )
        await update.message.reply_text("Enter another song code, or type /cancel to stop.")
        return ENTER_SONG

    song_type, _, song_number = user_input.partition('-')

    if song_type not in ['H', 'L', 'C'] or not song_number.isdigit():
        await update.message.reply_text(
            "❌ Invalid input. Use H-, L-, or C- followed by a number (e.g. H-27).",
            reply_markup=ReplyKeyboardRemove()
        )
        await update.message.reply_text("Enter another song code, or type /cancel to stop.")
        return ENTER_SONG

    # Prepare arguments for isVocabulary
    from data.vocabulary import ChoirVocabulary
    from data.datasets import df, dfH, dfL, dfC, dfTH, Tune_finder_of_known_songs
    Vocabulary = ChoirVocabulary(df, dfH, dfL, dfC)[0]
    result = isVocabulary(user_input, Vocabulary, dfH, dfTH, Tune_finder_of_known_songs)

    # Fetch song name
    song_name = None
    if song_type == 'H':
        row = dfH[dfH['Hymn no'] == int(song_number)]
        if not row.empty:
            song_name = row.iloc[0].get('Hymn Name')
    elif song_type == 'L':
        row = dfL[dfL['Lyric no'] == int(song_number)]
        if not row.empty:
            song_name = row.iloc[0].get('Lyric Name')
    elif song_type == 'C':
        row = dfC[dfC['Convention no'] == int(song_number)]
        if not row.empty:
            song_name = row.iloc[0].get('Convention Name')

    # Fetch song name using IndexFinder (Malayalam name/index)
    from data.datasets import IndexFinder
    song_index = IndexFinder(user_input)
    song_display = f"{user_input}: {song_index}" if song_index and song_index != "Invalid Number" else user_input
    if result.startswith(user_input):
        result = result.replace(user_input, song_display, 1)

    await update.message.reply_text(
        result,
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=ReplyKeyboardRemove()
    )
    await update.message.reply_text("Enter another song code, or type /cancel to stop.")
    return ENTER_SONG

# /last

# States
ENTER_LAST_SONG, ASK_SHOW_ALL = range(2)
#Download command states
ENTER_URL, SELECT_QUALITY = range(2, 4)
 
 # /last entry point
async def last_sung_start(update: Update, context: CallbackContext) -> int:
    user = update.effective_user

    # Check if last feature is enabled and user has access
    try:
        from data.feature_control import can_user_access_feature

        can_access, error_message = can_user_access_feature('last', user.id)
        if not can_access:
            await update.message.reply_text(
                error_message,
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardRemove()
            )
            user_logger.info(f"Last access blocked for {user.first_name} ({user.id}) - {error_message[:50]}...")
            return ConversationHandler.END
    except Exception as feature_check_error:
        user_logger.error(f"Error checking last feature access: {feature_check_error}")
        # Continue with normal flow if feature check fails

    await update.message.reply_text(
        "🎼 Please enter the song (e.g. H-27, L-14, C-5):",
        reply_markup=ReplyKeyboardRemove()
    )
    return ENTER_LAST_SONG
 
 # Handle song input
async def last_sung_input(update: Update, context: CallbackContext) -> int:
    # Check if AI provided input
    if 'ai_song_input' in context.user_data:
        user_input = context.user_data.pop('ai_song_input').strip().upper()
    else:
        user_input = update.message.text.strip().upper()
    
    user_input = standardize_hlc_value(user_input)

    if not user_input or '-' not in user_input:
        await update.message.reply_text("❌ Invalid format. Please use format like H-27.")
        await update.message.reply_text("Enter another song code, or type /cancel to stop.")
        return ENTER_LAST_SONG

    song_type, _, song_number = user_input.partition('-')

    if song_type not in ['H', 'L', 'C'] or not song_number.isdigit():
        await update.message.reply_text("❌ Invalid code. Use H-, L-, or C- followed by a number (e.g. H-27).")
        await update.message.reply_text("Enter another song code, or type /cancel to stop.")
        return ENTER_LAST_SONG

    full_song = f"{song_type}-{song_number}"
    context.user_data["last_category"] = song_type
    context.user_data["last_song"] = full_song

    # Get last sung date
    result = Datefinder(full_song, song_type, first=True)
    keyboard = [[InlineKeyboardButton("Show all dates", callback_data=f"showalldates:{full_song}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(result, reply_markup=reply_markup)
    await update.message.reply_text("Enter another song code, or type /cancel to stop.")
    return ENTER_LAST_SONG

async def last_show_all_dates_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    if not query.data.startswith("showalldates:"):
        return
    song_code = query.data.replace("showalldates:", "")
    song_type, _, _ = song_code.partition('-')
    result = Datefinder(song_code, song_type, first=False)
    await query.edit_message_text(result)
    # Optionally, prompt again for another song
    await context.bot.send_message(chat_id=query.message.chat_id, text="Enter another song code, or type /cancel to stop.")

# TODO: Add more command handlers (check, last, search, tune, notation, theme, vocabulary, download, comment, refresh, reply, cancel, etc.) 

def get_tune_info(song_code):
    """
    Get tune information for a song code.
    Returns tune string for hymns, empty string for lyrics/conventions.
    """
    try:
        from data.datasets import Tune_finder_of_known_songs

        # Handle empty or None input
        if not song_code:
            return ""

        song_code = str(song_code).strip().upper()

        # Check if it's a valid hymn code
        if song_code.startswith('H') and len(song_code) > 1:
            tune = Tune_finder_of_known_songs(song_code)
            if tune and tune != "Invalid Number" and str(tune).strip():
                return f" - {tune}"

        return ""  # No tune info for lyrics/conventions or invalid hymns
    except Exception:
        return ""

def get_songs_by_date(input_date):
    """
    Accepts:
    - 'DD/MM/YYYY', 'DD-MM-YYYY'
    - 'DD/MM/YY', 'DD-MM-YY'
    - 'DD/MM', 'DD-MM'
    - 'DD' (uses current month and year)

    If no songs found on the given date, returns next available date with songs.
    """
    from data.datasets import get_all_data
    data = get_all_data()
    df = data["df"]
    today = date.today()
    current_year = today.year
    current_month = today.month

    # Normalize input: replace '-' with '/' for easier parsing
    if isinstance(input_date, str):
        input_date = input_date.replace('-', '/').strip()
        parts = input_date.split('/')

        try:
            if len(parts) == 3:
                input_date = pd.to_datetime(input_date, dayfirst=True).date()
            elif len(parts) == 2:
                day, month = map(int, parts)
                input_date = date(current_year, month, day)
            elif len(parts) == 1:
                day = int(parts[0])
                input_date = date(current_year, current_month, day)
            else:
                return "Invalid date format. Use DD, DD/MM, DD/MM/YY, or DD/MM/YYYY."
        except Exception as e:
            return f"Date parsing error: {e}"

    # Ensure 'Date' column is datetime.date
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce').dt.date
    df.dropna(subset=['Date'], inplace=True)

    # Sort dates
    available_dates = sorted(df['Date'].unique())

    # Find songs on the input date
    matching_rows = df[df['Date'] == input_date]

    if matching_rows.empty:
        # Get the next available date with songs
        next_dates = [d for d in available_dates if d > input_date]
        if not next_dates:
            return f"No songs found on {input_date.strftime('%d/%m/%Y')} or any later date."
        next_date = next_dates[0]
        matching_rows = df[df['Date'] == next_date]
        message = f"No songs found on {input_date.strftime('%d/%m/%Y')}. Showing songs from next available date: {next_date.strftime('%d/%m/%Y')}"
    else:
        next_date = input_date
        message = f"Songs sung on {next_date.strftime('%d/%m/%Y')}"

    # Get song columns
    song_columns = [col for col in df.columns if col != 'Date']
    songs = []

    for _, row in matching_rows.iterrows():
        for col in song_columns:
            song = row[col]
            if pd.notna(song) and str(song).strip() != '':
                songs.append(song.strip())

    # If date exists but has no songs, find next date with actual songs
    if not songs:
        next_dates = [d for d in available_dates if d > input_date]
        if not next_dates:
            return f"No songs found on {input_date.strftime('%d/%m/%Y')} or any later date."
        
        # Find the next date that actually has songs
        for next_date in next_dates:
            matching_rows = df[df['Date'] == next_date]
            temp_songs = []
            for _, row in matching_rows.iterrows():
                for col in song_columns:
                    song = row[col]
                    if pd.notna(song) and str(song).strip() != '':
                        temp_songs.append(song.strip())
            
            if temp_songs:  # Found a date with actual songs
                songs = temp_songs
                message = f"No songs found on {input_date.strftime('%d/%m/%Y')}. Showing songs from next available date: {next_date.strftime('%d/%m/%Y')}"
                break
        
        # If still no songs found after checking all future dates
        if not songs:
            return f"No songs found on {input_date.strftime('%d/%m/%Y')} or any later date."

    return {
        "date": next_date.strftime('%d/%m/%Y'),
        "message": message,
        "songs": songs
    } 

async def handle_song_code(update: Update, context: CallbackContext) -> None:
    user_input = update.message.text.strip().upper()
    user_input = standardize_hlc_value(user_input)

    # Basic format check
    if not user_input or '-' not in user_input:
        await update.message.reply_text(
            "❌ Invalid format. Please use format like H-27.",
            reply_markup=ReplyKeyboardRemove()
        )
        return

    song_type, _, song_number = user_input.partition('-')

    if song_type not in ['H', 'L', 'C'] or not song_number.isdigit():
        await update.message.reply_text(
            "❌ Invalid input. Use H-, L-, or C- followed by a number (e.g. H-27).",
            reply_markup=ReplyKeyboardRemove()
        )
        return

    from data.vocabulary import ChoirVocabulary
    from data.datasets import df, dfH, dfL, dfC, dfTH, Tune_finder_of_known_songs
    Vocabulary = ChoirVocabulary(df, dfH, dfL, dfC)[0]
    result = isVocabulary(user_input, Vocabulary, dfH, dfTH, Tune_finder_of_known_songs)

    # Fetch song name
    song_name = None
    if song_type == 'H':
        row = dfH[dfH['Hymn no'] == int(song_number)]
        if not row.empty:
            song_name = row.iloc[0].get('Hymn Name')
    elif song_type == 'L':
        row = dfL[dfL['Lyric no'] == int(song_number)]
        if not row.empty:
            song_name = row.iloc[0].get('Lyric Name')
    elif song_type == 'C':
        row = dfC[dfC['Convention no'] == int(song_number)]
        if not row.empty:
            song_name = row.iloc[0].get('Convention Name')

    # Fetch song name using IndexFinder (Malayalam name/index)
    from data.datasets import IndexFinder
    song_index = IndexFinder(user_input)
    song_display = f"{user_input}: {song_index}" if song_index and song_index != "Invalid Number" else user_input
    if result.startswith(user_input):
        result = result.replace(user_input, song_display, 1)
    reply_text = result
    await update.message.reply_text(
        reply_text,
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=ReplyKeyboardRemove()
    ) 

# Bible conversation states
BIBLE_INPUT = 2000
BIBLE_CONFIRM = 2001

# Interactive Bible command handler
async def bible_start(update: Update, context: CallbackContext) -> int:
    """Start the interactive Bible command"""
    user = update.effective_user
    user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) started /bible")
    
    # Check if user provided arguments
    args = context.args
    if len(args) >= 1:
        user_input = " ".join(args)
        # --- New: Parse for verse or range ---
        book_chapter_input = user_input
        verse_spec = None
        # Detect verse or range (e.g., Gen 1:1 or Gen 2:4-7)
        m = re.search(r":\s*(\d+)(?:\s*-\s*(\d+))?$", user_input)
        if m:
            verse_spec = (int(m.group(1)), int(m.group(2)) if m.group(2) else int(m.group(1)))
            book_chapter_input = user_input[:m.start()].strip()
        # Default to Malayalam if no language specified
        result = get_wordproject_url_from_input('malayalam', book_chapter_input)
        url, matched_book, formatted_reference, fuzzy_matched = result

        if url.startswith("❌"):
            await update.message.reply_text(url)
        elif fuzzy_matched:
            # Store the data for confirmation
            context.user_data['bible_url'] = url
            context.user_data['bible_reference'] = formatted_reference
            context.user_data['bible_verse_spec'] = verse_spec
            context.user_data['bible_language'] = 'malayalam'
            context.user_data['bible_original_input'] = user_input

            # Create inline keyboard with Yes/No buttons
            keyboard = [
                [
                    InlineKeyboardButton("✅ Yes", callback_data="bible_confirm_yes"),
                    InlineKeyboardButton("❌ No", callback_data="bible_confirm_no")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            confirmation_text = f"🤔 Did you mean *{formatted_reference}*?"
            await update.message.reply_text(confirmation_text, parse_mode="Markdown", reply_markup=reply_markup)
            return BIBLE_CONFIRM
        else:
            raw_text = extract_bible_chapter_text(url)
            if raw_text.startswith("❌"):
                await update.message.reply_text(raw_text)
            else:
                cleaned_text = clean_bible_text(raw_text, 'ml')
                # --- New: Extract verses if verse_spec is set ---
                if verse_spec:
                    verses = extract_verses_from_cleaned_text(cleaned_text, verse_spec[0], verse_spec[1])
                    if not verses:
                        await update.message.reply_text(f"❌ Verse(s) not found in this chapter.\n🔗 [View on WordProject]({url})", parse_mode="Markdown", disable_web_page_preview=True)
                        return ConversationHandler.END
                    cleaned_text = "\n".join(verses)
                # Split long text into multiple messages if needed
                if len(cleaned_text) > 4000:
                    chunks = [cleaned_text[i:i+4000] for i in range(0, len(cleaned_text), 4000)]
                    for i, chunk in enumerate(chunks):
                        if i == 0:
                            header = f"📖 *Bible Passage*\n\n*Reference:* {user_input.title()}\n*Language:* Malayalam (default)\n\n"
                            await update.message.reply_text(header + chunk, parse_mode="Markdown")
                        else:
                            await update.message.reply_text(chunk)
                    link_text = f"🔗 [View on WordProject]({url})"
                    await update.message.reply_text(link_text, parse_mode="Markdown", disable_web_page_preview=True)
                else:
                    response_text = (
                        f"📖 *Bible Passage*\n\n"
                        f"*Reference:* {user_input.title()}\n"
                        f"*Language:* Malayalam (default)\n\n"
                        f"{cleaned_text}\n\n"
                        f"🔗 [View on WordProject]({url})"
                    )
                    await update.message.reply_text(response_text, parse_mode="Markdown", disable_web_page_preview=True)
        return ConversationHandler.END
    
    # Start interactive mode
    welcome_text = (
        "📖 *Bible Command*\n\n"
        "Please enter the book and chapter:\n\n"
        "*Examples:*\n"
        "• `Gen 10`\n"
        "• `Exodus 12`\n"
        "• `John 3`\n"
        "• `യോഹന്നാൻ 3`\n"
        "• `Gen 10 mal` (for Malayalam)\n"
        "• `Exodus 12 english` (for English)\n\n"
        f"*Note:* If no language is specified, your default language ({get_user_bible_language(user.id).title()}) will be used.\n"
        "You can change your default language using /setting."
    )
    
    await update.message.reply_text(welcome_text, parse_mode="Markdown")
    return BIBLE_INPUT

async def bible_input_handler(update: Update, context: CallbackContext) -> int:
    """Handle book, chapter, and optional language input"""
    try:
        user = update.effective_user
        
        # Check if AI provided input
        if 'ai_bible_input' in context.user_data:
            user_input = context.user_data.pop('ai_bible_input').strip()
        else:
            user_input = update.message.text.strip()
        
        parts = user_input.split()
        # Get user's preferred Bible language
        language = get_user_bible_language(user.id)  # Use user's preference
        book_chapter_input = user_input
        language_codes = {
            'mal', 'malayalam', 'eng', 'english', 'hin', 'hindi', 
            'tam', 'tamil', 'tel', 'telugu', 'kan', 'kannada',
            'mar', 'marathi', 'guj', 'gujarati', 'pun', 'punjabi',
            'ben', 'bengali', 'ur', 'urdu', 'es', 'spanish',
            'fr', 'french', 'de', 'german', 'zh', 'chinese',
            'ja', 'japanese', 'ru', 'russian'
        }
        if len(parts) >= 2 and parts[-1].lower() in language_codes:
            language = parts[-1].lower()
            book_chapter_input = ' '.join(parts[:-1])
        # --- New: Parse for verse or range ---
        verse_spec = None
        m = re.search(r":\s*(\d+)(?:\s*-\s*(\d+))?$", book_chapter_input)
        if m:
            verse_spec = (int(m.group(1)), int(m.group(2)) if m.group(2) else int(m.group(1)))
            book_chapter_input = book_chapter_input[:m.start()].strip()
        result = get_wordproject_url_from_input(language, book_chapter_input)
        url, matched_book, formatted_reference, fuzzy_matched = result

        if url.startswith("❌"):
            await update.message.reply_text(url)
        elif fuzzy_matched:
            # Store the data for confirmation
            context.user_data['bible_url'] = url
            context.user_data['bible_reference'] = formatted_reference
            context.user_data['bible_verse_spec'] = verse_spec
            context.user_data['bible_language'] = language
            context.user_data['bible_original_input'] = user_input

            # Create inline keyboard with Yes/No buttons
            keyboard = [
                [
                    InlineKeyboardButton("✅ Yes", callback_data="bible_confirm_yes"),
                    InlineKeyboardButton("❌ No", callback_data="bible_confirm_no")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            confirmation_text = f"🤔 Did you mean *{formatted_reference}*?"
            await update.message.reply_text(confirmation_text, parse_mode="Markdown", reply_markup=reply_markup)
            return BIBLE_CONFIRM
        else:
            raw_text = extract_bible_chapter_text(url)
            if raw_text.startswith("❌"):
                await update.message.reply_text(raw_text)
            else:
                lang_code = 'ml'  # default to Malayalam
                if language in ['english', 'eng']:
                    lang_code = 'kj'
                cleaned_text = clean_bible_text(raw_text, lang_code)
                # --- New: Extract verses if verse_spec is set ---
                if verse_spec:
                    verses = extract_verses_from_cleaned_text(cleaned_text, verse_spec[0], verse_spec[1])
                    if not verses:
                        await update.message.reply_text(f"❌ Verse(s) not found in this chapter.\n🔗 [View on WordProject]({url})", parse_mode="Markdown", disable_web_page_preview=True)
                        next_text = (
                            "📖 *Enter another Bible reference, or type /cancel to stop:*\n\n"
                            "*Examples:*\n"
                            "• `Gen 10`\n"
                            "• `Exodus 12 english`\n"
                            "• `John 3`\n"
                            "• `യോഹന്നാൻ 3`"
                        )
                        await update.message.reply_text(next_text, parse_mode="Markdown")
                        return BIBLE_INPUT
                    cleaned_text = "\n".join(verses)
                if len(cleaned_text) > 4000:
                    chunks = [cleaned_text[i:i+4000] for i in range(0, len(cleaned_text), 4000)]
                    for i, chunk in enumerate(chunks):
                        if i == 0:
                            header = f"📖 *Bible Passage Found!*\n\n*Reference:* {book_chapter_input.title()}\n*Language:* {language.title()}\n\n"
                            await update.message.reply_text(header + chunk, parse_mode="Markdown")
                        else:
                            await update.message.reply_text(chunk)
                    link_text = f"🔗 [View on WordProject]({url})"
                    await update.message.reply_text(link_text, parse_mode="Markdown", disable_web_page_preview=True)
                else:
                    response_text = (
                        f"📖 *Bible Passage Found!*\n\n"
                        f"*Reference:* {book_chapter_input.title()}\n"
                        f"*Language:* {language.title()}\n\n"
                        f"{cleaned_text}\n\n"
                        f"🔗 [View on WordProject]({url})"
                    )
                    await update.message.reply_text(response_text, parse_mode="Markdown", disable_web_page_preview=True)
        next_text = (
            "📖 *Enter another Bible reference, or type /cancel to stop:*\n\n"
            "*Examples:*\n"
            "• `Gen 10`\n"
            "• `Exodus 12 english`\n"
            "• `John 3`\n"
            "• `യോഹന്നാൻ 3`"
        )
        await update.message.reply_text(next_text, parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")
        next_text = (
            "📖 *Enter another Bible reference, or type /cancel to stop:*\n\n"
            "*Examples:*\n"
            "• `Gen 10`\n"
            "• `Exodus 12 english`\n"
            "• `John 3`\n"
            "• `യോഹന്നാൻ 3`"
        )
        await update.message.reply_text(next_text, parse_mode="Markdown")
    return BIBLE_INPUT

async def bible_confirm_handler(update: Update, context: CallbackContext) -> int:
    """Handle confirmation for fuzzy matched Bible references"""
    try:
        # Handle both button callbacks and text input
        if update.callback_query:
            query = update.callback_query
            await query.answer()
            user_response = query.data
        else:
            user_response = update.message.text.strip().lower()

        if user_response == 'bible_confirm_yes' or user_response in ['yes', 'y', 'yeah', 'yep', 'ok', 'okay']:
            # User confirmed, proceed with the Bible passage
            url = context.user_data.get('bible_url')
            formatted_reference = context.user_data.get('bible_reference')
            verse_spec = context.user_data.get('bible_verse_spec')
            language = context.user_data.get('bible_language')
            original_input = context.user_data.get('bible_original_input')

            if not url:
                await update.message.reply_text("❌ Session expired. Please try again.")
                return ConversationHandler.END

            raw_text = extract_bible_chapter_text(url)
            if raw_text.startswith("❌"):
                await update.message.reply_text(raw_text)
            else:
                lang_code = 'ml'  # default to Malayalam
                if language in ['english', 'eng']:
                    lang_code = 'kj'
                cleaned_text = clean_bible_text(raw_text, lang_code)

                # Extract verses if verse_spec is set
                if verse_spec:
                    verses = extract_verses_from_cleaned_text(cleaned_text, verse_spec[0], verse_spec[1])
                    if not verses:
                        await update.message.reply_text(f"❌ Verse(s) not found in this chapter.\n🔗 [View on WordProject]({url})", parse_mode="Markdown", disable_web_page_preview=True)
                        return ConversationHandler.END
                    cleaned_text = "\n".join(verses)

                # Split long text into multiple messages if needed
                if len(cleaned_text) > 4000:
                    chunks = [cleaned_text[i:i+4000] for i in range(0, len(cleaned_text), 4000)]
                    for i, chunk in enumerate(chunks):
                        if i == 0:
                            header = f"📖 *Bible Passage Found!*\n\n*Reference:* {formatted_reference}\n*Language:* {language.title()}\n\n"
                            await update.message.reply_text(header + chunk, parse_mode="Markdown")
                        else:
                            await update.message.reply_text(chunk)
                    link_text = f"🔗 [View on WordProject]({url})"
                    await update.message.reply_text(link_text, parse_mode="Markdown", disable_web_page_preview=True)
                else:
                    response_text = (
                        f"📖 *Bible Passage Found!*\n\n"
                        f"*Reference:* {formatted_reference}\n"
                        f"*Language:* {language.title()}\n\n"
                        f"{cleaned_text}\n\n"
                        f"🔗 [View on WordProject]({url})"
                    )
                    # Send to callback query if it's a button press, otherwise to message
                    if update.callback_query:
                        await update.callback_query.edit_message_text(response_text, parse_mode="Markdown", disable_web_page_preview=True)
                    else:
                        await update.message.reply_text(response_text, parse_mode="Markdown", disable_web_page_preview=True)

            # Continue the conversation instead of ending it
            next_text = (
                "📖 *Enter another Bible reference, or type /cancel to stop:*\n\n"
                "*Examples:*\n"
                "• `Gen 10`\n"
                "• `Exodus 12 english`\n"
                "• `John 3`\n"
                "• `യോഹന്നാൻ 3`"
            )
            if update.callback_query:
                await update.callback_query.message.reply_text(next_text, parse_mode="Markdown")
            else:
                await update.message.reply_text(next_text, parse_mode="Markdown")

            # Clear user data
            context.user_data.clear()
            return BIBLE_INPUT

        elif user_response == 'bible_confirm_no' or user_response in ['no', 'n', 'nope', 'cancel']:
            # User declined
            decline_text = "❌ Could not find the Bible reference you were looking for."

            next_text = (
                "📖 *Enter another Bible reference, or type /cancel to stop:*\n\n"
                "*Examples:*\n"
                "• `Gen 10`\n"
                "• `Exodus 12 english`\n"
                "• `John 3`\n"
                "• `യോഹന്നാൻ 3`"
            )

            if update.callback_query:
                await update.callback_query.edit_message_text(decline_text)
                await update.callback_query.message.reply_text(next_text, parse_mode="Markdown")
            else:
                await update.message.reply_text(decline_text)
                await update.message.reply_text(next_text, parse_mode="Markdown")

            # Clear user data
            context.user_data.clear()
            return BIBLE_INPUT
        else:
            # Invalid response
            invalid_text = "Please click one of the buttons above or type 'yes' to confirm or 'no' to cancel."
            if update.callback_query:
                await update.callback_query.message.reply_text(invalid_text)
            else:
                await update.message.reply_text(invalid_text)
            return BIBLE_CONFIRM

    except Exception as e:
        error_text = f"❌ Error: {str(e)}"
        if update.callback_query:
            await update.callback_query.message.reply_text(error_text)
        else:
            await update.message.reply_text(error_text)
        return BIBLE_INPUT

# --- Helper for extracting verses from cleaned text ---
def extract_verses_from_cleaned_text(cleaned_text, start_verse, end_verse):
    """Extracts verses from cleaned text, even if multiple verses are on the same line."""
    # Use re.findall to match all verse numbers and their text
    # This will match verse numbers followed by text, even if multiple on one line
    # Handles both Malayalam and English
    pattern = re.compile(r'(\d{1,3})\s+([^\d\n]+)')
    matches = pattern.findall(cleaned_text)
    verses = []
    for vnum_str, vtext in matches:
        try:
            vnum = int(vnum_str)
            if start_verse <= vnum <= end_verse:
                verses.append(f"{vnum} {vtext.strip()}")
        except Exception:
            continue
    return verses

# === USER DATABASE ADMIN COMMANDS ===
# admin_users_stats and admin_user_info removed due to Markdown parsing errors
# admin_save_database restored - it was working fine

async def admin_save_database(update: Update, context: CallbackContext) -> None:
    """Admin command to manually save user database to Google Drive"""
    user = update.effective_user

    # Check if user is admin
    if user.id != ADMIN_ID:
        await update.message.reply_text("❌ Admin access required")
        return

    try:
        await update.message.reply_text("💾 Saving user database to Google Drive...")

        # Use save_if_pending for efficiency
        success = save_if_pending()

        if success:
            await update.message.reply_text("✅ User database saved successfully to Google Drive!")
            user_logger.info(f"Admin {user.id} manually saved user database")
        else:
            await update.message.reply_text("❌ Failed to save user database to Google Drive")
            user_logger.error(f"Admin {user.id} failed to save user database")

    except Exception as e:
        await update.message.reply_text(f"❌ Error saving database: {str(e)}")
        user_logger.error(f"Error in admin_save_database: {e}")

# === AUTHORIZED USERS MANAGEMENT ===

async def admin_view_authorized_users(update: Update, context: CallbackContext) -> None:
    """Admin command to view all authorized users"""
    user = update.effective_user

    # Check if user is admin
    if user.id != ADMIN_ID:
        await update.message.reply_text("❌ Admin access required")
        return

    try:
        from data.udb import get_authorized_users

        authorized_users = get_authorized_users()

        if not authorized_users:
            await update.message.reply_text("📋 No Authorized Users Found\n\nThere are currently no authorized users in the database.")
            return

        # Build the authorized users list (without Markdown to avoid parsing errors)
        users_text = f"👥 Authorized Users List\n\n"
        users_text += f"Total Authorized Users: {len(authorized_users)}\n\n"

        for i, auth_user in enumerate(authorized_users, 1):
            user_id = auth_user['user_id']
            username = auth_user.get('username', '')
            name = auth_user.get('name', 'Unknown')
            last_seen = auth_user.get('last_seen', 'Never')
            is_admin = auth_user.get('is_admin', False)

            admin_badge = " 👑" if is_admin else ""
            username_display = f"@{username}" if username else "No username"

            # Escape special characters that might cause parsing issues
            safe_name = str(name).replace('_', ' ').replace('*', ' ').replace('[', '(').replace(']', ')')
            safe_username = str(username_display).replace('_', ' ').replace('*', ' ')

            users_text += f"{i}. {safe_name}{admin_badge}\n"
            users_text += f"   • ID: {user_id}\n"
            users_text += f"   • Username: {safe_username}\n"
            users_text += f"   • Last Seen: {last_seen}\n\n"

        users_text += "Commands:\n"
        users_text += "• /add_authorized_user <user_id> - Add user to authorized list\n"
        users_text += "• /remove_authorized_user <user_id> - Remove user from authorized list"

        await update.message.reply_text(users_text)
        user_logger.info(f"Admin {user.id} viewed authorized users list")

    except Exception as e:
        await update.message.reply_text(f"❌ Error retrieving authorized users: {str(e)}")
        user_logger.error(f"Error in admin_view_authorized_users: {e}")

async def admin_add_authorized_user(update: Update, context: CallbackContext) -> None:
    """Admin command to add a user to the authorized list"""
    global user_logger
    
    user = update.effective_user

    # Check if user is admin
    if user.id != ADMIN_ID:
        await update.message.reply_text("❌ Admin access required")
        return

    # Check if user_id was provided
    if not context.args:
        await update.message.reply_text(
            "❌ User ID required\n\n"
            "Usage: /add_authorized_user <user_id>\n\n"
            "Example: /add_authorized_user 123456789\n\n"
            "How to get User ID:\n"
            "• Forward a message from the user to @userinfobot\n"
            "• Or ask the user to send /start and check the logs\n"
            "• Use /users command to see all users in database"
        )
        return

    try:
        target_user_id = int(context.args[0])

        from data.udb import set_user_authorization, get_user_by_id, is_user_authorized

        # First check if user exists in database
        user_info = get_user_by_id(target_user_id)
        
        if user_info is None:
            await update.message.reply_text(
                f"❌ User Not Found\n\n"
                f"User ID <code>{target_user_id}</code> doesn't exist in the database.\n\n"
                f"<b>Note:</b> Users must interact with the bot at least once (e.g., send /start) "
                f"before they can be authorized.\n\n"
                f"Use /users to see all registered users.",
                parse_mode="HTML"
            )
            return

        # Check if user is already authorized
        if is_user_authorized(target_user_id):
            name = user_info.get('name', 'Unknown')
            username = user_info.get('username', '')
            username_display = f"@{username}" if username else "No username"
            
            await update.message.reply_text(
                f"ℹ️ <b>User Already Authorized</b>\n\n"
                f"<b>User Details:</b>\n"
                f"• Name: {name}\n"
                f"• Username: {username_display}\n"
                f"• ID: <code>{target_user_id}</code>\n\n"
                f"This user is already in the authorized users list.",
                parse_mode="HTML"
            )
            return

        # Add user to authorized list
        success = set_user_authorization(target_user_id, authorized=True)

        if success:
            name = user_info.get('name', 'Unknown')
            username = user_info.get('username', '')
            username_display = f"@{username}" if username else "No username"

            success_text = f"✅ <b>User Authorized Successfully!</b>\n\n"
            success_text += f"<b>User Details:</b>\n"
            success_text += f"• Name: {name}\n"
            success_text += f"• Username: {username_display}\n"
            success_text += f"• ID: <code>{target_user_id}</code>\n\n"
            success_text += f"This user can now access restricted bot features."

            await update.message.reply_text(success_text, parse_mode="HTML")
            user_logger.info(f"Admin {user.id} authorized user {target_user_id}")
        else:
            await update.message.reply_text(
                "❌ <b>Failed to authorize user</b>\n\n"
                "There was an error updating the database. Please check logs.",
                parse_mode="HTML"
            )
            user_logger.error(f"Failed to authorize user {target_user_id} - set_user_authorization returned False")

    except ValueError:
        await update.message.reply_text(
            "❌ <b>Invalid User ID</b>\n\n"
            "Please provide a valid numeric user ID.\n\n"
            "Example: <code>/add_authorized_user 123456789</code>",
            parse_mode="HTML"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error authorizing user: {str(e)}")
        user_logger.error(f"Error in admin_add_authorized_user: {e}", exc_info=True)

        
async def admin_remove_authorized_user(update: Update, context: CallbackContext) -> None:
    """Admin command to remove a user from the authorized list"""
    user = update.effective_user

    # Check if user is admin
    if user.id != ADMIN_ID:
        await update.message.reply_text("❌ Admin access required")
        return

    # Check if user_id was provided
    if not context.args:
        await update.message.reply_text(
            "❌ User ID required\n\n"
            "Usage: /remove_authorized_user <user_id>\n\n"
            "Example: /remove_authorized_user 123456789\n\n"
            "Use /view_authorized_users to see the list of authorized users."
        )
        return

    try:
        target_user_id = int(context.args[0])

        # Prevent admin from removing themselves
        if target_user_id == ADMIN_ID:
            await update.message.reply_text("❌ Cannot Remove Admin\n\nYou cannot remove your own admin authorization.")
            return

        from data.udb import set_user_authorization, get_user_by_id, is_user_authorized

        # Check if user is currently authorized
        if not is_user_authorized(target_user_id):
            await update.message.reply_text(f"ℹ️ User Not Authorized\n\nUser ID {target_user_id} is not in the authorized users list.")
            return

        # Remove user from authorized list
        success = set_user_authorization(target_user_id, authorized=False)

        if success:
            # Get user info if available
            user_info = get_user_by_id(target_user_id)
            if user_info is not None:
                name = user_info.get('name', 'Unknown')
                username = user_info.get('username', '')
                username_display = f"@{username}" if username else "No username"

                # Escape special characters
                safe_name = str(name).replace('_', ' ').replace('*', ' ').replace('[', '(').replace(']', ')')
                safe_username = str(username_display).replace('_', ' ').replace('*', ' ')

                success_text = f"🚫 User Authorization Revoked\n\n"
                success_text += f"User Details:\n"
                success_text += f"• Name: {safe_name}\n"
                success_text += f"• Username: {safe_username}\n"
                success_text += f"• ID: {target_user_id}\n\n"
                success_text += f"This user can no longer access restricted bot features."
            else:
                success_text = f"🚫 User Authorization Revoked\n\n"
                success_text += f"User ID: {target_user_id}\n\n"
                success_text += f"User authorization has been removed."

            await update.message.reply_text(success_text)
            user_logger.info(f"Admin {user.id} removed authorization for user {target_user_id}")
        else:
            await update.message.reply_text("❌ Failed to remove authorization\n\nThere was an error updating the database.")

    except ValueError:
        await update.message.reply_text("❌ Invalid User ID\n\nPlease provide a valid numeric user ID.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error removing authorization: {str(e)}")
        user_logger.error(f"Error in admin_remove_authorized_user: {e}")

async def admin_list_users(update: Update, context: CallbackContext) -> None:
    """Admin command to list all users with their names and IDs"""
    user = update.effective_user

    # Check if user is admin
    if user.id != ADMIN_ID:
        await update.message.reply_text("❌ Admin access required")
        return

    try:
        # Import user database functions
        from data.udb import get_user_database

        # Get user database
        db = get_user_database()

        if db.empty:
            await update.message.reply_text("📝 **No users found in database.**")
            return

        # Sort users by last_seen (most recent first)
        db_sorted = db.sort_values('last_seen', ascending=False, na_position='last')

        # Create user list message
        user_list = "👥 <b>All Users in Database</b>\n\n"
        
        # Add summary
        total_users = len(db)
        authorized_users = len(db[db['is_authorized'] == True])
        admin_users = len(db[db['is_admin'] == True])
        
        user_list += f"📊 <b>Summary:</b>\n"
        user_list += f"• Total Users: {total_users}\n"
        user_list += f"• Authorized: {authorized_users}\n"
        user_list += f"• Admins: {admin_users}\n\n"

        # Add user details (limit to 50 users to avoid message length issues)
        max_users = 50
        users_to_show = db_sorted.head(max_users)
        
        for idx, (_, user_row) in enumerate(users_to_show.iterrows(), 1):
            user_id = user_row['user_id']
            username = user_row.get('username', 'N/A')
            name = user_row.get('name', 'N/A')
            is_authorized = user_row.get('is_authorized', False)
            is_admin = user_row.get('is_admin', False)
            last_seen = user_row.get('last_seen', 'N/A')
            
            # Format username
            if username != 'N/A' and username:
                username_display = f"@{username}"
            else:
                username_display = "No username"
            
            # Format name - escape HTML special characters
            if name != 'N/A' and name:
                name_display = str(name).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            else:
                name_display = "No name"
            
            # Status indicators
            status_icons = ""
            if is_admin:
                status_icons += "👑 "  # Admin
            if is_authorized:
                status_icons += "✅ "  # Authorized
            
            # Format last seen
            if last_seen != 'N/A' and last_seen:
                try:
                    from datetime import datetime
                    last_seen_dt = datetime.fromisoformat(last_seen)
                    last_seen_display = last_seen_dt.strftime('%Y-%m-%d')
                except:
                    last_seen_display = str(last_seen)[:10]  # First 10 chars
            else:
                last_seen_display = "Unknown"
            
            user_list += f"{idx:2d}. {status_icons}<b>{name_display}</b>\n"
            user_list += f"    ID: <code>{user_id}</code> | {username_display}\n"
            user_list += f"    Last seen: {last_seen_display}\n\n"
        
        # Add note if there are more users
        if total_users > max_users:
            user_list += f"... and {total_users - max_users} more users\n\n"
        
        user_list += "<b>Usage:</b>\n"
        user_list += "• Use <code>/add_authorized_user &lt;user_id&gt;</code> to authorize\n"
        user_list += "• Use <code>/remove_authorized_user &lt;user_id&gt;</code> to remove\n"
        user_list += "• Tap on user IDs to copy them"

        # Split message if too long (Telegram limit is 4096 characters)
        if len(user_list) > 4000:
            # Split into chunks
            chunks = []
            current_chunk = "👥 <b>All Users in Database</b>\n\n"
            current_chunk += f"📊 <b>Summary:</b>\n"
            current_chunk += f"• Total Users: {total_users}\n"
            current_chunk += f"• Authorized: {authorized_users}\n"
            current_chunk += f"• Admins: {admin_users}\n\n"
            
            for idx, (_, user_row) in enumerate(users_to_show.iterrows(), 1):
                user_id = user_row['user_id']
                username = user_row.get('username', 'N/A')
                name = user_row.get('name', 'N/A')
                is_authorized = user_row.get('is_authorized', False)
                is_admin = user_row.get('is_admin', False)
                last_seen = user_row.get('last_seen', 'N/A')
                
                # Format user info (same as above)
                if username != 'N/A' and username:
                    username_display = f"@{username}"
                else:
                    username_display = "No username"
                
                if name != 'N/A' and name:
                    name_display = str(name).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                else:
                    name_display = "No name"
                
                status_icons = ""
                if is_admin:
                    status_icons += "👑 "
                if is_authorized:
                    status_icons += "✅ "
                
                if last_seen != 'N/A' and last_seen:
                    try:
                        from datetime import datetime
                        last_seen_dt = datetime.fromisoformat(last_seen)
                        last_seen_display = last_seen_dt.strftime('%Y-%m-%d')
                    except:
                        last_seen_display = str(last_seen)[:10]
                else:
                    last_seen_display = "Unknown"
                
                user_entry = f"{idx:2d}. {status_icons}<b>{name_display}</b>\n"
                user_entry += f"    ID: <code>{user_id}</code> | {username_display}\n"
                user_entry += f"    Last seen: {last_seen_display}\n\n"
                
                # Check if adding this user would exceed limit
                if len(current_chunk + user_entry) > 4000:
                    chunks.append(current_chunk)
                    current_chunk = f"👥 <b>All Users (Part {len(chunks) + 1})</b>\n\n"
                
                current_chunk += user_entry
            
            if current_chunk:
                chunks.append(current_chunk)
            
            # Send each chunk
            for i, chunk in enumerate(chunks):
                if i == len(chunks) - 1:  # Last chunk
                    chunk += "<b>Usage:</b>\n"
                    chunk += "• Use <code>/add_authorized_user &lt;user_id&gt;</code> to authorize\n"
                    chunk += "• Use <code>/remove_authorized_user &lt;user_id&gt;</code> to remove\n"
                    chunk += "• Tap on user IDs to copy them"
                
                try:
                    await update.message.reply_text(chunk, parse_mode="HTML")
                except Exception as parse_error:
                    # Fallback to plain text if HTML parsing fails
                    plain_chunk = chunk.replace('<b>', '').replace('</b>', '').replace('<code>', '').replace('</code>', '').replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
                    await update.message.reply_text(plain_chunk)
        else:
            try:
                await update.message.reply_text(user_list, parse_mode="HTML")
            except Exception as parse_error:
                # Fallback to plain text if HTML parsing fails
                plain_list = user_list.replace('<b>', '').replace('</b>', '').replace('<code>', '').replace('</code>', '').replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
                await update.message.reply_text(plain_list)

        # Log the action
        user_logger.info(f"Admin {user.id} viewed user list ({total_users} users)")

    except Exception as e:
        await update.message.reply_text(f"❌ Error retrieving user list: {str(e)}")
        user_logger.error(f"Error in admin_list_users: {e}")


async def admin_list_commands(update: Update, context: CallbackContext) -> None:
    """Admin command to list all available admin commands"""
    user = update.effective_user

    # Check if user is admin
    if user.id != ADMIN_ID:
        await update.message.reply_text("❌ Admin access required")
        return

    try:
        admin_commands = f"""
🔧 **Admin Commands List**

**System & Sync Management:**
• `/syncstatus` - Check auto-sync status and last sync times
• `/syncinfo` - Detailed sync analytics (mode, API usage, performance)
• `/forcesync` - Manually trigger dataset sync
• `/dnstest` - Test DNS resolution and network connectivity

**User Management:**
• `/admin_save_db` - Manually save user database to Google Drive
• `/users` - View all users with names and IDs
• `/view_authorized_users` - View all authorized users
• `/add_authorized_user <user_id>` - Add user to authorized list
• `/remove_authorized_user <user_id>` - Remove user from authorized list

**Feature Control:**
• `/disable <feature> [reason]` - Disable a bot feature
• `/enable <feature>` - Enable a bot feature
• `/restrict_access <feature> [reason]` - Restrict feature to authorized users only
• `/unrestrict_access <feature>` - Remove access restriction
• `/set_admin_only <feature> [reason]` - Set feature to admin-only access
• `/unset_admin_only <feature>` - Remove admin-only restriction
• `/feature_status` - View all feature statuses
• `/debug_features` - Debug feature loading (troubleshooting)
• `/add_missing_features` - Add missing features to Database
• `/restore_all_features` - Restore all features (fix missing features)

**AI Model Management:**
• `/model` - Check current AI model status (Gemini/Groq)
• `/switchmodel <provider>` - Switch AI provider (gemini/groq/both)
• `/testmodel` - Test AI providers with actual requests (uses quota)

**Notation & Sheet Music Management:**
• `/notation_status <number>` - Check if a specific lyric notation is available
• `/missing_notations` - List all lyrics that need notation uploads
• `/update_notation_status` - Bidirectional sync: scan all files, update Status (adds & removes)
• `/listuploads` - List recently uploaded sheet music files

**Admin Communication:**
• `/reply` - Reply to user comments/feedback (interactive conversation)

**Admin Utilities:**
• `/list` - Show this admin commands list

**User-Facing Commands (Available to All):**

📱 *Navigation & Information:*
• `/start` - Welcome message and user tracking
• `/help` - Show general bot help

🎵 *Music & Songs:*
• `/notation` - Get sheet music notation
• `/tune` - Find tune information
• `/check` - Get song details
• `/last` - Check when songs were last sung
• `/search` - Search songs by various criteria
• `/vocabulary` - Access choir vocabulary
• `/theme` - Search by themes
• `/rooster` - View organist assignments for songs

🎹 *MIDI & Audio:*
• `/midi` - Convert MIDI files to Synthesia-style piano videos
• `/download` - Download audio from YouTube/Spotify links

📖 *Bible & Spiritual:*
• `/bible` - Bible verse lookup
• `/games` - Bible quiz games

📅 *Schedule & Planning:*
• `/date` - Check songs sung on specific dates
• `/refresh` - Reload all datasets from Google Drive
• `/updatesunday` - Update Sunday Songs sheet with next available date (admin only)
• `/updatedate` - Update Sunday Songs sheet with custom date (admin only)
• `/assignsongs` - Assign Sunday songs to organists (admin only)
• `/unused` - Find songs not sung in a specific period (admin only)

📤 *File & Data Management:*
• `/upload` - Upload sheet music files to the collection

⚙️ *User Settings:*
• `/setting` - Manage personal settings (language, preferences, etc)

💬 *Feedback & Communication:*
• `/comment` - Send feedback/comments to admin

**Usage Examples:**
• `/notation_status 6`
• `/missing_notations`
• `/disable bible Maintenance work`
• `/reply Thanks for your feedback!`
• `/switchmodel groq`
"""
        await update.message.reply_text(admin_commands, parse_mode="Markdown")
        user_logger.info(f"Admin {user.id} viewed admin commands list")
    
    except Exception as e:
        await update.message.reply_text(f"❌ Error retrieving admin commands: {str(e)}")
        user_logger.error(f"Error in admin_list_commands: {e}")

async def admin_check_ai_model(update: Update, context: CallbackContext) -> None:
    """Admin command to check which AI model is currently active"""
    user = update.effective_user
    
    # Check if user is admin
    config = get_config()
    admin_id = config.ADMIN_ID
    if user.id != admin_id:
        await update.message.reply_text("❌ Admin access required")
        return
    
    try:
        from utils import ai_assistant
        
        response_lines = ["🤖 *AI Model Status*\n"]
        
        # Check Gemini
        if ai_assistant._gemini_model is not None:
            client, model_name = ai_assistant._gemini_model
            response_lines.append(f"✅ *Gemini:* Active")
            response_lines.append(f"   Model: `{model_name}`")
        else:
            response_lines.append(f"❌ *Gemini:* Not initialized")
        
        response_lines.append("")
        
        # Check Groq
        if ai_assistant._groq_client is not None:
            response_lines.append(f"✅ *Groq:* Active")
            response_lines.append(f"   Model: `llama-3.3-70b-versatile`")
        else:
            response_lines.append(f"⚠️ *Groq:* Not initialized")
        
        response_lines.append("")
        response_lines.append("*Current Behavior:*")
        
        # Show behavior based on preferred provider
        preferred = getattr(ai_assistant, '_preferred_provider', 'gemini')
        
        if preferred == 'gemini':
            if ai_assistant._gemini_model is not None:
                response_lines.append("• Using *Gemini* as primary")
                if ai_assistant._groq_client is not None:
                    response_lines.append("• Will fallback to Groq if Gemini fails")
                else:
                    response_lines.append("• No fallback available")
            else:
                if ai_assistant._groq_client is not None:
                    response_lines.append("• Gemini unavailable, using Groq")
                else:
                    response_lines.append("• ⚠️ No AI providers available")
        
        elif preferred == 'groq':
            if ai_assistant._groq_client is not None:
                response_lines.append("• Using *Groq* as primary")
                if ai_assistant._gemini_model is not None:
                    response_lines.append("• Will fallback to Gemini if Groq fails")
                else:
                    response_lines.append("• No fallback available")
            else:
                if ai_assistant._gemini_model is not None:
                    response_lines.append("• Groq unavailable, using Gemini")
                else:
                    response_lines.append("• ⚠️ No AI providers available")
        
        elif preferred == 'both':
            if ai_assistant._gemini_model is not None and ai_assistant._groq_client is not None:
                response_lines.append("• Using *both* providers (Gemini primary)")
                response_lines.append("• Will fallback to Groq if Gemini fails")
            elif ai_assistant._gemini_model is not None:
                response_lines.append("• Only Gemini available")
            elif ai_assistant._groq_client is not None:
                response_lines.append("• Only Groq available")
            else:
                response_lines.append("• ⚠️ No AI providers available")
        
        response = "\n".join(response_lines)
        await update.message.reply_text(response, parse_mode="Markdown")
        user_logger.info(f"Admin {user.id} checked AI model status")
    
    except Exception as e:
        await update.message.reply_text(f"❌ Error checking AI model: {str(e)}")
        user_logger.error(f"Error in admin_check_ai_model: {e}")

async def admin_switch_ai_model(update: Update, context: CallbackContext) -> None:
    """Admin command to switch between AI providers"""
    user = update.effective_user
    
    # Check if user is admin
    config = get_config()
    admin_id = config.ADMIN_ID
    if user.id != admin_id:
        await update.message.reply_text("❌ Admin access required")
        return
    
    # Check if a provider was specified
    args = context.args
    
    if not args:
        # Show options
        from utils import ai_assistant
        
        status_lines = ["🔄 *Switch AI Model*\n"]
        status_lines.append("Current status:")
        
        if ai_assistant._gemini_model is not None:
            status_lines.append("• Gemini: ✅ Active")
        else:
            status_lines.append("• Gemini: ❌ Inactive")
        
        if ai_assistant._groq_client is not None:
            status_lines.append("• Groq: ✅ Active")
        else:
            status_lines.append("• Groq: ❌ Inactive")
        
        status_lines.append("\n*Usage:*")
        status_lines.append("• `/switchmodel gemini` - Switch to Gemini")
        status_lines.append("• `/switchmodel groq` - Switch to Groq")
        status_lines.append("• `/switchmodel both` - Initialize both")
        
        await update.message.reply_text("\n".join(status_lines), parse_mode="Markdown")
        return
    
    provider = args[0].lower()
    
    try:
        from utils import ai_assistant
        
        if provider == "gemini":
            # Force reinitialize Gemini (no test to save quota)
            ai_assistant._gemini_model = None
            ai_assistant._preferred_provider = "gemini"
            success = ai_assistant.initialize_gemini()
            
            if success:
                await update.message.reply_text(
                    "✅ *Switched to Gemini*\n\n"
                    "AI requests will now use Gemini as primary provider.",
                    parse_mode="Markdown"
                )
                user_logger.info(f"Admin {user.id} switched to Gemini")
            else:
                await update.message.reply_text(
                    "❌ *Failed to initialize Gemini*\n\n"
                    "Check if:\n"
                    "• GEMINI_API_KEY is valid\n"
                    "• Quota is not exceeded\n"
                    "• Network connection is working",
                    parse_mode="Markdown"
                )
        
        elif provider == "groq":
            # Force reinitialize Groq
            ai_assistant._groq_client = None
            ai_assistant._preferred_provider = "groq"
            success = ai_assistant.initialize_groq()
            
            if success:
                await update.message.reply_text(
                    "✅ *Switched to Groq*\n\n"
                    "AI requests will now use Groq as primary provider.",
                    parse_mode="Markdown"
                )
                user_logger.info(f"Admin {user.id} switched to Groq")
            else:
                await update.message.reply_text(
                    "❌ *Failed to initialize Groq*\n\n"
                    "Check if:\n"
                    "• GROQ_API_KEY is set in config\n"
                    "• groq package is installed (`pip install groq`)\n"
                    "• Network connection is working",
                    parse_mode="Markdown"
                )
        
        elif provider == "both":
            # Initialize both (no tests to save quota)
            ai_assistant._gemini_model = None
            ai_assistant._groq_client = None
            ai_assistant._preferred_provider = "both"
            
            gemini_ok = ai_assistant.initialize_gemini()
            groq_ok = ai_assistant.initialize_groq()
            
            results = []
            if gemini_ok:
                results.append("✅ Gemini initialized")
            else:
                results.append("❌ Gemini failed")
            
            if groq_ok:
                results.append("✅ Groq initialized")
            else:
                results.append("❌ Groq failed")
            
            await update.message.reply_text(
                "🔄 *Initialized Both Providers*\n\n" + "\n".join(results),
                parse_mode="Markdown"
            )
            user_logger.info(f"Admin {user.id} initialized both AI providers")
        
        else:
            await update.message.reply_text(
                f"❌ Unknown provider: `{provider}`\n\n"
                f"Use: `gemini`, `groq`, or `both`",
                parse_mode="Markdown"
            )
    
    except Exception as e:
        await update.message.reply_text(f"❌ Error switching model: {str(e)}")
        user_logger.error(f"Error in admin_switch_ai_model: {e}")

async def admin_test_ai_model(update: Update, context: CallbackContext) -> None:
    """Admin command to test AI providers with actual requests"""
    user = update.effective_user
    
    # Check if user is admin
    config = get_config()
    admin_id = config.ADMIN_ID
    if user.id != admin_id:
        await update.message.reply_text("❌ Admin access required")
        return
    
    try:
        from utils import ai_assistant
        
        status_msg = await update.message.reply_text("🧪 Testing AI models...")
        
        results = ["🧪 *AI Model Test Results*\n"]
        
        # Test Gemini
        results.append("*Testing Gemini:*")
        if ai_assistant._gemini_model is None:
            results.append("❌ Not initialized")
            results.append("")
        else:
            try:
                client, model_name = ai_assistant._gemini_model
                test_response = client.models.generate_content(
                    model=model_name,
                    contents="Reply with just 'OK'"
                )
                response_text = test_response.text.strip()
                results.append(f"✅ Working!")
                results.append(f"   Model: `{model_name}`")
                results.append(f"   Response: {response_text[:30]}")
                results.append("")
            except Exception as e:
                error_msg = str(e)[:100]
                if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                    results.append(f"⚠️ Quota exceeded")
                    results.append(f"   Switch to Groq: `/switchmodel groq`")
                else:
                    results.append(f"❌ Error: {error_msg}")
                results.append("")
        
        # Test Groq
        results.append("*Testing Groq:*")
        if ai_assistant._groq_client is None:
            results.append("❌ Not initialized")
            results.append("   Initialize: `/switchmodel groq`")
        else:
            try:
                test_response = ai_assistant._groq_client.chat.completions.create(
                    messages=[{"role": "user", "content": "Reply with just 'OK'"}],
                    model="llama-3.3-70b-versatile",
                    max_tokens=10
                )
                response_text = test_response.choices[0].message.content.strip()
                results.append(f"✅ Working!")
                results.append(f"   Model: `llama-3.3-70b-versatile`")
                results.append(f"   Response: {response_text[:30]}")
            except Exception as e:
                results.append(f"❌ Error: {str(e)[:100]}")
        
        results.append("")
        results.append("💡 *Note:* Testing uses API quota")
        
        response = "\n".join(results)
        await status_msg.edit_text(response, parse_mode="Markdown")
        user_logger.info(f"Admin {user.id} tested AI models")
    
    except Exception as e:
        await update.message.reply_text(f"❌ Error testing models: {str(e)}")
        user_logger.error(f"Error in admin_test_ai_model: {e}")

# === FEATURE CONTROL ADMIN COMMANDS ===

async def admin_disable_feature(update: Update, context: CallbackContext) -> None:
    """Admin command to disable a bot feature"""
    user = update.effective_user

    # Check if user is admin
    if user.id != ADMIN_ID:
        await update.message.reply_text("❌ Admin access required")
        return

    try:
        # Import feature controller
        from data.feature_control import get_feature_controller

        feature_controller = get_feature_controller()

        # Get feature name from command arguments
        if not context.args:
            available_features = feature_controller.get_available_features()
            features_list = "\n".join([f"• `{f}`" for f in available_features])

            await update.message.reply_text(
                f"❌ **Feature name required**\n\n"
                f"**Usage:** `/disable <feature> [reason]`\n\n"
                f"**Available features:**\n{features_list}\n\n"
                f"**Example:** `/disable download Temporarily disabled for maintenance`",
                parse_mode="Markdown"
            )
            return

        feature_name = context.args[0].lower()
        reason = " ".join(context.args[1:]) if len(context.args) > 1 else "There are some problems in the commmand"

        success, message = feature_controller.disable_feature(feature_name, user.id, reason)

        if success:
            await update.message.reply_text(
                f"{message}\n\n**Reason:** {reason}\n\n"
                f"Users will now see a disabled message when trying to use this feature.",
                parse_mode="Markdown"
            )
            user_logger.info(f"Admin {user.id} disabled feature '{feature_name}': {reason}")
        else:
            await update.message.reply_text(f"❌ {message}")

    except Exception as e:
        await update.message.reply_text(f"❌ Error disabling feature: {str(e)}")
        user_logger.error(f"Error in admin_disable_feature: {e}")

async def admin_enable_feature(update: Update, context: CallbackContext) -> None:
    """Admin command to enable a bot feature"""
    user = update.effective_user

    # Check if user is admin
    if user.id != ADMIN_ID:
        await update.message.reply_text("❌ Admin access required")
        return

    try:
        # Import feature controller
        from data.feature_control import get_feature_controller

        feature_controller = get_feature_controller()

        # Get feature name from command arguments
        if not context.args:
            available_features = feature_controller.get_available_features()
            features_list = "\n".join([f"• `{f}`" for f in available_features])

            await update.message.reply_text(
                f"❌ **Feature name required**\n\n"
                f"**Usage:** `/enable <feature>`\n\n"
                f"**Available features:**\n{features_list}\n\n"
                f"**Example:** `/enable download`",
                parse_mode="Markdown"
            )
            return

        feature_name = context.args[0].lower()

        success, message = feature_controller.enable_feature(feature_name, user.id)

        if success:
            await update.message.reply_text(
                f"{message}\n\n"
                f"Users can now use this feature normally.",
                parse_mode="Markdown"
            )
            user_logger.info(f"Admin {user.id} enabled feature '{feature_name}'")
        else:
            await update.message.reply_text(f"❌ {message}")

    except Exception as e:
        await update.message.reply_text(f"❌ Error enabling feature: {str(e)}")
        user_logger.error(f"Error in admin_enable_feature: {e}")

async def admin_feature_status(update: Update, context: CallbackContext) -> None:
    """Admin command to view all feature statuses"""
    user = update.effective_user

    # Check if user is admin
    if user.id != ADMIN_ID:
        await update.message.reply_text("❌ Admin access required")
        return

    try:
        # Import feature controller
        from data.feature_control import get_feature_controller

        feature_controller = get_feature_controller()

        all_features = feature_controller.get_all_features_status()

        status_text = "🔧 **Feature Control Status**\n\n"

        for feature_name, feature_info in all_features.items():
            # Status icons
            enabled_icon = "✅" if feature_info['enabled'] else "❌"
            restricted_icon = "🔒" if feature_info.get('restricted_to_authorized', False) else ""
            admin_only_icon = "🔐" if feature_info.get('admin_only', False) else ""

            feature_display = feature_info['name']

            status_text += f"{enabled_icon}{restricted_icon}{admin_only_icon} **{feature_display}**\n"
            status_text += f"   Commands: {', '.join(feature_info['commands'])}\n"

            # Show disabled status
            if not feature_info['enabled']:
                reason = feature_info.get('reason', 'No reason provided')
                modified_date = feature_info.get('disabled_date', 'Unknown')
                if modified_date and modified_date != 'Unknown':
                    try:
                        from datetime import datetime
                        dt = datetime.fromisoformat(modified_date)
                        modified_date = dt.strftime('%Y-%m-%d %H:%M')
                    except:
                        pass
                status_text += f"   ❌ Disabled: {modified_date}\n"
                status_text += f"   Reason: {reason}\n"

            # Show admin-only status
            if feature_info.get('admin_only', False):
                admin_only_reason = feature_info.get('admin_only_reason', 'No reason provided')
                admin_only_date = feature_info.get('admin_only_date', 'Unknown')
                if admin_only_date and admin_only_date != 'Unknown':
                    try:
                        from datetime import datetime
                        dt = datetime.fromisoformat(admin_only_date)
                        admin_only_date = dt.strftime('%Y-%m-%d %H:%M')
                    except:
                        pass
                status_text += f"   🔐 Admin-Only: {admin_only_date}\n"
                status_text += f"   Access: Administrators only\n"
                status_text += f"   Reason: {admin_only_reason}\n"

            # Show restriction status
            if feature_info.get('restricted_to_authorized', False):
                restriction_reason = feature_info.get('restriction_reason', 'No reason provided')
                restricted_date = feature_info.get('restricted_date', 'Unknown')
                if restricted_date and restricted_date != 'Unknown':
                    try:
                        from datetime import datetime
                        dt = datetime.fromisoformat(restricted_date)
                        restricted_date = dt.strftime('%Y-%m-%d %H:%M')
                    except:
                        pass
                status_text += f"   🔒 Restricted: {restricted_date}\n"
                status_text += f"   Access: Authorized users only\n"
                status_text += f"   Reason: {restriction_reason}\n"

            status_text += "\n"

        status_text += "**Commands:**\n"
        status_text += "• `/disable <feature> [reason]` - Disable a feature\n"
        status_text += "• `/enable <feature>` - Enable a feature\n"
        status_text += "• `/restrict_access <feature> [reason]` - Restrict to authorized users\n"
        status_text += "• `/unrestrict_access <feature>` - Remove access restriction\n"
        status_text += "• `/set_admin_only <feature> [reason]` - Set feature to admin-only\n"
        status_text += "• `/unset_admin_only <feature>` - Remove admin-only restriction\n"
        status_text += "• `/feature_status` - View this status\n\n"
        status_text += "**Legend:**\n"
        status_text += "✅ = Enabled, ❌ = Disabled, 🔒 = Restricted to authorized users, 🔐 = Admin-only"

        await update.message.reply_text(status_text, parse_mode="Markdown")
        user_logger.info(f"Admin {user.id} viewed feature status")

    except Exception as e:
        await update.message.reply_text(f"❌ Error retrieving feature status: {str(e)}")
        user_logger.error(f"Error in admin_feature_status: {e}")

# === ACCESS RESTRICTION ADMIN COMMANDS ===

async def admin_restrict_access(update: Update, context: CallbackContext) -> None:
    """Admin command to restrict a feature to authorized users only"""
    user = update.effective_user

    # Check if user is admin
    if user.id != ADMIN_ID:
        await update.message.reply_text("❌ Admin access required")
        return

    try:
        # Import feature controller
        from data.feature_control import get_feature_controller

        feature_controller = get_feature_controller()

        # Get feature name from command arguments
        if not context.args:
            available_features = feature_controller.get_available_features()
            features_list = "\n".join([f"• `{f}`" for f in available_features])

            await update.message.reply_text(
                f"❌ **Feature name required**\n\n"
                f"**Usage:** `/restrict_access <feature> [reason]`\n\n"
                f"**Available features:**\n{features_list}\n\n"
                f"**Example:** `/restrict_access download Premium feature - contact admin for access`",
                parse_mode="Markdown"
            )
            return

        feature_name = context.args[0].lower()
        reason = " ".join(context.args[1:]) if len(context.args) > 1 else "Restricted to authorized users only"

        success, message = feature_controller.restrict_access(feature_name, user.id, reason)

        if success:
            await update.message.reply_text(
                f"{message}\n\n**Reason:** {reason}\n\n"
                f"Only authorized users can now access this feature.\n"
                f"Unauthorized users will see a restriction message.",
                parse_mode="Markdown"
            )
            user_logger.info(f"Admin {user.id} restricted access to '{feature_name}': {reason}")
        else:
            await update.message.reply_text(f"❌ {message}")

    except Exception as e:
        await update.message.reply_text(f"❌ Error restricting access: {str(e)}")
        user_logger.error(f"Error in admin_restrict_access: {e}")

async def admin_unrestrict_access(update: Update, context: CallbackContext) -> None:
    """Admin command to remove access restriction from a feature"""
    user = update.effective_user

    # Check if user is admin
    if user.id != ADMIN_ID:
        await update.message.reply_text("❌ Admin access required")
        return

    try:
        # Import feature controller
        from data.feature_control import get_feature_controller

        feature_controller = get_feature_controller()

        # Get feature name from command arguments
        if not context.args:
            available_features = feature_controller.get_available_features()
            features_list = "\n".join([f"• `{f}`" for f in available_features])

            await update.message.reply_text(
                f"❌ **Feature name required**\n\n"
                f"**Usage:** `/unrestrict_access <feature>`\n\n"
                f"**Available features:**\n{features_list}\n\n"
                f"**Example:** `/unrestrict_access download`",
                parse_mode="Markdown"
            )
            return

        feature_name = context.args[0].lower()

        success, message = feature_controller.unrestrict_access(feature_name, user.id)

        if success:
            await update.message.reply_text(
                f"{message}\n\n"
                f"All users can now access this feature normally.",
                parse_mode="Markdown"
            )
            user_logger.info(f"Admin {user.id} unrestricted access to '{feature_name}'")
        else:
            await update.message.reply_text(f"❌ {message}")

    except Exception as e:
        await update.message.reply_text(f"❌ Error unrestricting access: {str(e)}")
        user_logger.error(f"Error in admin_unrestrict_access: {e}")

# === ADMIN-ONLY CONTROL COMMANDS ===

async def admin_set_admin_only(update: Update, context: CallbackContext) -> None:
    """Admin command to set a feature to admin-only"""
    user = update.effective_user

    # Check if user is admin
    if user.id != ADMIN_ID:
        await update.message.reply_text("❌ Admin access required")
        return

    try:
        # Import feature controller
        from data.feature_control import get_feature_controller

        feature_controller = get_feature_controller()

        # Get feature name from command arguments
        if not context.args:
            available_features = feature_controller.get_available_features()
            features_list = "\n".join([f"• `{f}`" for f in available_features])

            await update.message.reply_text(
                f"❌ **Feature name required**\n\n"
                f"**Usage:** `/set_admin_only <feature> [reason]`\n\n"
                f"**Available features:**\n{features_list}\n\n"
                f"**Example:** `/set_admin_only refresh Admin maintenance command`",
                parse_mode="Markdown"
            )
            return

        feature_name = context.args[0].lower()
        reason = " ".join(context.args[1:]) if len(context.args) > 1 else "Restricted to administrators only"

        success, message = feature_controller.set_admin_only(feature_name, user.id, reason)

        if success:
            await update.message.reply_text(
                f"{message}\n\n**Reason:** {reason}\n\n"
                f"Only administrators can now access this feature.\n"
                f"Non-admin users will see an admin-only message.",
                parse_mode="Markdown"
            )
            user_logger.info(f"Admin {user.id} set '{feature_name}' to admin-only: {reason}")
        else:
            await update.message.reply_text(f"❌ {message}")

    except Exception as e:
        await update.message.reply_text(f"❌ Error setting admin-only: {str(e)}")
        user_logger.error(f"Error in admin_set_admin_only: {e}")

async def admin_unset_admin_only(update: Update, context: CallbackContext) -> None:
    """Admin command to remove admin-only restriction from a feature"""
    user = update.effective_user

    # Check if user is admin
    if user.id != ADMIN_ID:
        await update.message.reply_text("❌ Admin access required")
        return

    try:
        # Import feature controller
        from data.feature_control import get_feature_controller

        feature_controller = get_feature_controller()

        # Get feature name from command arguments
        if not context.args:
            available_features = feature_controller.get_available_features()
            features_list = "\n".join([f"• `{f}`" for f in available_features])

            await update.message.reply_text(
                f"❌ **Feature name required**\n\n"
                f"**Usage:** `/unset_admin_only <feature>`\n\n"
                f"**Available features:**\n{features_list}\n\n"
                f"**Example:** `/unset_admin_only refresh`",
                parse_mode="Markdown"
            )
            return

        feature_name = context.args[0].lower()

        success, message = feature_controller.unset_admin_only(feature_name, user.id)

        if success:
            await update.message.reply_text(
                f"{message}\n\n"
                f"All users can now access this feature normally.",
                parse_mode="Markdown"
            )
            user_logger.info(f"Admin {user.id} removed admin-only from '{feature_name}'")
        else:
            await update.message.reply_text(f"❌ {message}")

    except Exception as e:
        await update.message.reply_text(f"❌ Error unsetting admin-only: {str(e)}")
        user_logger.error(f"Error in admin_unset_admin_only: {e}")

async def admin_debug_features(update: Update, context: CallbackContext) -> None:
    """Admin command to debug feature loading"""
    user = update.effective_user

    # Check if user is admin
    if user.id != ADMIN_ID:
        await update.message.reply_text("❌ Admin access required")
        return

    try:
        await update.message.reply_text("🔍 **Debugging Feature Loading...**\n\nCheck the logs for detailed information.", parse_mode="Markdown")

        # Import feature controller
        from data.feature_control import get_feature_controller

        feature_controller = get_feature_controller()

        # Force reload from Google Drive (bypass cache)
        feature_controller._cache = None
        df = feature_controller._load_from_drive()

        debug_text = "🔍 **Feature Loading Debug Results**\n\n"
        debug_text += f"**Data Source:** Google Drive\n"
        debug_text += f"**Rows Loaded:** {len(df)}\n"
        debug_text += f"**Columns:** {len(df.columns)}\n\n"

        debug_text += "**Feature Status from Excel:**\n"
        for _, row in df.iterrows():
            feature_name = row.get('feature_name', 'UNKNOWN')
            enabled = row.get('enabled', 'UNKNOWN')
            enabled_icon = "✅" if enabled else "❌"
            debug_text += f"{enabled_icon} {feature_name}: {enabled}\n"

        debug_text += "\n**Feature Status from Bot Logic:**\n"
        for _, row in df.iterrows():
            feature_name = row.get('feature_name', 'UNKNOWN')
            bot_enabled = feature_controller.is_feature_enabled(feature_name)
            enabled_icon = "✅" if bot_enabled else "❌"
            debug_text += f"{enabled_icon} {feature_name}: {bot_enabled}\n"

        await update.message.reply_text(debug_text, parse_mode="Markdown")
        user_logger.info(f"Admin {user.id} debugged feature loading")

    except Exception as e:
        await update.message.reply_text(f"❌ Error debugging features: {str(e)}")
        user_logger.error(f"Error in admin_debug_features: {e}")

async def admin_add_missing_features(update: Update, context: CallbackContext) -> None:
    """Admin command to add missing features to Database"""
    user = update.effective_user

    # Check if user is admin
    if user.id != ADMIN_ID:
        await update.message.reply_text("❌ Admin access required")
        return

    try:
        await update.message.reply_text("🆕 **Adding Missing Features...**\n\nThis may take a moment...", parse_mode="Markdown")

        # Import feature controller
        from data.feature_control import get_feature_controller
        import pandas as pd
        from datetime import datetime

        feature_controller = get_feature_controller()

        # Get current data
        df = feature_controller._load_from_drive()
        existing_features = df['feature_name'].tolist() if 'feature_name' in df.columns else []

        # Define new features to add
        new_features_data = [
            {
                'feature_name': 'notation',
                'feature_display_name': 'Musical Notation',
                'commands': '/notation, notation search',
                'enabled': True,
                'disabled_reason': '',
                'disabled_by_admin_id': '',
                'disabled_date': '',
                'restricted_to_authorized': False,
                'restriction_reason': '',
                'restricted_by_admin_id': '',
                'restricted_date': '',
                'last_modified': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            },
            {
                'feature_name': 'vocabulary',
                'feature_display_name': 'Song Vocabulary',
                'commands': '/vocabulary, word search',
                'enabled': True,
                'disabled_reason': '',
                'disabled_by_admin_id': '',
                'disabled_date': '',
                'restricted_to_authorized': False,
                'restriction_reason': '',
                'restricted_by_admin_id': '',
                'restricted_date': '',
                'last_modified': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            },
            {
                'feature_name': 'games',
                'feature_display_name': 'Bible Games',
                'commands': '/games, bible games',
                'enabled': True,
                'disabled_reason': '',
                'disabled_by_admin_id': '',
                'disabled_date': '',
                'restricted_to_authorized': False,
                'restriction_reason': '',
                'restricted_by_admin_id': '',
                'restricted_date': '',
                'last_modified': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            },
            {
                'feature_name': 'tune',
                'feature_display_name': 'Tune Finder',
                'commands': '/tune, tune search',
                'enabled': True,
                'disabled_reason': '',
                'disabled_by_admin_id': '',
                'disabled_date': '',
                'restricted_to_authorized': False,
                'restriction_reason': '',
                'restricted_by_admin_id': '',
                'restricted_date': '',
                'last_modified': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            },
            {
                'feature_name': 'theme',
                'feature_display_name': 'Theme Search',
                'commands': '/theme, theme finder',
                'enabled': True,
                'disabled_reason': '',
                'disabled_by_admin_id': '',
                'disabled_date': '',
                'restricted_to_authorized': False,
                'restriction_reason': '',
                'restricted_by_admin_id': '',
                'restricted_date': '',
                'last_modified': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
        ]

        # Check which features need to be added
        features_to_add = []
        for feature_data in new_features_data:
            if feature_data['feature_name'] not in existing_features:
                features_to_add.append(feature_data)

        # Also check if we need to restore original features
        original_features_data = [
            {
                'feature_name': 'download',
                'feature_display_name': 'Download Commands',
                'commands': '/download, URL downloads',
                'enabled': False,  # Keep previous disabled state
                'disabled_reason': 'There are some problems in the commmand',
                'disabled_by_admin_id': '757438955',
                'disabled_date': '2025-08-30 11:57:20',
                'restricted_to_authorized': False,
                'restriction_reason': '',
                'restricted_by_admin_id': '',
                'restricted_date': '',
                'last_modified': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            },
            {
                'feature_name': 'search',
                'feature_display_name': 'Song Search',
                'commands': '/search',
                'enabled': True,
                'disabled_reason': '',
                'disabled_by_admin_id': '',
                'disabled_date': '',
                'restricted_to_authorized': False,
                'restriction_reason': '',
                'restricted_by_admin_id': '',
                'restricted_date': '',
                'last_modified': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            },
            {
                'feature_name': 'date',
                'feature_display_name': 'Date Commands',
                'commands': '/date',
                'enabled': True,
                'disabled_reason': '',
                'disabled_by_admin_id': '',
                'disabled_date': '',
                'restricted_to_authorized': False,
                'restriction_reason': '',
                'restricted_by_admin_id': '',
                'restricted_date': '',
                'last_modified': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            },
            {
                'feature_name': 'bible',
                'feature_display_name': 'Bible Verses',
                'commands': '/bible',
                'enabled': True,
                'disabled_reason': '',
                'disabled_by_admin_id': '',
                'disabled_date': '',
                'restricted_to_authorized': False,
                'restriction_reason': '',
                'restricted_by_admin_id': '',
                'restricted_date': '',
                'last_modified': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            },
            {
                'feature_name': 'check',
                'feature_display_name': 'Song Checking',
                'commands': '/check',
                'enabled': True,
                'disabled_reason': '',
                'disabled_by_admin_id': '',
                'disabled_date': '',
                'restricted_to_authorized': False,
                'restriction_reason': '',
                'restricted_by_admin_id': '',
                'restricted_date': '',
                'last_modified': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            },
            {
                'feature_name': 'last',
                'feature_display_name': 'Last Sung',
                'commands': '/last',
                'enabled': True,  # Re-enable last (was disabled before)
                'disabled_reason': '',
                'disabled_by_admin_id': '',
                'disabled_date': '',
                'restricted_to_authorized': False,
                'restriction_reason': '',
                'restricted_by_admin_id': '',
                'restricted_date': '',
                'last_modified': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
        ]

        # Check which original features need to be restored
        for feature_data in original_features_data:
            if feature_data['feature_name'] not in existing_features:
                features_to_add.append(feature_data)

        if not features_to_add:
            await update.message.reply_text("✅ **All features already exist!**\n\nNo new features need to be added.", parse_mode="Markdown")
            return

        # Add missing features to DataFrame
        new_rows_df = pd.DataFrame(features_to_add)
        updated_df = pd.concat([df, new_rows_df], ignore_index=True)

        # Save to Google Drive
        if feature_controller._save_to_drive(updated_df):
            # Clear cache to force reload
            feature_controller._cache = None

            added_names = [f['feature_display_name'] for f in features_to_add]
            result_text = f"🎉 **Added {len(features_to_add)} New Features!**\n\n"
            result_text += "**New Features:**\n"
            for name in added_names:
                result_text += f"• {name}\n"

            result_text += f"\n**Total Features:** {len(updated_df)}\n\n"
            result_text += "**Next Steps:**\n"
            result_text += "• Use `/feature_status` to see all features\n"
            result_text += "• Use `/disable <feature>` to disable any feature\n"
            result_text += "• Use `/restrict_access <feature>` to restrict access"

            await update.message.reply_text(result_text, parse_mode="Markdown")
            user_logger.info(f"Admin {user.id} added {len(features_to_add)} new features")
        else:
            await update.message.reply_text("❌ **Failed to save new features**\n\nThere was an error saving to Google Drive.", parse_mode="Markdown")

    except Exception as e:
        await update.message.reply_text(f"❌ Error adding features: {str(e)}")
        user_logger.error(f"Error in admin_add_missing_features: {e}")

async def admin_restore_all_features(update: Update, context: CallbackContext) -> None:
    """Admin command to restore all 11 features (original 6 + new 5)"""
    user = update.effective_user

    # Check if user is admin
    if user.id != ADMIN_ID:
        await update.message.reply_text("❌ Admin access required")
        return

    try:
        await update.message.reply_text("🔄 **Restoring All Features...**\n\nThis will restore all 11 features in the Database.", parse_mode="Markdown")

        # Import feature controller
        from data.feature_control import get_feature_controller
        import pandas as pd
        from datetime import datetime

        feature_controller = get_feature_controller()

        # Create complete feature set (all 11 features)
        all_features_data = [
            # Original 6 features
            {
                'feature_name': 'download',
                'feature_display_name': 'Download Commands',
                'commands': '/download, URL downloads',
                'enabled': False,  # Keep disabled as it was
                'disabled_reason': 'There are some problems in the commmand',
                'disabled_by_admin_id': '757438955',
                'disabled_date': '2025-08-30 11:57:20',
                'restricted_to_authorized': False,
                'restriction_reason': '',
                'restricted_by_admin_id': '',
                'restricted_date': '',
                'last_modified': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            },
            {
                'feature_name': 'search',
                'feature_display_name': 'Song Search',
                'commands': '/search',
                'enabled': True,
                'disabled_reason': '',
                'disabled_by_admin_id': '',
                'disabled_date': '',
                'restricted_to_authorized': False,
                'restriction_reason': '',
                'restricted_by_admin_id': '',
                'restricted_date': '',
                'last_modified': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            },
            {
                'feature_name': 'date',
                'feature_display_name': 'Date Commands',
                'commands': '/date',
                'enabled': True,
                'disabled_reason': '',
                'disabled_by_admin_id': '',
                'disabled_date': '',
                'restricted_to_authorized': False,
                'restriction_reason': '',
                'restricted_by_admin_id': '',
                'restricted_date': '',
                'last_modified': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            },
            {
                'feature_name': 'bible',
                'feature_display_name': 'Bible Verses',
                'commands': '/bible',
                'enabled': True,
                'disabled_reason': '',
                'disabled_by_admin_id': '',
                'disabled_date': '',
                'restricted_to_authorized': False,
                'restriction_reason': '',
                'restricted_by_admin_id': '',
                'restricted_date': '',
                'last_modified': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            },
            {
                'feature_name': 'check',
                'feature_display_name': 'Song Checking',
                'commands': '/check',
                'enabled': True,
                'disabled_reason': '',
                'disabled_by_admin_id': '',
                'disabled_date': '',
                'restricted_to_authorized': False,
                'restriction_reason': '',
                'restricted_by_admin_id': '',
                'restricted_date': '',
                'last_modified': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            },
            {
                'feature_name': 'last',
                'feature_display_name': 'Last Sung',
                'commands': '/last',
                'enabled': True,
                'disabled_reason': '',
                'disabled_by_admin_id': '',
                'disabled_date': '',
                'restricted_to_authorized': False,
                'restriction_reason': '',
                'restricted_by_admin_id': '',
                'restricted_date': '',
                'last_modified': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            },
            # New 5 features
            {
                'feature_name': 'notation',
                'feature_display_name': 'Musical Notation',
                'commands': '/notation, notation search',
                'enabled': True,
                'disabled_reason': '',
                'disabled_by_admin_id': '',
                'disabled_date': '',
                'restricted_to_authorized': False,
                'restriction_reason': '',
                'restricted_by_admin_id': '',
                'restricted_date': '',
                'last_modified': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            },
            {
                'feature_name': 'vocabulary',
                'feature_display_name': 'Song Vocabulary',
                'commands': '/vocabulary, word search',
                'enabled': True,
                'disabled_reason': '',
                'disabled_by_admin_id': '',
                'disabled_date': '',
                'restricted_to_authorized': False,
                'restriction_reason': '',
                'restricted_by_admin_id': '',
                'restricted_date': '',
                'last_modified': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            },
            {
                'feature_name': 'games',
                'feature_display_name': 'Bible Games',
                'commands': '/games, bible games',
                'enabled': True,
                'disabled_reason': '',
                'disabled_by_admin_id': '',
                'disabled_date': '',
                'restricted_to_authorized': False,
                'restriction_reason': '',
                'restricted_by_admin_id': '',
                'restricted_date': '',
                'last_modified': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            },
            {
                'feature_name': 'tune',
                'feature_display_name': 'Tune Finder',
                'commands': '/tune, tune search',
                'enabled': True,
                'disabled_reason': '',
                'disabled_by_admin_id': '',
                'disabled_date': '',
                'restricted_to_authorized': False,
                'restriction_reason': '',
                'restricted_by_admin_id': '',
                'restricted_date': '',
                'last_modified': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            },
            {
                'feature_name': 'theme',
                'feature_display_name': 'Theme Search',
                'commands': '/theme, theme finder',
                'enabled': True,
                'disabled_reason': '',
                'disabled_by_admin_id': '',
                'disabled_date': '',
                'restricted_to_authorized': False,
                'restriction_reason': '',
                'restricted_by_admin_id': '',
                'restricted_date': '',
                'last_modified': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
        ]

        # Create complete DataFrame
        complete_df = pd.DataFrame(all_features_data)

        # Save to Google Drive (replace entire sheet)
        if feature_controller._save_to_drive(complete_df):
            # Clear cache to force reload
            feature_controller._cache = None

            result_text = f"🎉 **All Features Restored Successfully!**\n\n"
            result_text += f"**Total Features:** 11\n\n"
            result_text += "**Original Features (6):**\n"
            result_text += "• Download Commands (disabled)\n"
            result_text += "• Song Search\n"
            result_text += "• Date Commands\n"
            result_text += "• Bible Verses\n"
            result_text += "• Song Checking\n"
            result_text += "• Last Sung\n\n"
            result_text += "**New Features (5):**\n"
            result_text += "• Musical Notation\n"
            result_text += "• Song Vocabulary\n"
            result_text += "• Bible Games\n"
            result_text += "• Tune Finder\n"
            result_text += "• Theme Search\n\n"
            result_text += "Use `/feature_status` to see all features!"

            await update.message.reply_text(result_text, parse_mode="Markdown")
            user_logger.info(f"Admin {user.id} restored all 11 features")
        else:
            await update.message.reply_text("❌ **Failed to restore features**\n\nThere was an error saving to Google Drive.", parse_mode="Markdown")

    except Exception as e:
        await update.message.reply_text(f"❌ Error restoring features: {str(e)}")
        user_logger.error(f"Error in admin_restore_all_features: {e}")

# === AI ASSISTANT HANDLER ===

async def execute_tune_search(update: Update, context: CallbackContext, query: str) -> None:
    """
    Helper function to execute tune search directly without conversation flow.
    Supports both hymn number (e.g., "44", "H-44") and tune name (e.g., "abridge").
    """
    from data.datasets import Tune_finder_of_known_songs, Hymn_Tune_no_Finder, get_all_data
    from utils.notation import find_tune_page_number, getNotation
    
    query = query.strip()
    
    # Try to parse as hymn number
    hymn_match = re.match(r'^[Hh]?-?(\d+)$', query)
    
    if hymn_match:
        # Search by hymn number
        hymn_no = int(hymn_match.group(1))
        tune_result = Tune_finder_of_known_songs(hymn_no)
        
        if not tune_result or tune_result == "Invalid Number":
            await update.message.reply_text(f"❌ No tunes found for H-{hymn_no}.")
            return
        
        # Parse tune names
        tune_names = [tune.strip() for tune in str(tune_result).split(',') if tune.strip()]
        
        if not tune_names:
            await update.message.reply_text(f"❌ No tunes found for H-{hymn_no}.")
            return
        
        # Build result with notation links
        all_data = get_all_data()
        dfH = all_data.get('dfH')
        dfTH = all_data.get('dfTH')
        
        result_lines = [f"🎵 **Tunes for H-{hymn_no}:**\n"]
        
        for i, tune_name in enumerate(tune_names, 1):
            page_no, source = find_tune_page_number(tune_name, hymn_no, dfH, dfTH)
            
            line = f"{i}. ♪ {tune_name}"
            
            if page_no:
                notation_link = getNotation(page_no)
                if notation_link and "http" in str(notation_link):
                    line += f" - [📖 Notation]({notation_link})"
                else:
                    line += f" - Page {page_no}"
            
            result_lines.append(line)
        
        result = "\n".join(result_lines)
        await update.message.reply_text(result, parse_mode="Markdown", disable_web_page_preview=True)
        
    else:
        # Search by tune name
        all_data = get_all_data()
        dfTH = all_data.get('dfTH')
        dfH = all_data.get('dfH')
        
        if dfTH is None or dfTH.empty:
            await update.message.reply_text("❌ Tune database not available.")
            return
        
        result_df = Hymn_Tune_no_Finder(dfTH, query, top_n=10)
        
        if result_df.empty:
            await update.message.reply_text(f"❌ No tunes found matching '{query}'.")
            return
        
        # Build result with notation links
        result_lines = [f"🎵 **Top matching hymns for tune '{query}':**\n"]
        
        for _, row in result_df.iterrows():
            hymn_no = int(row['Hymn no'])
            tune_name = row['Tune Index']
            similarity = row['Similarity']
            
            page_no, source = find_tune_page_number(tune_name, hymn_no, dfH, dfTH)
            
            line = f"**H-{hymn_no}**: {tune_name} (match: {similarity:.0%})"
            
            if page_no:
                notation_link = getNotation(page_no)
                if notation_link and "http" in str(notation_link):
                    line += f" - [📖 Notation]({notation_link})"
                else:
                    line += f" - Page {page_no}"
            
            result_lines.append(line)
        
        result = "\n".join(result_lines)
        await update.message.reply_text(result, parse_mode="Markdown", disable_web_page_preview=True)

async def execute_search(update: Update, context: CallbackContext, query: str) -> None:
    """
    Helper function to execute song search directly without conversation flow.
    Searches across hymns, lyrics, and conventions.
    """
    from utils.search import find_best_match
    from data.datasets import IndexFinder
    
    query = query.strip()
    
    if not query:
        await update.message.reply_text("❌ Please provide a search query.")
        return
    
    # Check if it's a direct song code (H-44, L-123, C-21)
    song_code_match = re.match(r'^([HLC])-?(\d+)$', query, re.IGNORECASE)
    if song_code_match:
        song_type = song_code_match.group(1).upper()
        song_num = song_code_match.group(2)
        song_code = f"{song_type}-{song_num}"
        song_name = IndexFinder(song_code)
        
        if song_name and song_name != "Invalid Number":
            await update.message.reply_text(f"🎵 **{song_code}**: {song_name}")
        else:
            await update.message.reply_text(f"❌ Song {song_code} not found.")
        return
    
    # Search all categories
    results = {}
    for category in ['hymn', 'lyric', 'convention']:
        try:
            search_result = find_best_match(query, category=category, top_n=5)
            if isinstance(search_result, tuple) and search_result[0]:
                results[category] = search_result
        except Exception as e:
            user_logger.error(f"Search error for {category}: {e}")
    
    if not results:
        await update.message.reply_text(f"❌ No results found for '{query}'.")
        return
    
    # Build comprehensive results
    response_lines = [f"🔍 **Search results for '{query}':**\n"]
    
    prefix_map = {'hymn': 'H', 'lyric': 'L', 'convention': 'C'}
    
    for category, (matches, column) in results.items():
        if not matches:
            continue
        
        prefix = prefix_map[category]
        category_name = category.capitalize()
        response_lines.append(f"**{category_name}s:**")
        
        for song_num, similarity, context in matches[:3]:  # Top 3 per category
            song_code = f"{prefix}-{song_num}"
            song_name = IndexFinder(song_code)
            
            if song_name and song_name != "Invalid Number":
                line = f"  • **{song_code}**: {song_name}"
                if similarity < 1.0:
                    line += f" (match: {similarity:.0%})"
                response_lines.append(line)
        
        response_lines.append("")  # Empty line between categories
    
    result_text = "\n".join(response_lines)
    await update.message.reply_text(result_text, parse_mode="Markdown")

async def execute_theme_search(update: Update, context: CallbackContext, theme_query: str, theme_type: str = None) -> None:
    """
    Helper function to execute theme search directly without conversation flow.
    Searches for songs by theme across hymns or lyrics.
    """
    from data.datasets import get_all_data, IndexFinder
    from data.vocabulary import ChoirVocabulary
    from telegram_handlers.conversations import get_theme_model, get_theme_embeddings, find_similar_themes, get_vocabulary_cache
    from sklearn.metrics.pairwise import cosine_similarity
    
    theme_query = theme_query.strip()
    
    if not theme_query:
        await update.message.reply_text("❌ Please provide a theme to search for.")
        return
    
    # Get data
    data = get_all_data()
    dfH = data.get('dfH')
    dfL = data.get('dfL')
    
    if dfH is None or dfL is None:
        await update.message.reply_text("❌ Theme database not available.")
        return
    
    # Get vocabulary
    _, Hymn_Vocabulary, Lyric_Vocabulary, _ = get_vocabulary_cache()
    
    # Determine which type to search (default to both)
    search_hymns = theme_type is None or theme_type.lower() in ['hymns', 'hymn', 'h']
    search_lyrics = theme_type is None or theme_type.lower() in ['lyrics', 'lyric', 'l']
    
    results = {}
    
    # Search hymns
    if search_hymns:
        hymn_themes = dfH["Themes"].dropna().str.split(",").explode().str.strip().unique()
        theme_embeddings, theme_texts = get_theme_embeddings("hymns", hymn_themes)
        matched_themes = find_similar_themes(theme_query, theme_texts, theme_embeddings, threshold=0.6)
        
        if matched_themes:
            filtered_df = dfH[dfH["Themes"].apply(lambda x: any(t in str(x) for t in matched_themes))]
            known = Hymn_Vocabulary.values
            
            # Get songs that are in vocabulary (known songs)
            hymn_results = []
            for _, row in filtered_df.iterrows():
                hymn_no = int(row['Hymn no'])
                if hymn_no in known:
                    song_code = f"H-{hymn_no}"
                    song_name = IndexFinder(song_code)
                    if song_name and song_name != "Invalid Number":
                        hymn_results.append((song_code, song_name))
            
            if hymn_results:
                results['hymns'] = (hymn_results, matched_themes)
    
    # Search lyrics
    if search_lyrics:
        lyric_themes = dfL["Themes"].dropna().str.split(",").explode().str.strip().unique()
        theme_embeddings, theme_texts = get_theme_embeddings("lyrics", lyric_themes)
        matched_themes = find_similar_themes(theme_query, theme_texts, theme_embeddings, threshold=0.6)
        
        if matched_themes:
            filtered_df = dfL[dfL["Themes"].apply(lambda x: any(t in str(x) for t in matched_themes))]
            known = Lyric_Vocabulary.values
            
            # Get songs that are in vocabulary (known songs)
            lyric_results = []
            for _, row in filtered_df.iterrows():
                lyric_no = int(row['Lyric no'])
                if lyric_no in known:
                    song_code = f"L-{lyric_no}"
                    song_name = IndexFinder(song_code)
                    if song_name and song_name != "Invalid Number":
                        lyric_results.append((song_code, song_name))
            
            if lyric_results:
                results['lyrics'] = (lyric_results, matched_themes)
    
    if not results:
        await update.message.reply_text(f"❌ No songs found with theme '{theme_query}'.")
        return
    
    # Build response
    response_lines = [f"🎯 **Songs with theme '{theme_query}':**\n"]
    
    for category, (songs, themes) in results.items():
        category_name = category.capitalize()
        response_lines.append(f"**{category_name}:**")
        response_lines.append(f"_Matched themes: {', '.join(themes[:3])}_\n")
        
        # Show up to 10 songs per category
        for song_code, song_name in songs[:10]:
            response_lines.append(f"• **{song_code}**: {song_name}")
        
        if len(songs) > 10:
            response_lines.append(f"\n_...and {len(songs) - 10} more_")
        
        response_lines.append("")  # Empty line
    
    result_text = "\n".join(response_lines)
    await update.message.reply_text(result_text, parse_mode="Markdown")

async def execute_notation(update: Update, context: CallbackContext, song_code: str) -> None:
    """
    Helper function to execute notation request directly.
    Checks if user is authorized before providing notation.
    """
    from data.datasets import Tune_finder_of_known_songs, get_all_data
    from data.vocabulary import standardize_hlc_value
    from utils.notation import find_tune_page_number, getNotation
    from config import get_config
    
    user = update.effective_user
    config = get_config()
    
    # Check if user is authorized (admin only)
    if user.id != config.ADMIN_ID:
        await update.message.reply_text(
            "🚫 **Access Restricted**\n\n"
            "I cannot fetch notation for you as this feature is restricted to authorized users only.\n\n"
            "The notation feature requires special authorization. Please contact the administrator if you need access.",
            parse_mode="Markdown"
        )
        return
    
    # User is authorized, proceed with notation
    song_code = standardize_hlc_value(song_code.strip())
    
    if not song_code:
        await update.message.reply_text("❌ Please provide a valid song code (e.g., H-44, L-323).")
        return
    
    # Handle hymns
    if song_code.startswith("H-"):
        tunes = Tune_finder_of_known_songs(song_code)
        
        if not tunes or tunes == "Invalid Number":
            await update.message.reply_text(f"❌ No tunes found for {song_code}.")
            return
        
        # Parse tune names
        if isinstance(tunes, str):
            tune_list = [t.strip() for t in tunes.split(",") if t.strip()]
        else:
            await update.message.reply_text("❌ Could not parse tunes.")
            return
        
        if not tune_list:
            await update.message.reply_text("❌ No tunes available.")
            return
        
        # Get notation for all tunes
        all_data = get_all_data()
        dfH = all_data.get('dfH')
        dfTH = all_data.get('dfTH')
        
        hymn_no = int(song_code.split('-')[1])
        result_lines = [f"🎵 **Notation for {song_code}:**\n"]
        
        for i, tune_name in enumerate(tune_list, 1):
            page_no, source = find_tune_page_number(tune_name, hymn_no, dfH, dfTH)
            
            line = f"{i}. ♪ {tune_name}"
            
            if page_no:
                notation_link = getNotation(page_no)
                if notation_link and "http" in str(notation_link):
                    line += f" - [📖 View Notation]({notation_link})"
                else:
                    line += f" - Page {page_no}"
            else:
                line += " - ❌ No notation found"
            
            result_lines.append(line)
        
        result = "\n".join(result_lines)
        await update.message.reply_text(result, parse_mode="Markdown", disable_web_page_preview=True)
    
    # Handle lyrics
    elif song_code.startswith("L-"):
        from telegram_handlers.conversations import get_lyrics_pdf_by_lyric_number, lyrics_file_map, DOWNLOAD_DIR
        from data.sheet_upload import search_uploaded_file_by_lyric, download_uploaded_file
        import os
        
        lyric_number = int(song_code.split('-')[1])
        downloading_msg = await update.message.reply_text("⏳ Downloading music sheet... Please wait.")

        try:
            # First, try to get from main lyrics database
            pdf_path = get_lyrics_pdf_by_lyric_number(lyric_number, lyrics_file_map)

            if pdf_path and os.path.exists(pdf_path):
                # Found in main database
                await downloading_msg.delete()
                
                # Verify file size before sending
                file_size = os.path.getsize(pdf_path)
                if file_size > 50 * 1024 * 1024:  # 50MB limit for Telegram
                    await update.message.reply_text(f"❌ PDF file for {song_code} is too large to send via Telegram.")
                else:
                    with open(pdf_path, 'rb') as pdf_file:
                        await update.message.reply_document(
                            document=pdf_file,
                            filename=f"{song_code}.pdf",
                            caption=f"🎵 Here is the notation for {song_code}."
                        )
                    # Clean up the downloaded file after sending
                    try:
                        os.remove(pdf_path)
                    except:
                        pass  # Ignore cleanup errors
            else:
                # Not found in main database - search in upload folder
                await downloading_msg.edit_text("⏳ Not found in main database. Searching uploaded files...")
                
                found, file_id, filename = search_uploaded_file_by_lyric(lyric_number)
                
                if found:
                    # Found in upload folder - download and send it
                    await downloading_msg.edit_text(f"✅ Found in uploads: {filename}\n⏳ Downloading...")
                    
                    # Download from upload folder
                    upload_pdf_path = download_uploaded_file(file_id, filename, DOWNLOAD_DIR)
                    
                    if upload_pdf_path and os.path.exists(upload_pdf_path):
                        await downloading_msg.delete()
                        
                        # Verify file size before sending
                        file_size = os.path.getsize(upload_pdf_path)
                        if file_size > 50 * 1024 * 1024:  # 50MB limit for Telegram
                            await update.message.reply_text(f"❌ PDF file for {song_code} is too large to send via Telegram.")
                        else:
                            with open(upload_pdf_path, 'rb') as pdf_file:
                                await update.message.reply_document(
                                    document=pdf_file,
                                    filename=filename,
                                    caption=f"📁 Notation for {song_code}\n(From user uploads)"
                                )
                        
                        # Clean up the downloaded file after sending
                        try:
                            os.remove(upload_pdf_path)
                        except:
                            pass  # Ignore cleanup errors
                    else:
                        await downloading_msg.delete()
                        await update.message.reply_text(
                            f"❌ Found file in uploads but could not download it.\n"
                            f"File: {filename}"
                        )
                else:
                    # Not found anywhere
                    await downloading_msg.delete()
                    await update.message.reply_text(
                        f"❌ **Notation Not Found**\n\n"
                        f"{song_code} was not found in:\n"
                        f"• Main notation database\n"
                        f"• User uploaded files\n\n"
                        f"💡 You can upload the notation using /upload command.",
                        parse_mode="Markdown"
                    )
                    
        except Exception as e:
            await downloading_msg.delete()
            await update.message.reply_text(f"❌ Error processing {song_code}: {str(e)}")
    
    # Handle conventions
    elif song_code.startswith("C-"):
        await update.message.reply_text(
            f"❌ Notation for convention songs ({song_code}) is not currently available in the database."
        )
    
    else:
        await update.message.reply_text(
            f"❌ Invalid song code format. Please use H-XX for hymns, L-XX for lyrics, or C-XX for conventions."
        )

async def ai_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle natural language messages using AI to determine intent and execute commands.
    This is called for messages that don't start with / and aren't song codes.
    """
    from utils.ai_assistant import parse_user_intent, should_use_ai
    
    user = update.effective_user
    message_text = update.message.text.strip()
    
    # Check if this message should be processed by AI
    if not should_use_ai(message_text):
        # Let other handlers deal with it
        return
    
    user_logger.info(f"AI processing message from {user.id}: {message_text[:50]}")
    
    # Initialize conversation history if not present
    if 'conversation_history' not in context.user_data:
        context.user_data['conversation_history'] = []
    
    # Get recent conversation history (last 5 messages)
    conversation_history = context.user_data['conversation_history'][-5:]
    
    # Send "thinking" indicator
    await update.message.chat.send_action("typing")
    
    try:
        # Parse user intent with Gemini, including conversation history
        intent = parse_user_intent(message_text, conversation_history)
        
        command = intent.get("command")
        parameters = intent.get("parameters", {})
        response_text = intent.get("response_text", "")
        confidence = intent.get("confidence", 0.0)
        mentioned_entities = intent.get("mentioned_entities", {})
        
        user_logger.info(f"AI Intent: command={command}, confidence={confidence}")
        
        # Store user message in conversation history
        context.user_data['conversation_history'].append({
            'role': 'user',
            'message': message_text,
            'entities': mentioned_entities
        })
        
        # Keep only last 10 messages to prevent memory bloat
        if len(context.user_data['conversation_history']) > 10:
            context.user_data['conversation_history'] = context.user_data['conversation_history'][-10:]
        
        # Send AI response first
        if response_text:
            await update.message.reply_text(response_text)
            # Store bot response in history
            context.user_data['conversation_history'].append({
                'role': 'bot',
                'message': response_text,
                'entities': mentioned_entities
            })
        
        # If no command or low confidence, just give conversational response
        if command is None or confidence < 0.5:
            if not response_text:
                await update.message.reply_text(
                    "I'm not sure what you're looking for. Try asking something like:\n"
                    "• 'What songs were sung on Christmas?'\n"
                    "• 'Find H-44'\n"
                    "• 'Who is the organist?'\n\n"
                    "Or use /help to see all commands!"
                )
            return
        
        # Execute the appropriate command based on AI interpretation
        await execute_ai_command(update, context, command, parameters)
        
    except Exception as e:
        user_logger.error(f"Error in AI handler: {str(e)[:200]}")
        await update.message.reply_text(
            "I had trouble understanding that. You can try:\n"
            "• Using a direct command like /help\n"
            "• Rephrasing your question\n"
            "• Asking something more specific"
        )

async def execute_ai_command(update: Update, context: ContextTypes.DEFAULT_TYPE, command: str, parameters: dict) -> None:
    """Execute the bot command determined by AI"""
    
    try:
        if command == "date":
            # Extract date and call date_input handler
            date_str = parameters.get("date", "")
            if date_str:
                # Store in context and call handler
                context.user_data['expecting_date'] = True
                context.user_data['ai_date_input'] = date_str
                await date_input(update, context)
        
        elif command == "search":
            query = parameters.get("query", "")
            if query:
                await execute_search(update, context, query)
            else:
                await update.message.reply_text("Please specify what you'd like to search for.")
        
        elif command == "rooster":
            # Import and call organist roster handler
            from telegram_handlers.conversations import organist_roster_start
            await organist_roster_start(update, context)
        
        elif command == "last":
            song_code = parameters.get("song_code", "")
            if song_code:
                # Store in context and call handler
                context.user_data['ai_song_input'] = song_code
                await last_sung_input(update, context)
            else:
                await update.message.reply_text("Please use /last followed by a song code (e.g., /last H-44)")
        
        elif command == "check":
            song_code = parameters.get("song_code", "")
            if song_code:
                # Store in context and call handler
                context.user_data['ai_song_input'] = song_code
                await check_song_input(update, context)
            else:
                await update.message.reply_text("Please use /check followed by a song code (e.g., /check H-44)")
        
        elif command == "tune":
            # Get query - could be hymn number or tune name
            query = parameters.get("song_code") or parameters.get("tune_name", "")
            if query:
                await execute_tune_search(update, context, query)
            else:
                await update.message.reply_text("Please specify a hymn number or tune name. Example: 'find tune for H-44' or 'find tune abridge'")
        
        elif command == "theme":
            theme_query = parameters.get("theme", "")
            theme_type = parameters.get("type")  # Optional: 'hymns' or 'lyrics'
            if theme_query:
                await execute_theme_search(update, context, theme_query, theme_type)
            else:
                await update.message.reply_text("Please specify a theme to search for. Example: 'songs with theme peace'")
        
        elif command == "notation":
            song_code = parameters.get("song_code", "")
            if song_code:
                await execute_notation(update, context, song_code)
            else:
                await update.message.reply_text("Please specify a song code. Example: 'get notation for H-44'")
        
        elif command == "bible":
            reference = parameters.get("reference", "")
            if reference:
                # Store in context and call handler
                context.user_data['ai_bible_input'] = reference
                await bible_input_handler(update, context)
            else:
                await update.message.reply_text("Please use /bible followed by a verse reference (e.g., /bible John 3:16)")
        
        elif command == "games":
            from telegram_handlers.conversations import bible_game_start
            await bible_game_start(update, context)
        
        elif command == "download":
            await update.message.reply_text("To download audio, please use /download and paste a YouTube or Spotify link.")
        
        elif command == "help":
            await help_command(update, context)
        
        elif command == "updatesunday":
            from telegram_handlers.conversations import update_sunday_songs
            await update_sunday_songs(update, context)
        
        else:
            await update.message.reply_text(
                f"I understood you want to use '{command}', but I'm not sure how to help with that yet. "
                f"Try using /{command} directly or check /help for available commands."
            )
    
    except Exception as e:
        user_logger.error(f"Error executing AI command '{command}': {str(e)[:200]}")
        await update.message.reply_text(
            f"I had trouble executing that command. Please try using /{command} directly."
        )


async def list_uploads_command(update: Update, context: CallbackContext) -> None:
    """Command to list recently uploaded files (available to all users)"""
    user = update.effective_user
    
    try:
        from data.sheet_upload import list_uploaded_files
        
        status_msg = await update.message.reply_text("📂 Loading uploaded files...")
        
        file_list = list_uploaded_files(limit=10)
        
        await status_msg.edit_text(file_list, parse_mode="Markdown", disable_web_page_preview=True)
        user_logger.info(f"User {user.id} ({user.full_name}) listed uploaded files")
    
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)[:100]}")
        user_logger.error(f"Error in list_uploads_command: {e}")


# --- Notation Availability Commands ---

async def notation_status_command(update: Update, context: CallbackContext) -> None:
    """
    Check the availability status of a specific lyric notation.
    Usage: /notation_status <lyric_number>
    Example: /notation_status 6
    """
    user = update.effective_user
    user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) used /notation_status")
    
    try:
        # Check if a lyric number is provided
        if not context.args:
            await update.message.reply_text(
                "📝 <b>Notation Status Checker</b>\n\n"
                "Usage: /notation_status &lt;lyric_number&gt;\n\n"
                "Example: /notation_status 6\n\n"
                "This will check if the music notation for that lyric is available.",
                parse_mode="HTML"
            )
            return
        
        # Get the lyric number from arguments
        try:
            lyric_num = int(context.args[0])
        except ValueError:
            await update.message.reply_text("❌ Please provide a valid lyric number (e.g., /notation_status 6)")
            return
        
        # Load datasets
        data = get_all_data()
        dfL = data.get('dfL')
        
        if dfL is None:
            await update.message.reply_text("❌ Error: Could not load lyric database")
            return
        
        # Check notation availability
        from utils.notation_checker import Notation_Availability_Checker, Format_Notation_Availability
        notation_name, status = Notation_Availability_Checker(dfL, lyric_num)
        
        # Format and send response
        response = f"<b>L-{lyric_num}</b>\n\n" + Format_Notation_Availability(notation_name, status)
        await update.message.reply_text(response, parse_mode="HTML")
        
        user_logger.info(f"User {user.id} checked notation status for L-{lyric_num}")
    
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)[:150]}")
        user_logger.error(f"Error in notation_status_command: {e}")


async def missing_notations_command(update: Update, context: CallbackContext) -> None:
    """
    Show all known lyrics in the vocabulary that are missing or have pending notations.
    This helps identify which music sheets need to be uploaded.
    Usage: /missing_notations
    """
    user = update.effective_user
    user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) used /missing_notations")
    
    try:
        # Show loading message
        status_msg = await update.message.reply_text("🔍 Analyzing notation statuses...")
        
        # Load datasets
        data = get_all_data()
        dfL = data.get('dfL')
        df = data.get('df')
        dfH = data.get('dfH')
        dfC = data.get('dfC')
        
        if dfL is None or df is None:
            await status_msg.edit_text("❌ Error: Could not load databases")
            return
        
        # Get vocabulary
        vocabulary, _, lyric_vocab, _ = ChoirVocabulary(df, dfH, dfL, dfC)
        
        # Get missing notations
        from utils.notation_checker import Get_Missing_Notations, Format_Missing_Notations
        missing_notations = Get_Missing_Notations(dfL, lyric_vocab)
        
        # Format and send response
        response = Format_Missing_Notations(missing_notations)
        
        # If response is too long, split it
        if len(response) > 4096:
            # Split into chunks
            chunks = [response[i:i+4096] for i in range(0, len(response), 4096)]
            await status_msg.delete()
            for i, chunk in enumerate(chunks):
                if i == 0:
                    await update.message.reply_text(chunk, parse_mode="HTML")
                else:
                    await update.message.reply_text(chunk, parse_mode="HTML")
        else:
            await status_msg.edit_text(response, parse_mode="HTML")
        
        user_logger.info(f"User {user.id} checked missing notations ({len(missing_notations)} missing)")
    
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)[:150]}")
        user_logger.error(f"Error in missing_notations_command: {e}")


async def update_notation_status_command(update: Update, context: CallbackContext) -> None:
    """
    Update the Status field in Lyric List by checking notation database and uploads.
    Admin only command.
    Usage: /update_notation_status
    """
    user = update.effective_user
    
    # Check if user is admin
    if user.id != ADMIN_ID:
        await update.message.reply_text("❌ Admin access required")
        return
    
    user_logger.info(f"Admin {user.full_name} (@{user.username}, ID: {user.id}) used /update_notation_status")
    
    try:
        # Show loading message
        status_msg = await update.message.reply_text("🔄 Updating notation status...\nScanning all sources...")
        
        # Load datasets
        data = get_all_data()
        dfL = data.get('dfL')
        df = data.get('df')
        dfH = data.get('dfH')
        dfC = data.get('dfC')
        
        if dfL is None or df is None:
            await status_msg.edit_text("❌ Error: Could not load databases")
            return
        
        # Get all available lyric numbers from BOTH sources in just 2 fast API calls
        await status_msg.edit_text("🔄 Scanning notation database and upload folder...")
        from data.sheet_upload import get_all_available_lyric_numbers
        all_available, from_uploads, from_notation_db = get_all_available_lyric_numbers()
        
        if not all_available:
            msg = "📁 No lyric files found in either notation database or upload folder.\n\n"
            msg += "Upload files should contain 'L-' followed by a number in the filename.\n"
            msg += "Example: 'L-32 രാജരാജ ദൈവജാതൻ.pdf'"
            await status_msg.edit_text(msg)
            return
        
        # Show what was found
        scan_info = f"📊 Found {len(all_available)} available lyrics:\n"
        scan_info += f"   • Notation Database: {len(from_notation_db)}\n"
        scan_info += f"   • Upload Folder: {len(from_uploads)}\n\n"
        await status_msg.edit_text(scan_info + "🔄 Updating status...")
        
        # Get vocabulary to determine Pending vs Not Available
        from data.vocabulary import ChoirVocabulary
        vocabulary, _, lyric_vocab, _ = ChoirVocabulary(df, dfH, dfL, dfC)
        vocabulary_set = set(lyric_vocab.values)  # Set of lyric numbers in vocabulary
        
        # Update status for ALL lyrics (bidirectional sync)
        updated_to_available = 0
        updated_to_pending = 0
        updated_to_not_available = 0
        already_correct = 0
        updates_list = []
        removals_list = []
        
        for idx, row in dfL.iterrows():
            lyric_num = row['Lyric no']
            current_status = row.get('Status', '')
            is_currently_available = str(current_status).strip() == "Available"
            is_actually_available = lyric_num in all_available
            is_in_vocabulary = lyric_num in vocabulary_set
            
            if is_actually_available and not is_currently_available:
                # File exists but status is not Available → UPDATE TO AVAILABLE
                dfL.at[idx, 'Status'] = 'Available'
                updated_to_available += 1
                from data.datasets import IndexFinder
                lyric_name = IndexFinder(f"L-{lyric_num}")
                
                # Determine source
                source = []
                if lyric_num in from_notation_db:
                    source.append("DB")
                if lyric_num in from_uploads:
                    source.append("Uploads")
                source_str = " + ".join(source)
                
                updates_list.append(f"L-{lyric_num}: {lyric_name} [{source_str}]")
                
            elif not is_actually_available and is_currently_available:
                # Status is Available but file doesn't exist → REMOVE STATUS
                from data.datasets import IndexFinder
                lyric_name = IndexFinder(f"L-{lyric_num}")
                
                if is_in_vocabulary:
                    # In vocabulary → mark as Pending
                    dfL.at[idx, 'Status'] = 'Pending'
                    updated_to_pending += 1
                    removals_list.append(f"L-{lyric_num}: {lyric_name} → Pending (in vocabulary)")
                else:
                    # Not in vocabulary → mark as Not Available
                    dfL.at[idx, 'Status'] = 'Not Available'
                    updated_to_not_available += 1
                    removals_list.append(f"L-{lyric_num}: {lyric_name} → Not Available")
                
            else:
                # Status already correct
                already_correct += 1
        
        total_updated = updated_to_available + updated_to_pending + updated_to_not_available
        
        # Save updated dfL back to Google Drive
        if total_updated > 0:
            await status_msg.edit_text(f"💾 Saving {total_updated} updates to Google Drive...")
            from data.datasets import save_lyric_list_to_drive
            
            if save_lyric_list_to_drive(dfL):
                # Count current status distribution
                available_count = len(dfL[dfL['Status'] == 'Available'])
                pending_count = len(dfL[dfL['Status'] == 'Pending'])
                not_available_count = len(dfL[dfL['Status'] == 'Not Available'])
                
                # Build response message
                response = (
                    f"✅ <b>Notation Status Synchronized!</b>\n\n"
                    f"📊 <b>Scan Results:</b>\n"
                    f"• Notation Database: {len(from_notation_db)} files\n"
                    f"• Upload Folder: {len(from_uploads)} files\n"
                    f"• Total Available: {len(all_available)} unique lyrics\n\n"
                    f"📝 <b>Changes Made:</b>\n"
                    f"• Already Correct: {already_correct}\n"
                    f"• Marked Available: {updated_to_available}\n"
                    f"• Marked Pending: {updated_to_pending}\n"
                    f"• Marked Not Available: {updated_to_not_available}\n"
                    f"• Total Changes: {total_updated}\n\n"
                    f"✅ <b>Current Status Distribution:</b>\n"
                    f"• Available: {available_count}\n"
                    f"• Pending: {pending_count}\n"
                    f"• Not Available: {not_available_count}\n\n"
                )
                
                # Show additions
                if updated_to_available > 0:
                    if updated_to_available <= 10:
                        response += f"<b>➕ Marked as Available:</b>\n"
                        for item in updates_list:
                            response += f"• {item}\n"
                    else:
                        response += f"<b>➕ Marked as Available (first 10):</b>\n"
                        for item in updates_list[:10]:
                            response += f"• {item}\n"
                        response += f"... and {updated_to_available - 10} more\n"
                    response += "\n"
                
                # Show removals
                if updated_to_pending + updated_to_not_available > 0:
                    removal_count = updated_to_pending + updated_to_not_available
                    if removal_count <= 10:
                        response += f"<b>➖ Status Changed (files removed):</b>\n"
                        for item in removals_list:
                            response += f"• {item}\n"
                    else:
                        response += f"<b>➖ Status Changed (first 10):</b>\n"
                        for item in removals_list[:10]:
                            response += f"• {item}\n"
                        response += f"... and {removal_count - 10} more\n"
                
                await status_msg.edit_text(response, parse_mode="HTML")
                user_logger.info(f"Admin {user.id} synchronized {total_updated} notation statuses "
                               f"(+{updated_to_available} available, {updated_to_pending} pending, "
                               f"{updated_to_not_available} not available)")
            else:
                await status_msg.edit_text("❌ Error: Failed to save updates to Google Drive")
        else:
            # Count current status distribution
            available_count = len(dfL[dfL['Status'] == 'Available'])
            pending_count = len(dfL[dfL['Status'] == 'Pending'])
            not_available_count = len(dfL[dfL['Status'] == 'Not Available'])
            
            response = (
                f"✅ <b>All Status Fields are Correct!</b>\n\n"
                f"📊 <b>Scan Results:</b>\n"
                f"• Notation Database: {len(from_notation_db)} files\n"
                f"• Upload Folder: {len(from_uploads)} files\n"
                f"• Total Available: {len(all_available)} unique lyrics\n\n"
                f"📝 <b>Current Status Distribution:</b>\n"
                f"• Available: {available_count}\n"
                f"• Pending: {pending_count}\n"
                f"• Not Available: {not_available_count}\n\n"
                f"No changes needed - everything is in sync! ✨"
            )
            await status_msg.edit_text(response, parse_mode="HTML")
    
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)[:150]}")
        user_logger.error(f"Error in update_notation_status_command: {e}")
        import traceback
        traceback.print_exc()


# === MIDI to Video Converter Command ===

async def midi_command(update: Update, context: CallbackContext) -> None:
    """
    Handle /midi command to convert MIDI files to Synthesia-style videos
    Accepts a MIDI file from the user and returns a video with falling notes animation
    """
    user = update.effective_user
    user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) used /midi command")
    
    # Check authorization
    if not await is_authorized(update):
        return
    
    try:
        # Check if user sent a file
        if update.message.document:
            document = update.message.document
            
            # Check if user sent a file
            if not (document.file_name.lower().endswith('.mid') or document.file_name.lower().endswith('.midi')):
                await update.message.reply_text(
                    "❌ Please send a valid MIDI file (.mid or .midi extension)\n\n"
                    "Example: Upload a .mid file and I'll create a Synthesia-style video!"
                )
                return
            
            # Check file size (limit to 10MB for cloud deployment)
            if document.file_size > 10 * 1024 * 1024:
                await update.message.reply_text(
                    "❌ File too large! Please send a MIDI file smaller than 10MB.\n\n"
                    "💡 Tip: Shorter songs (3-5 minutes) work best in the cloud environment."
                )
                return
            
            # Send processing message
            status_msg = await update.message.reply_text(
                "🎹 Processing your MIDI file...\n"
                "This may take a few minutes depending on the length of the song.\n\n"
                "⏳ Step 1/3: Downloading MIDI file..."
            )
            
            # Download the MIDI file
            import tempfile
            import os
            
            temp_dir = tempfile.mkdtemp()
            midi_file_path = os.path.join(temp_dir, document.file_name)
            output_video_path = os.path.join(temp_dir, f"{os.path.splitext(document.file_name)[0]}.mp4")
            
            try:
                file = await context.bot.get_file(document.file_id)
                await file.download_to_drive(midi_file_path)
                
                await status_msg.edit_text(
                    "🎹 Processing your MIDI file...\n\n"
                    "✅ Step 1/3: MIDI file downloaded\n"
                    "⏳ Step 2/3: Converting to video (this may take 3-8 minutes)...\n\n"
                    "💡 Please be patient, cloud processing takes time!"
                )
                
                # Convert MIDI to video with timeout protection for cloud deployment
                from utils.midi_converter import convert_midi_to_video
                import asyncio
                
                # Use cloud-optimized settings (lower resolution and fps for faster processing)
                # This helps stay within Streamlit Cloud's resource limits
                try:
                    # Run conversion in executor to avoid blocking
                    loop = asyncio.get_event_loop()
                    success = await loop.run_in_executor(
                        None,
                        lambda: convert_midi_to_video(
                            midi_path=midi_file_path,
                            output_path=output_video_path,
                            width=960,   # 960x540 (16:9 aspect ratio, cloud-optimized)
                            height=540,
                            fps=24,      # 24fps for faster processing and smaller file size
                            include_audio=True
                        )
                    )
                except asyncio.TimeoutError:
                    await status_msg.edit_text(
                        "❌ Conversion timed out. Your MIDI file might be too complex or too long.\n\n"
                        "Please try:\n"
                        "• A shorter MIDI file (under 4 minutes)\n"
                        "• A simpler MIDI arrangement"
                    )
                    return
                except Exception as conv_error:
                    await status_msg.edit_text(
                        f"❌ Conversion error: {str(conv_error)[:150]}\n\n"
                        "This might be due to cloud resource limits. Try a shorter/simpler MIDI file."
                    )
                    user_logger.error(f"MIDI conversion error for user {user.id}: {conv_error}")
                    return
                
                if not success:
                    await status_msg.edit_text(
                        "❌ Failed to convert MIDI to video. The file might be corrupted or empty.\n\n"
                        "Please try another MIDI file."
                    )
                    return
                
                await status_msg.edit_text(
                    "🎹 Processing your MIDI file...\n\n"
                    "✅ Step 1/3: MIDI file downloaded\n"
                    "✅ Step 2/3: Video generated successfully\n"
                    "⏳ Step 3/3: Uploading video to Telegram..."
                )
                
                # Check if video file exists and has reasonable size
                if not os.path.exists(output_video_path):
                    await status_msg.edit_text("❌ Video file was not generated. Please try again.")
                    return
                
                video_size = os.path.getsize(output_video_path)
                if video_size > 50 * 1024 * 1024:  # 50MB Telegram limit
                    await status_msg.edit_text(
                        "❌ Generated video is too large for Telegram (>50MB).\n\n"
                        "Please try a shorter MIDI file."
                    )
                    return
                
                # Send the video
                with open(output_video_path, 'rb') as video_file:
                    await update.message.reply_video(
                        video=video_file,
                        caption=(
                            f"🎹 <b>Synthesia Video Generated!</b>\n\n"
                            f"📄 File: {document.file_name}\n"
                            f"📊 Video Size: {video_size / (1024*1024):.2f} MB\n\n"
                            f"Enjoy your piano visualization! 🎵"
                        ),
                        parse_mode="HTML",
                        supports_streaming=True
                    )
                
                await status_msg.edit_text(
                    "✅ <b>Complete!</b>\n\n"
                    "Your Synthesia-style video has been generated and sent successfully! 🎉",
                    parse_mode="HTML"
                )
                
                user_logger.info(f"Successfully converted MIDI to video for user {user.id}: {document.file_name}")
                
            except Exception as e:
                await status_msg.edit_text(
                    f"❌ Error during conversion: {str(e)[:200]}\n\n"
                    "Please try again or contact the administrator if the problem persists."
                )
                user_logger.error(f"Error converting MIDI for user {user.id}: {e}")
                import traceback
                traceback.print_exc()
            finally:
                # Clean up temporary files
                import shutil
                try:
                    if os.path.exists(temp_dir):
                        shutil.rmtree(temp_dir)
                except Exception as cleanup_error:
                    user_logger.warning(f"Failed to clean up temp directory {temp_dir}: {cleanup_error}")
        
        else:
            # No file attached, show instructions
            await update.message.reply_text(
                "🎹 <b>MIDI to Synthesia Video Converter</b>\n\n"
                "Send me a MIDI file (.mid or .midi) and I'll create a beautiful "
                "Synthesia-style piano visualization with falling notes and audio!\n\n"
                "📋 <b>How to use:</b>\n"
                "1. Simply send a MIDI file to the bot\n"
                "2. Wait while I process it (typically 2-5 minutes)\n"
                "3. Receive your video with piano animation!\n\n"
                "⚠️ <b>Cloud Deployment Limits:</b>\n"
                "• Max MIDI file size: 10 MB\n"
                "• Max output video size: 50 MB\n"
                "• Recommended song length: 3-5 minutes\n"
                "• Video output: 960x540 @ 24fps (optimized for cloud)\n\n"
                "💡 <b>Best results:</b> Use MIDI files with clear piano parts and moderate length.\n\n"
                "🎵 Try it now by uploading a MIDI file!",
                parse_mode="HTML"
            )
    
    except Exception as e:
        await update.message.reply_text(f"❌ Unexpected error: {str(e)[:150]}")
        user_logger.error(f"Error in midi_command: {e}")
        import traceback
        traceback.print_exc()


async def handle_midi_file(update: Update, context: CallbackContext) -> None:
    """
    Handle MIDI files sent directly without the /midi command
    """
    # If user sends a MIDI file, process it automatically
    if update.message.document:
        document = update.message.document
        if document.file_name.lower().endswith('.mid') or document.file_name.lower().endswith('.midi'):
            # Call the midi_command handler
            await midi_command(update, context)
