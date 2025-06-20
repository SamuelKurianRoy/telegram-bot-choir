import re
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from indicnlp.tokenize import indic_tokenize

# --- Song/Hymn/Lyric/Convention Logic ---
def standardize_hlc_value(value):
    """
    Standardizes HLC song codes (e.g., H 23, H23 -> H-23).
    """
    value = str(value).upper().strip()
    value = re.sub(r'^([HLC])\s*[-]?\s*(\d+)$', r'\1-\2', value)
    value = re.sub(r'-+', '-', value)
    value = re.sub(r'\s*-\s*', '-', value)
    return value

def IndexFinder(Song, dfH, dfL, dfC):
    song = standardize_hlc_value(Song)
    if song.startswith("H"):
        song = song.replace('H','').strip().replace("-", "")
        song = int(song)
        return dfH['Hymn Index'][song-1]
    elif song.startswith("L"):
        song = song.replace('L','').strip().replace("-", "")
        song = int(song)
        return dfL['Lyric Index'][song-1]
    elif song.startswith("C"):
        song = song.replace('C','').strip().replace("-", "")
        song = int(song)
        return dfC['Convention Index'][song-1]
    else:
        return "Invalid Number"

def Tune_finder_of_known_songs(song, dfH):
    song = standardize_hlc_value(song)
    if song.startswith("H"):
        song = song.replace('H','').strip().replace("-", "")
        song = int(song)
        return dfH['Tunes'][song-1]
    else:
        return "Invalid Number"

def ChoirVocabulary(df, dfH, dfL, dfC):
    """
    Extracts vocabulary for hymns, lyrics, and conventions from the main DataFrame.
    Returns: vocabulary, unique_sorted_hymn, lyric_unique_sorted, convention_unique_sorted
    """
    def HymnVocabulary():
        hymns = []
        for column in ['1st Song', '2nd Song', '3rd Song', '4th Song', '5th Song']:
            try:
                col_data = df[column].dropna().astype(str)
                filtered = col_data[col_data.str.contains('H')]
                extracted = filtered.str.extract(r'(\d+)')[0]
                valid_numbers = extracted.dropna()
                if not valid_numbers.empty:
                    hymns += valid_numbers.astype(int).tolist()
            except Exception:
                continue
        Hymn = pd.Series(hymns, name='Hymn no')
        unique_sorted_hymn = pd.Series(Hymn.unique(), name='Hymn no').sort_values().reset_index(drop=True)
        return unique_sorted_hymn
    def LyricVocabulary():
        lyric = []
        for column in ['1st Song', '2nd Song', '3rd Song', '4th Song', '5th Song']:
            try:
                col_data = df[column].dropna().astype(str)
                filtered = col_data[col_data.str.contains('L')]
                extracted = filtered.str.extract(r'(\d+)')[0]
                valid_numbers = extracted.dropna()
                if not valid_numbers.empty:
                    lyric += valid_numbers.astype(int).tolist()
            except Exception:
                continue
        Lyric = pd.Series(lyric, name='Lyric no')
        lyric_unique_sorted = pd.Series(Lyric.unique(), name="Lyric no").sort_values().reset_index(drop=True)
        return lyric_unique_sorted
    def ConventionVocabulary():
        convention = []
        for column in ['1st Song', '2nd Song', '3rd Song', '4th Song', '5th Song']:
            try:
                col_data = df[column].dropna().astype(str)
                filtered = col_data[col_data.str.contains('C')]
                extracted = filtered.str.extract(r'(\d+)')[0]
                valid_numbers = extracted.dropna()
                if not valid_numbers.empty:
                    convention += valid_numbers.astype(int).tolist()
            except Exception:
                continue
        Convention = pd.Series(convention, name='Convention no')
        convention_unique_sorted = pd.Series(Convention.unique(), name='Convention no').sort_values().reset_index(drop=True)
        return convention_unique_sorted
    def Vocabulary():
        vocabulary = pd.DataFrame({
            'Hymn no': unique_sorted_hymn.astype("string"),
            'Lyric no': lyric_unique_sorted.astype("string"),
            'Convention no': convention_unique_sorted.astype("string")
        })
        vocabulary = vocabulary.fillna('')
        return vocabulary
    unique_sorted_hymn = HymnVocabulary()
    lyric_unique_sorted = LyricVocabulary()
    convention_unique_sorted = ConventionVocabulary()
    vocabulary = Vocabulary()
    return vocabulary, unique_sorted_hymn, lyric_unique_sorted, convention_unique_sorted

def isVocabulary(Songs, Vocabulary, dfH, Music_notation_link):
    songs_std = standardize_hlc_value(Songs)
    song = songs_std
    prefix_mapping = {
        "H": "Hymn no",
        "L": "Lyric no",
        "C": "Convention no"
    }
    for prefix, col in prefix_mapping.items():
        if song.startswith(prefix):
            number_str = song.replace(prefix, '').replace("-", '').strip()
            try:
                song_number = int(number_str)
            except ValueError:
                return f"Invalid song number: {song}"
            def to_int(x):
                x = x.strip()
                return int(x) if x.isdigit() and int(x) != 0 else None
            valid_numbers = (Vocabulary[col]
                             .dropna()
                             .apply(to_int)
                             .dropna()
                             .astype(int)
                             .values)
            in_vocab = song_number in valid_numbers
            notation_block = ""
            if songs_std.startswith('H'):
                notation_block = Music_notation_link(songs_std)
            tune_info = ""
            if notation_block:
                tune_info = "\n🎶 Tune:\n" + notation_block
            if in_vocab:
                return (
                    f"{songs_std}: {IndexFinder(songs_std, dfH, None, None)} is in the choir Vocabulary"
                    f"{tune_info}"
                )
            else:
                return (
                    f"{songs_std}: {IndexFinder(songs_std, dfH, None, None)} was not found in the choir Vocabulary"
                    f"{tune_info}"
                    "\n\nNote: A Known Song may appear here if it hasn't been sung in the past three years"
                )
    return "Invalid Response"

def find_best_match(query, category, vectorizer_hymn, tfidf_matrix_hymn, dfH, vectorizer_lyric, tfidf_matrix_lyric, dfL, vectorizer_convention, tfidf_matrix_convention, dfC, top_n=5):
    """
    Returns the top N best matching items (Hymn no / Lyric no / Convention no) for a given query.
    """
    if not query.strip():
        return "Query is empty. Please provide search text."
    category = category.lower().strip()
    category_map = {
        "hymn": {
            "vectorizer": vectorizer_hymn,
            "tfidf": tfidf_matrix_hymn,
            "data": dfH,
            "column": "Hymn no",
            "context": "Title" if "Title" in dfH.columns else None
        },
        "lyric": {
            "vectorizer": vectorizer_lyric,
            "tfidf": tfidf_matrix_lyric,
            "data": dfL,
            "column": "Lyric no",
            "context": "Line" if "Line" in dfL.columns else None
        },
        "convention": {
            "vectorizer": vectorizer_convention,
            "tfidf": tfidf_matrix_convention,
            "data": dfC,
            "column": "Convention no",
            "context": "Title" if "Title" in dfC.columns else None
        }
    }
    if category not in category_map:
        return f"Invalid category '{category}'. Choose from hymn, lyric, or convention."
    config = category_map[category]
    query_vec = config["vectorizer"].transform([query])
    similarities = cosine_similarity(query_vec, config["tfidf"]).flatten()
    if similarities.max() == 0:
        return "No match found. Try a different query."
    top_indices = similarities.argsort()[::-1]
    results = []
    for idx in top_indices:
        number = config["data"].iloc[idx][config["column"]]
        if int(number) == 0:
            continue
        similarity = round(float(similarities[idx]), 3)
        context = (
            str(config["data"].iloc[idx][config["context"]])
            if config["context"] and pd.notna(config["data"].iloc[idx][config["context"]])
            else None
        )
        results.append((int(number), similarity, context))
        if len(results) == top_n:
            break
    return results, config["column"]

def malayalam_tokenizer(text):
    return indic_tokenize.trivial_tokenize(text, lang='ml')

# ... (other helpers and logic can be added here as needed) ... 