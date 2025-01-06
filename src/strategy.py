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
        # Panggil fungsi check_price dari modul terpisah
        return check_price(self.client, self.symbol, latest_activity)

    def calculate_dynamic_buy_price(self, window: int = 10, margin: float = 0.05) -> float:
        historical_data = self.get_historical_data()
        if historical_data.empty:
            return 10000  # Default jika tidak ada data historis
        prices = historical_data['close'].values
        moving_average = prices[-window:].mean()  # Rata-rata dari window harga terakhir
        return moving_average * (1 - margin)  # margin di bawah rata-rata

    def calculate_dynamic_sell_price(self, window: int = 10, margin: float = 0.05) -> float:
        historical_data = self.get_historical_data()
        if historical_data.empty:
            return 9000  # Default jika tidak ada data historis
        prices = historical_data['close'].values
        moving_average = prices[-window:].mean()  # Rata-rata dari window harga terakhir
        return moving_average * (1 + margin)  # margin di atas rata-rata

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
            historical_data['timestamp'] = pd.to_datetime(historical_data['timestamp'], unit='ms', utc=True)
            historical_data['close'] = historical_data['close'].astype(float)
            return historical_data
        except Exception as e:
            logging.error(f"Error saat mengambil data historis untuk {self.symbol}: {e}")
            return pd.DataFrame()

    def manage_risk(self, action: str, price: float, quantity: float, stop_loss_margin: float = 0.02, take_profit_margin: float = 0.05) -> dict:
        """Mengatur stop-loss dan take-profit berdasarkan harga dan kuantitas."""
        if action == 'BUY':
            stop_loss = price * (1 - stop_loss_margin)  # Stop-loss berdasarkan margin
            take_profit = price * (1 + take_profit_margin)  # Take-profit berdasarkan margin
        elif action == 'SELL':
            stop_loss = price * (1 + stop_loss_margin)  # Stop-loss berdasarkan margin
            take_profit = price * (1 - take_profit_margin)  # Take-profit berdasarkan margin
        else:
            return {}

        # Validasi stop-loss dan take-profit
        if action == 'BUY' and stop_loss >= take_profit:
            logging.error("Stop-loss tidak boleh lebih besar atau sama dengan take-profit untuk BUY.")
            return {}
        if action == 'SELL' and stop_loss <= take_profit:
            logging.error("Stop-loss tidak boleh lebih kecil atau sama dengan take-profit untuk SELL.")
            return {}

        return {
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'quantity': quantity
        }
