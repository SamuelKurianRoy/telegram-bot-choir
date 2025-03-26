# Load JSON key from Railway environment variables
import os
import json
import tempfile

# Load JSON key from environment variables
KEY_JSON = os.getenv("KEY_JSON")  # This contains the entire JSON file content

if KEY_JSON:
    # Save JSON key to a temporary file
    with tempfile.NamedTemporaryFile(delete=False, mode="w", suffix=".json") as temp_key_file:
        temp_key_file.write(KEY_JSON)
        KEY_PATH = temp_key_file.name  # This is the new path to the JSON key

    print(f"Temporary JSON key saved at: {KEY_PATH}")  # Debugging
else:
    print("ERROR: KEY_JSON environment variable not found!")



import logging
from telegram import Update
from telegram.ext import Application, CommandHandler,ConversationHandler, MessageHandler, filters, CallbackContext
import pandas as pd
from google.oauth2 import service_account
from googleapiclient.discovery import build
import io
from googleapiclient.http import MediaIoBaseDownload
import numpy as np
from telegram import Update, ReplyKeyboardMarkup
import logging
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove

# Enable logging
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)

# Step 1: Authenticate and build the drive service
creds = service_account.Credentials.from_service_account_file(KEY_PATH, scopes=SCOPES)
drive_service = build("drive", "v3", credentials=creds)

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
    xls = pd.ExcelFile(file_data)  # Read the file into an ExcelFile object
    print("Excel file loaded successfully.")
except Exception as e:
    print(f"Failed to load Excel file: {e}")

# Step 4: Try to read specific sheets and handle errors
yr23 = None
yr24 = None
yr25 = None
df = None

# Attempt to load '2023' sheet
try:
    yr23 = pd.read_excel(xls, sheet_name="2023")
    print("Successfully loaded the '2023' sheet.")
except ValueError:
    print("Sheet '2023' not found.")

# Attempt to load '2024' sheet
try:
    yr24 = pd.read_excel(xls, sheet_name="2024")
    print("Successfully loaded the '2024' sheet.")
except ValueError:
    print("Sheet '2024' not found.")

# Attempt to load '2025' sheet
try:
    yr25 = pd.read_excel(xls, sheet_name="2025")
    print("Successfully loaded the '2025' sheet.")
except ValueError:
    print("Sheet '2025' not found.")

# Attempt to load 'Sheet 1' sheet
try:
    df = pd.read_excel(xls, sheet_name="Sheet 1")
    print("Successfully loaded the 'Sheet 1' sheet.")
except ValueError:
    print("Sheet 'Sheet 1' not found.")


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
    vocabulary = pd.DataFrame({'Hymn no': unique_sorted_hymn, 'Lyric no': lyric_unique_sorted, 'Convention no': convention_unique_sorted})

    # Display the vocabulary DataFrame
    vocabulary= vocabulary.fillna(0).astype(int)
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


def isVocabulary(Song):
  Found= False
  song=Song.strip()
  if (Song.startswith("H")):
    Song=song.replace('H','')
    song=Song.strip()
    Song=song.replace("-",'')
    song= Song.strip()
    song=int(song)
    for i in Vocabulary['Hymn no']:
      if i == song:
        Found = True
        break
      else:
        pass

  elif (Song.startswith("L")):
    Song=song.replace('L','')
    song=Song.strip()
    Song=song.replace("-",'')
    song= Song.strip()
    song=int(song)
    for i in Vocabulary['Lyric no']:
      if i== 0:
        break
      elif i== song:
        Found = True
        break
      else: pass

  elif (Song.startswith("C")):
    Song=song.replace('C','')
    song=Song.strip()
    Song=song.replace("-",'')
    song= Song.strip()
    song=int(song)
    for i in Vocabulary['Convention no']:
      if i== 0:
        break
      elif i== song:
        Found = True

        break
      else: pass
  else:
    print("Invalid Response")
  if Found == True:
    return "The Song is in the choir Vocabulory"
  else:
    return "The Song not found in the choir vocabulory"

def Datefinder(song):
  song=song.strip()
  Found = False
  for i in range (len(df)-1,-1,-1):
    if song in df.iloc[i].tolist():
      Found = True
      song = df['Date'].iloc[i]
      formatted_date = song.strftime("%d/%m/%Y")
      break


  if Found == True:
    return f"The song was last sang on: {formatted_date}"
  else:
    return "Song Not Sang in the past years since 2022"
  



#Telegram bot

async def start(update: Update, context: CallbackContext) -> None:
    """Handles the /start command."""
    welcome_text = (
        "🎵 *Welcome to the Choir Song Bot!*\n\n"
        "Use `/check <song>` to check if a song is in the vocabulary.\n"
        "Use `/last <song>` to find when it was last sung.\n"
        "_Example:_ `/check H-27` or `/last H-27`"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

async def check_song(update: Update, context: CallbackContext) -> None:
    """Handles the /check command to verify if a song is in the vocabulary."""
    if not context.args:
        await update.message.reply_text("⚠️ Please provide a song number.\n_Example:_ `/check H-27`", parse_mode="Markdown")
        return
    song = context.args[0]
    result = isVocabulary(song)
    await update.message.reply_text(result)

async def last_sung(update: Update, context: CallbackContext) -> None:
    """Handles the /last command to check when a song was last sung."""
    if not context.args:
        await update.message.reply_text("⚠️ Please provide a song number.\n_Example:_ `/last H-27`", parse_mode="Markdown")
        return
    song = context.args[0]
    result = Datefinder(song)
    await update.message.reply_text(result)
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

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("check", check_song))
    app.add_handler(CommandHandler("last", last_sung))
    app.add_handler(conv_handler)
    

    logging.info("🤖 Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()

