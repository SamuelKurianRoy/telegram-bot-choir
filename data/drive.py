# data/drive.py
# Google Drive/Docs API functions 

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2 import service_account
import json
import os
from config import get_config

# Google Drive/Docs API setup and helpers

def get_drive_service():
    """
    Returns an authenticated Google Drive service instance.
    """
    config = get_config()
    # Save service account data to a temp file if not already present
    if not os.path.exists(config.KEY_PATH):
        with open(config.KEY_PATH, "w") as f:
            json.dump(config.service_account_data, f)
    creds = service_account.Credentials.from_service_account_file(
        config.KEY_PATH, scopes=["https://www.googleapis.com/auth/drive"]
    )
    return build("drive", "v3", credentials=creds)

def get_docs_service():
    """
    Returns an authenticated Google Docs service instance.
    """
    config = get_config()
    if not os.path.exists(config.KEY_PATH):
        with open(config.KEY_PATH, "w") as f:
            json.dump(config.service_account_data, f)
    creds = service_account.Credentials.from_service_account_file(
        config.KEY_PATH, scopes=["https://www.googleapis.com/auth/documents"]
    )
    return build("docs", "v1", credentials=creds)

def upload_log_to_google_doc(doc_id: str, log_file: str):
    """
    Uploads a local log file's contents to a Google Docs file.
    Clears the existing content and appends the new content.
    """
    docs_service = get_docs_service()
    if not os.path.exists(log_file):
        print(f"⚠️ Log file {log_file} does not exist.")
        return
    with open(log_file, "r", encoding="utf-8") as file:
        content = file.read().strip()
    if not content:
        print(f"ℹ️ Log file {log_file} is empty. Skipping upload.")
        return
    try:
        doc = docs_service.documents().get(documentId=doc_id).execute()
        end_index = doc.get('body', {}).get('content', [{}])[-1].get('endIndex', 1)
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
        requests.append({
            'insertText': {
                'location': {'index': 1},
                'text': content
            }
        })
        docs_service.documents().batchUpdate(
            documentId=doc_id,
            body={'requests': requests}
        ).execute()
        print(f"✅ Successfully uploaded {log_file} to Google Doc ({doc_id})")
    except HttpError as e:
        print(f"❌ Failed to log due to: {e}")

def append_download_to_google_doc(yfile_id: str, download_entry: str):
    """
    Appends a download entry directly to a Google Docs file.
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
        print(f"❌ Failed to append download entry to Google Doc ({yfile_id}): {e}")

# TODO: Add file download/upload helpers as needed for your bot 