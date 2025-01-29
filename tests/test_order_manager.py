# tests/test_order_manager.py
import pytest
from unittest.mock import MagicMock, patch
from src.order_manager import OrderManager
from src.exceptions import OrderError

@pytest.fixture
def mock_client():
    client = MagicMock()
    client.create_order.return_value = {
        "orderId": "12345",
        "status": "FILLED",
        "executedQty": "1.0",
        "transactTime": 1610000000000
    }
    return client

def test_valid_market_order(mock_client):
    om = OrderManager(mock_client, "BTCUSDT")
    response = om.create_order("BUY", 0.1)
    
    mock_client.create_order.assert_called_once_with(
        symbol="BTCUSDT",
        side="BUY",
        type="MARKET",
        quantity=0.1
    )
    assert "12345" in om.open_orders
    assert om.open_orders["12345"]["status"] == "FILLED"

def test_invalid_order_type(mock_client):
    om = OrderManager(mock_client, "BTCUSDT")
    with pytest.raises(OrderError):
        om.create_order("BUY", 0.1, "LIMIT")
        
def test_order_tracking(mock_client):
    om = OrderManager(mock_client, "BTCUSDT")
    om.create_order("SELL", 0.5)
    
    assert len(om.open_orders) == 1
    order = om.open_orders["12345"]
    assert order["executed_qty"] == 1.0
    assert order["transact_time"] == 1610000000000