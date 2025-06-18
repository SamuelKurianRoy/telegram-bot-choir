def standardize_hlc_value(value):
   value = str(value).upper().strip()
   # Fix format if it's like H 23 or H23 -> H-23
   value = re.sub(r'^([HLC])\s*[-]?\s*(\d+)$', r'\1-\2', value)
   # Replace multiple hyphens with a single hyphen and remove spaces around them
   value = re.sub(r'-+', '-', value)
   value = re.sub(r'\s*-\s*', '-', value)
   return value

    
def IndexFinder(Song):
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
    


def Tune_finder_of_known_songs(song):
        song = standardize_hlc_value(song)
        if song.startswith("H"):
         song = song.replace('H','').strip().replace("-", "")
         song = int(song)
         return dfH['Tunes'][song-1]
        else:
         return "Invalid Number"

 
def ChoirVocabulary():
   def HymnVocabulary():
       # Extract hymns from the '1st Song', '2nd Song', '3rd Song', '4th Song', and '5th Song' columns
       hymns = []
       for column in ['1st Song', '2nd Song', '3rd Song', '4th Song', '5th Song']:
           try:
               # Drop original NaNs and convert the column to strings
               col_data = df[column].dropna().astype(str)
               # Filter rows that contain 'H'
               filtered = col_data[col_data.str.contains('H')]
               # Extract the first group of digits
               extracted = filtered.str.extract(r'(\d+)')[0]
               # Drop any NaN values resulting from extraction
               valid_numbers = extracted.dropna()
               # Convert the extracted digits to integers and add them to the list
               if not valid_numbers.empty:
                   hymns += valid_numbers.astype(int).tolist()
           except Exception as e:
               # Optionally log the error (e.g., print(e)) and continue processing.
               continue
       # Create a Pandas Series with the hymn numbers
       Hymn = pd.Series(hymns, name='Hymn no')
       # Get unique hymn numbers and sort them
       unique_sorted_hymn = pd.Series(Hymn.unique(), name='Hymn no').sort_values().reset_index(drop=True)
       return unique_sorted_hymn
   def LyricVocabulary():
       # Extract lyric hymns from the '1st Song', '2nd Song', '3rd Song', '4th Song', and '5th Song' columns
       lyric = []
       for column in ['1st Song', '2nd Song', '3rd Song', '4th Song', '5th Song']:
           try:
               col_data = df[column].dropna().astype(str)
               filtered = col_data[col_data.str.contains('L')]
               extracted = filtered.str.extract(r'(\d+)')[0]
               valid_numbers = extracted.dropna()
               if not valid_numbers.empty:
                   lyric += valid_numbers.astype(int).tolist()
           except Exception as e:
               continue
       Lyric = pd.Series(lyric, name='Lyric no')
       lyric_unique_sorted = pd.Series(Lyric.unique(), name="Lyric no").sort_values().reset_index(drop=True)
       return lyric_unique_sorted
   def ConventionVocabulary():
       # Extract convention hymns from the '1st Song', '2nd Song', '3rd Song', '4th Song', and '5th Song' columns
       convention = []
       for column in ['1st Song', '2nd Song', '3rd Song', '4th Song', '5th Song']:
           try:
               col_data = df[column].dropna().astype(str)
               filtered = col_data[col_data.str.contains('C')]
               extracted = filtered.str.extract(r'(\d+)')[0]
               valid_numbers = extracted.dropna()
               if not valid_numbers.empty:
                   convention += valid_numbers.astype(int).tolist()
           except Exception as e:
               continue
       Convention = pd.Series(convention, name='Convention no')
       convention_unique_sorted = pd.Series(Convention.unique(), name='Convention no').sort_values().reset_index(drop=True)
       return convention_unique_sorted

   def Vocabulary():
        # Create a DataFrame called vocabulary with these three series.
        # Convert numbers to strings for consistency in the vocabulary DataFrame.
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

 
 

# Define a function to apply IndexFinder to a vocabulary series
def apply_index_finder(vocab_series, prefix):
   # Combine prefix with number to create full song label (e.g., H123)
   full_labels = prefix + vocab_series.astype(str)
   # Apply IndexFinder
   return full_labels.apply(IndexFinder)

# Apply IndexFinder to each vocabulary type
 
 
 # Malayalam tokenizer using indic-nlp-library
def malayalam_tokenizer(text):
    return indic_tokenize.trivial_tokenize(text, lang='ml')
 
 # TF-IDF Vectorizer setup for Hymn, Lyric, and Convention with character n-grams
 # Hymn
 
 


def find_best_match(query, category="hymn", top_n=5):
    """
    Returns the top N best matching items (Hymn no / Lyric no / Convention no) for a given query,
    skipping entries with 0 as the number.
    
    :param query: Input text
    :param category: "hymn", "lyric", or "convention"
    :param top_n: Number of top matches to return
    :return: Tuple of (list of tuples, column label). Each tuple is (number, similarity, context)
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

def song_search_index():
    """
    Interactively gets a search query and category from the user and then prints the top 5 matches.
    """
    try:
        user_query = input("Enter search text: ").strip()
        category = input("Search in (hymn/lyric/convention)? ").strip().lower()

        result = find_best_match(user_query, category)
        if isinstance(result, str):
            print(result)
            return
        
        matches, column_label = result
        # Clean the label, e.g., "Hymn no" becomes "Hymn"
        label_clean = column_label.replace(" no", "").capitalize()
        
        print(f"\nTop {len(matches)} matches for '{user_query}' in {category}:\n")
        for i, (num, score, context) in enumerate(matches, 1):
            line = f"{i}. {label_clean} {num} (Similarity: {score:.3f})"
            if context and context.strip().lower() != "none":
                line += f" — {context.strip()}"
            print(line)
    
    except Exception as e:
        print(f"An error occurred: {e}")

 
 
def search_index(no, option):
     """
     Returns the index (number) from the corresponding DataFrame given the number and option.
     :param no: The one-based index number.
     :param option: "hymn" or "lyric".
     :return: The corresponding number or an error message.
     """
     try:
         no = int(no)
     except ValueError:
         return "Index must be an integer."
     
     if option == 'hymn':
         if no < 1 or no > len(dfH):
             return "Invalid hymn index."
         return dfH['Hymn Index'].iloc[no - 1]
     elif option == 'lyric':
         if no < 1 or no > len(dfL):
             return "Invalid lyric index."
         return dfL['Lyric Index'].iloc[no - 1]
     elif option == 'convention':
         if no < 1 or no > len(dfC):
             return "Invalid convention index."
         return dfC['Convention Index'].iloc[no - 1]
     else:
         return "Invalid option. Use 'hymn' or 'lyric'."


 
def getNotation(p):
  p=int(str(p))
  if p<=0:
    return "Enter a valid number"
  elif p<501:
    return f"https://online.fliphtml5.com/btdsx/ohjz/#p={p}"
  elif p<838:
    p-=500
    return f"https://online.fliphtml5.com/btdsx/bszu/#p={p}"
  else:
    return "Invalid Page Number"
  

  
def Music_notation_link(hymnno): 
    hymnno = standardize_hlc_value(hymnno)
    results = []

    if hymnno.startswith("H"):
        hymnno = hymnno.replace('H', '').strip().replace("-", "")
        hymnno = int(hymnno)
        t = dfH["Tunes"][hymnno - 1]
        t = t.split(',')

        for hymn_name in t:
            hymn_name = hymn_name.strip()
            tune = dfTH[dfTH["Hymn no"] == hymnno]["Tune Index"]
            tune = tune.tolist()

            if hymn_name in tune:
                mask = (dfTH["Hymn no"] == hymnno) & (dfTH["Tune Index"] == hymn_name)
                page_no = dfTH[mask]['Page no']
                if not page_no.empty:
                    page = str(page_no.values[0]).split(',')[0]
                    link = getNotation(page)
                    results.append(f'<a href="{link}">{hymn_name}</a>')
                else:
                    results.append(f'{hymn_name}: Page not found')
            else:
                for idx, i in enumerate(dfTH['Tune Index']):
                    i_list = str(i).split(',')
                    if hymn_name in i_list:
                        page_number = str(dfTH['Page no'].iloc[idx]).split(',')[0]
                        link = getNotation(page_number)
                        results.append(f'<a href="{link}">{hymn_name}</a>')

        if not results:
            return f"{Tune_finder_of_known_songs(f'H-{hymnno}')}: Notation not found"
        return "\n".join(results)

    else:
        return "Invalid Number"



  
      
 
 
def isVocabulary(Songs):
    songs_std = standardize_hlc_value(Songs)
    song = songs_std

    # Mapping prefixes to the corresponding column names
    prefix_mapping = {
        "H": "Hymn no",
        "L": "Lyric no",
        "C": "Convention no"
    }

    for prefix, col in prefix_mapping.items():
        if song.startswith(prefix):
            # strip off prefix/dashes and parse number
            number_str = song.replace(prefix, '').replace("-", '').strip()
            try:
                song_number = int(number_str)
            except ValueError:
                return f"Invalid song number: {song}"

            # build list of valid numbers in that column
            def to_int(x):
                x = x.strip()
                return int(x) if x.isdigit() and int(x) != 0 else None

            valid_numbers = (Vocabulary[col]
                             .dropna()
                             .apply(to_int)
                             .dropna()
                             .astype(int)
                             .values)

            # check membership
            in_vocab = song_number in valid_numbers

            # fetch your notation block (this will be lines joined by "\n")
            notation_block = ""
            if songs_std.startswith('H'):
                notation_block = Music_notation_link(songs_std)

            # build the tune_info multiline string
            tune_info = ""
            if notation_block:
                tune_info = "\n🎶 Tune:\n" + notation_block

            # choose the correct message template
            if in_vocab:
                return (
                    f"{songs_std}: {IndexFinder(songs_std)} is in the choir Vocabulary"
                    f"{tune_info}"
                )
            else:
                return (
                    f"{songs_std}: {IndexFinder(songs_std)} was not found in the choir Vocabulary"
                    f"{tune_info}"
                    "\n\nNote: A Known Song may appear here if it hasn't been sung in the past three years"
                )

    return "Invalid Response"


def Datefinder(songs, category=None, first=False):
    First=first
    Song = standardize_hlc_value(songs)
    Found = False
    formatted_date = []
    for i in range(len(df) - 1, -1, -1):
        if Song in df.iloc[i].tolist():
            Found = True
            date_val = df['Date'].iloc[i]
            formatted_date.append(date_val.strftime("%d/%m/%Y"))
            if First:
                break
    if Found and First:
         return f"{Song}: {IndexFinder(Song)} was last sung on: {formatted_date[0]}"
    elif Found:
        dates_string = ''.join(f"{i}\n" for i in formatted_date)
        return f"{Song}: {IndexFinder(Song)} was sung on: \n{dates_string}"

    else:
         return f"The Song {Song} was not Sang in the past years since 2022"

     
 
def filter_hymns_by_theme(data=dfH, theme=None):
     """
     Filters the DataFrame for rows where the "Themes" column contains the given theme.
     """
     filtered = data[data["Themes"].str.contains(theme, case=False, na=False)]
     return filtered
 
def hymn_filter_search(df):
     """
     Prompts the user for a theme, filters the DataFrame, and checks which hymns
     are in the Hymn_Vocabulary Series.
     Returns two lists: hymns in vocabulary and hymns not in vocabulary.
     """
     theme_input = input("Enter a theme to filter hymns: ").strip()
     filtered_df = filter_hymns_by_theme(df, theme_input)
 
     filtered_indf = []
     filtered_notindf = []
 
     if filtered_df.empty:
         print(f"No hymns found for theme: {theme_input}")
     else:
         for i in range(len(filtered_df)):
             hymn_no = filtered_df['Hymn no'].iloc[i]
             if hymn_no in Hymn_Vocabulary.values:
                 filtered_indf.append(hymn_no)
             else:
                 filtered_notindf.append(hymn_no)
 
     return filtered_indf, filtered_notindf
 
 
def get_songs_by_date(input_date):
    """
    Accepts:
    - 'DD/MM/YYYY', 'DD-MM-YYYY'
    - 'DD/MM/YY', 'DD-MM-YY'
    - 'DD/MM', 'DD-MM'
    - 'DD' (uses current month and year)

    If no songs found on the given date, returns next available date with songs.
    """
    today = date.today()
    current_year = today.year      # <--- No hardcoding here!
    current_month = today.month

    # Normalize input: replace '-' with '/' for easier parsing
    if isinstance(input_date, str):
        input_date = input_date.replace('-', '/').strip()
        parts = input_date.split('/')

        try:
            if len(parts) == 3:
                input_date = pd.to_datetime(input_date, dayfirst=True).date()
            elif len(parts) == 2:
                day, month = map(int, parts)
                input_date = date(current_year, month, day)
            elif len(parts) == 1:
                day = int(parts[0])
                input_date = date(current_year, current_month, day)
            else:
                return "Invalid date format. Use DD, DD/MM, DD/MM/YY, or DD/MM/YYYY."
        except Exception as e:
            return f"Date parsing error: {e}"

    # Continue with rest of logic...
    # (Same as in the previous version of the function)


    # Ensure 'Date' column is datetime.date
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce').dt.date
    df.dropna(subset=['Date'], inplace=True)

    # Sort dates
    available_dates = sorted(df['Date'].unique())

    # Find songs on the input date
    matching_rows = df[df['Date'] == input_date]

    if matching_rows.empty:
        # Get the next available date with songs
        next_dates = [d for d in available_dates if d > input_date]
        if not next_dates:
            return f"No songs found on {input_date.strftime('%d/%m/%Y')} or any later date."
        next_date = next_dates[0]
        matching_rows = df[df['Date'] == next_date]
        message = f"No songs found on {input_date.strftime('%d/%m/%Y')}. Showing songs from next available date: {next_date.strftime('%d/%m/%Y')}"
    else:
        next_date = input_date
        message = f"Songs sung on {next_date.strftime('%d/%m/%Y')}"

    # Get song columns
    song_columns = [col for col in df.columns if col != 'Date']
    songs = []

    for _, row in matching_rows.iterrows():
        for col in song_columns:
            song = row[col]
            if pd.notna(song) and str(song).strip() != '':
                songs.append(song.strip())

    return {
        "date": next_date.strftime('%d/%m/%Y'),
        "message": message,
        "songs": songs
    }
 
def Tunenofinder(no):
    try:
        no = int(no)
    except ValueError:
        return "Index must be an integer."
    
    if no < 1 or no > len(dfH):
        return "Invalid hymn index."
    
    result = dfTH[dfTH['Hymn no'] == no]['Tune Index']
    
    if not result.empty:
        # Strip whitespace from each tune name and join them on newline characters
        return "\n".join(tune.strip() for tune in result.tolist())
    else:
        return "Tune Index not found."
    
    
def Hymn_Tune_no_Finder(dfTH, tune_query, top_n=10):
    # Preprocess: lowercase all entries
    dfTH = dfTH.copy()
    dfTH['Tune Index'] = dfTH['Tune Index'].astype(str).str.lower()
    tune_query = tune_query.lower()

    # Combine all tune names into a list and add the query
    tune_list = dfTH['Tune Index'].tolist()
    all_tunes = tune_list + [tune_query]

    # Use character n-grams (for partial and fuzzy matching)
    vectorizer = TfidfVectorizer(analyzer='char_wb', ngram_range=(2, 4))
    tfidf_matrix = vectorizer.fit_transform(all_tunes)

    # Compute cosine similarity
    cosine_sim = cosine_similarity(tfidf_matrix[-1], tfidf_matrix[:-1]).flatten()

    # Get top N indices
    top_indices = cosine_sim.argsort()[::-1][:top_n]

    # Build results DataFrame
    results = dfTH.iloc[top_indices][['Hymn no', 'Tune Index']].copy()
    results['Similarity'] = cosine_sim[top_indices]

    return results.reset_index(drop=True)