# utils/search.py
# Search, matching, and index utilities

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# These should be set up after loading the datasets
tfidf_vectorizers = {}
tfidf_matrices = {}
dataframes = {}

# Call this after loading datasets to initialize search

def setup_search(dfH, dfL, dfC):
    global tfidf_vectorizers, tfidf_matrices, dataframes
    tfidf_vectorizers = {
        'hymn': TfidfVectorizer(analyzer='char_wb', ngram_range=(3, 5)),
        'lyric': TfidfVectorizer(analyzer='char_wb', ngram_range=(3, 5)),
        'convention': TfidfVectorizer(analyzer='char_wb', ngram_range=(3, 5)),
    }
    tfidf_matrices = {
        'hymn': tfidf_vectorizers['hymn'].fit_transform(dfH['Hymn Index'].fillna('')),
        'lyric': tfidf_vectorizers['lyric'].fit_transform(dfL['Lyric Index'].fillna('')),
        'convention': tfidf_vectorizers['convention'].fit_transform(dfC['Convention Index'].fillna('')),
    }
    dataframes = {'hymn': dfH, 'lyric': dfL, 'convention': dfC}

def find_best_match(query, category="hymn", top_n=5):
    """
    Returns the top N best matching items for a given query in the specified category.
    """
    if not query.strip():
        return "Query is empty. Please provide search text."
    category = category.lower().strip()
    if category not in tfidf_vectorizers:
        return f"Invalid category '{category}'. Choose from hymn, lyric, or convention."
    vectorizer = tfidf_vectorizers[category]
    tfidf_matrix = tfidf_matrices[category]
    df = dataframes[category]
    column = {
        'hymn': 'Hymn no',
        'lyric': 'Lyric no',
        'convention': 'Convention no',
    }[category]
    context_col = {
        'hymn': 'Title' if 'Title' in df.columns else None,
        'lyric': 'Line' if 'Line' in df.columns else None,
        'convention': 'Title' if 'Title' in df.columns else None,
    }[category]
    query_vec = vectorizer.transform([query])
    similarities = cosine_similarity(query_vec, tfidf_matrix).flatten()
    if similarities.max() == 0:
        return "No match found. Try a different query."
    top_indices = similarities.argsort()[::-1]
    results = []
    for idx in top_indices:
        number = df.iloc[idx][column]
        if int(number) == 0:
            continue
        similarity = round(float(similarities[idx]), 3)
        context = (
            str(df.iloc[idx][context_col])
            if context_col and pd.notna(df.iloc[idx][context_col])
            else None
        )
        results.append((int(number), similarity, context))
        if len(results) == top_n:
            break
    return results, column

def search_index(no, option):
    try:
        no = int(no)
    except ValueError:
        return "Index must be an integer."
    if option == 'hymn':
        df = dataframes['hymn']
        if no < 1 or no > len(df):
            return "Invalid hymn index."
        return df['Hymn Index'].iloc[no - 1]
    elif option == 'lyric':
        df = dataframes['lyric']
        if no < 1 or no > len(df):
            return "Invalid lyric index."
        return df['Lyric Index'].iloc[no - 1]
    elif option == 'convention':
        df = dataframes['convention']
        if no < 1 or no > len(df):
            return "Invalid convention index."
        return df['Convention Index'].iloc[no - 1]
    else:
        return "Invalid option. Use 'hymn', 'lyric', or 'convention'." 