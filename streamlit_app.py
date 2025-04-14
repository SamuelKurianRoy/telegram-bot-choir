import streamlit as st
import os
import signal
from run_bot import start_bot_in_background

st.title("🎶 Railway Choir Bot")

# Initialize session state variable
if "bot_started" not in st.session_state:
    st.session_state["bot_started"] = False

# Start Bot button
if st.button("Start Bot") and not st.session_state["bot_started"]:
    start_bot_in_background()
    st.session_state["bot_started"] = True
    st.success("Bot started!")

# Stop Bot button
if st.button("Stop Bot") and st.session_state["bot_started"]:
    os.kill(os.getpid(), signal.SIGINT)
    st.session_state["bot_started"] = False
    st.warning("Bot stopped!")

# Show status
if st.session_state["bot_started"]:
    st.write("✅ The Telegram bot is running in the background.")
else:
    st.write("❌ The Telegram bot is not running.")
