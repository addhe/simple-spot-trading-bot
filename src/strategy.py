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
        """Mengatur stop-loss dan take-profit berdasarkan harga dan kuantitas."""
        if action == 'BUY':
            stop_loss = price * 0.98  # Stop-loss 2% di bawah harga beli
            take_profit = price * 1.05  # Take-profit 5% di atas harga beli
        elif action == 'SELL':
            stop_loss = price * 1.02  # Stop-loss 2% di atas harga jual
            take_profit = price * 0.95  # Take-profit 5% di bawah harga jual
        else:
            return {}

        return {
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'quantity': quantity
        }
