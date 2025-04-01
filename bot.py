from concurrent.futures import ThreadPoolExecutor
from googleapiclient.http import MediaIoBaseDownload
import io
import pandas as pd
import os
from googleapiclient.discovery import build
from google.oauth2 import service_account
import json
import logging
from telegram.ext import Application, CommandHandler, ConversationHandler, MessageHandler, filters, CallbackContext
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
import re
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import pandas as pd
from indicnlp.tokenize import indic_tokenize

# Check for missing environment variables
lines = [os.getenv(f"l{i}") for i in range(1, 29)]
if any(line == "" or line is None for line in lines):
    missing = [f"l{i}" for i in range(1, 29) if (os.getenv(f"l{i}") == "" or os.getenv(f"l{i}") is None)]
    raise ValueError(f"Missing or empty environment variables: {', '.join(missing)}")

# Join them into a single private key
private_key = "\n".join(lines)

# Dynamically construct the service account JSON
service_account_data = {
    "type": os.getenv("type"),
    "project_id": os.getenv("project_id"),
    "private_key_id": os.getenv("private_key_id"),
    "private_key": private_key,
    "client_email": os.getenv("client_email"),
    "client_id": os.getenv("client_id"),
    "auth_uri": os.getenv("auth_uri"),
    "token_uri": os.getenv("token_uri"),
    "auth_provider_x509_cert_url": os.getenv("auth_provider_x509_cert_url"),
    "client_x509_cert_url": os.getenv("client_x509_cert_url"),
    "universe_domain": os.getenv("universe_domain"),
}

# Save the JSON to a temporary file
KEY_PATH = "service_account.json"
with open(KEY_PATH, "w") as f:
    json.dump(service_account_data, f)

# Set the GOOGLE_APPLICATION_CREDENTIALS environment variable
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = KEY_PATH

# Set the file IDs from environment variables
HFILE_ID = os.getenv("HFILE_ID")
LFILE_ID = os.getenv("LFILE_ID")
CFILE_ID = os.getenv("CFILE_ID")
FILE_ID = os.getenv("FILE_ID")
TOKEN = os.getenv("TOKEN")

SCOPES = ["https://www.googleapis.com/auth/drive"]

print("✅ Environment variables loaded successfully!")

# Enable logging
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)

# Authenticate and build the drive service
creds = service_account.Credentials.from_service_account_file(KEY_PATH, scopes=SCOPES)
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

# def hymn_filter_search(df):
#     """
#     Prompts the user for a theme, filters the DataFrame, and displays the hymn details.
#     """
#     theme_input = input("Enter a theme to filter hymns: ").strip()
#     filtered_df = filter_hymns_by_theme(df, theme_input)
    
#     if filtered_df.empty:
#         print(f"No hymns found for theme: {theme_input}")
#     else:
#         print("Filtered Hymns:")
#         return filtered_df





#Telegram bot

async def start(update: Update, context: CallbackContext) -> None:
    """Handles the /start command."""
    welcome_text = (
        "🎵 *Welcome to the Choir Song Bot!*\n\n"
        "Use `/check <song>` to check if a song is in the vocabulary.\n"
        "Use `/last <song>` to find when it was last sung.\n"
        "Use `/searchno <category> <search text>` to search for a hymn, lyric, or convention by text.\n"
        "Use `/searchindex` to interactively search by index: you'll be prompted to select 'Hymn' or 'Lyric' and then provide the index number.\n"
        "_Example:_ Type `/searchindex` and follow the prompts."
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

async def help_command(update: Update, context: CallbackContext) -> None:
    help_text = (
        "🎵 *Choir Song Bot Help*\n\n"
        "Here are the available commands and how to use them:\n\n"
        "• **/start**\n"
        "  - *Description:* Starts the bot and shows the welcome message with basic instructions.\n"
        "  - *Example:* Simply type `/start`.\n\n"
        "• **/check <song>**\n"
        "  - *Description:* Checks if a song is in the vocabulary.\n"
        "  - *Example:* `/check H-27`\n\n"
        "• **/last <song>**\n"
        "  - *Description:* Finds out when the song was last sung.\n"
        "  - *Example:* `/last H-27`\n\n"
        "• **/searchno <category> <search text>**\n"
        "  - *Description:* Searches for a hymn, lyric, or convention by text using TF-IDF matching.\n"
        "  - *Category Options:* `hymn`, `lyric`, or `convention`.\n"
        "  - *Example:* `/searchno hymn ആത്മാവേ നീ`\n\n"
        "• **/searchindex**\n"
        "  - *Description:* Initiates an interactive search by index.\n"
        "  - *Process:* The bot will prompt you to select a category (Hymn, Lyric, or Convention) and then ask for the index number.\n"
        "  - *Example:* Type `/searchindex` and follow the prompts.\n\n"
        "• **/filtertheme <theme>**\n"
        "  - *Description:* Filters the hymns by the specified theme and displays matching hymn numbers and titles.\n"
        "  - *Example:* `/filtertheme Additional Hymns`\n\n"
        "• **/vocabulary**\n"
        "  - *Description:* Starts the vocabulary export conversation.\n"
        "  - *Example:* Type `/vocabulary` and follow the instructions.\n\n"
        "• **/cancel**\n"
        "  - *Description:* Cancels the current operation.\n"
        "  - *Example:* If you are in a conversation, type `/cancel` to stop it.\n\n"
        "If you need further assistance, feel free to ask!"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")



async def check_song(update: Update, context: CallbackContext) -> None:
    if not context.args:
        await update.message.reply_text("⚠️ Please provide a song number.\n_Example:_ `/check H-27`", parse_mode="Markdown")
        return
    # Join all parts of the argument into a single string
    song = " ".join(context.args)
    result = isVocabulary(song)
    await update.message.reply_text(result)


async def last_sung(update: Update, context: CallbackContext) -> None:
    if not context.args:
        await update.message.reply_text("⚠️ Please provide a song number.\n_Example:_ `/last H-27`", parse_mode="Markdown")
        return
    song = " ".join(context.args)
    result = Datefinder(song)
    await update.message.reply_text(result)

async def search_no(update: Update, context: CallbackContext) -> None:
    """
    New command: /searchno
    Usage: /searchno <category> <search text>
    For example: /searchno hymn ആത്മാവേ നീ
    """
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("⚠️ Please provide a category and search text.\n_Example:_ `/searchno hymn ആത്മാവേ നീ`", parse_mode="Markdown")
        return
    # Extract the category (first argument) and the query (rest of the arguments)
    category = context.args[0].strip().lower()
    query = " ".join(context.args[1:])
    result = find_best_match(query, category)
    await update.message.reply_text(f"The best match for your query is: {result}")

# --- Conversation Handler for /searchindex command ---
SEARCH_CATEGORY, SEARCH_NUMBER = range(2)

async def search_index_start(update: Update, context: CallbackContext) -> int:
    """
    Starts the conversation by asking the user whether to search in hymn or lyric.
    """
    keyboard = [["Hymn", "Lyric","Convention"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
    await update.message.reply_text("Please select which index you want to search:", reply_markup=reply_markup)
    return SEARCH_CATEGORY

async def search_index_category(update: Update, context: CallbackContext) -> int:
    """
    Stores the chosen category and asks the user for the index number.
    """
    user_choice = update.message.text.strip().lower()
    if user_choice not in ["hymn", "lyric","convention"]:
        await update.message.reply_text("Invalid choice. Please select either 'Hymn' , 'Lyric' or 'Convention'.")
        return SEARCH_CATEGORY
    context.user_data["search_index_category"] = user_choice
    await update.message.reply_text("Please enter the index number:")
    return SEARCH_NUMBER

async def search_index_number(update: Update, context: CallbackContext) -> int:
    """
    Processes the index number, calls the search_index function, and returns the result.
    """
    index_text = update.message.text.strip()
    category = context.user_data.get("search_index_category")
    try:
        index_num = int(index_text)
    except ValueError:
        await update.message.reply_text("Index must be an integer. Please enter a valid index number:")
        return SEARCH_NUMBER
    
    result = search_index(index_num, category)
    await update.message.reply_text(f"Search index result: {result}", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def search_index_cancel(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text("Search index operation cancelled.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END




# Step 1: Start vocabulary conversation
CATEGORY_SELECTION, EXPORT_CONFIRMATION = range(2)
async def start_vocabulary(update: Update, context: CallbackContext) -> int:
    keyboard = [
        ["Full Vocabulary", "Hymn Vocabulary"],
        ["Lyric Vocabulary", "Convention Vocabulary"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
    await update.message.reply_text(
        "📚 Please choose a vocabulary category:", reply_markup=reply_markup
    )
    return CATEGORY_SELECTION

# Step 2: Process category selection and show preview
async def category_selection(update: Update, context: CallbackContext) -> int:
    user_choice = update.message.text.strip()
    if user_choice not in VOCABULARY_CATEGORIES:
        await update.message.reply_text("⚠️ Invalid choice. Please use /vocabulary again.")
        return CATEGORY_SELECTION

    data = VOCABULARY_CATEGORIES[user_choice]

    # Convert Series to DataFrame if needed
    
    # If it's a Series, convert it to a DataFrame for consistency.
    if isinstance(data, pd.Series):
        data = data.to_frame(name=user_choice)
    # For "Full Vocabulary", remove rows where all values are zero.
    if user_choice == "Full Vocabulary":
        data = data[(data != 0).any(axis=1)]
    else:
        # For Series-based vocabularies, remove rows where the value is zero.
        data = data[data[user_choice] != 0]

    # Store the cleaned data and filename in user_data.
    context.user_data["export_data"] = data
    context.user_data["export_filename"] = f"{user_choice}.xlsx"

    # Show a preview (first 10 rows) of the data.
    preview_text = f"📋 {user_choice} Preview:\n" + data.head(10).to_string(index=False)
    await update.message.reply_text(preview_text)

    # Ask if the user wants to export the data as Excel
    


    # Ask the user if they want to export the data.
    keyboard = [["Yes", "No"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
    await update.message.reply_text("📂 Would you like to export this as an Excel file?", reply_markup=reply_markup)
    return EXPORT_CONFIRMATION

# Step 3: Handle the export confirmation.
async def export_confirmation(update: Update, context: CallbackContext) -> int:
    response = update.message.text.strip().lower()
    if response == "yes":
        if "export_data" in context.user_data:
            data = context.user_data["export_data"]
            filename = context.user_data["export_filename"]

            # Convert the DataFrame to an in-memory Excel file.
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                data.to_excel(writer, sheet_name="Vocabulary", index=False)
            output.seek(0)  # Reset the pointer to the beginning of the file

            await update.message.reply_document(
                document=output,
                filename=filename,
                caption="📂 Here is your vocabulary data in Excel format."
            )
        else:
            await update.message.reply_text("⚠️ No data found for export.")
    elif response == "no":
        if "export_data" in context.user_data:
            data = context.user_data["export_data"]
            full_vocab = data.to_string(index=False)
            # Send the full vocabulary as text (using Markdown formatting for a code block)
            await update.message.reply_text(
                f"Here is the full vocabulary:\n```\n{full_vocab}\n```",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardRemove()
            )
        else:
            await update.message.reply_text("⚠️ No data found.")
    else:
        await update.message.reply_text("⚠️ Invalid choice. Please reply with 'Yes' or 'No'.")
        return EXPORT_CONFIRMATION

    return ConversationHandler.END

async def filter_theme(update: Update, context: CallbackContext) -> None:
    """
    Handles the /filtertheme command.
    Usage: /filtertheme <theme>
    It filters the hymns DataFrame by the given theme and replies with the matching hymn numbers and titles.
    """
    if not context.args:
        await update.message.reply_text(
            "⚠️ Please provide a theme.\nExample: /filtertheme Additional Hymns"
        )
        return

    theme_input = " ".join(context.args).strip()
    filtered_df = filter_hymns_by_theme(dfH, theme_input)
    
    if filtered_df.empty:
        await update.message.reply_text(f"No hymns found for theme: '{theme_input}'.")
    else:
        # Build a text message from the filtered results.
        output_lines = []
        for _, row in filtered_df.iterrows():
            output_lines.append(f"Hymn no: {row['Hymn no']} - {row['Hymn Index']}")
        output_text = "\n".join(output_lines)
        await update.message.reply_text(f"Filtered Hymns for theme '{theme_input}':\n{output_text}")



# Fallback in case the user cancels the operation.
async def cancel(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text("Operation canceled.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END




def main():
    """Starts the bot and registers command handlers."""
    app = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("vocabulary", start_vocabulary)],
        states={
            CATEGORY_SELECTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, category_selection)],
            EXPORT_CONFIRMATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, export_confirmation)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    search_index_conv = ConversationHandler(
    entry_points=[CommandHandler("searchindex", search_index_start)],
    states={
        SEARCH_CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_index_category)],
        SEARCH_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_index_number)],
    },
    fallbacks=[CommandHandler("cancel", search_index_cancel)]
)



    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("check", check_song))
    app.add_handler(CommandHandler("last", last_sung))
    app.add_handler(CommandHandler("searchno", search_no))
    app.add_handler(CommandHandler("filtertheme", filter_theme))
    app.add_handler(search_index_conv)
    app.add_handler(conv_handler)
    

    logging.info("🤖 Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()


