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
from src.send_telegram_message import send_telegram_message

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
    'trade_thread': True,
    'status_thread': True,
    'cleanup_thread': True
}

def save_historical_data(symbol, klines):
    """Enhanced historical data saving with data validation"""
    try:
        conn = sqlite3.connect('table_transactions.db', check_same_thread=False)
        cursor = conn.cursor()

        # Data validation
        validated_klines = [
            kline for kline in klines
            if _validate_kline_data(kline)
        ]

        for kline in validated_klines:
            timestamp = datetime.fromtimestamp(kline[0]/1000).strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute('''
                INSERT OR REPLACE INTO historical_data
                (symbol, timestamp, open_price, high_price, low_price, close_price, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                symbol,
                timestamp,
                float(kline[1]),  # open
                float(kline[2]),  # high
                float(kline[3]),  # low
                float(kline[4]),  # close
                float(kline[5])   # volume
            ))

        conn.commit()
        conn.close()
        logging.info(f"Saved {len(validated_klines)} validated historical data points for {symbol}")

    except sqlite3.Error as e:
        logging.error(f"Failed to save historical data: {e}")

def _validate_kline_data(kline):
    """Validate individual kline data point"""
    try:
        # Check data types and ranges
        float_values = [
            float(kline[1]),  # open
            float(kline[2]),  # high
            float(kline[3]),  # low
            float(kline[4]),  # close
            float(kline[5])   # volume
        ]

        # Validate price and volume
        if (
            float_values[1] >= float_values[3] and  # high >= close
            float_values[2] <= float_values[3] and  # low <= close
            float_values[5] >= 0  # volume non-negative
        ):
            return True

    except (ValueError, TypeError):
        pass

    return False

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

def get_db_connection():
    conn = sqlite3.connect('table_transactions.db', check_same_thread=False)
    return conn

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

def get_balances():
    """
    Get account balances from Binance
    Returns: dict with 'USDT' and other asset balances
    """
    try:
        account = client.get_account()
        balances = {}

        for balance in account['balances']:
            asset = balance['asset']
            free = float(balance['free'])
            locked = float(balance['locked'])

            if free > 0 or locked > 0:  # Only store assets with balance
                balances[asset] = {
                    'free': free,
                    'locked': locked,
                    'total': free + locked
                }
        return balances
    except BinanceAPIException as e:
        logging.error(f"Failed to get balances: {e}")
        return {}

def send_asset_status():
    """Send current asset status to Telegram."""
    try:
        balances = get_balances()
        usdt_free = balances.get('USDT', {}).get('free', 0.0)

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        status_message = f"🔄 Status Aset ({current_time})\n\n"
        status_message += f"💵 USDT: {usdt_free:.2f}\n\n"

        total_value_usdt = usdt_free

        for symbol in SYMBOLS:
            asset = symbol.replace('USDT', '')
            balance = balances.get(asset, {}).get('free', 0.0)
            last_price = get_last_price(symbol)

            if last_price:
                value_usdt = balance * last_price
                total_value_usdt += value_usdt

                last_buy_price = get_last_buy_price(symbol)
                profit_loss = ""
                if last_buy_price and balance > 0:
                    pl_percent = ((last_price - last_buy_price) / last_buy_price) * 100
                    profit_loss = f"(P/L: {pl_percent:.2f}%)"

                status_message += f"🪙 {asset}:\n"
                status_message += f"   Jumlah: {balance:.8f}\n"
                status_message += f"   Harga: {last_price:.2f} USDT\n"
                status_message += f"   Nilai: {value_usdt:.2f} USDT {profit_loss}\n\n"

        status_message += f"💰 Total Nilai Portfolio: {total_value_usdt:.2f} USDT"

        send_telegram_message(status_message)
        logging.info("Status aset berhasil dikirim ke Telegram")

    except Exception as e:
        logging.error(f"Gagal mengirim status aset: {e}")

def trade():
    while True:
        try:
            balances = get_balances()
            usdt_balance = balances.get('USDT', {}).get('free', 0.0)

            if usdt_balance > 0:
                usdt_per_symbol = usdt_balance / len(SYMBOLS)
            else:
                usdt_per_symbol = 0

            for symbol in SYMBOLS:
                last_price = get_last_price(symbol)
                if last_price is None:
                    continue

                asset = symbol.replace('USDT', '')
                asset_balance = balances.get(asset, {}).get('free', 0.0)

                if asset_balance == 0 and usdt_per_symbol > 0:
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

                elif asset_balance > 0:
                    last_buy_price = get_last_buy_price(symbol)
                    if last_buy_price and last_price >= last_buy_price * SELL_MULTIPLIER:
                        sell_asset(symbol, asset_balance)

        except Exception as e:
            logging.error(f"Error dalam fungsi trade: {e}")
            app_status['trade_thread'] = False

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

def get_last_buy_price(symbol):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT price FROM transactions
            WHERE symbol = ? AND type = 'buy'
            ORDER BY timestamp DESC
            LIMIT 1
        ''', (symbol,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None
    except sqlite3.Error as e:
        logging.error(f"Gagal mendapatkan harga pembelian terakhir: {e}")
        return None

def get_last_price(symbol):
    try:
        ticker = client.get_symbol_ticker(symbol=symbol)
        return float(ticker['price'])
    except BinanceAPIException as e:
        logging.error(f"Gagal mendapatkan harga terakhir untuk {symbol}: {e}")
        return None

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
    while True:
        cleanup_old_data()
        time.sleep(3600)  # Bersihkan setiap jam

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

def status_monitor():
    """Thread terpisah untuk memantau dan mengirim status setiap jam."""
    while True:
        send_asset_status()
        time.sleep(STATUS_INTERVAL)

def check_app_status():
    """Memeriksa status aplikasi dan mengirim notifikasi jika ada masalah."""
    while True:
        if not all(app_status.values()):
            logging.error("Salah satu thread tidak aktif! Memeriksa kembali...")
            send_telegram_message("⚠️ Peringatan: Salah satu thread tidak aktif! Silakan periksa aplikasi.")
        time.sleep(600)  # Cek setiap 10 menit

def cleanup_monitor():
    """Thread untuk membersihkan data lama secara periodik"""
    while True:
        cleanup_old_data()
        time.sleep(3600)  # Bersihkan setiap jam

def main():
    setup_database()
    for symbol in SYMBOLS:
        update_historical_data(symbol)

    # Memulai thread untuk monitoring status
    status_thread = threading.Thread(target=status_monitor, daemon=True)
    status_thread.start()

    # Memulai thread untuk trading
    trade_thread = threading.Thread(target=trade, daemon=True)
    trade_thread.start()

    # Memulai thread untuk cleanup
    cleanup_thread = threading.Thread(target=cleanup_monitor, daemon=True)
    cleanup_thread.start()

    # Memulai thread untuk pengecekan status aplikasi
    status_check_thread = threading.Thread(target=check_app_status, daemon=True)
    status_check_thread.start()

    # Menunggu kedua thread selesai
    status_thread.join()
    trade_thread.join()
    cleanup_thread.join()
    status_check_thread.join()

if __name__ == "__main__":
    main()
