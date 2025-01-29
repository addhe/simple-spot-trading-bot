# src/trading_strategy.py
from abc import ABC, abstractmethod
import pandas as pd

class TradingStrategy(ABC):
    @abstractmethod
    def generate_signal(self, data: pd.DataFrame) -> int:
        """
        Generate trading signal
        Returns: 1 (buy), -1 (sell), 0 (hold)
        """
        pass

class SMACrossoverStrategy(TradingStrategy):
    def __init__(self, short_window: int = 50, long_window: int = 200):
        self.short_window = short_window
        self.long_window = long_window

    def generate_signal(self, data: pd.DataFrame) -> int:
        data["SMA50"] = data["close"].rolling(self.short_window).mean()
        data["SMA200"] = data["close"].rolling(self.long_window).mean()

        if (
            data["SMA50"].iloc[-2] < data["SMA200"].iloc[-2]
            and data["SMA50"].iloc[-1] > data["SMA200"].iloc[-1]
        ):
            return 1
        elif (
            data["SMA50"].iloc[-2] > data["SMA200"].iloc[-2]
            and data["SMA50"].iloc[-1] < data["SMA200"].iloc[-1]
        ):
            return -1
        return 0
