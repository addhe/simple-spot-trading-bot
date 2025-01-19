import sys
import os
import time
import logging
import requests
from dotenv import load_dotenv
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from src.bot import BotTrading

# Konfigurasi logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def check_internet_connection(url='http://www.google.com', timeout=5):
    """Memeriksa koneksi internet dengan mencoba mengakses URL tertentu."""
    try:
        requests.get(url, timeout=timeout)
        return True
    except requests.ConnectionError:
        logging.error("Tidak ada koneksi internet.")
        return False

def check_binance_status():
    """Memeriksa status API Binance."""
    try:
        response = requests.get('https://api.binance.com/api/v3/ping', timeout=5)
        if response.status_code == 200:
            logging.info("API Binance dalam keadaan baik.")
            return True
        else:
            logging.warning("API Binance tidak responsif.")
            return False
    except requests.RequestException as e:
        logging.error(f"Error saat memeriksa status API Binance: {e}")
        return False

def retry_request(func, retries=3, delay=2, *args, **kwargs):
    """Melakukan retry pada fungsi yang diberikan jika terjadi kesalahan."""
    for attempt in range(retries):
        if check_internet_connection() and check_binance_status():
            try:
                return func(*args, **kwargs)
            except requests.exceptions.SSLError as ssl_error:
                logging.error(f"SSL Error: {ssl_error}. Coba lagi dalam {delay} detik...")
                time.sleep(delay)
            except requests.exceptions.ConnectionError as conn_error:
                logging.error(f"Connection Error: {conn_error}. Coba lagi dalam {delay} detik...")
                time.sleep(delay)
            except Exception as e:
                logging.error(f"Error saat melakukan request: {e}. Coba lagi dalam {delay} detik...")
                time.sleep(delay)
        else:
            logging.error("Koneksi internet atau API Binance tidak tersedia.")
            time.sleep(delay)
    raise Exception("Gagal melakukan request setelah beberapa kali percobaan.")

class ReloadHandler(FileSystemEventHandler):
    def __init__(self, bot):
        self.bot = bot
        self.lock = False  # Untuk mencegah reload ganda dalam waktu singkat
        self.last_modified_time = 0

    def on_modified(self, event):
        current_time = time.time()
        if self.lock or (current_time - self.last_modified_time < 2):  # Debounce 2 detik
            return

        self.lock = True
        self.last_modified_time = current_time

        try:
            if event.src_path.endswith(('bot.py', 'strategy.py', 'config.py')):
                logging.info(f"File {event.src_path} dimodifikasi. Memuat ulang bot...")
                self.bot.stop()  # Hentikan instance bot saat ini
                self.bot = BotTrading()  # Buat instance bot baru
                self.bot.run()  # Jalankan bot lagi
        except Exception as e:
            logging.error(f"Error saat memuat ulang bot: {e}")
        finally:
            self.lock = False

def main():
    load_dotenv()
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

    try:
        bot = BotTrading()
        observer = Observer()
        event_handler = ReloadHandler(bot)

        # Path absolut untuk keandalan yang lebih baik
        src_path = os.path.abspath('src')
        observer.schedule(event_handler, path=src_path, recursive=False)
        observer.start()

        bot.run()  # Mulai logika trading bot

    except KeyboardInterrupt:
        logging.info("Mematikan bot dan observer.")
        observer.stop()
    except Exception as e:
        logging.error(f"Error saat menjalankan bot: {e}")
    finally:
        observer.join()

if __name__ == "__main__":
    main()
