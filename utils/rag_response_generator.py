# utils/rag_response_generator.py
# Generate natural language responses from RAG data

import google.generativeai as genai
from logging_utils import setup_loggers
import json

bot_logger, user_logger = setup_loggers()


async def generate_natural_response(user_question: str, command: str, rag_data: dict) -> str:
    """
    Generate a natural language response based on retrieved data (RAG).
    
    Args:
        user_question: Original user question
        command: Command that was executed
        rag_data: Data retrieved from command execution
        
    Returns:
        Natural language response string
    """
    
    try:
        # Get Gemini model
        from utils.ai_assistant import _gemini_model
        
        if _gemini_model is None:
            # Fallback to formatted response
            return format_data_fallback(command, rag_data)
        
        # Create prompt for response generation
        prompt = f"""You are a helpful church choir assistant. A user asked a question and we retrieved relevant data for you.

Generate a natural, conversational response based on the data provided. Be friendly, concise, and informative.

User's question: "{user_question}"

Command executed: {command}

Retrieved data:
{json.dumps(rag_data, indent=2, ensure_ascii=False)}

Guidelines:
- Start with a direct answer to their question
- Present song lists in a clear format (use bullet points or numbers)
- Include relevant details like Malayalam names when available
- Keep the tone warm and helpful
- If no results found, suggest alternatives
- Don't mention technical terms like "RAG", "command", "database"
- Use emojis sparingly but appropriately (🎵, 🎶, 📅, 👤)

Generate ONLY the response text (no JSON, no explanations, just the message to send to the user):
"""
        
        response = _gemini_model.generate_content(prompt)
        generated_text = response.text.strip()
        
        user_logger.info(f"Generated RAG response for {command}: {generated_text[:100]}")
        return generated_text
        
    except Exception as e:
        user_logger.error(f"Error generating natural response: {str(e)[:200]}")
        # Fallback to formatted response
        return format_data_fallback(command, rag_data)


def format_data_fallback(command: str, rag_data: dict) -> str:
    """Fallback formatter if Gemini fails"""
    
    data = rag_data.get("data", {})
    
    if command == "date":
        date = data.get("date")
        songs = data.get("songs", [])
        if not songs:
            return f"📅 No songs found for {date}."
        
        songs_list = "\n".join([f"• {song}" for song in songs])
        return f"📅 *Songs sung on {date}:*\n\n{songs_list}\n\n({len(songs)} songs total)"
    
    elif command == "last":
        song = data.get("song_code")
        last_date = data.get("last_date")
        if not last_date:
            return f"🎵 {song} hasn't been sung recently (not in our records)."
        return f"🎵 {song} was last sung on *{last_date}*"
    
    elif command == "check":
        song = data.get("song_code")
        name = data.get("name", "Unknown")
        in_vocab = data.get("in_vocabulary")
        last_sung = data.get("last_sung")
        
        response = f"🎵 *{song}*"
        if name != "Invalid Number":
            response += f"\n📝 Name: {name}"
        if in_vocab:
            response += f"\n✅ In our vocabulary"
            if last_sung:
                response += f"\n📅 Last sung: {last_sung}"
        else:
            response += f"\n❌ Not in vocabulary (never sung)"
        return response
    
    elif command == "organist":
        if "organist" in data:
            organist = data["organist"]
            songs = data.get("songs", [])
            if not songs:
                return f"👤 {organist} has no songs assigned."
            songs_list = "\n".join([f"{i+1}. {song}" for i, song in enumerate(songs)])
            return f"👤 *{organist}'s Songs* ({len(songs)} total):\n\n{songs_list}"
        else:
            summary = data.get("summary", {})
            return f"🎶 *Organist Roster Summary*\n\n" \
                   f"• Total Songs: {summary.get('total_songs', 0)}\n" \
                   f"• Assigned: {summary.get('assigned_songs', 0)}\n" \
                   f"• Unassigned: {summary.get('unassigned_songs', 0)}\n" \
                   f"• Organists: {summary.get('total_organists', 0)}"
    
    elif command == "theme":
        category = data.get("category")
        theme = data.get("theme")
        songs = data.get("songs", [])
        if not songs:
            return f"🎵 No {category} found for theme '{theme}'."
        songs_list = "\n".join([f"• {song}" for song in songs[:20]])  # Limit to 20
        more_text = f"\n\n...and {len(songs)-20} more" if len(songs) > 20 else ""
        return f"🎵 *{category} - {theme.title()}*\n\n{songs_list}{more_text}\n\n({len(songs)} songs total)"
    
    elif command == "unused":
        duration = data.get("duration")
        category = data.get("category")
        songs = data.get("unused_songs", [])
        if not songs:
            return f"✅ All {category} have been sung in {duration}!"
        
        if len(songs) <= 10:
            songs_list = "\n".join([f"• {s['code']}: {s['name']}" for s in songs])
            return f"🎵 *Unused {category}* (not sung in {duration}):\n\n{songs_list}\n\n({len(songs)} songs)"
        else:
            return f"🎵 Found *{len(songs)} unused {category}* not sung in {duration}.\n\n" \
                   f"(List too long to display here - use /unused for full details)"
    
    elif command == "search":
        query = data.get("query")
        results = data.get("results", [])
        if not results:
            return f"🔍 No results found for '{query}'."
        results_list = "\n".join([f"• {r}" for r in results[:10]])
        return f"🔍 *Search results for '{query}':*\n\n{results_list}"
    
    elif command == "tune":
        song = data.get("song_code")
        tune_name = data.get("tune_name")
        tune_no = data.get("tune_number")
        if not tune_name and not tune_no:
            return f"🎵 Tune information not found for {song}."
        response = f"🎵 *{song} Tune*\n"
        if tune_name:
            response += f"📝 Name: {tune_name}\n"
        if tune_no:
            response += f"🔢 Number: {tune_no}"
        return response
    
    else:
        return "✅ Command executed successfully!"
