import os
import streamlit as st

# Load secrets from Streamlit

def load_secrets():
    secrets = st.secrets
    # Compose private key from lines if needed
    private_key = "\n".join([secrets[f"l{i}"] for i in range(1, 29)])
    service_account_data = {
        "type": secrets["type"],
        "project_id": secrets["project_id"],
        "private_key_id": secrets["private_key_id"],
        "private_key": private_key,
        "client_email": secrets["client_email"],
        "client_id": secrets["client_id"],
        "auth_uri": secrets["auth_uri"],
        "token_uri": secrets["token_uri"],
        "auth_provider_x509_cert_url": secrets["auth_provider_x509_cert_url"],
        "client_x509_cert_url": secrets["client_x509_cert_url"],
        "universe_domain": secrets["universe_domain"],
    }
    return {
        "service_account_data": service_account_data,
        "HLCFILE_ID": secrets["HLCFILE_ID"],
        "TFILE_ID": secrets["TFILE_ID"],
        "FILE_ID": secrets["FILE_ID"],
        "H_SHEET_MUSIC": secrets["H_SHEET_MUSIC"],
        "TOKEN": secrets["TOKEN"],
        "BFILE_ID": secrets["BFILE_ID"],
        "UFILE_ID": secrets["UFILE_ID"],
        "YFILE_ID": secrets["YFILE_ID"],
        "AUTHORIZED_USERS": secrets["AUTHORIZED_USERS"],
        "ADMIN_ID": secrets["ADMIN_ID"],
        "COMFILE_ID": secrets.get("COMFILE_ID", None),
    }

# Load secrets at import time
SECRETS = load_secrets()

# Expose constants
SERVICE_ACCOUNT_DATA = SECRETS["service_account_data"]
HLCFILE_ID = SECRETS["HLCFILE_ID"]
TFILE_ID = SECRETS["TFILE_ID"]
FILE_ID = SECRETS["FILE_ID"]
H_SHEET_MUSIC = SECRETS["H_SHEET_MUSIC"]
TOKEN = SECRETS["TOKEN"]
BFILE_ID = SECRETS["BFILE_ID"]
UFILE_ID = SECRETS["UFILE_ID"]
YFILE_ID = SECRETS["YFILE_ID"]
AUTHORIZED_USERS = SECRETS["AUTHORIZED_USERS"]
ADMIN_ID = SECRETS["ADMIN_ID"]
COMFILE_ID = SECRETS["COMFILE_ID"]

# Google API scopes
SCOPES = ["https://www.googleapis.com/auth/drive"]
DOC_SCOPES = ["https://www.googleapis.com/auth/documents"]

# Path for temporary service account file
KEY_PATH = "/tmp/service_account.json"

# Write service account data to file
with open(KEY_PATH, "w") as f:
    import json
    json.dump(SERVICE_ACCOUNT_DATA, f)

# Set environment variable for Google credentials
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = KEY_PATH 