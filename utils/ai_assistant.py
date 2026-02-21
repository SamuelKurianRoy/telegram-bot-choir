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
_preferred_provider = "gemini"  # Track user's preferred provider: 'gemini', 'groq', or 'both'

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

def parse_user_intent(user_message: str, conversation_history: list = None) -> dict:
    """
    Parse user's natural language message to determine intent and extract parameters.
    
    Args:
        user_message: The user's message text
        conversation_history: Optional list of recent messages for context [{"role": "user"/"bot", "message": "...", "entities": {...}}]
        
    Returns:
        dict with keys:
            - command: The bot command to execute (e.g., 'date', 'search', 'rooster')
            - parameters: Dict of parameters needed for the command
            - response_text: Optional conversational response
            - confidence: Confidence score (0-1)
            - mentioned_entities: Dict of entities mentioned (for context tracking)
    """
    global _gemini_model
    global _groq_client
    global _preferred_provider
    
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
        
        # Build conversation context if available
        context_str = ""
        pending_query = None
        if conversation_history:
            context_str = "\n\n🔍 CONVERSATION CONTEXT (use this to resolve references):\n"
            for msg in conversation_history[-3:]:  # Last 3 messages
                role = msg.get('role', 'user')
                text = msg.get('message', '')
                entities = msg.get('entities', {})
                context_str += f"{role.upper()}: {text}\n"
                if entities:
                    context_str += f"  Entities mentioned: {entities}\n"
                    # Extract pending_query if present
                    if 'pending_query' in entities:
                        pending_query = entities['pending_query']
            
            if pending_query:
                context_str += f"\n⚠️ IMPORTANT: There's a pending query '{pending_query}' waiting for clarification!\n"
                context_str += f"If user says 'tune' or 'tune name', execute: {{\"command\": \"tune\", \"parameters\": {{\"tune_name\": \"{pending_query}\"}}}}\n"
                context_str += f"If user says 'song' or 'song name', execute: {{\"command\": \"search\", \"parameters\": {{\"query\": \"{pending_query}\"}}}}\n"
        
        # Create a detailed prompt for Gemini
        prompt = f"""You are a helpful assistant for a church choir Telegram bot. Analyze the user's message and determine which bot command they want to use.{context_str}

IMPORTANT: Today's date is {today.strftime("%d/%m/%Y")} (DD/MM/YYYY format). Last Sunday was {last_sunday_str}.

Available commands:
1. /date <DD/MM/YYYY> - Find songs sung on a specific date (e.g., "What songs were sung on Christmas?" → /date 25/12/2024)
2. /search - Search for songs by title, lyrics, or hymn number (e.g., "Find H-44" or "Search for Emmanuel")
3. /rooster - View organist roster and assignments (e.g., "Who is the organist?" or "Show organist roster")
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
14. /notation <song_code> - Get sheet music notation (requires authorization, will check user permissions)
15. None - If the message is just casual conversation or doesn't match any command

NOTE: /notation requires authorization but the system will automatically check user permissions. Include it as an option if user asks for notation or sheet music.

User message: "{user_message}"

Respond with ONLY a JSON object (no markdown, no code blocks, just the raw JSON):
{{
    "command": "command_name (without /)",
    "parameters": {{"param_name": "value"}},
    "response_text": "A friendly response acknowledging their request",
    "confidence": 0.0-1.0,
    "reasoning": "Brief explanation of why you chose this command",
    "mentioned_entities": {{"song_code": "H-44", "date": "25/12/2024", "tune_name": "abridge"}} // Extract key entities mentioned
}}

Guidelines:
- CRITICAL: Check conversation history FIRST for pending queries or references
  * If user says just "tune name", "tune", "song name", or "song", look for "pending_query" in history
  * Extract the query from history and execute immediately
  * Example: History shows pending_query="abridge", user says "tune" → execute tune search for "abridge"
  
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

- For tune queries: Use "tune" command with appropriate parameters
  * If asking about hymn number's tune: use song_code parameter (e.g., "tune for H-44" → {{"song_code": "H-44"}})
  * If asking about tune name: use tune_name parameter (e.g., "find tune abridge" → {{"tune_name": "abridge"}})
  * IMPORTANT: If query is ambiguous (could be song name OR tune name), ask for clarification
    - "find abridge" → ambiguous (could be song index or tune name)
    - "where to find abridge" → ambiguous
    - Solution: Set command to null and ask user to clarify
  * CRITICAL: When user responds to clarification with "tune name", "tune", "song name", or "song":
    - Look at conversation history to find what they were originally asking about
    - If they say "tune" or "tune name", execute tune search with the original query from history
    - If they say "song" or "song name", execute search with the original query from history
    - Example flow:
      User: "find abridge" → Bot: "Is it a song or tune?"
      User: "tune name" → Extract "abridge" from history, execute: {{"command": "tune", "parameters": {{"tune_name": "abridge"}}}}
  * Clear tune queries (use "tune" command):
    - "what is the tune for H-44?" → {{"command": "tune", "parameters": {{"song_code": "H-44"}}}}
    - "find tune abridge" → {{"command": "tune", "parameters": {{"tune_name": "abridge"}}}}
    - "where can I find the TUNE abridge" → {{"command": "tune", "parameters": {{"tune_name": "abridge"}}}}
  * Examples:
    - "what is the tune for H-44?" → {{"command": "tune", "parameters": {{"song_code": "H-44"}}}}
    - "find tune abridge" → {{"command": "tune", "parameters": {{"tune_name": "abridge"}}}}
    - "where can I find tune moscow" → {{"command": "tune", "parameters": {{"tune_name": "moscow"}}}}
    - "find abridge" → {{"command": null, "response_text": "Are you looking for 'abridge' as a song name or as a tune name? Please clarify:\\n• For song: Use /search abridge\\n• For tune: Use /tune and search for abridge", "mentioned_entities": {{"pending_query": "abridge"}}}}
    - Context: User asked "find abridge", then says "tune name" → {{"command": "tune", "parameters": {{"tune_name": "abridge"}}, "response_text": "Searching for tune 'abridge'!", "confidence": 0.9}}
  
- For notation requests: Use "notation" command with song_code parameter
  * System checks notation database FIRST, then provides external links if not found
  * "get notation for H-21" → {{"command": "notation", "parameters": {{"song_code": "H-21"}}}}
  * "show me sheet music for L-323" → {{"command": "notation", "parameters": {{"song_code": "L-323"}}}}
  * "can you get me the notation of H21" → {{"command": "notation", "parameters": {{"song_code": "H-21"}}}}
  
- For searches, include the search query in parameters
- Set confidence between 0-1 based on how clear the intent is
- If message is casual chat (hi, thanks, etc.), set command to null
- Always provide a friendly response_text

IMPORTANT: If asked about the bot creator, developer, or who made it:
- Respond that this bot was created by Samuel Kurian Roy
- Be friendly and mention you're here to help with choir-related tasks

Examples:
"What songs did we sing on Christmas?" → {{"command": "date", "parameters": {{"date": "25/12/{current_year}"}}, "response_text": "Let me check what songs were sung on Christmas!", "confidence": 0.9, "mentioned_entities": {{"date": "25/12/{current_year}"}}}}
"Songs from last Sunday" → {{"command": "date", "parameters": {{"date": "{last_sunday_str}"}}, "response_text": "I'll look up the songs sung on last Sunday for you!", "confidence": 0.95, "mentioned_entities": {{"date": "{last_sunday_str}"}}}}
"Find H-44" → {{"command": "search", "parameters": {{"query": "H-44"}}, "response_text": "Searching for hymn H-44...", "confidence": 0.95}}
"When was hymn 21 last sung?" → {{"command": "last", "parameters": {{"song_code": "H-21"}}, "response_text": "Let me check when Hymn 21 was last sung!", "confidence": 0.95}}
"When was convention 21 sung?" → {{"command": "last", "parameters": {{"song_code": "C-21"}}, "response_text": "Let me check when Convention 21 was last sung!", "confidence": 0.95}}
"Can you tell me where to find the tune abridge?" → {{"command": "tune", "parameters": {{"tune_name": "abridge"}}, "response_text": "I'll search for the tune 'abridge' in our database!", "confidence": 0.9}}
"What is the tune for H-44?" → {{"command": "tune", "parameters": {{"song_code": "H-44"}}, "response_text": "Let me find the tune for Hymn 44!", "confidence": 0.95}}
"Find tune moscow" → {{"command": "tune", "parameters": {{"tune_name": "moscow"}}, "response_text": "Searching for tune 'moscow'...", "confidence": 0.9}}
"Where to find abridge" → {{"command": null, "parameters": {{}}, "response_text": "I need clarification: Are you looking for 'abridge' as a song name or tune name?\\n\\n• If it's a song, use: /search abridge\\n• If it's a tune, use: /tune and search for 'abridge'", "confidence": 1.0, "mentioned_entities": {{"pending_query": "abridge"}}}}
"tune name" (with context showing user asked about "abridge") → {{"command": "tune", "parameters": {{"tune_name": "abridge"}}, "response_text": "Got it! Searching for tune 'abridge'!", "confidence": 0.95}}
"song name" (with context showing user asked about "abridge") → {{"command": "search", "parameters": {{"query": "abridge"}}, "response_text": "Got it! Searching for song 'abridge'!", "confidence": 0.95}}
"Find abridge" → {{"command": null, "parameters": {{}}, "response_text": "Could you clarify? Are you searching for:\\n\\n• A song named 'abridge'? → Use /search\\n• A tune named 'abridge'? → Use /tune\\n\\nOr just specify: 'find tune abridge' or 'find song abridge'", "confidence": 1.0, "mentioned_entities": {{"pending_query": "abridge"}}}}
"Get notation for hymn 21" → {{"command": "notation", "parameters": {{"song_code": "H-21"}}, "response_text": "Let me check the notation database for H-21!", "confidence": 0.95}}
"can you get me the notation of H21" → {{"command": "notation", "parameters": {{"song_code": "H-21"}}, "response_text": "I'll fetch the notation for H-21 from our database!", "confidence": 0.95}}
"Show me sheet music for H-44" → {{"command": "notation", "parameters": {{"song_code": "H-44"}}, "response_text": "Checking our notation library for H-44...", "confidence": 0.95}}
"Who made this bot?" → {{"command": null, "parameters": {{}}, "response_text": "This bot was created by Samuel Kurian Roy to help our church choir manage songs and information. How can I assist you today?", "confidence": 1.0}}
"Hello" → {{"command": null, "parameters": {{}}, "response_text": "Hello! I'm here to help you with choir songs. You can ask me things like 'What songs were sung on Christmas?' or 'Find H-44'.", "confidence": 1.0}}
"""

        # Try Gemini first (if available)
        response_text = None
        used_provider = None
        
        # Determine which provider to try first based on preference
        primary_provider = _preferred_provider if _preferred_provider in ['gemini', 'groq'] else 'gemini'
        
        if primary_provider == 'gemini' and _gemini_model is not None:
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
        
        elif primary_provider == 'groq' and _groq_client is not None:
            try:
                # Use Groq as primary
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
                
            except Exception as groq_error:
                # If Groq fails, try Gemini fallback
                user_logger.warning(f"Groq failed: {str(groq_error)[:100]}, trying Gemini fallback...")
                response_text = None
        
        # If primary provider failed or wasn't available, try fallback
        if response_text is None:
            # Try the other provider as fallback
            if primary_provider == 'gemini' and _groq_client is not None:
                # Gemini failed, use Groq as fallback
                if _groq_client is None:
                    if not initialize_groq():
                        return {
                            "command": None,
                            "parameters": {},
                            "response_text": "AI assistant encountered an error. Please use /help.",
                            "confidence": 0.0
                        }
                
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
                used_provider = "Groq (fallback)"
                user_logger.info("✅ Used Groq fallback successfully")
                
            elif primary_provider == 'groq' and _gemini_model is not None:
                # Groq failed, use Gemini as fallback
                try:
                    client, model_name = _gemini_model
                    response = client.models.generate_content(
                        model=model_name,
                        contents=prompt
                    )
                    response_text = response.text.strip()
                    used_provider = "Gemini (fallback)"
                    user_logger.info("✅ Used Gemini fallback successfully")
                except Exception as e:
                    user_logger.error(f"Both providers failed: {str(e)[:100]}")
                    return {
                        "command": None,
                        "parameters": {},
                        "response_text": "AI assistant encountered an error. Please use /help.",
                        "confidence": 0.0
                    }
        
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
            
            # Ensure mentioned_entities is present
            if 'mentioned_entities' not in result:
                result['mentioned_entities'] = {}
            
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
