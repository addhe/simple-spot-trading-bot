import os
import sqlite3
import logging
from typing import Any, Dict, List, Optional, Union
from datetime import datetime, timedelta
from cachetools import TTLCache
from tenacity import retry, stop_after_attempt, wait_exponential
from src.logger import logger
from src.monitoring import metrics

class DatabaseManager:
    def __init__(self, db_path: str = "table_transactions.db"):
        self.db_path = db_path
        self.conn = None
        self.setup_tables()

    def setup_tables(self):
        """Setup database tables"""
        try:
            self.conn = sqlite3.connect(self.db_path)
            cursor = self.conn.cursor()

            # Create trades table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    price REAL NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Create historical data table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS historical_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    timestamp DATETIME NOT NULL,
                    open_price REAL NOT NULL,
                    high_price REAL NOT NULL,
                    low_price REAL NOT NULL,
                    close_price REAL NOT NULL,
                    volume REAL NOT NULL
                )
            ''')

            # Create price tracking table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS price_tracking (
                    symbol TEXT PRIMARY KEY,
                    highest_price REAL NOT NULL,
                    last_buy_price REAL,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            self.conn.commit()
            logger.info("Database tables initialized successfully")

        except Exception as e:
            logger.error(f"Error setting up database tables: {e}")
            raise

    def close_connection(self):
        """Close the database connection"""
        if self.conn:
            self.conn.close()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def execute_query(self, query: str, parameters: tuple = None):
        """Execute a query"""
        try:
            cursor = self.conn.cursor()
            if parameters:
                cursor.execute(query, parameters)
            else:
                cursor.execute(query)
            self.conn.commit()
            return cursor.fetchall()
        except Exception as e:
            logger.error(f"Error executing query: {e}")
            metrics.record_error("database_query")
            raise

    def insert_trade(self, symbol: str, side: str, quantity: float, price: float, timestamp: datetime):
        """Insert a trade record"""
        query = '''
            INSERT INTO trades (symbol, side, quantity, price, timestamp)
            VALUES (?, ?, ?, ?, ?)
        '''
        self.execute_query(query, (symbol, side, quantity, price, timestamp))

    def get_last_trade(self, symbol: str) -> Optional[Dict]:
        """Get the last trade for a symbol"""
        query = '''
            SELECT * FROM trades
            WHERE symbol = ?
            ORDER BY timestamp DESC
            LIMIT 1
        '''
        result = self.execute_query(query, (symbol,))
        if result:
            return {
                'symbol': result[0][1],
                'side': result[0][2],
                'quantity': result[0][3],
                'price': result[0][4],
                'timestamp': result[0][5]
            }
        return None

    def get_trade_history(self, symbol: str, limit: int = 100) -> List[Dict]:
        """Get trade history for a symbol"""
        query = '''
            SELECT * FROM trades
            WHERE symbol = ?
            ORDER BY timestamp DESC
            LIMIT ?
        '''
        results = self.execute_query(query, (symbol, limit))
        return [{
            'symbol': row[1],
            'side': row[2],
            'quantity': row[3],
            'price': row[4],
            'timestamp': row[5]
        } for row in results]

    def insert_historical_data(self, symbol: str, data: Dict):
        """Insert historical price data"""
        query = '''
            INSERT INTO historical_data (
                symbol, timestamp, open_price, high_price,
                low_price, close_price, volume
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        '''
        self.execute_query(query, (
            symbol,
            data['timestamp'],
            data['open'],
            data['high'],
            data['low'],
            data['close'],
            data['volume']
        ))

    def get_historical_data(self, symbol: str, limit: int = 500) -> List[Dict]:
        """Get historical data for a symbol"""
        query = '''
            SELECT * FROM historical_data
            WHERE symbol = ?
            ORDER BY timestamp DESC
            LIMIT ?
        '''
        results = self.execute_query(query, (symbol, limit))
        return [{
            'timestamp': row[2],
            'open': row[3],
            'high': row[4],
            'low': row[5],
            'close': row[6],
            'volume': row[7]
        } for row in results]

    def update_price_tracking(self, symbol: str, highest_price: float, last_buy_price: float = None):
        """Update price tracking data"""
        query = '''
            INSERT OR REPLACE INTO price_tracking (
                symbol, highest_price, last_buy_price, updated_at
            ) VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        '''
        self.execute_query(query, (symbol, highest_price, last_buy_price))

    def get_price_tracking(self, symbol: str) -> Optional[Dict]:
        """Get price tracking data for a symbol"""
        query = '''
            SELECT * FROM price_tracking
            WHERE symbol = ?
        '''
        result = self.execute_query(query, (symbol,))
        if result:
            return {
                'symbol': result[0][0],
                'highest_price': result[0][1],
                'last_buy_price': result[0][2],
                'updated_at': result[0][3]
            }
        return None

# Initialize database manager
db_manager = DatabaseManager()
