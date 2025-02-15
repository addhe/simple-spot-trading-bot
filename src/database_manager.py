import sqlite3
from src.logger import logger

class DatabaseManager:
    def __init__(self, db_path='table_transactions.db'):
        self.db_path = db_path
        self._connection = None
        self._cursor = None

    def get_connection(self):
        """Get a database connection, creating it if necessary"""
        if self._connection is None:
            try:
                self._connection = sqlite3.connect(self.db_path)
                self._connection.row_factory = sqlite3.Row
            except Exception as e:
                logger.error(f"Error connecting to database: {e}")
                raise
        return self._connection

    def close_connection(self):
        """Close the database connection if it exists"""
        if self._connection is not None:
            try:
                self._connection.close()
                self._connection = None
                self._cursor = None
            except Exception as e:
                logger.error(f"Error closing database connection: {e}")

    def setup_tables(self):
        """Initialize database tables"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            # Create transactions table if not exists
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    type TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    price REAL NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create symbol stats table for tracking highest prices
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS symbol_stats (
                    symbol TEXT PRIMARY KEY,
                    highest_price REAL NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            conn.commit()
        except Exception as e:
            logger.error(f"Error setting up database tables: {e}")
            raise

    def get_highest_price(self, symbol):
        """Get the highest price recorded for a symbol since last buy"""
        try:
            cursor = self.get_connection().cursor()
            cursor.execute("""
                SELECT highest_price FROM symbol_stats
                WHERE symbol = ? ORDER BY timestamp DESC LIMIT 1
            """, (symbol,))
            result = cursor.fetchone()
            return float(result[0]) if result else 0
        except Exception as e:
            logger.error(f"Error getting highest price for {symbol}: {e}")
            return 0

    def update_highest_price(self, symbol, price):
        """Update the highest price for a symbol"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO symbol_stats (symbol, highest_price, timestamp)
                VALUES (?, ?, datetime('now'))
            """, (symbol, price))
            conn.commit()
        except Exception as e:
            logger.error(f"Error updating highest price for {symbol}: {e}")

    def get_last_buy_price(self, symbol):
        """Get the last buy price for a symbol"""
        try:
            cursor = self.get_connection().cursor()
            cursor.execute("""
                SELECT price FROM transactions
                WHERE symbol = ? AND type = 'BUY'
                ORDER BY timestamp DESC LIMIT 1
            """, (symbol,))
            result = cursor.fetchone()
            return float(result[0]) if result else None
        except Exception as e:
            logger.error(f"Error getting last buy price for {symbol}: {e}")
            return None

    def save_transaction(self, symbol, transaction_type, quantity, price):
        """Save a transaction to the database"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO transactions (symbol, type, quantity, price)
                VALUES (?, ?, ?, ?)
            """, (symbol, transaction_type, quantity, price))
            conn.commit()
        except Exception as e:
            logger.error(f"Error saving transaction: {e}")
            raise
