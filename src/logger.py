import os
import logging

def setup_logging(self):
    """Configure logging with rotation"""
    log_directory = 'logs/bot'
    if not os.path.exists(log_directory):
        os.makedirs(log_directory)
    self.logger = logging.getLogger('TradingBot')
    self.logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(
        os.path.join(log_directory, 'bot.log'),
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    self.logger.addHandler(handler)