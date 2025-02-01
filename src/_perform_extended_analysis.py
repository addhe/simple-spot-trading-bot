import pandas as pd
import logging
import threading

from src.get_db_connection import get_db_connection

# Database connection lock
db_lock = threading.Lock()

def _perform_extended_analysis(symbol):
    """Perform extended analysis on historical data"""
    try:
        with db_lock:
            conn = get_db_connection()
            df = pd.read_sql_query(f'''
                SELECT timestamp, close_price, volume
                FROM historical_data
                WHERE symbol = '{symbol}'
                ORDER BY timestamp DESC
                LIMIT 500
            ''', conn)
            conn.close()

        if len(df) < 50:
            return

        # Calculate additional technical indicators
        df['EMA_20'] = df['close_price'].ewm(span=20).mean()
        df['STD_20'] = df['close_price'].rolling(window=20).std()

        # Save analysis results if needed
        logging.info(f"Extended analysis completed for {symbol}")

    except Exception as e:
        logging.error(f"Extended analysis failed for {symbol}: {e}")