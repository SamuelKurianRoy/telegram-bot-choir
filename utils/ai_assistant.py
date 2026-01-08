# utils/ai_assistant.py
# AI Assistant for natural language command interpretation using Google Gemini

from google import genai
from google.genai import types
from config import get_config
from logging_utils import setup_loggers
import json
import re

bot_logger, user_logger = setup_loggers()

# Initialize AI providers
_gemini_model = None
_groq_client = None

def initialize_gemini():
    """
    Initialize Gemini API with the API key from config.
    Does NOT test the connection to save quota.
    """
    global _gemini_model
    
    try:
        config = get_config()
        api_key = config.secrets.get("GEMINI_API_KEY")
        
        if not api_key:
            user_logger.warning("GEMINI_API_KEY not found in secrets. AI assistant disabled.")
            return False
        
        # Initialize client with new API
        client = genai.Client(api_key=api_key)
        
        # Use known working model (no testing to save quota)
        model_name = 'models/gemini-2.5-flash'  # Confirmed working on free tier
        
        # Store the client and model name without testing
        _gemini_model = (client, model_name)
        user_logger.info(f"✅ Gemini AI initialized with {model_name} (no test)")
        return True
        
    except Exception as e:
        user_logger.error(f"Failed to initialize Gemini: {str(e)[:200]}")
        import traceback
        user_logger.error(f"Init traceback: {traceback.format_exc()[:500]}")
        return False

def initialize_groq():
    """Initialize Groq API as a free fallback option"""
    global _groq_client
    
    try:
        # Try importing groq
        try:
            from groq import Groq
        except ImportError:
            user_logger.warning("Groq package not installed. Install with: pip install groq")
            return False
        
        config = get_config()
        api_key = config.secrets.get("GROQ_API_KEY")
        
        if not api_key:
            user_logger.warning("GROQ_API_KEY not found in secrets. Free AI fallback disabled.")
            user_logger.info("To enable free fallback: Get API key from https://console.groq.com/keys")
            return False
        
        # Initialize Groq client
        _groq_client = Groq(api_key=api_key)
        
        # Test the client
        test_response = _groq_client.chat.completions.create(
            messages=[{"role": "user", "content": "Say OK"}],
            model="llama-3.3-70b-versatile",  # Fast and free
            max_tokens=10
        )
        
        user_logger.info(f"✅ Groq AI (free) initialized as fallback")
        return True
        
    except Exception as e:
        user_logger.error(f"Failed to initialize Groq: {str(e)[:200]}")
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
    global _groq_client
    
    # Try to initialize Gemini if not already done
    if _gemini_model is None:
        gemini_ok = initialize_gemini()
        if not gemini_ok:
            user_logger.warning("Gemini not available, will try Groq fallback")
    
    # If Gemini is still not available, try Groq
    if _gemini_model is None and _groq_client is None:
        groq_ok = initialize_groq()
        if not groq_ok:
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
12. /updatesunday - Update Songs for Sunday sheet with next available date
13. /updatedate <date> - Update Songs for Sunday sheet with songs for a specific date (e.g., /updatedate 25/12/2025)
14. None - If the message is just casual conversation or doesn't match any command

NOTE: /notation is NOT available through AI - it requires authorization. If user asks for notation, respond conversationally and suggest using /notation command directly.

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
- For dates: Convert to DD/MM/YYYY format
  * "last Sunday" → {last_sunday_str}
  * "yesterday" → calculate from today's date ({(today - timedelta(days=1)).strftime("%d/%m/%Y")})
  * "Christmas" → 25/12/{current_year}
  * "Easter" → calculate Easter date for {current_year}
  * If year is missing, use {current_year}
  * Always use DD/MM/YYYY format (not MM/DD/YYYY)
  
- For song codes: ALWAYS extract in H-XX, L-XX, or C-XX format
  * "hymn 21" → H-21
  * "lyric 323" → L-323
  * "convention 21" → C-21
  * "H44" → H-44
  * IMPORTANT: When user says "hymn/lyric/convention NUMBER", convert to proper format (H-/L-/C-)
  
- For notation requests: Set command to null (notation requires authorization, handled separately)
  * "get notation for H-21" → command: null, response: "Please use /notation to access sheet music"
  
- For searches, include the search query in parameters
- Set confidence between 0-1 based on how clear the intent is
- If message is casual chat (hi, thanks, etc.), set command to null
- Always provide a friendly response_text

IMPORTANT: If asked about the bot creator, developer, or who made it:
- Respond that this bot was created by Samuel Kurian Roy
- Be friendly and mention you're here to help with choir-related tasks

Examples:
"What songs did we sing on Christmas?" → {{"command": "date", "parameters": {{"date": "25/12/{current_year}"}}, "response_text": "Let me check what songs were sung on Christmas!", "confidence": 0.9}}
"Songs from last Sunday" → {{"command": "date", "parameters": {{"date": "{last_sunday_str}"}}, "response_text": "I'll look up the songs sung on last Sunday for you!", "confidence": 0.95}}
"Find H-44" → {{"command": "search", "parameters": {{"query": "H-44"}}, "response_text": "Searching for hymn H-44...", "confidence": 0.95}}
"When was hymn 21 last sung?" → {{"command": "last", "parameters": {{"song_code": "H-21"}}, "response_text": "Let me check when Hymn 21 was last sung!", "confidence": 0.95}}
"When was convention 21 sung?" → {{"command": "last", "parameters": {{"song_code": "C-21"}}, "response_text": "Let me check when Convention 21 was last sung!", "confidence": 0.95}}
"Get notation for hymn 21" → {{"command": null, "parameters": {{}}, "response_text": "To access sheet music notation, please use the /notation command. This feature requires authorization.", "confidence": 1.0}}
"Who made this bot?" → {{"command": null, "parameters": {{}}, "response_text": "This bot was created by Samuel Kurian Roy to help our church choir manage songs and information. How can I assist you today?", "confidence": 1.0}}
"Hello" → {{"command": null, "parameters": {{}}, "response_text": "Hello! I'm here to help you with choir songs. You can ask me things like 'What songs were sung on Christmas?' or 'Find H-44'.", "confidence": 1.0}}
"""

        # Try Gemini first (if available)
        response_text = None
        used_provider = None
        
        if _gemini_model is not None:
            try:
                client, model_name = _gemini_model
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt
                )
                response_text = response.text.strip()
                used_provider = "Gemini"
                
            except Exception as gemini_error:
                # If Gemini fails (rate limit, quota, etc.), try Groq fallback
                user_logger.warning(f"Gemini failed: {str(gemini_error)[:100]}, trying Groq fallback...")
                response_text = None
        
        # If Gemini failed or wasn't available, use Groq
        if response_text is None:
            if _groq_client is None:
                if not initialize_groq():
                    return {
                        "command": None,
                        "parameters": {},
                        "response_text": "AI assistant encountered an error. Please use /help.",
                        "confidence": 0.0
                    }
            
            # Use Groq as fallback
            groq_response = _groq_client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that interprets user messages for a church choir bot. Always respond with valid JSON only."},
                    {"role": "user", "content": prompt}
                ],
                model="llama-3.3-70b-versatile",
                temperature=0.3,
                max_tokens=500
            )
            response_text = groq_response.choices[0].message.content.strip()
            used_provider = "Groq"
            user_logger.info("✅ Used Groq fallback successfully")
        
        # Clean up response - remove markdown code blocks if present
        response_text = re.sub(r'^```json\s*', '', response_text)
        response_text = re.sub(r'^```\s*', '', response_text)
        response_text = re.sub(r'\s*```$', '', response_text)
        response_text = response_text.strip()
        
        user_logger.info(f"{used_provider} raw response: {response_text[:200]}")
        
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
