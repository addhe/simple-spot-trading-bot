import sys
import os
import time
import logging
from dotenv import load_dotenv
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

if __name__ == "__main__":
    load_dotenv()
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))
    from bot import BotTrading

    class ReloadHandler(FileSystemEventHandler):
        def __init__(self, bot):
            self.bot = bot
            self.lock = False  # To prevent multiple reloads in quick succession

        def on_modified(self, event):
            if self.lock:  # Skip if already reloading
                return
            self.lock = True

            try:
                if event.src_path.endswith(('bot.py', 'strategy.py', 'config.py')):
                    logging.info(f"File {event.src_path} modified. Reloading bot...")
                    self.bot.stop()  # Stop the current bot instance
                    self.bot = BotTrading()  # Create a new bot instance
                    self.bot.run()  # Run the bot again
            except Exception as e:
                logging.error(f"Error during bot reload: {e}")
            finally:
                self.lock = False

    def main():
        bot = BotTrading()
        observer = Observer()
        event_handler = ReloadHandler(bot)

        # Absolute path for better reliability
        src_path = os.path.abspath('src')
        observer.schedule(event_handler, path=src_path, recursive=False)
        observer.start()

        try:
            bot.run()  # Start the bot trading logic
        except KeyboardInterrupt:
            logging.info("Shutting down bot and observer.")
            observer.stop()
        observer.join()

    main()
