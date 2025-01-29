# tests/test_risk_management.py
from unittest.mock import MagicMock  # Add this import
from src.risk_management import RiskManager

def test_position_size_calculation():
    mock_client = MagicMock()
    mock_client.get_account.return_value = {
        'balances': [{'asset': 'USDT', 'free': '1000.0'}]
    }
    
    rm = RiskManager(mock_client)
    size = rm.calculate_position_size('BTCUSDT', 50000, 49000)
    # Correct calculation: (1000 * 0.01) / (50000 - 49000) = 0.01
    assert round(size, 4) == 0.0100