import os
import logging
import sqlite3

# Konfigurasi logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
                    filename='get_latest_price.log', filemode='w')  # Menyimpan log ke file

# Direktori database
DB_NAME = 'table_transactions.db'

# Inisialisasi koneksi database SQLite
conn = sqlite3.connect(DB_NAME, check_same_thread=False)
cursor = conn.cursor()

# Fungsi untuk mendapatkan harga pembelian terakhir
def get_last_buy_price(symbol):
    try:
        cursor.execute('''
            SELECT timestamp, quantity, price FROM transactions
            WHERE symbol = ? AND type = 'buy'
            ORDER BY timestamp DESC
            LIMIT 1
        ''', (symbol,))
        result = cursor.fetchone()
        if result:
            timestamp, quantity, price = result
            logging.info(f"Transaksi pembelian terakhir untuk {symbol}: Waktu: {timestamp}, Jumlah: {quantity}, Harga: {price}")
        else:
            logging.info(f"Tidak ada transaksi pembelian terakhir untuk {symbol}.")
    except sqlite3.Error as e:
        logging.error(f"Gagal mendapatkan harga pembelian terakhir: {e}")

# Fungsi untuk mendapatkan harga penjualan terakhir
def get_last_sell_price(symbol):
    try:
        cursor.execute('''
            SELECT timestamp, quantity, price FROM transactions
            WHERE symbol = ? AND type = 'sell'
            ORDER BY timestamp DESC
            LIMIT 1
        ''', (symbol,))
        result = cursor.fetchone()
        if result:
            timestamp, quantity, price = result
            logging.info(f"Transaksi penjualan terakhir untuk {symbol}: Waktu: {timestamp}, Jumlah: {quantity}, Harga: {price}")
        else:
            logging.info(f"Tidak ada transaksi penjualan terakhir untuk {symbol}.")
    except sqlite3.Error as e:
        logging.error(f"Gagal mendapatkan harga penjualan terakhir: {e}")

# Fungsi utama
def main():
    symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
    for symbol in symbols:
        logging.info(f"Memeriksa transaksi untuk {symbol}")
        get_last_buy_price(symbol)
        get_last_sell_price(symbol)

if __name__ == "__main__":
    main()
