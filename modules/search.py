from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import pandas as pd
from indicnlp.tokenize import indic_tokenize
import re

class SearchEngine:
    def __init__(self, dfH, dfL, dfC):
        self.dfH = dfH
        self.dfL = dfL
        self.dfC = dfC
        
        # Initialize vectorizers
        self.vectorizer_hymn = TfidfVectorizer(analyzer='char_wb', ngram_range=(3, 5))
        self.vectorizer_lyric = TfidfVectorizer(analyzer='char_wb', ngram_range=(3, 5))
        self.vectorizer_convention = TfidfVectorizer(analyzer='char_wb', ngram_range=(3, 5))
        
        # Create TF-IDF matrices
        self.tfidf_matrix_hymn = self.vectorizer_hymn.fit_transform(dfH['Hymn Index'].fillna(''))
        self.tfidf_matrix_lyric = self.vectorizer_lyric.fit_transform(dfL['Lyric Index'].fillna(''))
        self.tfidf_matrix_convention = self.vectorizer_convention.fit_transform(dfC['Convention Index'].fillna(''))

    def find_best_match(self, query, category="hymn", top_n=5):
        """
        Returns the top N best matching items for a given query.
        """
        if not query.strip():
            return "Query is empty. Please provide search text."
        
        category = category.lower().strip()
        category_map = {
            "hymn": {
                "vectorizer": self.vectorizer_hymn,
                "tfidf": self.tfidf_matrix_hymn,
                "data": self.dfH,
                "column": "Hymn no",
                "context": "Title" if "Title" in self.dfH.columns else None
            },
            "lyric": {
                "vectorizer": self.vectorizer_lyric,
                "tfidf": self.tfidf_matrix_lyric,
                "data": self.dfL,
                "column": "Lyric no",
                "context": "Line" if "Line" in self.dfL.columns else None
            },
            "convention": {
                "vectorizer": self.vectorizer_convention,
                "tfidf": self.tfidf_matrix_convention,
                "data": self.dfC,
                "column": "Convention no",
                "context": "Title" if "Title" in self.dfC.columns else None
            }
        }

        if category not in category_map:
            return f"Invalid category '{category}'. Choose from hymn, lyric, or convention."
        
        config = category_map[category]
        
        # Convert the query into its vector representation
        query_vec = config["vectorizer"].transform([query])
        similarities = cosine_similarity(query_vec, config["tfidf"]).flatten()

        if similarities.max() == 0:
            return "No match found. Try a different query."
        
        # Sort indices in descending order of similarity
        top_indices = similarities.argsort()[::-1]
        results = []
        
        for idx in top_indices:
            number = config["data"].iloc[idx][config["column"]]
            if int(number) == 0:
                continue  # Skip invalid or zero entries
            
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

    def search_index(self, no, option):
        """
        Returns the index (number) from the corresponding DataFrame.
        """
        try:
            no = int(no)
        except ValueError:
            return "Index must be an integer."
        
        if option == 'hymn':
            if no < 1 or no > len(self.dfH):
                return "Invalid hymn index."
            return self.dfH['Hymn Index'].iloc[no - 1]
        elif option == 'lyric':
            if no < 1 or no > len(self.dfL):
                return "Invalid lyric index."
            return self.dfL['Lyric Index'].iloc[no - 1]
        elif option == 'convention':
            if no < 1 or no > len(self.dfC):
                return "Invalid convention index."
            return self.dfC['Convention Index'].iloc[no - 1]
        else:
            return "Invalid option. Use 'hymn' or 'lyric'."

    @staticmethod
    def malayalam_tokenizer(text):
        """Tokenize Malayalam text using indic-nlp-library."""
        return indic_tokenize.trivial_tokenize(text, lang='ml')
