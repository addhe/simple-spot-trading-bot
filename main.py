import os
import time
import logging
import sqlite3
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceOrderException
from src.send_telegram_message import send_telegram_message

# Konfigurasi logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
                    filename='bot.log', filemode='a')  # Menyimpan log ke file

# Mengambil variabel lingkungan
API_KEY = os.environ['API_KEY_SPOT_TESTNET_BINANCE']
API_SECRET = os.environ['API_SECRET_SPOT_TESTNET_BINANCE']
BASE_URL = 'https://testnet.binance.vision/api'
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_GROUP_ID = os.getenv('TELEGRAM_GROUP_ID')
SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
INTERVAL = '1m'
CACHE_LIFETIME = 300  # 5 menit
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
                min_qty = float(filter_info['minQty'])
                max_qty = float(filter_info['maxQty'])
                return step_size, min_qty, max_qty
        logging.error(f"Tidak ditemukan stepSize, minQty, atau maxQty untuk simbol {symbol}")
        return None, None, None
    except BinanceAPIException as e:
        logging.error(f"Gagal mendapatkan informasi simbol untuk {symbol}: {e}")
        return None, None, None

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

# Fungsi untuk memuat riwayat transaksi dari database
def load_transactions():
    try:
        cursor.execute('SELECT symbol, type, quantity, price FROM transactions')
        transactions = cursor.fetchall()
        logging.info(f"Riwayat Transaksi: {transactions}")
        return transactions
    except sqlite3.Error as e:
        logging.error(f"Gagal memuat riwayat transaksi dari database: {e}")
        return []

# Fungsi untuk mengirimkan status saldo setiap satu jam
def send_status_update():
    usdt_free, asset_balances = get_balances()
    status_message = f"Status Saldo:\nSaldo USDT: {usdt_free}\nSaldo Aset: {asset_balances}"
    logging.info(status_message)
    send_telegram_message(status_message)

# Fungsi untuk memeriksa apakah ada pending order
def has_pending_orders():
    try:
        open_orders = client.get_open_orders()
        return len(open_orders) > 0
    except BinanceAPIException as e:
        logging.error(f"Gagal mendapatkan open orders: {e}")
        return False

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

# Fungsi utama
def main():
    last_status_time = time.time()
    last_transaction_time = time.time()

    while True:
        if has_pending_orders():
            logging.info("Ada pending order, menunggu 5 menit sebelum melanjutkan.")
            time.sleep(CACHE_LIFETIME)  # 5 menit
            continue

        usdt_free, asset_balances = get_balances()
        logging.info(f"Saldo USDT: {usdt_free}, Saldo Aset: {asset_balances}")
        send_telegram_message(f"Saldo USDT: {usdt_free}, Saldo Aset: {asset_balances}")

        # Memuat riwayat transaksi
        transaction_history = load_transactions()

        # Pembagian saldo USDT merata antara simbol
        usdt_per_symbol = usdt_free / len(SYMBOLS)

        for symbol in SYMBOLS:
            last_price = get_last_price(symbol)
            if last_price is None:
                continue

            asset = symbol.replace('USDT', '')
            asset_balance = asset_balances.get(asset, 0.0)

            if asset_balance == 0.0:
                # Membeli aset jika tidak memiliki aset tersebut
                quantity = usdt_per_symbol * BUY_MULTIPLIER / last_price
                step_size, min_qty, max_qty = get_symbol_info(symbol)
                if step_size is not None and min_qty is not None and max_qty is not None:
                    quantity = round_quantity(quantity, step_size)
                    quantity = max(quantity, min_qty)
                    quantity = min(quantity, max_qty)

                    if quantity > 0 and can_buy_asset(usdt_free, last_price, quantity):
                        if not has_pending_orders():
                            buy_asset(symbol, quantity)
                            last_transaction_time = time.time()
                            time.sleep(CACHE_LIFETIME)  # Jeda 5 menit setelah beli
            else:
                # Menjual aset jika harga naik 3%
                sell_price = last_price * SELL_MULTIPLIER
                if sell_price >= last_price * (1 + TOLERANCE):
                    # Memeriksa riwayat transaksi untuk harga pembelian
                    buy_transactions = [t for t in transaction_history if t[0] == symbol and t[1] == 'buy']
                    if buy_transactions:
                        last_buy_price = max(buy_transactions, key=lambda x: x[2])[3]
                        if sell_price > last_buy_price:
                            if not has_pending_orders():
                                sell_asset(symbol, asset_balance)
                                last_transaction_time = time.time()
                                time.sleep(CACHE_LIFETIME)  # Jeda 5 menit setelah jual

        # Mengirimkan status saldo setiap satu jam
        current_time = time.time()
        if current_time - last_status_time >= 3600:  # 3600 detik = 1 jam
            send_status_update()
            last_status_time = current_time

        # Menunggu CACHE_LIFETIME detik sebelum iterasi berikutnya
        time.sleep(CACHE_LIFETIME)

if __name__ == "__main__":
    main()
