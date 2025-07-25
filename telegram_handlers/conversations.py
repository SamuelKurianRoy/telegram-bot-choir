# telegram/conversations.py
# ConversationHandler states and flows
import pandas as pd
import streamlit as st
from telegram import Update, ReplyKeyboardRemove, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext, ConversationHandler, ContextTypes
from config import get_config
from logging_utils import setup_loggers
from PyPDF2 import PdfMerger
import tempfile
# Import isVocabulary from the appropriate module
from data.vocabulary import ChoirVocabulary, isVocabulary, standardize_hlc_value
from utils.search import find_best_match, search_index
from utils.notation import Music_notation_link, getNotation
from data.datasets import Tunenofinder, Tune_finder_of_known_songs, Datefinder, IndexFinder, Hymn_Tune_no_Finder, get_all_data
from telegram_handlers.utils import get_wordproject_url_from_input, extract_bible_chapter_text, clean_bible_text
from data.drive import save_game_score, get_user_best_score, get_user_best_scores_all_difficulties, get_leaderboard, get_combined_leaderboard
import re
import os
import random
import requests
from data.drive import get_drive_service, append_download_to_google_doc, get_docs_service, get_all_users
from datetime import datetime
import io
from telegram_handlers.handlers import is_authorized
from config import get_config
from downloader import AudioDownloader
import logging
import asyncio
from telegram.constants import ParseMode


DOWNLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'tmp')
HYMN_FOLDER_URL = f'https://drive.google.com/drive/folders/{get_config().H_SHEET_MUSIC}'
drive_service = get_drive_service()
file_map = {}
bot_logger, user_logger = setup_loggers()

# Bible Game Data
BIBLE_VERSES = {
    "Easy": [
        {"reference": "John 3:16", "book": "john", "chapter": 3, "verse": 16},
        {"reference": "Genesis 1:1", "book": "genesis", "chapter": 1, "verse": 1},
        {"reference": "Psalm 23:1", "book": "psalms", "chapter": 23, "verse": 1},
        {"reference": "Romans 3:23", "book": "romans", "chapter": 3, "verse": 23},
        {"reference": "Romans 6:23", "book": "romans", "chapter": 6, "verse": 23},
        {"reference": "Ephesians 2:8", "book": "ephesians", "chapter": 2, "verse": 8},
        {"reference": "1 John 1:9", "book": "1 john", "chapter": 1, "verse": 9},
        {"reference": "Matthew 28:19", "book": "matthew", "chapter": 28, "verse": 19},
        {"reference": "Acts 1:8", "book": "acts", "chapter": 1, "verse": 8},
        {"reference": "Philippians 4:13", "book": "philippians", "chapter": 4, "verse": 13},
    ],
    "Medium": [
        {"reference": "Isaiah 53:5", "book": "isaiah", "chapter": 53, "verse": 5},
        {"reference": "Jeremiah 29:11", "book": "jeremiah", "chapter": 29, "verse": 11},
        {"reference": "Proverbs 3:5", "book": "proverbs", "chapter": 3, "verse": 5},
        {"reference": "2 Timothy 3:16", "book": "2 timothy", "chapter": 3, "verse": 16},
        {"reference": "Hebrews 11:1", "book": "hebrews", "chapter": 11, "verse": 1},
        {"reference": "James 1:17", "book": "james", "chapter": 1, "verse": 17},
        {"reference": "1 Peter 5:7", "book": "1 peter", "chapter": 5, "verse": 7},
        {"reference": "Galatians 2:20", "book": "galatians", "chapter": 2, "verse": 20},
        {"reference": "Colossians 3:23", "book": "colossians", "chapter": 3, "verse": 23},
        {"reference": "1 Thessalonians 5:16", "book": "1 thessalonians", "chapter": 5, "verse": 16},
    ],
    "Hard": [
        {"reference": "Habakkuk 2:4", "book": "habakkuk", "chapter": 2, "verse": 4},
        {"reference": "Malachi 3:10", "book": "malachi", "chapter": 3, "verse": 10},
        {"reference": "Zephaniah 3:17", "book": "zephaniah", "chapter": 3, "verse": 17},
        {"reference": "Nahum 1:7", "book": "nahum", "chapter": 1, "verse": 7},
        {"reference": "Micah 6:8", "book": "micah", "chapter": 6, "verse": 8},
        {"reference": "Jonah 2:8", "book": "jonah", "chapter": 2, "verse": 8},
        {"reference": "Obadiah 1:15", "book": "obadiah", "chapter": 1, "verse": 15},
        {"reference": "Amos 5:24", "book": "amos", "chapter": 5, "verse": 24},
        {"reference": "Joel 2:32", "book": "joel", "chapter": 2, "verse": 32},
        {"reference": "Hosea 6:6", "book": "hosea", "chapter": 6, "verse": 6},
    ]
}

# Bible Game Helper Functions
def extract_verse_from_text(text, verse_number):
    """Extract a specific verse from cleaned Bible text"""
    lines = text.strip().split('\n')
    for line in lines:
        line = line.strip()
        if line.startswith(f"{verse_number} "):
            return line[len(f"{verse_number} "):].strip()
    return None

def get_bible_verse(book, chapter, verse, language='english'):
    """Fetch a specific Bible verse in the specified language"""
    try:
        # Get the URL for the chapter
        result = get_wordproject_url_from_input(language, f"{book} {chapter}")
        url, _, _, _ = result

        if url.startswith("❌"):
            return None

        # Extract the chapter text
        raw_text = extract_bible_chapter_text(url)
        if raw_text.startswith("❌"):
            return None

        # Determine language code for cleaning
        lang_code = 'kj'  # default English
        if language.lower() in ['malayalam', 'mal']:
            lang_code = 'ml'
        elif language.lower() in ['hindi', 'hin']:
            lang_code = 'in'
        elif language.lower() in ['tamil', 'tam']:
            lang_code = 'tm'
        elif language.lower() in ['telugu', 'tel']:
            lang_code = 'te'
        elif language.lower() in ['chinese', 'zh']:
            lang_code = 'big5'
        elif language.lower() in ['japanese', 'ja']:
            lang_code = 'jp'
        else:
            # For other languages, use the language code as-is
            # The clean_bible_text function will handle generic cleaning
            lang_code = language.lower()

        # Clean the text
        cleaned_text = clean_bible_text(raw_text, lang_code)

        # Extract the specific verse
        verse_text = extract_verse_from_text(cleaned_text, verse)

        if verse_text:
            # Clean up common formatting issues
            verse_text = verse_text.replace('  ', ' ')  # Remove double spaces
            verse_text = verse_text.strip()
            # Fix common word concatenation issues (mainly for English)
            if language.lower() in ['english', 'eng']:
                verse_text = verse_text.replace('Christwhich', 'Christ which')
                verse_text = verse_text.replace('Godand', 'God and')
                verse_text = verse_text.replace('Lordand', 'Lord and')

        return verse_text

    except Exception:
        return None

def generate_wrong_options(correct_reference, _):
    """Generate 3 wrong options for the multiple choice"""
    all_verses = []
    for diff_level in BIBLE_VERSES.values():
        all_verses.extend(diff_level)

    # Remove the correct answer from options
    wrong_options = [v for v in all_verses if v["reference"] != correct_reference]

    # Select 3 random wrong options
    selected_wrong = random.sample(wrong_options, min(3, len(wrong_options)))
    return [opt["reference"] for opt in selected_wrong]

def create_bible_question(difficulty, used_verses=None, language='english'):
    """Create a new Bible question, avoiding duplicates"""
    if used_verses is None:
        used_verses = []

    verses = BIBLE_VERSES[difficulty]
    available_verses = [v for v in verses if v["reference"] not in used_verses]

    # If all verses have been used, reset the list
    if not available_verses:
        available_verses = verses
        used_verses.clear()

    # Try up to 3 times to get a working verse
    for attempt in range(3):
        selected_verse = random.choice(available_verses)

        # Get the verse text in the specified language
        verse_text = get_bible_verse(selected_verse["book"], selected_verse["chapter"], selected_verse["verse"], language)

        if verse_text:
            # Generate options
            wrong_options = generate_wrong_options(selected_verse["reference"], difficulty)
            all_options = [selected_verse["reference"]] + wrong_options
            random.shuffle(all_options)

            return {
                "verse_text": verse_text,
                "correct_answer": selected_verse["reference"],
                "options": all_options,
                "difficulty": difficulty,
                "reference": selected_verse["reference"],
                "language": language
            }
        else:
            # Remove this verse from available options and try another
            available_verses = [v for v in available_verses if v["reference"] != selected_verse["reference"]]
            if not available_verses:
                break

    return None

# Define authorized_users globally for use in all handlers
authorized_users_str = st.secrets["AUTHORIZED_USERS"]
authorized_users = list(map(int, authorized_users_str.split(','))) if authorized_users_str else []

# Downloader feature flag
DOWNLOADER_AVAILABLE = True

# Add new states for notation
NOTATION_TYPE, NOTATION_HYMN_INPUT, NOTATION_LYRIC_INPUT = range(100, 103)

# Lyrics PDF logic
LYRICS_DOWNLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'tmp')
LYRICS_FOLDER_ID = st.secrets["L_SHEET_MUSIC"]
LYRICS_FOLDER_URL = f'https://drive.google.com/drive/folders/{LYRICS_FOLDER_ID}'

def extract_lyrics_folder_id(folder_url):
    match = re.search(r'/folders/([a-zA-Z0-9_-]+)', folder_url)
    if match:
        return match.group(1)
    raise ValueError("Invalid folder URL")

def fetch_lyrics_file_map(folder_url):
    folder_id = extract_lyrics_folder_id(folder_url)
    lyrics_file_map = {}
    page_token = None
    while True:
        response = drive_service.files().list(
            q=f"'{folder_id}' in parents and mimeType = 'application/pdf' and trashed = false",
            fields="nextPageToken, files(id, name)",
            pageToken=page_token
        ).execute()
        for file in response.get('files', []):
            filename = file['name']
            match = re.match(r'L-(\d+)\.pdf$', filename)
            if match:
                lyric_no = int(match.group(1))
                lyrics_file_map[lyric_no] = file['id']
        page_token = response.get('nextPageToken', None)
        if page_token is None:
            break
    return lyrics_file_map

def download_lyrics_pdf(file_id, filename):
    url = f"https://drive.google.com/uc?id={file_id}"
    response = requests.get(url)
    if response.status_code == 200:
        save_path = os.path.join(LYRICS_DOWNLOAD_DIR, filename)
        with open(save_path, 'wb') as f:
            f.write(response.content)
        return save_path
    else:
        return None

def get_lyrics_pdf_by_lyric_number(lyric_number, lyrics_file_map):
    lyric_number = int(lyric_number)
    if lyric_number in lyrics_file_map:
        file_id = lyrics_file_map[lyric_number]
        filename = f"L-{lyric_number}.pdf"
        return download_lyrics_pdf(file_id, filename)
    else:
        return None

os.makedirs(LYRICS_DOWNLOAD_DIR, exist_ok=True)
lyrics_file_map = fetch_lyrics_file_map(LYRICS_FOLDER_URL)

# --- /notation command (interactive only, no arguments supported) ---
async def notation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 Please enter the hymn or lyric number (e.g. H-86 or L-222):",
        reply_markup=ReplyKeyboardRemove()
    )
    return NOTATION_TYPE

async def notation_code_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code_input_raw = update.message.text
    code_input = standardize_hlc_value(code_input_raw)
    if code_input.startswith("H-") and code_input[2:].isdigit():
        song_id = code_input
        tunes = Tune_finder_of_known_songs(song_id)
        if not tunes or tunes == "Invalid Number":
            await update.message.reply_text(f"❌ No known tunes found for {song_id}. Try again or type /cancel to stop.")
            await update.message.reply_text("Enter another hymn or lyric number, or type /cancel to stop.")
            return NOTATION_TYPE
        if isinstance(tunes, str):
            tune_list = [t.strip() for t in tunes.split(",") if t.strip()]
        else:
            await update.message.reply_text("⚠️ Could not parse tunes.")
            await update.message.reply_text("Enter another hymn or lyric number, or type /cancel to stop.")
            return NOTATION_TYPE
        if not tune_list:
            await update.message.reply_text("🎵 No tunes available.")
            await update.message.reply_text("Enter another hymn or lyric number, or type /cancel to stop.")
            return NOTATION_TYPE
        keyboard = [
            [InlineKeyboardButton(tune, callback_data=f"notation:{tune}|{song_id}")]
            for tune in tune_list
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"🎶 Select a tune for {song_id}:", reply_markup=reply_markup
        )
        await update.message.reply_text("Enter another hymn or lyric number, or type /cancel to stop.")
        return NOTATION_TYPE
    elif code_input.startswith("L-") and code_input[2:].isdigit():
        lyric_number = int(code_input[2:])
        downloading_msg = await update.message.reply_text("⏳ Downloading music sheet... Please wait.")
        pdf_path = get_lyrics_pdf_by_lyric_number(lyric_number, lyrics_file_map)
        await downloading_msg.delete()
        if pdf_path:
            with open(pdf_path, 'rb') as pdf_file:
                await update.message.reply_document(
                    document=pdf_file,
                    filename=f"L-{lyric_number}.pdf",
                    caption=f"Here is the notation for Lyric L-{lyric_number}."
                )
        else:
            await update.message.reply_text(f"❌ Could not find notation PDF for Lyric L-{lyric_number}.")
        await update.message.reply_text("Enter another hymn or lyric number, or type /cancel to stop.")
        return NOTATION_TYPE
    else:
        await update.message.reply_text("❌ Invalid format. Please use H-<number> or L-<number> (e.g. H-86 or L-222). Try again or type /cancel to stop.")
        await update.message.reply_text("Enter another hymn or lyric number, or type /cancel to stop.")
        return NOTATION_TYPE

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
     try:
         folder_id = extract_folder_id(folder_url)
         drive_service = get_drive_service()
         file_map = {}
         page_token = None
         max_retries = 3
         retry_count = 0

         while True:
             try:
                 response = drive_service.files().list(
                     q=f"'{folder_id}' in parents and mimeType='application/pdf' and trashed = false",
                     fields="nextPageToken, files(id, name)",
                     pageToken=page_token,
                     pageSize=100  # Limit page size to avoid large responses
                 ).execute()

                 # Reset retry count on successful request
                 retry_count = 0

                 for file in response.get('files', []):
                     try:
                         page_num = int(file['name'].split('.')[0])
                         file_map[page_num] = file['id']
                     except ValueError:
                         continue  # Skip files that don't start with a number

                 page_token = response.get('nextPageToken', None)
                 if page_token is None:
                     break

             except Exception as e:
                 retry_count += 1
                 if retry_count >= max_retries:
                     print(f"❌ Failed to load images after {max_retries} retries: {e}")
                     break
                 print(f"⚠️ Retry {retry_count}/{max_retries} for loading images: {e}")
                 import time
                 time.sleep(2 ** retry_count)  # Exponential backoff

         return file_map

     except Exception as e:
         print(f"❌ Error initializing image file loading: {e}")
         return {}
 
 # === DOWNLOAD IMAGE ===
def download_image(file_id, filename):
    try:
        # Use Google Drive API instead of direct download URL for better reliability
        drive_service = get_drive_service()

        # Get file metadata first to check if it exists
        try:
            file_metadata = drive_service.files().get(fileId=file_id).execute()
        except Exception as e:
            print(f"File {file_id} not found or not accessible: {e}")
            return None

        # Download the file content
        request = drive_service.files().get_media(fileId=file_id)

        # Create a BytesIO object to store the downloaded content
        import io
        file_content = io.BytesIO()

        from googleapiclient.http import MediaIoBaseDownload
        downloader = MediaIoBaseDownload(file_content, request)

        done = False
        while done is False:
            status, done = downloader.next_chunk()

        # Save the content to file
        save_path = os.path.join(DOWNLOAD_DIR, filename)
        file_content.seek(0)

        with open(save_path, 'wb') as f:
            f.write(file_content.read())

        # Verify the file was downloaded correctly
        if os.path.exists(save_path) and os.path.getsize(save_path) > 0:
            return save_path
        else:
            print(f"Downloaded file {filename} is empty or corrupted")
            return None

    except Exception as e:
        print(f"Error downloading PDF {filename}: {str(e)}")
        return None
 
 # === GET IMAGE FOR PAGE ===
def get_image_by_page(page_number, file_map):
     page_number = int(page_number)
     if page_number in file_map:
         file_id = file_map[page_number]
         filename = f"{page_number}.pdf"
         downloaded_path = download_image(file_id, filename)
         if downloaded_path and os.path.exists(downloaded_path) and os.path.getsize(downloaded_path) > 0:
             return downloaded_path
         else:
             print(f"Failed to download or verify PDF for page {page_number}")
             return None
     else:
         print(f"Page {page_number} not found in file map")
         return None
 
 # === MAIN EXECUTION ===
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
# Load file_map at startup with error handling
try:
    print("Loading hymn image files from Google Drive...")
    file_map = get_image_files_from_folder(HYMN_FOLDER_URL)
    print(f"Successfully loaded {len(file_map)} hymn images")
except Exception as e:
    print(f"❌ Error loading hymn images: {e}")
    print("⚠️ Bot will continue without notation images")
    file_map = {}  # Empty dict allows bot to continue



def Music_notation_downloader(hymnno, file_map):
    if isinstance(hymnno, str) and hymnno.upper().startswith('H-'):
        hymnno = hymnno[2:]
    hymnno = int(hymnno)
    results = {}

    # Get data
    data = get_all_data()
    dfH = data["dfH"]
    dfTH = data["dfTH"]

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



# Helper function to send long messages in chunks
async def send_long_message(update, message_parts, parse_mode="Markdown", max_length=3500):
    """
    Sends a message, splitting it into multiple messages if it's too long.
    Ensures that no message part exceeds max_length.
    """
    def split_text(text, max_len):
        # Split text into chunks of max_len, trying to split at newlines
        chunks = []
        while len(text) > max_len:
            split_at = text.rfind('\n', 0, max_len)
            if split_at == -1 or split_at < max_len // 2:
                split_at = max_len
            chunks.append(text[:split_at])
            text = text[split_at:]
        if text:
            chunks.append(text)
        return chunks

    # Flatten message_parts so that no part exceeds max_length
    flat_parts = []
    for part in message_parts:
        if len(part) > max_length:
            flat_parts.extend(split_text(part, max_length))
        else:
            flat_parts.append(part)

    full_message = "\n\n".join(flat_parts)
    if len(full_message) <= max_length:
        await update.message.reply_text(
            full_message,
            parse_mode=parse_mode,
            reply_markup=ReplyKeyboardRemove()
        )
    else:
        current_chunk = ""
        for part in flat_parts:
            if len(current_chunk + "\n\n" + part) <= max_length:
                if current_chunk:
                    current_chunk += "\n\n" + part
                else:
                    current_chunk = part
            else:
                if current_chunk:
                    await update.message.reply_text(
                        current_chunk,
                        parse_mode=parse_mode,
                        reply_markup=ReplyKeyboardRemove()
                    )
                current_chunk = part
        if current_chunk:
            await update.message.reply_text(
                current_chunk,
                parse_mode=parse_mode,
                reply_markup=ReplyKeyboardRemove()
            )

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

    # List to store paths of downloaded PDFs
    pdf_files = []
    
    # Download all pages first
    for page in page_numbers:
        filename = f"{page}.pdf"
        file_path = os.path.join(DOWNLOAD_DIR, filename)

        if not os.path.exists(file_path):
            # Try to download the PDF from Google Drive
            downloaded_path = get_image_by_page(page, file_map)
            if downloaded_path and os.path.exists(downloaded_path):
                pdf_files.append(downloaded_path)
            else:
                await context.bot.send_message(chat_id=chat_id, text=f"❌ Page {page} could not be downloaded.")
                continue
        else:
            pdf_files.append(file_path)

    if not pdf_files:
        await context.bot.send_message(chat_id=chat_id, text=f"❌ No PDF pages could be downloaded for {song_id} ({tune_name}).")
        return

    try:
        # If there's only one page, send it directly
        if len(pdf_files) == 1:
            # Verify the PDF file is valid before sending
            try:
                from PyPDF2 import PdfReader
                with open(pdf_files[0], 'rb') as test_file:
                    reader = PdfReader(test_file)
                    if len(reader.pages) == 0:
                        raise Exception("PDF file is empty or corrupted")
            except Exception as pdf_error:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"❌ PDF file for {song_id} ({tune_name}) is corrupted. Please try again later."
                )
                return

            with open(pdf_files[0], 'rb') as pdf_file:
                await context.bot.send_document(
                    chat_id=chat_id,
                    document=pdf_file,
                    filename=f"{song_id}_{tune_name}.pdf",
                    caption=f"Notation for {song_id} ({tune_name})"
                )
        else:
            # If there are multiple pages, merge them with better error handling
            merger = PdfMerger()
            valid_pdfs = []

            # Validate each PDF before merging
            for pdf_path in pdf_files:
                try:
                    from PyPDF2 import PdfReader
                    with open(pdf_path, 'rb') as test_file:
                        reader = PdfReader(test_file)
                        if len(reader.pages) > 0:
                            valid_pdfs.append(pdf_path)
                        else:
                            print(f"Skipping empty PDF: {pdf_path}")
                except Exception as pdf_error:
                    print(f"Skipping corrupted PDF {pdf_path}: {pdf_error}")
                    continue

            if not valid_pdfs:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"❌ All PDF files for {song_id} ({tune_name}) are corrupted. Please try again later."
                )
                return

            # Merge only valid PDFs
            for pdf_path in valid_pdfs:
                try:
                    merger.append(pdf_path)
                except Exception as merge_error:
                    print(f"Error merging {pdf_path}: {merge_error}")
                    continue

            # Create a temporary file for the merged PDF
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_file:
                try:
                    merger.write(tmp_file.name)
                    merger.close()

                    # Verify the merged PDF is valid
                    from PyPDF2 import PdfReader
                    with open(tmp_file.name, 'rb') as test_file:
                        reader = PdfReader(test_file)
                        if len(reader.pages) == 0:
                            raise Exception("Merged PDF is empty")

                    # Send the merged PDF
                    with open(tmp_file.name, 'rb') as merged_pdf:
                        await context.bot.send_document(
                            chat_id=chat_id,
                            document=merged_pdf,
                            filename=f"{song_id}_{tune_name}_complete.pdf",
                            caption=f"Complete notation for {song_id} ({tune_name}) - {len(valid_pdfs)} pages"
                        )
                except Exception as merge_error:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=f"❌ Error creating merged PDF for {song_id} ({tune_name}): {str(merge_error)}"
                    )
                finally:
                    # Clean up the temporary file
                    try:
                        os.unlink(tmp_file.name)
                    except:
                        pass

    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Error processing PDFs: {str(e)}")
        print(f"Error processing PDFs: {str(e)}")  # For debugging



async def start_notation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 Please enter the hymn or lyric number (e.g. H-86 or L-222):",
        reply_markup=ReplyKeyboardRemove()
    )
    return ASK_HYMN_NO

async def receive_hymn_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    song_id = standardize_hlc_value(update.message.text.strip())

    tunes = Tune_finder_of_known_songs(song_id)
    if not tunes or tunes == "Invalid Number":
        await update.message.reply_text(
            f"❌ No known tunes found for {song_id}.\n\n"
            "Please check the number and try again, or type /cancel to stop.\n"
            "Enter another hymn or lyric number:",
            reply_markup=ReplyKeyboardRemove()
        )
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

    # Show downloading message
    downloading_msg = await context.bot.send_message(chat_id=query.message.chat_id, text="⏳ Downloading music sheet... Please wait.")
    # Send the image using the fixed function
    await send_notation_image(update, context, tune_name.strip(), song_id.strip())
    # Delete the downloading message
    await downloading_msg.delete()



  
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
        "\n"
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
            "❌ This URL is not supported. Please send a YouTube or Spotify link.",
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
    progress_message = await update.message.reply_text(
        f"🎵 Starting download from {platform}...\n"
        f"Quality: {quality_text}\n\n"
        "This may take a few minutes. Please wait...\n"
        "💡 Use /cancel to stop the download.",
        reply_markup=ReplyKeyboardRemove()
    )

    try:
        # Log download request to Google Doc (similar to comment function)
        yfile_id = st.secrets["YFILE_ID"]
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        chat_id = update.effective_chat.id

        download_request_entry = f"{timestamp} - {user.full_name} (@{user.username}, ID: {user.id}, ChatID: {chat_id}) requested download:\nPlatform: {platform} | Quality: {quality} | URL: {url}\n\n"

        if yfile_id:
            try:
                append_download_to_google_doc(yfile_id, download_request_entry)
            except Exception as log_error:
                bot_logger.error(f"Error logging download request: {log_error}")

        # Initialize downloader
        downloader = AudioDownloader()

        # Create a cancellation event
        cancel_event = asyncio.Event()

        # Store the cancel event in context for potential cancellation
        context.user_data["cancel_event"] = cancel_event
        context.user_data["download_in_progress"] = True

        # Download the audio with timeout and cancellation support
        try:
            # Create a task for the download
            download_task = asyncio.create_task(
                downloader.download_audio(url, quality, chat_id=str(chat_id), cancel_event=cancel_event)
            )

            # Create a task for progress updates
            async def send_progress_updates():
                await asyncio.sleep(30)  # Wait 30 seconds
                if not download_task.done() and not cancel_event.is_set():
                    try:
                        await progress_message.edit_text(
                            f"🎵 Download in progress from {platform}...\n"
                            f"Quality: {quality_text}\n\n"
                            "⏳ Still downloading... This may take a while for longer videos.\n"
                            "💡 Use /cancel to stop the download."
                        )
                    except Exception:
                        pass  # Ignore edit errors

                await asyncio.sleep(60)  # Wait another minute
                if not download_task.done() and not cancel_event.is_set():
                    try:
                        await progress_message.edit_text(
                            f"🎵 Download in progress from {platform}...\n"
                            f"Quality: {quality_text}\n\n"
                            "⏳ Download is taking longer than expected...\n"
                            "💡 Use /cancel to stop the download."
                        )
                    except Exception:
                        pass  # Ignore edit errors

            # Start progress updates
            progress_task = asyncio.create_task(send_progress_updates())

            # Wait for download with timeout
            result = await asyncio.wait_for(download_task, timeout=600)  # 10 minutes timeout

            # Cancel progress updates
            progress_task.cancel()
        except asyncio.TimeoutError:
            # Cancel progress updates
            if 'progress_task' in locals():
                progress_task.cancel()

            await update.message.reply_text(
                "⏰ Download timed out after 10 minutes.\n\n"
                "This usually happens with very long videos or slow internet.\n"
                "Please try again with a shorter video or check your connection.",
                reply_markup=ReplyKeyboardRemove()
            )
            context.user_data.pop("cancel_event", None)
            context.user_data.pop("download_in_progress", None)
            return ConversationHandler.END
        except asyncio.CancelledError:
            # Cancel progress updates
            if 'progress_task' in locals():
                progress_task.cancel()

            await update.message.reply_text(
                "❌ Download was cancelled by user.",
                reply_markup=ReplyKeyboardRemove()
            )
            context.user_data.pop("cancel_event", None)
            context.user_data.pop("download_in_progress", None)
            return ConversationHandler.END
        except Exception as e:
            # Cancel progress updates
            if 'progress_task' in locals():
                progress_task.cancel()

            bot_logger.error(f"Download error for user {user.id}: {str(e)}")

            # Log failed download to Google Doc
            error_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            download_error_entry = f"{error_timestamp} - DOWNLOAD ERROR for {user.full_name} (@{user.username}, ID: {user.id}):\nPlatform: {platform} | Quality: {quality} | URL: {url}\nError: {str(e)}\n\n"

            if yfile_id:
                try:
                    append_download_to_google_doc(yfile_id, download_error_entry)
                except Exception as log_error:
                    bot_logger.error(f"Error logging download error: {log_error}")

            await update.message.reply_text(
                "❌ An error occurred during download. Please try again later.",
                reply_markup=ReplyKeyboardRemove()
            )
            context.user_data.pop("cancel_event", None)
            context.user_data.pop("download_in_progress", None)
            return ConversationHandler.END
        finally:
            # Clean up context
            context.user_data.pop("cancel_event", None)
            context.user_data.pop("download_in_progress", None)

        if result is None:
            # Log failed download to Google Doc
            download_failed_entry = f"{timestamp} - DOWNLOAD FAILED for {user.full_name} (@{user.username}, ID: {user.id}):\nPlatform: {platform} | Quality: {quality} | URL: {url}\n\n"

            if yfile_id:
                try:
                    append_download_to_google_doc(yfile_id, download_failed_entry)
                except Exception as log_error:
                    bot_logger.error(f"Error logging download failure: {log_error}")

            await update.message.reply_text(
                "❌ Download failed. Please try again or contact the administrator."
            )
            return ConversationHandler.END

        file_path, file_info = result

        # Cancel progress updates
        if 'progress_task' in locals():
            progress_task.cancel()

        # Show download completion
        try:
            await progress_message.edit_text(
                f"✅ *Download completed!*\n\n"
                f"🎵 *{file_info['title']}*\n"
                f"👤 *Artist:* {file_info['artist']}\n"
                f"📱 *Platform:* {file_info['platform']}\n"
                f"📊 *Size:* {file_info['size_mb']:.1f} MB\n\n"
                "Sending file...",
                parse_mode="Markdown"
            )
        except Exception:
            # If edit fails, send a new message
            await update.message.reply_text(
                f"✅ *Download completed!*\n\n"
                f"🎵 *{file_info['title']}*\n"
                f"👤 *Artist:* {file_info['artist']}\n"
                f"📱 *Platform:* {file_info['platform']}\n"
                f"📊 *Size:* {file_info['size_mb']:.1f} MB\n\n"
                "Sending file...",
                parse_mode="Markdown"
            )

        # Send the audio file
        try:
            with open(file_path, 'rb') as audio_file:
                await update.message.reply_audio(
                    audio=audio_file,
                    title=file_info['title'],
                    performer=file_info['artist'],
                    duration=file_info.get('duration', 0)
                )
        except Exception as send_error:
            bot_logger.error(f"Error sending audio file: {send_error}")
            await update.message.reply_text(
                "❌ Download completed but failed to send the audio file. Please try again."
            )
            # Clean up the file since we couldn't send it
            downloader.cleanup_file(file_path)
            return ConversationHandler.END

        # Log successful download
        user_logger.info(f"Download completed for {user.full_name} ({user.id}): {file_info['title']}")

        # Log successful download to Google Doc
        download_success_entry = f"{timestamp} - DOWNLOAD SUCCESS for {user.full_name} (@{user.username}, ID: {user.id}):\nTitle: {file_info['title']} | Artist: {file_info['artist']} | Platform: {file_info['platform']} | Size: {file_info['size_mb']:.1f}MB | Quality: {quality}\nURL: {url}\n\n"

        if yfile_id:
            try:
                append_download_to_google_doc(yfile_id, download_success_entry)
            except Exception as log_error:
                bot_logger.error(f"Error logging download success: {log_error}")

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
        error_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        download_error_entry = f"{error_timestamp} - DOWNLOAD ERROR for {user.full_name} (@{user.username}, ID: {user.id}):\nPlatform: {platform} | Quality: {quality} | Error: {str(e)}\nURL: {url}\n\n"

        if yfile_id:
            try:
                append_download_to_google_doc(yfile_id, download_error_entry)
            except Exception as log_error:
                bot_logger.error(f"Error logging download error: {log_error}")

        await update.message.reply_text(
            "❌ An error occurred during download. Please try again later."
        )
        return ConversationHandler.END

# Custom cancel handler for downloads
async def cancel_download(update: Update, context: CallbackContext) -> int:
    """Cancel handler that can interrupt downloads"""
    user = update.effective_user
    user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) sent /cancel")

    # Check if download is in progress
    if context.user_data.get("download_in_progress", False):
        # Signal cancellation
        cancel_event = context.user_data.get("cancel_event")
        if cancel_event:
            cancel_event.set()

        # Clean up context
        context.user_data.pop("cancel_event", None)
        context.user_data.pop("download_in_progress", None)
        context.user_data.pop("download_url", None)
        context.user_data.pop("platform", None)

        try:
            await update.message.reply_text(
                "❌ Download cancelled successfully.",
                reply_markup=ReplyKeyboardRemove()
            )
        except Exception as e:
            bot_logger.error(f"Error sending cancel message: {e}")
            # Try to send a simpler message without keyboard removal
            try:
                await update.message.reply_text("❌ Download cancelled.")
            except Exception as e2:
                bot_logger.error(f"Error sending simple cancel message: {e2}")
    else:
        # Regular cancel
        try:
            await update.message.reply_text(
                "Operation canceled.",
                reply_markup=ReplyKeyboardRemove()
            )
        except Exception as e:
            bot_logger.error(f"Error sending cancel message: {e}")
            try:
                await update.message.reply_text("Operation canceled.")
            except Exception as e2:
                bot_logger.error(f"Error sending simple cancel message: {e2}")

    return ConversationHandler.END


# Telegram command handler for /tune command

# States for ConversationHandler
CHOOSE_METHOD, GET_INPUT = range(2)

# Bible Game States
BIBLE_GAME_LANGUAGE, BIBLE_GAME_DIFFICULTY, BIBLE_GAME_QUESTION = range(3)
 
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

# Bible Game Handlers
async def bible_game_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the Bible game"""
    user = update.effective_user
    user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) started Bible game")

    # Reset game data for new session
    context.user_data['bible_game_score'] = 0
    context.user_data['bible_game_total'] = 0
    context.user_data['current_difficulty'] = None
    context.user_data['current_language'] = None
    context.user_data['used_verses'] = []  # Track used verses to avoid duplicates

    # Get user's best scores from database for all difficulties
    user_best_scores = get_user_best_scores_all_difficulties(user.id)

    # Show welcome message and language selection
    welcome_text = (
        "📖 *Welcome to the Bible Game!* 🎮\n\n"
        "Test your Bible knowledge! I'll show you a verse, and you need to guess which Bible reference it's from.\n\n"
        f"🏆 *Your Best Scores:*\n"
        f"🟢 Easy: {user_best_scores['Easy']}\n"
        f"🟡 Medium: {user_best_scores['Medium']}\n"
        f"🔴 Hard: {user_best_scores['Hard']}\n\n"
        "First, choose your preferred language:"
    )

    keyboard = [
        ["🇺🇸 English", "🇮🇳 Malayalam"],
        ["📊 View Stats", "🏅 Leaderboard"],
        ["❌ Cancel"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)

    await update.message.reply_text(welcome_text, parse_mode="Markdown", reply_markup=reply_markup)
    return BIBLE_GAME_LANGUAGE

async def bible_game_language_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle language selection"""
    user_input = update.message.text.strip()
    user = update.effective_user

    if user_input == "❌ Cancel":
        await update.message.reply_text("Bible game cancelled. Type /games to play again!", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    elif user_input == "📊 View Stats":
        score = context.user_data.get('bible_game_score', 0)
        total = context.user_data.get('bible_game_total', 0)
        current_difficulty = context.user_data.get('current_difficulty', 'Easy')
        accuracy = (score / total * 100) if total > 0 else 0

        # Get user's best scores for all difficulties
        user_best_scores = get_user_best_scores_all_difficulties(user.id)

        stats_text = (
            f"📊 *Your Bible Game Stats:*\n\n"
            f"*Current Session ({current_difficulty}):*\n"
            f"✅ Correct Answers: {score}\n"
            f"❌ Wrong Answers: {total - score}\n"
            f"📈 Total Questions: {total}\n"
            f"🎯 Accuracy: {accuracy:.1f}%\n\n"
            f"🏆 *Your Best Scores:*\n"
            f"🟢 Easy: {user_best_scores['Easy']}\n"
            f"🟡 Medium: {user_best_scores['Medium']}\n"
            f"🔴 Hard: {user_best_scores['Hard']}\n"
        )

        keyboard = [
            ["🇺🇸 English", "🇮🇳 Malayalam"],
            ["🏅 Leaderboard", "❌ Cancel"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)

        await update.message.reply_text(stats_text, parse_mode="Markdown", reply_markup=reply_markup)
        return BIBLE_GAME_LANGUAGE

    elif user_input == "🏅 Leaderboard":
        # Get leaderboards for all difficulties
        leaderboards = get_combined_leaderboard(5)  # Top 5 for each difficulty

        leaderboard_text = "🏅 *Bible Game Leaderboards - Top 5*\n\n"

        for difficulty, emoji in [("Easy", "🟢"), ("Medium", "🟡"), ("Hard", "🔴")]:
            leaderboard_text += f"{emoji} *{difficulty} Level:*\n"
            difficulty_leaderboard = leaderboards.get(difficulty, [])

            if difficulty_leaderboard:
                for i, player in enumerate(difficulty_leaderboard, 1):
                    if i == 1:
                        medal = "🥇"
                    elif i == 2:
                        medal = "🥈"
                    elif i == 3:
                        medal = "🥉"
                    else:
                        medal = f"{i}."

                    # Highlight current user
                    if player['User_id'] == user.id:
                        leaderboard_text += f"*{medal} {player['User_Name']}: {player['Score']} ⭐*\n"
                    else:
                        leaderboard_text += f"{medal} {player['User_Name']}: {player['Score']}\n"
            else:
                leaderboard_text += "No scores yet!\n"

            leaderboard_text += "\n"

        keyboard = [
            ["🇺🇸 English", "🇮🇳 Malayalam"],
            ["📊 View Stats", "❌ Cancel"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)

        await update.message.reply_text(leaderboard_text, parse_mode="Markdown", reply_markup=reply_markup)
        return BIBLE_GAME_LANGUAGE

    # Handle language selection
    language_map = {
        "🇺🇸 English": "english",
        "🇮🇳 Malayalam": "malayalam"
    }

    if user_input not in language_map:
        await update.message.reply_text("Please choose a valid language from the keyboard.")
        return BIBLE_GAME_LANGUAGE

    language = language_map[user_input]
    context.user_data['current_language'] = language
    user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) chose {language} language")

    # Show difficulty selection
    difficulty_text = (
        f"🌍 *Language Selected:* {user_input}\n\n"
        f"📊 *Current Session:* {context.user_data['bible_game_score']}/{context.user_data['bible_game_total']} correct\n\n"
        "Now choose your difficulty level:"
    )

    keyboard = [
        ["🟢 Easy", "🟡 Medium", "🔴 Hard"],
        ["📊 View Stats", "🏅 Leaderboard"],
        ["🔄 Reset Score", "❌ Cancel"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)

    await update.message.reply_text(difficulty_text, parse_mode="Markdown", reply_markup=reply_markup)
    return BIBLE_GAME_DIFFICULTY

async def bible_game_difficulty_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle difficulty selection and other options"""
    user_input = update.message.text.strip()
    user = update.effective_user

    if user_input == "❌ Cancel":
        # Save score if user answered at least one question in current difficulty
        score = context.user_data.get('bible_game_score', 0)
        total = context.user_data.get('bible_game_total', 0)
        current_difficulty = context.user_data.get('current_difficulty')

        if total > 0 and current_difficulty:
            save_game_score(user.full_name or user.username or "Unknown", user.id, score, current_difficulty)

        await update.message.reply_text("Bible game cancelled. Type /games to play again!", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    elif user_input == "📊 View Stats":
        score = context.user_data.get('bible_game_score', 0)
        total = context.user_data.get('bible_game_total', 0)
        current_difficulty = context.user_data.get('current_difficulty', 'Easy')
        accuracy = (score / total * 100) if total > 0 else 0

        # Get user's best scores for all difficulties
        user_best_scores = get_user_best_scores_all_difficulties(user.id)

        stats_text = (
            f"📊 *Your Bible Game Stats:*\n\n"
            f"*Current Session ({current_difficulty}):*\n"
            f"✅ Correct Answers: {score}\n"
            f"❌ Wrong Answers: {total - score}\n"
            f"📈 Total Questions: {total}\n"
            f"🎯 Accuracy: {accuracy:.1f}%\n\n"
            f"🏆 *Your Best Scores:*\n"
            f"🟢 Easy: {user_best_scores['Easy']}\n"
            f"🟡 Medium: {user_best_scores['Medium']}\n"
            f"🔴 Hard: {user_best_scores['Hard']}\n"
        )

        keyboard = [
            ["🟢 Easy", "🟡 Medium", "🔴 Hard"],
            ["🏅 Leaderboard", "🔄 Reset Score"],
            ["❌ Cancel"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)

        await update.message.reply_text(stats_text, parse_mode="Markdown", reply_markup=reply_markup)
        return BIBLE_GAME_DIFFICULTY

    elif user_input == "🏅 Leaderboard":
        # Get leaderboards for all difficulties
        leaderboards = get_combined_leaderboard(5)  # Top 5 for each difficulty

        leaderboard_text = "🏅 *Bible Game Leaderboards - Top 5*\n\n"

        for difficulty, emoji in [("Easy", "🟢"), ("Medium", "🟡"), ("Hard", "🔴")]:
            leaderboard_text += f"{emoji} *{difficulty} Level:*\n"
            difficulty_leaderboard = leaderboards.get(difficulty, [])

            if difficulty_leaderboard:
                for i, player in enumerate(difficulty_leaderboard, 1):
                    if i == 1:
                        medal = "🥇"
                    elif i == 2:
                        medal = "🥈"
                    elif i == 3:
                        medal = "🥉"
                    else:
                        medal = f"{i}."

                    # Highlight current user
                    if player['User_id'] == user.id:
                        leaderboard_text += f"*{medal} {player['User_Name']}: {player['Score']} ⭐*\n"
                    else:
                        leaderboard_text += f"{medal} {player['User_Name']}: {player['Score']}\n"
            else:
                leaderboard_text += "No scores yet!\n"

            leaderboard_text += "\n"

        keyboard = [
            ["🟢 Easy", "🟡 Medium", "🔴 Hard"],
            ["📊 View Stats", "🔄 Reset Score"],
            ["❌ Cancel"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)

        await update.message.reply_text(leaderboard_text, parse_mode="Markdown", reply_markup=reply_markup)
        return BIBLE_GAME_DIFFICULTY

    elif user_input == "🔄 Reset Score":
        context.user_data['bible_game_score'] = 0
        context.user_data['bible_game_total'] = 0

        keyboard = [
            ["🟢 Easy", "🟡 Medium", "🔴 Hard"],
            ["📊 View Stats", "🏅 Leaderboard"],
            ["❌ Cancel"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)

        await update.message.reply_text("🔄 Score reset! Choose your difficulty:", reply_markup=reply_markup)
        return BIBLE_GAME_DIFFICULTY



    elif user_input == "❌ Quit Game":
        score = context.user_data.get('bible_game_score', 0)
        total = context.user_data.get('bible_game_total', 0)
        accuracy = (score / total * 100) if total > 0 else 0

        # Save score to database if user answered at least one question
        if total > 0:
            current_difficulty = context.user_data.get('current_difficulty', 'Easy')
            save_success = save_game_score(user.full_name or user.username or "Unknown", user.id, score, current_difficulty)
            save_status = "✅ Score saved!" if save_success else "⚠️ Could not save score."
        else:
            save_status = ""

        final_text = (
            f"🎮 *Game Over!*\n\n"
            f"📊 *Final Stats:*\n"
            f"✅ Correct: {score}\n"
            f"❌ Wrong: {total - score}\n"
            f"📈 Total: {total}\n"
            f"🎯 Accuracy: {accuracy:.1f}%\n\n"
            f"{save_status}\n"
            f"Thanks for playing! Type /games to play again."
        )

        await update.message.reply_text(final_text, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    # Handle difficulty selection
    difficulty_map = {
        "🟢 Easy": "Easy",
        "🟡 Medium": "Medium",
        "🔴 Hard": "Hard"
    }

    if user_input not in difficulty_map:
        await update.message.reply_text("Please choose a valid option from the keyboard.")
        return BIBLE_GAME_DIFFICULTY

    difficulty = difficulty_map[user_input]

    # Reset session data when switching difficulties
    if context.user_data.get('current_difficulty') != difficulty:
        context.user_data['bible_game_score'] = 0
        context.user_data['bible_game_total'] = 0
        context.user_data['used_verses'] = []

    context.user_data['current_difficulty'] = difficulty  # Store current difficulty
    user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) chose {difficulty} difficulty")

    # Generate a question
    await update.message.reply_text("🔄 Loading Bible verse...", reply_markup=ReplyKeyboardRemove())

    used_verses = context.user_data.get('used_verses', [])
    current_language = context.user_data.get('current_language', 'english')
    question = create_bible_question(difficulty, used_verses, current_language)
    if not question:
        await update.message.reply_text(
            "❌ Sorry, I couldn't load a Bible verse right now. Please try again with /games",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END

    # Store question in context and track used verse
    context.user_data['current_question'] = question
    context.user_data['used_verses'].append(question['reference'])

    # Display the question
    question_text = (
        f"📖 *Bible Game - {difficulty} Level*\n\n"
        f"*Here's your verse:*\n\n"
        f"_{question['verse_text']}_\n\n"
        f"*Which Bible reference is this verse from?*"
    )

    # Create answer options keyboard
    keyboard = []
    for i, option in enumerate(question['options']):
        keyboard.append([f"{chr(65+i)}) {option}"])
    keyboard.append(["❌ Cancel"])

    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)

    await update.message.reply_text(question_text, parse_mode="Markdown", reply_markup=reply_markup)
    return BIBLE_GAME_QUESTION

async def bible_game_question_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle answer selection"""
    user_input = update.message.text.strip()
    user = update.effective_user

    if user_input == "❌ Cancel":
        # Save score if user answered at least one question in current difficulty
        score = context.user_data.get('bible_game_score', 0)
        total = context.user_data.get('bible_game_total', 0)
        current_difficulty = context.user_data.get('current_difficulty')

        if total > 0 and current_difficulty:
            save_game_score(user.full_name or user.username or "Unknown", user.id, score, current_difficulty)

        await update.message.reply_text("Bible game cancelled. Type /games to play again!", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    # Get the current question
    question = context.user_data.get('current_question')
    if not question:
        await update.message.reply_text("❌ Something went wrong. Please start a new game with /games", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    # Parse the user's answer (remove the letter prefix)
    if len(user_input) > 3 and user_input[1:3] == ") ":
        selected_answer = user_input[3:]
    else:
        await update.message.reply_text("Please select a valid option from the keyboard.")
        return BIBLE_GAME_QUESTION

    # Check if the answer is correct
    correct_answer = question['correct_answer']
    is_correct = selected_answer == correct_answer

    # Update score
    context.user_data['bible_game_total'] += 1
    if is_correct:
        context.user_data['bible_game_score'] += 1

    # Log the answer
    user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) answered {selected_answer} - {'Correct' if is_correct else 'Wrong'}")

    # Prepare response
    if is_correct:
        result_text = f"🎉 *Correct!* ✅\n\nThe answer is indeed *{correct_answer}*"
    else:
        result_text = f"❌ *Wrong!*\n\nThe correct answer is *{correct_answer}*"

    # Show current stats
    score = context.user_data['bible_game_score']
    total = context.user_data['bible_game_total']
    accuracy = (score / total * 100) if total > 0 else 0

    stats_text = f"\n\n📊 *Your Stats:* {score}/{total} correct ({accuracy:.1f}%)"

    # Send the result first
    await update.message.reply_text(
        result_text + stats_text,
        parse_mode="Markdown"
    )

    # Clear current question
    context.user_data['current_question'] = None

    # Automatically generate next question with same difficulty
    current_difficulty = question['difficulty']

    # Show loading message
    await update.message.reply_text("🔄 Loading next Bible verse...")

    # Generate new question, avoiding duplicates
    used_verses = context.user_data.get('used_verses', [])
    current_language = context.user_data.get('current_language', 'english')
    new_question = create_bible_question(current_difficulty, used_verses, current_language)
    if not new_question:
        # If failed to load, go back to difficulty selection
        keyboard = [
            ["🟢 Easy", "🟡 Medium", "🔴 Hard"],
            ["📊 View Stats", "🔄 Reset Score"],
            ["❌ Quit Game"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)

        await update.message.reply_text(
            "❌ Sorry, I couldn't load the next Bible verse. Please choose difficulty again:",
            reply_markup=reply_markup
        )
        return BIBLE_GAME_DIFFICULTY

    # Store new question in context and track used verse
    context.user_data['current_question'] = new_question
    context.user_data['used_verses'].append(new_question['reference'])

    # Display the new question
    question_text = (
        f"📖 *Bible Game - {current_difficulty} Level*\n\n"
        f"*Here's your verse:*\n\n"
        f"_{new_question['verse_text']}_\n\n"
        f"*Which Bible reference is this verse from?*"
    )

    # Create answer options keyboard
    keyboard = []
    for i, option in enumerate(new_question['options']):
        keyboard.append([f"{chr(65+i)}) {option}"])
    keyboard.append(["❌ Cancel"])

    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)

    await update.message.reply_text(question_text, parse_mode="Markdown", reply_markup=reply_markup)
    return BIBLE_GAME_QUESTION

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
THEME_TYPE = 0  # New state for choosing Hymns or Lyrics
THEME_SELECTION = 1
YEAR_FILTER = 2

# Add a new state for typo confirmation
TYPO_CONFIRM = 99

# Simplified theme function - similar to oldbot.py.bak
async def theme_type_choice(update: Update, context: CallbackContext) -> int:
    """
    Start theme filtering - simplified version like oldbot.py.bak
    Lists available unique themes and prompts user to choose.
    """
    user = update.effective_user
    user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) sent /theme")

    # Get unique themes from the DataFrame, splitting by comma if necessary (like oldbot)
    data = get_all_data()
    dfH = data["dfH"]
    all_themes = dfH["Themes"].dropna().str.split(",").explode().str.strip().unique()
    themes = sorted(all_themes)

    # Build keyboard layout (2 themes per row) - exactly like oldbot
    keyboard = [themes[i:i+2] for i in range(0, len(themes), 2)]

    await update.message.reply_text(
        "🎯 *Available Themes:*\nPlease select or type one of the themes below:",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    )

    return THEME_SELECTION  # Skip THEME_TYPE, go directly to selection









# Simplified theme selection - like oldbot.py.bak
async def handle_theme_selection(update: Update, context: CallbackContext) -> int:
    """
    Handles the user's theme selection by filtering the hymns,
    displays them grouped as known/unknown, and then asks
    if the user wants to filter by year.
    """
    theme_input = update.message.text.strip()
    # Save theme in user_data for later
    context.user_data["theme_input"] = theme_input

    # Use simple filtering like oldbot.py.bak
    data = get_all_data()
    dfH = data["dfH"]
    df = data["df"]
    dfL = data["dfL"]
    dfC = data["dfC"]

    # Get vocabularies
    _, Hymn_Vocabulary, Lyric_Vocabulary, _ = ChoirVocabulary(df, dfH, dfL, dfC)

    filtered_df = filter_hymns_by_theme(dfH, theme_input)

    if filtered_df.empty:
        await update.message.reply_text(
            f"😕 No hymns found for theme: *{theme_input}*",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END

    # Instead of storing formatted strings, store raw hymn numbers (like oldbot)
    known_hymns = []
    unknown_hymns = []

    for _, row in filtered_df.iterrows():
        hymn_no = row["Hymn no"]
        if hymn_no in Hymn_Vocabulary.values:
            known_hymns.append(hymn_no)
        else:
            unknown_hymns.append(hymn_no)

    # Build display lines for known and unknown hymns (show ALL, no limits) - like oldbot
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
    context.user_data["known_items"] = known_hymns
    context.user_data["unknown_items"] = unknown_hymns

    # Ask the user if they want to filter by year (like oldbot)
    await update.message.reply_text(
        "📅 Do you want to filter these hymns to see Songs Sung this year?",
        reply_markup=ReplyKeyboardMarkup([["Yes", "No"]], one_time_keyboard=True, resize_keyboard=True)
    )
    return YEAR_FILTER



# Step 3: Ask the user if they want year filtering (now supports both Hymns and Lyrics)
async def handle_year_filter(update: Update, context: CallbackContext) -> int:
    reply = update.message.text.strip().lower()
    if reply != "yes":
        await update.message.reply_text("Okay! No year filtering applied.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    s_year = datetime.now().year  # Automatically get current year
    data = get_all_data()
    theme_type = "hymns"  # Simplified to hymns only like oldbot.py.bak
    theme = context.user_data.get("theme_input", "")
    known = context.user_data.get("known_items", [])
    unknown = context.user_data.get("unknown_items", [])

    # Simplified to hymns only like oldbot.py.bak
    dfH = data["dfH"]

    def get_last_sung_date(song_code):
        result = Datefinder(songs=song_code, first=True)
        if result and len(result) >= 10:
            try:
                return datetime.strptime(result[-10:], "%d/%m/%Y")
            except:
                return None
        return None

    # Group by year: Expect hymn_list to contain raw hymn numbers (like oldbot.py.bak)
    def group_by_year(hymn_list):
        sung, not_sung = [], []
        for h in hymn_list:
            hymn_code = f"H-{h}"
            date_obj = get_last_sung_date(hymn_code)
            # Retrieve hymn index and tune from DataFrame
            index = dfH[dfH['Hymn no'] == h]['Hymn Index'].values[0]
            tune = dfH[dfH['Hymn no'] == h]['Tunes'].values[0]
            if date_obj and date_obj.year == s_year:
                sung.append(f"{hymn_code} - {index}  -{tune}")
            else:
                not_sung.append(f"{hymn_code} - {index} -{tune}")
        return sung, not_sung

    sung_known, not_sung_known = group_by_year(known)
    not_sung_unknown = group_by_year(unknown)[1]

    message_parts = [f"📅 *Theme:* `{theme}` – *Year:* {s_year}"]

    # Add the three categories like oldbot.py.bak
    if sung_known:
        message_parts.append(f"✅ *Songs that were Sung ({len(sung_known)} total):*\n" + "\n".join(sung_known))

    if not_sung_known:
        message_parts.append(f"❌ *Songs that were Not Sung ({len(not_sung_known)} total):*\n" + "\n".join(not_sung_known))

    if not_sung_unknown:
        message_parts.append(f"🚫 *Songs Choir Doesn't Know ({len(not_sung_unknown)} total):*\n" + "\n".join(not_sung_unknown))

    # Add the total count
    total_known = len(known)
    total_unknown = len(unknown)
    message_parts.append(f"📊 *Total {theme_type.capitalize()} in this theme:*\n"
                         f"✅ Known: {total_known}\n"
                         f"❌ Unknown: {total_unknown}")

    await send_long_message(update, message_parts)
    return ConversationHandler.END

# --- Conversation States ---
# Example: CHECK_SONG, ENTER_SONG, etc.
# TODO: Define all necessary states for conversations

# --- Conversation Flows ---
# TODO: Implement conversation entry points and state handlers for each major conversation 

print("Reached Telegram Bot code")
 

#Telegram bot
 
 
 
#/check

 







 



    



 #/comment

COMMENT, REPLY, ADMIN_REPLY_MESSAGE = range(3)

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
        print("✅ Comment successfully send.")
    except Exception as e:
        logging.error(f"❌ Failed to comment: {e}")

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

        await update.message.reply_text(f"✅ Reply sent to user.")
    except Exception as e:
        logging.error(f"❌ Failed to send reply: {e}")
        await update.message.reply_text(f"❌ Failed to send reply: {e}")

# New Admin Reply System Handlers

async def handle_admin_reply_selection(update: Update, context: CallbackContext) -> int:
    """Handle when admin selects a user or 'all users' to reply to"""
    query = update.callback_query
    await query.answer()

    # Check if user is admin
    config = get_config()
    admin_id = config.ADMIN_ID
    if query.from_user.id != admin_id:
        await query.message.reply_text("❌ You are not authorized to use this command.")
        return ConversationHandler.END

    data = query.data

    if data == "reply_all":
        # Admin wants to send to all users
        context.user_data["reply_target"] = "all"
        await query.message.reply_text(
            "📢 <b>Send message to ALL users</b>\n\n"
            "Type your message below. This will be sent to all users in the database:",
            parse_mode="HTML"
        )
        return ADMIN_REPLY_MESSAGE

    elif data.startswith("reply_user_"):
        # Admin wants to send to specific user
        user_id = data.split("_")[2]
        context.user_data["reply_target"] = user_id

        # Get user info for confirmation
        users = get_all_users()
        target_user = next((u for u in users if str(u['user_id']) == user_id), None)

        if target_user:
            await query.message.reply_text(
                f"👤 <b>Send message to: {target_user['display_name']}</b>\n\n"
                "Type your message below:",
                parse_mode="HTML"
            )
        else:
            await query.message.reply_text(
                f"👤 <b>Send message to User ID: {user_id}</b>\n\n"
                "Type your message below:",
                parse_mode="HTML"
            )
        return ADMIN_REPLY_MESSAGE

    elif data == "reply_more":
        await query.message.reply_text(
            "ℹ️ To see more users or send to a specific user ID, use the old format:\n"
            "<code>/reply &lt;user_id&gt; &lt;message&gt;</code>",
            parse_mode="HTML"
        )
        return ConversationHandler.END

    return ConversationHandler.END

async def handle_admin_reply_message(update: Update, context: CallbackContext) -> int:
    """Handle the admin's reply message"""
    # Check if user is admin
    config = get_config()
    admin_id = config.ADMIN_ID
    if update.effective_user.id != admin_id:
        await update.message.reply_text("❌ You are not authorized to use this command.")
        return ConversationHandler.END

    message = update.message.text
    reply_target = context.user_data.get("reply_target")

    if not reply_target:
        await update.message.reply_text("❌ No target selected. Please start over with /reply")
        return ConversationHandler.END

    try:
        if reply_target == "all":
            # Send to all users
            users = get_all_users()
            sent_count = 0
            failed_count = 0

            for user_info in users:
                try:
                    await context.bot.send_message(
                        chat_id=user_info['user_id'],
                        text=f"📢 <b>Message from Admin:</b>\n\n{message}",
                        parse_mode="HTML"
                    )
                    sent_count += 1
                except Exception as e:
                    failed_count += 1
                    logging.error(f"Failed to send message to user {user_info['user_id']}: {e}")

            await update.message.reply_text(
                f"✅ <b>Broadcast completed!</b>\n\n"
                f"📤 Sent to: {sent_count} users\n"
                f"❌ Failed: {failed_count} users",
                parse_mode="HTML"
            )
        else:
            # Send to specific user
            await context.bot.send_message(
                chat_id=int(reply_target),
                text=f"💬 <b>Admin's reply:</b>\n\n{message}",
                parse_mode="HTML"
            )
            await update.message.reply_text(f"✅ Reply sent to user {reply_target}.")

    except Exception as e:
        logging.error(f"❌ Failed to send reply: {e}")
        await update.message.reply_text(f"❌ Failed to send reply: {e}")

    return ConversationHandler.END



 

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

