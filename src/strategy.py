# src/strategy.py
import pandas as pd
import logging
from binance.client import Client
from config.settings import settings
from src.check_price import CryptoPriceChecker  # Mengimpor kelas CryptoPriceChecker

class PriceActionStrategy:
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.client = Client(settings['API_KEY'], settings['API_SECRET'])
        self.client.API_URL = 'https://testnet.binance.vision/api'
        self.data = pd.DataFrame()
        self.price_checker = CryptoPriceChecker(self.client)  # Membuat instance dari CryptoPriceChecker
        self.cached_data = None  # Menyimpan data historis yang sudah diambil sebelumnya

    def check_price(self, latest_activity: dict) -> tuple:
        """Memeriksa harga saat ini dan menentukan aksi trading."""
        try:
            return self.price_checker.check_price(self.symbol, latest_activity)  # Menggunakan instance price_checker
        except Exception as e:
            logging.error(f"Error saat memeriksa harga untuk {self.symbol}: {e}")
            return 'HOLD', 0  # Kembalikan 'HOLD' jika terjadi kesalahan

    def get_historical_data(self, cache=True) -> pd.DataFrame:
        """Mengambil data historis untuk simbol yang ditentukan, dengan cache data untuk optimisasi."""
        if cache and self.cached_data is not None:
            return self.cached_data  # Kembalikan data yang sudah ada di cache

        try:
            klines = self.client.get_historical_klines(
                self.symbol,
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

            # Simpan data untuk penggunaan berikutnya
            self.cached_data = historical_data
            return historical_data
        except Exception as e:
            logging.error(f"Error saat mengambil data historis untuk {self.symbol}: {e}")
            return pd.DataFrame()  # Kembalikan DataFrame kosong jika terjadi kesalahan

    def calculate_dynamic_buy_price(self) -> float:
        """Menghitung harga beli dinamis berdasarkan data historis."""
        try:
            historical_data = self.get_historical_data()
            if historical_data.empty:
                logging.warning("Tidak ada data historis. Menggunakan harga default untuk buy.")
                return 10000  # Default jika tidak ada data historis

            prices = historical_data['close'].values
            moving_average = prices[-10:].mean()  # Rata-rata dari 10 harga terakhir
            dynamic_buy_price = moving_average * 0.95  # 5% di bawah rata-rata
            return dynamic_buy_price
        except Exception as e:
            logging.error(f"Error dalam menghitung harga beli dinamis untuk {self.symbol}: {e}")
            return 10000  # Kembalikan default jika terjadi kesalahan

    def calculate_dynamic_sell_price(self) -> float:
        """Menghitung harga jual dinamis berdasarkan data historis."""
        try:
            historical_data = self.get_historical_data()
            if historical_data.empty:
                logging.warning("Tidak ada data historis. Menggunakan harga default untuk sell.")
                return 9000  # Default jika tidak ada data historis

            prices = historical_data['close'].values
            moving_average = prices[-10:].mean()  # Rata-rata dari 10 harga terakhir
            dynamic_sell_price = moving_average * 1.05  # 5% di atas rata-rata
            return dynamic_sell_price
        except Exception as e:
            logging.error(f"Error dalam menghitung harga jual dinamis untuk {self.symbol}: {e}")
            return 9000  # Kembalikan default jika terjadi kesalahan

    def manage_risk(self, action: str, price: float, quantity: float) -> dict:
        """Mengatur stop-loss dan take-profit berdasarkan ATR."""
        try:
            atr = self.calculate_atr()
            if atr == 0:
                logging.warning(f"ATR untuk {self.symbol} adalah 0. Mengabaikan pengaturan stop-loss dan take-profit.")
                return {}

            if action == 'BUY':
                stop_loss = price - (2 * atr)
                take_profit = price + (3 * atr)
            elif action == 'SELL':
                stop_loss = price + (2 * atr)
                take_profit = price - (3 * atr)
            else:
                return {}

            return {
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'quantity': quantity
            }
        except Exception as e:
            logging.error(f"Error dalam mengatur risiko untuk {action} pada harga {price}: {e}")
            return {}

    def calculate_atr(self) -> float:
        """Menghitung Average True Range (ATR) untuk volatilitas."""
        try:
            historical_data = self.get_historical_data()
            if historical_data.empty:
                logging.warning(f"Tidak ada data historis untuk ATR di {self.symbol}.")
                return 0

            high_low = historical_data['high'] - historical_data['low']
            high_close = abs(historical_data['high'] - historical_data['close'].shift())
            low_close = abs(historical_data['low'] - historical_data['close'].shift())
            ranges = pd.concat([high_low, high_close, low_close], axis=1)
            true_range = ranges.max(axis=1)
            atr = true_range.rolling(window=14).mean().iloc[-1]
            return atr
        except Exception as e:
            logging.error(f"Error dalam menghitung ATR untuk {self.symbol}: {e}")
            return 0

    def should_sell(self, current_price: float, latest_activity: dict) -> bool:
        """Menentukan apakah harus menjual berdasarkan kondisi stop-loss atau take-profit."""
        try:
            if latest_activity['buy']:
                stop_loss = latest_activity['stop_loss']
                take_profit = latest_activity['take_profit']
                if current_price <= stop_loss or current_price >= take_profit:
                    return True
            return False
        except Exception as e:
            logging.error(f"Error dalam menentukan apakah harus menjual untuk {self.symbol}: {e}")
            return False

    def should_buy(self, current_price: float) -> bool:
        """Menentukan apakah harus membeli berdasarkan moving average dan tren pasar."""
        try:
            moving_average = self.calculate_moving_average(10)  # Rata-rata bergerak 10 periode
            if current_price > moving_average:  # Beli jika harga saat ini di atas moving average
                return True
            return False
        except Exception as e:
            logging.error(f"Error dalam menentukan apakah harus membeli untuk {self.symbol}: {e}")
            return False

    def calculate_moving_average(self, window: int) -> float:
        """Menghitung moving average dari harga penutupan."""
        historical_data = self.get_historical_data()
        if not historical_data.empty:
            return historical_data['close'].rolling(window=window).mean().iloc[-1]
        return 0
