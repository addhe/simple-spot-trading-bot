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
    TAKE_PROFIT
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
        self.min_trade_amounts = MIN_TRADE_AMOUNT
        self.min_24h_volumes = MIN_24H_VOLUME
        self.buy_multiplier = BUY_MULTIPLIER
        self.sell_multiplier = SELL_MULTIPLIER
        self.trailing_stops = TRAILING_STOP
        self.take_profits = TAKE_PROFIT

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

    def process_symbol_trade(self, symbol, usdt_per_symbol, available_balance):
        """Process trades for configured trading pairs"""
        try:
            # Get current market data
            current_price = self.get_current_market_price(symbol)
            if not current_price:
                self.logger.error(f"Could not get current price for {symbol}")
                return

            # Check if we have any position
            balances = get_balances()
            has_position, position_size = self.check_symbol_balance(symbol, balances)

            # Process existing position
            if has_position:
                action, quantity = self.trade_manager.process_trade(symbol, current_price, position_size)
                if action == 'SELL':
                    self.trade_manager.execute_sell(symbol, quantity)
                    return

            # Check if we should buy
            if self.should_buy(symbol, current_price):
                quantity = self.calculate_position_size(symbol, current_price, usdt_per_symbol)
                if quantity > 0:
                    self.trade_manager.execute_buy(symbol, quantity)

        except Exception as e:
            self.logger.error(f"Error processing {symbol}: {e}")
            self.error_counts[symbol] += 1

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

            # Decision logic for buying
            if latest['close_price'] < latest['BB_lower'] and latest['RSI'] < 30:
                return True  # Conditions for buying are met

            return False  # Conditions not met
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
        # Calculate potential quantity based on available USDT
        potential_quantity = usdt_per_symbol / current_price

        # Validate minimum position size
        min_position_size = self.min_position_sizes.get(symbol, MIN_POSITION_SIZE)
        if potential_quantity < min_position_size:
            self.logger.warning(f"Trade amount {potential_quantity} below minimum position size {min_position_size} for {symbol}")
            return 0

        return potential_quantity

    def trade(self):
        """Main trading loop"""
        error_count = 0
        max_errors = 3
        error_sleep = 60  # Sleep 1 minute after error

        while self.thread_status['main_thread']:
            try:
                if not self.thread_status['trade_thread']:
                    self.logger.info("Restarting trade thread...")
                    self.thread_status['trade_thread'] = True
                    error_count = 0

                # Check internet connection first
                if not self._check_internet_connection():
                    self.logger.warning("No internet connection, waiting...")
                    time.sleep(error_sleep)
                    continue

                balances = get_balances()
                self.logger.info(f"Balances fetched: {balances}")
                message = "📊 Trading Bot Status Report\n"
                message += f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                message += "💰 Portfolio Summary:\n"
                message += f"Total Value: ${self.calculate_total_value(balances)}\n"
                message += f"USDT Available: {balances.get('USDT', {}).get('free', 0)}\n\n"
                message += "🔐 Asset Positions:\n"

                for symbol in SYMBOL_CONFIG:
                    if symbol in balances:
                        free_balance = balances[symbol]['free']
                        if self.is_valid_symbol(symbol):
                            current_price = self.get_current_market_price(symbol)
                            message += f"{symbol}: Current Price: {current_price}, Balance: {free_balance}\n"
                        else:
                            self.logger.error(f"Invalid symbol: {symbol} not in SYMBOLS list.")
                    else:
                        self.logger.error(f"Invalid symbol: {symbol} not in balances.")

                send_telegram_message(message)

                for symbol in SYMBOL_CONFIG:
                    try:
                        self.process_symbol_trade(symbol, balances.get('USDT', {}).get('free', 0.0) / len(SYMBOL_CONFIG), self.available_balance)
                    except Exception as e:
                        self.logger.error(f"Error processing {symbol}: {e}")
                        send_telegram_message(f"❌ Error processing trade for {symbol}: {e}")
                        self.handle_symbol_error(symbol, e)
                        continue  # Continue with next symbol

            except Exception as e:
                self.logger.error(f"Critical error in trade function: {e}")
                error_count += 1
                if error_count >= max_errors:
                    self.logger.error("Trade thread: Too many consecutive errors")
                    self.thread_status['trade_thread'] = False
                time.sleep(error_sleep)
                continue

            time.sleep(CACHE_LIFETIME)

    def cleanup_old_data(self):
        """Clean up historical data older than 24 hours"""
        try:
            conn = self.db_manager.get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM historical_data
                WHERE timestamp < datetime('now', '-24 hours', 'localtime')
            ''')
            conn.commit()
            conn.close()
            self.logger.info("Successfully cleaned up old historical data")
        except sqlite3.Error as e:
            self.logger.error(f"Failed to clean up historical data: {e}")

    def cleanup_monitor(self):
        """Monitor thread for cleaning up old data"""
        error_count = 0
        max_errors = 3
        error_sleep = 60  # Sleep 1 minute after error
        cleanup_interval = 3600  # Run cleanup every hour

        while self.thread_status['cleanup_thread']:
            try:
                if not self.thread_status['cleanup_thread']:
                    self.logger.info("Restarting cleanup monitor thread...")
                    self.thread_status['cleanup_thread'] = True
                    error_count = 0

                # Attempt database cleanup
                try:
                    self.cleanup_old_data()
                    # Reset error count on successful cleanup
                    error_count = 0
                except sqlite3.Error as e:
                    self.logger.error(f"Database error during cleanup: {e}")
                    error_count += 1
                except Exception as e:
                    self.logger.error(f"Unexpected error during cleanup: {e}")
                    error_count += 1

                if error_count >= max_errors:
                    self.logger.error("Cleanup monitor: Too many consecutive errors")
                    self.thread_status['cleanup_thread'] = False
                    time.sleep(error_sleep)
                    continue

            except Exception as e:
                self.logger.error(f"Critical error in cleanup monitor: {e}")
                error_count += 1
                if error_count >= max_errors:
                    self.logger.error("Cleanup monitor: Too many consecutive errors")
                    self.thread_status['cleanup_thread'] = False
                time.sleep(error_sleep)
                continue

            time.sleep(cleanup_interval)

    def check_app_status(self):
        """Monitor application status"""
        while self.thread_status['status_thread']:
            if not all(self.thread_status.values()):
                self.logger.error("One or more threads are inactive!")
                send_telegram_message("⚠️ Warning: System degraded - check application status")
            time.sleep(600)

    def run(self):
        """Run the trading bot"""
        try:
            threads = [
                threading.Thread(target=self.trade, daemon=True),
                threading.Thread(target=lambda: status_monitor(self), daemon=True),
                threading.Thread(target=self.cleanup_monitor, daemon=True),
                threading.Thread(target=self.check_app_status, daemon=True)
            ]

            for thread in threads:
                thread.start()

            # Jika mode simulasi (hanya untuk satu siklus) kita hentikan setelah satu iterasi.
            if getattr(self, 'simulate', False):
                self.logger.info("MODE SIMULASI AKTIF: Selesai satu siklus trading.")
                self.thread_status['main_thread'] = False

            # Wait for threads
            while any(thread.is_alive() for thread in threads):
                time.sleep(1)

        except KeyboardInterrupt:
            self.logger.info("Shutting down gracefully...")
            self.thread_status['main_thread'] = False

            # Wait for threads to finish
            for thread in threads:
                thread.join(timeout=5.0)

        except Exception as e:
            self.logger.critical(f"Fatal error: {e}")
            self.thread_status['main_thread'] = False

        finally:
            self.cleanup()

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
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Trading Bot Runner")
    parser.add_argument(
        "--simulate",
        action="store_true",
        help="Jalankan satu siklus simulasi trading (tanpa loop berkelanjutan)"
    )
    args = parser.parse_args()

    try:
        bot = TradingBot()
        if args.simulate:
            bot.simulate = True  # Flag untuk mode simulasi
            # Lakukan satu siklus simulasi: ambil saldo, hitung alokasi, dan proses setiap simbol.
            bot.logger.info("MODE SIMULASI AKTIF: Menjalankan satu siklus trading untuk setiap simbol")
            balances = get_balances()
            if not balances:
                bot.logger.error("Saldo tidak dapat diambil. Pastikan koneksi ke API Binance berjalan dengan baik.")
                sys.exit(1)
            usdt_balance = float(balances.get('USDT', {}).get('free', 0.0))
            if usdt_balance <= 0:
                bot.logger.error("Saldo USDT kosong. Simulasi tidak dapat dijalankan.")
                sys.exit(1)
            usdt_per_symbol = usdt_balance / len(SYMBOL_CONFIG)
            bot.logger.debug(f"Saldo USDT: {usdt_balance}, Alokasi per simbol: {usdt_per_symbol}")

            for symbol in SYMBOL_CONFIG:
                bot.logger.info(f"Simulasi trade untuk {symbol} dengan alokasi {usdt_per_symbol} USDT")
                bot.process_symbol_trade(symbol, usdt_per_symbol, bot.available_balance)
            # Setelah simulasi selesai, hentikan bot
            bot.thread_status['main_thread'] = False
        else:
            bot.run()
    except Exception as e:
        logger.critical(f"Failed to start trading bot: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
