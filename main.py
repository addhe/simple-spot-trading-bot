import os
import time
import logging
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from src.bot import BotTrading

class ReloadHandler(FileSystemEventHandler):
    def __init__(self, bot):
        self.bot = bot

    def on_modified(self, event):
        if event.src_path.endswith('.py'):
            logging.info(f"File {event.src_path} telah diubah. Memuat ulang bot...")
            self.bot.stop()  # Hentikan bot
            self.bot.run()   # Jalankan kembali bot

def main():
    logging.basicConfig(level=logging.DEBUG, filename='bot.log',
                        format='%(asctime)s - %(levelname)s - %(message)s')

    bot = BotTrading()  # Inisialisasi bot
    observer = Observer()
    observer.schedule(ReloadHandler(bot), path='src', recursive=True)  # Ganti dengan path yang sesuai
    observer.start()

    try:
        bot.run()  # Jalankan bot
    except KeyboardInterrupt:
        bot.stop()
    finally:
        observer.stop()
        observer.join()

if __name__ == "__main__":
    main()
