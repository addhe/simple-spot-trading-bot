# trading_bot/services/binance_service.py
from typing import Dict, Any, Optional
from binance.client import Client
from binance.exceptions import BinanceAPIException

from ..config.settings import Settings
from ..utils.exceptions import TradingBotException
from ..utils.audit_logger import AuditLogger


class BinanceService:
    """Service layer for Binance API interactions."""
    
    def __init__(
        self, 
        settings: Settings, 
        logger: Optional[AuditLogger] = None
    ):
        """
        Initialize Binance service with secure configuration.
        
        Args:
            settings: Application configuration settings
            logger: Optional audit logger instance
        """
        self._client = Client(
            api_key=settings.api_key, 
            api_secret=settings.secret_key
        )
        self._logger = logger or AuditLogger()
        self._symbol = settings.symbol
    
    def get_current_price(self) -> float:
        """
        Retrieve current market price for configured symbol.
        
        Returns:
            Current market price as a float
        
        Raises:
            TradingBotException: If price retrieval fails
        """
        try:
            ticker = self._client.get_symbol_ticker(symbol=self._symbol)
            price = float(ticker['price'])
            self._logger.info(f"Current {self._symbol} price: {price}")
            return price
        except BinanceAPIException as e:
            self._logger.error(f"Price retrieval failed: {e}")
            raise TradingBotException(f"Price retrieval error: {e}")