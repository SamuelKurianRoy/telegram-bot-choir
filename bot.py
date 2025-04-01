from concurrent.futures import ThreadPoolExecutor
from googleapiclient.http import MediaIoBaseDownload
import io
import pandas as pd
import os
from googleapiclient.discovery import build
from google.oauth2 import service_account
import json
import re
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import pandas as pd
from indicnlp.tokenize import indic_tokenize
import streamlit as st
import tempfile
from googleapiclient.errors import HttpError

# Check for missing environment variables
lines = [st.secrets[f"l{i}"] for i in range(1, 29)]
private_key = "\n".join(lines)

service_account_data = {
    "type": st.secrets["type"],
    "project_id": st.secrets["project_id"],
    "private_key_id": st.secrets["private_key_id"],
    "private_key": private_key,
    "client_email": st.secrets["client_email"],
    "client_id": st.secrets["client_id"],
    "auth_uri": st.secrets["auth_uri"],
    "token_uri": st.secrets["token_uri"],
    "auth_provider_x509_cert_url": st.secrets["auth_provider_x509_cert_url"],
    "client_x509_cert_url": st.secrets["client_x509_cert_url"],
    "universe_domain": st.secrets["universe_domain"],
}

# Set the file IDs from environment variables
HFILE_ID = st.secrets["HFILE_ID"]
LFILE_ID = st.secrets["LFILE_ID"]
CFILE_ID = st.secrets["CFILE_ID"]
FILE_ID = st.secrets["FILE_ID"]
TOKEN = st.secrets["TOKEN"]

SCOPES = ["https://www.googleapis.com/auth/drive"]

print("✅ Environment variables loaded successfully!")

# Authenticate and build the drive service
creds = service_account.Credentials.from_service_account_info(service_account_data, scopes=SCOPES)
drive_service = build("drive", "v3", credentials=creds)

def download_file(file_id, label):
    """Downloads a Google Sheet file and loads it into a Pandas DataFrame"""
    request = drive_service.files().export_media(
        fileId=file_id,
        mimeType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    file_data = io.BytesIO()
    downloader = MediaIoBaseDownload(file_data, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()

    file_data.seek(0)  # Reset file pointer

    # Load the Excel data into Pandas
    try:
        df = pd.read_excel(file_data)
        print(f"✅ {label} has been loaded!")
        return df
    except Exception as e:
        print(f"❌ Failed to load {label}: {e}")
        return None

# Use ThreadPoolExecutor to download both files concurrently
with ThreadPoolExecutor(max_workers=2) as executor:
    future_HFILE = executor.submit(download_file, HFILE_ID, "Hymn Index")
    future_LFILE = executor.submit(download_file, LFILE_ID, "Lyric Index")
    future_CFILE = executor.submit(download_file, CFILE_ID, "Convention Index")

    dfH = future_HFILE.result()
    dfL = future_LFILE.result()
    dfC = future_CFILE.result()

# Step 2: Download the file into memory
request = drive_service.files().get_media(fileId=FILE_ID)
file_data = io.BytesIO()
downloader = MediaIoBaseDownload(file_data, request)
done = False
while not done:
    _, done = downloader.next_chunk()

file_data.seek(0)  # Reset file pointer

# Step 3: Read the Excel file into Pandas
try:
    xls = pd.ExcelFile(file_data)
    print("Excel file loaded successfully.")
except Exception as e:
    print(f"Failed to load Excel file: {e}")

# Load sheets into respective variables
sheets = {"2023": None, "2024": None, "2025": None, "Sheet 1": None}
for sheet in sheets:
    try:
        sheets[sheet] = pd.read_excel(xls, sheet_name=sheet)
        print(f"✅ Successfully loaded the '{sheet}' sheet.")
    except ValueError:
        print(f"❌ Sheet '{sheet}' not found.")

# Assign variables
yr23, yr24, yr25, df = sheets["2023"], sheets["2024"], sheets["2025"], sheets["Sheet 1"]



def yrDataPreprocessing():

   yr23.dropna(inplace=True)
   yr23.columns = yr23.iloc[0]
   yr23.drop(index=1,inplace=True)
   yr23.reset_index(drop=True,inplace=True)
   yr23['Date'] = pd.to_datetime(yr23['Date']).dt.date

   yr24.dropna(inplace=True)
   yr24.columns = yr24.iloc[0]
   yr24.drop(index=1,inplace=True)
   yr24.reset_index(drop=True,inplace=True)
   yr24['Date'] = pd.to_datetime(yr24['Date']).dt.date

   Themes= yr25['Unnamed: 6']
   yr25.drop('Unnamed: 6',axis=1,inplace=True)
   yr25.dropna(inplace=True)
   yr25.columns = yr25.iloc[0]
   yr25.drop(index=1,inplace=True)
   yr25.reset_index(drop=True,inplace=True)
   yr25['Date'] = pd.to_datetime(yr25['Date']).dt.date


yrDataPreprocessing()


df.dropna(inplace=True)
df.shape
df= df[pd.to_datetime(df['Date'],errors='coerce').notna()]
df = df[df['Date'].notna()]
df.reset_index(drop=True,inplace=True)
df['Date'] = pd.to_datetime(df['Date']).dt.date

def standardize_song_columns(df):
    standardized_df = df.copy()
    song_columns = [col for col in df.columns if col != 'Date']
    
    for col in song_columns:
        standardized_df[col] = standardized_df[col].astype(str).apply(lambda x: re.sub(r'\s+', '', x))
    
    return standardized_df
df = standardize_song_columns(df)




def standardize_hlc_value(value):
    
    # Replace multiple consecutive hyphens with a single hyphen
    value = re.sub(r'-+', '-', value)
    # Remove spaces around the hyphen and strip extra spaces
    value = re.sub(r'\s*-+\s*', '-', value).strip()
    return value

    


def ChoirVocabulary():
  def HymnVocabulary():
     # Extract hymns from the '1st Song', '2nd Song', '3rd Song', and '4th Song' columns
     hymns = []

     for column in ['1st Song', '2nd Song', '3rd Song', '4th Song']:
         # Extract hymn numbers that contain 'H'
         hymns += df[df[column].str.contains('H', na=False)][column].str.extract('(\d+)').astype(int).squeeze().tolist()

     # Create a Pandas Series with the hymn numbers
     Hymn = pd.Series(hymns, name='Hymn no')

     # Get unique hymn numbers and sort them
     unique_sorted_hymn = pd.Series(Hymn.unique(),name='Hymn').sort_values().reset_index(drop=True)

     # Display the sorted, unique hymn numbers
     return unique_sorted_hymn

  def LyricVocabulary():
    # Extract lyric hymns from the '1st Song', '2nd Song', '3rd Song', and '4th Song' columns
    lyric = []

    # Iterate through each column
    for column in ['1st Song', '2nd Song', '3rd Song', '4th Song']:
        # Extract lyric hymn numbers (assuming they contain 'L' and digits)
        lyric += df[df[column].str.contains('L', na=False)][column].str.extract('(\d+)').astype(int).squeeze().tolist()

    # Create a Pandas Series with the hymn numbers
    Lyric = pd.Series(lyric, name='Lyric no')

    # Get unique values and sort them
    lyric_unique_sorted = pd.Series(Lyric.unique(),name="Lyric").sort_values().reset_index(drop=True)

    # Display the sorted lyric hymn numbers
    return lyric_unique_sorted


  def ConventionVocabulary():
    # Extract convention hymns from the '1st Song', '2nd Song', '3rd Song', and '4th Song' columns
    convention = []

    # Iterate through each column
    for column in ['1st Song', '2nd Song', '3rd Song', '4th Song']:
        # Extract convention hymn numbers (assuming they contain 'C' and digits)
        convention += df[df[column].str.contains('C', na=False)][column].str.extract('(\d+)').astype(int).squeeze().tolist()

    # Create a Pandas Series with the hymn numbers
    Convention = pd.Series(convention, name='Convention no')

    # Get unique values and sort them
    convention_unique_sorted = pd.Series(Convention.unique(),name='Convention').sort_values().reset_index(drop=True)

    # Display the sorted convention hymn numbers
    return convention_unique_sorted

  def Vocabulary():

    # Create a DataFrame called vocabulary with these three series
    vocabulary = pd.DataFrame({'Hymn no': unique_sorted_hymn.astype("string"), 'Lyric no': lyric_unique_sorted.astype('string'), 'Convention no': convention_unique_sorted.astype('string')})

    # Display the vocabulary DataFrame
    vocabulary= vocabulary.fillna('')
    return vocabulary


  unique_sorted_hymn = HymnVocabulary()
  lyric_unique_sorted = LyricVocabulary()
  convention_unique_sorted = ConventionVocabulary()
  vocabulary = Vocabulary()
  return vocabulary, unique_sorted_hymn, lyric_unique_sorted, convention_unique_sorted


Vocabulary, Hymn_Vocabulary, Lyric_Vocabulary, Convention_Vocabulary = ChoirVocabulary()
VOCABULARY_CATEGORIES = {
    "Full Vocabulary": Vocabulary,
    "Hymn Vocabulary": Hymn_Vocabulary,
    "Lyric Vocabulary": Lyric_Vocabulary,
    "Convention Vocabulary": Convention_Vocabulary,
}



# Malayalam tokenizer using indic-nlp-library
def malayalam_tokenizer(text):
    return indic_tokenize.trivial_tokenize(text, lang='ml')

# TF-IDF Vectorizer setup for Hymn and Lyric
vectorizer_hymn = TfidfVectorizer(analyzer='word', tokenizer=malayalam_tokenizer, token_pattern=None)
tfidf_matrix_hymn = vectorizer_hymn.fit_transform(dfH['Hymn Index'])

vectorizer_lyric = TfidfVectorizer(analyzer='word', tokenizer=malayalam_tokenizer, token_pattern=None)
tfidf_matrix_lyric = vectorizer_lyric.fit_transform(dfL['Lyric Index'])

vectorizer_convention = TfidfVectorizer(analyzer='word', tokenizer=malayalam_tokenizer, token_pattern=None)
tfidf_matrix_convention = vectorizer_convention.fit_transform(dfC['Convention Index'])

def find_best_match(query, category="hymn"):
    """
    Given a query string, this function returns the best matching hymn or lyric number.
    :param query: Input text
    :param category: "hymn" for Hymn Index, "lyric" for Lyric Index
    :return: Best matching number (Hymn no or Lyric no)
    """
    if category == "hymn":
        vectorizer = vectorizer_hymn
        tfidf_matrix = tfidf_matrix_hymn
        data = dfH
        column_no = 'Hymn no'
    elif category == "lyric":
        vectorizer = vectorizer_lyric
        tfidf_matrix = tfidf_matrix_lyric
        data = dfL
        column_no = 'Lyric no'
    elif category == "convention":
        vectorizer = vectorizer_convention
        tfidf_matrix = tfidf_matrix_convention
        data = dfC
        column_no = 'Convention no'
    else:
        return "Invalid category!"

    # Transform the query into the TF-IDF vector space
    query_vec = vectorizer.transform([query])
    
    # Compute cosine similarity between the query and each text
    similarities = cosine_similarity(query_vec, tfidf_matrix).flatten()
    
    # Find the index with the highest similarity score
    best_index = similarities.argmax()
    
    # Return the corresponding hymn or lyric number
    return data[column_no].iloc[best_index]

# Example usage:
def song_search_index():
    user_query = input("Enter search text: ")  # Example: "ആത്മാവേ നീ"
    category = input("Search in (hymn/lyric/convention)? ").strip().lower()

    result_number = find_best_match(user_query, category)
    print(f"The best match for your query is: {result_number}")


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
     


def isVocabulary(Songs):
    Found = False
    songs = standardize_hlc_value(Songs)
    song= songs

    if song.startswith("H"):
        song = song.replace('H', '').replace("-", '').strip()
        song = int(song)
        for i in Vocabulary['Hymn no']:
            if int(i) == 0:
                break
            elif int(i) == song:
                Found = True
                break
    elif song.startswith("L"):
        song = song.replace('L', '').replace("-", '').strip()
        song = int(song)
        for i in Vocabulary['Lyric no']:
            if int(i) == 0:
                break
            elif int(i) == song:
                Found = True
                break
    elif song.startswith("C"):
        song = song.replace('C', '').replace("-", '').strip()
        song = int(song)
        for i in Vocabulary['Convention no']:
            if int(i) == 0:
                break
            elif int(i) == song:
                Found = True
                break
    else:
        print("Invalid Response")

    if Found:
        return f"{songs}: {IndexFinder(songs)} is in the choir Vocabulary"
    else:
        return "The Song was not found in the choir vocabulary"


def Datefinder(songs):
    Song = standardize_hlc_value(songs)
    Found = False
    for i in range(len(df) - 1, -1, -1):
        if Song in df.iloc[i].tolist():
            Found = True
            Songs = df['Date'].iloc[i]
            formatted_date = Songs.strftime("%d/%m/%Y")
            break
    if Found:
        return f"{Song}: {IndexFinder(Song)}  was last sung on: {formatted_date}"
    else:
        return "Song Not Sang in the past years since 2022"

  
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
    

def filter_hymns_by_theme(data, theme):
    """
    Filters the DataFrame for rows where the "Themes" column contains the given theme.
    """
    filtered = data[data["Themes"].str.contains(theme, case=False, na=False)]
    return filtered


# ------------------------------
# Streamlit App
# ------------------------------

st.title("Choir Song App")
st.write("Welcome to the Choir Song App! Use the sidebar to select a function.")

# Sidebar menu for navigation
menu_options = [
    "Check Song",
    "Last Sung",
    "Search by Text",
    "Search by Index",
    "Filter by Theme",
    "Vocabulary"
]
choice = st.sidebar.selectbox("Select Function", menu_options)

# --- Check Song ---
if choice == "Check Song":
    st.header("Check if a Song is in the Vocabulary")
    song_input = st.text_input("Enter song (e.g., H-27):")
    if st.button("Check Song"):
        result = isVocabulary(song_input)
        st.write(result)

# --- Last Sung ---
elif choice == "Last Sung":
    st.header("Find Last Sung Date")
    song_input = st.text_input("Enter song (e.g., H-27):")
    if st.button("Find Last Sung Date"):
        result = Datefinder(song_input)
        st.write(result)

# --- Search by Text ---
elif choice == "Search by Text":
    st.header("Search for a Song by Text")
    category = st.selectbox("Select Category", ["hymn", "lyric", "convention"])
    query = st.text_input("Enter search text:")
    if st.button("Search"):
        result = find_best_match(query, category)
        st.write(result)

# --- Search by Index ---
elif choice == "Search by Index":
    st.header("Search for a Song by Index")
    category = st.selectbox("Select Category", ["hymn", "lyric", "convention"], key="index_category")
    index_input = st.text_input("Enter index number:")
    if st.button("Search by Index"):
        try:
            index_num = int(index_input)
            result = search_index(index_num, category)
        except ValueError:
            result = "Index must be an integer."
        st.write(result)

# --- Filter by Theme ---
elif choice == "Filter by Theme":
    st.header("Filter Hymns by Theme")
    theme_input = st.text_input("Enter theme (e.g., Joy):")
    if st.button("Filter"):
        filtered_df = filter_hymns_by_theme(dfH, theme_input)
        if filtered_df.empty:
            st.write(f"No hymns found for theme: '{theme_input}'")
        else:
            st.write(f"Filtered Hymns for theme '{theme_input}':")
            for _, row in filtered_df.iterrows():
                st.write(f"Hymn no: {row['Hymn no']} - {row['Hymn Index']}")

# --- Vocabulary ---
elif choice == "Vocabulary":
    st.header("Vocabulary Export")
    vocab_choice = st.selectbox("Select Vocabulary", list(VOCABULARY_CATEGORIES.keys()))
    data = VOCABULARY_CATEGORIES[vocab_choice]

    # If the vocabulary is a Series, convert it to a DataFrame for consistent display.
    if isinstance(data, pd.Series):
        data = data.to_frame(name=vocab_choice)
    
    st.write(f"{vocab_choice} Preview:")
    st.dataframe(data.head(10))
    
    # Option to export as Excel
    if st.button("Export as Excel"):
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            data.to_excel(writer, sheet_name="Vocabulary", index=False)
        output.seek(0)
        st.download_button(
            label="Download Excel file",
            data=output,
            file_name=f"{vocab_choice}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )