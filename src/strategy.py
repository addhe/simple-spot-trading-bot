# src/strategy.py
import pandas as pd
import logging
from binance.client import Client
from config.settings import settings
from src.check_price import check_price

class PriceActionStrategy:
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.client = Client(settings['API_KEY'], settings['API_SECRET'])
        self.client.API_URL = 'https://testnet.binance.vision/api'
        self.data = pd.DataFrame()

    def check_price(self, latest_activity: dict) -> tuple:
        return check_price(self.client, self.symbol, latest_activity)

    def calculate_dynamic_buy_price(self) -> float:
        historical_data = self.get_historical_data()
        if historical_data.empty:
            return 10000  # Default jika tidak ada data historis
        prices = historical_data['close'].values
        moving_average = prices[-10:].mean()  # Rata-rata dari 10 harga terakhir
        return moving_average * 0.95  # 5% di bawah rata-rata

    def calculate_dynamic_sell_price(self) -> float:
        historical_data = self.get_historical_data()
        if historical_data.empty:
            return 9000  # Default jika tidak ada data historis
        prices = historical_data['close'].values
        moving_average = prices[-10:].mean()  # Rata-rata dari 10 harga terakhir
        return moving_average * 1.05  # 5% di atas rata-rata

    def get_historical_data(self) -> pd.DataFrame:
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
            return historical_data
        except Exception as e:
            logging.error(f"Error saat mengambil data historis untuk {self.symbol}: {e}")
            return pd.DataFrame()

    def manage_risk(self, action: str, price: float, quantity: float) -> dict:
        """Mengatur stop-loss dan take-profit berdasarkan ATR."""
        atr = self.calculate_atr()
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

    def should_sell(self, current_price: float, latest_activity: dict) -> bool:
        """Menentukan apakah harus menjual berdasarkan kondisi stop-loss atau take-profit."""
        if latest_activity['buy']:
            stop_loss = latest_activity['stop_loss']
            take_profit = latest_activity['take_profit']
            if current_price <= stop_loss or current_price >= take_profit:
                return True
        return False

    def calculate_atr(self) -> float:
        """Menghitung Average True Range (ATR) untuk volatilitas."""
        historical_data = self.get_historical_data()
        if historical_data.empty:
            return 0
        high_low = historical_data['high'] - historical_data['low']
        high_close = abs(historical_data['high'] - historical_data['close'].shift())
        low_close = abs(historical_data['low'] - historical_data['close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)
        atr = true_range.rolling(window=14).mean().iloc[-1]
        return atr

    def calculate_moving_average(self, period: int) -> float:
        """Menghitung moving average untuk periode tertentu."""
        historical_data = self.get_historical_data()
        if historical_data.empty or len(historical_data) < period:
            return 0
        return historical_data['close'].tail(period).mean()

    def should_buy(self, current_price: float) -> bool:
        """Menentukan apakah harus membeli berdasarkan moving average."""
        moving_average = self.calculate_moving_average(10)  # Rata-rata bergerak 10 periode
        return current_price > moving_average  # Beli jika harga saat ini di atas moving average
