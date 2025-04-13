import streamlit as st

st.title("Telegram Bot Controller")

if st.button("Start Bot"):
    st.write("Attempting to start the bot...")

    try:
        # Check imports explicitly to fail early
        from bot import run_bot

        # Wrap actual bot run in a try-except
        try:
            run_bot()
            st.success("Bot started successfully!")
        except Exception as bot_error:
            st.error(f"Bot failed to run: {bot_error}")

    except ModuleNotFoundError as import_error:
        st.error(f"Dependency missing: {import_error}")
    except Exception as e:
        st.error(f"Unexpected error: {e}")
