# src/send_telegram_message.py

import requests

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_GROUP_ID,
        'text': message
    }
    response = requests.post(url, json=payload)
    return response.json()
