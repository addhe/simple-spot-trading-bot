import os
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceOrderException

from config.settings import API_KEY, API_SECRET, BASE_URL
from src.logger import logger

# Inisialisasi klien Binance
client = Client(api_key=API_KEY, api_secret=API_SECRET)
if BASE_URL:
    client.API_URL = BASE_URL

def get_last_price(symbol):
    try:
        ticker = client.get_symbol_ticker(symbol=symbol)
        return float(ticker['price'])
    except BinanceAPIException as e:
        logger.error(f"Gagal mendapatkan harga terakhir untuk {symbol}: {e}")
        return None
