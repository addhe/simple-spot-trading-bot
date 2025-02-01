import logging
import os
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceOrderException

API_KEY = os.getenv('API_KEY_SPOT_TESTNET_BINANCE', '')
API_SECRET = os.getenv('API_SECRET_SPOT_TESTNET_BINANCE', '')
BASE_URL = 'https://testnet.binance.vision/api'

# Inisialisasi klien Binance
client = Client(api_key=API_KEY, api_secret=API_SECRET, testnet=True)

def get_symbol_step_size(symbol):
    try:
        info = client.get_symbol_info(symbol)
        for f in info['filters']:
            if f['filterType'] == 'LOT_SIZE':
                return float(f['stepSize'])
    except BinanceAPIException as e:
        logging.error(f"Gagal mendapatkan stepSize untuk {symbol}: {e}")
    return None