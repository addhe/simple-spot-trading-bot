# src/risk_management.py
from typing import Dict, Optional
import pandas as pd
from binance import Client
from .exceptions import RiskManagementError
from .utils import InputValidator

class RiskManager:
    """Handles risk calculations and portfolio risk management.

    Attributes:
        client: Binance API client instance
        risk_per_trade: Percentage of capital to risk per trade (0.01 = 1%)
        exposure: Dictionary tracking current position exposures
    """

    def __init__(self, client: Client, risk_per_trade: float = 0.01):
        self.client = client
        self.risk_per_trade = risk_per_trade
        self.exposure: Dict[str, float] = {}

    def calculate_position_size(
        self, symbol: str, entry_price: float, stop_loss: float
    ) -> float:
        """Calculate position size based on risk parameters.

        Args:
            symbol: Trading pair symbol (e.g., 'BTCUSDT')
            entry_price: Proposed entry price
            stop_loss: Stop-loss price

        Returns:
            Position size in base asset units

        Raises:
            RiskManagementError: If calculation fails
        """
        InputValidator.validate_symbol(symbol)

        try:
            balance = self._get_available_balance()
            risk_amount = balance * self.risk_per_trade
            risk_per_unit = abs(entry_price - stop_loss)

            if risk_per_unit <= 0:
                raise ValueError("Invalid risk per unit (<= 0)")

            size = round(risk_amount / risk_per_unit, 6)
            self._update_exposure(symbol, size)
            return size
        except Exception as e:
            raise RiskManagementError(
                f"Position calculation failed: {str(e)}", component="position_size"
            ) from e

    def calculate_take_profit(
        self,
        entry_price: float,
        strategy: str = "FIXED",
        data: Optional[pd.DataFrame] = None,
    ) -> float:
        """Calculate take-profit price using specified strategy.

        Args:
            entry_price: Entry price of the position
            strategy: TP strategy (FIXED, ATR, TRAILING)
            data: Historical data for volatility-based strategies

        Returns:
            Take-profit price

        Raises:
            RiskManagementError: If invalid strategy or inputs
        """
        try:
            strategies = {
                "FIXED": self._fixed_tp,
                "ATR": self._atr_based_tp,
                "TRAILING": self._trailing_stop,
            }

            if strategy not in strategies:
                raise ValueError(f"Invalid strategy: {strategy}")

            return strategies[strategy](entry_price, data)
        except Exception as e:
            raise RiskManagementError(
                f"Take-profit calculation failed: {str(e)}", component="take_profit"
            ) from e

    def get_portfolio_exposure(self) -> float:
        """Calculate total exposure across all positions.

        Returns:
            Total exposure in quote currency (USDT)
        """
        return sum(self.exposure.values())

    def validate_position_size(self, symbol: str, size: float):
        """Validate position against risk limits.

        Args:
            symbol: Trading pair symbol
            size: Proposed position size

        Raises:
            RiskManagementError: If position exceeds risk limits
        """
        max_size = self.calculate_max_position_value()
        current_exposure = self.get_portfolio_exposure()

        if size > max_size:
            raise RiskManagementError(
                f"Position size {size} exceeds max allowed {max_size}",
                component="position_validation",
            )

        if (current_exposure + size) > (self._get_available_balance() * 0.5):
            raise RiskManagementError(
                "New position would exceed 50% portfolio exposure",
                component="exposure_limit",
            )

    def calculate_max_position_value(self) -> float:
        """Calculate maximum allowable position value.

        Returns:
            Maximum position value in quote currency
        """
        equity = self._get_available_balance()
        return equity * self.risk_per_trade

    def calculate_leverage(self, position_size: float) -> float:
        """Calculate required leverage for position.

        Args:
            position_size: Size of the position in base asset

        Returns:
            Leverage ratio (position_size / equity)
        """
        equity = self._get_available_balance()
        return position_size / equity if equity > 0 else 0.0

    def _get_available_balance(self) -> float:
        """Get available USDT balance.

        Returns:
            Available USDT balance
        """
        account = self.client.get_account()
        return next(
            float(asset["free"])
            for asset in account["balances"]
            if asset["asset"] == "USDT"
        )

    def _fixed_tp(self, entry: float, *_) -> float:
        """Fixed percentage take-profit (2%)."""
        return entry * 1.02

    def _atr_based_tp(self, entry: float, data: pd.DataFrame) -> float:
        """Average True Range based take-profit."""
        if data is None or len(data) < 14:
            raise ValueError("ATR strategy requires 14 periods of historical data")

        high_low = data["high"] - data["low"]
        high_close = (data["high"] - data["close"].shift()).abs()
        low_close = (data["low"] - data["close"].shift()).abs()
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = true_range.mean()
        return entry + (atr * 3)

    def _trailing_stop(self, entry: float, data: pd.DataFrame) -> float:
        """Trailing stop based on recent volatility."""
        if data is None or len(data) < 5:
            raise ValueError("Trailing stop requires 5 periods of historical data")

        recent_volatility = data["close"].pct_change().std()
        return entry * (1 + (recent_volatility * 2))

    def _update_exposure(self, symbol: str, size: float):
        """Track position exposure.

        Args:
            symbol: Trading pair symbol
            size: Position size to add
        """
        self.exposure[symbol] = self.exposure.get(symbol, 0.0) + size
