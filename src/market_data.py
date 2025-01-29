# src/market_data.py
from typing import Optional, Dict
from cachetools import cached, TTLCache
from datetime import timedelta
import pandas as pd
from binance import Client
from .utils import APIUtils, InputValidator
from .exceptions import MarketDataError

class MarketData:
    """Handles market data retrieval with caching and rate limiting"""

    def __init__(self, client: Client):
        self.client = client
        self.cache = TTLCache(maxsize=100, ttl=timedelta(minutes=5).total_seconds())

    @APIUtils.rate_limited_api_call
    @cached(cache=TTLCache(maxsize=50, ttl=300))
    def get_historical_data(
        self, symbol: str, interval: str, limit: int = 100
    ) -> pd.DataFrame:
        """Fetch historical candlestick data with caching"""
        InputValidator.validate_symbol(symbol)

        try:
            candles = self.client.get_klines(
                symbol=symbol, interval=interval, limit=limit
            )
            return self._format_data(candles)
        except Exception as e:
            raise MarketDataError(f"Failed to get historical data: {str(e)}") from e

    @APIUtils.rate_limited_api_call
    @cached(cache=TTLCache(maxsize=100, ttl=15))
    def get_current_price(self, symbol: str) -> float:
        """Get latest price with 15-second cache"""
        InputValidator.validate_symbol(symbol)

        try:
            return float(self.client.get_symbol_ticker(symbol=symbol)["price"])
        except Exception as e:
            raise MarketDataError(f"Failed to get price: {str(e)}") from e

    def _format_data(self, candles: list) -> pd.DataFrame:
        """Format raw API data into DataFrame"""
        columns = [
            "timestamp",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "close_time",
            "quote_volume",
            "trades",
            "taker_buy_base",
            "taker_buy_quote",
            "ignore",
        ]
        df = pd.DataFrame(candles, columns=columns)
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        numeric_cols = ["open", "high", "low", "close", "volume"]
        df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric)
        return df[["timestamp"] + numeric_cols]
