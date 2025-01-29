# src/check_price.py
import os
import time
import pandas as pd
import logging
from binance.client import Client
from binance.exceptions import BinanceAPIException
from config.settings import settings
from src.logger import redirect_stdout_stderr

# Konfigurasi logging yang lebih baik untuk produksi
log_file_path = "logs/bot/bot.log"
os.makedirs(os.path.dirname(log_file_path), exist_ok=True)
redirect_stdout_stderr(log_file_path)

class CryptoPriceChecker:
    BUY_MULTIPLIER = settings['BUY_MULTIPLIER']
    SELL_MULTIPLIER = settings['SELL_MULTIPLIER']
    DATA_DIR = "historical_data"
    CACHE_LIFETIME = settings['CACHE_LIFETIME']
    MAX_RETRIES = settings['MAX_RETRIES']
    RETRY_BACKOFF = settings['RETRY_BACKOFF']

    def __init__(self, client: Client):
        self.client = client
        os.makedirs(self.DATA_DIR, exist_ok=True)  # Pastikan direktori data ada
        self.cached_data = {}

    def _get_offline_data_path(self, symbol: str) -> str:
        """Menentukan path file CSV untuk data historis offline."""
        return os.path.join(self.DATA_DIR, f"{symbol}_historical.csv")

    def _load_offline_data(self, symbol: str) -> pd.DataFrame:
        """Memuat data historis dari file offline."""
        path = self._get_offline_data_path(symbol)
        if os.path.exists(path):
            logging.info(f"Memuat data historis offline untuk {symbol} dari {path}...")
            return pd.read_csv(path, parse_dates=['timestamp'])
        else:
            logging.warning(f"Tidak ditemukan data historis offline untuk {symbol} di {path}.")
            return pd.DataFrame()

    def _save_offline_data(self, symbol: str, data: pd.DataFrame):
        """Menyimpan data historis ke file CSV."""
        path = self._get_offline_data_path(symbol)
        try:
            logging.info(f"Menyimpan data historis offline untuk {symbol} ke {path}...")
            data.to_csv(path, index=False)
        except Exception as e:
            logging.error(f"Gagal menyimpan data historis untuk {symbol}: {e}")

    def _retry_api_call(self, func, *args, **kwargs):
        """Mengelola percakapan API dengan retry dan backoff eksponensial."""
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
        """Mengambil data historis untuk simbol tertentu dengan menggunakan cache atau API."""
        # Cek apakah data historis sudah tersedia dalam cache
        if symbol in self.cached_data and time.time() - self.cached_data[symbol]['timestamp'] < self.CACHE_LIFETIME:
            logging.info(f"Data historis untuk {symbol} diambil dari cache.")
            return self.cached_data[symbol]['data']

        # Jika data offline tersedia, coba gunakan data tersebut
        offline_data = self._load_offline_data(symbol)
        try:
            logging.info(f"Mengambil data historis untuk {symbol} dari API...")
            klines = self._retry_api_call(self.client.get_historical_klines, symbol, interval, start_time)

            if klines is None:
                logging.error(f"Gagal mengambil data historis dari API, menggunakan data offline.")
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

    def calculate_dynamic_price(self, symbol: str, multiplier: float, tolerance: float = 0.01) -> float:
        """Menghitung harga dinamis dengan toleransi margin untuk meminimalkan hold."""
        try:
            logging.info(f"Menghitung harga dinamis untuk {symbol} dengan toleransi {tolerance}...")
            historical_data = self.get_historical_data(symbol)
            if historical_data.empty:
                logging.warning(f"Tidak ada data historis untuk {symbol}. Menggunakan harga 0.")
                return 0.0

            prices = historical_data['close'].values
            dynamic_price = prices.mean() * multiplier
            logging.info(f"Harga dinamis untuk {symbol} berhasil dihitung: {dynamic_price}")

            # Adjust the dynamic price with a tolerance margin
            adjusted_price = dynamic_price * (1 + tolerance)
            return adjusted_price
        except Exception as e:
            logging.error(f"Error saat menghitung harga dinamis untuk {symbol}: {e}")
            return 0.0

    def log_balance(self):
        """Mencetak saldo saat ini ke log."""
        try:
            balance = self.client.get_asset_balance(asset='USDT')  # Ganti dengan aset yang relevan
            if balance:
                logging.info(f"Saldo USDT saat ini: {balance['free']}")
            else:
                logging.warning("Saldo USDT tidak ditemukan.")
        except Exception as e:
            logging.error(f"Error saat mengambil saldo: {e}")

    def get_asset_balance(self, asset: str) -> float:
        """Mengambil saldo aset."""
        try:
            balance = self.client.get_asset_balance(asset)
            return float(balance['free']) if balance else 0.0
        except Exception as e:
            logging.error(f"Error saat mengambil saldo aset {asset}: {e}")
            return 0.0

    def calculate_dynamic_buy_price(self, symbol: str) -> float:
        """Menghitung harga beli dinamis untuk simbol tertentu."""
        return self.calculate_dynamic_price(symbol, self.BUY_MULTIPLIER)

    def calculate_dynamic_sell_price(self, symbol: str) -> float:
        """Menghitung harga jual dinamis untuk simbol tertentu."""
        return self.calculate_dynamic_price(symbol, self.SELL_MULTIPLIER)

    def get_current_price(self, symbol: str) -> float:
        """Mengambil harga saat ini untuk simbol tertentu."""
        try:
            logging.info(f"Mengambil harga saat ini untuk {symbol}...")
            data = self._retry_api_call(self.client.get_symbol_ticker, symbol=symbol)
            if data is None:
                logging.error(f"Gagal mengambil harga saat ini untuk {symbol}.")
                return 0.0
            current_price = float(data['price'])
            logging.info(f"Harga saat ini untuk {symbol} berhasil diambil: {current_price}")
            return current_price
        except Exception as e:
            logging.error(f"Error saat mengambil harga saat ini untuk {symbol}: {e}")
            raise ValueError(f"Error saat mengambil harga saat ini untuk {symbol}: {e}")

    def check_price(self, symbol: str, latest_activity: dict):
        """Memeriksa harga dan menentukan apakah perlu melakukan aksi BUY, SELL, atau HOLD."""
        try:
            buy_price = self.calculate_dynamic_buy_price(symbol)
            sell_price = self.calculate_dynamic_sell_price(symbol)
            current_price = self.get_current_price(symbol)
            base_asset = symbol.split('USDT')[0]
            quote_asset = 'USDT'
            base_asset_balance = self.get_asset_balance(base_asset)
            quote_asset_balance = self.get_asset_balance(quote_asset)

            logging.info(f"Buy price: {buy_price}, Sell price: {sell_price}, Current price: {current_price}")
            logging.info(f"Saldo {base_asset}: {base_asset_balance}, Saldo {quote_asset}: {quote_asset_balance}")

            if current_price < buy_price and not latest_activity.get('buy', False) and quote_asset_balance > 0:
                logging.info(f"Harga saat ini untuk {symbol} lebih rendah dari harga beli: {current_price} < {buy_price}. Aksi: BUY")
                return 'BUY', current_price
            elif current_price > sell_price and latest_activity.get('buy', False) and base_asset_balance > 0:
                logging.info(f"Harga saat ini untuk {symbol} lebih tinggi dari harga jual: {current_price} > {sell_price}. Aksi: SELL")
                return 'SELL', current_price
            else:
                logging.info(f"Harga saat ini untuk {symbol} berada di antara harga beli dan harga jual: {current_price}. Aksi: HOLD")
                return 'HOLD', current_price
        except Exception as e:
            logging.error(f"Error saat memeriksa harga untuk {symbol}: {e}")
            raise ValueError(f"Error saat memeriksa harga untuk {symbol}: {e}")

# Example usage:
# client = Client(API_KEY, API_SECRET)
# price_checker = CryptoPriceChecker(client)
# price_checker.check_price("BTCUSDT", {'buy': True})