import sqlite3
import os
from datetime import datetime
from src.logger import logger

class DatabaseManager:
    def __init__(self, db_path='trading_data.db'):
        self.db_path = db_path
        self.logger = logger
        self.initialize_database()

    def initialize_database(self):
        """Initialize database with required tables"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Create historical data table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS historical_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    timestamp INTEGER NOT NULL,
                    open_price REAL,
                    high_price REAL,
                    low_price REAL,
                    close_price REAL,
                    volume REAL,
                    UNIQUE(symbol, timestamp)
                )
            ''')

            # Create trades table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    price REAL NOT NULL,
                    quantity REAL NOT NULL,
                    timestamp INTEGER NOT NULL,
                    status TEXT NOT NULL
                )
            ''')

            conn.commit()
            conn.close()
            self.logger.info("Database initialized successfully")
        except Exception as e:
            self.logger.error(f"Error initializing database: {e}")

    def store_historical_data(self, symbol, klines):
        """Store historical kline data"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            for kline in klines:
                cursor.execute('''
                    INSERT OR REPLACE INTO historical_data 
                    (symbol, timestamp, open_price, high_price, low_price, close_price, volume)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    symbol,
                    int(kline[0]),  # timestamp
                    float(kline[1]),  # open
                    float(kline[2]),  # high
                    float(kline[3]),  # low
                    float(kline[4]),  # close
                    float(kline[5])   # volume
                ))

            conn.commit()
            conn.close()
            self.logger.debug(f"Stored {len(klines)} historical data points for {symbol}")
        except Exception as e:
            self.logger.error(f"Error storing historical data: {e}")

    def get_historical_data(self, symbol, limit=500):
        """Get historical data for analysis"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT timestamp, close_price, volume
                FROM historical_data
                WHERE symbol = ?
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (symbol, limit))
            
            data = cursor.fetchall()
            conn.close()
            return data
        except Exception as e:
            self.logger.error(f"Error retrieving historical data: {e}")
            return None

    def record_trade(self, symbol, side, price, quantity):
        """Record a trade in the database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO trades (symbol, side, price, quantity, timestamp, status)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                symbol,
                side,
                price,
                quantity,
                int(datetime.now().timestamp() * 1000),
                'executed'
            ))
            
            conn.commit()
            conn.close()
            self.logger.info(f"Recorded {side} trade for {symbol}: {quantity} @ {price}")
        except Exception as e:
            self.logger.error(f"Error recording trade: {e}")

    def get_last_trade(self, symbol):
        """Get the last trade for a symbol"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT side, price, quantity, timestamp
                FROM trades
                WHERE symbol = ?
                ORDER BY timestamp DESC
                LIMIT 1
            ''', (symbol,))
            
            trade = cursor.fetchone()
            conn.close()
            return trade
        except Exception as e:
            self.logger.error(f"Error getting last trade: {e}")
            return None
