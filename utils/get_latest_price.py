import sqlite3
import logging

# Konfigurasi logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Nama database
DB_NAME = 'table_transactions.db'

def get_latest_transaction(symbol):
    try:
        # Membuka koneksi ke database
        conn = sqlite3.connect(DB_NAME, check_same_thread=False)
        cursor = conn.cursor()

        # Mengambil transaksi terakhir untuk simbol tertentu
        cursor.execute('''
            SELECT * FROM transactions
            WHERE symbol = ?
            ORDER BY timestamp DESC
            LIMIT 1
        ''', (symbol,))
        latest_transaction = cursor.fetchone()

        # Menutup koneksi ke database
        conn.close()

        return latest_transaction
    except sqlite3.Error as e:
        logging.error(f"Gagal mengambil transaksi terakhir untuk {symbol}: {e}")
        return None

def main():
    for symbol in ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']:
        logging.info(f"Memeriksa transaksi untuk {symbol}")
        latest_transaction = get_latest_transaction(symbol)
        if latest_transaction:
            if latest_transaction[3] == 'buy':
                logging.info(f"Transaksi pembelian terakhir untuk {symbol}: {latest_transaction}")
            elif latest_transaction[3] == 'sell':
                logging.info(f"Transaksi penjualan terakhir untuk {symbol}: {latest_transaction}")
        else:
            logging.info(f"Tidak ada transaksi terakhir untuk {symbol}.")

if __name__ == "__main__":
    main()
