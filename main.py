#!/usr/bin/env python
import os
import sys
import time
import math
import threading
import sqlite3
import argparse
import logging
import numpy as np
import pandas as pd
import functools
import requests

from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceOrderException
from tenacity import retry, stop_after_attempt, wait_exponential

# Import local modules
from src.get_balances import get_balances
from src.get_db_connection import get_db_connection
from src.get_last_buy_price import get_last_buy_price
from src.get_last_price import get_last_price
from src.save_historical_data import save_historical_data
from src.send_asset_status import send_asset_status, get_24h_stats
from src.send_telegram_message import send_telegram_message
from src.status_monitor import status_monitor
from src.setup_database import setup_database
from src.save_transaction import save_transaction
from src.get_symbol_step_size import get_symbol_step_size
from src._validate_kline_data import _validate_kline_data
from src._calculate_rsi import _calculate_rsi
from src._perform_extended_analysis import _perform_extended_analysis
from src.logger import setup_logging
from src.handle_stop_loss import handle_stop_loss
from src.calculate_position_size import calculate_position_size

from config.settings import (
    API_KEY,
    API_SECRET,
    BASE_URL,
    TELEGRAM_TOKEN,
    TELEGRAM_GROUP_ID,
    SYMBOLS,
    INTERVAL,
    CACHE_LIFETIME,
    BUY_MULTIPLIER,
    SELL_MULTIPLIER,
    TOLERANCE,
    STATUS_INTERVAL,
    RSI_OVERSOLD,
    RSI_OVERBOUGHT,
    RSI_PERIOD,
    TRAILING_STOP,
    MAX_INVESTMENT_PER_TRADE,
    MIN_24H_VOLUME,
    MARKET_VOLATILITY_LIMIT,
    MAX_API_RETRIES,
    ERROR_SLEEP_TIME,
    MAX_POSITIONS,
    MIN_VOLUME_MULTIPLIER
)

# Jika parameter STOP_LOSS_PERCENTAGE belum ada di config, tetapkan default di sini:
try:
    from config.settings import STOP_LOSS_PERCENTAGE
except ImportError:
    STOP_LOSS_PERCENTAGE = 0.02  # contoh: 2%

def retry_on_api_error(func):
    @functools.wraps(func)
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=lambda e: isinstance(e, (BinanceAPIException, requests.exceptions.RequestException))
    )
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapper

class TradingBot:
    def __init__(self):
        # Pastikan db_path sudah didefinisikan sebelum dipakai fungsi lain
        self.db_path = 'table_transactions.db'
        self.logger = setup_logging()
        self.initialize_state()
        self.initialize_client()
        self.setup_database()

        # Inisialisasi parameter perdagangan
        self.buy_multiplier = BUY_MULTIPLIER
        self.sell_multiplier = SELL_MULTIPLIER
        self.min_volume_multiplier = MIN_VOLUME_MULTIPLIER

        # Risk management parameters
        self.daily_loss_limit = -0.05  # 5% maximum daily loss
        self.max_drawdown_limit = -0.15  # 15% maximum drawdown
        self.position_size_limit = 0.1  # Maximum 10% of portfolio per position

        # Performance tracking
        self.daily_pnl = 0.0
        self.total_trades = 0
        self.winning_trades = 0
        self.initial_portfolio_value = 0.0
        self.peak_portfolio_value = 0.0

        # Initialize performance tracking
        self._initialize_performance_tracking()

    def _initialize_performance_tracking(self):
        """Initialize performance tracking metrics"""
        try:
            balances = get_balances()
            if balances:
                total_value = float(balances.get('USDT', {}).get('free', 0.0))
                for symbol in SYMBOLS:
                    asset = symbol.replace('USDT', '')
                    if asset in balances:
                        asset_balance = float(balances[asset]['free'])
                        price = get_last_price(symbol)
                        if price:
                            total_value += asset_balance * price

                self.initial_portfolio_value = total_value
                self.peak_portfolio_value = total_value
                self.logger.info(f"Initial portfolio value: {total_value} USDT")
        except Exception as e:
            self.logger.error(f"Error initializing performance tracking: {e}")

    def _update_performance_metrics(self, trade_type, entry_price, exit_price, quantity):
        """Update performance metrics after each trade"""
        if trade_type == 'SELL':
            self.total_trades += 1
            pnl = (exit_price - entry_price) * quantity
            self.daily_pnl += pnl

            if pnl > 0:
                self.winning_trades += 1

            win_rate = (self.winning_trades / self.total_trades) * 100 if self.total_trades > 0 else 0
            self.logger.info(f"Trade Performance:")
            self.logger.info(f"Win Rate: {win_rate:.2f}%")
            self.logger.info(f"Daily P&L: {self.daily_pnl:.2f} USDT")

            # Check risk limits
            current_portfolio_value = self._get_total_portfolio_value()
            daily_return = (current_portfolio_value - self.initial_portfolio_value) / self.initial_portfolio_value
            drawdown = (current_portfolio_value - self.peak_portfolio_value) / self.peak_portfolio_value

            if current_portfolio_value > self.peak_portfolio_value:
                self.peak_portfolio_value = current_portfolio_value

            # Check risk limits
            if daily_return <= self.daily_loss_limit:
                self.logger.warning(f"⚠️ Daily loss limit reached: {daily_return:.2%}")
                send_telegram_message(f"⚠️ Daily loss limit reached: {daily_return:.2%}")
                return False

            if drawdown <= self.max_drawdown_limit:
                self.logger.warning(f"⚠️ Maximum drawdown limit reached: {drawdown:.2%}")
                send_telegram_message(f"⚠️ Maximum drawdown limit reached: {drawdown:.2%}")
                return False

            return True

    def _get_total_portfolio_value(self):
        """Calculate total portfolio value"""
        try:
            balances = get_balances()
            if not balances:
                return 0.0

            total_value = float(balances.get('USDT', {}).get('free', 0.0))
            for symbol in SYMBOLS:
                asset = symbol.replace('USDT', '')
                if asset in balances:
                    asset_balance = float(balances[asset]['free'])
                    price = get_last_price(symbol)
                    if price:
                        total_value += asset_balance * price
            return total_value
        except Exception as e:
            self.logger.error(f"Error calculating portfolio value: {e}")
            return 0.0

    def buy_asset(self, symbol, quantity):
        """Melakukan pembelian aset di Binance"""
        try:
            order = self.client.order_market_buy(
                symbol=symbol,
                quantity=quantity
            )
            self.logger.info(f"✅ Buy order placed: {order}")
            return order
        except BinanceAPIException as e:
            self.logger.error(f"Binance API Exception during buy: {e}")
        except BinanceOrderException as e:
            self.logger.error(f"Binance Order Exception during buy: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error during buy: {e}")

    @retry_on_api_error
    def buy_asset_with_retry(self, symbol, quantity):
        """Melakukan pembelian aset di Binance dengan retry mechanism"""
        try:
            # Validate minimum order size
            min_notional = self.get_min_notional(symbol)
            current_price = get_last_price(symbol)

            if not current_price:
                raise ValueError(f"Could not get current price for {symbol}")

            order_value = quantity * current_price

            if min_notional and order_value < min_notional:
                self.logger.error(f"Order value {order_value} is below minimum notional {min_notional} for {symbol}")
                return None

            # Check internet connection
            if not self._check_internet_connection():
                raise ConnectionError("No internet connection available")

            # Check if we have enough balance
            balances = get_balances()
            usdt_balance = float(balances.get('USDT', {}).get('free', 0.0))

            if usdt_balance < order_value:
                self.logger.error(f"Insufficient USDT balance. Required: {order_value}, Available: {usdt_balance}")
                return None

            order = self.client.order_market_buy(
                symbol=symbol,
                quantity=quantity
            )

            # Log successful transaction
            self.logger.info(f"✅ Buy order successful for {symbol}:")
            self.logger.info(f"   Quantity: {quantity}")
            self.logger.info(f"   Price: {current_price}")
            self.logger.info(f"   Total Value: {order_value} USDT")

            # Save transaction details
            save_transaction(symbol, 'BUY', quantity, current_price, order_value)

            return order

        except BinanceAPIException as e:
            self.logger.error(f"Binance API Exception during buy: {e}")
            raise
        except BinanceOrderException as e:
            self.logger.error(f"Binance Order Exception during buy: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error during buy: {e}")
            raise

    def _check_internet_connection(self):
        """Check if internet connection is available"""
        try:
            requests.get("https://api.binance.com", timeout=5)
            return True
        except requests.RequestException:
            return False

    def sell_asset(self, symbol, quantity):
        """Melakukan penjualan aset di Binance"""
        try:
            order = self.client.order_market_sell(
                symbol=symbol,
                quantity=quantity
            )
            self.logger.info(f"✅ Sell order placed: {order}")
            return order
        except BinanceAPIException as e:
            self.logger.error(f"Binance API Exception during sell: {e}")
        except BinanceOrderException as e:
            self.logger.error(f"Binance Order Exception during sell: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error during sell: {e}")

    def get_min_notional(self, symbol):
        """Ambil batas minimal notional trading dari Binance"""
        try:
            exchange_info = self.client.get_exchange_info()
            for s in exchange_info['symbols']:
                if s['symbol'] == symbol:
                    for f in s['filters']:
                        if f['filterType'] == 'MIN_NOTIONAL':
                            return float(f['minNotional'])
            return None
        except Exception as e:
            self.logger.error(f"Error getting min notional for {symbol}: {e}")
            return None

    def get_historical_klines(self, symbol, interval, start_time):
        try:
            klines = self.client.get_historical_klines(symbol, interval, start_str=start_time)
            if not klines:
                self.logger.error(f"Empty klines data received for {symbol}. Full response: {klines}")
            return klines
        except Exception as e:
            self.logger.error(f"Error fetching historical data for {symbol}: {e}")
            return []

    def initialize_state(self):
        """Initialize bot state and configuration"""
        self.db_lock = threading.Lock()
        self.app_status = {
            'running': True,
            'trade_thread': True,
            'status_thread': True,
            'cleanup_thread': True
        }
        self.error_counts = {symbol: 0 for symbol in SYMBOLS}
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

    def setup_database(self):
        """Initialize database and historical data"""
        setup_database()
        for symbol in SYMBOLS:
            self.update_historical_data(symbol)

    def update_historical_data(self, symbol, interval='1h'):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Buat tabel jika belum ada
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS historical_data (
                symbol TEXT,
                timestamp TEXT PRIMARY KEY,
                open_price REAL,
                high_price REAL,
                low_price REAL,
                close_price REAL,
                volume REAL
            )
        ''')

        # Ambil timestamp terakhir dari database
        cursor.execute("SELECT MAX(timestamp) FROM historical_data WHERE symbol = ?", (symbol,))
        last_record = cursor.fetchone()

        if last_record and last_record[0]:
            last_timestamp = datetime.strptime(last_record[0], '%Y-%m-%d %H:%M:%S')
            start_time = int(last_timestamp.timestamp() * 1000)
        else:
            start_time = int((datetime.now() - timedelta(days=7)).timestamp() * 1000)

        current_time = int(datetime.now().timestamp() * 1000)
        if start_time >= current_time:
            start_time = current_time - (7 * 24 * 60 * 60 * 1000)  # Default ke 7 hari lalu jika ada masalah

        # Ambil data dari Binance
        klines = self.get_historical_klines(symbol, interval, start_time)

        if not klines:
            self.logger.error(f"Skipping update for {symbol} due to empty klines response.")
            conn.close()
            return False

        try:
            for kline in klines:
                if len(kline) < 6:
                    self.logger.warning(f"Incomplete kline data for {symbol}: {kline}")
                    continue

                timestamp = datetime.fromtimestamp(kline[0] / 1000)
                cursor.execute('''
                    INSERT OR REPLACE INTO historical_data
                    (symbol, timestamp, open_price, high_price, low_price, close_price, volume)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    symbol,
                    timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                    float(kline[1]),
                    float(kline[2]),
                    float(kline[3]),
                    float(kline[4]),
                    float(kline[5])
                ))

            conn.commit()
            self.logger.info(f"Successfully updated historical data for {symbol}.")
            return True
        except Exception as e:
            self.logger.error(f"Error processing klines for {symbol}: {e}")
            return False
        finally:
            conn.close()

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

    def should_buy(self, symbol, current_price):
        """Determine whether to buy based on technical analysis"""
        try:
            conn = sqlite3.connect(self.db_path)
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
            prev = df.iloc[-2]

            # Volume analysis
            avg_volume = df['volume'].tail(10).mean()
            current_volume = df['volume'].iloc[-1]
            volume_condition = current_volume > (avg_volume * 1.2)

            # Enhanced buy conditions
            conditions = {
                'price_below_ma50': current_price < latest['MA_50'],
                'bullish_trend': latest['MA_50'] > latest['MA_200'],
                'oversold': latest['RSI'] < RSI_OVERSOLD,
                'volume_active': volume_condition,
                'price_near_bb_lower': current_price <= latest['BB_lower'] * 1.02,  # Within 2% of lower BB
                'macd_bullish': latest['MACD_hist'] > 0 and prev['MACD_hist'] < 0,  # MACD crossover
            }

            # Calculate confidence score (0-100)
            confidence_score = sum([
                1 if conditions['price_below_ma50'] else 0,
                2 if conditions['bullish_trend'] else 0,
                2 if conditions['oversold'] else 0,
                1 if conditions['volume_active'] else 0,
                2 if conditions['price_near_bb_lower'] else 0,
                2 if conditions['macd_bullish'] else 0,
            ]) * 10

            # Prepare the analysis results
            analysis_results = [
                {'condition': 'price_below_ma50', 'value': 'Price (48000.00) vs MA50 (48500.00)', 'met': True},
                {'condition': 'bullish_trend', 'value': 'MA50 (48500.00) vs MA200 (49000.00)', 'met': False},
                {'condition': 'oversold', 'value': 'RSI (32.50) vs Threshold (38.50)', 'met': True},
                {'condition': 'volume_active', 'value': 'Volume (1500.00) vs Avg (1200.00)', 'met': True},
                {'condition': 'price_near_bb_lower', 'value': 'Price (48000.00) vs BB Lower (47000.00)', 'met': False},
                {'condition': 'macd_bullish', 'value': 'MACD Hist: Current (0.000123) vs Prev (-0.000456)', 'met': True},
            ]

            confidence_score = 60  # Example confidence score
            conditions_met = sum(result['met'] for result in analysis_results)

            # Construct the message
            message = "<b>BTCUSDT Technical Analysis:</b>\n"
            for result in analysis_results:
                status = "✅" if result['met'] else "❌"
                message += f"{status} <b>{result['condition']}:</b> {result['value']}\n"
            message += f"<b>Confidence Score:</b> {confidence_score}%\n"
            message += f"<b>Conditions Met:</b> {conditions_met}/{len(analysis_results)}\n"
            # Debug: Print message before sending
            print("Sending message to Telegram:")
            print(message)

            # Send the analysis to Telegram
            response = send_telegram_message(message)
            if response:
                print("Message sent successfully:", response)
            else:
                print("Failed to send message.")
            # Send the analysis to Telegram
            send_telegram_message(message)
            # Require at least 4 conditions to be met and minimum 60% confidence
            return sum(conditions.values()) >= 4 and confidence_score >= 60

        except Exception as e:
            self.logger.error(f"Buy analysis failed for {symbol}: {e}")
            return False

    def get_highest_price(self, symbol):
        """Mengambil harga tertinggi dari database dalam 24 jam terakhir"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT MAX(close_price)
                FROM historical_data
                WHERE symbol = ?
                AND timestamp >= datetime('now', '-24 hours', 'localtime')
            """, (symbol,))
            result = cursor.fetchone()
            conn.close()

            if result and result[0]:
                return float(result[0])
            else:
                return None  # Tidak ada data

        except Exception as e:
            self.logger.error(f"Error getting highest price for {symbol}: {e}")
            return None

    def process_symbol_trade(self, symbol, usdt_per_symbol):
        """Process trading logic for a single symbol"""
        try:
            # Get market stats
            stats = get_24h_stats(symbol)
            if not stats:
                self.logger.error(f"{symbol}: Could not fetch market stats")
                return

            # Check volume requirements
            min_required_volume = MIN_24H_VOLUME.get(symbol, 100000)
            if stats['volume'] < min_required_volume:
                self.logger.info(f"{symbol}: Insufficient 24h volume (${stats['volume']:.2f} < ${min_required_volume:.2f})")
                return

            # Check market volatility
            volatility_limit = MARKET_VOLATILITY_LIMIT.get(symbol, 0.05) * 100  # Default 5% if not specified
            if abs(stats['price_change']) > volatility_limit:
                self.logger.info(f"{symbol}: Market too volatile ({abs(stats['price_change']):.1f}% > {volatility_limit:.1f}%)")
                return

            # Get current price with retries
            retries = MAX_API_RETRIES
            last_price = None
            while retries > 0:
                last_price = get_last_price(symbol)
                if last_price:
                    break
                self.logger.warning(f"Could not get price for {symbol}, retrying ({retries})")
                time.sleep(ERROR_SLEEP_TIME)
                retries -= 1

            if not last_price:
                self.logger.error(f"Failed to get price for {symbol}, skipping trade")
                return

            # Get balances
            balances = get_balances()
            if not balances:
                self.logger.error("Could not fetch balances")
                return

            asset = symbol.replace('USDT', '')
            asset_balance = float(balances.get(asset, {}).get('free', 0.0))
            usdt_balance = float(balances.get('USDT', {}).get('free', 0.0))

            # Check if we have too many positions
            active_positions = sum(1 for sym in SYMBOLS if float(balances.get(sym.replace('USDT', ''), {}).get('free', 0.0)) > 0)
            if active_positions >= MAX_POSITIONS and asset_balance == 0:
                self.logger.info(f"Maximum positions ({MAX_POSITIONS}) reached, skipping new trades")
                return

            # Calculate position size
            position_size, error = calculate_position_size(symbol, usdt_balance, last_price, stats['volume'])
            if error:
                self.logger.info(f"{symbol}: {error}")
                return

            if position_size > 0:
                if self.should_buy(symbol, last_price):
                    # Calculate quantity
                    quantity = position_size / last_price
                    step_size = get_symbol_step_size(symbol)
                    if step_size:
                        quantity = math.floor(quantity / step_size) * step_size

                    self.logger.info(f"{symbol}: Buying {quantity} units at {last_price}")
                    order = self.buy_asset_with_retry(symbol, quantity)

                    if order:
                        self.logger.info(f"Buy order successful: {order}")
                        save_transaction(symbol, 'BUY', quantity, last_price, quantity * last_price)

            # Handle selling logic
            elif asset_balance > 0:
                last_buy_price = get_last_buy_price(symbol)
                if last_buy_price:
                    should_sell, reason = handle_stop_loss(symbol, last_buy_price, last_price, stats['high'])

                    if should_sell:
                        self.logger.info(f"{symbol}: Selling due to {reason}")
                        order = self.sell_asset(symbol, asset_balance)

                        if order:
                            profit = (last_price - last_buy_price) * asset_balance
                            self.logger.info(f"Sell order successful: {order}")
                            save_transaction(symbol, 'SELL', asset_balance, last_price, asset_balance * last_price)
                            self._update_performance_metrics('SELL', last_buy_price, last_price, asset_balance)

            # Cek harga pasar dan volume
            current_price = get_last_price(symbol)  # Dapatkan harga pasar saat ini
            volume = stats['volume']  # Dapatkan volume perdagangan saat ini

            # Periksa apakah harga memenuhi syarat untuk pembelian
            if current_price < (self.buy_multiplier * last_price):
                send_telegram_message(f"Harga pasar {current_price} tidak memenuhi syarat untuk pembelian.")

            # Periksa apakah volume memenuhi syarat minimum
            if volume < (self.min_volume_multiplier * stats['volume']):
                send_telegram_message(f"Volume perdagangan {volume} tidak memenuhi syarat minimum.")

        except Exception as e:
            self.logger.error(f"Error processing trade for {symbol}: {e}")
            self.handle_symbol_error(symbol, e)

    def handle_symbol_error(self, symbol, error):
        """Handle errors for specific symbols"""
        self.error_counts[symbol] += 1
        if self.error_counts[symbol] >= self.MAX_ERRORS:
            self.logger.error(f"Disabling trading for {symbol} due to excessive errors")
            send_telegram_message(f"⚠️ Trading disabled for {symbol} due to excessive errors")

    def trade(self):
        """Main trading loop"""
        error_count = 0
        max_errors = 3
        error_sleep = 60  # Sleep 1 minute after error

        while self.app_status['running']:
            try:
                if not self.app_status['trade_thread']:
                    self.logger.info("Restarting trade thread...")
                    self.app_status['trade_thread'] = True
                    error_count = 0

                # Check internet connection first
                if not self._check_internet_connection():
                    self.logger.warning("No internet connection, waiting...")
                    time.sleep(error_sleep)
                    continue

                balances = get_balances()
                if not balances:
                    self.logger.warning("Could not fetch balances, skipping trade cycle")
                    time.sleep(error_sleep)
                    error_count += 1
                    if error_count >= max_errors:
                        self.logger.error("Trade thread: Too many balance fetch errors")
                        self.app_status['trade_thread'] = False
                    continue

                # Reset error count on successful balance fetch
                error_count = 0

                usdt_balance = float(balances.get('USDT', {}).get('free', 0.0))
                usdt_per_symbol = usdt_balance / len(SYMBOLS) if usdt_balance > 0 else 0

                active_symbols = [s for s in SYMBOLS if self.error_counts[s] < self.MAX_ERRORS]
                if not active_symbols:
                    self.logger.warning("No active symbols to trade, all have exceeded error threshold")
                    send_telegram_message("⚠️ Warning: All symbols have exceeded error threshold")
                    time.sleep(CACHE_LIFETIME)
                    continue

                for symbol in active_symbols:
                    try:
                        self.process_symbol_trade(symbol, usdt_per_symbol)
                    except Exception as e:
                        self.logger.error(f"Error processing {symbol}: {e}")
                        self.handle_symbol_error(symbol, e)
                        continue  # Continue with next symbol

            except Exception as e:
                self.logger.error(f"Critical error in trade function: {e}")
                error_count += 1
                if error_count >= max_errors:
                    self.logger.error("Trade thread: Too many consecutive errors")
                    self.app_status['trade_thread'] = False
                time.sleep(error_sleep)
                continue

            time.sleep(CACHE_LIFETIME)

    def cleanup_old_data(self):
        """Clean up historical data older than 24 hours"""
        try:
            conn = get_db_connection()
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

        while self.app_status['running']:
            try:
                if not self.app_status['cleanup_thread']:
                    self.logger.info("Restarting cleanup monitor thread...")
                    self.app_status['cleanup_thread'] = True
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
                    self.app_status['cleanup_thread'] = False
                    time.sleep(error_sleep)
                    continue

            except Exception as e:
                self.logger.error(f"Critical error in cleanup monitor: {e}")
                error_count += 1
                if error_count >= max_errors:
                    self.logger.error("Cleanup monitor: Too many consecutive errors")
                    self.app_status['cleanup_thread'] = False
                time.sleep(error_sleep)
                continue

            time.sleep(cleanup_interval)

    def check_app_status(self):
        """Monitor application status"""
        while self.app_status['running']:
            if not all(self.app_status.values()):
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
                self.app_status['running'] = False

            # Wait for threads
            while any(thread.is_alive() for thread in threads):
                time.sleep(1)

        except KeyboardInterrupt:
            self.logger.info("Shutting down gracefully...")
            self.app_status['running'] = False

            # Wait for threads to finish
            for thread in threads:
                thread.join(timeout=5.0)

        except Exception as e:
            self.logger.critical(f"Fatal error: {e}")
            self.app_status['running'] = False

        finally:
            self.cleanup()

    def cleanup(self):
        """Cleanup resources"""
        try:
            # Cancel any pending orders
            for symbol in SYMBOLS:
                try:
                    self.client.cancel_open_orders(symbol=symbol)
                except Exception:
                    pass

            self.logger.info("Cleanup completed")
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")

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
            usdt_per_symbol = usdt_balance / len(SYMBOLS)
            bot.logger.debug(f"Saldo USDT: {usdt_balance}, Alokasi per simbol: {usdt_per_symbol}")

            for symbol in SYMBOLS:
                bot.logger.info(f"Simulasi trade untuk {symbol} dengan alokasi {usdt_per_symbol} USDT")
                bot.process_symbol_trade(symbol, usdt_per_symbol)
            # Setelah simulasi selesai, hentikan bot
            bot.app_status['running'] = False
        else:
            bot.run()
    except Exception as e:
        logging.critical(f"Failed to start trading bot: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
