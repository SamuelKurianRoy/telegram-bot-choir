# telegram/utils.py
# Telegram-specific helpers

import requests
from bs4 import BeautifulSoup
import re

def send_long_message(update, message_parts, parse_mode="Markdown", max_length=3500):
    """
    Sends a message, splitting it into multiple messages if it's too long.
    """
    # TODO: Implement message chunking logic
    pass

def extract_bible_chapter_text(url: str) -> str:
    try:
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        # Extract all <p> tags that contain verse text
        paragraphs = soup.find_all("p")

        verses = []
        for p in paragraphs:
            text = p.get_text(strip=True)
            # Skip empty and non-verse lines
            if not text:
                continue
            # Heuristically exclude junk like "JavaScript is required"
            if "javascript" in text.lower() or "wordproject" in text.lower():
                continue
            # Exclude overly long strings of digits (chapter nav)
            if text.strip().isdigit() and len(text.strip()) > 2:
                continue
            # Exclude footer content
            if any(footer_word in text.lower() for footer_word in ['contact', 'disclaimer', 'statement', 'mission', 'copyrights']):
                continue
            # Exclude lines that are just punctuation
            if text.strip() in ['|', '|', '|', '|', '|']:
                continue
            # Include lines that contain Malayalam text, English text, or verse numbers
            if (any('\u0D00' <= char <= '\u0D7F' for char in text) or  # Malayalam
                any(ord('A') <= ord(char) <= ord('Z') or ord('a') <= ord(char) <= ord('z') for char in text) or  # English
                re.search(r'\b\d{1,3}\b', text)):  # Verse numbers
                verses.append(text)

        return "\n".join(verses) if verses else "❌ No verses found on the page."

    except Exception as e:
        return f"❌ Error: {str(e)}"

def clean_malayalam_bible_text(text: str) -> str:
    lines = text.strip().splitlines()
    cleaned_lines = []
    for line in lines:
        lstripped = line.strip()
        # If line starts with 'അദ്ധ്യായം', extract Malayalam text after navigation digits
        if lstripped.startswith('അദ്ധ്യായം'):
            # Remove 'അദ്ധ്യായം' and everything up to and including the last digit in a run of digits
            m = re.search(r'^അദ്ധ്യായം[^\u0D00-\u0D7F\d]*([\d]+)([^\u0D00-\u0D7F\d]*)', lstripped)
            if m:
                idx = m.end()
                after_nav = lstripped[idx:].lstrip()
                # If there is Malayalam text after, add it (don't require a number)
                if after_nav and any('\u0D00' <= c <= '\u0D7F' for c in after_nav):
                    cleaned_lines.append(after_nav)
            continue
        # Skip lines that are just numbers (chapter navigation)
        if lstripped.isdigit() and len(lstripped) <= 3:
            continue
        # Skip lines that contain only chapter numbers like "123456789..."
        if len(lstripped) > 10 and all(c.isdigit() for c in lstripped):
            continue
        # Skip empty lines
        if not lstripped:
            continue
        # Skip footer content
        if any(footer_word in lstripped.lower() for footer_word in ['contact', 'disclaimer', 'statement', 'mission', 'copyrights']):
            continue
        # Skip lines that are just punctuation or special characters
        if lstripped in ['|', '|', '|', '|', '|']:
            continue
        # Clean the line
        cleaned_line = lstripped
        if cleaned_line:
            cleaned_lines.append(cleaned_line)
    # If the first cleaned line does not start with a number but contains Malayalam, prepend '1 '
    if cleaned_lines:
        first = cleaned_lines[0]
        if not first.lstrip().split(' ', 1)[0].isdigit() and any('\u0D00' <= c <= '\u0D7F' for c in first):
            cleaned_lines[0] = f"1 {first}"
    # Remove any leading lines until the first verse (should start with a number)
    while cleaned_lines and not cleaned_lines[0].lstrip().split(' ', 1)[0].isdigit():
        cleaned_lines.pop(0)
    # Join lines and do final cleaning
    result = "\n".join(cleaned_lines)
    # Remove any remaining chapter navigation patterns
    result = re.sub(r'\b\d{1,3}\s*\d{1,3}\s*\d{1,3}\b', '', result)
    # Clean up multiple spaces
    result = re.sub(r'\s+', ' ', result)
    # Remove footer content that might have been missed
    result = re.sub(r'Contact\|Disclaimer\|Statement of Faith\|Mission\|Copyrights.*$', '', result, flags=re.MULTILINE)
    # Format verses to start on new lines
    verses = re.split(r'(\d+)\s+', result)
    formatted_verses = []
    for i in range(0, len(verses), 2):
        if i + 1 < len(verses):
            verse_num = verses[i]
            verse_text = verses[i + 1].strip()
            if verse_num.isdigit() and verse_text:
                formatted_verses.append(f"{verse_num} {verse_text}")
    if not formatted_verses:
        result = re.sub(r'(\d+)\s+([അ-ഹ])', r'\n\1 \2', result)
        return result.strip()
    return "\n".join(formatted_verses)

def clean_english_bible_text(text: str) -> str:
    lines = text.strip().splitlines()
    cleaned_lines = []
    
    for line in lines:
        # Skip empty lines
        if not line.strip():
            continue
            
        # Skip lines that are just numbers (chapter navigation)
        if line.strip().isdigit() and len(line.strip()) <= 3:
            continue
        
        # Skip lines that contain only chapter numbers like "123456789..."
        if len(line.strip()) > 10 and all(c.isdigit() for c in line.strip()):
            continue
            
        # Skip footer content
        if any(footer_word in line.lower() for footer_word in ['contact', 'disclaimer', 'statement', 'mission', 'copyrights']):
            continue
            
        # Skip lines that are just punctuation
        if line.strip() in ['|', '|', '|', '|', '|']:
            continue
            
        # Clean the line
        cleaned_line = line.strip()
        if cleaned_line:
            cleaned_lines.append(cleaned_line)
    
    # Join lines and do final cleaning
    result = "\n".join(cleaned_lines)
    
    # Remove any remaining chapter navigation patterns
    result = re.sub(r'\b\d{1,3}\s*\d{1,3}\s*\d{1,3}\b', '', result)
    
    # Clean up multiple spaces
    result = re.sub(r'\s+', ' ', result)
    
    # Remove footer content that might have been missed
    result = re.sub(r'Contact\|Disclaimer\|Statement of Faith\|Mission\|Copyrights.*$', '', result, flags=re.MULTILINE)
    
    # Format verses to start on new lines
    # Split by verse numbers and format each verse
    verses = re.split(r'(\d+)\s+', result)
    formatted_verses = []
    
    for i in range(0, len(verses), 2):
        if i + 1 < len(verses):
            verse_num = verses[i]
            verse_text = verses[i + 1].strip()
            if verse_num.isdigit() and verse_text:
                formatted_verses.append(f"{verse_num} {verse_text}")
    
    # If no verses were found with the above method, try alternative formatting
    if not formatted_verses:
        # Add newlines before verse numbers
        result = re.sub(r'(\d+)\s+([A-Za-z])', r'\n\1 \2', result)
        return result.strip()
    
    return "\n".join(formatted_verses)

def normalize_and_format_bible_text(text: str) -> str:
    # Fix spacing between concatenated words (e.g., Abramwent → Abram went)
    text = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', text)              # between lowercase-uppercase
    text = re.sub(r'(?<=[A-Z][a-z])(?=[A-Z][a-z])', ' ', text)    # between proper nouns
    text = re.sub(r'(?<=[a-zA-Z])(?=\d)', ' ', text)              # letter-digit
    text = re.sub(r'(?<=\d)(?=[A-Za-z])', ' ', text)              # digit-letter

    # Ensure verse numbers start on a new line (e.g., "2 And" → "\n2 And")
    text = re.sub(r'(?<!\n)(?<!\d)(\s*)(\d{1,3})(\s+)(?=[A-Z])', r'\n\2 ', text)

    return text.strip()

def clean_bible_text(text: str, language: str = 'ml') -> str:
    if language == 'ml':
        text = re.sub(r'(?<=[\u0D00-\u0D7F]\.)(\d{1,3})(?=[\u0D00-\u0D7F])', r'\n\1 ', text)
        return clean_malayalam_bible_text(text)
    elif language == 'kj':  # English
        text = normalize_and_format_bible_text(text)
        return clean_english_bible_text(text)

    return text.strip()  # fallback

def get_wordproject_url_from_input(lang: str, user_input: str) -> str:
    # Bible book name to number map (with English and Malayalam full & short names)
    book_map = {
        # Old Testament
        "genesis": 1, "gen": 1, "ഉല്പത്തി": 1, "ഉല്പ": 1,
        "exodus": 2, "exo": 2, "ex": 2, "പുറപ്പാടു്": 2, "പുറ": 2,
        "leviticus": 3, "lev": 3, "ലേവ്യപുസ്തകം": 3, "ലേവ്യ": 3,
        "numbers": 4, "num": 4, "സംഖ്യാപുസ്തകം": 4, "സംഖ്യ": 4,
        "deuteronomy": 5, "deut": 5, "dt": 5, "ആവർത്തനം": 5, "ആവ": 5,
        "joshua": 6, "josh": 6, "യോശുവ": 6, "യോശ": 6,
        "judges": 7, "judg": 7, "ന്യായാധിപന്മാർ": 7, "ന്യായാ": 7,
        "ruth": 8, "രൂത്ത്": 8,
        "1 samuel": 9, "1 sam": 9, "i samuel": 9, "ശമൂവേൽ 1": 9, "1 ശമൂ": 9,
        "2 samuel": 10, "2 sam": 10, "ii samuel": 10, "ശമൂവേൽ 2": 10, "2 ശമൂ": 10,
        "1 kings": 11, "1 kgs": 11, "i kings": 11, "രാജാക്കന്മാർ 1": 11, "1 രാജാ": 11,
        "2 kings": 12, "2 kgs": 12, "ii kings": 12, "രാജാക്കന്മാർ 2": 12, "2 രാജാ": 12,
        "1 chronicles": 13, "1 chr": 13, "ദിനവൃത്താന്തം 1": 13, "1 ദിന": 13,
        "2 chronicles": 14, "2 chr": 14, "ദിനവൃത്താന്തം 2": 14, "2 ദിന": 14,
        "ezra": 15, "എസ്രാ": 15,
        "nehemiah": 16, "neh": 16, "നെഹെമ്യാവു": 16, "നെഹെ": 16,
        "esther": 17, "esth": 17, "എസ്ഥേർ": 17,
        "job": 18, "യോബ്": 18,
        "psalms": 19, "ps": 19, "psalm": 19, "സങ്കീർത്തനങ്ങൾ": 19, "സങ്കീ": 19,
        "proverbs": 20, "prov": 20, "പ്രവൃത്തിയുടെ പാഠങ്ങൾ": 20, "പ്രവാ": 20,
        "ecclesiastes": 21, "eccl": 21, "സഭാപ്രസംഗി": 21, "സഭാ": 21,
        "song of solomon": 22, "song": 22, "songs": 22, "sos": 22, "ഉത്തമഗീതം": 22, "ഉത്ത": 22,
        "isaiah": 23, "isa": 23, "യെശയ്യാ": 23, "യെശ": 23,
        "jeremiah": 24, "jer": 24, "യിരേമ്യാവു": 24, "യിരേ": 24,
        "lamentations": 25, "lam": 25, "വിലാപങ്ങൾ": 25, "വിലാ": 25,
        "ezekiel": 26, "ezek": 26, "യേഹേസ്കേൽ": 26, "യേഹേ": 26,
        "daniel": 27, "dan": 27, "ദാനീയേൽ": 27, "ദാനീ": 27,
        "hosea": 28, "hos": 28, "ഹോശേയ": 28, "ഹോഷ": 28,
        "joel": 29, "യോവേൽ": 29,
        "amos": 30, "ആമോസ്": 30,
        "obadiah": 31, "obad": 31, "ഓബദ്യാവു": 31,
        "jonah": 32, "jon": 32, "യോനാ": 32,
        "micah": 33, "mic": 33, "മീഖാ": 33,
        "nahum": 34, "nah": 34, "നാഹും": 34,
        "habakkuk": 35, "hab": 35, "ഹബക്കുക്ക്‍": 35,
        "zephaniah": 36, "zeph": 36, "സെഫാനിയാവു": 36,
        "haggai": 37, "hag": 37, "ഹഗ്ഗായി": 37,
        "zechariah": 38, "zech": 38, "സെഖർയ്യാവു": 38,
        "malachi": 39, "mal": 39, "മലാഖി": 39,

        # New Testament
        "matthew": 40, "matt": 40, "mt": 40, "മത്തായി": 40, "മത്താ": 40,
        "mark": 41, "mk": 41, "മർക്കൊസ്": 41, "മർക്ക": 41,
        "luke": 42, "lk": 42, "ലൂക്കോസ്": 42, "ലൂക്കോ": 42,
        "john": 43, "jn": 43, "യോഹന്നാൻ": 43, "യോഹ": 43,
        "acts": 44, "പ്രവൃത്തികൾ": 44, "പ്രവൃ": 44,
        "romans": 45, "rom": 45, "റോമർ": 45,
        "1 corinthians": 46, "1 cor": 46, "കൊരിന്ത്യർ 1": 46, "1 കൊരി": 46,
        "2 corinthians": 47, "2 cor": 47, "കൊരിന്ത്യർ 2": 47, "2 കൊരി": 47,
        "galatians": 48, "gal": 48, "ഗലാത്യർ": 48,
        "ephesians": 49, "eph": 49, "എഫെസ്യർ": 49,
        "philippians": 50, "phil": 50, "ഫിലിപ്പിയർ": 50,
        "colossians": 51, "col": 51, "കൊലൊസ്സ്യർ": 51,
        "1 thessalonians": 52, "1 thess": 52, "തെസ്സലൊനീക്യർ 1": 52, "1 തെസ്സ": 52,
        "2 thessalonians": 53, "2 thess": 53, "തെസ്സലൊനീക്യർ 2": 53, "2 തെസ്സ": 53,
        "1 timothy": 54, "1 tim": 54, "തിമൊഥെയൊസ് 1": 54, "1 തിമൊ": 54,
        "2 timothy": 55, "2 tim": 55, "തിമൊഥെയൊസ് 2": 55, "2 തിമൊ": 55,
        "titus": 56, "തീത്തൊസ്": 56,
        "philemon": 57, "philem": 57, "ഫിലേമോൻ": 57,
        "hebrews": 58, "heb": 58, "എബ്രായർ": 58,
        "james": 59, "jas": 59, "യാക്കോബ്": 59,
        "1 peter": 60, "1 pet": 60, "പത്രൊസ് 1": 60, "1 പത്രോ": 60,
        "2 peter": 61, "2 pet": 61, "പത്രൊസ് 2": 61, "2 പത്രോ": 61,
        "1 john": 62, "1 jn": 62, "യോഹന്നാൻ 1": 62, "1 യോഹ": 62,
        "2 john": 63, "2 jn": 63, "യോഹന്നാൻ 2": 63, "2 യോഹ": 63,
        "3 john": 64, "3 jn": 64, "യോഹന്നാൻ 3": 64, "3 യോഹ": 64,
        "jude": 65, "യുദാ": 65,
        "revelation": 66, "rev": 66, "വെളിപാട്": 66, "വെളി" : 66
    }

    # Chapter counts for each book (book number -> chapter count)
    book_chapter_counts = {
        1: 50, 2: 40, 3: 27, 4: 36, 5: 34, 6: 24, 7: 21, 8: 4, 9: 31,
        10: 24, 11: 22, 12: 25, 13: 29, 14: 36, 15: 10, 16: 13, 17: 10,
        18: 42, 19: 150, 20: 31, 21: 12, 22: 8, 23: 66, 24: 52, 25: 5,
        26: 48, 27: 12, 28: 14, 29: 3, 30: 9, 31: 1, 32: 4, 33: 7,
        34: 3, 35: 3, 36: 3, 37: 2, 38: 14, 39: 4, 40: 28, 41: 16,
        42: 24, 43: 21, 44: 28, 45: 16, 46: 16, 47: 13, 48: 6, 49: 6,
        50: 4, 51: 4, 52: 5, 53: 3, 54: 6, 55: 4, 56: 3, 57: 1,
        58: 13, 59: 5, 60: 5, 61: 3, 62: 5, 63: 1, 64: 1, 65: 1, 66: 22
    }

    # Language code map with short names
    language_code_map = {
        "malayalam": "ml", "mal": "ml",
        "english": "kj", "eng": "kj",
        "hindi": "hi", "hin": "hi",
        "tamil": "ta", "tam": "ta",
        "telugu": "te", "tel": "te",
        "kannada": "kn", "kan": "kn",
        "marathi": "mr", "mar": "mr",
        "gujarati": "gu", "guj": "gu",
        "punjabi": "pa", "pun": "pa",
        "bengali": "bn", "ben": "bn",
        "urdu": "ur", "urd": "ur",
        "spanish": "es", "spa": "es",
        "french": "fr", "fre": "fr",
        "german": "de", "ger": "de",
        "chinese": "zh", "chi": "zh",
        "japanese": "ja", "jap": "ja",
        "russian": "ru", "rus": "ru",
    }

    try:
        key = lang.strip().lower()
        if key not in language_code_map:
            raise ValueError(f"Unsupported language '{lang}'")
        lc = language_code_map[key]

        # Clean and process the input
        user_input = user_input.strip()
        
        # Handle verse references like "Gen 3:3" - extract just book and chapter
        if ':' in user_input:
            # Split by colon and take the part before it
            parts = user_input.split(':')
            if len(parts) >= 2:
                # Take everything before the colon (book and chapter)
                user_input = parts[0].strip()
        
        parts = user_input.lower().split()
        if len(parts) < 2:
            raise ValueError("Input must be 'Book Chapter'")

        # Match the longest possible book name
        for i in range(len(parts)-1, 0, -1):
            name = ' '.join(parts[:i])
            if name in book_map:
                chap = int(parts[i])
                bn = book_map[name]
                
                # Validate chapter number
                if bn in book_chapter_counts:
                    max_chapters = book_chapter_counts[bn]
                    if chap < 1 or chap > max_chapters:
                        raise ValueError(f"Chapter {chap} does not exist in the selected book. Valid chapters are 1-{max_chapters}")
                else:
                    raise ValueError(f"Invalid book number: {bn}")
                
                return f"https://www.wordproject.org/bibles/{lc}/{bn:02d}/{chap}.htm#0"

        raise ValueError("Book name not recognized")
    except Exception as e:
        return f"❌ Error: {e}"

# TODO: Add more Telegram-specific helpers as needed 