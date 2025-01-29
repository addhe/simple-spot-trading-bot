import sqlite3
import logging

# Konfigurasi logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Nama database
DB_NAME = 'table_transactions.db'

def get_latest_transaction():
    try:
        # Membuka koneksi ke database
        conn = sqlite3.connect(DB_NAME, check_same_thread=False)
        cursor = conn.cursor()

        # Mengambil transaksi terakhir
        cursor.execute('SELECT * FROM transactions ORDER BY timestamp DESC LIMIT 1')
        latest_transaction = cursor.fetchone()

        # Menutup koneksi database
        conn.close()

        if latest_transaction:
            logging.info(f"Transaksi Terakhir: {latest_transaction}")
            return latest_transaction
        else:
            logging.info("Tidak ada transaksi terakhir.")
            return None
    except sqlite3.Error as e:
        logging.error(f"Gagal mengambil transaksi terakhir dari database: {e}")
        return None

if __name__ == "__main__":
    get_latest_transaction()
