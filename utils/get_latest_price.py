import logging
import sqlite3

# Konfigurasi logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
                    filename='get_latest_price.log', filemode='w')  # Menyimpan log ke file

# Nama database
DB_NAME = 'table_transactions.db'

def get_latest_transaction(symbol, type):
    try:
        # Membuka koneksi ke database
        conn = sqlite3.connect(DB_NAME, check_same_thread=False)
        cursor = conn.cursor()

        # Mengambil transaksi terakhir untuk simbol dan jenis transaksi tertentu
        cursor.execute('''
            SELECT * FROM transactions
            WHERE symbol = ? AND type = ?
            ORDER BY timestamp DESC
            LIMIT 1
        ''', (symbol, type))
        latest_transaction = cursor.fetchone()

        # Menutup koneksi ke database
        conn.close()

        return latest_transaction
    except sqlite3.Error as e:
        logging.error(f"Gagal mengambil transaksi terakhir untuk {symbol} dengan jenis {type}: {e}")
        return None

def main():
    symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
    for symbol in symbols:
        logging.info(f"Memeriksa transaksi untuk {symbol}")

        # Mendapatkan transaksi pembelian terakhir
        latest_buy = get_latest_transaction(symbol, 'buy')
        if latest_buy:
            logging.info(f"Transaksi pembelian terakhir untuk {symbol}: {latest_buy}")
        else:
            logging.info(f"Tidak ada transaksi pembelian terakhir untuk {symbol}")

        # Mendapatkan transaksi penjualan terakhir
        latest_sell = get_latest_transaction(symbol, 'sell')
        if latest_sell:
            logging.info(f"Transaksi penjualan terakhir untuk {symbol}: {latest_sell}")
        else:
            logging.info(f"Tidak ada transaksi penjualan terakhir untuk {symbol}")

if __name__ == "__main__":
    main()
