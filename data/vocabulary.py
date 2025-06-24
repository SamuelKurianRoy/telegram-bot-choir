# data/vocabulary.py
# Vocabulary extraction and related helpers 

import pandas as pd
import re
from utils.notation import Music_notation_link

# Vocabulary extraction and helpers

def ChoirVocabulary(df, dfH, dfL, dfC):
    """
    Extracts hymn, lyric, and convention vocabularies from the main DataFrame.
    Returns: (Vocabulary, Hymn_Vocabulary, Lyric_Vocabulary, Convention_Vocabulary)
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

    unique_sorted_hymn = HymnVocabulary()
    lyric_unique_sorted = LyricVocabulary()
    convention_unique_sorted = ConventionVocabulary()

    vocabulary = pd.DataFrame({
        'Hymn no': unique_sorted_hymn.astype("string"),
        'Lyric no': lyric_unique_sorted.astype("string"),
        'Convention no': convention_unique_sorted.astype("string")
    }).fillna('')

    return vocabulary, unique_sorted_hymn, lyric_unique_sorted, convention_unique_sorted

def standardize_hlc_value(value):
    value = str(value).upper().strip()
    value = re.sub(r'^([HLC])\s*[-]?\s*(\d+)$', r'\1-\2', value)
    value = re.sub(r'-+', '-', value)
    value = re.sub(r'\s*-\s*', '-', value)
    return value

def isVocabulary(Songs, Vocabulary, dfH, dfTH, Tune_finder_of_known_songs):
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
                notation_block = Music_notation_link(songs_std, dfH, dfTH, Tune_finder_of_known_songs)
            tune_info = ""
            if notation_block:
                tune_info = "\n🎶 Tune:\n" + notation_block
            if in_vocab:
                return (
                    f"{songs_std}: is in the choir Vocabulary"
                    f"{tune_info}"
                )
            else:
                return (
                    f"{songs_std}: was not found in the choir Vocabulary"
                    f"{tune_info}"
                    "\n\nNote: A Known Song may appear here if it hasn't been sung in the past three years"
                )
    return "Invalid Response"

# TODO: Add more helpers as needed for vocabulary management 