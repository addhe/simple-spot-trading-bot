import requests
import os
import logging
from typing import Optional, Dict

from config.settings import TELEGRAM_TOKEN, TELEGRAM_GROUP_ID

logger = logging.getLogger(__name__)

def send_telegram_message(message: str) -> Optional[Dict]:
    """
    Send message to Telegram with HTML formatting support

    Args:
        message: The message to send, can include HTML formatting tags

    Returns:
        Dict with response from Telegram API or None if failed
    """
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            'chat_id': TELEGRAM_GROUP_ID,
            'text': message,
            'parse_mode': 'HTML'  # Enable HTML formatting
        }
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()  # Raise exception for bad status codes
        return response.json()
    except requests.RequestException as e:
        logger.error(f"Failed to send Telegram message: {e}")
        return None
