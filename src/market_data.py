# src/market_data.py
import asyncio
import logging
import json
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Dict, Optional, Callable, List, AsyncGenerator

import aiofiles
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from async_lru import alru_cache
from binance import AsyncClient, BinanceSocketManager
from binance.exceptions import BinanceAPIException
from pydantic import BaseModel, ValidationError
from src.formatters import truncate_decimal

from config.settings import AppSettings
from src.utils import (
    async_retry,
    error_handler,
    financial_precision,
    truncate_to_step,
    validate_timestamp
)

logger = logging.getLogger(__name__)

class MarketEvent(BaseModel):
    """Pydantic model for validating market data events"""
    symbol: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    interval: str

    @classmethod
    def from_websocket(cls, msg: dict):
        k = msg['k']
        return cls(
            symbol=msg['s'],
            timestamp=datetime.fromtimestamp(k['t'] / 1000),
            open=Decimal(k['o']),
            high=Decimal(k['h']),
            low=Decimal(k['l']),
            close=Decimal(k['c']),
            volume=Decimal(k['v']),
            interval=k['i']
        )

class CandleStick(BaseModel):
    """Historical candlestick data model"""
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    timestamp: datetime
    trades: int
    quote_volume: Decimal

class MarketData:
    """Real-time market data provider with multi-layer caching"""
    
    def __init__(self, client: AsyncClient, settings: AppSettings):
        self.client = client
        self.settings = settings
        self.bsm: Optional[BinanceSocketManager] = None
        self._websocket_tasks: List[asyncio.Task] = []
        self._subscriptions: Dict[str, List[Callable[[MarketEvent], None]]] = {}
        self._price_cache: Dict[str, Decimal] = {}
        self._historical_cache = {}
        self.data_dir = Path(settings.data_dir) / "market_data"
        self.data_dir.mkdir(parents=True, exist_ok=True)

    async def initialize(self):
        """Initialize WebSocket connections and background tasks"""
        self.bsm = BinanceSocketManager(
            self.client,
            user_timeout=self.settings.websocket_timeout
        )
        await self._connect_websockets()
        asyncio.create_task(self._cache_janitor())

    async def _connect_websockets(self):
        """Connect to WebSocket streams with reconnection logic"""
        for symbol in self.settings.trading_pairs:
            task = asyncio.create_task(
                self._manage_websocket(symbol),
                name=f"WS_{symbol}"
            )
            self._websocket_tasks.append(task)

    async def _manage_websocket(self, symbol: str):
        """WebSocket connection manager with reconnection"""
        while True:
            try:
                await self._listen_websocket(symbol)
            except Exception as e:
                logger.error(f"WebSocket error for {symbol}: {str(e)}")
                await asyncio.sleep(self.settings.websocket_reconnect_delay)

    async def _listen_websocket(self, symbol: str):
        """Listen and process WebSocket data for a symbol"""
        async with self.bsm.kline_socket(symbol, interval='1m') as socket:
            async for msg in socket:
                try:
                    event = MarketEvent.from_websocket(msg)
                    await self._process_event(event)
                except ValidationError as e:
                    logger.error(f"Invalid market event: {str(e)}")

    async def _process_event(self, event: MarketEvent):
        """Process and distribute validated market events"""
        self._price_cache[event.symbol] = event.close
        
        if event.symbol in self._subscriptions:
            for callback in self._subscriptions[event.symbol]:
                try:
                    await callback(event)
                except Exception as e:
                    logger.error(f"Subscription callback failed: {str(e)}")

    def subscribe(
        self,
        symbol: str,
        callback: Callable[[MarketEvent], None]
    ):
        """Subscribe to real-time market events"""
        if symbol not in self._subscriptions:
            self._subscriptions[symbol] = []
        self._subscriptions[symbol].append(callback)

    @alru_cache(maxsize=100, ttl=300)
    @async_retry(max_retries=3)
    @error_handler(notify=True)
    async def get_historical_data(
        self,
        symbol: str,
        interval: str = '1h',
        days: int = 7
    ) -> List[CandleStick]:
        """Get historical data with layered caching"""
        # Try memory cache
        if cached := self._historical_cache.get(symbol):
            if validate_timestamp(cached['timestamp']):
                return cached['data']

        # Try disk cache
        if disk_data := await self._load_disk_cache(symbol):
            self._historical_cache[symbol] = {
                'data': disk_data,
                'timestamp': datetime.now().timestamp()
            }
            return disk_data

        # Fetch from API
        fresh_data = await self._fetch_fresh_data(symbol, interval, days)
        await self._save_disk_cache(symbol, fresh_data)
        return fresh_data

    async def _load_disk_cache(self, symbol: str) -> Optional[List[CandleStick]]:
        """Load cached data from disk"""
        file_path = self.data_dir / f"{symbol}.parquet"
        try:
            async with aiofiles.open(file_path, 'rb') as f:
                data = await f.read()
                table = pa.ipc.open_stream(data).read_all()
                return [
                    CandleStick(
                        open=row['open'],
                        high=row['high'],
                        low=row['low'],
                        close=row['close'],
                        volume=row['volume'],
                        timestamp=row['timestamp'],
                        trades=row['trades'],
                        quote_volume=row['quote_volume']
                    )
                    for row in table.to_pylist()
                ]
        except Exception as e:
            logger.warning(f"Disk cache load failed: {str(e)}")
            return None

    async def _save_disk_cache(
        self,
        symbol: str,
        data: List[CandleStick]
    ):
        """Save data to disk cache"""
        file_path = self.data_dir / f"{symbol}.parquet"
        try:
            df = pd.DataFrame([d.dict() for d in data])
            table = pa.Table.from_pandas(df)
            
            async with aiofiles.open(file_path, 'wb') as f:
                writer = pa.ipc.new_stream(f, table.schema)
                writer.write(table)
                writer.close()
        except Exception as e:
            logger.error(f"Disk cache save failed: {str(e)}")

    async def _fetch_fresh_data(
        self,
        symbol: str,
        interval: str,
        days: int
    ) -> List[CandleStick]:
        """Fetch fresh data from exchange API"""
        end_time = datetime.now()
        start_time = end_time - timedelta(days=days)
        
        klines = await self.client.get_historical_klines(
            symbol=symbol,
            interval=interval,
            start_str=start_time.isoformat(),
            end_str=end_time.isoformat()
        )

        return [
            CandleStick(
                open=Decimal(str(k[1])),
                high=Decimal(str(k[2])),
                low=Decimal(str(k[3])),
                close=Decimal(str(k[4])),
                volume=Decimal(str(k[5])),
                timestamp=datetime.fromtimestamp(k[0] / 1000),
                trades=int(k[8]),
                quote_volume=Decimal(str(k[7]))
            )
            for k in klines
        ]

    @async_retry(max_retries=3)
    @error_handler()
    async def get_current_price(self, symbol: str) -> Decimal:
        """Get current price with fallback strategy"""
        try:
            return self._price_cache[symbol]
        except KeyError:
            ticker = await self.client.get_symbol_ticker(symbol=symbol)
            return financial_precision(ticker['price'])

    async def get_tick_size(self, symbol: str) -> Decimal:
        """Get exchange tick size for a symbol"""
        info = await self.client.get_symbol_info(symbol)
        filters = {f['filterType']: f for f in info['filters']}
        return Decimal(filters['PRICE_FILTER']['tickSize'])

    async def _cache_janitor(self):
        """Background task to manage cache resources"""
        while True:
            try:
                self._clean_price_cache()
                await self._clean_historical_cache()
                await asyncio.sleep(300)
            except Exception as e:
                logger.error(f"Cache janitor failed: {str(e)}")

    def _clean_price_cache(self):
        """Clean expired price cache entries"""
        expired = []
        for symbol, price in self._price_cache.items():
            if not validate_timestamp(price.timestamp, max_age=300):
                expired.append(symbol)
        for symbol in expired:
            del self._price_cache[symbol]

    async def _clean_historical_cache(self):
        """Clean historical cache based on LRU policy"""
        if len(self._historical_cache) > 100:
            oldest = sorted(
                self._historical_cache.items(),
                key=lambda x: x[1]['timestamp']
            )[:10]
            for symbol, _ in oldest:
                del self._historical_cache[symbol]

class PriceAlertSystem:
    """Smart price alert system with debouncing"""
    
    def __init__(self, market_data: MarketData):
        self.market_data = market_data
        self._thresholds: Dict[str, Dict[Decimal, List[Callable]]] = {}
        self._active_alerts: Dict[str, asyncio.Task] = {}

    def add_alert(
        self,
        symbol: str,
        price: Decimal,
        callback: Callable[[Decimal], None],
        tolerance: Decimal = Decimal('0.01')
    ):
        """Add price alert with debouncing"""
        if symbol not in self._thresholds:
            self._thresholds[symbol] = {}
            self.market_data.subscribe(symbol, self._check_alerts)

        key = truncate_to_step(price, tolerance)
        if key not in self._thresholds[symbol]:
            self._thresholds[symbol][key] = []
        
        self._thresholds[symbol][key].append(callback)

    async def _check_alerts(self, event: MarketEvent):
        """Check alerts with debouncing"""
        symbol = event.symbol
        current_price = event.close

        if symbol in self._active_alerts:
            return  # Prevent multiple triggers

        for threshold, callbacks in self._thresholds[symbol].items():
            if abs(current_price - threshold) <= self._tolerance:
                self._active_alerts[symbol] = asyncio.create_task(
                    self._trigger_alerts(symbol, current_price, callbacks)
                )
                break

    async def _trigger_alerts(
        self,
        symbol: str,
        price: Decimal,
        callbacks: List[Callable]
    ):
        """Trigger alerts with debouncing"""
        await asyncio.sleep(1)  # Debounce period
        for callback in callbacks:
            try:
                await callback(price)
            except Exception as e:
                logger.error(f"Alert callback failed: {str(e)}")
        del self._active_alerts[symbol]

class PricingModel:
    """Advanced pricing model with multiple calculation strategies"""
    
    def __init__(self, market_data: MarketData):
        self.market_data = market_data

    async def calculate_fair_value(
        self,
        symbol: str,
        model: str = 'VOLATILITY_WEIGHTED',
        params: dict = None
    ) -> Decimal:
        """Calculate fair value using selected model"""
        models = {
            'VOLATILITY_WEIGHTED': self._volatility_weighted,
            'VWAP': self._volume_weighted,
            'EMA': self._ema_based,
            'TIME_WEIGHTED': self._time_weighted
        }
        
        return await models[model](symbol, params or {})

    async def _volatility_weighted(
        self,
        symbol: str,
        params: dict
    ) -> Decimal:
        """Volatility-weighted average price"""
        data = await self.market_data.get_historical_data(symbol)
        returns = [c.close for c in data]
        volatility = pd.Series(returns).std()
        avg_price = sum(c.close for c in data) / len(data)
        return truncate_to_step(
            avg_price * (1 - volatility),
            await self.market_data.get_tick_size(symbol)
        )

    async def _volume_weighted(
        self,
        symbol: str,
        params: dict
    ) -> Decimal:
        """Volume-weighted average price"""
        data = await self.market_data.get_historical_data(symbol)
        total_volume = sum(c.volume for c in data)
        vwap = sum(c.close * c.volume for c in data) / total_volume
        return truncate_to_step(
            vwap,
            await self.market_data.get_tick_size(symbol)
        )

    async def _ema_based(
        self,
        symbol: str,
        params: dict
    ) -> Decimal:
        """Exponential moving average based pricing"""
        period = params.get('period', 20)
        data = await self.market_data.get_historical_data(symbol)
        closes = [float(c.close) for c in data]
        ema = pd.Series(closes).ewm(span=period).mean().iloc[-1]
        return truncate_to_step(
            Decimal(ema),
            await self.market_data.get_tick_size(symbol)
        )

    async def _time_weighted(
        self,
        symbol: str,
        params: dict
    ) -> Decimal:
        """Time-weighted average price"""
        data = await self.market_data.get_historical_data(symbol)
        total_time = data[-1].timestamp - data[0].timestamp
        weighted_sum = sum(
            c.close * (c.timestamp - data[0].timestamp).total_seconds()
            for c in data
        )
        return truncate_to_step(
            weighted_sum / total_time.total_seconds(),
            await self.market_data.get_tick_size(symbol)
        )