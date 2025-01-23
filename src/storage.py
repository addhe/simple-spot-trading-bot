# src/storage.py
import asyncio
import logging
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import List, Optional, Dict, AsyncGenerator

import aiosqlite
from pydantic import BaseModel, ValidationError

from config.settings import AppSettings
from src.models import OrderActivity

logger = logging.getLogger(__name__)

class OrderRecord(BaseModel):
    """Data model for order storage validation"""
    symbol: str
    side: str
    quantity: Decimal
    price: Decimal
    stop_loss: Optional[Decimal]
    take_profit: Optional[Decimal]
    created_at: datetime
    updated_at: datetime
    status: str  # 'open' | 'filled' | 'canceled'

class DataStorage:
    """Async SQLite storage with connection pooling and proper type handling"""
    
    def __init__(self, settings: AppSettings):
        self.db_path = Path(settings.DATA_DIR) / "trading_bot.db"
        self._conn_pool: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock()

    async def __aenter__(self):
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()

    async def initialize(self):
        """Initialize database connection and schema"""
        self._conn_pool = await aiosqlite.connect(self.db_path)
        await self._conn_pool.execute("PRAGMA journal_mode=WAL")
        
        await self._create_tables()
        await self._create_indexes()

    async def _create_tables(self):
        """Initialize database schema"""
        await self._conn_pool.execute('''
            CREATE TABLE IF NOT EXISTS activities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                quantity TEXT NOT NULL,
                price TEXT NOT NULL,
                stop_loss TEXT,
                take_profit TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT NOT NULL CHECK(status IN ('open', 'filled', 'canceled'))
            )
        ''')

    async def _create_indexes(self):
        """Create performance optimizations"""
        await self._conn_pool.execute('''
            CREATE INDEX IF NOT EXISTS idx_activities_symbol 
            ON activities (symbol)
        ''')
        await self._conn_pool.execute('''
            CREATE INDEX IF NOT EXISTS idx_activities_status 
            ON activities (status)
        ''')

    async def save_activity(self, activity: OrderActivity) -> int:
        """Save order activity with validation"""
        try:
            record = OrderRecord(
                **activity.__dict__,
                created_at=datetime.now(),
                updated_at=datetime.now(),
                status='open'
            )
        except ValidationError as e:
            logger.error(f"Invalid order activity: {e}")
            raise

        async with self._lock:
            cursor = await self._conn_pool.execute('''
                INSERT INTO activities (
                    symbol, side, quantity, price, 
                    stop_loss, take_profit, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                record.symbol,
                record.side,
                str(record.quantity),
                str(record.price),
                str(record.stop_loss) if record.stop_loss else None,
                str(record.take_profit) if record.take_profit else None,
                record.status
            ))
            await self._conn_pool.commit()
            return cursor.lastrowid

    async def update_order_status(self, order_id: int, status: str) -> bool:
        """Update order status with optimistic locking"""
        async with self._lock:
            cursor = await self._conn_pool.execute('''
                UPDATE activities 
                SET status = ?, updated_at = CURRENT_TIMESTAMP 
                WHERE id = ? AND status != ?
            ''', (status, order_id, status))
            await self._conn_pool.commit()
            return cursor.rowcount > 0

    async def load_bot_state(self) -> Dict[str, List[OrderActivity]]:
        """Load all open orders as bot state"""
        async with self._conn_pool.execute('''
            SELECT 
                symbol, side, quantity, price, 
                stop_loss, take_profit 
            FROM activities 
            WHERE status = 'open'
        ''') as cursor:
            rows = await cursor.fetchall()
            
        activities = []
        for row in rows:
            try:
                activities.append(OrderActivity(
                    symbol=row[0],
                    side=row[1],
                    quantity=Decimal(row[2]),
                    price=Decimal(row[3]),
                    stop_loss=Decimal(row[4]) if row[4] else None,
                    take_profit=Decimal(row[5]) if row[5] else None
                ))
            except (ValueError, TypeError) as e:
                logger.error(f"Failed to parse order record: {e}")
                
        return {'activities': activities}

    async def get_order_history(
        self, 
        symbol: Optional[str] = None,
        limit: int = 100
    ) -> AsyncGenerator[OrderRecord, None]:
        """Retrieve order history with filtering"""
        query = '''
            SELECT * FROM activities 
            WHERE 1=1
            {}
            ORDER BY created_at DESC 
            LIMIT ?
        '''.format("AND symbol = ?" if symbol else "")
        params = [symbol] if symbol else []
        params.append(limit)

        async with self._conn_pool.execute(query, params) as cursor:
            async for row in cursor:
                try:
                    yield OrderRecord(
                        symbol=row[1],
                        side=row[2],
                        quantity=Decimal(row[3]),
                        price=Decimal(row[4]),
                        stop_loss=Decimal(row[5]) if row[5] else None,
                        take_profit=Decimal(row[6]) if row[6] else None,
                        created_at=datetime.fromisoformat(row[7]),
                        updated_at=datetime.fromisoformat(row[8]),
                        status=row[9]
                    )
                except (ValueError, TypeError) as e:
                    logger.error(f"Invalid order record format: {e}")

    async def close(self):
        """Close database connection"""
        if self._conn_pool:
            await self._conn_pool.close()
            logger.info("Database connection closed")

    async def vacuum(self):
        """Optimize database storage"""
        async with self._lock:
            await self._conn_pool.execute("VACUUM")
            await self._conn_pool.commit()