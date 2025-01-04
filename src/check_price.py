# src/check_price.py
import logging
from binance.client import Client
import pandas as pd
from strategy import PriceActionStrategy

def check_price(client: Client, symbol: str, latest_activity: dict) -> tuple:
    try:
        data = client.get_symbol_ticker(symbol=symbol)
        current_price = float(data['price'])

        logging.debug(f"Harga saat ini untuk {symbol}: {current_price}, Type: {type(current_price)}")

        strategy = PriceActionStrategy(symbol)
        buy_price = strategy.calculate_dynamic_buy_price()
        sell_price = strategy.calculate_dynamic_sell_price()

        logging.debug(f"Harga Beli Dinamis: {buy_price}, Type: {type(buy_price)}")
        logging.debug(f"Harga Jual Dinamis: {sell_price}, Type: {type(sell_price)}")

        if current_price > buy_price:
            logging.info(f"Mempertimbangkan untuk membeli {symbol} pada harga {current_price}")
            return 'BUY', current_price
        elif current_price < sell_price or (latest_activity['buy'] and current_price < latest_activity['stop_loss']):
            logging.info(f"Mempertimbangkan untuk menjual {symbol} pada harga {current_price}")
            return 'SELL', current_price
        else:
            logging.info(f"Tidak ada aksi yang diambil untuk {symbol} pada harga {current_price}")
            return 'HOLD', current_price

    except Exception as e:
        logging.error(f"Error saat memeriksa harga untuk {symbol}: {e}")
        return 'HOLD', 0  # Kembalikan 'HOLD' jika terjadi kesalahan
