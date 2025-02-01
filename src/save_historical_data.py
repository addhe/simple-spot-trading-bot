import os
import time
import logging
import sqlite3
from datetime import datetime, timedelta
from src._validate_kline_data import _validate_kline_data

def save_historical_data(symbol, klines):
    """Enhanced historical data saving with data validation"""
    try:
        conn = sqlite3.connect('table_transactions.db', check_same_thread=False)
        cursor = conn.cursor()

        # Data validation
        validated_klines = [
            kline for kline in klines
            if _validate_kline_data(kline)
        ]

        for kline in validated_klines:
            timestamp = datetime.fromtimestamp(kline[0]/1000).strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute('''
                INSERT OR REPLACE INTO historical_data
                (symbol, timestamp, open_price, high_price, low_price, close_price, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                symbol,
                timestamp,
                float(kline[1]),  # open
                float(kline[2]),  # high
                float(kline[3]),  # low
                float(kline[4]),  # close
                float(kline[5])   # volume
            ))

        conn.commit()
        conn.close()
        logging.info(f"Saved {len(validated_klines)} validated historical data points for {symbol}")

    except sqlite3.Error as e:
        logging.error(f"Failed to save historical data: {e}")