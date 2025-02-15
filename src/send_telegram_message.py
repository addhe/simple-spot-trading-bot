import requests
import os
import logging
from typing import Optional, Dict

from config.settings import TELEGRAM_TOKEN, TELEGRAM_GROUP_ID
from src.logger import logger

def send_telegram_message(message: str,
                          chat_id: str = TELEGRAM_GROUP_ID,
                          parse_mode: str = 'HTML',
                          disable_web_page_preview: bool = False,
                          disable_notification: bool = False,
                          reply_to_message_id: int = None,
                          keyboard: Dict = None) -> Optional[Dict]:
    """
    Send message to Telegram with HTML formatting support.

    Args:
        message: The message to send, can include HTML formatting tags.
        chat_id: Unique identifier for the target chat or username of the target channel.
        parse_mode: Send Markdown or HTML, if you want Telegram apps to show bold, italic, fixed-width text or inline URLs in your bot's message.
        disable_web_page_preview: Disables link previews for links in this message.
        disable_notification: Sends the message silently. Users will receive a notification with no sound.
        reply_to_message_id: If the message is a reply, ID of the original message.
        keyboard: A JSON-serialized object for an inline keyboard.

    Returns:
        Dict with response from Telegram API or None if failed.
    """
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        # Update the message formatting to use Markdown or HTML
        payload = {
            'chat_id': chat_id,
            'text': message,
            'parse_mode': parse_mode,
            'disable_web_page_preview': disable_web_page_preview,
            'disable_notification': disable_notification,
        }
        if reply_to_message_id:
            payload['reply_to_message_id'] = reply_to_message_id
        if keyboard:
            payload['reply_markup'] = keyboard
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()  # Raise exception for bad status codes
        logger.info(f"Sent Telegram message: {message}")
        return response.json()
    except requests.RequestException as e:
        logger.error(f"Failed to send Telegram message: {e}")
        return None
