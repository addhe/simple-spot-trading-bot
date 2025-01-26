# src/market_data.py
import asyncio
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Dict, Optional, Callable, List, AsyncGenerator, TypeVar

import aiofiles
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from async_lru import alru_cache
from binance import AsyncClient, BinanceSocketManager
from binance.exceptions import BinanceAPIException
from pydantic import BaseModel, ValidationError, Field

from config.settings import AppSettings
from src.decorators import AsyncRetry, AsyncErrorHandler, CircuitBreaker
from src.formatters import (
    format_decimal,
    truncate_decimal,
    FormatterConfig
)
from src.utils import (
    financial_precision,
    validate_timestamp,
    async_timed_task
)

logger = logging.getLogger(__name__)
T = TypeVar('T')

class MarketEvent(BaseModel):
    """Validated market data event with precision formatting"""
    symbol: str = Field(..., min_length=3, max_length=10)
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    interval: str = Field(..., pattern=r'^[1-5][mhdw]$')

    @classmethod
    def from_websocket(cls, msg: dict):
        k = msg['k']
        config = FormatterConfig()
        return cls(
            symbol=msg['s'],
            timestamp=datetime.fromtimestamp(k['t'] / 1000),
            open=truncate_decimal(Decimal(k['o']), config.price_precision),
            high=truncate_decimal(Decimal(k['h']), config.price_precision),
            low=truncate_decimal(Decimal(k['l']), config.price_precision),
            close=truncate_decimal(Decimal(k['c']), config.price_precision),
            volume=truncate_decimal(Decimal(k['v']), config.volume_precision),
            interval=k['i']
        )

class CandleStick(BaseModel):
    """Historical candlestick model with locale-safe formatting"""
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    timestamp: datetime
    trades: int
    quote_volume: Decimal

    def formatted_dict(self, config: FormatterConfig) -> dict:
        return {
            'open': format_decimal(self.open, config),
            'high': format_decimal(self.high, config),
            'low': format_decimal(self.low, config),
            'close': format_decimal(self.close, config),
            'volume': format_decimal(self.volume, config),
            'timestamp': self.timestamp.isoformat(),
            'trades': self.trades,
            'quote_volume': format_decimal(self.quote_volume, config)
        }

class MarketData:
    """Real-time market data provider with enhanced reliability patterns"""
    
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

        self.error_handler = AsyncErrorHandler(
            circuit_breaker_threshold=3,
            notification_channel='telegram'
        )
        self.retry_decorator = AsyncRetry(
            max_retries=3,
            exponential_backoff=True
        )
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout=60
        )

    @async_timed_task(threshold=timedelta(seconds=10))
    async def initialize(self):
        """Initialize WebSocket connections with circuit breaking"""
        try:
            self.bsm = BinanceSocketManager(
                self.client,
                user_timeout=self.settings.websocket_timeout
            )
            await self._connect_websockets()
            asyncio.create_task(self._cache_janitor())
        except Exception as e:
            self.error_handler.handle_error(
                e,
                context="WebSocket Initialization",
                critical=True
            )
            raise

    @CircuitBreaker(failure_threshold=3, recovery_timeout=300)
    async def _connect_websockets(self):
        """Connect to WebSocket streams with circuit breaker"""
        for symbol in self.settings.trading_pairs:
            task = asyncio.create_task(
                self._manage_websocket(symbol),
                name=f"WS_{symbol}"
            )
            self._websocket_tasks.append(task)

    async def _manage_websocket(self, symbol: str):
        """WebSocket connection manager with enhanced recovery"""
        retry_policy = self.retry_decorator(
            max_retries=5,
            allowed_exceptions=(BinanceAPIException,)
        )
        
        while True:
            try:
                await retry_policy(self._listen_websocket)(symbol)
            except Exception as e:
                self.error_handler.handle_error(
                    e,
                    context=f"WebSocket {symbol}",
                    notify=True
                )
                await asyncio.sleep(self.settings.websocket_reconnect_delay)

    async def _listen_websocket(self, symbol: str):
        """Process WebSocket data with structured logging"""
        async with self.bsm.kline_socket(symbol, interval='1m') as socket:
            async for msg in socket:
                try:
                    event = MarketEvent.from_websocket(msg)
                    await self._process_event(event)
                except ValidationError as e:
                    logger.error(
                        "Invalid market event",
                        extra={
                            'symbol': symbol,
                            'error_type': 'validation',
                            'error_details': str(e)
                        }
                    )

    async def _process_event(self, event: MarketEvent):
        """Distribute events with error-protected callbacks"""
        self._price_cache[event.symbol] = event.close
        
        if event.symbol in self._subscriptions:
            for callback in self._subscriptions[event.symbol]:
                try:
                    await self.error_handler.protect(callback)(event)
                except Exception as e:
                    logger.error(
                        "Subscription callback error",
                        extra={
                            'symbol': event.symbol,
                            'callback': callback.__name__,
                            'error_type': type(e).__name__
                        }
                    )

    def subscribe(
        self,
        symbol: str,
        callback: Callable[[MarketEvent], None]
    ):
        """Subscribe to market events with circuit breaker check"""
        if symbol not in self._subscriptions:
            self._subscriptions[symbol] = []
        self._subscriptions[symbol].append(
            self.circuit_breaker.protect(callback)
        )

    @alru_cache(maxsize=100, ttl=300)
    @AsyncRetry(max_retries=3, circuit_breaker=True)
    @AsyncErrorHandler(notify=True, context="HistoricalData")
    async def get_historical_data(
        self,
        symbol: str,
        interval: str = '1h',
        days: int = 7
    ) -> List[CandleStick]:
        """Get historical data with enhanced caching strategy"""
        if cached := self._historical_cache.get(symbol):
            if validate_timestamp(cached['timestamp']):
                return cached['data']

        if disk_data := await self._load_disk_cache(symbol):
            self._historical_cache[symbol] = {
                'data': disk_data,
                'timestamp': datetime.now().timestamp()
            }
            return disk_data

        fresh_data = await self._fetch_fresh_data(symbol, interval, days)
        await self._save_disk_cache(symbol, fresh_data)
        return fresh_data

    async def _load_disk_cache(self, symbol: str) -> Optional[List[CandleStick]]:
        """Load cached data from disk with error handling"""
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
            logger.warning(
                "Disk cache load failed",
                extra={
                    'symbol': symbol,
                    'error_type': type(e).__name__
                }
            )
            return None

    async def _save_disk_cache(
        self,
        symbol: str,
        data: List[CandleStick]
    ):
        """Save data to disk cache with structured logging"""
        file_path = self.data_dir / f"{symbol}.parquet"
        try:
            df = pd.DataFrame([d.dict() for d in data])
            table = pa.Table.from_pandas(df)
            
            async with aiofiles.open(file_path, 'wb') as f:
                writer = pa.ipc.new_stream(f, table.schema)
                writer.write(table)
                writer.close()
        except Exception as e:
            logger.error(
                "Disk cache save failed",
                extra={
                    'symbol': symbol,
                    'error_type': type(e).__name__
                }
            )

    async def _fetch_fresh_data(
        self,
        symbol: str,
        interval: str,
        days: int
    ) -> List[CandleStick]:
        """Fetch fresh data from exchange API with precision handling"""
        end_time = datetime.now()
        start_time = end_time - timedelta(days=days)
        
        klines = await self.client.get_historical_klines(
            symbol=symbol,
            interval=interval,
            start_str=start_time.isoformat(),
            end_str=end_time.isoformat()
        )

        config = FormatterConfig()
        return [
            CandleStick(
                open=truncate_decimal(Decimal(str(k[1])), config.price_precision),
                high=truncate_decimal(Decimal(str(k[2])), config.price_precision),
                low=truncate_decimal(Decimal(str(k[3])), config.price_precision),
                close=truncate_decimal(Decimal(str(k[4])), config.price_precision),
                volume=truncate_decimal(Decimal(str(k[5])), config.volume_precision),
                timestamp=datetime.fromtimestamp(k[0] / 1000),
                trades=int(k[8]),
                quote_volume=truncate_decimal(Decimal(str(k[7])), config.volume_precision)
            )
            for k in klines
        ]

    @AsyncRetry(max_retries=3)
    @AsyncErrorHandler()
    async def get_current_price(self, symbol: str) -> Decimal:
        """Get current price with fallback strategy"""
        try:
            return self._price_cache[symbol]
        except KeyError:
            ticker = await self.client.get_symbol_ticker(symbol=symbol)
            return financial_precision(ticker['price'])

    @CircuitBreaker(failure_threshold=3, recovery_timeout=60)
    async def get_tick_size(self, symbol: str) -> Decimal:
        """Get exchange tick size with circuit breaker"""
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
                logger.error(
                    "Cache janitor failed",
                    extra={
                        'error_type': type(e).__name__,
                        'error_details': str(e)
                    }
                )

    def _clean_price_cache(self):
        """Clean expired price cache entries"""
        expired = [
            symbol for symbol, price in self._price_cache.items()
            if not validate_timestamp(price.timestamp, max_age=300)
        ]
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
    """Smart price alert system with debouncing and circuit breaking"""
    
    def __init__(self, market_data: MarketData):
        self.market_data = market_data
        self._thresholds: Dict[str, Dict[Decimal, List[Callable]]] = {}
        self._active_alerts: Dict[str, asyncio.Task] = {}
        self.alert_circuit = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout=300
        )

    def add_alert(
        self,
        symbol: str,
        price: Decimal,
        callback: Callable[[Decimal], None],
        tolerance: Decimal = Decimal('0.01')
    ):
        """Add protected price alert with debouncing"""
        protected_callback = self.alert_circuit.protect(callback)
        
        if symbol not in self._thresholds:
            self._thresholds[symbol] = {}
            self.market_data.subscribe(symbol, self._check_alerts)

        key = truncate_to_step(price, tolerance)
        if key not in self._thresholds[symbol]:
            self._thresholds[symbol][key] = []
        
        self._thresholds[symbol][key].append(protected_callback)

    async def _check_alerts(self, event: MarketEvent):
        """Check alerts with debouncing and error handling"""
        symbol = event.symbol
        current_price = event.close

        if symbol in self._active_alerts:
            return

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
        """Trigger alerts with debouncing and error protection"""
        await asyncio.sleep(1)
        for callback in callbacks:
            try:
                await callback(price)
            except Exception as e:
                logger.error(
                    "Alert callback failed",
                    extra={
                        'symbol': symbol,
                        'callback': callback.__name__,
                        'error_type': type(e).__name__
                    }
                )
        del self._active_alerts[symbol]

class PricingModel:
    """Advanced pricing model with multiple calculation strategies"""
    
    def __init__(self, market_data: MarketData):
        self.market_data = market_data
        self.error_handler = AsyncErrorHandler(
            circuit_breaker_threshold=3,
            notification_channel='telegram'
        )

    @AsyncRetry(max_retries=3)
    @AsyncErrorHandler(context="PricingModel")
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