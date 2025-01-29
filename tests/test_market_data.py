# tests/test_market_data.py
from unittest.mock import MagicMock  # Add this import
import pandas as pd
from src.market_data import MarketData

def test_historical_data_formatting():
    mock_client = MagicMock()
    # Provide full 12-element candle data
    mock_client.get_klines.return_value = [
        [1610000000000, "100", "105", "95", "102", "1000",
         1610003600000, "100000", "50", "500", "50000", "0"]
    ]
    
    md = MarketData(mock_client)
    df = md.get_historical_data('BTCUSDT', '1h')
    assert df['close'].iloc[0] == 102.0