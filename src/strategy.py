import pandas as pd
import logging
from binance.client import Client
from config.settings import settings

class PriceActionStrategy:
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.client = Client(settings['API_KEY'], settings['API_SECRET'])
        self.client.API_URL = 'https://testnet.binance.vision/api'
        self.data = pd.DataFrame()

    def check_price(self) -> tuple:
        try:
            self.data = self.client.get_symbol_ticker(symbol=self.symbol)
            current_price = float(self.data['price'])

            logging.debug(f"Harga saat ini untuk {self.symbol}: {current_price}, Type: {type(current_price)}")

            buy_price = self.calculate_dynamic_buy_price()
            sell_price = self.calculate_dynamic_sell_price()

            logging.debug(f"Harga Beli Dinamis: {buy_price}, Type: {type(buy_price)}")
            logging.debug(f"Harga Jual Dinamis: {sell_price}, Type: {type(sell_price)}")

            buy_price = float(buy_price)
            sell_price = float(sell_price)

            if current_price > buy_price:
                logging.info(f"Mempertimbangkan untuk membeli {self.symbol} pada harga {current_price}")
                return 'BUY', current_price
            elif current_price < sell_price:
                logging.info(f"Mempertimbangkan untuk menjual {self.symbol} pada harga {current_price}")
                return 'SELL', current_price
            else:
                logging.info(f"Tidak ada aksi yang diambil untuk {self.symbol} pada harga {current_price}")
                return 'HOLD', current_price

        except Exception as e:
            logging.error(f"Error saat memeriksa harga untuk {self.symbol}: {e}")

    def calculate_dynamic_buy_price(self) -> float:
        historical_data = self.get_historical_data()
        if historical_data.empty:
            return 10000  # Default jika tidak ada data historis
        prices = historical_data['close'].values
        return prices.mean() * 0.95  # 5% di bawah rata-rata

    def calculate_dynamic_sell_price(self) -> float:
        historical_data = self.get_historical_data()
        if historical_data.empty:
            return 9000  # Default jika tidak ada data historis
        prices = historical_data['close'].values
        return prices.mean() * 1.05  # 5% di atas rata-rata

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
