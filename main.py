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
import logging

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
    RSI_OVERSOLD,
    MIN_USDT_BALANCE
)

from src.logger import logger
from src.get_balances import get_balances
from src.db_manager import DatabaseManager
from src.trade_manager import TradeManager
from src.send_telegram_message import send_telegram_message
from src.historical_data import HistoricalDataCollector

class TradingBot:
    def __init__(self):
        """Initialize trading bot with configuration"""
        # Initialize logger
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG)  # Set logger to DEBUG level
        self.logger.info("Initializing trading bot...")

        # Configure logging
        logging.basicConfig(
            level=logging.DEBUG,  # Set root logger to DEBUG level
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('logs/bot/bot.log'),
                logging.StreamHandler()
            ]
        )

        # Initialize database manager
        self.db_manager = DatabaseManager('trading_data.db')
        self.db_manager.initialize_database()  # Initialize database tables

        # Initialize Binance client
        self.initialize_client()

        # Initialize historical data collector
        self.historical_collector = HistoricalDataCollector(self.client, self.db_manager)

        # Initialize trade manager
        self.trade_manager = TradeManager(self.db_manager, self.client)

        # Collect initial historical data
        for symbol in SYMBOL_CONFIG:
            self.historical_collector.collect_historical_data(symbol)

        # Initialize trading pairs and parameters
        self.trading_pairs = list(SYMBOL_CONFIG.keys())
        self.min_trade_amount = MIN_TRADE_AMOUNT
        self.min_24h_volumes = MIN_24H_VOLUME
        self.buy_multiplier = BUY_MULTIPLIER
        self.sell_multiplier = SELL_MULTIPLIER
        self.trailing_stop = TRAILING_STOP
        self.take_profit = TAKE_PROFIT

        # Initialize balances
        self.update_balances()

        # Initialize thread status and error tracking
        self.thread_status = {
            'main_thread': True,
            'error_thread': True
        }
        self.error_count = 0
        self.last_error_time = None
        self.logger.info(f"Initialized trading pairs: {self.trading_pairs}")
        self.logger.info("Trading bot initialized successfully")

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

    def update_balances(self):
        """Update current balances"""
        try:
            self.balances = get_balances(self.client)
            if self.balances:
                self.logger.info(f"Retrieved balances: {self.balances}")
                initial_value = self.calculate_total_value(self.balances)
                self.logger.info(f"Current portfolio value: {initial_value} USDT")
                return True
            else:
                self.logger.error("Failed to get balances")
                return False
        except Exception as e:
            self.logger.error(f"Error updating balances: {e}")
            return False

    def process_symbol_trade(self, symbol, usdt_per_symbol, balances):
        """Process trades for configured trading pairs"""
        try:
            # Get current market price
            current_price = self.get_current_market_price(symbol)
            if not current_price:
                self.logger.error(f"Could not get current price for {symbol}")
                return

            # Get asset info
            base_asset, _ = self.get_symbol_info(symbol)
            
            # Check balances
            has_usdt, usdt_balance = self.check_buy_balance(balances)
            has_asset, asset_balance = self.check_sell_balance(symbol, balances)
            
            self.logger.debug(f"Balance Check for {symbol}:")
            self.logger.debug(f"USDT - Available: ${usdt_balance:.2f}, Sufficient: {has_usdt}")
            self.logger.debug(f"{base_asset} - Available: {asset_balance}, Sufficient: {has_asset}")

            # Get buy/sell decision
            buy_decision = self.trade_manager.should_buy(symbol, current_price)
            self.logger.debug(f"Buy decision for {symbol}: {buy_decision}")

            # Determine trade action based on balances and decision
            if buy_decision:
                if has_usdt:
                    # Calculate buy quantity based on available USDT
                    buy_quantity = self.calculate_position_size(symbol, current_price, usdt_balance)
                    if buy_quantity > 0:
                        self.logger.info(f"Executing buy order for {symbol}: {buy_quantity} @ ${current_price:.2f}")
                        self.trade_manager.execute_buy(symbol, buy_quantity)
                    else:
                        self.send_no_trade_notification(symbol, f"Calculated buy quantity too small")
                else:
                    self.send_no_trade_notification(symbol, f"Insufficient USDT balance (${usdt_balance:.2f}) for buying")
            else:
                # Only attempt to sell if we actually own the asset
                if has_asset and asset_balance > 0:
                    self.logger.info(f"Executing sell order for {symbol}: {asset_balance} @ ${current_price:.2f}")
                    self.trade_manager.execute_sell(symbol, asset_balance)
                else:
                    # Don't send notification if we don't own the asset and aren't trying to buy
                    self.logger.debug(f"No {base_asset} balance to sell and conditions don't favor buying")

        except Exception as e:
            self.logger.error(f"Error processing trade for {symbol}: {e}")
            self.handle_symbol_error(symbol, e)

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

    def check_symbol_balance(self, symbol, balances, current_price):
        base_asset, quote_asset = self.get_symbol_info(symbol)
        # Now pass symbol and current_price to should_buy()
        should_buy = self.trade_manager.should_buy(symbol, current_price)
        relevant_asset = quote_asset if should_buy else base_asset
        if relevant_asset in balances:
            balance = balances[relevant_asset]['free']
            return (True, balance) if balance > 0 else (False, 0)
        return False, 0

    def check_buy_balance(self, balances):
        """Check if there is enough USDT balance for buying"""
        self.logger.debug(f"Checking USDT balance in balances: {balances.get('USDT', {})}")
        
        if 'USDT' not in balances:
            self.logger.debug("No USDT found in balances")
            return False, 0
            
        usdt_balance = float(balances['USDT']['free'])
        self.logger.debug(f"Available USDT balance: ${usdt_balance:.2f}")
        
        # Check if balance meets minimum requirements
        min_required = MAX_INVESTMENT_PER_TRADE  # Use max investment as minimum required
        if usdt_balance < min_required:
            self.logger.debug(f"USDT balance (${usdt_balance:.2f}) below minimum required (${min_required:.2f})")
            return False, usdt_balance
            
        self.logger.debug(f"USDT balance (${usdt_balance:.2f}) is sufficient for trading")
        return True, usdt_balance

    def check_sell_balance(self, symbol, balances):
        """Check if there is enough base asset balance for selling"""
        base_asset, _ = self.get_symbol_info(symbol)
        self.logger.debug(f"Checking {base_asset} balance in balances: {balances.get(base_asset, {})}")
        
        if base_asset not in balances:
            self.logger.debug(f"No {base_asset} found in balances")
            return False, 0
            
        asset_balance = float(balances[base_asset]['free'])
        self.logger.debug(f"Available {base_asset} balance: {asset_balance}")
        
        # Check if balance meets minimum requirements
        min_required = MIN_TRADE_AMOUNT.get(symbol, 0)
        if asset_balance < min_required:
            self.logger.debug(f"{base_asset} balance ({asset_balance}) below minimum required ({min_required})")
            return False, asset_balance
            
        self.logger.debug(f"{base_asset} balance ({asset_balance}) is sufficient for trading")
        return True, asset_balance

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
        """Calculate total portfolio value in USDT"""
        total_value = 0.0

        # Add USDT balance
        usdt_balance = float(balances.get('USDT', {}).get('free', 0))
        total_value += usdt_balance
        self.logger.debug(f"USDT balance: {usdt_balance}")

        # Calculate value of other assets
        for symbol in self.trading_pairs:
            try:
                base_asset, _ = self.get_symbol_info(symbol)
                if base_asset in balances:
                    asset_balance = float(balances[base_asset]['free'])
                    if asset_balance > 0:
                        # Get current price
                        current_price = self.get_current_market_price(symbol)
                        if current_price:
                            asset_value = asset_balance * current_price
                            total_value += asset_value
                            self.logger.debug(f"Added {base_asset} value: {asset_value:.2f} USDT")
                        else:
                            self.logger.warning(f"Could not get current price for {symbol}")
                    else:
                        self.logger.debug(f"Zero balance for {base_asset}")
                else:
                    self.logger.debug(f"No balance entry for {base_asset}")
            except Exception as e:
                self.logger.error(f"Error calculating value for {symbol}: {e}")
                continue

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
                self.logger.debug(f"{symbol}: Not enough historical data for analysis (only {len(df)} records)")
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

            # Log all indicators for debugging
            self.logger.debug(f"Technical Analysis for {symbol}:")
            self.logger.debug(f"Current Price: ${current_price:.2f}")
            self.logger.debug(f"MA50: ${latest['MA_50']:.2f}")
            self.logger.debug(f"MA200: ${latest['MA_200']:.2f}")
            self.logger.debug(f"RSI: {latest['RSI']:.2f}")
            self.logger.debug(f"BB Lower: ${latest['BB_lower']:.2f}")
            self.logger.debug(f"MACD Histogram: {latest['MACD_hist']:.4f}")

            # Enhanced decision logic with more lenient conditions
            buy_signals = 0
            required_signals = 2  # Reduced from 3 to make it more sensitive

            # RSI oversold condition (weight: 2)
            if latest['RSI'] < RSI_OVERSOLD:
                buy_signals += 2
                self.logger.debug(f"✅ RSI is oversold ({latest['RSI']:.2f} < {RSI_OVERSOLD})")
            else:
                self.logger.debug(f"❌ RSI not oversold ({latest['RSI']:.2f} >= {RSI_OVERSOLD})")

            # Price near or below lower Bollinger Band (weight: 2)
            bb_threshold = latest['BB_lower'] * 1.01  # Allow price to be slightly above BB lower
            if current_price <= bb_threshold:
                buy_signals += 2
                self.logger.debug(f"✅ Price near/below BB lower (${current_price:.2f} <= ${bb_threshold:.2f})")
            else:
                self.logger.debug(f"❌ Price above BB lower (${current_price:.2f} > ${bb_threshold:.2f})")

            # MACD momentum (weight: 1)
            if df['MACD_hist'].iloc[-1] > df['MACD_hist'].iloc[-2]:
                buy_signals += 1
                self.logger.debug("✅ MACD momentum is positive")
            else:
                self.logger.debug("❌ MACD momentum is negative")

            # Price between MAs (weight: 1)
            if current_price > latest['MA_200'] and current_price < latest['MA_50']:
                buy_signals += 1
                self.logger.debug(f"✅ Price between MA200 and MA50")
            else:
                self.logger.debug(f"❌ Price not between MA200 and MA50")

            should_buy = buy_signals >= required_signals
            self.logger.info(f"{symbol} Buy Decision: {should_buy} (Signals: {buy_signals}/{required_signals})")
            return should_buy

        except Exception as e:
            self.logger.error(f"Error in should_buy for {symbol}: {str(e)}")
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
        _, quote_asset = self.get_symbol_info(symbol)
        usdt_balance = self.check_symbol_balance(symbol, self.balances)[1]

        # Ensure we don't exceed available USDT
        position_size_usdt = min(usdt_per_symbol, usdt_balance)
        position_size = position_size_usdt / current_price
        return round(position_size, 4)

    def trade(self):
        """Execute trading strategy"""
        try:
            # Update balances first
            if not self.update_balances():
                self.logger.error("Failed to update balances, skipping trade cycle")
                return

            for symbol in self.trading_pairs:
                try:
                    # Get current market price
                    current_price = self.get_current_market_price(symbol)
                    if not current_price:
                        continue

                    # Get trading decision
                    decision = self.trade_manager.process_trade(symbol, current_price)
                    
                    if decision == "BUY":
                        # Calculate position size based on available USDT
                        usdt_balance = float(self.balances.get('USDT', {}).get('free', 0))
                        position_size = min(usdt_balance * 0.95, MAX_INVESTMENT_PER_TRADE) / current_price
                        
                        if position_size * current_price >= MIN_TRADE_AMOUNT:
                            if self.trade_manager.execute_buy(symbol, position_size):
                                self.update_balances()  # Update balances after successful trade
                        else:
                            self.logger.info(f"Position size too small for {symbol}")
                    
                    elif decision == "SELL":
                        base_asset = SYMBOL_CONFIG[symbol]['base_asset']
                        position_size = float(self.balances.get(base_asset, {}).get('free', 0))
                        
                        if position_size * current_price >= MIN_TRADE_AMOUNT:
                            if self.trade_manager.execute_sell(symbol, position_size):
                                self.update_balances()  # Update balances after successful trade
                        else:
                            self.logger.info(f"Position size too small for {symbol}")

                except Exception as e:
                    self.logger.error(f"Error processing {symbol}: {e}")
                    self.error_count += 1
                    self.last_error_time = time.time()
                    
                    if self.error_count >= 3:
                        self.logger.error(f"Disabling trading for {symbol} due to excessive errors")
                        send_telegram_message(f"⚠️ Trading disabled for {symbol} due to excessive errors")
                        if symbol in self.trading_pairs:
                            self.trading_pairs.remove(symbol)

        except Exception as e:
            self.logger.error(f"Error in trade function: {e}")

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
