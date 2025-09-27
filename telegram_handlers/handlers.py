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
from datetime import date
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
        "• **/cancel**\n"
        "  - *Description:* Cancels the current operation.\n"
        "  - *Example:* If you are in a conversation, type `/cancel` to stop it.\n\n"
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

    # Check if user is admin
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

    user_logger.info(f"Admin {user.full_name} (@{user.username}, ID: {user.id}) used /refresh")

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
        dfH, dfL, dfC, yr23, yr24, yr25, df, dfTH, dfTD = load_datasets()
        yrDataPreprocessing()
        dfcleaning()
        df = standardize_song_columns()

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
            # Show tunes for hymns
            songs_text = "\n".join(
                f"{i + 1}. {s} - {IndexFinder(s)}{get_tune_info(s)}" for i, s in enumerate(valid_songs)
            )
        else:
            # Don't show tunes
            songs_text = "\n".join(
                f"{i + 1}. {s} - {IndexFinder(s)}" for i, s in enumerate(valid_songs)
            )

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
            "• Or ask the user to send /start and check the logs"
        )
        return

    try:
        target_user_id = int(context.args[0])

        from data.udb import set_user_authorization, get_user_by_id, is_user_authorized

        # Check if user is already authorized
        if is_user_authorized(target_user_id):
            await update.message.reply_text(f"ℹ️ User Already Authorized\n\nUser ID {target_user_id} is already in the authorized users list.")
            return

        # Add user to authorized list
        success = set_user_authorization(target_user_id, authorized=True)

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

                success_text = f"✅ User Authorized Successfully!\n\n"
                success_text += f"User Details:\n"
                success_text += f"• Name: {safe_name}\n"
                success_text += f"• Username: {safe_username}\n"
                success_text += f"• ID: {target_user_id}\n\n"
                success_text += f"This user can now access restricted bot features."
            else:
                success_text = f"✅ User Authorized Successfully!\n\n"
                success_text += f"User ID: {target_user_id}\n\n"
                success_text += f"User record created and authorized. They can now access restricted bot features."

            await update.message.reply_text(success_text)
            user_logger.info(f"Admin {user.id} authorized user {target_user_id}")
        else:
            await update.message.reply_text("❌ Failed to authorize user\n\nThere was an error updating the database.")

    except ValueError:
        await update.message.reply_text("❌ Invalid User ID\n\nPlease provide a valid numeric user ID.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error authorizing user: {str(e)}")
        user_logger.error(f"Error in admin_add_authorized_user: {e}")

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
        user_list = "👥 **All Users in Database**\n\n"
        
        # Add summary
        total_users = len(db)
        authorized_users = len(db[db['is_authorized'] == True])
        admin_users = len(db[db['is_admin'] == True])
        
        user_list += f"📊 **Summary:**\n"
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
            
            # Format name and escape special characters for Markdown
            if name != 'N/A' and name:
                # Escape special Markdown characters
                name_display = str(name).replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace(']', '\\]').replace('`', '\\`')
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
            
            user_list += f"{idx:2d}. {status_icons}**{name_display}**\n"
            user_list += f"    ID: <a href=\"tg://user?id={user_id}\">{user_id}</a> | @{username_display.replace('@', '')}\n"
            user_list += f"    Last seen: {last_seen_display}\n\n"
        
        # Add note if there are more users
        if total_users > max_users:
            user_list += f"... and {total_users - max_users} more users\n\n"
        
        user_list += "**Usage:**\n"
        user_list += "• Use `/add_authorized_user <user_id>` to authorize a user\n"
        user_list += "• Use `/remove_authorized_user <user_id>` to remove authorization\n"
        user_list += "• Copy user IDs from this list for authorization commands"

        # Split message if too long (Telegram limit is 4096 characters)
        if len(user_list) > 4000:
            # Split into chunks
            chunks = []
            current_chunk = "👥 **All Users in Database**\n\n"
            current_chunk += f"📊 **Summary:**\n"
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
                    # Escape special Markdown characters
                    name_display = str(name).replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace(']', '\\]').replace('`', '\\`')
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
                
                user_entry = f"{idx:2d}. {status_icons}**{name_display}**\n"
                user_entry += f"    ID: <a href=\"tg://user?id={user_id}\">{user_id}</a> | @{username_display.replace('@', '')}\n"
                user_entry += f"    Last seen: {last_seen_display}\n\n"
                
                # Check if adding this user would exceed limit
                if len(current_chunk + user_entry) > 4000:
                    chunks.append(current_chunk)
                    current_chunk = f"👥 **All Users (Part {len(chunks) + 1})**\n\n"
                
                current_chunk += user_entry
            
            if current_chunk:
                chunks.append(current_chunk)
            
            # Send each chunk
            for i, chunk in enumerate(chunks):
                if i == len(chunks) - 1:  # Last chunk
                    chunk += "**Usage:**\n"
                    chunk += "• Use `/add_authorized_user <user_id>` to authorize a user\n"
                    chunk += "• Use `/remove_authorized_user <user_id>` to remove authorization\n"
                    chunk += "• Copy user IDs from this list for authorization commands"
                
            try:
                await update.message.reply_text(chunk, parse_mode="HTML")
            except Exception as parse_error:
                # Fallback to plain text if HTML parsing fails
                plain_chunk = chunk.replace('**', '').replace('*', '').replace('<a href="tg://user?id=', '').replace('">', ': ').replace('</a>', '')
                await update.message.reply_text(plain_chunk)
        else:
            try:
                await update.message.reply_text(user_list, parse_mode="HTML")
            except Exception as parse_error:
                # Fallback to plain text if HTML parsing fails
                plain_list = user_list.replace('**', '').replace('*', '').replace('<a href="tg://user?id=', '').replace('">', ': ').replace('</a>', '')
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

**Feature Control:**
• `/disable <feature> [reason]` - Disable a bot feature
• `/enable <feature>` - Enable a bot feature
• `/restrict_access <feature> [reason]` - Restrict to authorized users only
• `/unrestrict_access <feature>` - Remove access restriction
• `/feature_status` - View all feature statuses
• `/debug_features` - Debug feature loading (troubleshooting)
• `/add_missing_features` - Add missing features to Database
• `/restore_all_features` - Restore all 11 features (fix missing features)

**User Management:**
• `/admin_save_db` - Manually save user database to Google Drive
• `/users` - View all users with names and IDs
• `/view_authorized_users` - View all authorized users
• `/add_authorized_user <user_id>` - Add user to authorized list
• `/remove_authorized_user <user_id>` - Remove user from authorized list

**Bot Management:**
• `/refresh` - Reload all datasets from Google Drive
• `/dnstest` - Test DNS resolution and network connectivity
• `/reply <message>` - Reply to user comments/feedback
• `/list` - Show this admin commands list

**General Commands (also available to admin):**
• `/start` - Welcome message and user tracking
• `/help` - Show general bot help
• `/notation` - Get sheet music notation
• `/bible` - Bible verse lookup
• `/games` - Bible quiz games
• `/date` - Check songs sung on specific dates
• `/vocabulary` - Access choir vocabulary
• `/search` - Search songs by various criteria
• `/tune` - Find tune information
• `/last` - Check when songs were last sung
• `/check` - Get song details
• `/theme` - Search by themes
• `/download` - Download audio from links
• `/comment` - Send feedback to admin
• `/setting` - Manage personal settings

**Usage Examples:**
• `/admin_user_info 757438955`
• `/reply Thanks for your feedback!`
• `/admin_users`
"""

        await update.message.reply_text(admin_commands, parse_mode="Markdown")
        user_logger.info(f"Admin {user.id} viewed admin commands list")

    except Exception as e:
        await update.message.reply_text(f"❌ Error retrieving admin commands: {str(e)}")
        user_logger.error(f"Error in admin_list_commands: {e}")

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

            feature_display = feature_info['name']

            status_text += f"{enabled_icon}{restricted_icon} **{feature_display}**\n"
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
        status_text += "• `/feature_status` - View this status\n\n"
        status_text += "**Legend:**\n"
        status_text += "✅ = Enabled, ❌ = Disabled, 🔒 = Restricted to authorized users"

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