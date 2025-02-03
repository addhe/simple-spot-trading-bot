import logging
import os
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceOrderException

from config.settings import API_KEY, API_SECRET, BASE_URL

# Inisialisasi klien Binance
client = Client(api_key=API_KEY, api_secret=API_SECRET, testnet=False)

def get_last_price(symbol):
    try:
        ticker = client.get_symbol_ticker(symbol=symbol)
        return float(ticker['price'])
    except BinanceAPIException as e:
        logging.error(f"Gagal mendapatkan harga terakhir untuk {symbol}: {e}")
        return None
