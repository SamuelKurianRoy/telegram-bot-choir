import streamlit as st
from run_bot import start_bot_in_background

if "bot_started" not in st.session_state:
    start_bot_in_background()
    st.session_state["bot_started"] = True

st.title("🎶 Railway Choir Bot")
st.write("The Telegram bot is running in the background.")
