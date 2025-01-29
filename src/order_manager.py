# src/order_manager.py
from typing import Dict, Optional
from binance import Client
from .exceptions import OrderError
from .utils import APIUtils, InputValidator

class OrderManager:
    """Handles order execution and tracking with enhanced error handling"""
    
    def __init__(self, client: Client, symbol: str):
        self.client = client
        self.symbol = symbol
        self.open_orders: Dict[str, dict] = {}
    
    @APIUtils.rate_limited_api_call
    def create_order(
        self,
        side: str,
        quantity: float,
        order_type: str = Client.ORDER_TYPE_MARKET,
        price: Optional[float] = None
    ) -> dict:
        """Execute orders with risk checks and audit logging"""
        try:
            InputValidator.validate_symbol(self.symbol)
            
            order_params = {
                "symbol": self.symbol,
                "side": side,
                "type": order_type,
                "quantity": round(quantity, 6)
            }
            
            if order_type != Client.ORDER_TYPE_MARKET:
                if not price:
                    raise OrderError("Limit orders require price parameter")
                order_params["price"] = round(price, 2)
            
            response = self.client.create_order(**order_params)
            self._track_order(response)
            return response
            
        except Exception as e:
            raise OrderError(f"Order failed: {str(e)}") from e
    
    def _track_order(self, order_response: dict):
        """Maintain internal order tracking state"""
        try:
            self.open_orders[str(order_response["orderId"])] = {
                "status": order_response.get("status", "UNKNOWN"),
                "executed_qty": float(order_response.get("executedQty", 0)),
                "transact_time": order_response.get("transactTime", 0)
            }
        except KeyError as e:
            raise OrderError(f"Invalid order response: {str(e)}") from e