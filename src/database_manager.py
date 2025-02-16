import os
import asyncio
import aiosqlite
import logging
from typing import Any, Dict, List, Optional, Union
from datetime import datetime, timedelta
from cachetools import TTLCache
from tenacity import retry, stop_after_attempt, wait_exponential
from src.logger import logger
from src.monitoring import metrics

class DatabasePool:
    def __init__(self, db_path: str, max_connections: int = 5):
        self.db_path = db_path
        self.max_connections = max_connections
        self._pool: List[aiosqlite.Connection] = []
        self._pool_lock = asyncio.Lock()
        self._connection_semaphore = asyncio.Semaphore(max_connections)

    async def _create_connection(self) -> aiosqlite.Connection:
        """Create a new database connection with retry mechanism"""
        @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
        async def connect_with_retry():
            try:
                conn = await aiosqlite.connect(self.db_path)
                await conn.execute("PRAGMA journal_mode=WAL")  # Enable Write-Ahead Logging
                await conn.execute("PRAGMA synchronous=NORMAL")  # Optimize performance
                await conn.execute("PRAGMA cache_size=-2000")  # Set cache size to 2MB
                return conn
            except Exception as e:
                logger.error(f"Database connection error: {str(e)}")
                metrics.record_error("database_connection")
                raise

        return await connect_with_retry()

    async def acquire(self) -> aiosqlite.Connection:
        """Acquire a connection from the pool"""
        async with self._pool_lock:
            if self._pool:
                return self._pool.pop()

        async with self._connection_semaphore:
            return await self._create_connection()

    async def release(self, conn: aiosqlite.Connection):
        """Release a connection back to the pool"""
        async with self._pool_lock:
            if len(self._pool) < self.max_connections:
                self._pool.append(conn)
            else:
                await conn.close()

class DatabaseManager:
    def __init__(self, db_path: str = "table_transactions.db"):
        self.db_path = db_path
        self.pool = DatabasePool(db_path)
        
        # Cache configuration
        self.cache = TTLCache(maxsize=100, ttl=300)  # Cache with 5 minutes TTL
        self._setup_tables_lock = asyncio.Lock()
        self._query_locks: Dict[str, asyncio.Lock] = {}

    async def _get_query_lock(self, query: str) -> asyncio.Lock:
        """Get or create a lock for a specific query"""
        if query not in self._query_locks:
            self._query_locks[query] = asyncio.Lock()
        return self._query_locks[query]

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def execute_query(self, query: str, parameters: tuple = None) -> Optional[List[Dict[str, Any]]]:
        """Execute a query with retry mechanism and connection pooling"""
        conn = await self.pool.acquire()
        try:
            async with metrics.measure_api_latency():
                async with conn.cursor() as cursor:
                    if parameters:
                        await cursor.execute(query, parameters)
                    else:
                        await cursor.execute(query)
                    
                    if query.lower().startswith("select"):
                        columns = [description[0] for description in cursor.description]
                        rows = await cursor.fetchall()
                        await conn.commit()
                        return [dict(zip(columns, row)) for row in rows]
                    else:
                        await conn.commit()
                        return None
        except Exception as e:
            logger.error(f"Database query error: {str(e)}, Query: {query}, Parameters: {parameters}")
            metrics.record_error("database_query")
            raise
        finally:
            await self.pool.release(conn)

    async def cached_query(self, query: str, parameters: tuple = None, cache_key: str = None) -> Optional[List[Dict[str, Any]]]:
        """Execute a query with caching"""
        if not cache_key:
            cache_key = f"{query}_{str(parameters)}"

        # Check cache first
        cached_result = self.cache.get(cache_key)
        if cached_result is not None:
            return cached_result

        # If not in cache, execute query and cache result
        result = await self.execute_query(query, parameters)
        if result is not None:
            self.cache[cache_key] = result
        return result

    async def setup_tables(self):
        """Setup database tables"""
        async with self._setup_tables_lock:
            create_tables_queries = [
                """
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    transaction_type TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    price REAL NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    profit_loss REAL DEFAULT 0
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS market_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    timestamp INTEGER NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    volume REAL NOT NULL,
                    UNIQUE(symbol, timestamp)
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS highest_prices (
                    symbol TEXT PRIMARY KEY,
                    price REAL NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            ]

            for query in create_tables_queries:
                await self.execute_query(query)

            # Create indexes for better performance
            index_queries = [
                "CREATE INDEX IF NOT EXISTS idx_transactions_symbol ON transactions(symbol)",
                "CREATE INDEX IF NOT EXISTS idx_transactions_timestamp ON transactions(timestamp)",
                "CREATE INDEX IF NOT EXISTS idx_market_data_symbol ON market_data(symbol)",
                "CREATE INDEX IF NOT EXISTS idx_market_data_timestamp ON market_data(timestamp)"
            ]

            for query in index_queries:
                await self.execute_query(query)

    async def get_last_buy_price(self, symbol: str) -> Optional[float]:
        """Get the last buy price for a symbol"""
        query = """
            SELECT price
            FROM transactions
            WHERE symbol = ? AND transaction_type = 'buy'
            ORDER BY timestamp DESC
            LIMIT 1
        """
        result = await self.cached_query(query, (symbol,))
        return float(result[0]['price']) if result else None

    async def get_highest_price(self, symbol: str) -> Optional[float]:
        """Get the highest price recorded for a symbol"""
        query = """
            SELECT price
            FROM highest_prices
            WHERE symbol = ?
        """
        result = await self.cached_query(query, (symbol,))
        return float(result[0]['price']) if result else 0

    async def update_highest_price(self, symbol: str, price: float) -> bool:
        """Update the highest price for a symbol"""
        query = """
            INSERT OR REPLACE INTO highest_prices (symbol, price)
            VALUES (?, ?)
        """
        await self.execute_query(query, (symbol, price))
        return True

    async def save_transaction(self, symbol: str, transaction_type: str, quantity: float, price: float) -> bool:
        """Save a transaction to the database"""
        query = """
            INSERT INTO transactions (symbol, transaction_type, quantity, price)
            VALUES (?, ?, ?, ?)
        """
        await self.execute_query(query, (symbol, transaction_type, quantity, price))
        return True

    async def get_market_data(self, symbol: str, start_time: datetime, end_time: datetime) -> List[Dict]:
        """Get market data for a symbol within a time range"""
        query = """
            SELECT timestamp, open, high, low, close, volume
            FROM market_data
            WHERE symbol = ? AND timestamp BETWEEN ? AND ?
            ORDER BY timestamp DESC
        """
        parameters = (symbol, start_time.timestamp(), end_time.timestamp())
        return await self.execute_query(query, parameters)

    async def get_trade_history(self, symbol: str, limit: int = 100) -> List[Dict]:
        """Get trade history for a symbol"""
        query = """
            SELECT * FROM transactions
            WHERE symbol = ?
            ORDER BY timestamp DESC
            LIMIT ?
        """
        parameters = (symbol, limit)
        return await self.execute_query(query, parameters)

# Initialize database manager
db_manager = DatabaseManager()
