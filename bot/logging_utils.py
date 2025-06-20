import logging
import sys
import os
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2 import service_account

from bot.config import KEY_PATH, DOC_SCOPES

# --- Logger Setup Functions ---
def setup_bot_logger():
    """
    Sets up and returns the bot logger.
    """
    bot_logger = logging.getLogger("telegram_bot")
    if not bot_logger.handlers:
        bot_logger.setLevel(logging.INFO)

        # Console handler (safe & simple)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(logging.Formatter('%(message)s'))
        bot_logger.addHandler(console_handler)

        # File handler for bot logs with UTF-8 (emoji support) - overwrite each time
        file_handler = logging.FileHandler("bot_log.txt", mode='w', encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
        bot_logger.addHandler(file_handler)
    return bot_logger

def setup_user_logger():
    """
    Sets up and returns the user logger.
    """
    user_logger = logging.getLogger("user_logger")
    if not user_logger.handlers:
        user_logger.setLevel(logging.INFO)
        user_logger.propagate = False

        # Use default append mode to keep all user interactions across bot restarts
        user_handler = logging.FileHandler("user_log.txt", encoding='utf-8')
        user_handler.setFormatter(logging.Formatter("%(asctime)s - %(message)s"))
        user_logger.addHandler(user_handler)
    return user_logger

# --- Google Docs Log Upload Functions ---
def get_docs_service():
    """
    Returns an authenticated Google Docs service client.
    """
    creds = service_account.Credentials.from_service_account_file(KEY_PATH, scopes=DOC_SCOPES)
    return build("docs", "v1", credentials=creds)

def upload_log_to_google_doc(doc_id: str, log_file: str):
    """
    Uploads a local log file's contents to a Google Docs file.
    Clears the existing content and appends the new content.
    """
    logger = logging.getLogger("telegram_bot")
    docs_service = get_docs_service()
    if not os.path.exists(log_file):
        logger.warning(f"⚠️ Log file {log_file} does not exist.")
        return

    with open(log_file, "r", encoding="utf-8") as file:
        content = file.read().strip()

    if not content:
        logger.info(f"ℹ️ Log file {log_file} is empty. Skipping upload.")
        return

    try:
        # Step 1: Get the document content to find its current length
        doc = docs_service.documents().get(documentId=doc_id).execute()
        end_index = doc.get('body', {}).get('content', [{}])[-1].get('endIndex', 1)

        # Step 2: Clear the document (if it has any content)
        requests = []
        if end_index > 1:
            requests.append({
                'deleteContentRange': {
                    'range': {
                        'startIndex': 1,
                        'endIndex': end_index - 1
                    }
                }
            })

        # Step 3: Insert new content
        requests.append({
            'insertText': {
                'location': {
                    'index': 1
                },
                'text': content
            }
        })

        # Step 4: Execute batch update
        docs_service.documents().batchUpdate(
            documentId=doc_id,
            body={'requests': requests}
        ).execute()

        logger.info(f"✅ Successfully uploaded {log_file} to Google Doc ({doc_id})")
        print("log Files Loaded")

    except HttpError as e:
        logger.error(f"❌ Failed to log due to: {e}")

def append_download_to_google_doc(yfile_id: str, download_entry: str):
    """
    Appends a download entry directly to a Google Docs file.
    Similar to how comments are handled.
    """
    docs_service = get_docs_service()
    try:
        doc = docs_service.documents().get(documentId=yfile_id).execute()
        end_index = doc.get("body").get("content")[-1].get("endIndex", 1)

        requests = [{
            "insertText": {
                "location": {"index": end_index - 1},
                "text": download_entry
            }
        }]

        docs_service.documents().batchUpdate(
            documentId=yfile_id,
            body={"requests": requests}
        ).execute()

        print("✅ Download entry appended to Google Doc.")
    except Exception as e:
        logging.error(f"❌ Failed to append download entry to Google Doc ({yfile_id}): {e}") 