# config.py
# Handles secrets/env/config loading for the bot 

import os
import streamlit as st

class Config:
    """
    Centralized configuration loader for secrets and environment variables.
    """
    def __init__(self):
        # Load secrets from Streamlit (or fallback to environment variables)
        self.secrets = st.secrets if hasattr(st, 'secrets') else {}
        self.TOKEN = self.secrets.get("TOKEN") or os.environ.get("TOKEN")
        self.ADMIN_ID = int(self.secrets.get("ADMIN_ID") or os.environ.get("ADMIN_ID", 0))
        self.AUTHORIZED_USERS = [
            int(uid) for uid in (self.secrets.get("AUTHORIZED_USERS") or os.environ.get("AUTHORIZED_USERS", "")).split(',') if uid.strip()
        ]
        # Google Drive/Docs file IDs
        self.HLCFILE_ID = self.secrets.get("HLCFILE_ID")
        self.TFILE_ID = self.secrets.get("TFILE_ID")
        self.FILE_ID = self.secrets.get("FILE_ID")
        self.H_SHEET_MUSIC = self.secrets.get("H_SHEET_MUSIC")
        self.BFILE_ID = self.secrets.get("BFILE_ID")
        self.UFILE_ID = self.secrets.get("UFILE_ID")
        self.YFILE_ID = self.secrets.get("YFILE_ID")
        self.COMFILE_ID = self.secrets.get("COMFILE_ID")
        self.GAME_SCORE = self.secrets.get("GAME_SCORE")
        self.U_DATABASE = self.secrets.get("U_DATABASE")
        # Service account info (for Google APIs)
        self.service_account_data = self._load_service_account_data()
        self.KEY_PATH = "/tmp/service_account.json"
        # Log upload interval (seconds)
        self.LOG_UPLOAD_INTERVAL = int(os.environ.get("LOG_UPLOAD_INTERVAL", 3600))
        # Auto-sync settings
        self.AUTO_SYNC_ENABLED = os.environ.get("AUTO_SYNC_ENABLED", "true").lower() == "true"
        self.AUTO_SYNC_INTERVAL = int(os.environ.get("AUTO_SYNC_INTERVAL", 120))  # seconds

    def _load_service_account_data(self):
        # Reconstruct private key from split lines if needed
        lines = [self.secrets.get(f"l{i}") for i in range(1, 29)]
        private_key = "\n".join([l for l in lines if l])
        return {
            "type": self.secrets.get("type"),
            "project_id": self.secrets.get("project_id"),
            "private_key_id": self.secrets.get("private_key_id"),
            "private_key": private_key,
            "client_email": self.secrets.get("client_email"),
            "client_id": self.secrets.get("client_id"),
            "auth_uri": self.secrets.get("auth_uri"),
            "token_uri": self.secrets.get("token_uri"),
            "auth_provider_x509_cert_url": self.secrets.get("auth_provider_x509_cert_url"),
            "client_x509_cert_url": self.secrets.get("client_x509_cert_url"),
            "universe_domain": self.secrets.get("universe_domain"),
        }

def get_config():
    """Returns a singleton Config instance."""
    if not hasattr(get_config, "_instance"):
        get_config._instance = Config()
    return get_config._instance 