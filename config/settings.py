# config/settings.py
from pathlib import Path
from typing import ClassVar, Literal, Annotated
from pydantic import (
    BaseModel,
    Field,
    SecretStr,
    HttpUrl,
    model_validator,
    confloat,
    conint,
    field_validator
)
from pydantic_settings import BaseSettings, SettingsConfigDict

# ----- Nested Models -----
class StrategyParams(BaseModel):
    """Strategy configuration parameters with validation"""
    stop_loss: Annotated[float, confloat(gt=0, le=20)] = 2.0  # 0-20%
    take_profit: Annotated[float, confloat(gt=0, le=50)] = 3.0  # 0-50%
    rsi_period: Annotated[int, conint(ge=5, le=50)] = 14
    ema_period: Annotated[int, conint(ge=5, le=200)] = 20
    max_leverage: Annotated[int, conint(ge=1, le=100)] = 10
    cooloff_period: Annotated[int, conint(ge=0)] = 300  # seconds

class ExchangeConfig(BaseModel):
    """Exchange connection parameters"""
    api_key: SecretStr
    api_secret: SecretStr
    base_url: HttpUrl = 'https://testnet.binance.vision/api'
    testnet: bool = True

class DatabaseConfig(BaseModel):
    url: str = 'sqlite:///data/db/bot_trading.db'
    echo: bool = False
    pool_size: int = 20
    max_overflow: int = 5

    @field_validator('url')
    def validate_db_url(cls, v):
        if not v.startswith(('sqlite:///', 'postgresql://', 'mysql://')):
            raise ValueError('Invalid database URL format')
        return v

class APIConfig(BaseModel):
    host: str = '0.0.0.0'
    port: int = 8000
    reload: bool = True
    cors_origins: list[str] = ['*']
    rate_limit: str = '100/minute'

# ----- Main Settings -----
class AppSettings(BaseSettings):
    # Environment Configuration
    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        env_nested_delimiter='__',
        case_sensitive=False
    )
    
    # Environment Mode
    environment: Literal['testnet', 'production'] = 'testnet'
    
    # Logging Configuration
    log_level: Literal['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'] = 'INFO'
    log_json: bool = False
    log_rotation: str = '10 MB'
    
    # Exchange Configuration
    exchange: ExchangeConfig = Field(
        default_factory=lambda: ExchangeConfig(
            api_key=SecretStr('your_api_key_here'),
            api_secret=SecretStr('your_api_secret_here'),
        )
    )
    
    # Trading Configuration
    trading_pairs: list[str] = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
    trading_interval: Literal['1m', '5m', '15m', '1h', '4h'] = '1m'
    max_concurrent_trades: Annotated[int, conint(ge=1, le=10)] = 3
    
    # Risk Management
    risk_per_trade: Annotated[float, confloat(gt=0, le=0.1)] = 0.02  # 0-10%
    risk_reserve: Annotated[float, confloat(ge=0, le=0.5)] = 0.1  # 10% reserve
    daily_loss_limit: Annotated[float, confloat(ge=0, le=0.3)] = 0.05  # 5%
    
    # Path Configuration
    data_dir: Path = Path('data')
    logs_dir: Path = Path('logs')
    cache_dir: Path = Path('cache')
    
    # Strategy Parameters
    strategy: StrategyParams = Field(default_factory=StrategyParams)
    
    # Telegram Configuration
    telegram_token: SecretStr = SecretStr('')
    telegram_chat_id: str = ''

    # Database Configuration
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    
    # API Configuration
    api: APIConfig = Field(default_factory=APIConfig)

    # ----- Validation -----
    @model_validator(mode='after')
    def validate_production(self):
        if self.environment == 'production':
            if self.exchange.testnet:
                raise ValueError("Production environment must use live exchange")
            
            api_key = self.exchange.api_key.get_secret_value()
            if not api_key.startswith('live_'):
                raise ValueError("Invalid production API key format")
                
            if not self.telegram_token.get_secret_value():
                raise ValueError("Telegram token required in production")
            
        return self

    @model_validator(mode='after')
    def validate_paths(self):
        self.data_dir.mkdir(exist_ok=True)
        self.logs_dir.mkdir(exist_ok=True)
        self.cache_dir.mkdir(exist_ok=True)
        return self

    @model_validator(mode='after')
    def validate_telegram(self):
        if self.telegram_token.get_secret_value() and not self.telegram_chat_id:
            raise ValueError("Telegram chat ID required when token is provided")
        return self

# Initialize settings instance
settings = AppSettings()