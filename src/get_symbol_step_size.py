import logging
import os
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceOrderException

from config.settings import API_KEY, API_SECRET, BASE_URL

# Inisialisasi klien Binance
client = Client(api_key=API_KEY, api_secret=API_SECRET, testnet=False)

def get_symbol_step_size(symbol):
    try:
        info = client.get_symbol_info(symbol)
        for f in info['filters']:
            if f['filterType'] == 'LOT_SIZE':
                return float(f['stepSize'])
    except BinanceAPIException as e:
        logging.error(f"Gagal mendapatkan stepSize untuk {symbol}: {e}")
    return None