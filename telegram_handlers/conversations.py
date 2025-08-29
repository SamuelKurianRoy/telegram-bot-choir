# telegram/conversations.py
# ConversationHandler states and flows
import pandas as pd
import streamlit as st
from telegram import Update, ReplyKeyboardRemove, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext, ConversationHandler, ContextTypes
from config import get_config
from logging_utils import setup_loggers
import logging

# Set up logger
logger = logging.getLogger(__name__)
from PyPDF2 import PdfMerger
import tempfile
# Import isVocabulary from the appropriate module
from data.vocabulary import ChoirVocabulary, isVocabulary, standardize_hlc_value
from utils.search import find_best_match, search_index
from utils.notation import Music_notation_link, getNotation
from data.datasets import Tunenofinder, Tune_finder_of_known_songs, Datefinder, IndexFinder, Hymn_Tune_no_Finder, get_all_data
from telegram_handlers.utils import get_wordproject_url_from_input, extract_bible_chapter_text, clean_bible_text
from data.drive import save_game_score, get_user_best_score, get_user_best_scores_all_difficulties, get_leaderboard, get_combined_leaderboard
from data.udb import get_user_bible_language, get_user_game_language, get_user_download_preference, get_user_download_quality, track_user_fast
import re
import os
import random
import requests
from data.drive import get_drive_service, append_download_to_google_doc, get_docs_service
from googleapiclient.http import MediaIoBaseDownload
from datetime import datetime
import io
from telegram_handlers.handlers import is_authorized
from downloader import AudioDownloader
import logging
import asyncio
from telegram.constants import ParseMode
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
from rapidfuzz import process, fuzz

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
    """Download PDF file from Google Drive using proper API"""
    try:
        save_path = os.path.join(LYRICS_DOWNLOAD_DIR, filename)

        # Use Google Drive API for proper download
        request = drive_service.files().get_media(fileId=file_id)
        file_data = io.BytesIO()
        downloader = MediaIoBaseDownload(file_data, request)

        done = False
        while not done:
            status, done = downloader.next_chunk()

        # Write the downloaded content to file
        file_data.seek(0)
        with open(save_path, 'wb') as f:
            f.write(file_data.read())

        # Verify the file was downloaded correctly
        if os.path.exists(save_path) and os.path.getsize(save_path) > 0:
            return save_path
        else:
            print(f"Failed to download or verify PDF: {filename}")
            return None

    except Exception as e:
        print(f"Error downloading PDF {filename}: {str(e)}")
        return None

def validate_pdf_file(file_path):
    """Validate that the downloaded file is a proper PDF"""
    try:
        if not os.path.exists(file_path):
            return False

        # Check file size
        if os.path.getsize(file_path) < 100:  # PDF files should be at least 100 bytes
            return False

        # Check PDF header
        with open(file_path, 'rb') as f:
            header = f.read(4)
            if header != b'%PDF':
                return False

        return True
    except Exception as e:
        print(f"Error validating PDF {file_path}: {str(e)}")
        return False

def get_lyrics_pdf_by_lyric_number(lyric_number, lyrics_file_map):
    lyric_number = int(lyric_number)
    if lyric_number in lyrics_file_map:
        file_id = lyrics_file_map[lyric_number]
        filename = f"L-{lyric_number}.pdf"
        pdf_path = download_lyrics_pdf(file_id, filename)

        # Validate the downloaded PDF
        if pdf_path and validate_pdf_file(pdf_path):
            return pdf_path
        else:
            print(f"Invalid PDF downloaded for L-{lyric_number}")
            # Clean up invalid file
            if pdf_path and os.path.exists(pdf_path):
                os.remove(pdf_path)
            return None
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

        try:
            pdf_path = get_lyrics_pdf_by_lyric_number(lyric_number, lyrics_file_map)
            await downloading_msg.delete()

            if pdf_path and os.path.exists(pdf_path):
                # Verify file size before sending
                file_size = os.path.getsize(pdf_path)
                if file_size > 50 * 1024 * 1024:  # 50MB limit for Telegram
                    await update.message.reply_text(f"❌ PDF file for L-{lyric_number} is too large to send via Telegram.")
                else:
                    with open(pdf_path, 'rb') as pdf_file:
                        await update.message.reply_document(
                            document=pdf_file,
                            filename=f"L-{lyric_number}.pdf",
                            caption=f"Here is the notation for Lyric L-{lyric_number}."
                        )
                    # Clean up the downloaded file after sending
                    try:
                        os.remove(pdf_path)
                    except:
                        pass  # Ignore cleanup errors
            else:
                await update.message.reply_text(f"❌ Could not find or download notation PDF for Lyric L-{lyric_number}.")
        except Exception as e:
            await downloading_msg.delete()
            await update.message.reply_text(f"❌ Error processing L-{lyric_number}: {str(e)}")
            print(f"Error processing L-{lyric_number}: {str(e)}")

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
    """Download PDF file from Google Drive using proper API"""
    try:
        save_path = os.path.join(DOWNLOAD_DIR, filename)

        # Use Google Drive API for proper download
        request = drive_service.files().get_media(fileId=file_id)
        file_data = io.BytesIO()
        downloader = MediaIoBaseDownload(file_data, request)

        done = False
        while not done:
            status, done = downloader.next_chunk()

        # Write the downloaded content to file
        file_data.seek(0)
        with open(save_path, 'wb') as f:
            f.write(file_data.read())

        # Verify the file was downloaded correctly
        if os.path.exists(save_path) and os.path.getsize(save_path) > 0:
            return save_path
        else:
            print(f"Failed to download or verify PDF: {filename}")
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

         # Validate the downloaded PDF
         if downloaded_path and validate_pdf_file(downloaded_path):
             return downloaded_path
         else:
             print(f"Failed to download or verify PDF for page {page_number}")
             # Clean up invalid file
             if downloaded_path and os.path.exists(downloaded_path):
                 os.remove(downloaded_path)
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
            # Verify file size before sending
            file_size = os.path.getsize(pdf_files[0])
            if file_size > 50 * 1024 * 1024:  # 50MB limit for Telegram
                await context.bot.send_message(chat_id=chat_id, text=f"❌ PDF file for {song_id} ({tune_name}) is too large to send via Telegram.")
            else:
                with open(pdf_files[0], 'rb') as pdf_file:
                    await context.bot.send_document(
                        chat_id=chat_id,
                        document=pdf_file,
                        filename=f"{song_id}_{tune_name}.pdf",
                        caption=f"Notation for {song_id} ({tune_name})"
                    )
        else:
            # If there are multiple pages, merge them
            merger = PdfMerger()
            try:
                for pdf in pdf_files:
                    # Validate each PDF before merging
                    if validate_pdf_file(pdf):
                        merger.append(pdf)
                    else:
                        print(f"Skipping invalid PDF: {pdf}")

                # Create a temporary file for the merged PDF
                with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_file:
                    merger.write(tmp_file.name)
                    merger.close()

                    # Check merged file size
                    merged_size = os.path.getsize(tmp_file.name)
                    if merged_size > 50 * 1024 * 1024:  # 50MB limit
                        await context.bot.send_message(chat_id=chat_id, text=f"❌ Merged PDF for {song_id} ({tune_name}) is too large to send via Telegram.")
                    else:
                        # Send the merged PDF
                        with open(tmp_file.name, 'rb') as merged_pdf:
                            await context.bot.send_document(
                                chat_id=chat_id,
                                document=merged_pdf,
                                filename=f"{song_id}_{tune_name}_complete.pdf",
                                caption=f"Complete notation for {song_id} ({tune_name}) - {len(pdf_files)} pages"
                            )

                    # Clean up the temporary file
                    os.unlink(tmp_file.name)
            except Exception as merge_error:
                merger.close()
                await context.bot.send_message(chat_id=chat_id, text=f"❌ Error merging PDFs: {str(merge_error)}")
                print(f"Error merging PDFs: {str(merge_error)}")

        # Clean up downloaded files after sending
        for pdf_file in pdf_files:
            try:
                if os.path.exists(pdf_file):
                    os.remove(pdf_file)
            except:
                pass  # Ignore cleanup errors

    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Error processing PDFs: {str(e)}")
        print(f"Error processing PDFs: {str(e)}")  # For debugging



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
ENTER_URL, SELECT_QUALITY, PLAYLIST_CHOICE = range(2, 5)

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

    # Debug: Log the raw input
    bot_logger.info(f"Raw URL input from {user.full_name}: '{user_input}' (length: {len(user_input)})")

    # Basic validation
    if not user_input or len(user_input) < 10:
        await update.message.reply_text(
            "❌ Invalid URL. Please send a complete YouTube or Spotify link.",
            reply_markup=ReplyKeyboardRemove()
        )
        return ENTER_URL

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

    # Debug: Log what was stored
    bot_logger.info(f"Stored URL in context: '{user_input}', Platform: {context.user_data['platform']}")

    # Check for playlist in YouTube URLs
    if context.user_data["platform"] == "YouTube" and ("list=" in user_input or "playlist" in user_input.lower()):
        # Get user's download preference
        download_pref = get_user_download_preference(user.id)

        if download_pref == 'single':
            # User prefers single video - automatically set preference and continue
            context.user_data["download_playlist"] = False
            await update.message.reply_text(
                "🎯 *YouTube Playlist Detected!*\n\n"
                "✅ Based on your settings, downloading *single video only*.\n"
                "The playlist will be ignored.\n\n"
                "💡 You can change this behavior in `/setting` → `📥 Download Behavior`",
                parse_mode="Markdown"
            )
        else:
            # User prefers to be asked - show playlist options
            playlist_keyboard = [
                ["🎵 Download Single Video Only"],
                ["📋 Download Entire Playlist"],
                ["❌ Cancel"]
            ]

            await update.message.reply_text(
                f"🎯 *YouTube Playlist Detected!*\n\n"
                f"This link contains a playlist. What would you like to do?\n\n"
                f"⚠️ *Warning:* Downloading entire playlists can take a very long time and may contain many videos.",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardMarkup(playlist_keyboard, one_time_keyboard=True, resize_keyboard=True)
            )
            return PLAYLIST_CHOICE

    # No playlist detected - check quality preference
    quality_pref = get_user_download_quality(user.id)

    if quality_pref in ['high', 'medium', 'low']:
        # User has a quality preference - use it directly
        context.user_data["download_quality"] = quality_pref

        quality_display = {
            'high': 'High Quality (320kbps)',
            'medium': 'Medium Quality (192kbps)',
            'low': 'Low Quality (128kbps)'
        }

        await update.message.reply_text(
            f"🎯 *{context.user_data['platform']} link detected!*\n\n"
            f"✅ Using your preferred quality: *{quality_display[quality_pref]}*\n\n"
            "Starting download...\n\n"
            "💡 You can change your default quality in `/setting` → `🎵 Download Quality`",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove()
        )

        # Skip quality selection and start download directly
        return await start_download_process(update, context)
    else:
        # User prefers to be asked - show quality selection
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

async def download_playlist_choice(update: Update, context: CallbackContext) -> int:
    """Handle playlist choice selection"""
    choice = update.message.text.strip()
    user = update.effective_user

    if choice == "❌ Cancel":
        await update.message.reply_text(
            "❌ Download cancelled.",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END

    # Store playlist preference
    if choice == "🎵 Download Single Video Only":
        context.user_data["download_playlist"] = False
        await update.message.reply_text(
            "✅ *Single video download selected*\n\n"
            "Only the specific video will be downloaded, ignoring the playlist.",
            parse_mode="Markdown"
        )
    elif choice == "📋 Download Entire Playlist":
        context.user_data["download_playlist"] = True
        await update.message.reply_text(
            "✅ *Playlist download selected*\n\n"
            "⚠️ *Warning:* This may take a very long time and download many files. "
            "Please be patient and ensure you have enough storage space.",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            "❌ Invalid selection. Please choose from the options provided.",
            reply_markup=ReplyKeyboardRemove()
        )
        return PLAYLIST_CHOICE

    # Check quality preference after playlist choice
    quality_pref = get_user_download_quality(user.id)

    if quality_pref in ['high', 'medium', 'low']:
        # User has a quality preference - use it directly
        context.user_data["download_quality"] = quality_pref

        quality_display = {
            'high': 'High Quality (320kbps)',
            'medium': 'Medium Quality (192kbps)',
            'low': 'Low Quality (128kbps)'
        }

        await update.message.reply_text(
            f"🎯 *{context.user_data['platform']} link ready!*\n\n"
            f"✅ Using your preferred quality: *{quality_display[quality_pref]}*\n\n"
            "Starting download...\n\n"
            "💡 You can change your default quality in `/setting` → `🎵 Download Quality`",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove()
        )

        # Skip quality selection and start download directly
        return await start_download_process(update, context)
    else:
        # User prefers to be asked - show quality selection
        quality_keyboard = [
            ["🔥 High Quality (320kbps)", "🎵 Medium Quality (192kbps)"],
            ["💾 Low Quality (128kbps)", "❌ Cancel"]
        ]

        await update.message.reply_text(
            f"🎯 *{context.user_data['platform']} link ready!*\n\n"
            "Please select the audio quality:",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(quality_keyboard, one_time_keyboard=True, resize_keyboard=True)
        )
        return SELECT_QUALITY

async def start_download_process(update: Update, context: CallbackContext) -> int:
    """Start the download process with user's preferred settings"""
    user = update.effective_user

    # Get download parameters from context
    url = context.user_data.get("download_url")
    platform = context.user_data.get("platform")
    quality = context.user_data.get("download_quality")

    # Debug: Check if URL got corrupted
    bot_logger.info(f"Retrieved from context - URL: '{url}' (length: {len(url) if url else 'None'}), Platform: {platform}, Quality: {quality}")

    # Validate URL before proceeding
    if not url or len(url) < 10:
        await update.message.reply_text(
            "❌ **Download Error**\n\n"
            "The URL appears to be corrupted or missing. Please try again:\n"
            "1. Send /download command\n"
            "2. Paste the complete YouTube or Spotify URL\n"
            "3. Select your preferences",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END

    # Map quality to display text
    quality_display_map = {
        "high": "🔥 High Quality (320kbps)",
        "medium": "🎵 Medium Quality (192kbps)",
        "low": "💾 Low Quality (128kbps)"
    }
    quality_text = quality_display_map.get(quality, f"{quality} quality")

    # Start download process (same logic as download_quality_selection)
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

        # Get playlist preference (default to single video for safety)
        download_playlist = context.user_data.get("download_playlist", False)

        # Check if this is a playlist download
        if download_playlist and platform == "YouTube":
            # For playlist downloads, use progressive delivery
            await update.message.reply_text(
                "📋 **Playlist download started!**\n\n"
                "🎵 Audio files will be sent to you as they are downloaded. "
                "This may take some time depending on the playlist size.\n\n"
                "💡 You can continue using other bot features while downloading.",
                parse_mode="Markdown"
            )

            # Use progressive playlist download
            success_count = 0
            failed_count = 0

            async for result in downloader.download_playlist_progressive(url, quality, chat_id=chat_id):
                if result is None:
                    failed_count += 1
                    await update.message.reply_text(f"❌ Failed to download audio #{success_count + failed_count}")
                    continue

                file_path, file_info = result
                success_count += 1

                try:
                    # Send the audio file
                    with open(file_path, 'rb') as audio_file:
                        caption = f"🎵 **{file_info.get('title', 'Unknown Title')}**\n" \
                                f"👤 **Artist:** {file_info.get('artist', 'Unknown Artist')}\n" \
                                f"🎯 **Quality:** {quality_text}\n" \
                                f"📊 **Progress:** {success_count}/{success_count + failed_count}"

                        await context.bot.send_audio(
                            chat_id=chat_id,
                            audio=audio_file,
                            caption=caption,
                            parse_mode="Markdown",
                            title=file_info.get('title', 'Unknown Title'),
                            performer=file_info.get('artist', 'Unknown Artist')
                        )

                    # Clean up the file
                    file_path.unlink(missing_ok=True)

                except Exception as send_error:
                    await update.message.reply_text(f"❌ Failed to send audio #{success_count}: {send_error}")

            # Send final summary
            if success_count > 0:
                await update.message.reply_text(
                    f"✅ **Playlist download completed!**\n\n"
                    f"📊 **Summary:**\n"
                    f"✅ Successfully downloaded: {success_count} files\n"
                    f"❌ Failed downloads: {failed_count} files\n\n"
                    f"🎵 All audio files have been sent to you.",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text(
                    "❌ **Playlist download failed**\n\n"
                    "No audio files could be downloaded from the playlist. "
                    "Please check the URL and try again.",
                    parse_mode="Markdown"
                )

        else:
            # Single video download
            # Debug: Log the URL being passed
            bot_logger.info(f"Telegram handler passing URL to downloader: '{url}' (length: {len(url) if url else 'None'})")
            user_logger.info(f"Download request from {user.full_name}: URL='{url}', Quality={quality}")

            # Start download in background task to avoid blocking other commands
            await update.message.reply_text(
                "🎵 **Download started!**\n\n"
                "⏳ Your audio is being processed in the background.\n"
                "📱 You can continue using other bot commands while waiting.\n"
                "🔔 I'll send you the file when it's ready!\n\n"
                "⚠️ *Note: Downloads may take 2-5 minutes depending on video length.*",
                parse_mode="Markdown"
            )

            # Create background task for download
            asyncio.create_task(
                background_download_task(
                    downloader, url, quality, str(chat_id), download_playlist,
                    update, context, user, platform
                )
            )

    except Exception as e:
        bot_logger.error(f"Error starting background download: {e}")
        await update.message.reply_text(
            "❌ **Error starting download**\n\n"
            "There was an issue starting your download. Please try again.",
            parse_mode="Markdown"
        )

    return ConversationHandler.END


async def background_download_task(downloader, url, quality, chat_id, download_playlist, update, context, user, platform):
    """Background task to handle downloads without blocking other commands"""
    try:
        bot_logger.info(f"Background download started for user {user.full_name}: {url}")
        bot_logger.info(f"Environment: Streamlit Cloud = {getattr(downloader, 'is_streamlit_cloud', 'Unknown')}")

        # Quick network connectivity test
        try:
            import socket
            socket.setdefaulttimeout(5)
            socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(('8.8.8.8', 53))
            bot_logger.info("Background task: Basic internet connectivity confirmed")

            # Test YouTube DNS resolution
            try:
                youtube_ip = socket.gethostbyname('www.youtube.com')
                bot_logger.info(f"Background task: YouTube DNS resolution successful: {youtube_ip}")
            except Exception as dns_e:
                bot_logger.error(f"Background task: YouTube DNS resolution failed: {dns_e}")

        except Exception as net_e:
            bot_logger.error(f"Background task: Network connectivity issue: {net_e}")

        # Perform the download
        bot_logger.info("Background task: Starting download_audio call...")
        result = await downloader.download_audio(url, quality, chat_id=chat_id, download_playlist=download_playlist)
        bot_logger.info(f"Background task: download_audio returned: {result is not None}")

        if result:
            file_path, file_info = result

            # Map quality for display
            quality_map = {"high": "🔥 High (320kbps)", "medium": "🎵 Medium (192kbps)", "low": "💾 Low (128kbps)"}
            quality_text = quality_map.get(quality, quality)

            # Send the audio file
            with open(file_path, 'rb') as audio_file:
                caption = f"🎵 **{file_info.get('title', 'Unknown Title')}**\n" \
                        f"👤 **Artist:** {file_info.get('artist', 'Unknown Artist')}\n" \
                        f"🎯 **Quality:** {quality_text}\n" \
                        f"🌐 **Platform:** {file_info.get('platform', platform)}"

                await context.bot.send_audio(
                    chat_id=int(chat_id),
                    audio=audio_file,
                    caption=caption,
                    parse_mode="Markdown",
                    title=file_info.get('title', 'Unknown Title'),
                    performer=file_info.get('artist', 'Unknown Artist')
                )

            # Clean up the file
            file_path.unlink(missing_ok=True)

            await context.bot.send_message(
                chat_id=int(chat_id),
                text="✅ **Download completed successfully!**\n\n🎵 Your audio file has been sent above.",
                parse_mode="Markdown"
            )

            bot_logger.info(f"Background download completed successfully for user {user.full_name}")

        else:
            # Download failed
            error_message = "❌ **Download failed**\n\nPlease try again with a different link or try again later."

            await context.bot.send_message(
                chat_id=int(chat_id),
                text=error_message,
                parse_mode="Markdown"
            )

            bot_logger.warning(f"Background download failed for user {user.full_name}: {url}")

    except Exception as e:
        bot_logger.error(f"Background download task error for user {user.full_name}: {e}")
        bot_logger.error(f"Full error details: {repr(e)}")
        bot_logger.error(f"Error type: {type(e).__name__}")

        # Log specific error patterns for debugging
        error_str = str(e).lower()
        if "failed to resolve" in error_str:
            bot_logger.error("DNS resolution error detected in background task")
        elif "timeout" in error_str:
            bot_logger.error("Timeout error detected in background task")
        elif "403" in error_str or "forbidden" in error_str:
            bot_logger.error("Access forbidden error detected in background task")

        # Send error message to user
        try:
            error_message = f"❌ **Download Error**\n\nAn error occurred during download: {str(e)[:100]}{'...' if len(str(e)) > 100 else ''}"
            await context.bot.send_message(
                chat_id=int(chat_id),
                text=error_message,
                parse_mode="Markdown"
            )
        except Exception as send_error:
            bot_logger.error(f"Failed to send error message to user: {send_error}")

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
    context.user_data["download_quality"] = quality

    # Use the centralized download process
    return await start_download_process(update, context)


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

    # Get user's preferred game language
    user_game_lang = get_user_game_language(user.id)
    default_lang_display = "🇮🇳 Malayalam" if user_game_lang == 'malayalam' else "🇺🇸 English"

    # Show welcome message and options
    welcome_text = (
        "📖 *Welcome to the Bible Game!* 🎮\n\n"
        "Test your Bible knowledge! I'll show you a verse, and you need to guess which Bible reference it's from.\n\n"
        f"🏆 *Your Best Scores:*\n"
        f"🟢 Easy: {user_best_scores['Easy']}\n"
        f"🟡 Medium: {user_best_scores['Medium']}\n"
        f"🔴 Hard: {user_best_scores['Hard']}\n\n"
        f"Your default game language is *{user_game_lang.title()}*.\n\n"
        "Choose an option below:"
    )

    # Create keyboard with single Language button and Start button
    keyboard = [
        [f"🌐 Language ({user_game_lang.title()})", "🎯 Start Game"],
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

    # Handle Language button - show language selection options
    if user_input.startswith("🌐 Language"):
        current_lang = get_user_game_language(user.id)

        language_selection_text = (
            "🌐 *Choose Game Language*\n\n"
            f"Current default: *{current_lang.title()}*\n\n"
            "Select your preferred language for this game:"
        )

        # Show language options with current default highlighted
        if current_lang == 'malayalam':
            keyboard = [
                ["🇺🇸 English", "⭐ 🇮🇳 Malayalam (Default)"],
                ["🔙 Back to Menu", "❌ Cancel"]
            ]
        else:  # English is default
            keyboard = [
                ["⭐ 🇺🇸 English (Default)", "🇮🇳 Malayalam"],
                ["🔙 Back to Menu", "❌ Cancel"]
            ]

        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
        await update.message.reply_text(language_selection_text, parse_mode="Markdown", reply_markup=reply_markup)
        return BIBLE_GAME_LANGUAGE

    # Handle Start Game button - use user's default language
    if user_input == "🎯 Start Game":
        # Use user's preferred game language
        language = get_user_game_language(user.id)
        context.user_data['current_language'] = language
        user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) started game with default language: {language}")

        # Skip to difficulty selection
        difficulty_text = (
            f"🎯 *Choose Difficulty Level* ({language.title()})\n\n"
            "🟢 *Easy:* Common verses, basic books\n"
            "🟡 *Medium:* Mix of familiar and challenging verses\n"
            "🔴 *Hard:* Difficult verses, less common books\n\n"
            "Select your difficulty:"
        )

        keyboard = [
            ["🟢 Easy", "🟡 Medium", "🔴 Hard"],
            ["🔙 Back", "❌ Cancel"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)

        await update.message.reply_text(difficulty_text, parse_mode="Markdown", reply_markup=reply_markup)
        return BIBLE_GAME_DIFFICULTY

    # Handle Back to Menu button - return to main game menu
    if user_input == "🔙 Back to Menu":
        return await bible_game_start(update, context)

    # Handle language selection from the language selection screen
    language_map = {
        "🇺🇸 English": "english",
        "🇮🇳 Malayalam": "malayalam",
        "⭐ 🇺🇸 English (Default)": "english",
        "⭐ 🇮🇳 Malayalam (Default)": "malayalam"
    }

    if user_input in language_map:
        language = language_map[user_input]
        context.user_data['current_language'] = language
        user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) chose {language} language")

        # After selecting language, go to difficulty selection
        difficulty_text = (
            f"🎯 *Choose Difficulty Level* ({language.title()})\n\n"
            "🟢 *Easy:* Common verses, basic books\n"
            "🟡 *Medium:* Mix of familiar and challenging verses\n"
            "🔴 *Hard:* Difficult verses, less common books\n\n"
            "Select your difficulty:"
        )

        keyboard = [
            ["🟢 Easy", "🟡 Medium", "🔴 Hard"],
            ["🔙 Back", "❌ Cancel"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)

        await update.message.reply_text(difficulty_text, parse_mode="Markdown", reply_markup=reply_markup)
        return BIBLE_GAME_DIFFICULTY

    # If no valid option was selected, show error
    await update.message.reply_text("Please choose a valid option from the keyboard.")
    return BIBLE_GAME_LANGUAGE

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

# Step 0: Ask user to choose Hymns or Lyrics
async def theme_type_choice(update: Update, context: CallbackContext) -> int:
    reply_keyboard = [["Hymns", "Lyrics"]]
    await update.message.reply_text(
        "What would you like to filter by theme?",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return THEME_TYPE

# Step 1: Handle Hymns/Lyrics choice and show available themes
async def handle_theme_type(update: Update, context: CallbackContext) -> int:
    choice = update.message.text.strip().lower()
    if choice not in ["hymns", "lyrics"]:
        await update.message.reply_text("Please choose either 'Hymns' or 'Lyrics'.")
        return THEME_TYPE
    context.user_data["theme_type"] = choice
    user = update.effective_user
    user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) chose {choice} for /theme")

    # Get unique themes from the correct DataFrame
    data = get_all_data()
    df = data["dfH"] if choice == "hymns" else data["dfL"]
    all_themes = df["Themes"].dropna().str.split(",").explode().str.strip().unique()
    themes = sorted(all_themes)
    keyboard = [themes[i:i+2] for i in range(0, len(themes), 2)]
    await update.message.reply_text(
        f"🎯 *Available Themes for {choice.capitalize()}:*\nPlease select or type one of the themes below:",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return THEME_SELECTION

# Load the embedding model once (with lazy loading)
_theme_model = None
_theme_embeddings = {}
_theme_texts = {}
_vocabulary_cache = None

def get_theme_model():
    global _theme_model
    if _theme_model is None:
        print("🔄 Loading theme model (first time only)...")
        _theme_model = SentenceTransformer('all-MiniLM-L6-v2')
        print("✅ Theme model loaded")
    return _theme_model

def get_vocabulary_cache():
    """Cache vocabulary computation to avoid repeated expensive operations"""
    global _vocabulary_cache
    if _vocabulary_cache is None:
        print("🔄 Computing vocabulary cache (first time only)...")
        data = get_all_data()
        df, dfH, dfL, dfC = data["df"], data["dfH"], data["dfL"], data["dfC"]
        _vocabulary_cache = ChoirVocabulary(df, dfH, dfL, dfC)
        print("✅ Vocabulary cache ready")
    return _vocabulary_cache

def initialize_theme_components():
    """Initialize all heavy theme components during bot startup"""
    try:
        print("🚀 Initializing theme components at startup...")

        # Pre-load the SentenceTransformer model
        print("  📥 Loading theme model...")
        get_theme_model()

        # Pre-load vocabulary cache
        print("  📚 Computing vocabulary cache...")
        get_vocabulary_cache()

        # Pre-compute theme embeddings for both hymns and lyrics
        print("  🔍 Pre-computing theme embeddings...")
        data = get_all_data()
        dfH, dfL = data["dfH"], data["dfL"]

        # Pre-compute hymn themes
        hymn_themes = dfH["Themes"].dropna().str.split(",").explode().str.strip().unique()
        if len(hymn_themes) > 0:
            get_theme_embeddings("hymns", hymn_themes)
            print(f"    ✅ Hymn themes ready ({len(hymn_themes)} themes)")

        # Pre-compute lyric themes
        lyric_themes = dfL["Themes"].dropna().str.split(",").explode().str.strip().unique()
        if len(lyric_themes) > 0:
            get_theme_embeddings("lyrics", lyric_themes)
            print(f"    ✅ Lyric themes ready ({len(lyric_themes)} themes)")

        print("✅ All theme components initialized successfully!")
        return True

    except Exception as e:
        print(f"❌ Error initializing theme components: {e}")
        print("⚠️ Theme command may be slower on first use")
        return False

def initialize_theme_components_background():
    """Initialize heavy theme components in background for better first-use performance"""
    try:
        print("🚀 Pre-loading theme components...")

        # Pre-load model
        get_theme_model()

        # Pre-load vocabulary
        get_vocabulary_cache()

        # Pre-compute theme embeddings for both hymns and lyrics
        data = get_all_data()
        dfH, dfL = data["dfH"], data["dfL"]

        # Pre-compute hymn themes
        hymn_themes = dfH["Themes"].dropna().str.split(",").explode().str.strip().unique()
        get_theme_embeddings("hymns", hymn_themes)

        # Pre-compute lyric themes
        lyric_themes = dfL["Themes"].dropna().str.split(",").explode().str.strip().unique()
        get_theme_embeddings("lyrics", lyric_themes)

        print("✅ Theme components pre-loaded successfully!")

    except Exception as e:
        print(f"⚠️ Error pre-loading theme components: {e}")
        # Don't fail the bot if pre-loading fails

def get_theme_embeddings(theme_type, all_themes):
    global _theme_embeddings, _theme_texts
    all_themes_list = list(all_themes)
    cache_key = f"{theme_type}_{len(all_themes_list)}"

    if theme_type not in _theme_embeddings or _theme_texts.get(theme_type) != all_themes_list:
        print(f"🔄 Computing {theme_type} theme embeddings (first time only)...")
        model = get_theme_model()
        _theme_embeddings[theme_type] = model.encode(all_themes_list)
        _theme_texts[theme_type] = all_themes_list
        print(f"✅ {theme_type.capitalize()} theme embeddings ready")
    return _theme_embeddings[theme_type], _theme_texts[theme_type]

def find_similar_themes(user_input, all_themes, theme_embeddings, threshold=0.7):
    model = get_theme_model()
    user_emb = model.encode([user_input])
    sims = cosine_similarity(user_emb, theme_embeddings)[0]
    matched = [theme for theme, sim in zip(all_themes, sims) if sim > threshold]
    return matched

def fuzzy_find_theme(user_input, all_themes, threshold=50):
    best_theme = None
    best_score = 0
    for theme in all_themes:
        for word in theme.split():
            score = fuzz.ratio(user_input.lower(), word.lower())
            if score > best_score:
                best_score = score
                best_theme = theme
    if best_score >= threshold:
        # Optionally, print for debugging
        # print(f"Fuzzy match: {best_theme} (score: {best_score})")
        return best_theme
    return None

# Helper to process theme selection logic for both direct and typo-confirmed input
async def process_theme_selection(theme_input, update, context):
    context.user_data["theme_input"] = theme_input
    data = get_all_data()
    theme_type = context.user_data.get("theme_type", "hymns")
    dfH = data["dfH"]
    dfL = data["dfL"]
    df = data["df"]
    dfC = data["dfC"]
    # Use cached vocabularies for better performance
    _, Hymn_Vocabulary, Lyric_Vocabulary, _ = get_vocabulary_cache()
    if theme_type == "hymns":
        all_themes = dfH["Themes"].dropna().str.split(",").explode().str.strip().unique()
        theme_embeddings, theme_texts = get_theme_embeddings("hymns", all_themes)
        matched_themes = find_similar_themes(theme_input, theme_texts, theme_embeddings, threshold=0.7)
        filtered_df = dfH[dfH["Themes"].apply(lambda x: any(t in str(x) for t in matched_themes))]
        known = Hymn_Vocabulary.values
        prefix = "H-"
        index_col = "Hymn Index"
        no_col = "Hymn no"
        tune_col = "Tunes"
    else:
        all_themes = dfL["Themes"].dropna().str.split(",").explode().str.strip().unique()
        theme_embeddings, theme_texts = get_theme_embeddings("lyrics", all_themes)
        matched_themes = find_similar_themes(theme_input, theme_texts, theme_embeddings, threshold=0.7)
        filtered_df = dfL[dfL["Themes"].apply(lambda x: any(t in str(x) for t in matched_themes))]
        known = Lyric_Vocabulary.values
        prefix = "L-"
        index_col = "Lyric Index"
        no_col = "Lyric no"
        tune_col = None
    # If no semantic match, try fuzzy matching and ask user for confirmation
    if filtered_df.empty or not matched_themes:
        suggestion = fuzzy_find_theme(theme_input, all_themes, threshold=50)
        if suggestion:
            context.user_data["theme_typo_suggestion"] = suggestion
            keyboard = [["Yes", "No"]]
            await update.message.reply_text(
                f"Did you mean: *{suggestion}*?",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
            )
            return TYPO_CONFIRM
        else:
            await update.message.reply_text(
                f"😕 No {theme_type} found for theme: *{theme_input}* (semantic & fuzzy match)",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardRemove()
            )
            return ConversationHandler.END
    known_items = []
    unknown_items = []
    for _, row in filtered_df.iterrows():
        item_no = row[no_col]
        if item_no in known:
            known_items.append(item_no)
        else:
            unknown_items.append(item_no)
    if theme_type == "hymns":
        display_known = [f"H-{h} - {dfH[dfH['Hymn no'] == h]['Hymn Index'].values[0]} - {dfH[dfH['Hymn no'] == h]['Tunes'].values[0]}" for h in known_items]
        display_unknown = [f"H-{h} - {dfH[dfH['Hymn no'] == h]['Hymn Index'].values[0]}" for h in unknown_items]
        message_parts = [f"🎼 *Hymns related to theme(s):* {', '.join(matched_themes)}"]
    else:
        display_known = [f"L-{l} - {dfL[dfL['Lyric no'] == l]['Lyric Index'].values[0]}" for l in known_items]
        display_unknown = [f"L-{l} - {dfL[dfL['Lyric no'] == l]['Lyric Index'].values[0]}" for l in unknown_items]
        message_parts = [f"🎼 *Lyrics related to theme(s):* {', '.join(matched_themes)}"]
    if display_known:
        message_parts.append(f"✅ *Choir Knows ({len(known_items)} total):*\n" + "\n".join(display_known))
    else:
        message_parts.append(f"❌ *No known {theme_type} found in this theme.*")
    if display_unknown:
        message_parts.append(f"❌ *Choir Doesn't Know ({len(unknown_items)} total):*\n" + "\n".join(display_unknown) + "\n\n*Note:* A known song may appear here if not sung in the past 3 years.")
    else:
        message_parts.append(f"🎉 *Choir knows all {theme_type} in this theme!*")
    await send_long_message(update, message_parts)
    context.user_data["known_items"] = known_items
    context.user_data["unknown_items"] = unknown_items
    await update.message.reply_text(
        "📅 Do you want to filter these to see Songs Sung this year?",
        reply_markup=ReplyKeyboardMarkup([["Yes", "No"]], one_time_keyboard=True, resize_keyboard=True)
    )
    return YEAR_FILTER

# Step 2: Process the theme selection (with typo correction logic)
async def handle_theme_selection(update: Update, context: CallbackContext) -> int:
    theme_input = update.message.text.strip()
    return await process_theme_selection(theme_input, update, context)

# Handler for typo confirmation (Yes/No)
async def handle_theme_typo_confirm(update: Update, context: CallbackContext) -> int:
    reply = update.message.text.strip().lower()
    suggestion = context.user_data.get("theme_typo_suggestion")
    if reply == "yes" and suggestion:
        context.user_data["theme_input"] = suggestion
        context.user_data.pop("theme_typo_suggestion", None)
        return await process_theme_selection(suggestion, update, context)
    else:
        await update.message.reply_text(
            "Sorry, nothing was found.",
            reply_markup=ReplyKeyboardRemove()
        )
        context.user_data.pop("theme_typo_suggestion", None)
        return ConversationHandler.END

# Step 3: Ask the user if they want year filtering (now supports both Hymns and Lyrics)
async def handle_year_filter(update: Update, context: CallbackContext) -> int:
    reply = update.message.text.strip().lower()
    if reply != "yes":
        await update.message.reply_text("Okay! No year filtering applied.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    s_year = datetime.now().year  # Automatically get current year
    data = get_all_data()
    theme_type = context.user_data.get("theme_type", "hymns")
    theme = context.user_data.get("theme_input", "")
    known = context.user_data.get("known_items", [])
    unknown = context.user_data.get("unknown_items", [])

    if theme_type == "hymns":
        df = data["dfH"]
        no_col = "Hymn no"
        index_col = "Hymn Index"
        tune_col = "Tunes"
        prefix = "H-"
    else:
        df = data["dfL"]
        no_col = "Lyric no"
        index_col = "Lyric Index"
        tune_col = None
        prefix = "L-"

    def get_last_sung_date(song_code):
        result = Datefinder(songs=song_code, first=True)
        if result and len(result) >= 10:
            try:
                return datetime.strptime(result[-10:], "%d/%m/%Y")
            except:
                return None
        return None

    def group_by_year(item_list):
        sung, not_sung = [], []
        for item in item_list:
            song_code = f"{prefix}{item}"
            date_obj = get_last_sung_date(song_code)
            # Retrieve index (and tune if hymns) from DataFrame
            index = df[df[no_col] == item][index_col].values[0]
            if theme_type == "hymns":
                tune = df[df[no_col] == item][tune_col].values[0]
            else:
                tune = None
            if date_obj and date_obj.year == s_year:
                if theme_type == "hymns":
                    sung.append(f"{song_code} - {index}  -{tune}")
                else:
                    sung.append(f"{song_code} - {index}")
            else:
                if theme_type == "hymns":
                    not_sung.append(f"{song_code} - {index} -{tune}")
                else:
                    not_sung.append(f"{song_code} - {index}")
        return sung, not_sung

    sung_known, not_sung_known = group_by_year(known)
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
    if 'was not found' not in song_info:
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

