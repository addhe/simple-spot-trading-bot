import os
import time
import logging
import sqlite3
import threading
import math
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceOrderException
from src.send_telegram_message import send_telegram_message

# Membuat folder logs jika belum ada
log_directory = 'logs/bot'
if not os.path.exists(log_directory):
    os.makedirs(log_directory)

# Konfigurasi logging untuk menulis ke file di folder logs/bot
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
                    filename=os.path.join(log_directory, 'bot.log'), filemode='a')

# Mengambil variabel lingkungan dengan fallback default
API_KEY = os.getenv('API_KEY_SPOT_TESTNET_BINANCE', '')
API_SECRET = os.getenv('API_SECRET_SPOT_TESTNET_BINANCE', '')
BASE_URL = 'https://testnet.binance.vision/api'
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', '')
TELEGRAM_GROUP_ID = os.getenv('TELEGRAM_GROUP_ID', '')

if not API_KEY or not API_SECRET:
    logging.error("API Key dan Secret tidak ditemukan! Pastikan telah diatur di environment variables.")
    exit(1)

SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
INTERVAL = '1m'
CACHE_LIFETIME = 300
BUY_MULTIPLIER = 0.925
SELL_MULTIPLIER = 1.03
TOLERANCE = 0.01

# Inisialisasi klien Binance
client = Client(api_key=API_KEY, api_secret=API_SECRET, testnet=True)

# Inisialisasi koneksi database SQLite dengan per thread connection
def get_db_connection():
    conn = sqlite3.connect('table_transactions.db', check_same_thread=False)
    return conn

def setup_database():
    conn = get_db_connection()
    cursor = conn.cursor()
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
    conn.commit()
    conn.close()

setup_database()

def round_quantity(quantity, step_size):
    precision = int(abs(math.log10(step_size)))
    return round(math.floor(quantity / step_size) * step_size, precision)

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

def get_balances():
    try:
        balances = {b['asset']: float(b['free']) for b in client.get_account()['balances']}
        usdt_free = balances.get('USDT', 0.0)
        asset_balances = {sym.replace('USDT', ''): balances.get(sym.replace('USDT', ''), 0.0) for sym in SYMBOLS}
        return usdt_free, asset_balances
    except BinanceAPIException as e:
        logging.error(f"Gagal mendapatkan saldo: {e}")
        return 0.0, {}

def buy_asset(symbol, quantity):
    try:
        order = client.order_market_buy(
            symbol=symbol,
            quantity=quantity
        )
        logging.info(f"Beli {quantity} {symbol} pada harga {order['fills'][0]['price']}")
        send_telegram_message(f"Beli {quantity} {symbol} pada harga {order['fills'][0]['price']}")
        save_transaction(symbol, 'buy', quantity, float(order['fills'][0]['price']))
        return order
    except (BinanceAPIException, BinanceOrderException) as e:
        logging.error(f"Gagal membeli {symbol}: {e}")
        send_telegram_message(f"Gagal membeli {symbol}: {e}")
        return None

def sell_asset(symbol, quantity):
    try:
        order = client.order_market_sell(
            symbol=symbol,
            quantity=quantity
        )
        logging.info(f"Jual {quantity} {symbol} pada harga {order['fills'][0]['price']}")
        send_telegram_message(f"Jual {quantity} {symbol} pada harga {order['fills'][0]['price']}")
        save_transaction(symbol, 'sell', quantity, float(order['fills'][0]['price']))
        return order
    except (BinanceAPIException, BinanceOrderException) as e:
        logging.error(f"Gagal menjual {symbol}: {e}")
        send_telegram_message(f"Gagal menjual {symbol}: {e}")
        return None

def trade():
    logging.info("Memulai proses trading...")
    while True:
        usdt_free, asset_balances = get_balances()
        logging.info(f"Saldo USDT: {usdt_free}, Saldo aset: {asset_balances}")

        if usdt_free > 0:
            usdt_per_symbol = usdt_free / len(SYMBOLS)
        else:
            usdt_per_symbol = 0

        for symbol in SYMBOLS:
            last_price = get_last_price(symbol)
            logging.info(f"Harga terakhir untuk {symbol}: {last_price}")
            if last_price is None:
                continue

            asset = symbol.replace('USDT', '')
            asset_balance = asset_balances.get(asset, 0.0)
            logging.info(f"Saldo {asset}: {asset_balance}")

            if asset_balance == 0.0:
                quantity = usdt_per_symbol * BUY_MULTIPLIER / last_price
                if quantity > 0:
                    logging.info(f"Menyiapkan pembelian untuk {symbol} dengan jumlah {quantity}")
                    buy_asset(symbol, quantity)
            else:
                last_buy_price = get_last_buy_price(symbol)
                logging.info(f"Harga beli terakhir untuk {symbol}: {last_buy_price}")
                if last_buy_price and last_price >= last_buy_price * SELL_MULTIPLIER:
                    logging.info(f"Menyiapkan penjualan untuk {symbol} dengan jumlah {asset_balance}")
                    sell_asset(symbol, asset_balance)

        time.sleep(CACHE_LIFETIME)


def main():
    trade_thread = threading.Thread(target=trade, daemon=True)
    trade_thread.start()
    trade_thread.join()

if __name__ == "__main__":
    main()
