# src/logger.py
import os
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime

def setup_logging():
    """Setup logging with file rotation"""
    log_directory = 'logs/bot'
    if not os.path.exists(log_directory):
        os.makedirs(log_directory)

    # Base logger configuration
    logger = logging.getLogger('TradingBot')
    logger.setLevel(logging.INFO)

    # Clear existing handlers
    logger.handlers = []

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)

    # File handler for all logs with size-based rotation
    file_handler = RotatingFileHandler(
        os.path.join(log_directory, 'bot.log'),
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    file_handler.setLevel(logging.INFO)
    file_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(file_format)
    logger.addHandler(file_handler)

    # File handler for error logs with size-based rotation
    error_handler = RotatingFileHandler(
        os.path.join(log_directory, 'error.log'),
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    error_handler.setLevel(logging.ERROR)
    error_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s\n%(pathname)s:%(lineno)d\n%(exc_info)s')
    error_handler.setFormatter(error_format)
    logger.addHandler(error_handler)

    return logger

# Initialize the logger
logger = setup_logging()
