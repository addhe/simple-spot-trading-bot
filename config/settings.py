# config/settings.py
from typing import Literal, Optional
from pydantic import (
    BaseModel, 
    Field, 
    ValidationInfo, 
    field_validator
)
from pydantic_settings import BaseSettings


class ExchangeConfig(BaseModel):
    """Binance exchange configuration model."""

    api_key: str = Field(
        description="Binance API key",
        min_length=64,
        max_length=64
    )
    api_secret: str = Field(
        description="Binance API secret",
        min_length=64,
        max_length=64
    )


class StrategyConfig(BaseModel):
    """Trading strategy configuration model."""

    type: Literal['sma_crossover', 'rsi', 'macd'] = 'sma_crossover'
    short_window: int = Field(
        default=10,
        description="Short period moving average window",
        gt=0,
        le=100
    )
    long_window: int = Field(
        default=50,
        description="Long period moving average window",
        gt=0,
        le=200
    )
    stop_loss: float = Field(
        default=2.0,
        description="Stop loss percentage",
        gt=0,
        le=10
    )


class Settings(BaseSettings):
    """Comprehensive trading bot configuration."""

    symbol: str = Field(
        description="Trading pair symbol",
        min_length=6,
        max_length=10
    )
    
    exchange: ExchangeConfig
    strategy: StrategyConfig = StrategyConfig()
    
    risk_per_trade: float = Field(
        default=0.02,
        description="Risk percentage per trade",
        gt=0,
        le=0.1
    )
    
    log_level: Literal['DEBUG', 'INFO', 'WARNING', 'ERROR'] = 'INFO'

    @field_validator('symbol')
    @classmethod
    def validate_symbol(cls, value: str) -> str:
        """Validate trading symbol format."""
        if not value.isupper() or not value.endswith('USDT'):
            raise ValueError("Symbol must be uppercase and end with 'USDT'")
        return value

    class Config:
        """Pydantic settings configuration."""
        
        env_file = '.env'
        env_prefix = 'TRADING_BOT_'
        case_sensitive = False