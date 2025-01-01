import ccxt
import logging
import json
from datetime import datetime
import time

# Konfigurasi logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
# Baca konfigurasi dari file JSON
with open('config.json', 'r') as config_file:
    config = json.load(config_file)

def calculate_ema(market_data, period):
    """Hitung EMA."""
    try:
        ema = []
        for i in range(len(market_data)):
            if i == 0:
                ema.append(market_data[i][4])
            else:
                ema.append((market_data[i][4] * (2 / (period + 1))) + (ema[i-1] * (1 - (2 / (period + 1)))))
        return ema
    except Exception as e:
        logger.error(f"Error calculating EMA: {str(e)}")
        return None