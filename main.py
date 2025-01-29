import os
import time
import logging
import sqlite3
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceOrderException

# Konfigurasi logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Mengambil variabel lingkungan
API_KEY = os.environ['API_KEY_SPOT_TESTNET_BINANCE']
API_SECRET = os.environ['API_SECRET_SPOT_TESTNET_BINANCE']
BASE_URL = 'https://testnet.binance.vision/api'
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_GROUP_ID = os.getenv('TELEGRAM_GROUP_ID')
SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
INTERVAL = '1m'
CACHE_LIFETIME = 60  # 5 menit
MAX_RETRIES = 5
RETRY_BACKOFF = 1  # 1 detik
BUY_MULTIPLIER = 0.925
SELL_MULTIPLIER = 1.03
TOLERANCE = 0.01

# Inisialisasi klien Binance
client = Client(api_key=API_KEY, api_secret=API_SECRET, testnet=True)

# Inisialisasi koneksi database SQLite
DB_NAME = 'table_transactions.db'
conn = sqlite3.connect(DB_NAME, check_same_thread=False)
cursor = conn.cursor()

# Membuat tabel transactions jika belum ada
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

# Fungsi untuk mengirim pesan ke Telegram
def send_telegram_message(message):
    import requests
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_GROUP_ID,
        'text': message
    }
    response = requests.post(url, json=payload)
    return response.json()

# Fungsi untuk membeli aset
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

# Fungsi untuk menjual aset
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

# Fungsi untuk mendapatkan harga terakhir
def get_last_price(symbol):
    try:
        ticker = client.get_symbol_ticker(symbol=symbol)
        return float(ticker['price'])
    except BinanceAPIException as e:
        logging.error(f"Gagal mendapatkan harga terakhir untuk {symbol}: {e}")
        return None

# Fungsi untuk mendapatkan saldo
def get_balances():
    try:
        balances = client.get_account()['balances']
        usdt_balance = next((item for item in balances if item['asset'] == 'USDT'), None)
        usdt_free = float(usdt_balance['free']) if usdt_balance else 0.0
        asset_balances = {item['asset']: float(item['free']) for item in balances if item['asset'] in ['BTC', 'ETH', 'SOL']}
        return usdt_free, asset_balances
    except BinanceAPIException as e:
        logging.error(f"Gagal mendapatkan saldo: {e}")
        return 0.0, {}

# Fungsi untuk mendapatkan informasi simbol
def get_symbol_info(symbol):
    try:
        symbol_info = client.get_symbol_info(symbol)
        for filter_info in symbol_info['filters']:
            if filter_info['filterType'] == 'LOT_SIZE':
                step_size = float(filter_info['stepSize'])
                return step_size
        logging.error(f"Tidak ditemukan stepSize untuk simbol {symbol}")
        return None
    except BinanceAPIException as e:
        logging.error(f"Gagal mendapatkan informasi simbol untuk {symbol}: {e}")
        return None

# Fungsi untuk membulatkan jumlah aset sesuai dengan presisi yang diizinkan
def round_quantity(quantity, step_size):
    return round(quantity / step_size) * step_size

# Fungsi untuk memeriksa apakah saldo cukup untuk membeli aset
def can_buy_asset(usdt_free, last_price, quantity):
    return usdt_free >= last_price * quantity

# Fungsi untuk menyimpan transaksi ke database
def save_transaction(symbol, type, quantity, price):
    try:
        cursor.execute('''
            INSERT INTO transactions (timestamp, symbol, type, quantity, price)
            VALUES (?, ?, ?, ?, ?)
        ''', (time.strftime('%Y-%m-%d %H:%M:%S'), symbol, type, quantity, price))
        conn.commit()
        logging.info(f"Transaksi {type} {quantity} {symbol} pada harga {price} disimpan ke database")
    except sqlite3.Error as e:
        logging.error(f"Gagal menyimpan transaksi ke database: {e}")

# Fungsi untuk mendapatkan riwayat transaksi
def get_transaction_history(symbol, type):
    try:
        cursor.execute('''
            SELECT * FROM transactions
            WHERE symbol = ? AND type = ?
            ORDER BY timestamp DESC
            LIMIT 1
        ''', (symbol, type))
        return cursor.fetchone()
    except sqlite3.Error as e:
        logging.error(f"Gagal mendapatkan riwayat transaksi: {e}")
        return None

# Fungsi untuk mengirimkan status saldo setiap satu jam
def send_status_update():
    usdt_free, asset_balances = get_balances()
    status_message = f"Status Saldo:\nSaldo USDT: {usdt_free}\nSaldo Aset: {asset_balances}"
    logging.info(status_message)
    send_telegram_message(status_message)

# Fungsi untuk mengecek pending orders
def check_pending_orders():
    try:
        open_orders = client.get_open_orders()
        return len(open_orders) > 0
    except BinanceAPIException as e:
        logging.error(f"Gagal mendapatkan open orders: {e}")
        return False

# Fungsi utama
def main():
    last_status_time = time.time()
    while True:
        usdt_free, asset_balances = get_balances()
        logging.info(f"Saldo USDT: {usdt_free}, Saldo Aset: {asset_balances}")
        send_telegram_message(f"Saldo USDT: {usdt_free}, Saldo Aset: {asset_balances}")

        for symbol in SYMBOLS:
            last_price = get_last_price(symbol)
            if last_price is None:
                continue

            asset = symbol.replace('USDT', '')
            asset_balance = asset_balances.get(asset, 0.0)

            if asset_balance == 0.0:
                # Membeli aset jika tidak memiliki aset tersebut
                quantity = usdt_free * BUY_MULTIPLIER / last_price
                step_size = get_symbol_info(symbol)
                if step_size is not None:
                    quantity = round_quantity(quantity, step_size)
                    if quantity > 0 and can_buy_asset(usdt_free, last_price, quantity):
                        if not check_pending_orders():
                            buy_asset(symbol, quantity)
                            time.sleep(300)  # Tunda 5 menit setelah membeli
            else:
                # Mendapatkan harga pembelian terakhir
                last_buy = get_transaction_history(symbol, 'buy')
                if last_buy is not None:
                    last_buy_price = last_buy[4]
                    sell_price = last_price * SELL_MULTIPLIER
                    if sell_price >= last_buy_price * (1 + TOLERANCE):
                        if not check_pending_orders():
                            sell_asset(symbol, asset_balance)
                            time.sleep(300)  # Tunda 5 menit setelah menjual

        # Mengirimkan status saldo setiap satu jam
        if time.time() - last_status_time >= 3600:  # 3600 detik = 1 jam
            send_status_update()
            last_status_time = time.time()

        time.sleep(CACHE_LIFETIME)

if __name__ == "__main__":
    main()
