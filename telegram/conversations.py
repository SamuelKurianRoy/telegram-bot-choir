# telegram/conversations.py
# ConversationHandler states and flows

from telegram import Update, ReplyKeyboardRemove, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext, ConversationHandler
from config import get_config
from logging_utils import setup_loggers
# Import isVocabulary from the appropriate module
from data.vocabulary import ChoirVocabulary, isVocabulary, standardize_hlc_value
from utils.search import find_best_match, search_index
from utils.notation import Music_notation_link

bot_logger, user_logger = setup_loggers()

# --- Conversation States ---
# Example: CHECK_SONG, ENTER_SONG, etc.
# TODO: Define all necessary states for conversations

# --- Conversation Flows ---
# TODO: Implement conversation entry points and state handlers for each major conversation 

ENTER_SONG = 0  # State for /check conversation
ENTER_LAST_SONG, ASK_SHOW_ALL = range(2)

# --- /search Conversation ---
SEARCH_METHOD, INDEX_CATEGORY, INDEX_TEXT, NUMBER_CATEGORY, NUMBER_INPUT = range(5)

async def search_start(update: Update, context: CallbackContext) -> int:
    keyboard = [["By Index", "By Number"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
    await update.message.reply_text("How would you like to search?", reply_markup=reply_markup)
    return SEARCH_METHOD

async def search_method_choice(update: Update, context: CallbackContext) -> int:
    method = update.message.text.strip().lower()
    if method == "by index":
        keyboard = [["Hymn", "Lyric", "Convention"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
        await update.message.reply_text("Please select the category for your text search:", reply_markup=reply_markup)
        return INDEX_CATEGORY
    elif method == "by number":
        keyboard = [["Hymn", "Lyric", "Convention"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
        await update.message.reply_text("Please select the category:", reply_markup=reply_markup)
        return NUMBER_CATEGORY
    else:
        await update.message.reply_text("Invalid choice. Please choose 'By Index' or 'By Number'.")
        return SEARCH_METHOD

async def search_index_category(update: Update, context: CallbackContext) -> int:
    category = update.message.text.strip().lower()
    if category not in ["hymn", "lyric", "convention"]:
        await update.message.reply_text("Invalid choice. Please select either 'Hymn', 'Lyric' or 'Convention'.")
        return INDEX_CATEGORY
    context.user_data["index_search_category"] = category
    await update.message.reply_text("Now, please type your search text:", reply_markup=ReplyKeyboardRemove())
    return INDEX_TEXT

async def search_by_index(update: Update, context: CallbackContext) -> int:
    query = update.message.text.strip()
    category = context.user_data.get("index_search_category")
    result = find_best_match(query, category)
    if isinstance(result, str):
        await update.message.reply_text(result)
        return ConversationHandler.END
    matches, column_label = result
    prefix_map = {"hymn": "H-", "lyric": "L-", "convention": "C-"}
    label_clean = category.capitalize()
    prefix = prefix_map.get(category, "")
    reply_lines = [f"Top {len(matches)} matches for '{query}' in {category}:\n"]
    for i, (num, score, context_text) in enumerate(matches, 1):
        line = f"{i}. {prefix}{num}: (Similarity: {score:.3f})"
        if context_text and str(context_text).strip().lower() != "none":
            line += f" — {context_text.strip()}"
        reply_lines.append(line)
    reply = "\n".join(reply_lines)
    await update.message.reply_text(reply)
    return ConversationHandler.END

async def search_number_category(update: Update, context: CallbackContext) -> int:
    category = update.message.text.strip().lower()
    if category not in ["hymn", "lyric", "convention"]:
        await update.message.reply_text("Invalid choice. Please select either 'Hymn', 'Lyric' or 'Convention'.")
        return NUMBER_CATEGORY
    context.user_data["number_search_category"] = category
    await update.message.reply_text("Please enter the index number:", reply_markup=ReplyKeyboardRemove())
    return NUMBER_INPUT

async def search_by_number(update: Update, context: CallbackContext) -> int:
    text = update.message.text.strip()
    category = context.user_data.get("number_search_category")
    try:
        index_num = int(text)
    except ValueError:
        await update.message.reply_text("Index must be an integer. Please enter a valid index number:")
        return NUMBER_INPUT
    result = search_index(index_num, category)
    await update.message.reply_text(f"Search result of {category[0].upper()}-{index_num} : {result}")
    return ConversationHandler.END

# --- /tune Conversation ---
CHOOSE_METHOD, GET_INPUT = range(2)
user_input_method = {}

async def tune_command(update: Update, context: CallbackContext) -> int:
    reply_keyboard = [["Hymn Number", "Tune Name"]]
    await update.message.reply_text(
        "How would you like to search?",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True),
    )
    return CHOOSE_METHOD

async def choose_method(update: Update, context: CallbackContext) -> int:
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

async def get_input(update: Update, context: CallbackContext) -> int:
    user_id = update.effective_user.id
    method = user_input_method.get(user_id)
    user_input = update.message.text.strip()
    if method == "hymn number":
        # TODO: Replace with actual tune finder logic
        result = Tunenofinder(user_input)
    elif method == "tune name":
        # TODO: Replace with actual fuzzy tune search logic
        result = f"(Placeholder) Fuzzy tune search for: {user_input}"
    else:
        result = "Something went wrong. Please try again with /tune."
    await update.message.reply_text(result)
    return ConversationHandler.END

# --- /notation Conversation ---
ASK_HYMN_NO = range(1)

async def start_notation(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text("📖 Please enter the hymn number (e.g. H-86):")
    return ASK_HYMN_NO

async def receive_hymn_number(update: Update, context: CallbackContext) -> int:
    song_id = standardize_hlc_value(update.message.text.strip())
    # TODO: Replace with actual tune finder logic
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

# --- /theme Conversation ---
THEME_SELECTION = 1
YEAR_FILTER = 2

async def filter_theme(update: Update, context: CallbackContext) -> int:
    # Placeholder for theme list
    themes = ["Theme1", "Theme2"]
    keyboard = [themes[i:i+2] for i in range(0, len(themes), 2)]
    await update.message.reply_text(
        "🎯 *Available Themes:*\nPlease select or type one of the themes below:",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return THEME_SELECTION

async def handle_theme_selection(update: Update, context: CallbackContext) -> int:
    theme_input = update.message.text.strip()
    # Placeholder for theme filter logic
    await update.message.reply_text(f"(Placeholder) Hymns for theme: {theme_input}")
    await update.message.reply_text(
        "📅 Do you want to filter these hymns to see Songs Sung this year?",
        reply_markup=ReplyKeyboardMarkup([["Yes", "No"]], one_time_keyboard=True, resize_keyboard=True)
    )
    return YEAR_FILTER

async def handle_year_filter(update: Update, context: CallbackContext) -> int:
    reply = update.message.text.strip().lower()
    if reply != "yes":
        await update.message.reply_text("Okay! No year filtering applied.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
    # Placeholder for year filter logic
    await update.message.reply_text("(Placeholder) Year filter applied.")
    return ConversationHandler.END

# --- /vocabulary Conversation ---
CATEGORY_SELECTION, EXPORT_CONFIRMATION = range(2)

async def start_vocabulary(update: Update, context: CallbackContext) -> int:
    keyboard = [
        ["Full Vocabulary", "Hymn Vocabulary"],
        ["Lyric Vocabulary", "Convention Vocabulary"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
    await update.message.reply_text(
        "📚 Please choose a vocabulary category:", reply_markup=reply_markup
    )
    return CATEGORY_SELECTION

async def category_selection(update: Update, context: CallbackContext) -> int:
    user_choice = update.message.text.strip()
    # Placeholder for vocabulary export logic
    await update.message.reply_text(f"(Placeholder) Exported: {user_choice}")
    return ConversationHandler.END

# --- /download Conversation ---
ENTER_URL, SELECT_QUALITY = range(2, 4)

async def download_start(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text(
        "🎵 *Audio Downloader*\n\nPlease send me a YouTube or Spotify link to download the audio.",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove()
    )
    return ENTER_URL

async def download_url_input(update: Update, context: CallbackContext) -> int:
    user_input = update.message.text.strip()
    # Placeholder for URL check
    await update.message.reply_text(
        f"(Placeholder) URL received: {user_input}\nPlease select the audio quality:",
        reply_markup=ReplyKeyboardMarkup([
            ["🔥 High Quality (320kbps)", "🎵 Medium Quality (192kbps)"],
            ["💾 Low Quality (128kbps)", "❌ Cancel"]
        ], one_time_keyboard=True, resize_keyboard=True)
    )
    return SELECT_QUALITY

async def download_quality_selection(update: Update, context: CallbackContext) -> int:
    quality_text = update.message.text.strip()
    if quality_text == "❌ Cancel":
        await update.message.reply_text(
            "❌ Download cancelled.",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END
    # Placeholder for download logic
    await update.message.reply_text(f"(Placeholder) Downloading in quality: {quality_text}")
    return ConversationHandler.END

# --- /comment Conversation ---
COMMENT, REPLY = range(2)

async def start_comment(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text(
        "Please type your comment, recommendation, or thoughts below. You can also type /cancel to exit."
    )
    return COMMENT

async def process_comment(update: Update, context: CallbackContext) -> int:
    comment = update.message.text.strip()
    # Placeholder for comment processing
    await update.message.reply_text("✅ Thank you for your feedback! We appreciate your thoughts.")
    return ConversationHandler.END

async def check_song_start(update: Update, context: CallbackContext) -> int:
    user = update.effective_user
    config = get_config()
    ADMIN_ID = config.ADMIN_ID
    authorized_users = config.AUTHORIZED_USERS
    # Authorization check (can be refactored to a helper)
    if user.id not in authorized_users:
        user_logger.warning(f"Unauthorized access attempt to /checksong by {user.full_name} (@{user.username}, ID: {user.id})")
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                f"🚨 <b>Unauthorized user accessed /checksong</b>\n\n"
                f"<b>Name:</b> {user.full_name}\n"
                f"<b>Username:</b> @{user.username}\n"
                f"<b>User ID:</b> <code>{user.id}</code>"
            ),
            parse_mode="HTML"
        )
    await update.message.reply_text(
        "🎵 Please enter the song (e.g. H-27, L-14, C-5):",
        reply_markup=ReplyKeyboardRemove()
    )
    return ENTER_SONG

async def check_song_input(update: Update, context: CallbackContext) -> int:
    user_input = update.message.text.strip().upper()
    # TODO: Replace with actual data wiring
    result = isVocabulary(user_input, Vocabulary, dfH, dfTH, Tune_finder_of_known_songs)
    await update.message.reply_text(
        result,
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END

async def last_sung_start(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text(
        "🎼 Please enter the song (e.g. H-27, L-14, C-5):",
        reply_markup=ReplyKeyboardRemove()
    )
    return ENTER_LAST_SONG

async def last_sung_input(update: Update, context: CallbackContext) -> int:
    user_input = update.message.text.strip().upper()
    song_type, _, song_number = user_input.partition('-')
    full_song = f"{song_type}-{song_number}"
    context.user_data["last_category"] = song_type
    context.user_data["last_song"] = full_song
    # TODO: Replace with actual Datefinder logic
    result = Datefinder(full_song, song_type, first=True)
    await update.message.reply_text(result)
    reply_keyboard = [["Yes", "No"]]
    await update.message.reply_text(
        "Would you like to see all the dates on which this song was sung?",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return ASK_SHOW_ALL

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