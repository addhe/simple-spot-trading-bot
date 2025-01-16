#src/check_price.py
import logging
from binance.client import Client
import pandas as pd

def check_price(client: Client, symbol: str, latest_activity: dict) -> tuple:
    try:
        data = client.get_symbol_ticker(symbol=symbol)
        current_price = float(data['price'])

        logging.debug(f"Harga saat ini untuk {symbol}: {current_price}, Type: {type(current_price)}")

        buy_price = calculate_dynamic_buy_price(client, symbol)
        sell_price = calculate_dynamic_sell_price(client, symbol)

        logging.debug(f"Harga Beli Dinamis: {buy_price}, Type: {type(buy_price)}")
        logging.debug(f"Harga Jual Dinamis: {sell_price}, Type: {type(sell_price)}")

        if current_price > buy_price:
            logging.info(f"Mempertimbangkan untuk membeli {symbol} pada harga {current_price}")
            return 'BUY', current_price
        elif current_price < sell_price or (latest_activity['buy'] and current_price < latest_activity['price'] * 0.98):
            logging.info(f"Mempertimbangkan untuk menjual {symbol} pada harga {current_price}")
            return 'SELL', current_price
        else:
            logging.info(f"Tidak ada aksi yang diambil untuk {symbol} pada harga {current_price}")
            return 'HOLD', current_price

    except Exception as e:
        logging.error(f"Error saat memeriksa harga untuk {symbol}: {e}")
        return 'HOLD', 0  # Kembalikan 'HOLD' jika terjadi kesalahan

def calculate_dynamic_buy_price(client: Client, symbol: str) -> float:
    historical_data = get_historical_data(client, symbol)
    if historical_data.empty:
        return 10000  # Default jika tidak ada data historis
    prices = historical_data['close'].values
    return prices.mean() * 0.95  # 5% di bawah rata-rata

def calculate_dynamic_sell_price(client: Client, symbol: str) -> float:
    historical_data = get_historical_data(client, symbol)
    if historical_data.empty:
        return 9000  # Default jika tidak ada data historis
    prices = historical_data['close'].values
    return prices.mean() * 1.05  # 5% di atas rata-rata

def get_historical_data(client: Client, symbol: str) -> pd.DataFrame:
    try:
        klines = client.get_historical_klines(
            symbol,
            '1m',  # Interval 1 menit
            '1 day ago UTC'  # Data dari 1 hari ke belakang
        )
        historical_data = pd.DataFrame(
            klines,
            columns=[
                'timestamp', 'open', 'high', 'low', 'close',
                'volume', 'close_time', 'quote_asset_volume',
                'number_of_trades', 'taker_buy_base_asset_volume',
                'taker_buy_quote_asset_volume', 'ignore'
            ]
        )
        historical_data['timestamp'] = pd.to_datetime(historical_data['timestamp'], unit='ms')
        historical_data['close'] = historical_data['close'].astype(float)
        return historical_data
    except Exception as e:
        logging.error(f"Error saat mengambil data historis untuk {symbol}: {e}")
        return pd.DataFrame()  # Kembalikan DataFrame kosong jika terjadi kesalahan
