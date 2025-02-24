import os
import logging
import sqlite3

# Konfigurasi logging
log_directory = 'logs/bot'
if not os.path.exists(log_directory):
    os.makedirs(log_directory)

log_file = os.path.join(log_directory, 'get_latest_price.log')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=5),
        logging.StreamHandler()
    ]
)

# Direktori database
DB_NAME = 'table_transactions.db'

# Inisialisasi koneksi database SQLite
conn = sqlite3.connect(DB_NAME, check_same_thread=False)
cursor = conn.cursor()

# Fungsi untuk mendapatkan riwayat transaksi terakhir untuk suatu simbol
def get_latest_transaction(symbol):
    try:
        cursor.execute('''
            SELECT * FROM transactions
            WHERE symbol = ?
            ORDER BY timestamp DESC
            LIMIT 1
        ''', (symbol,))
        result = cursor.fetchone()
        return result
    except sqlite3.Error as e:
        logging.error(f"Gagal mendapatkan riwayat transaksi: {e}")
        return None

# Fungsi utama
def main():
    symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
    for symbol in symbols:
        logging.info(f"Memeriksa transaksi untuk {symbol}")
        transaction = get_latest_transaction(symbol)
        if transaction:
            logging.info(f"Transaksi terakhir untuk {symbol}: {transaction}")
        else:
            logging.info(f"Tidak ada transaksi terakhir untuk {symbol}")

if __name__ == "__main__":
    main()
