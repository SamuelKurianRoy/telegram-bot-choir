# utils/rag_executor.py
# RAG (Retrieval-Augmented Generation) executor for AI assistant
# Executes bot commands programmatically and returns structured results

from datetime import datetime, timedelta
from logging_utils import setup_loggers
import traceback

bot_logger, user_logger = setup_loggers()


async def execute_command_for_rag(command: str, parameters: dict, context) -> dict:
    """
    Execute a bot command programmatically and return structured results.
    
    This is used by the RAG system to retrieve data without showing UI elements.
    The AI will then generate a natural language response based on this data.
    
    Args:
        command: Command name (e.g., 'date', 'last', 'theme')
        parameters: Command parameters
        context: Telegram context (for accessing global data)
        
    Returns:
        dict with:
            - success: bool
            - data: Retrieved data (structure varies by command)
            - error: Error message if failed
            - command: Original command name
    """
    
    try:
        if command == "date":
            return await _execute_date_command(parameters)
        
        elif command == "last":
            return await _execute_last_command(parameters)
        
        elif command == "check":
            return await _execute_check_command(parameters)
        
        elif command == "organist":
            return await _execute_organist_command(parameters)
        
        elif command == "theme":
            return await _execute_theme_command(parameters)
        
        elif command == "unused":
            return await _execute_unused_command(parameters)
        
        elif command == "search":
            return await _execute_search_command(parameters)
        
        elif command == "tune":
            return await _execute_tune_command(parameters)
        
        elif command == "bible":
            return await _execute_bible_command(parameters)
        
        else:
            return {
                "success": False,
                "data": None,
                "error": f"Command '{command}' not supported for RAG execution",
                "command": command
            }
            
    except Exception as e:
        user_logger.error(f"RAG executor error for {command}: {str(e)[:200]}")
        user_logger.error(f"Traceback: {traceback.format_exc()[:500]}")
        return {
            "success": False,
            "data": None,
            "error": f"Execution error: {str(e)[:100]}",
            "command": command
        }


async def _execute_date_command(parameters: dict) -> dict:
    """Execute /date command and return songs sung on that date"""
    from data.datasets import get_all_data
    
    date_str = parameters.get("date")
    if not date_str:
        return {"success": False, "error": "No date provided", "command": "date"}
    
    # Get global data
    dfH, dfL, dfC, yr23, yr24, yr25, df, dfTH, dfTD = get_all_data()
    
    # Find songs sung on this date
    date_songs = df[df['Date'] == date_str]
    
    if date_songs.empty:
        return {
            "success": True,
            "data": {
                "date": date_str,
                "songs": [],
                "count": 0
            },
            "command": "date"
        }
    
    # Extract songs from all columns
    songs = []
    for col in date_songs.columns:
        if col not in ['Date', 'Day']:
            song_val = date_songs[col].iloc[0]
            if song_val and str(song_val).strip() and str(song_val).upper() != 'NAN':
                songs.append(str(song_val).strip())
    
    return {
        "success": True,
        "data": {
            "date": date_str,
            "songs": songs,
            "count": len(songs)
        },
        "command": "date"
    }


async def _execute_last_command(parameters: dict) -> dict:
    """Execute /last command and return when a song was last sung"""
    from data.datasets import Datefinder
    
    song_code = parameters.get("song_code")
    if not song_code:
        return {"success": False, "error": "No song code provided", "command": "last"}
    
    # Find last sung date
    last_date = Datefinder(song_code)
    
    if not last_date or last_date == "Not found":
        return {
            "success": True,
            "data": {
                "song_code": song_code,
                "last_date": None,
                "found": False
            },
            "command": "last"
        }
    
    return {
        "success": True,
        "data": {
            "song_code": song_code,
            "last_date": last_date,
            "found": True
        },
        "command": "last"
    }


async def _execute_check_command(parameters: dict) -> dict:
    """Execute /check command and return song details"""
    from data.datasets import get_all_data, IndexFinder, isVocabulary, Datefinder
    from data.vocabulary import ChoirVocabulary
    
    song_code = parameters.get("song_code")
    if not song_code:
        return {"success": False, "error": "No song code provided", "command": "check"}
    
    # Get vocabulary
    dfH, dfL, dfC, yr23, yr24, yr25, df, dfTH, dfTD = get_all_data()
    Vocabulary, Hymn_Vocabulary, Lyric_Vocabulary, Convention_Vocabulary = ChoirVocabulary(df, dfH, dfL, dfC)
    
    # Get song details
    song_name = IndexFinder(song_code)
    is_in_vocab = isVocabulary(song_code, Vocabulary)
    last_date = Datefinder(song_code) if is_in_vocab else None
    
    return {
        "success": True,
        "data": {
            "song_code": song_code,
            "name": song_name,
            "in_vocabulary": is_in_vocab,
            "last_sung": last_date if last_date != "Not found" else None
        },
        "command": "check"
    }


async def _execute_organist_command(parameters: dict) -> dict:
    """Execute /organist command and return organist assignments"""
    from data.organist_roster import get_unique_organists, get_songs_by_organist, get_roster_summary, get_unassigned_songs
    
    organist_name = parameters.get("organist_name")
    
    # Get summary
    summary = get_roster_summary()
    
    if organist_name:
        # Get songs for specific organist
        songs = get_songs_by_organist(organist_name)
        return {
            "success": True,
            "data": {
                "organist": organist_name,
                "songs": songs,
                "count": len(songs),
                "summary": summary
            },
            "command": "organist"
        }
    else:
        # Get all organists
        organists = get_unique_organists()
        unassigned = get_unassigned_songs()
        
        return {
            "success": True,
            "data": {
                "organists": organists,
                "unassigned_songs": unassigned,
                "summary": summary
            },
            "command": "organist"
        }


async def _execute_theme_command(parameters: dict) -> dict:
    """Execute /theme command and return songs by theme"""
    from data.datasets import get_all_data
    from telegram_handlers.conversations import get_theme_components
    
    category = parameters.get("category", "").upper()  # H or L
    theme = parameters.get("theme", "").lower()
    year = parameters.get("year")  # Optional: 2023, 2024, 2025
    
    if not category or category not in ['H', 'L']:
        return {"success": False, "error": "Category must be 'H' (Hymns) or 'L' (Lyrics)", "command": "theme"}
    
    if not theme:
        return {"success": False, "error": "Theme not provided", "command": "theme"}
    
    # Get theme components
    theme_df, theme_index = get_theme_components()
    
    # Get data
    data_dict = get_all_data()
    dfH, dfL, dfC, yr23, yr24, yr25, df, dfTH, dfTD = data_dict
    
    # Select appropriate dataframe
    if category == "H":
        target_df = dfH
        no_col = "Hymn no"
        index_col = "Hymn Index"
        theme_col = "Themes"
        prefix = "H-"
    else:
        target_df = dfL
        no_col = "Lyric no"
        index_col = "Lyric Index"
        theme_col = "Themes"
        prefix = "L-"
    
    # Search for theme
    matching_songs = []
    
    try:
        # Search in theme column
        for idx, row in target_df.iterrows():
            themes_text = str(row.get(theme_col, "")).lower()
            if theme in themes_text:
                song_no = row.get(no_col)
                song_index = row.get(index_col, "")
                song_code = f"{prefix}{song_no}"
                matching_songs.append(f"{song_code} - {song_index}")
        
        return {
            "success": True,
            "data": {
                "category": "Hymns" if category == "H" else "Lyrics",
                "theme": theme,
                "year": year,
                "songs": matching_songs,
                "count": len(matching_songs)
            },
            "command": "theme"
        }
    except Exception as e:
        user_logger.error(f"Theme search error: {str(e)[:200]}")
        return {
            "success": False,
            "error": f"Theme search failed: {str(e)[:100]}",
            "command": "theme"
        }


async def _execute_unused_command(parameters: dict) -> dict:
    """Execute /unused command and return songs not sung in a time period"""
    from data.datasets import get_all_data, IndexFinder, standardize_hlc_value
    from data.vocabulary import ChoirVocabulary
    from datetime import datetime, timedelta
    
    duration = parameters.get("duration", "3months")  # 3months, 6months, thisyear, 1year
    category = parameters.get("category", "all").upper()  # H, L, C, or ALL
    
    # Calculate cutoff date
    today = datetime.now().date()
    
    if duration == "3months":
        cutoff_date = today - timedelta(days=90)
        duration_label = "3 Months"
    elif duration == "6months":
        cutoff_date = today - timedelta(days=180)
        duration_label = "6 Months"
    elif duration == "thisyear":
        cutoff_date = datetime(2025, 1, 1).date()
        duration_label = "This Year (2025)"
    elif duration == "1year":
        cutoff_date = today - timedelta(days=365)
        duration_label = "1 Year"
    else:
        cutoff_date = today - timedelta(days=90)
        duration_label = "3 Months"
    
    # Get data
    dfH, dfL, dfC, yr23, yr24, yr25, df, dfTH, dfTD = get_all_data()
    Vocabulary, Hymn_Vocabulary, Lyric_Vocabulary, Convention_Vocabulary = ChoirVocabulary(df, dfH, dfL, dfC)
    
    # Filter to recent data
    recent_df = df[df['Date'] >= cutoff_date]
    
    # Determine which categories to check
    if category == "H":
        vocab_to_check = {"H": Hymn_Vocabulary}
    elif category == "L":
        vocab_to_check = {"L": Lyric_Vocabulary}
    elif category == "C":
        vocab_to_check = {"C": Convention_Vocabulary}
    else:
        vocab_to_check = {
            "H": Hymn_Vocabulary,
            "L": Lyric_Vocabulary,
            "C": Convention_Vocabulary
        }
    
    # Find unused songs
    unused_songs = []
    
    for cat, vocab in vocab_to_check.items():
        for song_num in sorted(vocab):
            song_code = f"{cat}-{song_num}"
            
            # Check if song appears in recent data
            found = False
            for col in recent_df.columns:
                if col in ['Date', 'Day']:
                    continue
                
                standardized_values = recent_df[col].astype(str).apply(lambda x: standardize_hlc_value(x))
                if (standardized_values == song_code).any():
                    found = True
                    break
            
            if not found:
                song_name = IndexFinder(song_code)
                unused_songs.append({
                    "code": song_code,
                    "name": song_name,
                    "category": cat
                })
    
    return {
        "success": True,
        "data": {
            "duration": duration_label,
            "cutoff_date": str(cutoff_date),
            "category": category if category != "ALL" else "All Categories",
            "unused_songs": unused_songs,
            "count": len(unused_songs)
        },
        "command": "unused"
    }


async def _execute_search_command(parameters: dict) -> dict:
    """Execute /search command and return matching songs"""
    from utils.search import search_songs
    
    query = parameters.get("query", "")
    limit = parameters.get("limit", 10)
    
    if not query:
        return {"success": False, "error": "No search query provided", "command": "search"}
    
    # Perform search
    results = search_songs(query, limit=limit)
    
    return {
        "success": True,
        "data": {
            "query": query,
            "results": results,
            "count": len(results)
        },
        "command": "search"
    }


async def _execute_tune_command(parameters: dict) -> dict:
    """Execute /tune command and return tune information"""
    from data.datasets import Tune_finder_of_known_songs, Tunenofinder
    
    song_code = parameters.get("song_code")
    if not song_code:
        return {"success": False, "error": "No song code provided", "command": "tune"}
    
    # Find tune
    tune_known = Tune_finder_of_known_songs(song_code)
    tune_no = Tunenofinder(song_code)
    
    return {
        "success": True,
        "data": {
            "song_code": song_code,
            "tune_name": tune_known if tune_known != "Tune Not found" else None,
            "tune_number": tune_no if tune_no != "Tune Not found" else None
        },
        "command": "tune"
    }


async def _execute_bible_command(parameters: dict) -> dict:
    """Execute /bible command and return verse text"""
    from telegram_handlers.handlers import fetch_bible_verse
    
    reference = parameters.get("reference", "")
    language = parameters.get("language", "english")  # english or malayalam
    
    if not reference:
        return {"success": False, "error": "No reference provided", "command": "bible"}
    
    # Fetch verse
    verse_data = await fetch_bible_verse(reference, language)
    
    if not verse_data:
        return {
            "success": False,
            "error": f"Could not fetch verse: {reference}",
            "command": "bible"
        }
    
    return {
        "success": True,
        "data": verse_data,
        "command": "bible"
    }
