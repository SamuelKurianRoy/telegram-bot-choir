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
import pandas as pd
from datetime import date

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

    # Check authorization
    authorized_users_str = st.secrets["AUTHORIZED_USERS"]
    authorized_users = list(map(int, authorized_users_str.split(','))) if authorized_users_str else []

    if user.id not in authorized_users:
        # Notify admin but do NOT block user
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
 
     help_text = (
    "🎵 *Choir Song Bot Help*\n\n"
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
"  - *Example:* Type `/tune` and choose either *Hymn Number* or *Tune Index*, then enter your query (e.g. `Whit` or `29`).\n\n"
"• **/notation**\n"
"  - *Description:* Interactive notation lookup. Start by typing `/notation`, and the bot will ask you for a hymn or lyric number (e.g. `H-86` or `L-222`). You can enter multiple hymn or lyric numbers one after another, and for hymns, select a tune to view the notation. Type `/cancel` to stop.\n"
"  - *Example:* Type `/notation`, then enter a hymn number like `H-86` or a lyric number like `L-222`, and follow the prompts.\n\n"
"• **/theme**\n"
"  - *Description:* Initiates an interactive theme filter. You will be presented with a list of unique themes (collected from all comma-separated entries in the database), and you can select or type a theme to display the hymns related to it.\n"
"  - *Example:* Type `/theme` and choose from the displayed themes, or type a custom theme like `Additional Hymns`.\n\n"
"• **/date**\n"
"  - *Description:* Interactive date lookup. Start by typing `/date`, and the bot will ask you to enter a date (DD/MM/YYYY, DD/MM, or DD). You can enter multiple dates one after another to see the songs sung on those dates, until you type `/cancel` to stop.\n"
"  - *Example:* Type `/date`, then enter a date like `05/04/2024`, and keep entering dates as needed.\n\n"
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

     await update.message.reply_text(help_text, parse_mode="Markdown")

#Refresh
 
async def refresh_command(update: Update, context: CallbackContext) -> None:
    # Move imports here to avoid circular import
    import telegram_handlers.conversations as conversations
    from telegram_handlers.conversations import fetch_lyrics_file_map, LYRICS_FOLDER_URL

    user = update.effective_user
    user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) used /refresh")
    config = get_config()
    try:
        # Reload datasets
        dfH, dfL, dfC, yr23, yr24, yr25, df, dfTH, dfTD = load_datasets()
        yrDataPreprocessing()
        dfcleaning()
        df = standardize_song_columns()
        # Refresh lyrics_file_map
        conversations.lyrics_file_map = fetch_lyrics_file_map(LYRICS_FOLDER_URL)
        # Upload logs
        upload_log_to_google_doc(config.BFILE_ID, "bot_log.txt")
        upload_log_to_google_doc(config.UFILE_ID, "user_log.txt")
        await update.message.reply_text("Datasets and lyrics file map reloaded successfully!")
    except Exception as e:
        await update.message.reply_text(f"Error reloading datasets: {e}")

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
        songs_text = "\n".join(
            f"{i + 1}. {s} - {IndexFinder(s)}" for i, s in enumerate(result["songs"])
        )
        response = f"{result['message']}:\n\n{songs_text}"
    else:
        response = result
    await update.message.reply_text(response, parse_mode='Markdown')
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