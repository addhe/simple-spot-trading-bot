# src/send_telegram_message.py

import requests
import config.settings as settings
TELEGRAM_TOKEN = settings.TELEGRAM_TOKEN
TELEGRAM_GROUP_ID = settings.TELEGRAM_GROUP_ID

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_GROUP_ID,
        'text': message
    }
    response = requests.post(url, json=payload)
    return response.json()
