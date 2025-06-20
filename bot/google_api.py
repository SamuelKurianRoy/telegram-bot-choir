from googleapiclient.discovery import build
from google.oauth2 import service_account
from bot.config import KEY_PATH, SCOPES, DOC_SCOPES


def get_drive_service():
    """
    Returns an authenticated Google Drive service client.
    """
    creds = service_account.Credentials.from_service_account_file(KEY_PATH, scopes=SCOPES)
    return build("drive", "v3", credentials=creds)


def get_docs_service():
    """
    Returns an authenticated Google Docs service client.
    """
    creds = service_account.Credentials.from_service_account_file(KEY_PATH, scopes=DOC_SCOPES)
    return build("docs", "v1", credentials=creds) 