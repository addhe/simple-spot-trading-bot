# src/strategy.py
import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Optional, List, Type, AsyncGenerator

import pandas as pd
from async_lru import alru_cache
from pydantic import BaseModel, Field, ValidationError
from pytz import UTC

from config.settings import AppSettings
from src.market_data import MarketData
from src.utils import (
    async_retry,
    error_handler,
    financial_precision,
    truncate_to_step,
    validate_timestamp
)
from src.telegram_notifier import TelegramNotifier

logger = logging.getLogger(__name__)

class StrategyConfig(BaseModel):
    """Base configuration model for strategies"""
    name: str
    version: str = "1.0.0"
    enabled: bool = True
    risk_multiplier: float = Field(1.0, ge=0.5, le=3.0)
    max_retries: int = Field(3, ge=1, le=10)

class StrategyResult(BaseModel):
    """Standardized strategy decision output"""
    signal: str  # buy | sell | hold
    confidence: float
    parameters: dict
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

class TradingStrategy(ABC):
    """Abstract base class for all trading strategies"""
    
    def __init__(
        self,
        symbol: str,
        market_data: MarketData,
        config: StrategyConfig
    ):
        self.symbol = symbol
        self.market_data = market_data
        self.config = config
        self._last_calculated: Optional[datetime] = None

    @abstractmethod
    async def analyze(self) -> StrategyResult:
        """Main analysis method returning strategy decision"""
        pass

    @abstractmethod
    async def calculate_risk_parameters(
        self, 
        price: Decimal
    ) -> Dict[str, Decimal]:
        """Calculate SL/TP and other risk parameters"""
        pass

    async def is_fresh(self) -> bool:
        """Check if analysis is recent enough"""
        if not self._last_calculated:
            return False
        return (datetime.now(UTC) - self._last_calculated) < timedelta(minutes=1)

class PriceActionConfig(StrategyConfig):
    """Configuration for Price Action strategy"""
    atr_period: int = Field(14, ge=5, le=50)
    ma_period: int = Field(10, ge=5, le=200)
    base_offset: float = Field(0.05, ge=0.01, le=0.1)
    volatility_multiplier: float = Field(0.02, ge=0.01, le=0.1)

class PriceActionStrategy(TradingStrategy):
    """Volatility-adjusted price action strategy"""
    
    def __init__(
        self,
        symbol: str,
        market_data: MarketData,
        config: PriceActionConfig
    ):
        super().__init__(symbol, market_data, config)
        self._cache = {}

    @alru_cache(maxsize=10, ttl=300)
    @async_retry(max_retries=3)
    @error_handler(notify=True)
    async def get_historical_data(self) -> pd.DataFrame:
        """Get historical data with caching"""
        df = await self.market_data.get_historical_data(
            self.symbol,
            days=7,
            interval='1h'
        )
        return self._process_data(df)

    def _process_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Process raw market data"""
        required_cols = ['timestamp', 'open', 'high', 'low', 'close']
        if not all(col in df.columns for col in required_cols):
            raise ValueError("Missing required columns in historical data")

        df = df[required_cols].copy()
        df['returns'] = df['close'].pct_change()
        return df.dropna()

    async def calculate_volatility(self) -> Decimal:
        """Calculate normalized volatility using ATR"""
        df = await self.get_historical_data()
        if df.empty:
            return Decimal(0)

        high_low = df['high'] - df['low']
        high_close = (df['high'] - df['close'].shift()).abs()
        low_close = (df['low'] - df['close'].shift()).abs()
        
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = true_range.rolling(self.config.atr_period).mean().iloc[-1]
        return financial_precision(atr)

    async def calculate_moving_average(self) -> Decimal:
        """Calculate simple moving average"""
        df = await self.get_historical_data()
        if df.empty:
            return Decimal(0)

        ma = df['close'].rolling(self.config.ma_period).mean().iloc[-1]
        return financial_precision(ma)

    @error_handler()
    async def analyze(self) -> StrategyResult:
        """Generate trading signal based on price analysis"""
        current_price = await self.market_data.get_current_price(self.symbol)
        ma = await self.calculate_moving_average()
        volatility = await self.calculate_volatility()

        # Calculate dynamic thresholds
        buy_threshold = ma * (1 - (
            self.config.base_offset + 
            volatility * self.config.volatility_multiplier
        ))
        
        sell_threshold = ma * (1 + (
            self.config.base_offset + 
            volatility * self.config.volatility_multiplier
        ))

        # Generate signal
        if current_price <= buy_threshold:
            signal = 'buy'
            confidence = float((buy_threshold - current_price) / buy_threshold)
        elif current_price >= sell_threshold:
            signal = 'sell'
            confidence = float((current_price - sell_threshold) / sell_threshold)
        else:
            signal = 'hold'
            confidence = 0.0

        self._last_calculated = datetime.now(UTC)
        return StrategyResult(
            signal=signal,
            confidence=confidence,
            parameters={
                'ma': ma,
                'volatility': volatility,
                'buy_threshold': buy_threshold,
                'sell_threshold': sell_threshold
            }
        )

    async def calculate_risk_parameters(
        self, 
        price: Decimal
    ) -> Dict[str, Decimal]:
        """Calculate risk management parameters"""
        volatility = await self.calculate_volatility()
        ma = await self.calculate_moving_average()

        stop_loss = price * (1 - (
            self.config.base_offset + 
            volatility * self.config.risk_multiplier
        ))
        
        take_profit = price * (1 + (
            self.config.base_offset + 
            volatility * self.config.risk_multiplier * 1.5
        ))

        return {
            'stop_loss': truncate_to_step(
                stop_loss,
                await self.market_data.get_tick_size(self.symbol)
            ),
            'take_profit': truncate_to_step(
                take_profit,
                await self.market_data.get_tick_size(self.symbol)
            )
        }

class MovingAverageConfig(StrategyConfig):
    """Configuration for Moving Average Crossover strategy"""
    fast_period: int = Field(50, ge=10, le=100)
    slow_period: int = Field(200, ge=100, le=500)
    trend_threshold: float = Field(0.005, ge=0.001, le=0.01)

class MovingAverageStrategy(TradingStrategy):
    """Moving Average Crossover strategy implementation"""
    
    async def analyze(self) -> StrategyResult:
        """Implement MA crossover logic"""
        # Implementation example
        return StrategyResult(
            signal='hold',
            confidence=0.0,
            parameters={}
        )

class StrategyFactory:
    """Factory for creating strategy instances with dependency injection"""
    
    _registry = {
        'price_action': (PriceActionStrategy, PriceActionConfig),
        'moving_average': (MovingAverageStrategy, MovingAverageConfig)
    }

    @classmethod
    def create(
        cls,
        strategy_type: str,
        symbol: str,
        market_data: MarketData,
        config: dict
    ) -> TradingStrategy:
        """Create strategy instance with validated config"""
        if strategy_type not in cls._registry:
            raise ValueError(f"Unsupported strategy type: {strategy_type}")

        strategy_class, config_class = cls._registry[strategy_type]
        validated_config = config_class(**config)
        return strategy_class(symbol, market_data, validated_config)

    @classmethod
    def list_available_strategies(cls) -> List[str]:
        """Get list of registered strategy types"""
        return list(cls._registry.keys())