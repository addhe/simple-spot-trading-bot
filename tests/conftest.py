# tests/conftest.py
import pytest
from unittest.mock import MagicMock, patch
from binance import Client


@pytest.fixture
def mock_binance_client():
    client = MagicMock(spec=Client)

    # Mock account balance response
    client.get_account.return_value = {
        "balances": [{"asset": "USDT", "free": "1000.0"}]
    }

    # Mock klines response
    client.get_klines.return_value = [
        [1610000000000, "100", "105", "95", "102", "1000"],
        [1610003600000, "102", "108", "101", "107", "1500"],
    ]

    # Mock ticker price
    client.get_symbol_ticker.return_value = {"price": "105.0"}

    return client


@pytest.fixture
def risk_manager(mock_binance_client):
    from src.risk_management import RiskManager

    return RiskManager(mock_binance_client)


@pytest.fixture
def market_data(mock_binance_client):
    from src.market_data import MarketData

    return MarketData(mock_binance_client)
