import os
import logging
import sqlite3

# Konfigurasi logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Direktori database
DB_NAME = 'table_transactions.db'

# Fungsi untuk mendapatkan harga pembelian terakhir
def get_last_buy_price(symbol):
    try:
        conn = sqlite3.connect(DB_NAME, check_same_thread=False)
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

# Fungsi untuk mendapatkan semua transaksi terakhir
def get_latest_transactions():
    try:
        conn = sqlite3.connect(DB_NAME, check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT symbol, type, quantity, price, timestamp FROM transactions
            ORDER BY timestamp DESC
            LIMIT 10
        ''')
        transactions = cursor.fetchall()
        conn.close()
        return transactions
    except sqlite3.Error as e:
        logging.error(f"Gagal mendapatkan transaksi terakhir: {e}")
        return []

# Fungsi utama
def main():
    symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
    for symbol in symbols:
        logging.info(f"Memeriksa transaksi untuk {symbol}")
        last_buy_price = get_last_buy_price(symbol)
        if last_buy_price:
            logging.info(f"Harga pembelian terakhir untuk {symbol}: {last_buy_price}")
        else:
            logging.info(f"Tidak ada transaksi pembelian terakhir untuk {symbol}")

    transactions = get_latest_transactions()
    if transactions:
        logging.info("Riwayat Transaksi Terakhir:")
        for transaction in transactions:
            symbol, type, quantity, price, timestamp = transaction
            logging.info(f"{timestamp} - {symbol} - {type} - {quantity} - {price}")
    else:
        logging.info("Tidak ada transaksi terakhir.")

if __name__ == "__main__":
    main()
