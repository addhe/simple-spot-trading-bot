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
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceOrderException

# Import local modules
from src.get_balances import get_balances
from src.get_db_connection import get_db_connection
from src.get_last_buy_price import get_last_buy_price
from src.get_last_price import get_last_price
from src.save_historical_data import save_historical_data
from src.send_asset_status import send_asset_status
from src.send_telegram_message import send_telegram_message
from src.status_monitor import status_monitor
from src.setup_database import setup_database
from src.save_transaction import save_transaction
from src.get_symbol_step_size import get_symbol_step_size
from src._validate_kline_data import _validate_kline_data
from src._calculate_rsi import _calculate_rsi
from src._perform_extended_analysis import _perform_extended_analysis
from src.logger import setup_logging

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
    MAX_INVESTMENT_PER_TRADE
)

# Jika parameter STOP_LOSS_PERCENTAGE belum ada di config, tetapkan default di sini:
try:
    from config.settings import STOP_LOSS_PERCENTAGE
except ImportError:
    STOP_LOSS_PERCENTAGE = 0.02  # contoh: 2%

class TradingBot:
    def __init__(self):
        # Pastikan db_path sudah didefinisikan sebelum dipakai fungsi lain
        self.db_path = 'table_transactions.db'
        self.logger = setup_logging()
        self.initialize_state()
        self.initialize_client()
        self.setup_database()

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
            self.client = Client(api_key=API_KEY, api_secret=API_SECRET, testnet=True)
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

            # Calculate technical indicators
            df['MA_50'] = df['close_price'].rolling(window=50).mean()
            df['MA_200'] = df['close_price'].rolling(window=200).mean()
            df['RSI'] = _calculate_rsi(df['close_price'])

            latest = df.iloc[-1]

            # Volume analysis
            avg_volume = df['volume'].tail(10).mean()
            current_volume = df['volume'].iloc[-1]
            volume_condition = current_volume > (avg_volume * 1.2)

            # Buy conditions
            conditions = {
                'price_below_ma50': current_price < latest['MA_50'],
                'bullish_trend': latest['MA_50'] > latest['MA_200'],
                'oversold': latest['RSI'] < RSI_OVERSOLD,
                'volume_active': volume_condition
            }
            self.logger.debug(f"{symbol}: current_price={current_price}, MA_50={latest['MA_50']}, MA_200={latest['MA_200']}, RSI={latest['RSI']}")
            self.logger.debug(f"{symbol} Buy Analysis: {conditions}")
            send_telegram_message(f"{symbol} Buy Analysis:\n" +
                                  "\n".join([f"- {k}: {v}" for k, v in conditions.items()]))

            if not all(conditions.values()):
                self.logger.info(f"{symbol}: Tidak membeli karena kondisi tidak terpenuhi - {conditions}")

            return all(conditions.values())

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
            retries = 3
            last_price = None
            while retries > 0:
                last_price = get_last_price(symbol)
                if last_price:
                    break
                self.logger.warning(f"Tidak bisa mendapatkan harga {symbol}, mencoba lagi ({retries})")
                time.sleep(2)
                retries -= 1
            if not last_price:
                self.logger.error(f"Gagal mendapatkan harga terakhir untuk {symbol}, melewati trade")
                return

            # Ambil saldo aset yang tersedia
            balances = get_balances()
            asset = symbol.replace('USDT', '')
            asset_balance = float(balances.get(asset, {}).get('free', 0.0))
            usdt_balance = float(balances.get('USDT', {}).get('free', 0.0))

            # Hitung batas investasi per perdagangan
            total_portfolio_value = usdt_balance + sum(
                float(balances[sym.replace("USDT", "")]["free"]) * get_last_price(sym)
                for sym in SYMBOLS if sym.replace("USDT", "") in balances
            )
            max_trade_value = total_portfolio_value * MAX_INVESTMENT_PER_TRADE

            if usdt_per_symbol > max_trade_value:
                self.logger.info(f"{symbol}: Menyesuaikan investasi dari {usdt_per_symbol} ke {max_trade_value}")
                usdt_per_symbol = max_trade_value

            # 🚀 **Kondisi Pembelian**
            if asset_balance == 0 and usdt_per_symbol > 0:
                if self.should_buy(symbol, last_price):
                    # Hitung jumlah pembelian
                    quantity = (usdt_per_symbol * BUY_MULTIPLIER) / last_price
                    step_size = get_symbol_step_size(symbol)
                    if step_size:
                        quantity = math.floor(quantity / step_size) * step_size

                    # Pastikan order memenuhi batas minimal perdagangan
                    min_notional = self.get_min_notional(symbol)
                    if min_notional and (quantity * last_price) < min_notional:
                        self.logger.warning(f"{symbol}: Order terlalu kecil (Min Notional: {min_notional}, Order: {quantity * last_price})")
                        return  # Jangan lanjutkan order

                    if min_notional and (quantity * last_price) >= min_notional:
                        self.logger.info(f"{symbol}: Membeli {quantity} unit pada harga {last_price}")
                        self.buy_asset(symbol, quantity)
                    else:
                        self.logger.warning(f"{symbol}: Order tidak memenuhi batas minimal perdagangan")

            # 🚨 **Kondisi Penjualan**
            elif asset_balance > 0:
                last_buy_price = get_last_buy_price(symbol)
                if last_buy_price:
                    profit_percentage = ((last_price - last_buy_price) / last_buy_price) * 100
                    highest_price = self.get_highest_price(symbol)

                    # **Trailing Stop: Jual jika turun dari harga tertinggi**
                    if TRAILING_STOP and highest_price and (last_price < highest_price * (1 - TRAILING_STOP)):
                        self.logger.warning(f"{symbol}: Harga turun dari {highest_price} ke {last_price}, menjual aset")
                        self.sell_asset(symbol, asset_balance)
                        return

                    # **Take Profit: Jual jika harga naik >= SELL_MULTIPLIER**
                    if last_price >= last_buy_price * SELL_MULTIPLIER:
                        self.logger.info(f"{symbol}: Keuntungan {profit_percentage:.2f}%, menjual aset")
                        self.sell_asset(symbol, asset_balance)
                        return

                    # **Stop Loss: Jual jika rugi lebih dari STOP_LOSS_PERCENTAGE**
                    if profit_percentage <= -STOP_LOSS_PERCENTAGE * 100:
                        self.logger.error(f"{symbol}: Kerugian {profit_percentage:.2f}%, menjual aset untuk cut loss")
                        self.sell_asset(symbol, asset_balance)
                        return

        except Exception as e:
            self.logger.error(f"⚠️ Error processing trade for {symbol}: {e}")
            self.handle_symbol_error(symbol, e)

    def handle_symbol_error(self, symbol, error):
        """Handle errors for specific symbols"""
        self.error_counts[symbol] += 1
        if self.error_counts[symbol] >= self.MAX_ERRORS:
            self.logger.error(f"Disabling trading for {symbol} due to excessive errors")
            send_telegram_message(f"⚠️ Trading disabled for {symbol} due to excessive errors")

    def trade(self):
        """Main trading loop"""
        while self.app_status['running'] and self.app_status['trade_thread']:
            try:
                balances = get_balances()
                if not balances:
                    self.logger.warning("Tidak mendapatkan saldo, melewati siklus trade")
                    time.sleep(CACHE_LIFETIME)
                    continue

                usdt_balance = float(balances.get('USDT', {}).get('free', 0.0))
                usdt_per_symbol = usdt_balance / len(SYMBOLS) if usdt_balance > 0 else 0

                for symbol in SYMBOLS:
                    if self.error_counts[symbol] < self.MAX_ERRORS:
                        self.process_symbol_trade(symbol, usdt_per_symbol)

            except Exception as e:
                self.logger.error(f"Critical error in trade function: {e}")
                self.app_status['trade_thread'] = False
                break

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
        while self.app_status['running'] and self.app_status['cleanup_thread']:
            try:
                self.cleanup_old_data()
            except Exception as e:
                self.logger.error(f"Error in cleanup monitor: {e}")
                self.app_status['cleanup_thread'] = False
            time.sleep(3600)

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
                threading.Thread(target=status_monitor, daemon=True),
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
