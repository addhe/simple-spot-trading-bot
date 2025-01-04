# main.py
import sys
import os
import logging
from dotenv import load_dotenv
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from src.bot import BotTrading

# Konfigurasi logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class ReloadHandler(FileSystemEventHandler):
    def __init__(self, bot):
        self.bot = bot

    def on_modified(self, event):
        # Memeriksa apakah file yang diubah adalah file Python
        if event.src_path.endswith('.py'):
            logging.info(f"File {event.src_path} telah diubah. Memuat ulang bot...")
            self.bot.stop()  # Hentikan bot yang sedang berjalan
            self.bot.run()   # Jalankan kembali bot

def main():
    load_dotenv()  # Memuat variabel lingkungan dari file .env
    bot = BotTrading()  # Inisialisasi bot trading
    observer = Observer()
    event_handler = ReloadHandler(bot)

    # Mulai memantau direktori src
    observer.schedule(event_handler, path='src', recursive=True)  # Menggunakan recursive=True untuk memantau subdirektori
    observer.start()

    try:
        logging.info("Bot trading dimulai...")
        bot.run()  # Jalankan bot trading
    except KeyboardInterrupt:
        logging.info("Menghentikan bot trading...")
        observer.stop()
    except Exception as e:
        logging.error(f"Terjadi kesalahan: {e}")
    finally:
        observer.stop()
        observer.join()

if __name__ == "__main__":
    main()
