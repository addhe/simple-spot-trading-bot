import logging
import os
import pandas as pd
from binance.client import Client

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

    def __init__(self, client: Client):
        """
        Inisialisasi class CryptoPriceChecker.

        Args:
        - client (Client): Klien Binance.
        """
        self.client = client
        os.makedirs(self.DATA_DIR, exist_ok=True)  # Pastikan direktori data ada

    def _get_offline_data_path(self, symbol: str) -> str:
        """Mengembalikan path file untuk data historis offline."""
        return os.path.join(self.DATA_DIR, f"{symbol}_historical.csv")

    def _load_offline_data(self, symbol: str) -> pd.DataFrame:
        """
        Memuat data historis dari penyimpanan offline.

        Args:
        - symbol (str): Simbol aset cryptocurrency.

        Returns:
        - pd.DataFrame: Data historis dari file, atau DataFrame kosong jika file tidak ada.
        """
        path = self._get_offline_data_path(symbol)
        if os.path.exists(path):
            logging.info(f"Memuat data historis offline untuk {symbol} dari {path}...")
            return pd.read_csv(path, parse_dates=['timestamp'])
        else:
            logging.warning(f"Tidak ditemukan data historis offline untuk {symbol} di {path}.")
            return pd.DataFrame()

    def _save_offline_data(self, symbol: str, data: pd.DataFrame):
        """
        Menyimpan data historis ke penyimpanan offline.

        Args:
        - symbol (str): Simbol aset cryptocurrency.
        - data (pd.DataFrame): Data historis yang akan disimpan.
        """
        path = self._get_offline_data_path(symbol)
        logging.info(f"Menyimpan data historis offline untuk {symbol} ke {path}...")
        data.to_csv(path, index=False)

    def get_historical_data(self, symbol: str, interval: str = '1m', start_time: str = '1 day ago UTC') -> pd.DataFrame:
        """
        Fungsi untuk mendapatkan data historis aset cryptocurrency.

        Args:
        - symbol (str): Simbol aset cryptocurrency.
        - interval (str): Interval waktu data historis. Default: '1m'.
        - start_time (str): Waktu awal data historis. Default: '1 day ago UTC'.

        Returns:
        - pd.DataFrame: Data historis aset cryptocurrency.
        """
        offline_data = self._load_offline_data(symbol)

        try:
            logging.info(f"Mengambil data historis untuk {symbol} dari API...")
            klines = self.client.get_historical_klines(symbol, interval, start_time)

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
                combined_data = pd.concat([offline_data, new_data]).drop_duplicates(subset='timestamp').sort_values(by='timestamp')
            else:
                combined_data = new_data

            self._save_offline_data(symbol, combined_data)
            logging.info(f"Data historis untuk {symbol} berhasil diperbarui.")
            return combined_data

        except Exception as e:
            logging.error(f"Error saat mengambil data historis untuk {symbol}: {e}")
            return offline_data if not offline_data.empty else pd.DataFrame()

    def calculate_dynamic_price(self, symbol: str, multiplier: float) -> float:
        """
        Fungsi untuk menghitung harga dinamis aset cryptocurrency.

        Args:
        - symbol (str): Simbol aset cryptocurrency.
        - multiplier (float): Faktor pengali harga dinamis.

        Returns:
        - float: Harga dinamis aset cryptocurrency.
        """
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
        """
        Fungsi untuk menghitung harga beli dinamis aset cryptocurrency.

        Args:
        - symbol (str): Simbol aset cryptocurrency.

        Returns:
        - float: Harga beli dinamis aset cryptocurrency.
        """
        return self.calculate_dynamic_price(symbol, self.BUY_MULTIPLIER)

    def calculate_dynamic_sell_price(self, symbol: str) -> float:
        """
        Fungsi untuk menghitung harga jual dinamis aset cryptocurrency.

        Args:
        - symbol (str): Simbol aset cryptocurrency.

        Returns:
        - float: Harga jual dinamis aset cryptocurrency.
        """
        return self.calculate_dynamic_price(symbol, self.SELL_MULTIPLIER)

    def get_current_price(self, symbol: str) -> float:
        """
        Fungsi untuk mengambil harga saat ini aset cryptocurrency.

        Args:
        - symbol (str): Simbol aset cryptocurrency.

        Returns:
        - float: Harga saat ini aset cryptocurrency.
        """
        try:
            logging.info(f"Mengambil harga saat ini untuk {symbol}...")
            data = self.client.get_symbol_ticker(symbol=symbol)
            current_price = float(data['price'])
            logging.info(f"Harga saat ini untuk {symbol} berhasil diambil: {current_price}")
            return current_price
        except Exception as e:
            logging.error(f"Error saat mengambil harga saat ini untuk {symbol}: {e}")
            raise ValueError(f"Error saat mengambil harga saat ini untuk {symbol}: {e}")

    def check_price(self, symbol: str, latest_activity: dict):
        """
        Memeriksa harga terkini dan menentukan aksi.

        Args:
        - symbol (str): Simbol aset cryptocurrency.
        - latest_activity (dict): Aktivitas terakhir (e.g., {"buy": True, "price": 30000.0}).

        Returns:
        - tuple: (aksi, harga_saat_ini)
        """
        try:
            buy_price = self.calculate_dynamic_buy_price(symbol)
            sell_price = self.calculate_dynamic_sell_price(symbol)
            current_price = self.get_current_price(symbol)

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

