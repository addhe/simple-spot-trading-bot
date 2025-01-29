import requests
import os

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_GROUP_ID = os.getenv('TELEGRAM_GROUP_ID')

# fungsi untuk mengirimkan pesan ke telegram
def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_GROUP_ID,
        'text': message
    }
    response = requests.post(url, json=payload)
    return response.json()