import subprocess
import streamlit as st

st.set_page_config(page_title="Telegram Bot Controller", page_icon="🤖")
st.title("🎛️ Telegram Bot Controller")

if st.button("Start Bot"):
    subprocess.Popen(["python", "run_bot.py"])
    st.success("✅ Bot started successfully!")

st.info("Click the button to start your Telegram bot in the background.")
