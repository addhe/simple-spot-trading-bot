#!/usr/bin/env python
import os
import time
import sqlite3
import threading
import math
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from binance.exceptions import BinanceAPIException, BinanceOrderException
import argparse
import requests
import sys

from config.settings import (
    SYMBOL_CONFIG,
    INTERVAL,
    CACHE_LIFETIME,
    BUY_MULTIPLIER,
    SELL_MULTIPLIER,
    MIN_VOLUME_MULTIPLIER,
    MIN_POSITION_SIZE,
    MIN_24H_VOLUME,
    MARKET_VOLATILITY_LIMIT,
    TRAILING_STOP,
    TAKE_PROFIT,
    MIN_TRADE_AMOUNT,
    MAX_INVESTMENT_PER_TRADE,
    RSI_OVERSOLD
)

from src.logger import logger
from src.get_balances import get_balances
from src.database_manager import DatabaseManager
from src.trade_manager import TradeManager
from src.send_telegram_message import send_telegram_message
from src.binance_client import get_binance_client

class TradingBot:
    def __init__(self):
        """Initialize trading bot with configuration"""
        # Initialize logger
        self.logger = logger
        self.logger.info("Initializing trading bot...")

        # Initialize database manager
        self.db_manager = DatabaseManager('table_transactions.db')

        # Initialize Binance client
        self.client = get_binance_client()
        self.logger.info("Successfully initialized Binance client")

        # Initialize trade manager
        self.trade_manager = TradeManager(self.db_manager, self.client)

        # Get initial balances
        balances = get_balances()
        self.available_balance = balances.get('USDT', {}).get('free', 0)

        # Initialize trading pairs and parameters
        self.trading_pairs = list(SYMBOL_CONFIG.keys())
        self.min_trade_amount = MIN_TRADE_AMOUNT
        self.min_24h_volumes = MIN_24H_VOLUME
        self.buy_multiplier = BUY_MULTIPLIER
        self.sell_multiplier = SELL_MULTIPLIER
        self.trailing_stop = TRAILING_STOP
        self.take_profit = TAKE_PROFIT

        # Initialize database and calculate initial value
        self.db_manager.setup_tables()
        initial_value = self.calculate_total_value(balances)
        self.logger.info(f"Initial portfolio value: {initial_value} USDT")
        self.logger.info(f"Initialized trading pairs: {self.trading_pairs}")

        # Initialize thread status and error tracking
        self.thread_status = {
            'main_thread': True,
            'status_thread': True,
            'cleanup_thread': True
        }
        self.error_counts = {symbol: 0 for symbol in self.trading_pairs}
        self.MAX_ERRORS = 3

    def get_current_market_price(self, symbol):
        """
        Improved market price retrieval with proper error handling
        """
        normalized_symbol = self.get_normalized_symbol(symbol)
        try:
            ticker = self.client.get_ticker(symbol=normalized_symbol)
            return float(ticker['lastPrice'])
        except BinanceAPIException as e:
            self.logger.error(f"Binance API error getting price for {normalized_symbol}: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error getting price for {normalized_symbol}: {e}")
            return None

    def get_normalized_symbol(self, symbol):
        """
        Ensures consistent symbol format for Binance API calls
        """
        if not symbol.endswith('USDT'):
            return f"{symbol}USDT"
        return symbol

    def check_symbol_balance(self, symbol, balances):
        """
        Check if we have any balance for a given symbol
        Returns tuple of (has_balance, balance_amount)
        """
        base_symbol, _ = self.get_symbol_info(symbol)
        if not base_symbol:
            return False, 0

        if base_symbol in balances:
            balance = float(balances[base_symbol].get('free', 0))
            if balance > 0:
                return True, balance
            self.logger.debug(f"Zero balance for {base_symbol}")
        else:
            self.logger.debug(f"No balance entry for {base_symbol}")

        return False, 0

    def get_symbol_info(self, symbol):
        """
        Get detailed information about a trading symbol
        Returns base symbol and quote symbol
        """
        if symbol not in self.trading_pairs:
            self.logger.error(f"Symbol {symbol} not in configured trading pairs")
            return None, None

        config = SYMBOL_CONFIG.get(symbol)
        if not config:
            self.logger.error(f"No configuration found for {symbol}")
            return None, None

        return symbol.replace('USDT', ''), 'USDT'

    def calculate_total_value(self, balances):
        """
        Calculate total portfolio value based on configured trading pairs
        """
        total_value = 0.0
        try:
            for symbol in self.trading_pairs:
                base_symbol, _ = self.get_symbol_info(symbol)
                if not base_symbol:
                    continue

                if base_symbol in balances:
                    balance = balances[base_symbol]['total']
                    if balance > 0:
                        current_price = self.get_current_market_price(symbol)
                        if current_price:
                            total_value += balance * current_price

            # Add USDT balance
            if 'USDT' in balances:
                total_value += balances['USDT']['total']

        except Exception as e:
            self.logger.error(f"Error calculating total value: {e}")

        return total_value

    def process_symbol_trade(self, symbol, usdt_per_symbol, balances):
        """Process trades for configured trading pairs"""
        try:
            # Get current market price
            current_price = self.get_current_market_price(symbol)
            if not current_price:
                self.logger.error(f"Could not get current price for {symbol}")
                return

            # Check if we have any balance for this symbol
            has_balance, position_size = self.check_symbol_balance(symbol, balances)

            # Process trade decision
            action = self.trade_manager.process_trade(symbol, current_price, position_size if has_balance else None)

            if action == "SELL" and has_balance:
                # Execute sell order
                self.trade_manager.execute_sell(symbol, position_size)
                self.logger.info(f"Sell order executed for {symbol}")

            elif action == "BUY" and not has_balance:
                # Calculate position size
                buy_quantity = self.calculate_position_size(symbol, current_price, usdt_per_symbol)
                if buy_quantity > 0:
                    # Execute buy order
                    self.trade_manager.execute_buy(symbol, buy_quantity)
                    self.logger.info(f"Buy order executed for {symbol}")

        except Exception as e:
            self.logger.error(f"Error processing {symbol}: {e}")

    def calculate_position_size(self, symbol, current_price, usdt_per_symbol):
        """
        Calculate position size based on available balance and symbol configuration
        """
        try:
            config = SYMBOL_CONFIG.get(symbol, {})
            min_qty = config.get('min_qty', 0)
            qty_step = config.get('qty_step', 0)

            if not all([min_qty, qty_step]):
                self.logger.error(f"Invalid configuration for {symbol}")
                return 0

            # Calculate raw quantity
            raw_qty = usdt_per_symbol / current_price

            # Round down to the nearest step
            qty = math.floor(raw_qty / qty_step) * qty_step

            # Check minimum quantity
            if qty < min_qty:
                self.logger.debug(f"Calculated quantity {qty} is below minimum {min_qty} for {symbol}")
                return 0

            return qty

        except Exception as e:
            self.logger.error(f"Error calculating position size for {symbol}: {e}")
            return 0

    def cleanup(self):
        """Cleanup resources"""
        try:
            # Cancel any pending orders
            for symbol in SYMBOL_CONFIG:
                try:
                    self.client.cancel_open_orders(symbol=symbol)
                except Exception:
                    pass  # Ignore errors during cleanup

            # Close database connection
            self.db_manager.close_connection()

        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")

    def start(self):
        """Start the trading bot"""
        try:
            # Start the main trading loop
            trading_thread = threading.Thread(target=self.trade)
            trading_thread.daemon = True
            trading_thread.start()

            # Start the cleanup monitor
            cleanup_thread = threading.Thread(target=self.cleanup_monitor)
            cleanup_thread.daemon = True
            cleanup_thread.start()

            # Start the status monitor
            status_thread = threading.Thread(target=self.check_app_status)
            status_thread.daemon = True
            status_thread.start()

            # Keep the main thread alive
            while True:
                time.sleep(1)

        except KeyboardInterrupt:
            self.logger.info("Shutting down...")
            self.cleanup()
            sys.exit(0)
        except Exception as e:
            self.logger.error(f"Error in main loop: {e}")
            self.cleanup()
            sys.exit(1)

def status_monitor(bot):
    """Monitor and report bot status"""
    while bot.thread_status['status_thread']:
        try:
            bot.send_status_update()
            time.sleep(60)  # Update every minute
        except Exception as e:
            bot.logger.error(f"Error in status monitor: {e}")
            time.sleep(5)  # Short delay on error

def main():
    """Main entry point for the trading bot"""
    parser = argparse.ArgumentParser(description="Trading Bot Runner")
    parser.add_argument("--simulate", action="store_true", help="Run in simulation mode")
    args = parser.parse_args()

    try:
        bot = TradingBot()
        if args.simulate:
            bot.simulate = True
            logger.info("Running in simulation mode")

        bot.start()

    except Exception as e:
        logger.critical(f"Failed to start trading bot: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
