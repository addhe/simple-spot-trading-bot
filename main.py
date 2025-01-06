# main.py
import sys
import os
import time
import logging
from dotenv import load_dotenv
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class DebounceHandler(FileSystemEventHandler):
    def __init__(self, bot, debounce_time=1.0):
        self.bot = bot
        self.debounce_time = debounce_time
        self.last_modified = {}

    def on_modified(self, event):
        # Memeriksa apakah file yang diubah adalah salah satu dari yang kita pantau
        if event.src_path.endswith('.py'):
            current_time = time.time()
            if event.src_path in self.last_modified:
                if current_time - self.last_modified[event.src_path] < self.debounce_time:
                    return
            self.last_modified[event.src_path] = current_time
            logging.info(f"File {event.src_path} telah diubah. Memuat ulang bot...")
            self.bot.stop()  # Hentikan bot yang sedang berjalan
            self.bot = BotTrading()  # Buat instance baru dari BotTrading
            self.bot.run()   # Jalankan kembali bot

if __name__ == "__main__":
    load_dotenv()
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))
    from bot import BotTrading

    def main():
        bot = BotTrading()
        observer = Observer()
        event_handler = DebounceHandler(bot, debounce_time=2.0)  # Waktu debounce 2 detik

        # Mulai memantau direktori src
        observer.schedule(event_handler, path='src', recursive=True)
        observer.start()

        try:
            bot.run()  # Jalankan bot trading
        except KeyboardInterrupt:
            observer.stop()
        observer.join()

    main()
