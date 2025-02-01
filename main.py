import os
import time
import logging
import sqlite3
import threading
import math
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceOrderException

from src.get_balances import get_balances
from src.get_db_connection import get_db_connection
from src.get_last_buy_price import get_last_buy_price
from src.get_last_price import get_last_price
from src.save_historical_data import save_historical_data
from src.send_asset_status import send_asset_status
from src.send_telegram_message import send_telegram_message
from src.status_monitor import status_monitor

from src._validate_kline_data import _validate_kline_data

# Database connection lock
db_lock = threading.Lock()

# Membuat folder logs jika belum ada
log_directory = 'logs/bot'
if not os.path.exists(log_directory):
    os.makedirs(log_directory)

# Konfigurasi logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
                    filename=os.path.join(log_directory, 'bot.log'), filemode='a')

# Mengambil variabel lingkungan
API_KEY = os.getenv('API_KEY_SPOT_TESTNET_BINANCE', '')
API_SECRET = os.getenv('API_SECRET_SPOT_TESTNET_BINANCE', '')
BASE_URL = 'https://testnet.binance.vision/api'
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', '')
TELEGRAM_GROUP_ID = os.getenv('TELEGRAM_GROUP_ID', '')

if not API_KEY or not API_SECRET:
    logging.error("API Key dan Secret tidak ditemukan! Pastikan telah diatur di environment variables.")
    exit(1)

# Konfigurasi trading
SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
INTERVAL = '1m'
CACHE_LIFETIME = 300  # 5 menit
BUY_MULTIPLIER = 0.925
SELL_MULTIPLIER = 1.011
TOLERANCE = 0.01
STATUS_INTERVAL = 3600  # 1 jam dalam detik

# Inisialisasi klien Binance
client = Client(api_key=API_KEY, api_secret=API_SECRET, testnet=True)

# Status aplikasi
app_status = {
    'running': True,
    'trade_thread': True,
    'status_thread': True,
    'cleanup_thread': True
}

def _perform_extended_analysis(symbol):
    """Perform extended analysis on historical data"""
    try:
        with db_lock:
            conn = get_db_connection()
            df = pd.read_sql_query(f'''
                SELECT timestamp, close_price, volume
                FROM historical_data
                WHERE symbol = '{symbol}'
                ORDER BY timestamp DESC
                LIMIT 500
            ''', conn)
            conn.close()

        if len(df) < 50:
            return

        # Calculate additional technical indicators
        df['EMA_20'] = df['close_price'].ewm(span=20).mean()
        df['STD_20'] = df['close_price'].rolling(window=20).std()

        # Save analysis results if needed
        logging.info(f"Extended analysis completed for {symbol}")

    except Exception as e:
        logging.error(f"Extended analysis failed for {symbol}: {e}")


def update_historical_data(symbol, client, extended_analysis=True):
    """Advanced historical data update with multi-timeframe support"""
    try:
        conn = sqlite3.connect('table_transactions.db', check_same_thread=False)
        cursor = conn.cursor()

        # Fetch last recorded timestamp
        cursor.execute('''
            SELECT timestamp FROM historical_data
            WHERE symbol = ? ORDER BY timestamp DESC LIMIT 1
        ''', (symbol,))
        last_record = cursor.fetchone()

        # Determine start time for data retrieval
        if last_record:
            last_timestamp = datetime.strptime(last_record[0], '%Y-%m-%d %H:%M:%S')
            start_time = int(last_timestamp.timestamp() * 1000)
        else:
            # If no previous data, fetch last 7 days
            start_time = int((datetime.now() - timedelta(days=7)).timestamp() * 1000)

        # Multi-timeframe intervals
        intervals = [
            client.KLINE_INTERVAL_1MINUTE,
            client.KLINE_INTERVAL_15MINUTE,
            client.KLINE_INTERVAL_1HOUR
        ]

        for interval in intervals:
            klines = client.get_historical_klines(
                symbol,
                interval,
                start_str=start_time
            )
            save_historical_data(symbol, klines)

        conn.close()

        if extended_analysis:
            _perform_extended_analysis(symbol)

        return True

    except Exception as e:
        logging.error(f"Failed to update historical data for {symbol}: {e}")
        return False

def should_buy(symbol, current_price, advanced_indicators=True):
    """Advanced buying decision with multiple technical indicators"""
    try:
        # Retrieve historical data
        conn = sqlite3.connect('table_transactions.db', check_same_thread=False)
        df = pd.read_sql_query(f'''
            SELECT timestamp, close_price, volume
            FROM historical_data
            WHERE symbol = '{symbol}'
            ORDER BY timestamp DESC
            LIMIT 500
        ''', conn)
        conn.close()

        if len(df) < 50:
            logging.warning(f"Insufficient data for {symbol}")
            return False

        # Convert timestamp
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df.set_index('timestamp', inplace=True)

        # Technical Indicators
        df['MA_50'] = df['close_price'].rolling(window=50).mean()
        df['MA_200'] = df['close_price'].rolling(window=200).mean()
        df['RSI'] = _calculate_rsi(df['close_price'])

        latest = df.iloc[-1]

        # Advanced Buy Conditions
        buy_conditions = [
            current_price < latest['MA_50'],  # Price below short-term moving average
            latest['MA_50'] > latest['MA_200'],  # Short-term trend is bullish
            latest['RSI'] < 30,  # Oversold condition
            current_price < latest['MA_200'] * 0.95  # Significant discount
        ]

        # Volume confirmation
        volume_spike = df['volume'].tail(10).mean() * 1.5 < df['volume'].iloc[-1]

        logging.info(f"""
        {symbol} Buy Analysis:
        Current Price: {current_price}
        50-Day MA: {latest['MA_50']}
        200-Day MA: {latest['MA_200']}
        RSI: {latest['RSI']}
        Volume Spike: {volume_spike}
        Buy Signals Met: {sum(buy_conditions)}/4
        """)

        return sum(buy_conditions) >= 3 and volume_spike

    except Exception as e:
        logging.error(f"Buy condition analysis failed for {symbol}: {e}")
        return False

def _calculate_rsi(prices, periods=14):
    """Calculate Relative Strength Index"""
    delta = prices.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(window=periods).mean()
    avg_loss = loss.rolling(window=periods).mean()

    relative_strength = avg_gain / avg_loss
    rsi = 100.0 - (100.0 / (1.0 + relative_strength))

    return rsi

def execute_db_operation(operation, params=None):
    """Execute database operation with proper locking"""
    with db_lock:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            if params:
                cursor.execute(operation, params)
            else:
                cursor.execute(operation)
            conn.commit()
            result = cursor.fetchall() if cursor.description else None
            return result
        except sqlite3.Error as e:
            logging.error(f"Database error: {e}")
            conn.rollback()
            raise
        finally:
            conn.close()

def setup_database():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Tabel transaksi yang sudah ada
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT,
        symbol TEXT,
        type TEXT,
        quantity REAL,
        price REAL
    )
    ''')

    # Tabel baru untuk historical data
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS historical_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT,
        timestamp TEXT,
        open_price REAL,
        high_price REAL,
        low_price REAL,
        close_price REAL,
        volume REAL,
        UNIQUE(symbol, timestamp)
    )
    ''')

    # Index untuk mempercepat query
    cursor.execute('''
    CREATE INDEX IF NOT EXISTS idx_historical_symbol_timestamp
    ON historical_data(symbol, timestamp)
    ''')

    conn.commit()
    conn.close()

def process_symbol_trade(symbol, usdt_per_symbol):
    """Process trading logic for a single symbol"""
    last_price = get_last_price(symbol)
    if last_price is None:
        return

    balances = get_balances()
    asset = symbol.replace('USDT', '')
    asset_balance = balances.get(asset, {}).get('free', 0.0)

    if asset_balance == 0 and usdt_per_symbol > 0:
        handle_buy_scenario(symbol, last_price, usdt_per_symbol)
    elif asset_balance > 0:
        handle_sell_scenario(symbol, last_price, asset_balance)

def trade():
    """Main trading function with improved error handling"""
    while app_status['running'] and app_status['trade_thread']:
        try:
            balances = get_balances()
            if not balances:
                logging.error("Failed to get balances, skipping trade cycle")
                time.sleep(CACHE_LIFETIME)
                continue

            usdt_balance = balances.get('USDT', {}).get('free', 0.0)
            usdt_per_symbol = usdt_balance / len(SYMBOLS) if usdt_balance > 0 else 0

            for symbol in SYMBOLS:
                try:
                    process_symbol_trade(symbol, usdt_per_symbol)
                except Exception as e:
                    logging.error(f"Error processing trade for {symbol}: {e}")
                    continue

        except Exception as e:
            logging.error(f"Critical error in trade function: {e}")
            app_status['trade_thread'] = False
            break

        time.sleep(CACHE_LIFETIME)

def get_cached_historical_data(symbol, minutes=60):
    """Mengambil data historis dari cache"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT timestamp, close_price, volume
            FROM historical_data
            WHERE symbol = ?
            AND timestamp >= datetime('now', ?, 'localtime')
            ORDER BY timestamp ASC
        ''', (symbol, f'-{minutes} minutes'))

        results = cursor.fetchall()
        conn.close()

        return results
    except sqlite3.Error as e:
        logging.error(f"Gagal mengambil data historis dari cache: {e}")
        return []



def get_symbol_step_size(symbol):
    try:
        info = client.get_symbol_info(symbol)
        for f in info['filters']:
            if f['filterType'] == 'LOT_SIZE':
                return float(f['stepSize'])
    except BinanceAPIException as e:
        logging.error(f"Gagal mendapatkan stepSize untuk {symbol}: {e}")
    return None

def round_quantity(quantity, step_size):
    return math.floor(quantity / step_size) * step_size

def save_transaction(symbol, type, quantity, price):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO transactions (timestamp, symbol, type, quantity, price)
            VALUES (strftime('%Y-%m-%d %H:%M:%S', 'now'), ?, ?, ?, ?)
        ''', (symbol, type, quantity, price))
        conn.commit()
        conn.close()
        logging.info(f"Transaksi {type} {quantity} {symbol} pada harga {price} disimpan ke database")
    except sqlite3.Error as e:
        logging.error(f"Gagal menyimpan transaksi ke database: {e}")

def cleanup_old_data():
    """Membersihkan data historis yang lebih dari 24 jam"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            DELETE FROM historical_data
            WHERE timestamp < datetime('now', '-24 hours', 'localtime')
        ''')
        conn.commit()
        conn.close()
        logging.info("Berhasil membersihkan data historis lama")
    except sqlite3.Error as e:
        logging.error(f"Gagal membersihkan data historis: {e}")

def cleanup_monitor():
    """Thread untuk membersihkan data lama secara periodik"""
    while app_status['running'] and app_status['cleanup_thread']:
        try:
            cleanup_old_data()
        except Exception as e:
            logging.error(f"Error in cleanup monitor: {e}")
            app_status['cleanup_thread'] = False
        time.sleep(3600)

def get_min_notional(symbol):
    """Mendapatkan minimum notional value yang diizinkan untuk trading"""
    try:
        info = client.get_symbol_info(symbol)
        for f in info['filters']:
            if f['filterType'] == 'MIN_NOTIONAL':
                return float(f['minNotional'])
    except BinanceAPIException as e:
        logging.error(f"Gagal mendapatkan min notional untuk {symbol}: {e}")
    return None

def check_sufficient_balance(symbol, quantity, price, side='BUY'):
    """
    Memeriksa apakah balance mencukupi untuk melakukan order
    Returns: (bool, str) - (is_sufficient, error_message)
    """
    balances = get_balances()

    if side == 'BUY':
        required_usdt = quantity * price
        available_usdt = balances.get('USDT', {}).get('free', 0)

        if available_usdt < required_usdt:
            return False, f"Insufficient USDT balance. Required: {required_usdt}, Available: {available_usdt}"

    else:  # SELL
        asset = symbol.replace('USDT', '')
        available_asset = balances.get(asset, {}).get('free', 0)

        if available_asset < quantity:
            return False, f"Insufficient {asset} balance. Required: {quantity}, Available: {available_asset}"

    return True, None

def buy_asset(symbol, quantity):
    try:
        current_price = float(client.get_symbol_ticker(symbol=symbol)['price'])

        # Periksa minimum notional
        min_notional = get_min_notional(symbol)
        if min_notional and (quantity * current_price) < min_notional:
            logging.error(f"Order {symbol} terlalu kecil. Minimum notional: {min_notional} USDT")
            return None

        # Periksa balance sebelum order
        is_sufficient, error_msg = check_sufficient_balance(symbol, quantity, current_price, 'BUY')
        if not is_sufficient:
            logging.error(f"Gagal membeli {symbol}: {error_msg}")
            send_telegram_message(f"Gagal membeli {symbol}: {error_msg}")
            return None

        order = client.order_market_buy(
            symbol=symbol,
            quantity=quantity
        )

        actual_price = float(order['fills'][0]['price'])
        actual_quantity = float(order['executedQty'])

        logging.info(f"Beli {actual_quantity} {symbol} pada harga {actual_price}")
        send_telegram_message(f"Beli {actual_quantity} {symbol} pada harga {actual_price}")
        save_transaction(symbol, 'buy', actual_quantity, actual_price)
        return order

    except (BinanceAPIException, BinanceOrderException) as e:
        logging.error(f"Gagal membeli {symbol}: {e}")
        send_telegram_message(f"Gagal membeli {symbol}: {e}")
        return None

def sell_asset(symbol, quantity):
    try:
        current_price = float(client.get_symbol_ticker(symbol=symbol)['price'])

        # Periksa minimum notional
        min_notional = get_min_notional(symbol)
        if min_notional and (quantity * current_price) < min_notional:
            logging.error(f"Order {symbol} terlalu kecil. Minimum notional: {min_notional} USDT")
            return None

        # Periksa balance sebelum order
        is_sufficient, error_msg = check_sufficient_balance(symbol, quantity, current_price, 'SELL')
        if not is_sufficient:
            logging.error(f"Gagal menjual {symbol}: {error_msg}")
            send_telegram_message(f"Gagal menjual {symbol}: {error_msg}")
            return None

        order = client.order_market_sell(
            symbol=symbol,
            quantity=quantity
        )

        actual_price = float(order['fills'][0]['price'])
        actual_quantity = float(order['executedQty'])

        logging.info(f"Jual {actual_quantity} {symbol} pada harga {actual_price}")
        send_telegram_message(f"Jual {actual_quantity} {symbol} pada harga {actual_price}")
        save_transaction(symbol, 'sell', actual_quantity, actual_price)
        return order

    except (BinanceAPIException, BinanceOrderException) as e:
        logging.error(f"Gagal menjual {symbol}: {e}")
        send_telegram_message(f"Gagal menjual {symbol}: {e}")
        return None

def check_app_status():
    """Memeriksa status aplikasi dan mengirim notifikasi jika ada masalah."""
    while True:
        if not all(app_status.values()):
            logging.error("Salah satu thread tidak aktif! Memeriksa kembali...")
            send_telegram_message("⚠️ Peringatan: Salah satu thread tidak aktif! Silakan periksa aplikasi.")
        time.sleep(600)  # Cek setiap 10 menit

def handle_buy_scenario(symbol, last_price, usdt_per_symbol):
    """Handle buying scenario for a symbol"""
    if should_buy(symbol, last_price):
        # Calculate quantity based on available USDT
        quantity = (usdt_per_symbol * BUY_MULTIPLIER) / last_price
        step_size = get_symbol_step_size(symbol)
        if step_size:
            quantity = round_quantity(quantity, step_size)

        # Check minimum notional
        min_notional = get_min_notional(symbol)
        if min_notional and (quantity * last_price) >= min_notional:
            buy_asset(symbol, quantity)
        else:
            logging.info(f"Skipping buy {symbol}: Order size too small")
    else:
        logging.info(f"Kondisi membeli belum tepat untuk {symbol}")

def handle_sell_scenario(symbol, last_price, asset_balance):
    """Handle selling scenario for a symbol"""
    last_buy_price = get_last_buy_price(symbol)
    if last_buy_price and last_price >= last_buy_price * SELL_MULTIPLIER:
        sell_asset(symbol, asset_balance)

def main():
    """Enhanced main function with proper thread management"""
    setup_database()

    try:
        # Initialize historical data
        for symbol in SYMBOLS:
            update_historical_data(symbol, client)  # Menambahkan parameter client

        threads = [
            threading.Thread(target=status_monitor, daemon=True),
            threading.Thread(target=trade, daemon=True),
            threading.Thread(target=cleanup_monitor, daemon=True),
            threading.Thread(target=check_app_status, daemon=True)
        ]

        # Start all threads
        for thread in threads:
            thread.start()

        # Wait for threads while allowing keyboard interrupt
        try:
            while any(thread.is_alive() for thread in threads):
                time.sleep(1)
        except KeyboardInterrupt:
            logging.info("Shutting down gracefully...")
            app_status['running'] = False

            # Wait for threads to finish
            for thread in threads:
                thread.join(timeout=5.0)

    except Exception as e:
        logging.critical(f"Critical error in main: {e}")
        app_status['running'] = False
    finally:
        logging.info("Application shutdown complete")

if __name__ == "__main__":
    main()
