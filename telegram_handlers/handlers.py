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
from data.udb import track_user_interaction, user_exists, get_user_by_id, get_user_stats, get_user_summary, save_user_database, track_user_fast, save_if_pending
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
    user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) used /refresh")
    config = get_config()

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

#Admin reply

async def admin_reply(update: Update, context: CallbackContext) -> None:
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
    await update.message.reply_text(
        "📅 Please enter a date (DD/MM/YYYY, DD/MM, or DD):",
        reply_markup=ReplyKeyboardRemove()
    )
    return ASK_DATE

async def date_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    input_date = update.message.text.strip()
    result = get_songs_by_date(input_date)
    if isinstance(result, dict):
        # Split into two messages as requested
        # First message: Just the status message without the colon
        first_message = result['message'].rstrip(':')
        await update.message.reply_text(first_message, parse_mode='Markdown')

        # Second message: Date and songs list
        songs_text = "\n".join(
            f"{i + 1}. {s} - {IndexFinder(s)}" for i, s in enumerate(result["songs"])
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
        "*Note:* If no language is specified, Malayalam will be used by default."
    )
    
    await update.message.reply_text(welcome_text, parse_mode="Markdown")
    return BIBLE_INPUT

async def bible_input_handler(update: Update, context: CallbackContext) -> int:
    """Handle book, chapter, and optional language input"""
    try:
        user_input = update.message.text.strip()
        parts = user_input.split()
        language = 'malayalam'  # default
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

async def admin_users_stats(update: Update, context: CallbackContext) -> None:
    """Admin command to view user database statistics"""
    user = update.effective_user

    # Check if user is admin
    if user.id != ADMIN_ID:
        await update.message.reply_text("❌ Admin access required")
        return

    try:
        stats = get_user_stats()

        stats_text = f"""
📊 **User Database Statistics**

👥 **Total Users:** {stats['total_users']}
✅ **Authorized Users:** {stats['authorized_users']}
👑 **Admin Users:** {stats['admin_users']}
🟢 **Active Users:** {stats['active_users']}

Use /admin_user_info <user_id> to view specific user details.
"""

        await update.message.reply_text(stats_text, parse_mode="Markdown")
        user_logger.info(f"Admin {user.id} viewed user database statistics")

    except Exception as e:
        await update.message.reply_text(f"❌ Error retrieving user statistics: {str(e)}")
        user_logger.error(f"Error in admin_users_stats: {e}")

async def admin_user_info(update: Update, context: CallbackContext) -> None:
    """Admin command to view specific user information"""
    user = update.effective_user

    # Check if user is admin
    if user.id != ADMIN_ID:
        await update.message.reply_text("❌ Admin access required")
        return

    # Check if user_id was provided
    if not context.args:
        await update.message.reply_text("❌ Please provide a user ID. Usage: /admin_user_info <user_id>")
        return

    try:
        target_user_id = int(context.args[0])
        user_summary = get_user_summary(target_user_id)

        await update.message.reply_text(user_summary, parse_mode="Markdown")
        user_logger.info(f"Admin {user.id} viewed info for user {target_user_id}")

    except ValueError:
        await update.message.reply_text("❌ Invalid user ID. Please provide a numeric user ID.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error retrieving user information: {str(e)}")
        user_logger.error(f"Error in admin_user_info: {e}")

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

**User Management:**
• `/admin_users` - View user database statistics
• `/admin_user_info <user_id>` - View specific user details
• `/admin_save_db` - Manually save user database

**Bot Management:**
• `/refresh` - Reload all datasets from Google Drive
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