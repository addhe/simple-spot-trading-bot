# src/core/exceptions.py
from typing import Optional


class TradingBotError(Exception):
    """Base exception class for trading bot errors."""

    def __init__(
        self, 
        message: str, 
        error_code: str = "UNKNOWN_ERROR"
    ) -> None:
        self.error_code = error_code
        super().__init__(f"[{error_code}] {message}")


class MarketDataError(TradingBotError):
    """Raised when market data operations fail."""

    def __init__(
        self, 
        message: str, 
        original_error: Optional[Exception] = None
    ) -> None:
        super().__init__(
            f"Market data error: {message}",
            error_code="MARKET_DATA_ERROR"
        )
        self.original_error = original_error


class OrderError(TradingBotError):
    """Raised when order operations fail."""

    def __init__(
        self, 
        message: str, 
        order_id: Optional[str] = None
    ) -> None:
        super().__init__(
            f"Order error: {message}",
            error_code="ORDER_ERROR"
        )
        self.order_id = order_id


class RiskManagementError(TradingBotError):
    """Raised when risk management checks fail."""

    def __init__(self, message: str) -> None:
        super().__init__(
            f"Risk management error: {message}",
            error_code="RISK_ERROR"
        )