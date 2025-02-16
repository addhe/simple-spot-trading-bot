#!/usr/bin/env python
import os
import time
import sqlite3
import threading
import math
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceOrderException
import argparse
import requests
import sys

from config.settings import (
    API_KEY,
    API_SECRET,
    BASE_URL,
    TELEGRAM_TOKEN,
    TELEGRAM_GROUP_ID,
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

class TradingBot:
    def __init__(self):
        """Initialize trading bot with configuration"""
        # Initialize logger
        self.logger = logger
        self.logger.info("Initializing trading bot...")

        # Initialize database manager
        self.db_manager = DatabaseManager('table_transactions.db')

        # Initialize Binance client
        self.initialize_client()

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

    def initialize_client(self):
        """Initialize Binance client"""
        if not API_KEY or not API_SECRET:
            self.logger.error("API Key and Secret not found! Make sure they are set in environment variables.")
            raise ValueError("Missing API credentials")

        try:
            self.client = Client(api_key=API_KEY, api_secret=API_SECRET)
            if BASE_URL:
                self.client.API_URL = BASE_URL
            self.logger.info("Successfully initialized Binance client")
        except Exception as e:
            self.logger.error(f"Failed to initialize Binance client: {e}")
            raise

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
                else:
                    self.send_no_trade_notification(symbol, "Insufficient funds to buy.")

            else:
                reason = "No action taken. "
                if not has_balance:
                    reason += "No balance available for trading."
                elif action is None:
                    reason += "Conditions for trading not met."
                self.send_no_trade_notification(symbol, reason)

        except Exception as e:
            self.logger.error(f"Error processing {symbol}: {e}")

    def send_no_trade_notification(self, symbol, reason):
        message = f"📉 Trading Alert for {symbol}: {reason}"
        send_telegram_message(message)

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
            self.logger.error(f"No configuration found for symbol {symbol}")
            return None, None

        return config['base_asset'], config['quote_asset']

    def calculate_total_value(self, balances):
        """
        Calculate total portfolio value based on configured trading pairs
        """
        total_value = 0.0

        # Add USDT balance
        usdt_balance = float(balances.get('USDT', {}).get('free', 0))
        total_value += usdt_balance

        # Track processed base symbols to avoid duplicates
        processed_symbols = set()

        for symbol in SYMBOL_CONFIG:
            base_symbol, _ = self.get_symbol_info(symbol)
            if not base_symbol:
                continue

            # Skip if we've already processed this base symbol
            if base_symbol in processed_symbols:
                continue

            processed_symbols.add(base_symbol)

            if base_symbol in balances:
                asset_balance = float(balances[base_symbol].get('free', 0))
                if asset_balance > 0:
                    current_price = self.get_current_market_price(symbol)
                    if current_price:
                        asset_value = asset_balance * current_price
                        total_value += asset_value
                        self.logger.info(f"Added {base_symbol} value: {asset_value} USDT")
                else:
                    self.logger.debug(f"Zero balance for {base_symbol}")
            else:
                self.logger.debug(f"No balance entry for {base_symbol}")

        return total_value

    def should_buy(self, symbol, current_price):
        """Determine whether to buy based on technical analysis"""
        try:
            conn = self.db_manager.get_connection()
            query = f'''
                SELECT timestamp, close_price, volume
                FROM historical_data
                WHERE symbol = '{symbol}'
                ORDER BY timestamp DESC
                LIMIT 500
            '''
            df = pd.read_sql_query(query, conn)
            conn.close()

            if len(df) < 50:
                self.logger.debug(f"{symbol}: Data historis tidak cukup untuk analisis (hanya {len(df)} data)")
                return False

            # Calculate basic indicators
            df['MA_50'] = df['close_price'].rolling(window=50).mean()
            df['MA_200'] = df['close_price'].rolling(window=200).mean()
            df['RSI'] = _calculate_rsi(df['close_price'])

            # Calculate Bollinger Bands
            df['BB_upper'], df['BB_middle'], df['BB_lower'] = self._calculate_bollinger_bands(df['close_price'])

            # Calculate MACD
            df['MACD'], df['MACD_signal'] = self._calculate_macd(df['close_price'])
            df['MACD_hist'] = df['MACD'] - df['MACD_signal']

            latest = df.iloc[-1]

            # Log the indicator values for debugging
            self.logger.info(f"Latest indicators for {symbol} - MA_50: {latest['MA_50']}, MA_200: {latest['MA_200']}, RSI: {latest['RSI']}, BB_lower: {latest['BB_lower']}")

            # Enhanced decision logic for buying
            buy_signals = 0

            # RSI oversold condition (weight: 2)
            if latest['RSI'] < RSI_OVERSOLD:
                buy_signals += 2
                self.logger.info(f"{symbol} RSI oversold: {latest['RSI']:.2f}")

            # Price below lower Bollinger Band (weight: 2)
            if latest['close_price'] < latest['BB_lower']:
                buy_signals += 2
                self.logger.info(f"{symbol} Below BB: {latest['close_price']:.2f} < {latest['BB_lower']:.2f}")

            # MACD crossover (weight: 1)
            if df['MACD_hist'].iloc[-1] > 0 and df['MACD_hist'].iloc[-2] < 0:
                buy_signals += 1
                self.logger.info(f"{symbol} MACD crossover")

            # Price below MA50 but above MA200 (weight: 1)
            if latest['close_price'] < latest['MA_50'] and latest['close_price'] > latest['MA_200']:
                buy_signals += 1
                self.logger.info(f"{symbol} Between MAs")

            # Volume spike (weight: 1)
            avg_volume = df['volume'].rolling(window=20).mean().iloc[-1]
            if latest['volume'] > avg_volume * 1.5:
                buy_signals += 1
                self.logger.info(f"{symbol} Volume spike: {latest['volume']:.2f} > {avg_volume:.2f}")

            # Need at least 3 buy signals to enter
            should_buy = buy_signals >= 3
            if should_buy:
                self.logger.info(f"Buy signals triggered for {symbol}: {buy_signals} signals")

            return should_buy
        except Exception as e:
            self.logger.error(f"Error in should_buy for {symbol}: {e}")
            return False

    def _calculate_bollinger_bands(self, prices, window=20, num_std=2):
        """Calculate Bollinger Bands"""
        rolling_mean = prices.rolling(window=window).mean()
        rolling_std = prices.rolling(window=window).std()
        upper_band = rolling_mean + (rolling_std * num_std)
        lower_band = rolling_mean - (rolling_std * num_std)
        return upper_band, rolling_mean, lower_band

    def _calculate_macd(self, prices, fast=12, slow=26, signal=9):
        """Calculate MACD"""
        exp1 = prices.ewm(span=fast, adjust=False).mean()
        exp2 = prices.ewm(span=slow, adjust=False).mean()
        macd = exp1 - exp2
        signal_line = macd.ewm(span=signal, adjust=False).mean()
        return macd, signal_line

    def calculate_position_size(self, symbol, current_price, usdt_per_symbol):
        """
        Calculate position size based on available balance and symbol configuration
        """
        try:
            # Get minimum trade amount for the symbol
            min_trade = self.min_trade_amount.get(symbol, MIN_POSITION_SIZE)

            # Calculate minimum USDT required
            min_usdt_required = min_trade * current_price

            # Calculate maximum position size based on available balance
            max_position = min(usdt_per_symbol, MAX_INVESTMENT_PER_TRADE) / current_price

            # If we can't meet minimum trade amount, skip
            if max_position < min_trade:
                self.logger.warning(
                    f"Insufficient funds for {symbol}. "
                    f"Required: {min_usdt_required:.2f} USDT, "
                    f"Available per pair: {usdt_per_symbol:.2f} USDT"
                )
                return 0

            # Get symbol precision
            precision = SYMBOL_CONFIG[symbol]['quantity_precision']

            # Round down to meet symbol precision
            position_size = float(format(max_position, f'.{precision}f'))

            self.logger.info(
                f"Calculated position for {symbol}: {position_size} "
                f"({position_size * current_price:.2f} USDT)"
            )

            return position_size

        except Exception as e:
            self.logger.error(f"Error calculating position size for {symbol}: {e}")
            return 0

    def trade(self):
        """Main trading loop"""
        try:
            while self.thread_status['main_thread']:
                try:
                    # Get current balances
                    balances = get_balances()
                    if not balances:
                        self.logger.error("Failed to fetch balances")
                        time.sleep(10)
                        continue

                    # Update available balance
                    self.available_balance = balances.get('USDT', {}).get('free', 0)

                    # Calculate USDT per symbol
                    active_pairs = len(self.trading_pairs)
                    usdt_per_symbol = self.available_balance / active_pairs if active_pairs > 0 else 0

                    # Process each trading pair
                    for symbol in self.trading_pairs:
                        try:
                            self.process_symbol_trade(symbol, usdt_per_symbol, balances)
                        except Exception as e:
                            self.handle_symbol_error(symbol, e)
                            continue

                    # Sleep between iterations
                    time.sleep(10)

                except Exception as e:
                    self.logger.error(f"Error in trade loop: {e}")
                    time.sleep(10)

        except Exception as e:
            self.logger.error(f"Critical error in trade function: {e}")
        finally:
            # Make sure to close any open database connections in this thread
            self.db_manager.close_connection()

    def cleanup_old_data(self):
        """Clean up historical data older than 24 hours"""
        try:
            query = '''
                DELETE FROM historical_data
                WHERE timestamp < datetime('now', '-24 hours', 'localtime')
            '''
            self.db_manager.execute_query(query)
            self.logger.info("Successfully cleaned up old historical data")
        except Exception as e:
            self.logger.error(f"Failed to clean up historical data: {e}")
            raise

    def cleanup_monitor(self):
        """Monitor thread for cleaning up old data"""
        error_count = 0
        max_errors = 3
        error_sleep = 60  # Sleep 1 minute after error
        cleanup_interval = 3600  # Run cleanup every hour

        while self.thread_status['cleanup_thread']:
            try:
                # Attempt database cleanup
                self.cleanup_old_data()
                # Reset error count on successful cleanup
                error_count = 0

                # Sleep until next cleanup
                time.sleep(cleanup_interval)

            except Exception as e:
                self.logger.error(f"Error in cleanup monitor: {e}")
                error_count += 1

                if error_count >= max_errors:
                    self.logger.error("Cleanup monitor: Too many consecutive errors")
                    self.thread_status['cleanup_thread'] = False
                    break

                time.sleep(error_sleep)

    def check_app_status(self):
        """Monitor application status"""
        while self.thread_status['status_thread']:
            if not all(self.thread_status.values()):
                self.logger.error("One or more threads are inactive!")
                send_telegram_message("⚠️ Warning: System degraded - check application status")
            time.sleep(600)

    def send_status_update(self):
        """Send status update via Telegram"""
        try:
            balances = get_balances()
            if not balances:
                self.logger.error("Failed to fetch balances")
                return

            total_value = self.calculate_total_value(balances)

            # Format timestamp
            timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

            # Create message header
            message = f"📊 Trading Bot Status Report\n"
            message += f"⏰ {timestamp} UTC\n\n"

            # Add portfolio summary
            message += "💰 Portfolio Summary:\n"
            message += f"Total Value: ${total_value:.2f}\n"
            usdt_balance = balances.get('USDT', {}).get('free', 0)
            message += f"USDT Available: ${usdt_balance:.2f}\n"
            message += f"USDT Locked: ${balances.get('USDT', {}).get('locked', 0):.2f}\n\n"

            # Add asset positions
            message += "🔐 Asset Positions:\n"
            for symbol in self.trading_pairs:
                base_asset, _ = self.get_symbol_info(symbol)
                if base_asset in balances:
                    free_balance = float(balances[base_asset].get('free', 0))
                    locked_balance = float(balances[base_asset].get('locked', 0))
                    if free_balance > 0 or locked_balance > 0:
                        # Get current price
                        current_price = self.get_current_market_price(symbol)
                        if current_price:
                            value_usdt = (free_balance + locked_balance) * current_price
                            message += f"{base_asset}: {free_balance:.8f}"
                            if locked_balance > 0:
                                message += f" (🔒 {locked_balance:.8f})"
                            message += f" [${value_usdt:.2f}]\n"
                            message += f"Current Price: ${current_price:.2f}\n"

            # Add market conditions
            message += "\n📈 Market Conditions:\n"
            for symbol in self.trading_pairs:
                try:
                    ticker = self.client.get_ticker(symbol=symbol)
                    volume_24h = float(ticker['volume'])
                    price_change = float(ticker['priceChangePercent'])
                    message += f"{symbol}:\n"
                    message += f"24h Volume: ${volume_24h:.2f}\n"
                    message += f"24h Change: {price_change:+.2f}%\n"
                except Exception as e:
                    self.logger.error(f"Error getting market data for {symbol}: {e}")

            send_telegram_message(message)

        except Exception as e:
            self.logger.error(f"Error sending status update: {e}")

    def run(self):
        """Run the trading bot"""
        try:
            # Start trading threads
            trade_thread = threading.Thread(target=self.trade)
            status_monitor_thread = threading.Thread(target=status_monitor, args=(self,))
            status_thread = threading.Thread(target=self.check_app_status)
            cleanup_thread = threading.Thread(target=self.cleanup_monitor)

            threads = [trade_thread, status_monitor_thread, status_thread, cleanup_thread]

            for thread in threads:
                thread.daemon = True
                thread.start()

            # Send initial status update
            self.send_status_update()

            # Keep main thread alive
            while self.thread_status['main_thread']:
                time.sleep(1)

        except KeyboardInterrupt:
            self.logger.info("Shutting down gracefully...")
            self.thread_status['main_thread'] = False
            self.thread_status['status_thread'] = False

            # Wait for threads to finish
            for thread in threads:
                thread.join()

        except Exception as e:
            self.logger.critical(f"Fatal error: {e}")
            self.thread_status['main_thread'] = False
            self.thread_status['status_thread'] = False

        finally:
            self.cleanup()
            self.logger.info("Bot shutdown complete")

    def _check_internet_connection(self):
        """Check if internet connection is available"""
        try:
            requests.get("https://api.binance.com", timeout=5)
            return True
        except requests.RequestException:
            return False

    def handle_symbol_error(self, symbol, error):
        """Handle errors for specific symbols"""
        self.error_counts[symbol] += 1
        if self.error_counts[symbol] >= self.MAX_ERRORS:
            self.logger.error(f"Disabling trading for {symbol} due to excessive errors")
            send_telegram_message(f"⚠️ Trading disabled for {symbol} due to excessive errors")

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

        bot.run()

    except Exception as e:
        logger.critical(f"Failed to start trading bot: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
