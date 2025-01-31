import logging
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceOrderException

def get_last_price(symbol):
    try:
        ticker = client.get_symbol_ticker(symbol=symbol)
        return float(ticker['price'])
    except BinanceAPIException as e:
        logging.error(f"Gagal mendapatkan harga terakhir untuk {symbol}: {e}")
        return None
