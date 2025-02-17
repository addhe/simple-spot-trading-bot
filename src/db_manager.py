import sqlite3
import os
from datetime import datetime
from src.logger import logger

class DatabaseManager:
    def __init__(self, db_path='trading_data.db'):
        self.db_path = db_path
        self.logger = logger
        self.conn = None
        self.initialize_database()

    def initialize_database(self):
        """Initialize database with required tables"""
        try:
            self.conn = sqlite3.connect(self.db_path)
            cursor = self.conn.cursor()

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

            self.conn.commit()
            self.logger.info("Database initialized successfully")
        except Exception as e:
            self.logger.error(f"Error initializing database: {e}")

    def store_historical_data(self, symbol, klines):
        """Store historical kline data"""
        try:
            cursor = self.conn.cursor()

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

            self.conn.commit()
            self.logger.debug(f"Stored {len(klines)} historical data points for {symbol}")
        except Exception as e:
            self.logger.error(f"Error storing historical data: {e}")

    def get_historical_data(self, symbol, limit=500):
        """Get historical data for analysis"""
        try:
            cursor = self.conn.cursor()
            
            cursor.execute('''
                SELECT timestamp, close_price, volume
                FROM historical_data
                WHERE symbol = ?
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (symbol, limit))
            
            data = cursor.fetchall()
            return data
        except Exception as e:
            self.logger.error(f"Error retrieving historical data: {e}")
            return None

    def record_trade(self, symbol, side, price, quantity):
        """Record a trade in the database"""
        try:
            cursor = self.conn.cursor()
            
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
            
            self.conn.commit()
            self.logger.info(f"Recorded {side} trade for {symbol}: {quantity} @ {price}")
        except Exception as e:
            self.logger.error(f"Error recording trade: {e}")

    def get_last_trade(self, symbol):
        """Get the last trade for a symbol"""
        try:
            cursor = self.conn.cursor()
            
            cursor.execute('''
                SELECT side, price, quantity, timestamp
                FROM trades
                WHERE symbol = ?
                ORDER BY timestamp DESC
                LIMIT 1
            ''', (symbol,))
            
            trade = cursor.fetchone()
            return trade
        except Exception as e:
            self.logger.error(f"Error getting last trade: {e}")
            return None

    def get_last_buy_price(self, symbol):
        """Get the last buy price for a symbol"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT price
                FROM trades
                WHERE symbol = ? AND side = 'BUY'
                ORDER BY timestamp DESC
                LIMIT 1
            ''', (symbol,))
            
            result = cursor.fetchone()
            return float(result[0]) if result else None
        except Exception as e:
            self.logger.error(f"Error getting last buy price for {symbol}: {e}")
            return None

    def get_highest_price(self, symbol):
        """Get the highest price reached since last buy"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT MAX(close_price)
                FROM historical_data
                WHERE symbol = ? AND timestamp > (
                    SELECT MAX(timestamp)
                    FROM trades
                    WHERE symbol = ? AND side = 'BUY'
                )
            ''', (symbol, symbol))
            
            result = cursor.fetchone()
            return float(result[0]) if result and result[0] else 0
        except Exception as e:
            self.logger.error(f"Error getting highest price for {symbol}: {e}")
            return 0

    def update_highest_price(self, symbol, price):
        """Update the highest price for a symbol"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO historical_data
                (symbol, timestamp, close_price, volume)
                VALUES (?, datetime('now'), ?, 0)
            ''', (symbol, price))
            
            self.conn.commit()
            self.logger.debug(f"Updated highest price for {symbol} to {price}")
            return True
        except Exception as e:
            self.logger.error(f"Error updating highest price for {symbol}: {e}")
            return False

    def save_transaction(self, symbol, side, quantity, price):
        """Save a trade transaction"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT INTO trades
                (symbol, side, quantity, price, timestamp, status)
                VALUES (?, ?, ?, ?, datetime('now'), 'FILLED')
            ''', (symbol, side, quantity, price))
            
            self.conn.commit()
            self.logger.info(f"Saved {side} transaction for {symbol}: {quantity} @ {price}")
            return True
        except Exception as e:
            self.logger.error(f"Error saving transaction: {e}")
            return False

    def close_connection(self):
        """Close the database connection"""
        try:
            if hasattr(self, 'conn') and self.conn:
                self.conn.close()
                self.logger.info("Database connection closed successfully")
        except Exception as e:
            self.logger.error(f"Error closing database connection: {e}")

    def __del__(self):
        """Destructor to ensure connection is closed"""
        self.close_connection()
