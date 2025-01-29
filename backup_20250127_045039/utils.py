from ratelimit import limits, sleep_and_retry
import re
from datetime import timedelta

class APIUtils:
    """Handles API rate limiting and utilities"""
    
    @staticmethod
    @sleep_and_retry
    @limits(calls=1200, period=timedelta(hours=1).seconds)
    def rate_limited_api_call(func):
        """Decorator for Binance API rate limiting"""
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        return wrapper

class InputValidator:
    """Validates and sanitizes user inputs"""
    
    @staticmethod
    def validate_symbol(symbol: str):
        if not re.match(r"^[A-Z]{6,10}$", symbol):
            raise ValueError(f"Invalid symbol format: {symbol}")
            
    @staticmethod
    def sanitize_log_entry(entry: str) -> str:
        return re.sub(r"(api_key|api_secret)=[^&]+", r"\1=***", entry)

class ConnectionPool:
    """Manages reusable HTTP connections"""
    
    def __init__(self):
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=10, 
            pool_maxsize=100
        )
        self.session.mount('https://', adapter)

    def get(self, url: str, **kwargs):
        return self.session.get(url, **kwargs)