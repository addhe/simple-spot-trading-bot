import sqlite3
import threading
from src.logger import logger

class DatabaseManager:
    def __init__(self, db_path='table_transactions.db'):
        self.db_path = db_path
        self._local = threading.local()

    def get_connection(self):
        """Get a thread-local database connection"""
        if not hasattr(self._local, 'connection') or self._local.connection is None:
            try:
                self._local.connection = sqlite3.connect(self.db_path)
                self._local.connection.row_factory = sqlite3.Row
            except Exception as e:
                logger.error(f"Error connecting to database: {e}")
                raise
        return self._local.connection

    def get_cursor(self):
        """Get a cursor from the current connection"""
        conn = self.get_connection()
        if not hasattr(self._local, 'cursor') or self._local.cursor is None:
            self._local.cursor = conn.cursor()
        return self._local.cursor

    def commit(self):
        """Commit the current transaction"""
        if hasattr(self._local, 'connection') and self._local.connection is not None:
            try:
                self._local.connection.commit()
            except Exception as e:
                logger.error(f"Error committing transaction: {e}")
                raise

    def close_connection(self):
        """Close the thread-local database connection if it exists"""
        if hasattr(self._local, 'cursor') and self._local.cursor is not None:
            try:
                self._local.cursor.close()
            except Exception as e:
                logger.error(f"Error closing cursor: {e}")
            self._local.cursor = None

        if hasattr(self._local, 'connection') and self._local.connection is not None:
            try:
                self._local.connection.close()
            except Exception as e:
                logger.error(f"Error closing connection: {e}")
            self._local.connection = None

    def execute_query(self, query, params=None):
        """Execute a query and return the cursor"""
        try:
            cursor = self.get_cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            self.commit()
            return cursor
        except Exception as e:
            logger.error(f"Error executing query: {query} - {e}")
            raise

    def get_last_buy_price(self, symbol):
        """Get the last buy price for a symbol"""
        try:
            query = """
                SELECT price
                FROM transactions
                WHERE symbol = ? AND type = 'buy'
                ORDER BY timestamp DESC
                LIMIT 1
            """
            cursor = self.execute_query(query, (symbol,))
            result = cursor.fetchone()
            return float(result['price']) if result else None
        except Exception as e:
            logger.error(f"Error getting last buy price for {symbol}: {e}")
            return None

    def get_highest_price(self, symbol):
        """Get the highest price recorded for a symbol"""
        try:
            query = """
                SELECT highest_price
                FROM symbol_stats
                WHERE symbol = ?
            """
            cursor = self.execute_query(query, (symbol,))
            result = cursor.fetchone()
            return float(result['highest_price']) if result else 0
        except Exception as e:
            logger.error(f"Error getting highest price for {symbol}: {e}")
            return 0

    def update_highest_price(self, symbol, price):
        """Update the highest price for a symbol"""
        try:
            query = """
                INSERT OR REPLACE INTO symbol_stats (symbol, highest_price)
                VALUES (?, ?)
            """
            self.execute_query(query, (symbol, price))
        except Exception as e:
            logger.error(f"Error updating highest price for {symbol}: {e}")

    def setup_tables(self):
        """Initialize database tables"""
        try:
            # Create transactions table
            self.execute_query("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    type TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    price REAL NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create symbol stats table
            self.execute_query("""
                CREATE TABLE IF NOT EXISTS symbol_stats (
                    symbol TEXT PRIMARY KEY,
                    highest_price REAL NOT NULL,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create historical data table
            self.execute_query("""
                CREATE TABLE IF NOT EXISTS historical_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    timestamp DATETIME NOT NULL,
                    open_price REAL NOT NULL,
                    high_price REAL NOT NULL,
                    low_price REAL NOT NULL,
                    close_price REAL NOT NULL,
                    volume REAL NOT NULL,
                    UNIQUE(symbol, timestamp)
                )
            """)

        except Exception as e:
            logger.error(f"Error setting up database: {e}")
            raise

    def save_transaction(self, symbol, transaction_type, quantity, price):
        """Save a transaction to the database"""
        try:
            query = """
                INSERT INTO transactions (symbol, type, quantity, price)
                VALUES (?, ?, ?, ?)
            """
            self.execute_query(query, (symbol, transaction_type, quantity, price))
        except Exception as e:
            logger.error(f"Error saving transaction: {e}")
            raise
