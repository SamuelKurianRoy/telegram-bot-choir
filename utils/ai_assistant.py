# utils/ai_assistant.py
# AI Assistant for natural language command interpretation using Google Gemini

import google.generativeai as genai
from config import get_config
from logging_utils import setup_loggers
import json
import re

bot_logger, user_logger = setup_loggers()

# Initialize Gemini
_gemini_model = None

def initialize_gemini():
    """Initialize Gemini API with the API key from config"""
    global _gemini_model
    
    try:
        config = get_config()
        api_key = config.secrets.get("GEMINI_API_KEY")
        
        if not api_key:
            user_logger.warning("GEMINI_API_KEY not found in secrets. AI assistant disabled.")
            return False
        
        genai.configure(api_key=api_key)
        
        # Try different model names in order of preference
        # Based on test_gemini_api.py verification - only using confirmed working models
        model_names = [
            'models/gemini-2.5-flash',  # Primary - fast and reliable (confirmed working)
            'models/gemini-2.5-pro',    # Fallback - more capable
            'models/gemini-2.0-flash',  # Alternative - if 2.5 unavailable
        ]
        
        for model_name in model_names:
            try:
                user_logger.info(f"Trying model: {model_name}")
                _gemini_model = genai.GenerativeModel(model_name)
                
                # Test the model
                test_response = _gemini_model.generate_content("Say OK")
                user_logger.info(f"Model {model_name} works! Test: {test_response.text[:20]}")
                user_logger.info(f"✅ Gemini AI initialized with {model_name}")
                return True
                
            except Exception as model_error:
                user_logger.warning(f"Model {model_name} failed: {str(model_error)[:100]}")
                continue
        
        # If we get here, no model worked
        user_logger.error("All Gemini models failed to initialize")
        return False
        
    except Exception as e:
        user_logger.error(f"Failed to initialize Gemini: {str(e)[:200]}")
        import traceback
        user_logger.error(f"Init traceback: {traceback.format_exc()[:500]}")
        return False

def parse_user_intent(user_message: str) -> dict:
    """
    Parse user's natural language message to determine intent and extract parameters.
    
    Args:
        user_message: The user's message text
        
    Returns:
        dict with keys:
            - command: The bot command to execute (e.g., 'date', 'search', 'organist')
            - parameters: Dict of parameters needed for the command
            - response_text: Optional conversational response
            - confidence: Confidence score (0-1)
            - use_rag: Whether to use RAG (execute silently and generate response)
    """
    global _gemini_model
    
    if _gemini_model is None:
        if not initialize_gemini():
            return {
                "command": None,
                "parameters": {},
                "response_text": "AI assistant is not available. Please use /help to see available commands.",
                "confidence": 0.0
            }
    
    try:
        # Get current date for relative date calculations
        from datetime import datetime, timedelta
        today = datetime.now()
        current_year = today.year
        
        # Calculate last Sunday
        days_since_sunday = (today.weekday() + 1) % 7  # Monday=0, Sunday=6
        last_sunday = today - timedelta(days=days_since_sunday if days_since_sunday > 0 else 7)
        last_sunday_str = last_sunday.strftime("%d/%m/%Y")
        
        # Create a detailed prompt for Gemini
        prompt = f"""You are a helpful assistant for a church choir Telegram bot. Analyze the user's message and determine which bot command they want to use.

IMPORTANT: Today's date is {today.strftime("%d/%m/%Y")} (DD/MM/YYYY format). Last Sunday was {last_sunday_str}.

Available commands:
1. /date <DD/MM/YYYY> - Find songs sung on a specific date (e.g., "What songs were sung on Christmas?" → /date 25/12/2024)
2. /search - Search for songs by title, lyrics, or hymn number (e.g., "Find H-44" or "Search for Emmanuel")
3. /organist - View organist assignments (e.g., "Who is the organist?" or "Show organist roster")
4. /last <song_code> - Check when a song was last sung (e.g., "When was H-44 last sung?")
5. /check <song_code> - Get details about a song (e.g., "Tell me about L-323")
6. /tune <song_code> - Find tune information (e.g., "What tune is H-44?")
7. /theme - Search songs by theme (e.g., "Songs about Christmas" or "Advent songs")
8. /bible <reference> - Look up Bible verses (e.g., "Show John 3:16")
9. /games - Play Bible quiz games
10. /download - Download audio from YouTube/Spotify links
11. /help - Show help information
12. /updatesunday - Update Songs for Sunday sheet
13. /assignsongs - Assign Sunday songs to organists (e.g., "Assign songs to organists")
14. /unused - Find songs not sung in a specific period (e.g., "Show unused songs" or "Songs not sung this year")
15. None - If the message is just casual conversation or doesn't match any command

NOTE: /notation is NOT available through AI - it requires authorization. If user asks for notation, respond conversationally and suggest using /notation command directly.

User message: "{user_message}"

Respond with ONLY a JSON object (no markdown, no code blocks, just the raw JSON):
{{
    "command": "command_name (without /)",
    "parameters": {{"param_name": "value"}},
    "use_rag": true,
    "confidence": 0.0-1.0,
    "reasoning": "Brief explanation"
}}

IMPORTANT PARAMETERS BY COMMAND:
- date: {{"date": "DD/MM/YYYY"}}
- last/check/tune: {{"song_code": "H-21"}}
- organist: {{"organist_name": "Name"}} (optional - omit for full roster)
- theme: {{"category": "H or L", "theme": "keyword"}} (BOTH required)
- unused: {{"duration": "3months/6months/thisyear/1year", "category": "H/L/C/all"}}
- search: {{"query": "search text"}}

SET use_rag BASED ON COMMAND TYPE:
- use_rag: true → Data retrieval (date, last, check, theme, organist, unused, search, tune, bible)
- use_rag: false → Interactive/UI commands (help, games, download, assignsongs, updatesunday)

MULTI-STEP COMMAND EXAMPLES:
"Christmas hymns" → {{"command": "theme", "parameters": {{"category": "H", "theme": "christmas"}}, "use_rag": true, "confidence": 0.95}}
"funeral songs" → {{"command": "theme", "parameters": {{"category": "L", "theme": "funeral"}}, "use_rag": true, "confidence": 0.9}}
"songs assigned to Henel" → {{"command": "organist", "parameters": {{"organist_name": "Henel"}}, "use_rag": true, "confidence": 0.95}}
"unused hymns this year" → {{"command": "unused", "parameters": {{"duration": "thisyear", "category": "H"}}, "use_rag": true, "confidence": 0.95}}
"What did we sing on Christmas?" → {{"command": "date", "parameters": {{"date": "25/12/{current_year}"}}, "use_rag": true, "confidence": 0.9}}
"When was H-21 last sung?" → {{"command": "last", "parameters": {{"song_code": "H-21"}}, "use_rag": true, "confidence": 0.95}}
"Show help" → {{"command": "help", "parameters": {{}}, "use_rag": false, "confidence": 1.0}}
"""

        # Call Gemini
        response = _gemini_model.generate_content(prompt)
        response_text = response.text.strip()
        
        # Clean up response - remove markdown code blocks if present
        response_text = re.sub(r'^```json\s*', '', response_text)
        response_text = re.sub(r'^```\s*', '', response_text)
        response_text = re.sub(r'\s*```$', '', response_text)
        response_text = response_text.strip()
        
        user_logger.info(f"Gemini raw response: {response_text[:200]}")
        
        # Parse JSON response
        try:
            result = json.loads(response_text)
            user_logger.info(f"Parsed intent - Command: {result.get('command')}, Confidence: {result.get('confidence')}, Reasoning: {result.get('reasoning', 'N/A')[:50]}")
            return result
        except json.JSONDecodeError as je:
            user_logger.error(f"JSON parse error: {str(je)}, Response: {response_text[:200]}")
            return {
                "command": None,
                "parameters": {},
                "response_text": "I'm having trouble understanding that. Could you rephrase or use a command like /help?",
                "confidence": 0.0
            }
            
    except Exception as e:
        user_logger.error(f"Error parsing intent with Gemini: {str(e)[:200]}")
        import traceback
        user_logger.error(f"Full traceback: {traceback.format_exc()[:500]}")
        return {
            "command": None,
            "parameters": {},
            "response_text": "I encountered an error. Please try using a direct command like /help.",
            "confidence": 0.0
        }

def should_use_ai(message_text: str) -> bool:
    """
    Determine if a message should be processed by AI or is a direct command.
    
    Args:
        message_text: The user's message
        
    Returns:
        bool: True if should use AI, False if it's a direct command
    """
    # If message starts with /, it's a direct command - don't use AI
    if message_text.strip().startswith('/'):
        return False
    
    # If message matches a song code pattern exactly (H-123, L-45, C-96)
    if re.match(r'^[HLC]-\d+$', message_text.strip(), re.IGNORECASE):
        return False
    
    # Otherwise, use AI to interpret
    return True

def is_conversation_active(context) -> bool:
    """
    Check if user is currently in an active multi-step conversation.
    
    ConversationHandlers store state in context, so we check for known conversation markers.
    If user is in a conversation, AI should NOT intercept their response.
    
    Args:
        context: The telegram context object
        
    Returns:
        bool: True if conversation is active, False otherwise
    """
    try:
        # Check if ConversationHandler has stored a state
        # When a conversation is active, user_data contains specific keys
        user_data = context.user_data
        
        # List of conversation state indicators
        # These keys are set by various ConversationHandlers
        conversation_keys = [
            'expecting_date',  # /date command
            'ai_date_input',   # AI-triggered date
            'ai_song_input',   # AI-triggered song lookups
            'ai_bible_input',  # AI-triggered bible
            'current_search_method',  # /search
            'selected_category',  # /vocabulary, /search
            'selected_theme',  # /theme
            'tune_method',  # /tune
            'notation_type',  # /notation
            'download_url',  # /download
            'organist_roster_active',  # /organist (we'll add this)
            'comment_active',  # /comment
            'reply_active',  # /reply
            'bible_game_active',  # /games
            'setting_active',  # /setting
            'assign_songs_active',  # /assignsongs (we'll add this)
            'unused_songs_active',  # /unused (we'll add this)
        ]
        
        # If any conversation marker is present, conversation is active
        for key in conversation_keys:
            if key in user_data:
                return True
        
        # Also check if there's a conversation_state key (set by ConversationHandler internally)
        # This is a more reliable check
        if hasattr(context, 'conversation_state') and context.conversation_state is not None:
            return True
        
        return False
        
    except Exception as e:
        user_logger.error(f"Error checking conversation state: {str(e)[:100]}")
        # If error, assume no active conversation (safer to process with AI)
        return False
