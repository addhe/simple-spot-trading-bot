# src/strategy.py
import pandas as pd
import numpy as np
import logging
import os
import time
import pickle
from binance.client import Client
from config.settings import settings
from retrying import retry

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class PriceActionStrategy:
    def __init__(self, symbol: str, use_testnet=False):
        self.symbol = symbol
        self.use_testnet = use_testnet
        self.client = self._initialize_binance_client()
        self.cache_file = f"cache_{self.symbol}.pkl"  # Cache file name
        self.data = pd.DataFrame()

    def _initialize_binance_client(self):
        """Initialize Binance client with API keys."""
        try:
            api_url = 'https://testnet.binance.vision/api' if self.use_testnet else 'https://api.binance.com/api'
            client = Client(settings['API_KEY'], settings['API_SECRET'])
            client.API_URL = api_url
            logging.info(f"Binance client initialized for symbol {self.symbol}. Testnet: {self.use_testnet}")
            return client
        except Exception as e:
            logging.error(f"Error initializing Binance client: {e}")
            raise

    def load_cached_data(self):
        """Try to load cached data for optimization, only valid for 5 minutes."""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'rb') as f:
                    cached_data = pickle.load(f)
                    if time.time() - cached_data['timestamp'] < 300:  # Cache valid for 5 minutes
                        logging.info("Loaded data from cache.")
                        return cached_data['data']
            return None
        except Exception as e:
            logging.error(f"Error loading cached data: {e}")
            return None

    def save_to_cache(self, data):
        """Save data to cache."""
        try:
            with open(self.cache_file, 'wb') as f:
                pickle.dump({'timestamp': time.time(), 'data': data}, f)
            logging.info("Data saved to cache.")
        except Exception as e:
            logging.error(f"Error saving to cache: {e}")

    @retry(stop_max_attempt_number=5, wait_fixed=2000)
    def get_historical_data(self, cache=True) -> pd.DataFrame:
        """Fetch historical data with optional caching."""
        try:
            if cache:
                cached_data = self.load_cached_data()
                if cached_data is not None:
                    return cached_data

            klines = self.client.get_historical_klines(
                self.symbol,
                '1m',  # Interval 1 minute
                '1 day ago UTC'  # Data for the last 24 hours
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

            self.save_to_cache(historical_data)
            return historical_data
        except Exception as e:
            logging.error(f"Error getting historical data for {self.symbol}: {e}")
            return pd.DataFrame()

    def calculate_dynamic_buy_price(self) -> float:
        """Calculate dynamic buy price based on market volatility (ATR)."""
        try:
            historical_data = self.get_historical_data()
            if historical_data.empty:
                logging.warning(f"No historical data for {self.symbol}. Using default buy price.")
                return 10000  # Default if no historical data

            prices = historical_data['close'].values
            moving_average = prices[-10:].mean()  # Last 10 closing prices
            atr = self.calculate_atr(historical_data)

            if atr == 0:
                logging.warning(f"ATR for {self.symbol} is 0, using default multiplier.")
                return moving_average * 0.95  # Dynamic buy price, 5% below moving average

            dynamic_buy_price = moving_average * (1 - (0.05 + atr * 0.02))  # 5% minus volatility
            return dynamic_buy_price
        except Exception as e:
            logging.error(f"Error calculating dynamic buy price for {self.symbol}: {e}")
            return 10000

    def calculate_dynamic_sell_price(self) -> float:
        """Calculate dynamic sell price based on market volatility (ATR)."""
        try:
            historical_data = self.get_historical_data()
            if historical_data.empty:
                logging.warning(f"No historical data for {self.symbol}. Using default sell price.")
                return 9000  # Default if no historical data

            prices = historical_data['close'].values
            moving_average = prices[-10:].mean()  # Last 10 closing prices
            atr = self.calculate_atr(historical_data)

            if atr == 0:
                logging.warning(f"ATR for {self.symbol} is 0, using default multiplier.")
                return moving_average * 1.05  # Dynamic sell price, 5% above moving average

            dynamic_sell_price = moving_average * (1 + (0.05 + atr * 0.02))  # 5% plus volatility
            return dynamic_sell_price
        except Exception as e:
            logging.error(f"Error calculating dynamic sell price for {self.symbol}: {e}")
            return 9000

    def calculate_atr(self, historical_data: pd.DataFrame) -> float:
        """Calculate Average True Range (ATR) for market volatility."""
        try:
            high_low = historical_data['high'] - historical_data['low']
            high_close = abs(historical_data['high'] - historical_data['close'].shift())
            low_close = abs(historical_data['low'] - historical_data['close'].shift())
            ranges = pd.concat([high_low, high_close, low_close], axis=1)
            true_range = ranges.max(axis=1)
            atr = true_range.rolling(window=14).mean().iloc[-1]
            return atr
        except Exception as e:
            logging.error(f"Error calculating ATR for {self.symbol}: {e}")
            return 0

# Usage example in main.py
# strategy = PriceActionStrategy(symbol='BTCUSDT', use_testnet=True)
# buy_price = strategy.calculate_dynamic_buy_price()
# sell_price = strategy.calculate_dynamic_sell_price()
