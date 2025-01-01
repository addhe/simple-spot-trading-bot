import logging
import json

# Konfigurasi logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Baca konfigurasi dari file JSON
with open('config.json', 'r') as config_file:
    config = json.load(config_file)

def calculate_ema(market_data, period):
    """
    Hitung EMA (Exponential Moving Average).

    Parameters:
    market_data (list): Data pasar (cth: OHLCV)
    period (int): Periode EMA

    Returns:
    list: Nilai EMA
    """
    try:
        ema = [market_data[0][4]]
        for i in range(1, len(market_data)):
            ema.append((market_data[i][4] * (2 / (period + 1))) + (ema[i-1] * (1 - (2 / (period + 1)))))
        return ema
    except Exception as e:
        logger.error(f"Error calculating EMA: {str(e)}")
        return None