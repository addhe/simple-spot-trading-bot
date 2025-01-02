import requests
import os
from load_config import load_config, validate_config

def send_message_telegram(message):
    """
    Mengirimkan notifikasi ke Telegram jika order buy atau order sell terjadi.
    
    Args:
        message (str): Pesan yang akan dikirimkan ke Telegram.
    """
    config = load_config()
    config = validate_config(config)
    
    token = os.environ.get('TELEGRAM_BOT_TOKEN')  # Ambil token dari environment variable
    chat_id = config.get('TELEGRAM_CHAT_ID')  # Ambil chat_id dari config
    
    if not token or not chat_id:
        print("Konfigurasi Telegram tidak lengkap")
        return
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    params = {
        "chat_id": chat_id,
        "text": message
    }
    
    try:
        response = requests.post(url, params=params)
        response.raise_for_status()  # Menghasilkan kesalahan jika status code tidak 200
        print("Notifikasi Telegram berhasil dikirimkan!")
    except requests.exceptions.HTTPError as errh:
        print(f"Gagal mengirimkan notifikasi Telegram: {errh}")
    except requests.exceptions.ConnectionError as errc:
        print(f"Gagal mengirimkan notifikasi Telegram: {errc}")
    except requests.exceptions.Timeout as errt:
        print(f"Gagal mengirimkan notifikasi Telegram: {errt}")
    except requests.exceptions.RequestException as err:
        print(f"Gagal mengirimkan notifikasi Telegram: {err}")