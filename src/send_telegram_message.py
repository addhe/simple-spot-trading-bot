import requests
import os
import logging
from typing import Optional, Dict

from config.settings import TELEGRAM_TOKEN, TELEGRAM_GROUP_ID

logger = logging.getLogger(__name__)

def send_telegram_message(message: str, symbol: str = '', action: str = '', price: float = None) -> Optional[Dict]:
    """
    Send message to Telegram with HTML formatting support.

    Args:
        message: The message to send, can include HTML formatting tags.
        symbol: The trading symbol involved in the message.
        action: The action taken ('buy' or 'sell').
        price: The price at which the action was taken.

    Returns:
        Dict with response from Telegram API or None if failed.
    """
    try:
        # Create a detailed message
        detailed_message = f"<b>{action.capitalize()} Notification for {symbol}</b>\n"
        detailed_message += f"Price: {price}\n"
        detailed_message += f"Message: {message}"

        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            'chat_id': TELEGRAM_GROUP_ID,
            'text': detailed_message,
            'parse_mode': 'HTML'  # Enable HTML formatting
        }
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()  # Raise exception for bad status codes
        logger.info(f"Sent Telegram message: {detailed_message}")
        return response.json()
    except requests.RequestException as e:
        logger.error(f"Failed to send Telegram message: {e}")
        return None
