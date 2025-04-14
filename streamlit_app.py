import streamlit as st
from run_bot import start_bot_in_background

# Start bot only once per session
if "bot_started" not in st.session_state:
    start_bot_in_background()
    st.session_state["bot_started"] = True

st.title("📢 Railway Choir Bot")
st.write("This Streamlit app is running alongside the Telegram bot.")
