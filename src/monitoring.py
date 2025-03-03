import time
import logging
from datetime import datetime

class MetricsCollector:
    def __init__(self):
        """Initialize metrics collector"""
        self.logger = logging.getLogger('TradingBot')
        self.trades = {}
        self.profits = {}
        self.errors = {}
        self.balances = {}

    def record_trade(self, symbol: str, trade_type: str, amount: float, price: float):
        """Record trade metrics"""
        timestamp = datetime.now().isoformat()
        trade_info = {
            'timestamp': timestamp,
            'type': trade_type,
            'amount': amount,
            'price': price,
            'total': amount * price
        }

        if symbol not in self.trades:
            self.trades[symbol] = []
        self.trades[symbol].append(trade_info)

        self.logger.info(f"Trade recorded - Symbol: {symbol}, Type: {trade_type}, Amount: {amount}, Price: {price}")

    def update_profit(self, symbol: str, profit: float):
        """Update profit metrics"""
        self.profits[symbol] = profit
        self.logger.info(f"Profit updated - Symbol: {symbol}, Profit: {profit}")

    def record_error(self, error_type: str):
        """Record error metrics"""
        timestamp = datetime.now().isoformat()
        if error_type not in self.errors:
            self.errors[error_type] = []
        self.errors[error_type].append(timestamp)

        self.logger.error(f"Error recorded - Type: {error_type}")

    def update_balance(self, asset: str, balance: float):
        """Update balance metrics"""
        self.balances[asset] = balance
        self.logger.info(f"Balance updated - Asset: {asset}, Balance: {balance}")

    def get_metrics(self):
        """Get all metrics"""
        return {
            'trades': self.trades,
            'profits': self.profits,
            'errors': self.errors,
            'balances': self.balances
        }

# Initialize metrics collector
metrics = MetricsCollector()
