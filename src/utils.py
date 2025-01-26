# src/utils.py (Refactored)
import os
import sys
import time
import logging
import asyncio
import random
import json
from functools import wraps
from typing import (
    TypeVar, Callable, Optional, Any,
    Coroutine, Type, Union, Dict, Tuple,
    Generator, AsyncGenerator
)
from pathlib import Path
from decimal import Decimal, InvalidOperation
from datetime import datetime, timedelta
from typing import Union, Optional
from contextlib import asynccontextmanager
import aiohttp
import pytz
from rich.logging import RichHandler

from config.settings import AppSettings
from src.telegram_notifier import TelegramNotifier, ErrorNotification

# Type variables
F = TypeVar('F', bound=Callable[..., Any])
AsyncF = TypeVar('AsyncF', bound=Callable[..., Coroutine[Any, Any, Any]])

class AsyncRetry:
    """Class-based async retry decorator with enhanced features"""
    def __init__(
        self,
        max_retries: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 30.0,
        jitter: float = 0.1,
        handled_errors: Tuple[Type[Exception], ...] = (Exception,)
    ):
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.jitter = jitter
        self.handled_errors = handled_errors

    def __call__(self, func: AsyncF) -> AsyncF:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            current_delay = self.initial_delay
            for attempt in range(1, self.max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except self.handled_errors as e:
                    if attempt == self.max_retries:
                        logger.error(
                            "Max retries exceeded",
                            extra={
                                "function": func.__name__,
                                "attempt": attempt,
                                "error": str(e)
                            }
                        )
                        raise

                    current_delay = self._calculate_delay(current_delay)
                    logger.warning(
                        "Retrying function",
                        extra={
                            "function": func.__name__,
                            "attempt": attempt,
                            "next_delay": current_delay,
                            "error": str(e)
                        }
                    )
                    await asyncio.sleep(current_delay)
            raise RuntimeError("Retry logic failed unexpectedly")
        return wrapper

    def _calculate_delay(self, current_delay: float) -> float:
        """Calculate next delay with exponential backoff and jitter"""
        new_delay = current_delay * 2 * (1 + self.jitter * random.random())
        return min(new_delay, self.max_delay)

class ErrorHandler:
    """Class-based error handler with circuit breaker pattern"""
    def __init__(
        self,
        notify: bool = False,
        raise_on: Tuple[Type[Exception], ...] = (),
        max_notifications: int = 5
    ):
        self.notify = notify
        self.raise_on = raise_on
        self.max_notifications = max_notifications
        self.notification_count = 0

    def __call__(self, func: AsyncF) -> AsyncF:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except self.raise_on as e:
                raise
            except Exception as e:
                self._handle_error(e, func.__name__)
                raise

        return wrapper

    def _handle_error(self, error: Exception, context: str) -> None:
        """Handle error logging and notifications"""
        logger.error(
            "Operation failed",
            extra={
                "context": context,
                "error_type": type(error).__name__,
                "error_message": str(error),
                "notification_sent": self.notify and
                    self.notification_count < self.max_notifications
            },
            exc_info=True
        )

        if self.notify and self.notification_count < self.max_notifications:
            try:
                asyncio.create_task(self._send_notification(error, context))
                self.notification_count += 1
            except Exception as notify_err:
                logger.error(
                    "Notification failed",
                    extra={"error": str(notify_err)}
                )

    async def _send_notification(self, error: Exception, context: str) -> None:
        """Send error notification through Telegram"""
        async with TelegramNotifier(AppSettings()) as notifier:
            await notifier.send(
                ErrorNotification.from_exception(error, context=context)
            )

def configure_logging(settings: AppSettings) -> None:
    """Centralized logging configuration with structured format"""
    logs_dir = Path(settings.logs_dir)
    logs_dir.mkdir(parents=True, exist_ok=True)

    # File handler with JSON formatting
    file_handler = logging.handlers.RotatingFileHandler(
        filename=logs_dir / "trading_bot.log",
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setFormatter(logging.Formatter(
        fmt='{"time": "%(asctime)s", "level": "%(levelname)s", "name": "%(name)s", '
            '"message": "%(message)s", "module": "%(module)s", "func": "%(funcName)s"}',
        datefmt="%Y-%m-%dT%H:%M:%SZ"
    ))

    # Console handler with Rich formatting
    console_handler = RichHandler(
        show_time=False,
        show_path=False,
        markup=True
    ) if settings.environment == 'development' else logging.StreamHandler()

    logging.basicConfig(
        level=settings.log_level,
        handlers=[file_handler, console_handler],
        force=True
    )
    logging.captureWarnings(True)

@AsyncRetry(max_retries=3, initial_delay=1.0)
async def check_connectivity(
    url: str = "https://api.binance.com/api/v3/ping",
    timeout: int = 5
) -> bool:
    """Check network connectivity with enhanced diagnostics"""
    try:
        async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(ssl=False),
            headers={"User-Agent": "TradingBot/1.0"},
            timeout=aiohttp.ClientTimeout(total=timeout)
        ) as session:
            async with session.get(url) as response:
                return response.status == 200
    except Exception as e:
        logger.error(
            "Connectivity check failed",
            extra={
                "url": url,
                "timeout": timeout,
                "error": str(e)
            }
        )
        return False

@ErrorHandler(notify=True, max_notifications=3)
@AsyncRetry(max_retries=2, handled_errors=(aiohttp.ClientError,))
async def check_service_health(
    service_url: str,
    endpoint: str = "/api/v3/ping"
) -> Dict[str, Any]:
    """Check service health with detailed metrics"""
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{service_url}{endpoint}") as response:
            return {
                "status": response.status,
                "latency": response.latency,
                "headers": dict(response.headers)
            }

def financial_precision(
    value: Union[str, float, Decimal],
    max_precision: int = 8
) -> Decimal:
    """Safely convert to Decimal with precision control"""
    try:
        decimal_value = Decimal(str(value)).normalize()
        return decimal_value.quantize(Decimal(10) ** -max_precision)
    except InvalidOperation as e:
        logger.error(
            "Invalid financial value",
            extra={
                "input_value": str(value),
                "max_precision": max_precision
            }
        )
        raise ValueError(f"Invalid financial value: {value}") from e

@asynccontextmanager
async def async_timed_task(
    task_name: str,
    warn_threshold: float = 5.0  # Ubah ke float (detik)
) -> AsyncGenerator[None, None]:
    """Context manager untuk timing async operation dengan alert"""
    start_time = time.monotonic()
    try:
        yield
    finally:
        duration = time.monotonic() - start_time
        logger.info(
            "Task completed",
            extra={
                "task_name": task_name,
                "duration": f"{duration:.2f}s",
                "threshold_exceeded": duration > warn_threshold
            }
        )

def validate_timestamp(
    timestamp: Union[int, float, datetime],
    tolerance: int = 300,  # 5 menit dalam detik
    timezone: Optional[str] = "UTC"
) -> datetime:
    """
    Validasi dan konversi timestamp ke datetime object dengan:
    - Support multiple input types (unix, float, datetime)
    - Tolerance window untuk mencegah stale/future data
    - Timezone awareness
    
    Args:
        timestamp: Input timestamp (unix int/float atau datetime object)
        tolerance: Jumlah detik maksimum deviasi dari waktu saat ini
        timezone: Zona waktu target (default UTC)
    
    Returns:
        datetime: Objek datetime yang sudah divalidasi
    
    Raises:
        ValueError: Jika timestamp di luar tolerance window
        TypeError: Jika tipe input tidak valid
    """
    current_time = datetime.now(pytz.utc)
    
    # Konversi ke datetime object
    if isinstance(timestamp, (int, float)):
        dt = datetime.fromtimestamp(timestamp, tz=pytz.utc)
    elif isinstance(timestamp, datetime):
        dt = timestamp if timestamp.tzinfo else timestamp.replace(tzinfo=pytz.utc)
    else:
        raise TypeError(f"Invalid timestamp type: {type(timestamp)}")
    
    # Konversi timezone
    if timezone:
        target_tz = pytz.timezone(timezone)
        dt = dt.astimezone(target_tz)
        current_time = current_time.astimezone(target_tz)
    
    # Validasi tolerance window
    time_diff = abs((dt - current_time).total_seconds())
    if time_diff > tolerance:
        raise ValueError(
            f"Timestamp deviation {time_diff}s exceeds tolerance ({tolerance}s)\n"
            f"Input time: {dt.isoformat()}\n"
            f"Current time: {current_time.isoformat()}"
        )
    
    return dt

def validate_configuration(settings: AppSettings) -> bool:
    """Validate critical configuration values with detailed reporting"""
    validation_errors = []

    required_settings = [
        (settings.exchange.api_key, "Exchange API key"),
        (settings.exchange.api_secret, "Exchange API secret"),
        (settings.telegram_token, "Telegram token"),
        (settings.telegram_chat_id, "Telegram chat ID")
    ]

    for value, name in required_settings:
        if not value:
            validation_errors.append(f"{name} is required")

    if not (Decimal('0.01') <= settings.risk_per_trade <= Decimal('0.1')):
        validation_errors.append("Risk per trade must be between 1-10%")

    if validation_errors:
        logger.error(
            "Configuration validation failed",
            extra={
                "errors": validation_errors,
                "invalid_settings": [
                    setting[1] for setting in required_settings
                    if not setting[0]
                ]
            }
        )
        return False

    return True

# Helper functions with improved type hints
def truncate_to_step(
    value: Decimal,
    step_size: Union[str, Decimal],
    rounding: str = 'ROUND_DOWN'
) -> Decimal:
    """Precision-aware truncation for exchange-compatible values"""
    step = Decimal(str(step_size)).normalize()
    if step == 0:
        return value

    quantized_value = (value / step).to_integral_value(
        rounding=rounding
    ) * step
    return quantized_value.normalize()

def format_duration(seconds: float) -> str:
    """Human-readable duration formatting with precision control"""
    time_units = [
        ('day', 86400),
        ('hour', 3600),
        ('minute', 60),
        ('second', 1)
    ]

    components = []
    for unit, divisor in time_units:
        if seconds >= divisor or (not components and divisor == 1):
            value, seconds = divmod(seconds, divisor)
            components.append(f"{int(value)} {unit}{'s' if value != 1 else ''}")

    return ", ".join(components[:2]) or "0 seconds"
