# src/utils.py
import os
import sys
import time
import logging
import asyncio
import random
from functools import wraps
from typing import (
    TypeVar, Callable, Optional, Any,
    Coroutine, Type, Union, Dict, Tuple
)
from pathlib import Path
from decimal import Decimal, InvalidOperation
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
import aiohttp
import pytz
import logging.handlers
import json

from config.settings import AppSettings
from src.formatters import format_currency, truncate_decimal

# This module-level initialization happens first
settings = AppSettings()  # Correctly initialized once

# Type variables
F = TypeVar('F', bound=Callable[..., Any])
AsyncF = TypeVar('AsyncF', bound=Callable[..., Coroutine[Any, Any, Any]])

settings = AppSettings()
logger = logging.getLogger(__name__)

class StructuredFormatter(logging.Formatter):
    def format(self, record):
        log_data = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }
        return json.dumps(log_data)

def async_retry(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 30.0,
    jitter: float = 0.1,
    exceptions: Tuple[Type[Exception], ...] = (Exception,)
) -> Callable[[AsyncF], AsyncF]:
    """Decorator for retrying async operations with exponential backoff"""
    def decorator(func: AsyncF) -> AsyncF:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            current_delay = initial_delay
            for attempt in range(1, max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_retries:
                        logger.error(f"Final retry failed: {str(e)}")
                        raise
                    
                    # Calculate next delay with jitter
                    current_delay = min(
                        max_delay,
                        current_delay * 2 * (1 + jitter * random.random())
                    )
                    logger.warning(
                        f"Retrying {func.__name__} in {current_delay:.1f}s "
                        f"(attempt {attempt}/{max_retries})"
                    )
                    await asyncio.sleep(current_delay)
            raise RuntimeError("Retry logic failed unexpectedly")
        return wrapper
    return decorator

@async_retry(max_retries=3, initial_delay=1.0)
async def check_internet_connection() -> bool:
    """Check internet connectivity (alias untuk check_connectivity)"""
    return await check_connectivity()

@async_retry(max_retries=3, initial_delay=1.0)
async def check_exchange_status(url: str) -> bool:
    """Check exchange API status"""
    result = await check_service_health(url, "/api/v3/ping")
    return result["status"] == 200

def async_error_handler(message: str, notify: bool = False):
    """Decorator untuk handling error pada async function"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                logger.error(f"{message}: {str(e)}", exc_info=True)
                if notify:
                    from src.telegram_notifier import TelegramNotifier  # Lazy import
                    async with TelegramNotifier(AppSettings()) as notifier:
                        await notifier.notify_error(e, context=func.__name__)
                raise
        return wrapper
    return decorator

def configure_logging(logs_dir: Union[str, Path] = "logs") -> None:
    """Configure centralized logging with structured JSON format"""
    logs_path = Path(logs_dir)
    logs_path.mkdir(parents=True, exist_ok=True)

    class StructuredFormatter(logging.Formatter):
        def format(self, record):
            return {
                "timestamp": self.formatTime(record),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
                "module": record.module,
                "function": record.funcName,
                "line": record.lineno
            }

    file_handler = logging.handlers.RotatingFileHandler(
        filename=logs_path / "trading_bot.log",
        maxBytes=10*1024*1024,
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setFormatter(StructuredFormatter())

    console_handler = logging.StreamHandler()
    if settings.environment == 'production':
        console_handler.setLevel(logging.WARNING)
    else:
        from rich.logging import RichHandler
        console_handler = RichHandler(show_time=False, show_path=False)
    
    # Remove the local settings initialization here
    logging.basicConfig(
        level=logging.getLevelName(settings.log_level),  # Now uses module-level settings
        handlers=[file_handler, console_handler],
        force=True
    )
    logging.captureWarnings(True)

@asynccontextmanager
async def async_timed(name: str = "Operation") -> Any:
    """Context manager for async operation timing"""
    start = time.monotonic()
    try:
        yield
    finally:
        duration = time.monotonic() - start
        logger.info(f"{name} completed in {duration:.2f}s")

@async_retry(max_retries=3, initial_delay=1.0)
async def check_connectivity(
    url: str = "https://connectivity.binance.com",
    timeout: int = 5
) -> bool:
    """Check network connectivity with custom endpoint"""
    try:
        async with aiohttp.ClientSession(
            headers={"User-Agent": "TradingBot/1.0"}
        ) as session:
            async with session.get(url, timeout=timeout) as response:
                return response.status == 204
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        logger.error(f"Connectivity check failed: {str(e)}")
        return False

@async_retry()
async def check_service_health(
    service_url: str,
    endpoint: str = "/api/v3/ping",
    timeout: int = 3
) -> Dict[str, Any]:
    """Check service health with detailed diagnostics"""
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{service_url}{endpoint}",
            timeout=timeout
        ) as response:
            return {
                "status": response.status,
                "latency": response.latency,
                "headers": dict(response.headers)
            }

def financial_precision(
    value: Union[str, float, Decimal],
    max_precision: int = 8
) -> Decimal:
    """Convert value to Decimal with safe precision handling"""
    try:
        decimal_value = Decimal(str(value)).normalize()
        _, _, exponent = decimal_value.as_tuple()
        if abs(exponent) > max_precision:
            return decimal_value.quantize(Decimal(10) ** -max_precision)
        return decimal_value
    except InvalidOperation as e:
        logger.error(f"Invalid financial value: {value} - {str(e)}")
        raise ValueError(f"Invalid financial value: {value}") from e

def validate_timestamp(
    timestamp: Union[int, float],
    max_age: int = 300
) -> bool:
    """Validate timestamp freshness"""
    current_time = datetime.now(pytz.utc).timestamp()
    return (current_time - timestamp) <= max_age

@async_retry()
@asynccontextmanager
async def async_session(
    headers: Optional[Dict] = None,
    timeout: int = 10
) -> Any:
    """Reusable async HTTP session context manager"""
    session = aiohttp.ClientSession(
        headers=headers or {"User-Agent": "TradingBot/1.0"},
        timeout=aiohttp.ClientTimeout(total=timeout)
    )
    try:
        yield session
    finally:
        await session.close()

def error_handler(
    notify: bool = False,
    raise_on: Tuple[Type[Exception], ...] = (),
    max_notifications: int = 5
) -> Callable[[AsyncF], AsyncF]:
    """Decorator for comprehensive error handling with circuit breaker"""
    notification_count = 0
    
    def decorator(func: AsyncF) -> AsyncF:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            nonlocal notification_count
            try:
                return await func(*args, **kwargs)
            except raise_on as e:
                raise
            except Exception as e:
                logger.error(f"Error in {func.__name__}: {str(e)}", exc_info=True)
                
                if notify and notification_count < max_notifications:
                    try:
                        from src.telegram_notifier import TelegramNotifier  # Lazy import
                        async with TelegramNotifier(AppSettings()) as notifier:
                            await notifier.notify_error(
                                error=e,
                                context=func.__name__
                            )
                        notification_count += 1
                    except Exception as notify_err:
                        logger.error(f"Failed to send error notification: {notify_err}")
                        
                if not raise_on:
                    raise

        return wrapper
    return decorator

def validate_configuration(settings: AppSettings) -> None:
    """Validate critical configuration values"""
    errors = []
    
    required_settings = [
        ("exchange.api_key", "Exchange API key"),
        ("exchange.api_secret", "Exchange API secret"),
        ("telegram_token", "Telegram token"),
        ("telegram_chat_id", "Telegram chat ID")
    ]
    
    for setting, name in required_settings:
        if not getattr(settings, setting, None):
            errors.append(f"{name} is required")
    
    if settings.risk_per_trade > Decimal('0.1'):
        errors.append("Risk per trade cannot exceed 10%")
    
    if errors:
        logger.critical("Configuration validation failed:\n- " + "\n- ".join(errors))
        sys.exit(1)

def percentage_change(
    initial: Decimal,
    final: Decimal
) -> Decimal:
    """Calculate percentage change with safe division"""
    if initial == 0:
        return Decimal('Infinity') if final > 0 else Decimal('-Infinity')
    return ((final - initial) / initial) * 100

def truncate_to_step(
    value: Decimal,
    step_size: Union[str, Decimal],
    rounding: str = 'ROUND_DOWN'
) -> Decimal:
    """Truncate value to exchange step size precision"""
    step = Decimal(str(step_size)).normalize()
    if step == 0:
        return value
    
    quantizer = Decimal(1) / step
    return (value * quantizer).quantize(
        Decimal('1'),
        rounding=rounding
    ) / quantizer

def format_duration(seconds: float) -> str:
    """Format duration in human-readable format"""
    periods = [
        ('day', 86400),
        ('hour', 3600),
        ('minute', 60),
        ('second', 1)
    ]
    
    parts = []
    for period_name, period_seconds in periods:
        if seconds >= period_seconds:
            period_value, seconds = divmod(seconds, period_seconds)
            parts.append(f"{int(period_value)} {period_name}{'s' if period_value != 1 else ''}")
    
    return ", ".join(parts[:2]) if parts else "0 seconds"