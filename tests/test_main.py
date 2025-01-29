# tests/test_main.py
import pytest
import time
from unittest.mock import Mock, patch, MagicMock
from main import TradingBot
from config.settings import Settings, ExchangeConfig, StrategyConfig

@pytest.fixture
def mock_settings():
    return Settings(
        exchange=ExchangeConfig(
            api_key="test-key",
            api_secret="test-secret"
        ),
        symbol="BTCUSDT",
        risk_per_trade=0.02,
        strategy=StrategyConfig(stop_loss=2.0),
        log_level="DEBUG"
    )

@pytest.fixture
def mock_client():
    client = Mock()
    
    # Mock account balance response
    client.get_account.return_value = {
        'balances': [{'asset': 'USDT', 'free': '1000'}]
    }
    
    return client

@pytest.fixture
def trading_bot(mock_settings, mock_client):
    return TradingBot(mock_settings, mock_client)

def test_bot_initialization(trading_bot):
    assert trading_bot.settings.symbol == "BTCUSDT"
    assert trading_bot.running is False
    assert trading_bot.risk_manager is not None

def test_start_stop_sequence(trading_bot):
    trading_bot.start()
    assert trading_bot.running is True
    time.sleep(0.1)  # Allow thread to start
    trading_bot.stop()
    assert trading_bot.running is False

@patch.object(TradingBot, '_run_iteration')
def test_run_iteration(mock_iteration, trading_bot):
    trading_bot.start()
    time.sleep(0.1)
    trading_bot.stop()
    mock_iteration.assert_called()

def test_execute_trade(trading_bot):
    # Mock order manager and response
    trading_bot.order_manager.create_order = Mock(return_value={
        "orderId": 12345,
        "status": "FILLED",
        "executedQty": "0.02",
        "transactTime": 1629377492000
    })
    
    # Test BUY order
    trading_bot._execute_trade(1, 50000.0)
    trading_bot.order_manager.create_order.assert_called_with(
        "BUY", 
        pytest.approx(0.02, rel=1e-3)
    )
    
    # Test SELL order
    trading_bot._execute_trade(-1, 50000.0)
    trading_bot.order_manager.create_order.assert_called_with(
        "SELL", 
        pytest.approx(0.02, rel=1e-3)
    )

def test_error_handling(trading_bot, caplog):
    with patch.object(trading_bot.market_data, 'get_historical_data') as mock_get_data:
        mock_get_data.side_effect = Exception("Test error")
        trading_bot.start()
        time.sleep(0.1)
        trading_bot.stop()
        assert "Test error" in caplog.text