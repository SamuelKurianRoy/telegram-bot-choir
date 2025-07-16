# telegram/utils.py
# Telegram-specific helpers

import requests
from bs4 import BeautifulSoup
import re
from rapidfuzz import fuzz

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
    import re
    # Remove navigation, footers, and unwanted lines
    lines = text.strip().splitlines()
    cleaned_lines = []
    for line in lines:
        lstripped = line.strip()
        if lstripped.startswith('അദ്ധ്യായം'):
            m = re.search(r'^അദ്ധ്യായം[^00-\u0D7F\d]*([\d]+)([^\u0D00-\u0D7F\d]*)', lstripped)
            if m:
                idx = m.end()
                after_nav = lstripped[idx:].lstrip()
                if after_nav and any('\u0D00' <= c <= '\u0D7F' for c in after_nav):
                    cleaned_lines.append(after_nav)
            continue
        if lstripped.isdigit() and len(lstripped) <= 3:
            continue
        if len(lstripped) > 10 and all(c.isdigit() for c in lstripped):
            continue
        if not lstripped:
            continue
        if any(footer_word in lstripped.lower() for footer_word in ['contact', 'disclaimer', 'statement', 'mission', 'copyrights']):
            continue
        if lstripped in ['|', '|', '|', '|', '|']:
            continue
        cleaned_lines.append(lstripped)
    
    # Join all lines with a single space
    text = ' '.join(cleaned_lines)
    
    # Insert newline before every verse number (1-3 digits) that is not part of a larger number and is followed by Malayalam
    text = re.sub(r'(?<!\d)(\d{1,3})(?=[\u0D00-\u0D7F])', r'\n\1', text)
    
    # Additional pattern to catch verse numbers that might be followed by space then Malayalam
    text = re.sub(r'(?<!\d)(\d{1,3})\s+(?=[\u0D00-\u0D7F])', r'\n\1 ', text)
    
    # Remove accidental leading/trailing whitespace/newlines
    text = text.strip()
    
    # Split into lines and clean up
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    
    # Ensure a space after the verse number if followed by Malayalam
    new_lines = []
    for line in lines:
        new_lines.append(re.sub(r'^(\d{1,3})(?=[\u0D00-\u0D7F])', r'\1 ', line))
    lines = new_lines
    
    # If the first line does not start with a number, prepend '1 '
    if lines and not re.match(r'^\d{1,3}', lines[0]):
        lines[0] = '1 ' + lines[0]
    
    # Always return all lines joined by newline
    return '\n'.join(lines)

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

def get_wordproject_url_from_input(lang: str, user_input: str) -> tuple:
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
        "nehemiah": 16, "neh": 16, "നെഹെമ്യാവ്": 16, "നെഹെ": 16,
        "esther": 17, "est": 17, "എസ്തേർ": 17,
        "job": 18, "ഇയ്യോബ്": 18,
        "psalms": 19, "ps": 19, "psa": 19, "സങ്കീർത്തനങ്ങൾ": 19, "സങ്കീ": 19,
        "proverbs": 20, "prov": 20, "pr": 20, "സദൃശവാക്യങ്ങൾ": 20, "സദൃ": 20,
        "ecclesiastes": 21, "ecc": 21, "സഭാപ്രസംഗി": 21, "സഭാ": 21,
        "song of solomon": 22, "song": 22, "sos": 22, "ഉത്തമഗീതം": 22, "ഉത്തമ": 22,
        "isaiah": 23, "isa": 23, "യെശയ്യാവ്": 23, "യെശ": 23,
        "jeremiah": 24, "jer": 24, "യിരെമ്യാവ്": 24, "യിരെ": 24,
        "lamentations": 25, "lam": 25, "വിലാപങ്ങൾ": 25, "വിലാ": 25,
        "ezekiel": 26, "eze": 26, "യെഹെസ്കേൽ": 26, "യെഹെ": 26,
        "daniel": 27, "dan": 27, "ദാനീയേൽ": 27, "ദാനീ": 27,
        "hosea": 28, "hos": 28, "ഹോശേയ": 28, "ഹോശേ": 28,
        "joel": 29, "യോവേൽ": 29,
        "amos": 30, "ആമോസ്": 30,
        "obadiah": 31, "oba": 31, "ഓബദ്യാവ്": 31, "ഓബദ്": 31,
        "jonah": 32, "യോനാ": 32,
        "micah": 33, "mic": 33, "മീഖാ": 33,
        "nahum": 34, "nah": 34, "നഹൂം": 34,
        "habakkuk": 35, "hab": 35, "ഹബക്കൂക്": 35, "ഹബക്": 35,
        "zephaniah": 36, "zep": 36, "സെഫന്യാവ്": 36, "സെഫ": 36,
        "haggai": 37, "hag": 37, "ഹഗ്ഗായി": 37, "ഹഗ്ഗാ": 37,
        "zechariah": 38, "zec": 38, "സെഖര്യാവ്": 38, "സെഖ": 38,
        "malachi": 39, "mal": 39, "മലാഖി": 39,
        
        # New Testament
        "matthew": 40, "matt": 40, "mt": 40, "മത്തായി": 40, "മത്താ": 40,
        "mark": 41, "mk": 41, "മർക്കൊസ്": 41, "മർക്": 41,
        "luke": 42, "lk": 42, "ലൂക്കാ": 42, "ലൂക്": 42,
        "john": 43, "jn": 43, "യോഹന്നാൻ": 43, "യോഹ": 43,
        "acts": 44, "act": 44, "അപ്പൊസ്തലന്മാരുടെ പ്രവൃത്തികൾ": 44, "അപ്പൊ": 44,
        "romans": 45, "rom": 45, "റോമർ": 45, "റോമ": 45,
        "1 corinthians": 46, "1 cor": 46, "കൊരിന്ത്യർ 1": 46, "1 കൊരി": 46,
        "2 corinthians": 47, "2 cor": 47, "കൊരിന്ത്യർ 2": 47, "2 കൊരി": 47,
        "galatians": 48, "gal": 48, "ഗലാത്യർ": 48, "ഗലാ": 48,
        "ephesians": 49, "eph": 49, "എഫെസ്യർ": 49, "എഫെ": 49,
        "philippians": 50, "phil": 50, "ഫിലിപ്പ്യർ": 50, "ഫിലി": 50,
        "colossians": 51, "col": 51, "കൊലൊസ്സ്യർ": 51, "കൊലൊ": 51,
        "1 thessalonians": 52, "1 thess": 52, "1 th": 52, "തെസ്സലൊനീക്യർ 1": 52, "1 തെസ്": 52,
        "2 thessalonians": 53, "2 thess": 53, "2 th": 53, "തെസ്സലൊനീക്യർ 2": 53, "2 തെസ്": 53,
        "1 timothy": 54, "1 tim": 54, "തിമൊഥെയൊസ് 1": 54, "1 തിമൊ": 54,
        "2 timothy": 55, "2 tim": 55, "തിമൊഥെയൊസ് 2": 55, "2 തിമൊ": 55,
        "titus": 56, "tit": 56, "തീത്തൊസ്": 56, "തീത്": 56,
        "philemon": 57, "phlm": 57, "ഫിലേമോൻ": 57, "ഫിലേ": 57,
        "hebrews": 58, "heb": 58, "എബ്രായർ": 58, "എബ്രാ": 58,
        "james": 59, "jas": 59, "യാക്കോബ്": 59, "യാക്": 59,
        "1 peter": 60, "1 pet": 60, "പത്രൊസ് 1": 60, "1 പത്": 60,
        "2 peter": 61, "2 pet": 61, "പത്രൊസ് 2": 61, "2 പത്": 61,
        "1 john": 62, "1 jn": 62, "യോഹന്നാൻ 1": 62, "1 യോഹ": 62,
        "2 john": 63, "2 jn": 63, "യോഹന്നാൻ 2": 63, "2 യോഹ": 63,
        "3 john": 64, "3 jn": 64, "യോഹന്നാൻ 3": 64, "3 യോഹ": 64,
        "jude": 65, "യൂദാ": 65,
        "revelation": 66, "rev": 66, "വെളിപ്പാടു്": 66, "വെളി": 66
    }

    def fuzzy_find_book(book_input, threshold=60):
        """Find the best matching book name using fuzzy matching"""
        best_match = None
        best_score = 0
        
        for book_name in book_map.keys():
            score = fuzz.ratio(book_input.lower(), book_name.lower())
            if score > best_score:
                best_score = score
                best_match = book_name
        
        if best_score >= threshold:
            return best_match, best_score
        return None, 0

    language_code_map = {
        'malayalam': 'ml', 'mal': 'ml',
        'english': 'kj', 'eng': 'kj',
        'hindi': 'hi', 'hin': 'hi',
        'tamil': 'ta', 'tam': 'ta',
        'telugu': 'te', 'tel': 'te',
        'kannada': 'kn', 'kan': 'kn',
        'marathi': 'mr', 'mar': 'mr',
        'gujarati': 'gu', 'guj': 'gu',
        'punjabi': 'pa', 'pun': 'pa',
        'bengali': 'bn', 'ben': 'bn',
        'urdu': 'ur', 'ur': 'ur',
        'spanish': 'es', 'es': 'es',
        'french': 'fr', 'fr': 'fr',
        'german': 'de', 'de': 'de',
        'chinese': 'zh', 'zh': 'zh',
        'japanese': 'ja', 'ja': 'ja',
        'russian': 'ru', 'ru': 'ru'
    }

    try:
        # Get language code
        key = lang.strip().lower()
        if key not in language_code_map:
            return (f"❌ Unsupported language '{lang}'", None, None, False)
        lc = language_code_map[key]

        # Parse input
        parts = user_input.strip().lower().split()
        if len(parts) < 2:
            return ("❌ Please provide both book and chapter (e.g., 'Gen 1')", None, None, False)

        # Extract chapter number (last part should be a number)
        try:
            chapter = int(parts[-1])
        except ValueError:
            return ("❌ Chapter must be a number", None, None, False)

        # Book name is everything except the last part
        book_input = ' '.join(parts[:-1])

        # First try exact match
        book_number = book_map.get(book_input)
        fuzzy_matched = False
        matched_book_name = book_input

        # If no exact match, try fuzzy matching
        if book_number is None:
            matched_book, score = fuzzy_find_book(book_input)
            if matched_book:
                book_number = book_map[matched_book]
                fuzzy_matched = True
                matched_book_name = matched_book
            else:
                available_books = list(set([k for k in book_map.keys() if not k.isdigit()]))[:10]
                return (f"❌ Book '{book_input}' not found. Available books include: {', '.join(available_books[:5])}...", None, None, False)

        # Construct the URL with the correct format
        url = f"https://www.wordproject.org/bibles/{lc}/{book_number:02d}/{chapter}.htm#0"
        return (url, matched_book_name, f"{matched_book_name.title()} {chapter}", fuzzy_matched)

    except Exception as e:
        return (f"❌ Error: {str(e)}", None, None, False)

# TODO: Add more Telegram-specific helpers as needed 
