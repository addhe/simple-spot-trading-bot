import sqlite3
import logging

# Konfigurasi logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
                    filename='get_latest_price.log', filemode='a')  # Menyimpan log ke file

# Nama database
DB_NAME = 'table_transactions.db'

def get_latest_transaction(symbol, transaction_type):
    try:
        # Membuka koneksi ke database
        conn = sqlite3.connect(DB_NAME, check_same_thread=False)
        cursor = conn.cursor()

        # Mengambil transaksi terakhir berdasarkan jenis transaksi
        cursor.execute('SELECT * FROM transactions WHERE symbol = ? AND type = ? ORDER BY timestamp DESC LIMIT 1', (symbol, transaction_type))
        latest_transaction = cursor.fetchone()

        # Menutup koneksi database
        conn.close()

        if latest_transaction:
            logging.info(f"Transaksi Terakhir {transaction_type} untuk {symbol}: {latest_transaction}")
            return latest_transaction
        else:
            logging.info(f"Tidak ada transaksi {transaction_type} terakhir untuk {symbol}.")
            return None
    except sqlite3.Error as e:
        logging.error(f"Gagal mengambil transaksi terakhir dari database: {e}")
        return None

if __name__ == "__main__":
    for symbol in ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']:
        logging.info(f"Memeriksa transaksi untuk {symbol}")
        get_latest_transaction(symbol, 'buy')
        get_latest_transaction(symbol, 'sell')
