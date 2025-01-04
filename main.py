#main.py
import sys
import os
from dotenv import load_dotenv

if __name__ == "__main__":
    load_dotenv()
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))
    from bot import BotTrading

    bot = BotTrading()
    bot.run()
