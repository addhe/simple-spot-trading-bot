# src/check_price.py
import logging
import os
import pandas as pd
import time
from binance.client import Client
from binance.exceptions import BinanceAPIException
import random
import datetime

# Konfigurasi logging
logging.basicConfig(
    format='%(asctime)s [%(levelname)s] %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S'
)

class CryptoPriceChecker:
    BUY_MULTIPLIER = 0.95
    SELL_MULTIPLIER = 1.05
    DATA_DIR = "historical_data"
    CACHE_LIFETIME = 60  # Cache selama 60 detik untuk pengambilan data baru
    MAX_RETRIES = 5
    RETRY_BACKOFF = 2  # Waktu backoff eksponensial (detik)

    def __init__(self, client: Client):
        self.client = client
        os.makedirs(self.DATA_DIR, exist_ok=True)  # Pastikan direktori data ada
        self.cached_data = {}

    def _get_offline_data_path(self, symbol: str) -> str:
        return os.path.join(self.DATA_DIR, f"{symbol}_historical.csv")

    def _load_offline_data(self, symbol: str) -> pd.DataFrame:
        path = self._get_offline_data_path(symbol)
        if os.path.exists(path):
            logging.info(f"Memuat data historis offline untuk {symbol} dari {path}...")
            return pd.read_csv(path, parse_dates=['timestamp'])
        else:
            logging.warning(f"Tidak ditemukan data historis offline untuk {symbol} di {path}.")
            return pd.DataFrame()

    def _save_offline_data(self, symbol: str, data: pd.DataFrame):
        path = self._get_offline_data_path(symbol)
        logging.info(f"Menyimpan data historis offline untuk {symbol} ke {path}...")
        data.to_csv(path, index=False)

    def _retry_api_call(self, func, *args, **kwargs):
        retries = 0
        while retries < self.MAX_RETRIES:
            try:
                return func(*args, **kwargs)
            except BinanceAPIException as e:
                retries += 1
                logging.error(f"API Error {e}, Retrying {retries}/{self.MAX_RETRIES}...")
                time.sleep(self.RETRY_BACKOFF * (2 ** retries))  # Exponential backoff
            except Exception as e:
                logging.error(f"Unexpected error: {e}")
                break
        return None

    def get_historical_data(self, symbol: str, interval: str = '1m', start_time: str = '1 day ago UTC') -> pd.DataFrame:
        # Cek apakah data historis sudah tersedia dalam cache
        if symbol in self.cached_data and time.time() - self.cached_data[symbol]['timestamp'] < self.CACHE_LIFETIME:
            logging.info(f"Data historis untuk {symbol} diambil dari cache.")
            return self.cached_data[symbol]['data']

        offline_data = self._load_offline_data(symbol)
        try:
            logging.info(f"Mengambil data historis untuk {symbol} dari API...")
            klines = self._retry_api_call(self.client.get_historical_klines, symbol, interval, start_time)

            if klines is None:
                return offline_data

            new_data = pd.DataFrame(
                klines,
                columns=[
                    'timestamp', 'open', 'high', 'low', 'close',
                    'volume', 'close_time', 'quote_asset_volume',
                    'number_of_trades', 'taker_buy_base_asset_volume',
                    'taker_buy_quote_asset_volume', 'ignore'
                ]
            )
            new_data['timestamp'] = pd.to_datetime(new_data['timestamp'], unit='ms')
            new_data['close'] = new_data['close'].astype(float)

            # Gabungkan data baru dengan data offline jika ada
            if not offline_data.empty:
                last_timestamp = offline_data['timestamp'].max() if not offline_data.empty else None
                new_data_timestamp = new_data['timestamp'].max() if not new_data.empty else None

                if last_timestamp is None or new_data_timestamp > last_timestamp:
                    combined_data = pd.concat([offline_data, new_data]).drop_duplicates(subset='timestamp').sort_values(by='timestamp')
                    self._save_offline_data(symbol, combined_data)
                    self.cached_data[symbol] = {'data': combined_data, 'timestamp': time.time()}
                    logging.info(f"Data historis untuk {symbol} berhasil diperbarui.")
                    return combined_data
                else:
                    logging.info(f"Tidak ada data baru untuk {symbol}. Data historis tetap menggunakan yang lama.")
                    return offline_data
            else:
                self._save_offline_data(symbol, new_data)
                self.cached_data[symbol] = {'data': new_data, 'timestamp': time.time()}
                logging.info(f"Data historis untuk {symbol} berhasil diperbarui.")
                return new_data
        except Exception as e:
            logging.error(f"Error saat mengambil data historis untuk {symbol}: {e}")
            return offline_data if not offline_data.empty else pd.DataFrame()

    def calculate_dynamic_price(self, symbol: str, multiplier: float) -> float:
        try:
            logging.info(f"Menghitung harga dinamis untuk {symbol}...")
            historical_data = self.get_historical_data(symbol)
            if historical_data.empty:
                logging.warning(f"Tidak ada data historis untuk {symbol}. Menggunakan harga 0.")
                return 0.0

            prices = historical_data['close'].values
            dynamic_price = prices.mean() * multiplier
            logging.info(f"Harga dinamis untuk {symbol} berhasil dihitung: {dynamic_price}")
            return dynamic_price
        except Exception as e:
            logging.error(f"Error saat menghitung harga dinamis untuk {symbol}: {e}")
            return 0.0

    def calculate_dynamic_buy_price(self, symbol: str) -> float:
        return self.calculate_dynamic_price(symbol, self.BUY_MULTIPLIER)

    def calculate_dynamic_sell_price(self, symbol: str) -> float:
        return self.calculate_dynamic_price(symbol, self.SELL_MULTIPLIER)

    def get_current_price(self, symbol: str) -> float:
        try:
            logging.info(f"Mengambil harga saat ini untuk {symbol}...")
            data = self._retry_api_call(self.client.get_symbol_ticker, symbol=symbol)
            if data is None:
                return 0.0
            current_price = float(data['price'])
            logging.info(f"Harga saat ini untuk {symbol} berhasil diambil: {current_price}")
            return current_price
        except Exception as e:
            logging.error(f"Error saat mengambil harga saat ini untuk {symbol}: {e}")
            raise ValueError(f"Error saat mengambil harga saat ini untuk {symbol}: {e}")

    def check_price(self, symbol: str, latest_activity: dict):
        try:
            buy_price = self.calculate_dynamic_buy_price(symbol)
            sell_price = self.calculate_dynamic_sell_price(symbol)
            current_price = self.get_current_price(symbol)

            logging.info(f"Buy price: {buy_price}, Sell price: {sell_price}, Current price: {current_price}")

            if current_price < buy_price and not latest_activity.get('buy', False):
                logging.info(f"Harga saat ini untuk {symbol} lebih rendah dari harga beli: {current_price} < {buy_price}. Aksi: BUY")
                return 'BUY', current_price
            elif current_price > sell_price and latest_activity.get('buy', False):
                logging.info(f"Harga saat ini untuk {symbol} lebih tinggi dari harga jual: {current_price} > {sell_price}. Aksi: SELL")
                return 'SELL', current_price
            else:
                logging.info(f"Harga saat ini untuk {symbol} berada di antara harga beli dan harga jual: {current_price}. Aksi: HOLD")
                return 'HOLD', current_price
        except Exception as e:
            logging.error(f"Error saat memeriksa harga untuk {symbol}: {e}")
            raise ValueError(f"Error saat memeriksa harga untuk {symbol}: {e}")
