import os
import logging
import sqlite3

# Membuat folder logs jika belum ada
log_directory = 'logs/utils'
if not os.path.exists(log_directory):
    os.makedirs(log_directory)

# Konfigurasi logging untuk menulis ke file di folder logs/utils
log_file = os.path.join(log_directory, 'get_latest_price.log')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)

# Inisialisasi koneksi database SQLite
DB_NAME = 'table_transactions.db'
conn = sqlite3.connect(DB_NAME, check_same_thread=False)
cursor = conn.cursor()

def get_latest_buy_price(symbol):
    try:
        cursor.execute('''
            SELECT price FROM transactions
            WHERE symbol = ? AND type = 'buy'
            ORDER BY timestamp DESC
            LIMIT 1
        ''', (symbol,))
        result = cursor.fetchone()
        return result[0] if result else None
    except sqlite3.Error as e:
        logging.error(f"Gagal mendapatkan harga pembelian terakhir untuk {symbol}: {e}")
        return None

def get_latest_sell_price(symbol):
    try:
        cursor.execute('''
            SELECT price FROM transactions
            WHERE symbol = ? AND type = 'sell'
            ORDER BY timestamp DESC
            LIMIT 1
        ''', (symbol,))
        result = cursor.fetchone()
        return result[0] if result else None
    except sqlite3.Error as e:
        logging.error(f"Gagal mendapatkan harga penjualan terakhir untuk {symbol}: {e}")
        return None

def main():
    for symbol in ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']:
        logging.info(f"Memeriksa transaksi untuk {symbol}")
        latest_buy_price = get_latest_buy_price(symbol)
        if latest_buy_price is not None:
            logging.info(f"Harga pembelian terakhir untuk {symbol}: {latest_buy_price}")
        else:
            logging.info(f"Tidak ada transaksi pembelian terakhir untuk {symbol}.")

        latest_sell_price = get_latest_sell_price(symbol)
        if latest_sell_price is not None:
            logging.info(f"Harga penjualan terakhir untuk {symbol}: {latest_sell_price}")
        else:
            logging.info(f"Tidak ada transaksi penjualan terakhir untuk {symbol}.")

if __name__ == "__main__":
    main()
