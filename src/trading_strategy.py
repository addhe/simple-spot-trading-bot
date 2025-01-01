import ccxt
import logging
import json
from datetime import datetime
import time

import src.fetch_market_data as fetch_market_data
import src.calculate_ema as calculate_ema

# Konfigurasi logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load konfigurasi dari file config.json
with open('config.json') as f:
    config = json.load(f)

def trading_strategy(market_data):
    """Implementasi strategi trading."""
    try:
        ema_short = calculate_ema(market_data, config['EMA_SHORT_PERIOD'])
        ema_long = calculate_ema(market_data, config['EMA_LONG_PERIOD'])
        
        if ema_short[-1] > ema_long[-1]:
            return 'buy'
        elif ema_short[-1] < ema_long[-1]:
            return 'sell'
        else:
            return 'neutral'
    except Exception as e:
        logger.error(f"Error executing trading strategy: {str(e)}")
        return None