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
        
        # List available models to see what's actually available
        try:
            available_models = [m.name for m in genai.list_models()]
            user_logger.info(f"Available Gemini models: {available_models[:5]}")
        except:
            pass
        
        # Try different model names in order of preference
        model_names = [
            'gemini-1.5-flash-latest',
            'gemini-1.5-flash',
            'gemini-1.5-pro-latest',
            'gemini-pro',
            'models/gemini-1.5-flash-latest',
            'models/gemini-1.5-flash',
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
        # Create a detailed prompt for Gemini
        prompt = f"""You are a helpful assistant for a church choir Telegram bot. Analyze the user's message and determine which bot command they want to use.

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
11. /vocabulary - Export choir vocabulary
12. /notation - Get sheet music notation
13. /updatesunday - Update Songs for Sunday sheet
14. /help - Show help information
15. None - If the message is just casual conversation or doesn't match any command

User message: "{user_message}"

Respond with ONLY a JSON object (no markdown, no code blocks, just the raw JSON):
{{
    "command": "command_name (without /)",
    "parameters": {{"param_name": "value"}},
    "response_text": "A friendly response acknowledging their request",
    "confidence": 0.0-1.0,
    "reasoning": "Brief explanation of why you chose this command"
}}

Guidelines:
- For dates, extract DD/MM/YYYY format. If year is missing, use 2024.
- For song codes, extract the format like H-44, L-323, C-96
- For searches, include the search query in parameters
- Set confidence between 0-1 based on how clear the intent is
- If message is casual chat (hi, thanks, etc.), set command to null
- Always provide a friendly response_text

Examples:
"What songs did we sing on Christmas?" → {{"command": "date", "parameters": {{"date": "25/12/2024"}}, "response_text": "Let me check what songs were sung on Christmas!", "confidence": 0.9}}
"Find H-44" → {{"command": "search", "parameters": {{"query": "H-44"}}, "response_text": "Searching for hymn H-44...", "confidence": 0.95}}
"Hello" → {{"command": null, "parameters": {{}}, "response_text": "Hello! I'm here to help you with choir songs. You can ask me things like 'What songs were sung on Christmas?' or 'Find H-44'.", "confidence": 1.0}}
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
