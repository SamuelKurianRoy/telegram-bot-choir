# telegram/handlers.py
# Telegram command/callback handlers

from telegram import Update, ReplyKeyboardRemove
from telegram.ext import CallbackContext, ConversationHandler
from config import get_config
from logging_utils import setup_loggers
from data.datasets import load_datasets, yrDataPreprocessing, dfcleaning, standardize_song_columns
from data.drive import upload_log_to_google_doc

bot_logger, user_logger = setup_loggers()

# --- Command Handlers ---

async def start(update: Update, context: CallbackContext) -> None:
    """Handle /start command."""
    user = update.effective_user
    user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) sent /start")
    config = get_config()
    ADMIN_ID = config.ADMIN_ID
    authorized_users = config.AUTHORIZED_USERS
    if user.id not in authorized_users:
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
    welcome_text = (f"Hello {user.full_name if user.full_name else user.username}\n\n"
        "🎵 <b>Welcome to the Choir Bot!</b>\n\n"
        "This bot helps you quickly find details about choir songs!\n"
        "Simply type a song like <b>H-27</b>, <b>L-5</b>, or <b>C-12</b> and get instant info, including the last sung date.\n\n"
        "Use <b>/help</b> to explore all commands."
    )
    await update.message.reply_text(welcome_text, parse_mode="HTML")

async def help_command(update: Update, context: CallbackContext) -> None:
    """Handle /help command."""
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
        "  - *Description:* Interactive notation lookup. Start by typing `/notation`, and the bot will ask you for the hymn number (e.g. `H-86`). Then you'll be able to choose a tune and receive the notation image if available.\n"
        "  - *Example:* Type `/notation`, then enter a hymn number like `H-86`, and choose a tune to view notation.\n\n"
        "• **/theme**\n"
        "  - *Description:* Initiates an interactive theme filter. You will be presented with a list of unique themes (collected from all comma-separated entries in the database), and you can select or type a theme to display the hymns related to it.\n"
        "  - *Example:* Type `/theme` and choose from the displayed themes, or type a custom theme like `Additional Hymns`.\n\n"
        "• **/date**\n"
        "  - *Description:* Shows the songs sung on a specific date or the next available date if none found. Accepts various date formats.\n"
        "  - *Examples:*\n"
        "     - `/date 05/04/2024`\n\n"
        "• **/vocabulary**\n"
        "  - *Description:* Starts the vocabulary export conversation.\n"
        "  - *Example:* Type `/vocabulary` and follow the instructions.\n\n"
        "• **/download**\n"
        "  - *Description:* Download audio from YouTube, Spotify, or SoundCloud links. The bot will extract the audio and send it to you as an MP3 file.\n"
        "  - *Supported platforms:* YouTube, Spotify, SoundCloud\n"
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

async def refresh_command(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) used /refresh")
    config = get_config()
    try:
        # Reload datasets
        dfH, dfL, dfC, yr23, yr24, yr25, df, dfTH, dfTD = load_datasets()
        yrDataPreprocessing()
        dfcleaning()
        df = standardize_song_columns()
        # Upload logs
        upload_log_to_google_doc(config.BFILE_ID, "bot_log.txt")
        upload_log_to_google_doc(config.UFILE_ID, "user_log.txt")
        await update.message.reply_text("Datasets reloaded successfully!")
    except Exception as e:
        await update.message.reply_text(f"Error reloading datasets: {e}")

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

async def cancel(update: Update, context: CallbackContext) -> int:
    user = update.effective_user
    user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) sent /cancel")
    await update.message.reply_text("Operation canceled.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# TODO: Add more command handlers (check, last, search, tune, notation, theme, vocabulary, download, comment, refresh, reply, cancel, etc.) 