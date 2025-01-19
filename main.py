import sys
import os
import time
import logging
import requests
import asyncio
from dotenv import load_dotenv
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from src.bot import BotTrading

# Konfigurasi logging yang lebih baik untuk produksi
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)

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

async def retry_request(func, retries=3, delay=2, *args, **kwargs):
    """Melakukan retry pada fungsi yang diberikan jika terjadi kesalahan dengan menggunakan async."""
    for attempt in range(retries):
        if check_internet_connection() and check_binance_status():
            try:
                return await func(*args, **kwargs)
            except requests.exceptions.SSLError as ssl_error:
                logging.error(f"SSL Error: {ssl_error}. Coba lagi dalam {delay} detik...")
                await asyncio.sleep(delay)
            except requests.exceptions.ConnectionError as conn_error:
                logging.error(f"Connection Error: {conn_error}. Coba lagi dalam {delay} detik...")
                await asyncio.sleep(delay)
            except Exception as e:
                logging.error(f"Error saat melakukan request: {e}. Coba lagi dalam {delay} detik...")
                await asyncio.sleep(delay)
        else:
            logging.error("Koneksi internet atau API Binance tidak tersedia.")
            await asyncio.sleep(delay)
    raise Exception("Gagal melakukan request setelah beberapa kali percobaan.")

class ReloadHandler(FileSystemEventHandler):
    """Handler untuk memantau perubahan file konfigurasi dan strategi."""
    def __init__(self, bot):
        self.bot = bot
        self.lock = False  # Untuk mencegah reload ganda dalam waktu singkat
        self.last_modified_time = 0

    def on_modified(self, event):
        """Menghandle perubahan file yang dimonitor untuk reload bot."""
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

async def main():
    """Fungsi utama untuk menjalankan bot trading dan monitor file perubahan."""
    load_dotenv()  # Memuat variabel lingkungan dari file .env

    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

    try:
        bot = BotTrading()  # Membuat instance bot baru
        observer = Observer()  # Membuat observer untuk monitor perubahan file
        event_handler = ReloadHandler(bot)  # Membuat handler untuk perubahan file

        # Path absolut untuk keandalan yang lebih baik
        src_path = os.path.abspath('src')
        observer.schedule(event_handler, path=src_path, recursive=False)
        observer.start()  # Mulai observer untuk monitoring perubahan file

        # Menjalankan bot secara asynchronous
        await bot.run()  # Mulai logika trading bot asinkron

    except KeyboardInterrupt:
        logging.info("Mematikan bot dan observer.")
        observer.stop()  # Hentikan observer saat ada interrupt (Ctrl+C)
    except Exception as e:
        logging.error(f"Error saat menjalankan bot: {e}")
    finally:
        observer.join()  # Tunggu observer untuk berhenti dengan baik

if __name__ == "__main__":
    try:
        # Menjalankan aplikasi secara asinkron menggunakan asyncio
        asyncio.run(main())
    except Exception as e:
        logging.critical(f"Terjadi kesalahan fatal saat menjalankan aplikasi: {e}")
