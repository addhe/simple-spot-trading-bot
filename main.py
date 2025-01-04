# main.py
import sys
import os
import time
import logging
from dotenv import load_dotenv
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from src.bot import BotTrading

# Konfigurasi logging
logging.basicConfig(level=logging.INFO, filename='bot.log',
                    format='%(asctime)s - %(levelname)s - %(message)s')

class ReloadHandler(FileSystemEventHandler):
    def __init__(self, bot):
        self.bot = bot

    def on_modified(self, event):
        # Memeriksa apakah file yang diubah adalah salah satu dari yang kita pantau
        if event.src_path.endswith('.py'):
            logging.info(f"File {event.src_path} telah diubah. Memuat ulang bot...")
            self.bot.stop()  # Hentikan bot yang sedang berjalan
            self.bot = BotTrading()  # Buat instance baru dari BotTrading
            self.bot.run()   # Jalankan kembali bot

def main():
    load_dotenv()
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))
    bot = BotTrading()
    observer = Observer()
    event_handler = ReloadHandler(bot)

    # Mulai memantau direktori src
    observer.schedule(event_handler, path='src', recursive=True)
    observer.start()

    try:
        bot.run()  # Jalankan bot trading
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

if __name__ == "__main__":
    main()
