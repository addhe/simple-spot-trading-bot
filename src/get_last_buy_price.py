import sqlite3
import logging
from src.get_db_connection import get_db_connection

def get_last_buy_price(symbol):
    try:
        conn = get_db_connection()
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