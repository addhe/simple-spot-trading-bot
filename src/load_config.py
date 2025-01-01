import json
import logging
import os

logger = logging.getLogger(__name__)

def load_config():
    try:
        with open('config.json') as f:
            config = json.load(f)
            config['TRADE_INTERVAL'] = config.get('TRADE_INTERVAL', 60)
            return config
    except FileNotFoundError:
        logger.error("File config.json tidak ditemukan")
        exit(1)

def validate_config(config):
    required_keys = ['SYMBOL', 'TIMEFRAME', 'EMA_SHORT_PERIOD', 'EMA_LONG_PERIOD']
    if not all(key in config for key in required_keys):
        logger.error("Konfigurasi tidak valid")
        exit(1)
    
    # Load API Key and Secret from Environment Variables
    config['API_KEY_BINANCE'] = os.environ.get('API_KEY_BINANCE')
    config['API_SECRET_BINANCE'] = os.environ.get('API_SECRET_BINANCE')
    
    if not config['API_KEY_BINANCE'] or not config['API_SECRET_BINANCE']:
        logger.error("API Key atau Secret tidak ditemukan di variabel lingkungan")
        exit(1)
    
    return config