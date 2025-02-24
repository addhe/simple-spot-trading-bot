# src/send_telegram_message.py

import requests
import config.settings as settings
TELEGRAM_TOKEN = settings.TELEGRAM_TOKEN
TELEGRAM_GROUP_ID = settings.TELEGRAM_GROUP_ID

def send_telegram_message(message, token, chat_id):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': message
    }
    response = requests.post(url, data=payload)
    return response.json()
