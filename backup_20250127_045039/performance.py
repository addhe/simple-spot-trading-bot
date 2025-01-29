# src/performance.py
import asyncio
import aiohttp
from typing import Optional

class ConnectionPool:
    """Async HTTP connection pool with singleton pattern and connection reuse"""
    
    _instance: Optional["ConnectionPool"] = None
    _lock = asyncio.Lock()
    
    def __init__(self):
        self.session = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(
                limit=20,
                keepalive_timeout=30
            )
        )

    @classmethod
    async def get_instance(cls) -> "ConnectionPool":
        """Get singleton instance with thread-safe initialization"""
        async with cls._lock:
            if cls._instance is None or cls._instance.session.closed:
                cls._instance = ConnectionPool()
            return cls._instance

    async def get(self, url: str, **kwargs) -> dict:
        """Execute async GET request"""
        async with self.session.get(url, **kwargs) as response:
            response.raise_for_status()
            return await response.json()

    @classmethod
    async def close(cls):
        """Cleanly close connection pool"""
        async with cls._lock:
            if cls._instance and not cls._instance.session.closed:
                await cls._instance.session.close()
                cls._instance = None