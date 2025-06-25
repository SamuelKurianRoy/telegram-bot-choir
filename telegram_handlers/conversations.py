# telegram/conversations.py
# ConversationHandler states and flows
import pandas as pd
import streamlit as st
from telegram import Update, ReplyKeyboardRemove, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext, ConversationHandler, ContextTypes
from config import get_config
from logging_utils import setup_loggers
# Import isVocabulary from the appropriate module
from data.vocabulary import ChoirVocabulary, isVocabulary, standardize_hlc_value
from utils.search import find_best_match, search_index
from utils.notation import Music_notation_link, getNotation
from data.datasets import Tunenofinder, Tune_finder_of_known_songs, Datefinder, IndexFinder, Hymn_Tune_no_Finder, get_all_data
import re
import os
import requests
from data.drive import get_drive_service, append_download_to_google_doc, get_docs_service
from datetime import datetime
import io
from telegram_handlers.handlers import is_authorized
from downloader import AudioDownloader
import logging
from telegram.constants import ParseMode

DOWNLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'tmp')
HYMN_FOLDER_URL = f'https://drive.google.com/drive/folders/{get_config().H_SHEET_MUSIC}'
drive_service = get_drive_service()
file_map = {}
bot_logger, user_logger = setup_loggers()

# Define authorized_users globally for use in all handlers
authorized_users_str = st.secrets["AUTHORIZED_USERS"]
authorized_users = list(map(int, authorized_users_str.split(','))) if authorized_users_str else []

# Downloader feature flag
DOWNLOADER_AVAILABLE = True

# --- Conversation States ---
# Example: CHECK_SONG, ENTER_SONG, etc.
# TODO: Define all necessary states for conversations

# --- Conversation Flows ---
# TODO: Implement conversation entry points and state handlers for each major conversation 

print("Reached Telegram Bot code")
 

#Telegram bot
 
 
 
#/check

 



 #/notation

ASK_HYMN_NO = range(1)


# Function to send notation images
def normalize_tune(tune):
     return re.sub(r'[^a-z0-9]', '', tune.lower())


# === EXTRACT FOLDER ID ===
def extract_folder_id(folder_url):
     match = re.search(r'/folders/([a-zA-Z0-9_-]+)', folder_url)
     if match:
         return match.group(1)
     raise ValueError("Invalid folder URL")
 
 # === FETCH ALL IMAGE FILES ===
def get_image_files_from_folder(folder_url):
     folder_id = extract_folder_id(folder_url)
     file_map = {}
     page_token = None
 
     while True:
         response = drive_service.files().list(
             q=f"'{folder_id}' in parents and mimeType contains 'image/' and trashed = false",
             fields="nextPageToken, files(id, name)",
             pageToken=page_token
         ).execute()
 
         for file in response.get('files', []):
             try:
                 page_num = int(file['name'].split('.')[0])
                 file_map[page_num] = file['id']
             except ValueError:
                 continue  # Skip files that don't start with a number
 
         page_token = response.get('nextPageToken', None)
         if page_token is None:
             break
 
     # Remove or comment out any print statements that output file_map keys or numbers
     return file_map
 
 # === DOWNLOAD IMAGE ===
def download_image(file_id, filename):
    url = f"https://drive.google.com/uc?id={file_id}"
    response = requests.get(url)
    if response.status_code == 200:
        save_path = os.path.join(DOWNLOAD_DIR, filename)
        with open(save_path, 'wb') as f:
            f.write(response.content)
        return save_path
    else:
        return None
 
 # === GET IMAGE FOR PAGE ===
def get_image_by_page(page_number, file_map):
     page_number = int(page_number)
     if page_number in file_map:
         file_id = file_map[page_number]
         filename = f"{page_number}.jpg"
         return download_image(file_id, filename)
     else:
         return None
 
 # === MAIN EXECUTION ===
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
file_map = get_image_files_from_folder(HYMN_FOLDER_URL)



def Music_notation_downloader(hymnno, file_map): 
    if isinstance(hymnno, str) and hymnno.upper().startswith('H-'):
        hymnno = hymnno[2:]
    hymnno = int(hymnno)
    results = {}
    
    # Get tunes for the hymn
    tunes_str = dfH["Tunes"][hymnno - 1]
    tune_names = [t.strip() for t in tunes_str.split(',')]

    for tune_name in tune_names:
        # Check if the exact tune is present for this hymn
        tune_matches = dfTH[(dfTH["Hymn no"] == hymnno) & (dfTH["Tune Index"].str.contains(tune_name, na=False))]

        if not tune_matches.empty:
            page_str = str(tune_matches["Page no"].values[0]).split(',')[0]
            image_path = get_image_by_page(page_str, file_map)
            results[tune_name] = image_path or "Page not found"
        else:
            # Search in entire dataset for the tune
            found = False
            for idx, row in dfTH.iterrows():
                tune_indices = [ti.strip() for ti in str(row["Tune Index"]).split(',')]
                if tune_name in tune_indices:
                    page_str = str(row["Page no"]).split(',')[0]
                    image_path = get_image_by_page(page_str, file_map)
                    results[tune_name] = image_path or "Page not found"
                    found = True
                    break
            if not found:
                results[tune_name] = "Notation not found"

    return results




def filter_hymns_by_theme(data, theme=None):
    """
    Filters the DataFrame for rows where the "Themes" column contains the given theme.
    """
    filtered = data[data["Themes"].str.contains(theme, case=False, na=False)]
    return filtered



async def send_notation_image(update: Update, context: ContextTypes.DEFAULT_TYPE, tune_name: str, song_id: str):
    chat_id = update.effective_chat.id
    Song_id = standardize_hlc_value(song_id)
    hymnno = int(Song_id.replace("H-", "").strip())
    normalized_target = normalize_tune(tune_name)

    matched_row = None

    # === 1. Try to find it in the same hymn number
    data = get_all_data()
    dfTH = data["dfTH"]
    subset_df = dfTH[dfTH["Hymn no"] == hymnno]
    for _, row in subset_df.iterrows():
        tune_list = [normalize_tune(t.strip()) for t in str(row["Tune Index"]).split(",")]
        if normalized_target in tune_list:
            matched_row = row
            break

    # === 2. Global fallback if not found
    if matched_row is None:
        for _, row in dfTH.iterrows():
            tune_list = [normalize_tune(t.strip()) for t in str(row["Tune Index"]).split(",")]
            if normalized_target in tune_list:
                matched_row = row
                break

    # === 3. If still not found
    if matched_row is None:
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Could not find notation page for '{tune_name}' in {song_id}.")
        return

    # === 4. Parse page numbers
    raw_page_value = str(matched_row["Page no"])
    page_numbers = [p.strip() for p in raw_page_value.split(",") if p.strip().isdigit()]

    if not page_numbers:
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Invalid or missing page number for {tune_name} ({song_id})")
        return

    sent_any = False
    for page in page_numbers:
        filename = f"{page}.jpg"
        file_path = os.path.join(DOWNLOAD_DIR, filename)

        if not os.path.exists(file_path):
            # Try to download the image from Google Drive
            downloaded_path = get_image_by_page(page, file_map)
            if downloaded_path and os.path.exists(downloaded_path):
                file_path = downloaded_path
            else:
                await context.bot.send_message(chat_id=chat_id, text=f"❌ Image could not be found or downloaded.")
                sent_any = True
                continue

        try:
            with open(file_path, 'rb') as photo:
                await context.bot.send_photo(chat_id=chat_id, photo=photo, caption=f"{tune_name}")
            sent_any = True
        except Exception as e:
            await context.bot.send_message(chat_id=chat_id, text=f"❌ Failed to send image: {e}")
            sent_any = True


# /notation command handler
async def notation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❗ Usage: /notation <SongID> (e.g. /notation H-86)")
        return

    song_id = standardize_hlc_value(" ".join(context.args).strip())

    tunes = Tune_finder_of_known_songs(song_id)
    if not tunes or tunes == "Invalid Number":
        await update.message.reply_text(f"❌ No known tunes found for {song_id}")
        return

    if isinstance(tunes, str):
        tune_list = [t.strip() for t in tunes.split(",") if t.strip()]
    else:
        await update.message.reply_text("⚠️ Could not parse tunes.")
        return

    if not tune_list:
        await update.message.reply_text("🎵 No tunes available.")
        return

    # Create inline buttons: callback_data format "notation:tune|song_id"
    keyboard = [
        [InlineKeyboardButton(tune, callback_data=f"notation:{tune}|{song_id}")]
        for tune in tune_list
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"🎶 Select a tune for {song_id}:", reply_markup=reply_markup
    )
async def start_notation(update: Update, context: ContextTypes.DEFAULT_TYPE):
   await update.message.reply_text("📖 Please enter the hymn number (e.g. H-86):")
   return ASK_HYMN_NO

async def receive_hymn_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    song_id = standardize_hlc_value(update.message.text.strip())

    tunes = Tune_finder_of_known_songs(song_id)
    if not tunes or tunes == "Invalid Number":
        await update.message.reply_text(f"❌ No known tunes found for {song_id}. Try again or type /cancel to stop.")
        return ASK_HYMN_NO

    if isinstance(tunes, str):
        tune_list = [t.strip() for t in tunes.split(",") if t.strip()]
    else:
        await update.message.reply_text("⚠️ Could not parse tunes.")
        return ConversationHandler.END

    if not tune_list:
        await update.message.reply_text("🎵 No tunes available.")
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton(tune, callback_data=f"notation:{tune}|{song_id}")]
        for tune in tune_list
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"🎶 Select a tune for {song_id}:", reply_markup=reply_markup
    )
    return ConversationHandler.END



# Callback handler for button press
async def handle_notation_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not query.data.startswith("notation:"):
        return

    try:
        data = query.data.replace("notation:", "")
        tune_name, song_id = data.split("|", 1)
    except ValueError:
        await query.edit_message_text("⚠️ Invalid callback format.")
        return

    # Send the image using the fixed function
    await send_notation_image(update, context, tune_name.strip(), song_id.strip())



  
#/last

# States
ENTER_LAST_SONG, ASK_SHOW_ALL = range(2)

# Download command states
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
         return ENTER_LAST_SONG
 
     song_type, _, song_number = user_input.partition('-')
 
     if song_type not in ['H', 'L', 'C'] or not song_number.isdigit():
         await update.message.reply_text("❌ Invalid code. Use H-, L-, or C- followed by a number (e.g. H-27).")
         return ENTER_LAST_SONG
 
     full_song = f"{song_type}-{song_number}"
     context.user_data["last_category"] = song_type
     context.user_data["last_song"] = full_song
 
     # Get last sung date
     result = Datefinder(full_song, song_type, first=True)
     await update.message.reply_text(result)
 
     # Ask if user wants all dates
     reply_keyboard = [["Yes", "No"]]
     await update.message.reply_text(
         "Would you like to see all the dates on which this song was sung?",
         reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True)
     )
     return ASK_SHOW_ALL
 
# Handle "show all dates?" step
async def last_sung_show_all(update: Update, context: CallbackContext) -> int:
     reply = update.message.text.strip().lower()
     category = context.user_data.get("last_category")
     full_song = context.user_data.get("last_song")
 
     if reply == "yes":
         result = Datefinder(full_song, category, first=False)
         await update.message.reply_text(result, reply_markup=ReplyKeyboardRemove())
     else:
         await update.message.reply_text(
             "May the music stay in your heart 🎵\n(❁´◡`❁)\n<b><i>S.D.G</i></b>",
             parse_mode="HTML",
             reply_markup=ReplyKeyboardRemove()
         )
 
     return ConversationHandler.END


# /download command handlers
async def download_start(update: Update, context: CallbackContext) -> int:
    """Start the download conversation"""
    user = update.effective_user
    user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) used /download")

    if not DOWNLOADER_AVAILABLE:
        await update.message.reply_text(
            "❌ Audio download feature is not available. Please contact the administrator.",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END

    if not await is_authorized(update):
        user_logger.warning(f"Unauthorized access attempt to /download by {user.full_name} (@{user.username}, ID: {user.id})")
        return ConversationHandler.END

    await update.message.reply_text(
        "🎵 *Audio Downloader*\n\n"
        "Please send me a YouTube or Spotify link to download the audio.\n\n"
        "*Supported platforms:*\n"
        "• YouTube (youtube.com, youtu.be)\n"
        "• Spotify (spotify.com)\n"
        "• SoundCloud (soundcloud.com)\n\n"
        "Just paste the link and I'll download the audio for you!",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove()
    )
    return ENTER_URL

async def download_url_input(update: Update, context: CallbackContext) -> int:
    """Handle URL input for download"""
    user_input = update.message.text.strip()
    user = update.effective_user

    # Initialize downloader
    downloader = AudioDownloader()

    # Check if URL is supported
    if not downloader.is_supported_url(user_input):
        await update.message.reply_text(
            "❌ This URL is not supported. Please send a YouTube, Spotify, or SoundCloud link.",
            reply_markup=ReplyKeyboardRemove()
        )
        return ENTER_URL

    # Store URL in context
    context.user_data["download_url"] = user_input
    context.user_data["platform"] = downloader.detect_platform(user_input)

    # Show quality selection
    quality_keyboard = [
        ["🔥 High Quality (320kbps)", "🎵 Medium Quality (192kbps)"],
        ["💾 Low Quality (128kbps)", "❌ Cancel"]
    ]

    await update.message.reply_text(
        f"🎯 *{context.user_data['platform']} link detected!*\n\n"
        "Please select the audio quality:",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(quality_keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return SELECT_QUALITY

async def download_quality_selection(update: Update, context: CallbackContext) -> int:
    """Handle quality selection and start download"""
    quality_text = update.message.text.strip()
    user = update.effective_user

    # Map quality selection
    quality_map = {
        "🔥 High Quality (320kbps)": "high",
        "🎵 Medium Quality (192kbps)": "medium",
        "💾 Low Quality (128kbps)": "low"
    }

    if quality_text == "❌ Cancel":
        await update.message.reply_text(
            "❌ Download cancelled.",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END

    if quality_text not in quality_map:
        await update.message.reply_text(
            "❌ Invalid selection. Please choose a quality option.",
            reply_markup=ReplyKeyboardMarkup([
                ["🔥 High Quality (320kbps)", "🎵 Medium Quality (192kbps)"],
                ["💾 Low Quality (128kbps)", "❌ Cancel"]
            ], one_time_keyboard=True, resize_keyboard=True)
        )
        return SELECT_QUALITY

    quality = quality_map[quality_text]
    url = context.user_data.get("download_url")
    platform = context.user_data.get("platform")

    # Start download process
    await update.message.reply_text(
        f"🎵 Starting download from {platform}...\n"
        f"Quality: {quality_text}\n\n"
        "This may take a few minutes. Please wait...",
        reply_markup=ReplyKeyboardRemove()
    )

    try:
        # Log download request to Google Doc (similar to comment function)
        yfile_id = st.secrets["YFILE_ID"]
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        chat_id = update.effective_chat.id

        download_request_entry = f"{timestamp} - {user.full_name} (@{user.username}, ID: {user.id}, ChatID: {chat_id}) requested download:\nPlatform: {platform} | Quality: {quality} | URL: {url}\n\n"

        if yfile_id:
            append_download_to_google_doc(yfile_id, download_request_entry)

        # Initialize downloader
        downloader = AudioDownloader()

        # Download the audio
        result = await downloader.download_audio(url, quality)

        if result is None:
            # Log failed download to Google Doc
            download_failed_entry = f"{timestamp} - DOWNLOAD FAILED for {user.full_name} (@{user.username}, ID: {user.id}):\nPlatform: {platform} | Quality: {quality} | URL: {url}\n\n"

            if yfile_id:
                append_download_to_google_doc(yfile_id, download_failed_entry)

            await update.message.reply_text(
                "❌ Download failed. Please try again or contact the administrator."
            )
            return ConversationHandler.END

        file_path, file_info = result

        # Send the audio file
        await update.message.reply_text(
            f"✅ Download completed!\n\n"
            f"🎵 *{file_info['title']}*\n"
            f"👤 *Artist:* {file_info['artist']}\n"
            f"📱 *Platform:* {file_info['platform']}\n"
            f"📊 *Size:* {file_info['size_mb']:.1f} MB\n\n"
            "Sending file...",
            parse_mode="Markdown"
        )

        # Send the audio file
        with open(file_path, 'rb') as audio_file:
            await update.message.reply_audio(
                audio=audio_file,
                title=file_info['title'],
                performer=file_info['artist'],
                duration=file_info.get('duration', 0)
            )

        # Log successful download
        user_logger.info(f"Download completed for {user.full_name} ({user.id}): {file_info['title']}")

        # Log successful download to Google Doc
        download_success_entry = f"{timestamp} - DOWNLOAD SUCCESS for {user.full_name} (@{user.username}, ID: {user.id}):\nTitle: {file_info['title']} | Artist: {file_info['artist']} | Platform: {file_info['platform']} | Size: {file_info['size_mb']:.1f}MB | Quality: {quality}\nURL: {url}\n\n"

        if yfile_id:
            append_download_to_google_doc(yfile_id, download_success_entry)

        # Clean up the file
        downloader.cleanup_file(file_path)

        await update.message.reply_text(
            "🎉 Audio sent successfully!\n\n"
            "Send another link to download more audio, or use /cancel to stop."
        )

        return ENTER_URL  # Allow user to download another file

    except Exception as e:
        bot_logger.error(f"Download error for user {user.id}: {e}")

        # Log error to Google Doc
        download_error_entry = f"{timestamp} - DOWNLOAD ERROR for {user.full_name} (@{user.username}, ID: {user.id}):\nPlatform: {platform} | Quality: {quality} | Error: {str(e)}\nURL: {url}\n\n"

        if yfile_id:
            append_download_to_google_doc(yfile_id, download_error_entry)

        await update.message.reply_text(
            "❌ An error occurred during download. Please try again later."
        )
        return ConversationHandler.END


# Telegram command handler for /tune command

# States for ConversationHandler
CHOOSE_METHOD, GET_INPUT = range(2)
 
# Store user input temporarily
user_input_method = {}
 
# Start the tune command conversation
async def tune_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) sent /tune")

    # Ask user how they want to search
    reply_keyboard = [["Hymn Number", "Tune Name"]]
    await update.message.reply_text(
        "How would you like to search?",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True),
    )
    return CHOOSE_METHOD

 
# Handle the choice
async def choose_method(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
     choice = update.message.text.lower()
     user_input_method[update.effective_user.id] = choice
 
     if choice == "hymn number":
         await update.message.reply_text("Please enter the hymn number:")
     elif choice == "tune name":
         await update.message.reply_text("Please enter the tune name (or part of it):")
     else:
         await update.message.reply_text("Invalid choice. Please type /tune to start over.")
         return ConversationHandler.END
 
     return GET_INPUT
 
# Handle the actual search
async def get_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    method = user_input_method.get(user_id)
    user_input = update.message.text.strip()

    data = get_all_data()
    dfTH = data["dfTH"]

    if method == "hymn number":
        result = Tunenofinder(user_input)  # Your existing hymn number search
    elif method == "tune name":
        result_df = Hymn_Tune_no_Finder(dfTH, user_input, top_n=10)
        result = "Top matching hymns:\n" + "\n".join(
            f"H-{int(row['Hymn no'])}: Tune: {row['Tune Index']}, \t \t Similarity: {row['Similarity']:.2f}"
            for _, row in result_df.iterrows()
        )
    else:
        result = "Something went wrong. Please try again with /tune."

    await update.message.reply_text(result)
    return ConversationHandler.END


 
 
#/search command
SEARCH_METHOD, INDEX_CATEGORY, INDEX_TEXT, NUMBER_CATEGORY, NUMBER_INPUT = range(5)
 
# --- Entry point ---
async def search_start(update: Update, context: CallbackContext) -> int:
     user = update.effective_user
     user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) started /search")
 
     keyboard = [["By Index", "By Number"]]
     reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
     await update.message.reply_text("How would you like to search?", reply_markup=reply_markup)
     return SEARCH_METHOD
 
# --- Choose method: By Index or By Number ---
async def search_method_choice(update: Update, context: CallbackContext) -> int:
     method = update.message.text.strip().lower()
     user = update.effective_user
 
     if method == "by index":
         user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) chose to search by index (text query)")
         keyboard = [["Hymn", "Lyric", "Convention"]]
         reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
         await update.message.reply_text("Please select the category for your text search:", reply_markup=reply_markup)
         return INDEX_CATEGORY
 
     elif method == "by number":
         user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) chose to search by number (index)")
         keyboard = [["Hymn", "Lyric", "Convention"]]
         reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
         await update.message.reply_text("Please select the category:", reply_markup=reply_markup)
         return NUMBER_CATEGORY
 
     else:
         await update.message.reply_text("Invalid choice. Please choose 'By Index' or 'By Number'.")
         return SEARCH_METHOD
 
# --- For 'By Index': Choose category ---
async def search_index_category(update: Update, context: CallbackContext) -> int:
     category = update.message.text.strip().lower()
 
     if category not in ["hymn", "lyric", "convention"]:
         await update.message.reply_text("Invalid choice. Please select either 'Hymn', 'Lyric' or 'Convention'.")
         return INDEX_CATEGORY
 
     context.user_data["index_search_category"] = category
     await update.message.reply_text("Now, please type your search text:", reply_markup=ReplyKeyboardRemove())
     return INDEX_TEXT
 
# --- For 'By Index': Enter search text ---
async def search_by_index(update: Update, context: CallbackContext) -> int:
    user = update.effective_user
    category = context.user_data.get("index_search_category")
    query = update.message.text.strip()

    result = find_best_match(query, category)

    # If result is an error message (string), return it directly
    if isinstance(result, str):
        await update.message.reply_text(result)
        return ConversationHandler.END

    matches, column_label = result

    # Map category to prefix
    prefix_map = {
        "hymn": "H-",
        "lyric": "L-",
        "convention": "C-"
    }

    label_clean = category.capitalize()
    prefix = prefix_map.get(category, "")

    # Optional: Filter out zero similarity matches (if desired)
    # matches = [m for m in matches if m[1] > 0]

    reply_lines = [f"Top {len(matches)} matches for '{query}' in {category}:\n"]
    for i, (num, score, context_text) in enumerate(matches, 1):
        line = f"{i}. {prefix}{num}: {IndexFinder(f'{prefix}{num}')} (Similarity: {score:.3f})"
        if context_text and str(context_text).strip().lower() != "none":
            line += f" — {context_text.strip()}"
        reply_lines.append(line)

    reply = "\n".join(reply_lines)
    await update.message.reply_text(reply)

    user_logger.info(
        f"{user.full_name} (@{user.username}, ID: {user.id}) searched by index: {query} in {category}"
    )
    return ConversationHandler.END


 
# --- For 'By Number': Choose category ---
async def search_number_category(update: Update, context: CallbackContext) -> int:
     category = update.message.text.strip().lower()
 
     if category not in ["hymn", "lyric", "convention"]:
         await update.message.reply_text("Invalid choice. Please select either 'Hymn', 'Lyric' or 'Convention'.")
         return NUMBER_CATEGORY
 
     context.user_data["number_search_category"] = category
     await update.message.reply_text("Please enter the index number:", reply_markup=ReplyKeyboardRemove())
     return NUMBER_INPUT
 
# --- For 'By Number': Enter index number ---
async def search_by_number(update: Update, context: CallbackContext) -> int:
     user = update.effective_user
     category = context.user_data.get("number_search_category")
     text = update.message.text.strip()
 
     try:
         index_num = int(text)
     except ValueError:
         await update.message.reply_text("Index must be an integer. Please enter a valid index number:")
         return NUMBER_INPUT
 
     result = search_index(index_num, category)
     tune= f"\nTunes: {Tunenofinder(index_num)}" if category == 'hymn' else ''
     await update.message.reply_text(f"Search result of {category[0].upper()}-{index_num} : {result}{tune}")
     user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) searched by number: {index_num} in {category}")
     return ConversationHandler.END
 
 
CATEGORY_SELECTION, EXPORT_CONFIRMATION = range(2)
ADMIN_ID = int(st.secrets["ADMIN_ID"])

async def start_vocabulary(update: Update, context: CallbackContext) -> int:
    user = update.effective_user

    if user.id not in authorized_users: # Notify admin about unauthorized access /vocabulary
     await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=(
            f"📢 <b>User accessed /vocabulary</b>\n\n"
            f"<b>Name:</b> {user.full_name}\n"
            f"<b>Username:</b> @{user.username}\n"
            f"<b>User ID:</b> <code>{user.id}</code>"
        ),
        parse_mode="HTML"
    )

    user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) started /vocabulary")

    keyboard = [
        ["Full Vocabulary", "Hymn Vocabulary"],
        ["Lyric Vocabulary", "Convention Vocabulary"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)

    await update.message.reply_text(
        "📚 Please choose a vocabulary category:", reply_markup=reply_markup
    )
    return CATEGORY_SELECTION



# Step 2: Process category selection and show preview
async def category_selection(update: Update, context: CallbackContext) -> int:
    user = update.effective_user
    user_choice = update.message.text.strip()

    if user_choice not in get_vocabulary_categories():
        await update.message.reply_text("⚠️ Invalid choice. Please use /vocabulary again.")
        return CATEGORY_SELECTION

    data = get_vocabulary_categories()[user_choice]

    # Clean up the data
    if isinstance(data, pd.Series):
        data = data.to_frame(name="Value")
        data = data[data["Value"].astype(str).str.strip() != '']
        # Add index/tune columns for single vocabularies
        if user_choice == "Hymn Vocabulary":
            data["Hymn Index"] = data["Value"].apply(lambda x: IndexFinder(f"H-{x}") if str(x).strip() else "")
            data["Hymn Tune"] = data["Value"].apply(lambda x: Tune_finder_of_known_songs(f"H-{x}") if str(x).strip() else "")
        elif user_choice == "Lyric Vocabulary":
            data["Lyric Index"] = data["Value"].apply(lambda x: IndexFinder(f"L-{x}") if str(x).strip() else "")
        elif user_choice == "Convention Vocabulary":
            data["Convention Index"] = data["Value"].apply(lambda x: IndexFinder(f"C-{x}") if str(x).strip() else "")
    elif user_choice == "Full Vocabulary":
        data = data[(data != 0).any(axis=1)]
        # Add index/tune columns for full vocabulary
        data["Hymn Index"] = data["Hymn no"].apply(lambda x: IndexFinder(f"H-{x}") if str(x).strip() else "")
        data["Hymn Tune"] = data["Hymn no"].apply(lambda x: Tune_finder_of_known_songs(f"H-{x}") if str(x).strip() else "")
        data["Lyric Index"] = data["Lyric no"].apply(lambda x: IndexFinder(f"L-{x}") if str(x).strip() else "")
        data["Convention Index"] = data["Convention no"].apply(lambda x: IndexFinder(f"C-{x}") if str(x).strip() else "")
        # Reorder columns to match old output
        data = data[[
            "Hymn no", "Hymn Index", "Hymn Tune",
            "Lyric no", "Lyric Index",
            "Convention no", "Convention Index"
        ]]

    # Create and send the Excel file directly
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        data.to_excel(writer, sheet_name="Vocabulary", index=False)
    output.seek(0)

    filename = f"{user_choice}.xlsx"
    await update.message.reply_document(
        document=output,
        filename=filename,
        caption=f"📂 Here is your '{user_choice}' vocabulary in Excel format.",
        reply_markup=ReplyKeyboardRemove()
    )

    user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) downloaded vocabulary: {user_choice}.")
    return ConversationHandler.END


 
#/theme

# Define unique conversation states:
THEME_SELECTION = 1
YEAR_FILTER = 2

# Step 1: List available unique themes and prompt user
async def filter_theme(update: Update, context: CallbackContext) -> int:
    """
    Lists available unique themes and prompts the user to choose.
    Splits comma-separated themes and flattens the list.
    """
    user = update.effective_user
    user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) sent /theme")

    # Get unique themes from the DataFrame, splitting by comma if necessary
    data = get_all_data()
    dfH = data["dfH"]
    all_themes = dfH["Themes"].dropna().str.split(",").explode().str.strip().unique()
    themes = sorted(all_themes)

    # Build keyboard layout (2 themes per row)
    keyboard = [themes[i:i+2] for i in range(0, len(themes), 2)]

    await update.message.reply_text(
        "🎯 *Available Themes:*\nPlease select or type one of the themes below:",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    )

    return THEME_SELECTION

 # Helper function to send long messages in chunks
async def send_long_message(update, message_parts, parse_mode="Markdown", max_length=3500):
    """
    Sends a message, splitting it into multiple messages if it's too long.
    """
    full_message = "\n\n".join(message_parts)

    if len(full_message) <= max_length:
        await update.message.reply_text(
            full_message,
            parse_mode=parse_mode,
            reply_markup=ReplyKeyboardRemove()
        )
    else:
        # Split into chunks
        current_chunk = ""
        for part in message_parts:
            if len(current_chunk + "\n\n" + part) <= max_length:
                if current_chunk:
                    current_chunk += "\n\n" + part
                else:
                    current_chunk = part
            else:
                # Send current chunk
                if current_chunk:
                    await update.message.reply_text(
                        current_chunk,
                        parse_mode=parse_mode,
                        reply_markup=ReplyKeyboardRemove()
                    )
                current_chunk = part

        # Send remaining chunk
        if current_chunk:
            await update.message.reply_text(
                current_chunk,
                parse_mode=parse_mode,
                reply_markup=ReplyKeyboardRemove()
            )

# Step 2: Process the theme selection
async def handle_theme_selection(update: Update, context: CallbackContext) -> int:
    """
    Handles the user's theme selection by filtering the hymns,
    displays them grouped as known/unknown, and then asks
    if the user wants to filter by year.
    """
    theme_input = update.message.text.strip()
    # Save theme in user_data for later
    context.user_data["theme_input"] = theme_input

    data = get_all_data()
    dfH = data["dfH"]
    df = data["df"]
    dfL = data["dfL"]
    dfC = data["dfC"]
    # Compute Hymn_Vocabulary dynamically
    _, Hymn_Vocabulary, _, _ = ChoirVocabulary(df, dfH, dfL, dfC)

    filtered_df = filter_hymns_by_theme(dfH, theme_input)

    if filtered_df.empty:
        await update.message.reply_text(
            f"😕 No hymns found for theme: *{theme_input}*",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END

    # Instead of storing formatted strings, store raw hymn numbers.
    known_hymns = []
    unknown_hymns = []

    for _, row in filtered_df.iterrows():
        hymn_no = row["Hymn no"]
        if hymn_no in Hymn_Vocabulary.values:
            known_hymns.append(hymn_no)
        else:
            unknown_hymns.append(hymn_no)

    # Build display lines for known and unknown hymns (show ALL, no limits)
    display_known = [f"H-{h} - {dfH[dfH['Hymn no'] == h]['Hymn Index'].values[0]} - {dfH[dfH['Hymn no'] == h]['Tunes'].values[0]}" for h in known_hymns]
    display_unknown = [f"H-{h} - {dfH[dfH['Hymn no'] == h]['Hymn Index'].values[0]}" for h in unknown_hymns]

    message_parts = [f"🎼 *Hymns related to theme:* `{theme_input}`"]

    if display_known:
        message_parts.append(f"✅ *Choir Knows ({len(known_hymns)} total):*\n" + "\n".join(display_known))
    else:
        message_parts.append("❌ *No known hymns found in this theme.*")

    if display_unknown:
        message_parts.append(f"❌ *Choir Doesn't Know ({len(unknown_hymns)} total):*\n" + "\n".join(display_unknown) +
                             "\n\n*Note:* A known song may appear here if not sung in the past 3 years.")
    else:
        message_parts.append("🎉 *Choir knows all hymns in this theme!*")

    # Use the helper function to send the message (will split automatically if too long)
    await send_long_message(update, message_parts)

    # Store the raw hymn numbers for later processing in year filtering
    context.user_data["known_hymns"] = known_hymns
    context.user_data["unknown_hymns"] = unknown_hymns

    # Ask the user if they want to filter by year
    await update.message.reply_text(
        "📅 Do you want to filter these hymns to see Songs Sung this year?",
        reply_markup=ReplyKeyboardMarkup([["Yes", "No"]], one_time_keyboard=True, resize_keyboard=True)
    )
    return YEAR_FILTER

# Step 3: Ask the user if they want year filtering
async def handle_year_filter(update: Update, context: CallbackContext) -> int:
    reply = update.message.text.strip().lower()
    if reply != "yes":
        await update.message.reply_text("Okay! No year filtering applied.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    s_year = datetime.now().year  # Automatically get current year

    data = get_all_data()
    dfH = data["dfH"]

    def get_last_sung_date(hymn_code):
        result = Datefinder(songs=hymn_code, first=True)
        if result and len(result) >= 10:
            try:
                return datetime.strptime(result[-10:], "%d/%m/%Y")
            except:
                return None
        return None

    # Group by year: Expect hymn_list to contain raw hymn numbers.
    def group_by_year(hymn_list):
        sung, not_sung = [], []
        for h in hymn_list:
            hymn_code = f"H-{h}"
            date_obj = get_last_sung_date(hymn_code)
            # Retrieve hymn index from DataFrame
            index = dfH[dfH['Hymn no'] == h]['Hymn Index'].values[0]
            tune = dfH[dfH['Hymn no'] == h]['Tunes'].values[0]
            if date_obj and date_obj.year == s_year:
                sung.append(f"{hymn_code} - {index}  -{tune}")
            else:
                not_sung.append(f"{hymn_code} - {index} -{tune}")
        return sung, not_sung

    # Retrieve stored hymn numbers and theme from user_data
    known = context.user_data.get("known_hymns", [])
    unknown = context.user_data.get("unknown_hymns", [])
    theme = context.user_data.get("theme_input", "")

    sung_known, not_sung_known = group_by_year(known)
    # For unknown hymns, only the "not sung" part is needed.
    not_sung_unknown = group_by_year(unknown)[1]

    message_parts = [f"📅 *Theme:* `{theme}` – *Year:* {s_year}"]

    if sung_known:
        message_parts.append(f"✅ *Songs that were Sung ({len(sung_known)} total):*\n" + "\n".join(sung_known))

    if not_sung_known:
        message_parts.append(f"❌ *Songs that were Not Sung ({len(not_sung_known)} total):*\n" + "\n".join(not_sung_known))

    if not_sung_unknown:
        message_parts.append(f"🚫 *Songs Choir Doesn't Know ({len(not_sung_unknown)} total):*\n" + "\n".join(not_sung_unknown))

    # Use the helper function to send the message (will split automatically if too long)
    await send_long_message(update, message_parts)
    return ConversationHandler.END
 
# Add this function to periodically upload logs
async def periodic_log_upload():
    """Periodically upload logs to Google Drive."""
    # Get interval from environment variable or use default (1 hour)
    try:
        interval_seconds = int(os.environ.get("LOG_UPLOAD_INTERVAL", 3600))
    except ValueError:
        interval_seconds = 3600  # Default to 1 hour if not a valid integer

    minutes = interval_seconds // 60
    bot_logger.info(f"Periodic log upload scheduled every {minutes} minutes")

    while True:
        try:
            # Wait for the specified interval
            await asyncio.sleep(interval_seconds)

            # Check if we should still be running
            if not bot_should_run or check_stop_signal():
                break

            # Log the upload attempt
            bot_logger.info(f"Performing scheduled log upload (every {minutes} minutes)")

            # Upload logs to Google Drive
            try:
                upload_log_to_google_doc(st.secrets["BFILE_ID"], "bot_log.txt")
                upload_log_to_google_doc(st.secrets["UFILE_ID"], "user_log.txt")

                # Also upload downloader log if it exists
                if os.path.exists("downloader_log.txt"):
                    upload_log_to_google_doc(st.secrets["BFILE_ID"], "downloader_log.txt")
                    bot_logger.info("Downloader log uploaded to BFILE_ID")

                # Note: Download logs are directly appended to YFILE_ID Google Doc, no file upload needed
                bot_logger.info("Scheduled log upload completed successfully")
            except Exception as e:
                bot_logger.error(f"Scheduled log upload failed: {e}")

        except asyncio.CancelledError:
            # Task was cancelled
            break
        except Exception as e:
            bot_logger.error(f"Error in periodic log upload task: {e}")
            # Wait a bit before retrying
            await asyncio.sleep(60)

async def cancel(update: Update, context: CallbackContext) -> int:
    user = update.effective_user
    user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) sent /cancel")
    await update.message.reply_text("Operation canceled.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

 
 


 #Song Info Function
async def handle_song_code(update: Update, context: CallbackContext) -> None:
    data = get_all_data()
    df = data["df"]
    dfH = data["dfH"]
    dfL = data["dfL"]
    dfC = data["dfC"]
    dfTH = data["dfTH"]
    user_input_raw = update.message.text
    user_input = standardize_hlc_value(user_input_raw)
    song_type, _, song_number = user_input.partition('-')

    # Validate basic format again if needed
    if song_type not in ['H', 'L', 'C'] or not song_number.isdigit():
        return  # Ignore bad formats silently

    response_parts = []

    # Get Name/Index info
    Vocabulary = ChoirVocabulary(df, dfH, dfL, dfC)[0]
    song_info = isVocabulary(user_input, Vocabulary, dfH, dfTH, Tune_finder_of_known_songs)
    if 'not found' not in song_info:
        response_parts.append(f"🎵 <b>Song Info:</b> {song_info}")
        last_sung = Datefinder(user_input, song_type, first=True)
        response_parts.append(f"🗓️ <b>Last Sung:</b> {last_sung}")
    else:
        from data.datasets import IndexFinder
        response_parts.append(f"Choir doesn't know {f'{user_input}: {IndexFinder(user_input)}'}")

    # Send the reply
    await update.message.reply_text(
        "\n".join(response_parts),
        parse_mode="HTML", disable_web_page_preview=True
    )

# Add a new function to run the bot asynchronously
async def run_bot_async():
    """Runs the bot asynchronously."""
    try:
        await main()
    except Exception as e:
        bot_logger.error(f"Error in bot: {e}")
        global bot_should_run
        bot_should_run = False

# Add a function to stop the bot
def stop_bot():
    """Stops the bot gracefully."""
    global bot_should_run
    bot_should_run = False
    bot_logger.info("Bot stop requested")
    return True
    



 #/comment

COMMENT, REPLY = range(2)

# Step 1: Command to start commenting
async def start_comment(update: Update, context: CallbackContext) -> int:
    user = update.effective_user
    user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) started commenting.")
    
    # Ask user to provide their comment
    await update.message.reply_text(
        "Please type your comment, recommendation, or thoughts below. You can also type /cancel to exit."
    )
    return COMMENT
 



async def process_comment(update: Update, context: CallbackContext) -> int:
    user = update.effective_user
    comment = update.message.text.strip()

    admin_id = st.secrets["ADMIN_ID"]
    comfile_id = st.secrets["COMFILE_ID"]  # Google Doc ID to store comments

    # Build the full comment message
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    user_id = user.id
    chat_id = update.effective_chat.id
    comment_entry = f"{timestamp} - {user.full_name} (@{user.username}, ID: {user.id}, ChatID: {chat_id}) said:\n{comment}\n\n"

    # Send comment to admin with an inline button
    if admin_id:
        try:
            admin_id = int(admin_id)

            # Creating an inline button for replying
            reply_button = InlineKeyboardButton(
                text="Reply to User",
                callback_data=f"reply_{chat_id}"  # Encodes the chat_id in callback_data
            )
            reply_markup = InlineKeyboardMarkup([[reply_button]])

            # Send message with the inline button
            await context.bot.send_message(
                admin_id,
                f"📝 New comment from User:\n\n"
                f"{comment}\n\n"
                f"👉 Click the button below to reply to this user.",
                reply_markup=reply_markup
            )
        except ValueError:
            logging.error("Invalid admin ID in environment variables.")

    # Append comment to Google Doc
    try:
        docs_service = get_docs_service()
        doc = docs_service.documents().get(documentId=comfile_id).execute()
        end_index = doc.get("body").get("content")[-1].get("endIndex", 1)
        requests = [{
            "insertText": {
                "location": {"index": end_index - 1},
                "text": comment_entry
            }
        }]
        docs_service.documents().batchUpdate(
            documentId=comfile_id,
            body={"requests": requests}
        ).execute()
        print("✅ Comment appended to Google Doc.")
    except Exception as e:
        logging.error(f"❌ Failed to append comment to Google Doc ({comfile_id}): {e}")

    # Confirm to the user
    await update.message.reply_text("✅ Thank you for your feedback! We appreciate your thoughts.")

    # Log user's comment
    user_logger.info(f"Comment from {user.full_name} (@{user.username}, ID: {user.id}): {comment}")

    return ConversationHandler.END


# Function to handle the reply action when button is clicked
async def reply_to_user(update: Update, context: CallbackContext) -> int:
    """Sends the actual reply to the user."""
    query = update.callback_query
    await query.answer()

    data = query.data
    target_user_id = int(data.split("_")[1])

    context.user_data["target_user_id"] = target_user_id

    await query.message.reply_text(
        f"✏️ Type your reply to the User",
        parse_mode=ParseMode.HTML
    )

    return REPLY
 


 
async def send_reply_to_user(update: Update, context: CallbackContext) -> int:
    """Handles sending the admin's reply after they type the message."""
    user_message = update.message.text
    target_user_id = context.user_data.get("target_user_id")

    if not target_user_id:
        await update.message.reply_text("❌ No target user found to send the reply.")
        return ConversationHandler.END

    try:
        await context.bot.send_message(
            chat_id=target_user_id,
            text=f"💬 Admin's reply:\n\n{user_message}",
            parse_mode=ParseMode.HTML
        )
        await update.message.reply_text("✅ Your reply has been sent to the user.")
    except Exception as e:
        logging.error(f"❌ Failed to send reply: {e}")
        await update.message.reply_text(f"❌ Failed to send reply: {e}")

    return ConversationHandler.END


 # Admin reply function (keeps your original implementation)
async def admin_reply(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    admin_id = int(st.secrets["ADMIN_ID"])

    if user.id != admin_id:
        await update.message.reply_text("❌ You are not authorized to use this command.")
        return

    try:
        args = context.args
        if len(args) < 2:
            await update.message.reply_text("Usage: /reply <user_id> <your message>")
            return

        target_user_id = int(args[0])
        reply_message = " ".join(args[1:])

        await context.bot.send_message(
            chat_id=target_user_id,
            text=f"💬 Admin's reply:\n\n{reply_message}",
            parse_mode=ParseMode.HTML
        )

        await update.message.reply_text(f"✅ Reply sent to user {target_user_id}.")
    except Exception as e:
        logging.error(f"❌ Failed to send reply: {e}")
        await update.message.reply_text(f"❌ Failed to send reply: {e}")



 

# Step 3: Handle /cancel if the user wants to exit
async def cancel_comment(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text("Comment process has been canceled.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END






# Placeholder for file_map, should be loaded at startup or on demand
# TODO: Populate this with actual mapping from page number to file_id

# Dynamically compute vocabulary categories for export
from data.vocabulary import ChoirVocabulary
from data.datasets import get_all_data

def get_vocabulary_categories():
    data = get_all_data()
    df = data["df"]
    dfH = data["dfH"]
    dfL = data["dfL"]
    dfC = data["dfC"]
    Vocabulary, Hymn_Vocabulary, Lyric_Vocabulary, Convention_Vocabulary = ChoirVocabulary(df, dfH, dfL, dfC)
    return {
        "Full Vocabulary": Vocabulary,
        "Hymn Vocabulary": Hymn_Vocabulary,
        "Lyric Vocabulary": Lyric_Vocabulary,
        "Convention Vocabulary": Convention_Vocabulary,
    }

