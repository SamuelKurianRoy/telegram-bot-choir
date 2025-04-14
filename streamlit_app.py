import streamlit as st
import os
import signal
from run_bot import start_bot_in_background

# Start the bot if not already running.
if "bot_started" not in st.session_state:
    start_bot_in_background()
    st.session_state["bot_started"] = True

st.title("🎶 Railway Choir Bot")
st.write("The Telegram bot is running in the background.")

if st.button("Stop Bot"):
    # Sending SIGINT (Ctrl + C) to the current process.
    os.kill(os.getpid(), signal.SIGINT)
