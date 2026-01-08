# telegram_handlers/preferences.py
# User settings management handlers

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import CallbackContext, ConversationHandler
from data.udb import (
    get_user_preference, update_user_preference,
    get_user_bible_language, update_user_bible_language,
    get_user_game_language, update_user_game_language,
    get_user_download_preference, update_user_download_preference,
    get_user_download_quality, update_user_download_quality,
    get_user_show_tunes_in_date, update_user_show_tunes_in_date,
    get_user_upload_skip_filename, update_user_upload_skip_filename,
    get_user_upload_skip_description, update_user_upload_skip_description,
    track_user_fast, save_if_pending
)
from config import get_config
from logging_utils import setup_loggers

# Setup loggers
bot_logger, user_logger = setup_loggers()

# Conversation states
SETTING_MENU, BIBLE_LANGUAGE_CHOICE, GAME_LANGUAGE_CHOICE, SEARCH_LIMIT_INPUT, DOWNLOAD_PREFERENCE_CHOICE, DOWNLOAD_QUALITY_CHOICE, TUNE_DISPLAY_CHOICE, UPLOAD_PREFERENCE_CHOICE = range(8)

async def setting_start(update: Update, context: CallbackContext) -> int:
    """Start the settings management conversation"""
    user = update.effective_user
    user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) started /setting")
    
    # Track user interaction
    track_user_fast(user)
    
    # Get current preferences
    bible_lang = get_user_bible_language(user.id)
    game_lang = get_user_game_language(user.id)
    search_limit = get_user_preference(user.id, 'search_results_limit', 10)
    download_pref = get_user_download_preference(user.id)
    upload_skip_filename = get_user_upload_skip_filename(user.id)
    upload_skip_description = get_user_upload_skip_description(user.id)
    
    # Format upload preference
    if upload_skip_filename and upload_skip_description:
        upload_pref = "Skip Both"
    elif upload_skip_filename:
        upload_pref = "Skip Filename"
    elif upload_skip_description:
        upload_pref = "Skip Description"
    else:
        upload_pref = "Ask All"

    # Create settings menu
    welcome_text = (
        "⚙️ *User Settings*\n\n"
        "*Current Settings:*\n"
        f"📖 Bible Language: *{bible_lang.title()}*\n"
        f"🎮 Game Language: *{game_lang.title()}*\n"
        f"🔍 Search Results Limit: *{search_limit}*\n"
        f"📥 Download Behavior: *{download_pref.title()}*\n"
        f"🎵 Download Quality: *{download_quality.title()}*\n"
        f"🎼 Show Tunes in Date: *{'Yes' if show_tunes else 'No'}*\n"
        f"📤 Upload Preference: *{upload_pref}*\n\n"
        "What would you like to change?"
    )
    
    keyboard = [
        ["📖 Bible Language", "🎮 Game Language"],
        ["🔍 Search Results Limit", "📥 Download Behavior"],
        ["🎵 Download Quality", "🎼 Show Tunes in Date"],
        ["📤 Upload Preference", "📊 View All Settings"],
        [", "📥 Download Behavior"],
        ["🎵 Download Quality", "🎼 Show Tunes in Date"],
        ["📊 View All Settings", "❌ Cancel"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    
    await update.message.reply_text(welcome_text, parse_mode="Markdown", reply_markup=reply_markup)
    return SETTING_MENU

async def setting_menu_handler(update: Update, context: CallbackContext) -> int:
    """Handle settings menu selection"""
    user = update.effective_user
    user_input = update.message.text.strip()
    
    if user_input == "📖 Bible Language":
        current_lang = get_user_bible_language(user.id)

        lang_text = (
            "📖 *Bible Language Setting*\n\n"
            f"Current setting: *{current_lang.title()}*\n\n"
            "Choose your preferred language for Bible verses:"
        )
        
        keyboard = [
            ["🇮🇳 Malayalam", "🇺🇸 English"],
            ["🔙 Back to Menu", "❌ Cancel"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        
        await update.message.reply_text(lang_text, parse_mode="Markdown", reply_markup=reply_markup)
        return BIBLE_LANGUAGE_CHOICE

    elif user_input == "🎮 Game Language":
        current_lang = get_user_game_language(user.id)

        lang_text = (
            "🎮 *Bible Game Language Setting*\n\n"
            f"Current setting: *{current_lang.title()}*\n\n"
            "Choose your preferred language for Bible games:"
        )

        keyboard = [
            ["🇮🇳 Malayalam", "🇺🇸 English"],
            ["🔙 Back to Menu", "❌ Cancel"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)

        await update.message.reply_text(lang_text, parse_mode="Markdown", reply_markup=reply_markup)
        return GAME_LANGUAGE_CHOICE

    elif user_input == "🔍 Search Results Limit":
        current_limit = get_user_preference(user.id, 'search_results_limit', 10)
        
        search_text = (
            "🔍 *Search Results Limit*\n\n"
            f"Current setting: *{current_limit} results*\n\n"
            "Enter the maximum number of search results to display (1-50):"
        )
        
        await update.message.reply_text(search_text, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
        return SEARCH_LIMIT_INPUT

    elif user_input == "📥 Download Behavior":
        current_pref = get_user_download_preference(user.id)

        download_text = (
            "📥 *Download Behavior Setting*\n\n"
            f"Current setting: *{current_pref.title()}*\n\n"
            "Choose how you want playlist downloads to be handled:\n\n"
            "🎵 *Single Video* - Always download only the specific video (faster)\n"
            "❓ *Ask Every Time* - Show playlist options when detected"
        )

        keyboard = [
            ["🎵 Single Video Only", "❓ Ask Every Time"],
            ["🔙 Back to Menu", "❌ Cancel"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)

        await update.message.reply_text(download_text, parse_mode="Markdown", reply_markup=reply_markup)
        return DOWNLOAD_PREFERENCE_CHOICE

    elif user_input == "🎵 Download Quality":
        current_quality = get_user_download_quality(user.id)

        quality_text = (
            "🎵 *Download Quality Setting*\n\n"
            f"Current setting: *{current_quality.title()}*\n\n"
            "Choose your preferred audio quality:\n\n"
            "🔥 *High Quality* - 320kbps (best sound, larger files)\n"
            "🎵 *Medium Quality* - 192kbps (balanced)\n"
            "💾 *Low Quality* - 128kbps (smaller files, faster)\n"
            "❓ *Ask Every Time* - Choose quality for each download"
        )

        keyboard = [
            ["🔥 High Quality", "🎵 Medium Quality"],
            ["💾 Low Quality", "❓ Ask Every Time"],
            ["🔙 Back to Menu", "❌ Cancel"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)

        await update.message.reply_text(quality_text, parse_mode="Markdown", reply_markup=reply_markup)
        return DOWNLOAD_QUALITY_CHOICE

    elif user_input == "🎼 Show Tunes in Date":
        current_setting = get_user_show_tunes_in_date(user.id)

        tune_display_text = (
            "🎼 *Show Tunes in Date Command*\n\n"
            f"Current setting: *{'Yes' if current_setting else 'No'}*\n\n"
            "Choose whether to show tune names when using the `/date` command:\n\n"
            "✅ *Show Tunes* - Display tune names along with song information\n"
            "❌ *Hide Tunes* - Show only song codes and titles"
        )

        keyboard = [
            ["✅ Show Tunes", "❌ Hide Tunes"],
            ["🔙 Back to Menu", "❌ Cancel"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)

        await update.message.reply_text(tune_display_text, parse_mode="Markdown", reply_markup=reply_markup)
        return TUNE_DISPLAY_CHOICE    
    elif user_input == "📤 Upload Preference":
        upload_skip_filename = get_user_upload_skip_filename(user.id)
        upload_skip_description = get_user_upload_skip_description(user.id)
        
        if upload_skip_filename and upload_skip_description:
            current = "Skip Both"
        elif upload_skip_filename:
            current = "Skip Filename"
        elif upload_skip_description:
            current = "Skip Description"
        else:
            current = "Ask All"
        
        upload_text = (
            "📤 *Upload Preference Setting*\n\n"
            f"Current setting: *{current}*\n\n"
            "Choose how the /upload command should behave:\n\n"
            "• *Ask All* - Ask for both filename and description\n"
            "• *Skip Filename* - Use original filename, ask for description\n"
            "• *Skip Description* - Ask for filename, skip description\n"
            "• *Skip Both* - Use original filename, no description"
        )
        
        keyboard = [
            ["Ask All", "Skip Filename"],
            ["Skip Description", "Skip Both"],
            ["🔙 Back to Menu", "❌ Cancel"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        
        await update.message.reply_text(upload_text, parse_mode="Markdown", reply_markup=reply_markup)
        return UPLOAD_PREFERENCE_CHOICE
    elif user_input == "📊 View All Settings":
        # Get all current settings
        bible_lang = get_user_bible_language(user.id)
        game_lang = get_user_game_language(user.id)
        search_limit = get_user_preference(user.id, 'search_results_limit', 10)
        download_pref = get_user_download_preference(user.id)
        download_quality = get_user_download_quality(user.id)
        show_tunes = get_user_show_tunes_in_date(user.id)
        theme = get_user_preference(user.id, 'theme_preference', 'default')

        all_settings_text = (
            "📊 *All Your Settings*\n\n"
            f"📖 *Bible Language:* {bible_lang.title()}\n"
            f"🎮 *Game Language:* {game_lang.title()}\n"
            f"🔍 *Search Results Limit:* {search_limit}\n"
            f"📥 *Download Behavior:* {download_pref.title()}\n"
            f"🎵 *Download Quality:* {download_quality.title()}\n"
            f"🎼 *Show Tunes in Date:* {'Yes' if show_tunes else 'No'}\n"
            f"🎨 *Theme Setting:* {theme.title()}\n\n"
            "Use the menu to change any setting."
        )

        keyboard = [
            ["📖 Bible Language", "🎮 Game Language"],
            ["🔍 Search Results Limit", "📥 Download Behavior"],
            ["🎵 Download Quality", "🎼 Show Tunes in Date"],
            ["❌ Cancel"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        
        await update.message.reply_text(all_settings_text, parse_mode="Markdown", reply_markup=reply_markup)
        return SETTING_MENU

    elif user_input == "🔙 Back to Menu":
        # Return to main settings menu
        return await setting_start(update, context)

    elif user_input == "❌ Cancel":
        await update.message.reply_text(
            "✅ Settings cancelled.",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END

    else:
        await update.message.reply_text(
            "Please select a valid option from the menu.",
            reply_markup=ReplyKeyboardRemove()
        )
        return await setting_start(update, context)

async def bible_language_handler(update: Update, context: CallbackContext) -> int:
    """Handle Bible language setting selection"""
    user = update.effective_user
    user_input = update.message.text.strip()
    
    if user_input == "🇮🇳 Malayalam":
        success = update_user_bible_language(user.id, 'malayalam')
        if success:
            save_if_pending()  # Save changes immediately
            await update.message.reply_text(
                "✅ Bible language set to *Malayalam*.\n\n"
                "All Bible verses will now be displayed in Malayalam by default.",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardRemove()
            )
            user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) set Bible language to Malayalam")
        else:
            await update.message.reply_text(
                "❌ Failed to update Bible language setting. Please try again.",
                reply_markup=ReplyKeyboardRemove()
            )
        return ConversationHandler.END

    elif user_input == "🇺🇸 English":
        success = update_user_bible_language(user.id, 'english')
        if success:
            save_if_pending()  # Save changes immediately
            await update.message.reply_text(
                "✅ Bible language set to *English*.\n\n"
                "All Bible verses will now be displayed in English by default.",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardRemove()
            )
            user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) set Bible language to English")
        else:
            await update.message.reply_text(
                "❌ Failed to update Bible language setting. Please try again.",
                reply_markup=ReplyKeyboardRemove()
            )
        return ConversationHandler.END
        
    elif user_input == "🔙 Back to Menu":
        return await setting_start(update, context)

    elif user_input == "❌ Cancel":
        await update.message.reply_text(
            "✅ Bible language setting unchanged.",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END

    else:
        await update.message.reply_text(
            "Please select a valid language option.",
            reply_markup=ReplyKeyboardRemove()
        )
        return await setting_start(update, context)

async def game_language_handler(update: Update, context: CallbackContext) -> int:
    """Handle Bible game language setting selection"""
    user = update.effective_user
    user_input = update.message.text.strip()

    if user_input == "🇮🇳 Malayalam":
        success = update_user_game_language(user.id, 'malayalam')
        if success:
            save_if_pending()  # Save changes immediately
            await update.message.reply_text(
                "✅ Bible game language set to *Malayalam*.\n\n"
                "All Bible games will now use Malayalam by default.",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardRemove()
            )
            user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) set game language to Malayalam")
        else:
            await update.message.reply_text(
                "❌ Failed to update game language setting. Please try again.",
                reply_markup=ReplyKeyboardRemove()
            )
        return ConversationHandler.END

    elif user_input == "🇺🇸 English":
        success = update_user_game_language(user.id, 'english')
        if success:
            save_if_pending()  # Save changes immediately
            await update.message.reply_text(
                "✅ Bible game language set to *English*.\n\n"
                "All Bible games will now use English by default.",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardRemove()
            )
            user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) set game language to English")
        else:
            await update.message.reply_text(
                "❌ Failed to update game language setting. Please try again.",
                reply_markup=ReplyKeyboardRemove()
            )
        return ConversationHandler.END

    elif user_input == "🔙 Back to Menu":
        return await setting_start(update, context)

    elif user_input == "❌ Cancel":
        await update.message.reply_text(
            "✅ Game language setting unchanged.",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END

    else:
        await update.message.reply_text(
            "Please select a valid language option.",
            reply_markup=ReplyKeyboardRemove()
        )
        return await setting_start(update, context)

async def download_preference_handler(update: Update, context: CallbackContext) -> int:
    """Handle download preference selection"""
    user = update.effective_user
    user_input = update.message.text.strip()

    if user_input == "🎵 Single Video Only":
        success = update_user_download_preference(user.id, 'single')
        if success:
            save_if_pending()  # Save changes immediately
            await update.message.reply_text(
                "✅ Download behavior set to *Single Video Only*.\n\n"
                "When you share playlist links, only the specific video will be downloaded automatically. "
                "This is faster and uses less storage.",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardRemove()
            )
            user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) set download preference to single")
        else:
            await update.message.reply_text(
                "❌ Failed to update download preference. Please try again.",
                reply_markup=ReplyKeyboardRemove()
            )
        return ConversationHandler.END

    elif user_input == "❓ Ask Every Time":
        success = update_user_download_preference(user.id, 'ask')
        if success:
            save_if_pending()  # Save changes immediately
            await update.message.reply_text(
                "✅ Download behavior set to *Ask Every Time*.\n\n"
                "When you share playlist links, you'll be asked whether to download the single video or entire playlist.",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardRemove()
            )
            user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) set download preference to ask")
        else:
            await update.message.reply_text(
                "❌ Failed to update download preference. Please try again.",
                reply_markup=ReplyKeyboardRemove()
            )
        return ConversationHandler.END

    elif user_input == "🔙 Back to Menu":
        return await setting_start(update, context)

    elif user_input == "❌ Cancel":
        await update.message.reply_text(
            "✅ Download preference unchanged.",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END

    else:
        await update.message.reply_text(
            "Please select a valid download option.",
            reply_markup=ReplyKeyboardRemove()
        )
        return await setting_start(update, context)

async def download_quality_handler(update: Update, context: CallbackContext) -> int:
    """Handle download quality preference selection"""
    user = update.effective_user
    user_input = update.message.text.strip()

    if user_input == "🔥 High Quality":
        success = update_user_download_quality(user.id, 'high')
        if success:
            save_if_pending()  # Save changes immediately
            await update.message.reply_text(
                "✅ Download quality set to *High Quality (320kbps)*.\n\n"
                "All downloads will use the highest quality audio. "
                "Files will be larger but sound better.",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardRemove()
            )
            user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) set download quality to high")
        else:
            await update.message.reply_text(
                "❌ Failed to update download quality setting. Please try again.",
                reply_markup=ReplyKeyboardRemove()
            )
        return ConversationHandler.END

    elif user_input == "🎵 Medium Quality":
        success = update_user_download_quality(user.id, 'medium')
        if success:
            save_if_pending()  # Save changes immediately
            await update.message.reply_text(
                "✅ Download quality set to *Medium Quality (192kbps)*.\n\n"
                "All downloads will use balanced quality. "
                "Good sound quality with reasonable file sizes.",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardRemove()
            )
            user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) set download quality to medium")
        else:
            await update.message.reply_text(
                "❌ Failed to update download quality setting. Please try again.",
                reply_markup=ReplyKeyboardRemove()
            )
        return ConversationHandler.END

    elif user_input == "💾 Low Quality":
        success = update_user_download_quality(user.id, 'low')
        if success:
            save_if_pending()  # Save changes immediately
            await update.message.reply_text(
                "✅ Download quality set to *Low Quality (128kbps)*.\n\n"
                "All downloads will use lower quality audio. "
                "Smaller files that download faster.",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardRemove()
            )
            user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) set download quality to low")
        else:
            await update.message.reply_text(
                "❌ Failed to update download quality setting. Please try again.",
                reply_markup=ReplyKeyboardRemove()
            )
        return ConversationHandler.END

    elif user_input == "❓ Ask Every Time":
        success = update_user_download_quality(user.id, 'ask')
        if success:
            save_if_pending()  # Save changes immediately
            await update.message.reply_text(
                "✅ Download quality set to *Ask Every Time*.\n\n"
                "You'll be asked to choose the quality for each download.",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardRemove()
            )
            user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) set download quality to ask")
        else:
            await update.message.reply_text(
                "❌ Failed to update download quality setting. Please try again.",
                reply_markup=ReplyKeyboardRemove()
            )
        return ConversationHandler.END

    elif user_input == "🔙 Back to Menu":
        return await setting_start(update, context)

    elif user_input == "❌ Cancel":
        await update.message.reply_text(
            "✅ Download quality setting unchanged.",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END

    else:
        await update.message.reply_text(
            "Please select a valid quality option.",
            reply_markup=ReplyKeyboardRemove()
        )
        return await setting_start(update, context)



async def search_limit_handler(update: Update, context: CallbackContext) -> int:
    """Handle search results limit input"""
    user = update.effective_user
    user_input = update.message.text.strip()
    
    try:
        limit = int(user_input)
        if 1 <= limit <= 50:
            success = update_user_preference(user.id, 'search_results_limit', limit)
            if success:
                save_if_pending()
                await update.message.reply_text(
                    f"✅ Search results limit set to *{limit}*.\n\n"
                    f"Search commands will now show up to {limit} results.",
                    parse_mode="Markdown",
                    reply_markup=ReplyKeyboardRemove()
                )
                user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) set search limit to {limit}")
            else:
                await update.message.reply_text(
                    "❌ Failed to update search limit setting. Please try again.",
                    reply_markup=ReplyKeyboardRemove()
                )
            return ConversationHandler.END
        else:
            await update.message.reply_text(
                "❌ Please enter a number between 1 and 50.",
                reply_markup=ReplyKeyboardRemove()
            )
            return SEARCH_LIMIT_INPUT
    except ValueError:
        await update.message.reply_text(
            "❌ Please enter a valid number between 1 and 50.",
            reply_markup=ReplyKeyboardRemove()
        )
        return SEARCH_LIMIT_INPUT

async def tune_display_handler(update: Update, context: CallbackContext) -> int:
    """Handle tune display setting selection"""
    user = update.effective_user
    user_input = update.message.text.strip()

    if user_input == "✅ Show Tunes":
        success = update_user_show_tunes_in_date(user.id, True)
        if success:
            save_if_pending()  # Save changes immediately
            await update.message.reply_text(
                "✅ Tune display set to *Show Tunes*.\n\n"
                "When you use the `/date` command, tune names will be displayed along with song information.",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardRemove()
            )
            user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) enabled tune display in date command")
        else:
            await update.message.reply_text(
                "❌ Failed to update tune display setting. Please try again.",
                reply_markup=ReplyKeyboardRemove()
            )
        return ConversationHandler.END

    elif user_input == "❌ Hide Tunes":
        success = update_user_show_tunes_in_date(user.id, False)
        if success:
            save_if_pending()  # Save changes immediately
            await update.message.reply_text(
                "✅ Tune display set to *Hide Tunes*.\n\n"
                "When you use the `/date` command, only song codes and titles will be displayed.",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardRemove()
            )
            user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) disabled tune display in date command")
        else:
            await update.message.reply_text(
                "❌ Failed to update tune display setting. Please try again.",
                reply_markup=ReplyKeyboardRemove()
            )
        return ConversationHandler.END

    elif user_input == "🔙 Back to Menu":
        return await setting_start(update, context)

    elif user_input == "❌ Cancel":
        await update.message.reply_text(
            "✅ Settings cancelled.",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END

    else:
        await update.message.reply_text(
            "Please select a valid option from the menu.",
            reply_markup=ReplyKeyboardRemove()
        )
        return await setting_start(update, context)
async def upload_preference_handler(update: Update, context: CallbackContext) -> int:
    """Handle upload preference selection"""
    user = update.effective_user
    user_input = update.message.text.strip()
    
    if user_input == "Ask All":
        update_user_upload_skip_filename(user.id, False)
        update_user_upload_skip_description(user.id, False)
        save_if_pending()
        await update.message.reply_text(
            "✅ Upload preference set to *Ask All*.\n\n"
            "The bot will ask for both filename and description when you upload.",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove()
        )
        user_logger.info(f"{user.full_name} (ID: {user.id}) set upload preference to Ask All")
        return ConversationHandler.END
    
    elif user_input == "Skip Filename":
        update_user_upload_skip_filename(user.id, True)
        update_user_upload_skip_description(user.id, False)
        save_if_pending()
        await update.message.reply_text(
            "✅ Upload preference set to *Skip Filename*.\n\n"
            "The bot will use the original filename and ask for description.",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove()
        )
        user_logger.info(f"{user.full_name} (ID: {user.id}) set upload preference to Skip Filename")
        return ConversationHandler.END
    
    elif user_input == "Skip Description":
        update_user_upload_skip_filename(user.id, False)
        update_user_upload_skip_description(user.id, True)
        save_if_pending()
        await update.message.reply_text(
            "✅ Upload preference set to *Skip Description*.\n\n"
            "The bot will ask for filename but skip description.",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove()
        )
        user_logger.info(f"{user.full_name} (ID: {user.id}) set upload preference to Skip Description")
        return ConversationHandler.END
    
    elif user_input == "Skip Both":
        update_user_upload_skip_filename(user.id, True)
        update_user_upload_skip_description(user.id, True)
        save_if_pending()
        await update.message.reply_text(
            "✅ Upload preference set to *Skip Both*.\n\n"
            "The bot will use original filename and skip description prompt.",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove()
        )
        user_logger.info(f"{user.full_name} (ID: {user.id}) set upload preference to Skip Both")
        return ConversationHandler.END
    
    elif user_input == "🔙 Back to Menu":
        return await setting_start(update, context)
    
    elif user_input == "❌ Cancel":
        await update.message.reply_text(
            "✅ Settings cancelled.",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END
    
    else:
        await update.message.reply_text(
            "Please select a valid option.",
            reply_markup=ReplyKeyboardRemove()
        )
        return await setting_start(update, context)
async def cancel_settings(update: Update, context: CallbackContext) -> int:
    """Cancel the settings conversation"""
    await update.message.reply_text(
        "✅ Settings cancelled.",
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END
