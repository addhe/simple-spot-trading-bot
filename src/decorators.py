# src/decorators.py
import asyncio
import logging
from functools import wraps
from typing import Callable, Any

logger = logging.getLogger(__name__)

def async_retry(retries: int = 3, delay: float = 1):
    def decorator(func: Callable[..., Any]):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            for i in range(retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    if i == retries - 1:
                        raise
                    logger.warning(f"Retry {i+1}/{retries} for {func.__name__}")
                    await asyncio.sleep(delay)
            return None
        return wrapper
    return decorator

def async_error_handler(context: str = "operation"):
    def decorator(func: Callable[..., Any]):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                logger.error(f"Error in {context}: {str(e)}", exc_info=True)
                raise
        return wrapper
    return decorator