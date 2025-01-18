import logging
from binance.client import Client
import pandas as pd

# Konfigurasi logging
logging.basicConfig(
    format='%(asctime)s [%(levelname)s] %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S'
)

class CryptoPriceChecker:
    BUY_MULTIPLIER = 0.95
    SELL_MULTIPLIER = 1.05

    def __init__(self, client: Client):
        """
        Inisialisasi class CryptoPriceChecker.

        Args:
        - client (Client): Klien Binance.
        """
        self.client = client

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
        try:
            logging.info(f"Mengambil data historis untuk {symbol}...")
            klines = self.client.get_historical_klines(
                symbol,
                interval,
                start_time
            )
            logging.info(f"Data historis untuk {symbol} berhasil diambil.")
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
            logging.info(f"Data historis untuk {symbol} berhasil diproses.")
            return historical_data
        except Exception as e:
            logging.error(f"Error saat mengambil data historis untuk {symbol}: {e}")
            return pd.DataFrame()  # Kembalikan DataFrame kosong jika terjadi kesalahan

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
                return 0.0  # Default jika tidak ada data historis
            prices = historical_data['close'].astype(float).values
            dynamic_price = prices.mean() * multiplier
            logging.info(f"Harga dinamis untuk {symbol} berhasil dihitung: {dynamic_price}")
            return dynamic_price
        except Exception as e:
            logging.error(f"Error saat menghitung harga dinamis untuk {symbol}: {e}")
            return 0.0  # Default jika terjadi kesalahan

    def calculate_dynamic_buy_price(self, symbol: str) -> float:
        """
        Fungsi untuk menghitung harga beli dinamis aset cryptocurrency.

        Args:
        - symbol (str): Simbol aset cryptocurrency.

        Returns:
        - float: Harga beli dinamis aset cryptocurrency.
        """
        try:
            logging.info(f"Menghitung harga beli dinamis untuk {symbol}...")
            dynamic_price = self.calculate_dynamic_price(symbol, self.BUY_MULTIPLIER)
            logging.info(f"Harga beli dinamis untuk {symbol} berhasil dihitung: {dynamic_price}")
            return dynamic_price
        except Exception as e:
            logging.error(f"Error saat menghitung harga beli dinamis untuk {symbol}: {e}")
            return 0.0  # Default jika terjadi kesalahan

    def calculate_dynamic_sell_price(self, symbol: str) -> float:
        """
        Fungsi untuk menghitung harga jual dinamis aset cryptocurrency.

        Args:
        - symbol (str): Simbol aset cryptocurrency.

        Returns:
        - float: Harga jual dinamis aset cryptocurrency.
        """
        try:
            logging.info(f"Menghitung harga jual dinamis untuk {symbol}...")
            dynamic_price = self.calculate_dynamic_price(symbol, self.SELL_MULTIPLIER)
            logging.info(f"Harga jual dinamis untuk {symbol} berhasil dihitung: {dynamic_price}")
            return dynamic_price
        except Exception as e:
            logging.error(f"Error saat menghitung harga jual dinamis untuk {symbol}: {e}")
            return 0.0  # Default jika terjadi kesalahan

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

    def check_price(self, symbol, latest_activity):
        try:
            historical_data = self.get_historical_data(symbol)
            buy_price = self.calculate_dynamic_buy_price(symbol)
            sell_price = self.calculate_dynamic_sell_price(symbol)
            current_price = self.get_current_price(symbol)

            if current_price < buy_price and not latest_activity['buy']:
                logging.info(f"Harga saat ini untuk {symbol} lebih rendah dari harga beli: {current_price} < {buy_price}. Aksi: BUY")
                return 'BUY', current_price
            elif current_price > sell_price and latest_activity['buy']:
                logging.info(f"Harga saat ini untuk {symbol} lebih tinggi dari harga jual: {current_price} > {sell_price}. Aksi: SELL")
                return 'SELL', current_price
            else:
                logging.info(f"Harga saat ini untuk {symbol} berada di antara harga beli dan harga jual: {current_price}. Aksi: HOLD")
                return 'HOLD', current_price
        except Exception as e:
            logging.error(f"Error saat memeriksa harga untuk {symbol}: {e}")
            raise ValueError(f"Error saat memeriksa harga untuk {symbol}: {e}")

# Contoh penggunaan
client = Client(api_key='api_key', api_secret='api_secret')
crypto_checker = CryptoPriceChecker(client)
symbol = 'BTCUSDT'
latest_activity = {'buy': True, 'price': 30000.0}
action, current_price = crypto_checker.check_price(symbol, latest_activity)
print(f"Aksi: {action}, Harga saat ini: {current_price}")
