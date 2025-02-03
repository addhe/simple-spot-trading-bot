# src/logger.py
import os
import logging
from logging.handlers import RotatingFileHandler

def setup_logging():
    log_directory = 'logs/bot'
    if not os.path.exists(log_directory):
        os.makedirs(log_directory)

    logger = logging.getLogger('TradingBot')
    logger.setLevel(logging.INFO)

    # Cek apakah sudah ada handler yang ditambahkan
    if not logger.handlers:
        handler = RotatingFileHandler(
            os.path.join(log_directory, 'bot.log'),
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5
        )
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger
