# utils/enhanced_search.py
# Enhanced search functionality with notation support

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from utils.notation import find_tune_page_number, getNotation, save_confirmed_page_result
from data.datasets import get_all_data

logger = logging.getLogger(__name__)

# States for the enhanced search conversation
TUNE_CONFIRMATION = "tune_confirmation"

async def show_search_results_with_notation(update: Update, context: ContextTypes.DEFAULT_TYPE, search_results, category):
    """
    Enhanced search results display that includes notation for hymn tunes.
    """
    # Handle error messages or empty results
    if not search_results:
        await update.message.reply_text("No results found.")
        return

    if isinstance(search_results, str):
        await update.message.reply_text(search_results)
        return

    # Unpack the results tuple
    try:
        matches, column_label = search_results
    except (ValueError, TypeError):
        await update.message.reply_text("Error processing search results.")
        return
    
    # Map category to prefix
    prefix_map = {
        "hymn": "H-",
        "lyric": "L-",
        "convention": "C-"
    }
    
    prefix = prefix_map.get(category, "")
    
    # For hymns, we'll show notation links for tunes
    if category == "hymn":
        await show_hymn_results_with_notation(update, context, matches, prefix)
    else:
        # For lyrics and conventions, show regular results
        await show_regular_search_results(update, context, matches, prefix, category)

async def show_hymn_results_with_notation(update: Update, context: ContextTypes.DEFAULT_TYPE, matches, prefix):
    """Show hymn search results with notation support for tunes."""
    from data.datasets import Tune_finder_of_known_songs, IndexFinder
    
    data = get_all_data()
    dfH, dfTH = data["dfH"], data["dfTH"]
    
    reply_lines = ["🎵 **Hymn Search Results with Notation:**\n"]
    
    for i, (hymn_no, score, context_text) in enumerate(matches, 1):
        hymn_code = f"{prefix}{hymn_no}"
        hymn_name = IndexFinder(hymn_code)
        
        # Get tunes for this hymn
        tunes_str = Tune_finder_of_known_songs(hymn_code)
        
        line = f"{i}. **{hymn_code}**: {hymn_name} (Similarity: {score:.3f})"
        if context_text and str(context_text).strip().lower() != "none":
            line += f" — {context_text.strip()}"
        
        reply_lines.append(line)
        
        # Add tune information with notation links
        if tunes_str and tunes_str != "Invalid Number":
            tune_list = [t.strip() for t in tunes_str.split(",") if t.strip()]
            if tune_list:
                reply_lines.append("   🎶 **Tunes:**")
                for tune in tune_list:
                    # Try to find page number for this tune
                    page_no, source = find_tune_page_number(tune, hymn_no, dfH, dfTH)
                    if page_no:
                        notation_link = getNotation(page_no)
                        if "http" in notation_link:
                            reply_lines.append(f"      • [{tune}]({notation_link}) (Page {page_no})")
                        else:
                            reply_lines.append(f"      • {tune} (Page {page_no} - {notation_link})")
                    else:
                        # Will be handled by inline keyboard below
                        reply_lines.append(f"      • {tune} - 🔍 Notation search available")
        
        reply_lines.append("")  # Empty line between results
    
    # Send the message
    message_text = "\n".join(reply_lines)
    
    # Create inline keyboard for tunes without notation
    keyboard = []
    for i, (hymn_no, score, context_text) in enumerate(matches, 1):
        hymn_code = f"{prefix}{hymn_no}"
        tunes_str = Tune_finder_of_known_songs(hymn_code)
        
        if tunes_str and tunes_str != "Invalid Number":
            tune_list = [t.strip() for t in tunes_str.split(",") if t.strip()]
            for tune in tune_list:
                page_no, source = find_tune_page_number(tune, hymn_no, dfH, dfTH)
                if not page_no:  # Only add button if no notation found
                    button_text = f"🔍 Find notation for {tune} (H-{hymn_no})"
                    callback_data = f"find_notation:{hymn_no}:{tune}"
                    keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
    
    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    
    await update.message.reply_text(
        message_text, 
        parse_mode="Markdown", 
        disable_web_page_preview=True,
        reply_markup=reply_markup
    )

async def show_regular_search_results(update: Update, context: ContextTypes.DEFAULT_TYPE, matches, prefix, category):
    """Show regular search results for lyrics and conventions."""
    from data.datasets import IndexFinder
    
    reply_lines = [f"Top {len(matches)} matches for {category}:\n"]
    for i, (num, score, context_text) in enumerate(matches, 1):
        song_code = f"{prefix}{num}"
        song_name = IndexFinder(song_code)
        
        line = f"{i}. {song_code}: {song_name} (Similarity: {score:.3f})"
        if context_text and str(context_text).strip().lower() != "none":
            line += f" — {context_text.strip()}"
        reply_lines.append(line)
    
    reply = "\n".join(reply_lines)
    await update.message.reply_text(reply)

async def handle_find_notation_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the callback when user clicks 'Find Notation' button."""
    query = update.callback_query
    await query.answer()
    
    try:
        # Parse callback data: "find_notation:hymn_no:tune_name"
        _, hymn_no, tune_name = query.data.split(":", 2)
        hymn_no = int(hymn_no)
        
        # Store in context for the conversation
        context.user_data['current_hymn'] = hymn_no
        context.user_data['current_tune'] = tune_name
        context.user_data['page_attempts'] = []
        
        # Start the notation finding process
        await start_notation_finding_process(query, context, hymn_no, tune_name)
        
    except Exception as e:
        logger.error(f"Error handling find notation callback: {e}")
        await query.edit_message_text("❌ Error processing request. Please try again.")

async def start_notation_finding_process(query, context: ContextTypes.DEFAULT_TYPE, hymn_no, tune_name):
    """Start the interactive notation finding process."""
    data = get_all_data()
    dfH, dfTH = data["dfH"], data["dfTH"]
    
    # Get propabible pages for this hymn
    from utils.notation import get_propabible_pages
    pages = get_propabible_pages(hymn_no, dfH)
    
    if not pages:
        # Try neighboring hymns
        for offset in [1, -1, 2, -2]:
            neighbor_hymn = hymn_no + offset
            if neighbor_hymn > 0:
                pages = get_propabible_pages(neighbor_hymn, dfH)
                if pages:
                    hymn_no = neighbor_hymn  # Update to neighbor
                    break
    
    if not pages:
        await query.edit_message_text(
            f"❌ No probable pages found for tune '{tune_name}' in H-{hymn_no} or neighboring hymns."
        )
        return
    
    # Start with the first page
    context.user_data['available_pages'] = pages
    context.user_data['current_page_index'] = 0
    
    await show_notation_page_for_confirmation(query, context, hymn_no, tune_name, pages[0])

async def show_notation_page_for_confirmation(query, context: ContextTypes.DEFAULT_TYPE, hymn_no, tune_name, page_no):
    """Show a notation page and ask for user confirmation."""
    notation_link = getNotation(page_no)
    
    message_text = (
        f"🎵 **Finding notation for: {tune_name}** (H-{hymn_no})\n\n"
        f"📖 **Page {page_no}**: [View Notation]({notation_link})\n\n"
        f"Is this the correct tune for **{tune_name}**?"
    )
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Yes, this is correct", callback_data=f"confirm_notation:yes:{hymn_no}:{tune_name}:{page_no}"),
            InlineKeyboardButton("❌ No, try next", callback_data=f"confirm_notation:no:{hymn_no}:{tune_name}:{page_no}")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        message_text,
        parse_mode="Markdown",
        disable_web_page_preview=True,
        reply_markup=reply_markup
    )

async def handle_notation_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle user's confirmation of notation correctness."""
    query = update.callback_query
    await query.answer()
    
    try:
        # Parse callback data: "confirm_notation:yes/no:hymn_no:tune_name:page_no"
        _, confirmation, hymn_no, tune_name, page_no = query.data.split(":", 4)
        hymn_no = int(hymn_no)
        page_no = int(page_no)
        
        if confirmation == "yes":
            # Save the confirmed result
            data = get_all_data()
            dfTH = data["dfTH"]
            save_confirmed_page_result(tune_name, hymn_no, page_no, dfTH)
            
            notation_link = getNotation(page_no)
            await query.edit_message_text(
                f"✅ **Notation confirmed!**\n\n"
                f"🎵 **{tune_name}** (H-{hymn_no})\n"
                f"📖 **Page {page_no}**: [View Notation]({notation_link})\n\n"
                f"This notation has been saved for future searches.",
                parse_mode="Markdown",
                disable_web_page_preview=True
            )
        else:
            # Try next page or neighboring hymn
            await try_next_notation_option(query, context, hymn_no, tune_name)
            
    except Exception as e:
        logger.error(f"Error handling notation confirmation: {e}")
        await query.edit_message_text("❌ Error processing confirmation. Please try again.")

async def try_next_notation_option(query, context: ContextTypes.DEFAULT_TYPE, hymn_no, tune_name):
    """Try the next available notation option."""
    available_pages = context.user_data.get('available_pages', [])
    current_page_index = context.user_data.get('current_page_index', 0)
    
    # Try next page in current hymn
    if current_page_index + 1 < len(available_pages):
        context.user_data['current_page_index'] = current_page_index + 1
        next_page = available_pages[current_page_index + 1]
        await show_notation_page_for_confirmation(query, context, hymn_no, tune_name, next_page)
        return
    
    # Try neighboring hymns
    data = get_all_data()
    dfH = data["dfH"]
    
    for offset in [1, -1, 2, -2, 3, -3]:
        neighbor_hymn = hymn_no + offset
        if neighbor_hymn > 0:
            from utils.notation import get_propabible_pages
            neighbor_pages = get_propabible_pages(neighbor_hymn, dfH)
            if neighbor_pages:
                context.user_data['available_pages'] = neighbor_pages
                context.user_data['current_page_index'] = 0
                context.user_data['current_hymn'] = neighbor_hymn
                
                await show_notation_page_for_confirmation(query, context, neighbor_hymn, tune_name, neighbor_pages[0])
                return
    
    # No more options
    await query.edit_message_text(
        f"❌ **No more notation options found**\n\n"
        f"Could not find suitable notation for **{tune_name}** in H-{hymn_no} or neighboring hymns.\n"
        f"Please contact an admin or try a different search."
    )

async def handle_tune_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle confirmation of tune notation from /tune command."""
    query = update.callback_query
    await query.answer()

    try:
        # Parse callback data: confirm:hymn_no:tune_index:page_no
        _, hymn_no, tune_index, page_no = query.data.split(":", 3)
        hymn_no = int(hymn_no)
        tune_index = int(tune_index)
        page_no = int(page_no)

        # Retrieve full tune info from context
        tune_key = f"{hymn_no}:{tune_index}"
        tune_info = context.user_data.get('tune_confirmations', {}).get(tune_key)

        if not tune_info:
            await query.edit_message_text(
                "❌ Error: Could not retrieve tune information.\n\n"
                "Please try again with /tune."
            )
            return

        tune_name = tune_info['tune_name']
        source = tune_info['source']

        # Save the confirmed result
        save_confirmed_page_result(tune_name, hymn_no, page_no, source)

        # Show confirmation message
        await query.edit_message_text(
            f"✅ **Confirmation Saved!**\n\n"
            f"🎵 **Tune:** {tune_name}\n"
            f"📖 **Hymn:** H-{hymn_no}\n"
            f"📄 **Page:** {page_no}\n"
            f"📍 **Source:** {source}\n\n"
            f"Thank you for confirming! This will help improve future searches.\n\n"
            f"💡 Use /tune again to search for more hymns."
        )

        # Clean up context data
        if 'tune_confirmations' in context.user_data:
            context.user_data['tune_confirmations'].pop(tune_key, None)

    except Exception as e:
        await query.edit_message_text(
            f"❌ Error saving confirmation: {str(e)}\n\n"
            "Please try again with /tune."
        )
