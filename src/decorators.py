"""  
Modul untuk implementasi decorator async dengan fitur enterprise-grade.  
Mendukung retry cerdas, error handling terstruktur, dan circuit breaker pattern.  
"""  
  
import asyncio  
import logging  
from functools import wraps  
from typing import (  
    Any,  
    Callable,  
    Type,  
    Optional,  
    Union,  
    Tuple,  
    TypeVar,  
    Coroutine  
)  
from dataclasses import dataclass  
from datetime import datetime  
import time  
import os  
  
# Type variables untuk annotasi generik  
F = TypeVar('F', bound=Callable[..., Any])  
T = TypeVar('T')  
logger = logging.getLogger(__name__)  
  
@dataclass  
class DecoratorConfig:  
    """Konfigurasi global untuk decorators"""  
    MAX_RETRIES: int = int(os.getenv('DECORATOR_MAX_RETRIES', 5))  
    BASE_DELAY: float = float(os.getenv('DECORATOR_BASE_DELAY', 1.0))  
    CIRCUIT_BREAKER_THRESHOLD: int = int(os.getenv('DECORATOR_CIRCUIT_BREAKER_THRESHOLD', 3))  
    CIRCUIT_BREAKER_TIMEOUT: float = float(os.getenv('DECORATOR_CIRCUIT_BREAKER_TIMEOUT', 30.0))  
    DEFAULT_LOG_LEVEL: int = int(os.getenv('DECORATOR_DEFAULT_LOG_LEVEL', logging.ERROR))  
    NOTIFICATION_ENABLED: bool = os.getenv('DECORATOR_NOTIFICATION_ENABLED', 'False').lower() in ['true', '1', 't']  
  
class CircuitBreaker:  
    """Class untuk mengelola state circuit breaker"""  
      
    def __init__(self):  
        self._failure_count = 0  
        self._circuit_open = False  
        self._last_failure_time = 0.0  
        self._state_history = []  
  
    def record_failure(self, exception: Exception):  
        self._failure_count += 1  
        self._last_failure_time = time.monotonic()  
        self._state_history.append(("FAILURE", datetime.now(), exception.__class__.__name__, str(exception)))  
        if self._failure_count >= DecoratorConfig.CIRCUIT_BREAKER_THRESHOLD:  
            self._circuit_open = True  
            self._state_history.append(("OPEN", datetime.now()))  
            logger.critical("Circuit breaker triggered")  
  
    def reset(self):  
        self._failure_count = 0  
        self._circuit_open = False  
        self._state_history.append(("RESET", datetime.now()))  
        logger.info("Circuit breaker reset")  
  
    def is_open(self) -> bool:  
        if self._circuit_open:  
            elapsed = time.monotonic() - self._last_failure_time  
            if elapsed > DecoratorConfig.CIRCUIT_BREAKER_TIMEOUT:  
                self.reset()  
                return False  
            return True  
        return False  
  
class AsyncRetry:  
    """  
    Decorator class untuk retry async operation dengan exponential backoff dan circuit breaker.  
      
    Args:  
        retries (int): Jumlah maksimum retry.  
        delay (float): Delay awal sebelum retry.  
        backoff_factor (float): Faktor pengali untuk delay.  
        exceptions (Union[Type[Exception], Tuple[Type[Exception], ...]]): Jenis exception yang akan diretry.  
        circuit_breaker (Optional[CircuitBreaker]): Instance CircuitBreaker untuk digunakan.  
    """  
      
    def __init__(  
        self,  
        retries: int = DecoratorConfig.MAX_RETRIES,  
        delay: float = DecoratorConfig.BASE_DELAY,  
        backoff_factor: float = 2.0,  
        exceptions: Union[Type[Exception], Tuple[Type[Exception], ...]] = (Exception,),  
        circuit_breaker: Optional[CircuitBreaker] = None  
    ):  
        self.retries = retries  
        self.delay = delay  
        self.backoff_factor = backoff_factor  
        self.exceptions = exceptions  
        self.circuit_breaker = circuit_breaker or CircuitBreaker()  
  
    def __call__(self, func: F) -> F:  
        @wraps(func)  
        async def wrapper(*args, **kwargs) -> Coroutine[Any, Any, T]:  
            if self.circuit_breaker.is_open():  
                raise CircuitBreakerOpenError(  
                    f"Circuit open for {func.__name__}, skipping execution"  
                )  
  
            current_delay = self.delay  
            for attempt in range(1, self.retries + 1):  
                try:  
                    result = await func(*args, **kwargs)  
                    self.circuit_breaker.reset()  
                    return result  
                except self.exceptions as e:  
                    self.circuit_breaker.record_failure(e)  
                      
                    if attempt == self.retries:  
                        logger.error(  
                            "Operation failed after %d attempts",  
                            attempt,  
                            exc_info=True,  
                            extra={  
                                "function": func.__name__,  
                                "attempt": attempt,  
                                "circuit_state": self.circuit_breaker._state_history[-1]  
                            }  
                        )  
                        raise  
  
                    logger.warning(  
                        "Retry %d/%d for %s failed: %s",  
                        attempt,  
                        self.retries,  
                        func.__name__,  
                        str(e),  
                        extra={  
                            "backoff_delay": current_delay,  
                            "circuit_failures": self.circuit_breaker._failure_count  
                        }  
                    )  
                      
                    await asyncio.sleep(current_delay)  
                    current_delay *= self.backoff_factor  
            raise MaxRetriesExceededError(f"Max retries {self.retries} exceeded")  
  
        return wrapper  
  
class AsyncErrorHandler:  
    """  
    Decorator class untuk handling error async operation dengan structured logging.  
      
    Args:  
        context (str): Konteks operasi.  
        notify (bool): Apakah notifikasi harus dikirim.  
        log_level (int): Tingkat logging.  
    """  
      
    def __init__(  
        self,  
        context: str = "operation",  
        notify: bool = DecoratorConfig.NOTIFICATION_ENABLED,  
        log_level: int = DecoratorConfig.DEFAULT_LOG_LEVEL  
    ):  
        self.context = context  
        self.notify = notify  
        self.log_level = log_level  
        self._notifier = TelegramNotifier() if notify else None  
  
    def __call__(self, func: F) -> F:  
        @wraps(func)  
        async def wrapper(*args, **kwargs) -> Coroutine[Any, Any, T]:  
            try:  
                return await func(*args, **kwargs)  
            except Exception as e:  
                self._log_error(e)  
                self._send_notification(e)  
                raise  
        return wrapper  
  
    def _log_error(self, error: Exception) -> None:  
        logger.log(  
            self.log_level,  
            "Error in %s: %s",  
            self.context,  
            str(error),  
            exc_info=True,  
            extra={  
                "error_type": error.__class__.__name__,  
                "context": self.context,  
                "notified": self.notify,  
                "timestamp": datetime.utcnow().isoformat()  
            }  
        )  
  
    def _send_notification(self, error: Exception) -> None:  
        if self.notify and self._notifier:  
            message = (  
                f"🚨 Error in {self.context}\n"  
                f"• Type: {error.__class__.__name__}\n"  
                f"• Message: {str(error)}\n"  
                f"• Time: {datetime.utcnow().isoformat()}"  
            )  
            self._notifier.send(message)  
  
class CircuitBreakerOpenError(Exception):  
    """Exception khusus untuk state circuit breaker open"""  
    def __init__(self, message: str):  
        super().__init__(message)  
        self.timestamp = datetime.utcnow().isoformat()  
        self.state = "OPEN"  
  
class MaxRetriesExceededError(Exception):  
    """Exception untuk melebihi batas maksimum retry"""  
    def __init__(self, message: str):  
        super().__init__(message)  
        self.timestamp = datetime.utcnow().isoformat()  
        self.state = "RETRY_EXHAUSTED"  
  
# Contoh penggunaan  
if __name__ == "__main__":  
    @AsyncRetry(retries=3, delay=1)  
    @AsyncErrorHandler(context="database_operation", notify=True)  
    async def sample_operation():  
        pass  
