# telegram_handlers/preferences.py
# User preference management handlers

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import CallbackContext, ConversationHandler
from data.udb import (
    get_user_preference, update_user_preference, 
    get_user_bible_language, update_user_bible_language,
    track_user_fast, save_if_pending
)
from config import get_config
from logging_utils import setup_loggers

# Setup loggers
bot_logger, user_logger = setup_loggers()

# Conversation states
PREFERENCE_MENU, BIBLE_LANGUAGE_CHOICE, NOTIFICATION_CHOICE, SEARCH_LIMIT_INPUT, TIMEZONE_INPUT = range(5)

async def preference_start(update: Update, context: CallbackContext) -> int:
    """Start the preference management conversation"""
    user = update.effective_user
    user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) started /preference")
    
    # Track user interaction
    track_user_fast(user)
    
    # Get current preferences
    bible_lang = get_user_bible_language(user.id)
    notification_enabled = get_user_preference(user.id, 'notification_enabled', True)
    search_limit = get_user_preference(user.id, 'search_results_limit', 10)
    timezone = get_user_preference(user.id, 'timezone', 'Asia/Kolkata')
    
    # Create preference menu
    welcome_text = (
        "⚙️ *User Preferences*\n\n"
        "*Current Settings:*\n"
        f"📖 Bible Language: *{bible_lang.title()}*\n"
        f"🔔 Notifications: *{'Enabled' if notification_enabled else 'Disabled'}*\n"
        f"🔍 Search Results Limit: *{search_limit}*\n"
        f"🌍 Timezone: *{timezone}*\n\n"
        "What would you like to change?"
    )
    
    keyboard = [
        ["📖 Bible Language", "🔔 Notifications"],
        ["🔍 Search Results Limit", "🌍 Timezone"],
        ["📊 View All Preferences", "❌ Cancel"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    
    await update.message.reply_text(welcome_text, parse_mode="Markdown", reply_markup=reply_markup)
    return PREFERENCE_MENU

async def preference_menu_handler(update: Update, context: CallbackContext) -> int:
    """Handle preference menu selection"""
    user = update.effective_user
    user_input = update.message.text.strip()
    
    if user_input == "📖 Bible Language":
        current_lang = get_user_bible_language(user.id)
        
        lang_text = (
            "📖 *Bible Language Preference*\n\n"
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
        
    elif user_input == "🔔 Notifications":
        current_setting = get_user_preference(user.id, 'notification_enabled', True)
        
        notif_text = (
            "🔔 *Notification Preferences*\n\n"
            f"Current setting: *{'Enabled' if current_setting else 'Disabled'}*\n\n"
            "Would you like to receive bot notifications?"
        )
        
        keyboard = [
            ["✅ Enable Notifications", "❌ Disable Notifications"],
            ["🔙 Back to Menu", "❌ Cancel"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        
        await update.message.reply_text(notif_text, parse_mode="Markdown", reply_markup=reply_markup)
        return NOTIFICATION_CHOICE
        
    elif user_input == "🔍 Search Results Limit":
        current_limit = get_user_preference(user.id, 'search_results_limit', 10)
        
        search_text = (
            "🔍 *Search Results Limit*\n\n"
            f"Current setting: *{current_limit} results*\n\n"
            "Enter the maximum number of search results to display (1-50):"
        )
        
        await update.message.reply_text(search_text, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
        return SEARCH_LIMIT_INPUT
        
    elif user_input == "🌍 Timezone":
        current_tz = get_user_preference(user.id, 'timezone', 'Asia/Kolkata')
        
        tz_text = (
            "🌍 *Timezone Preference*\n\n"
            f"Current setting: *{current_tz}*\n\n"
            "Enter your timezone (e.g., Asia/Kolkata, America/New_York, Europe/London):"
        )
        
        await update.message.reply_text(tz_text, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
        return TIMEZONE_INPUT
        
    elif user_input == "📊 View All Preferences":
        # Get all current preferences
        bible_lang = get_user_bible_language(user.id)
        notification_enabled = get_user_preference(user.id, 'notification_enabled', True)
        search_limit = get_user_preference(user.id, 'search_results_limit', 10)
        theme = get_user_preference(user.id, 'theme_preference', 'default')
        timezone = get_user_preference(user.id, 'timezone', 'Asia/Kolkata')
        
        all_prefs_text = (
            "📊 *All Your Preferences*\n\n"
            f"📖 *Bible Language:* {bible_lang.title()}\n"
            f"🔔 *Notifications:* {'Enabled' if notification_enabled else 'Disabled'}\n"
            f"🔍 *Search Results Limit:* {search_limit}\n"
            f"🎨 *Theme Preference:* {theme.title()}\n"
            f"🌍 *Timezone:* {timezone}\n\n"
            "Use the menu to change any setting."
        )
        
        keyboard = [
            ["📖 Bible Language", "🔔 Notifications"],
            ["🔍 Search Results Limit", "🌍 Timezone"],
            ["❌ Cancel"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        
        await update.message.reply_text(all_prefs_text, parse_mode="Markdown", reply_markup=reply_markup)
        return PREFERENCE_MENU
        
    elif user_input == "🔙 Back to Menu":
        # Return to main preference menu
        return await preference_start(update, context)
        
    elif user_input == "❌ Cancel":
        await update.message.reply_text(
            "✅ Preference settings cancelled.", 
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END
        
    else:
        await update.message.reply_text(
            "Please select a valid option from the menu.",
            reply_markup=ReplyKeyboardRemove()
        )
        return await preference_start(update, context)

async def bible_language_handler(update: Update, context: CallbackContext) -> int:
    """Handle Bible language preference selection"""
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
                "❌ Failed to update Bible language preference. Please try again.",
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
                "❌ Failed to update Bible language preference. Please try again.",
                reply_markup=ReplyKeyboardRemove()
            )
        return ConversationHandler.END
        
    elif user_input == "🔙 Back to Menu":
        return await preference_start(update, context)
        
    elif user_input == "❌ Cancel":
        await update.message.reply_text(
            "✅ Bible language preference unchanged.", 
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END
        
    else:
        await update.message.reply_text(
            "Please select a valid language option.",
            reply_markup=ReplyKeyboardRemove()
        )
        return await preference_start(update, context)

async def notification_handler(update: Update, context: CallbackContext) -> int:
    """Handle notification preference selection"""
    user = update.effective_user
    user_input = update.message.text.strip()
    
    if user_input == "✅ Enable Notifications":
        success = update_user_preference(user.id, 'notification_enabled', True)
        if success:
            save_if_pending()
            await update.message.reply_text(
                "✅ Notifications *enabled*.\n\n"
                "You will receive bot notifications and updates.",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardRemove()
            )
            user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) enabled notifications")
        else:
            await update.message.reply_text(
                "❌ Failed to update notification preference. Please try again.",
                reply_markup=ReplyKeyboardRemove()
            )
        return ConversationHandler.END
        
    elif user_input == "❌ Disable Notifications":
        success = update_user_preference(user.id, 'notification_enabled', False)
        if success:
            save_if_pending()
            await update.message.reply_text(
                "✅ Notifications *disabled*.\n\n"
                "You will not receive bot notifications.",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardRemove()
            )
            user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) disabled notifications")
        else:
            await update.message.reply_text(
                "❌ Failed to update notification preference. Please try again.",
                reply_markup=ReplyKeyboardRemove()
            )
        return ConversationHandler.END
        
    elif user_input == "🔙 Back to Menu":
        return await preference_start(update, context)
        
    elif user_input == "❌ Cancel":
        await update.message.reply_text(
            "✅ Notification preference unchanged.", 
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END
        
    else:
        await update.message.reply_text(
            "Please select a valid notification option.",
            reply_markup=ReplyKeyboardRemove()
        )
        return await preference_start(update, context)

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
                    "❌ Failed to update search limit preference. Please try again.",
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

async def timezone_handler(update: Update, context: CallbackContext) -> int:
    """Handle timezone input"""
    user = update.effective_user
    user_input = update.message.text.strip()
    
    # Basic timezone validation (you could make this more sophisticated)
    if len(user_input) > 3 and ('/' in user_input or user_input.upper() in ['UTC', 'GMT']):
        success = update_user_preference(user.id, 'timezone', user_input)
        if success:
            save_if_pending()
            await update.message.reply_text(
                f"✅ Timezone set to *{user_input}*.\n\n"
                "This will be used for time-related features.",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardRemove()
            )
            user_logger.info(f"{user.full_name} (@{user.username}, ID: {user.id}) set timezone to {user_input}")
        else:
            await update.message.reply_text(
                "❌ Failed to update timezone preference. Please try again.",
                reply_markup=ReplyKeyboardRemove()
            )
        return ConversationHandler.END
    else:
        await update.message.reply_text(
            "❌ Please enter a valid timezone (e.g., Asia/Kolkata, America/New_York, UTC).",
            reply_markup=ReplyKeyboardRemove()
        )
        return TIMEZONE_INPUT

async def cancel_preferences(update: Update, context: CallbackContext) -> int:
    """Cancel the preference conversation"""
    await update.message.reply_text(
        "✅ Preference settings cancelled.", 
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END
