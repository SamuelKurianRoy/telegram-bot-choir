# telegram/utils.py
# Telegram-specific helpers

def send_long_message(update, message_parts, parse_mode="Markdown", max_length=3500):
    """
    Sends a message, splitting it into multiple messages if it's too long.
    """
    # TODO: Implement message chunking logic
    pass

# TODO: Add more Telegram-specific helpers as needed 