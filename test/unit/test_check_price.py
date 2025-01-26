# test/unit/test_check_price.py
import unittest
from unittest.mock import AsyncMock, patch, MagicMock
from decimal import Decimal
from datetime import datetime, timedelta
from src.market_data import CandleStick, MarketData
from src.formatters import FormatterConfig, truncate_decimal
from src.decorators import CircuitBreaker
from src.utils import validate_timestamp

class TestCryptoPriceChecker(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # Mock FormatterConfig
        self.formatter_config = FormatterConfig(
            price_precision=2,
            volume_precision=4,
            locale='en_US'
        )
        
        # Mock Binance client with async methods
        self.client = AsyncMock()
        self.market_data = MarketData(self.client, MagicMock())
        self.market_data.get_tick_size = AsyncMock(return_value=Decimal('0.01'))

    async def test_get_historical_data_success(self):
        """Test historical data retrieval with precision formatting"""
        # Mock API response
        self.client.get_historical_klines.return_value = [
            [
                1620000000000,  # timestamp
                '40000.1234',   # open
                '41000.5678',   # high
                '39000.9876',   # low
                '40500.4321',   # close
                '100.12345',    # volume
                1620000060000,  # close time
                '4000000.789',  # quote volume
                100,            # trades
                '50.5',         # taker buy base
                '200.2',        # taker buy quote
                '0'             # ignore
            ]
        ]

        data = await self.market_data.get_historical_data('BTCUSDT')
        
        # Validate CandleStick model
        self.assertIsInstance(data, list)
        self.assertIsInstance(data[0], CandleStick)
        
        # Test precision truncation
        self.assertEqual(data[0].close, truncate_decimal(Decimal('40500.4321'), 2))
        self.assertEqual(data[0].volume, truncate_decimal(Decimal('100.12345'), 4))
        
        # Test formatted output
        formatted = data[0].formatted_dict(self.formatter_config)
        self.assertEqual(formatted['close'], '40,500.43')

    async def test_get_historical_data_failure(self):
        """Test circuit breaker activation on API failure"""
        # Configure circuit breaker
        CircuitBreaker.reset_all()
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=60)
        
        # Mock failing API call
        self.client.get_historical_klines.side_effect = Exception("API Error")
        
        with self.assertLogs('src.market_data', level='ERROR') as cm:
            # First failure
            with self.assertRaises(Exception):
                await self.market_data.get_historical_data('BTCUSDT')
            
            # Second failure should trip circuit breaker
            with self.assertRaises(Exception):
                await self.market_data.get_historical_data('BTCUSDT')
            
            # Verify circuit breaker state
            self.assertTrue(cb.is_open())
            
            # Verify structured logs
            self.assertIn('CIRCUIT OPEN', cm.output[1])
            self.assertIn('failure_count=2', cm.output[1])

    async def test_price_calculation_precision(self):
        """Test tick size-aware price calculations"""
        # Mock historical data
        self.client.get_historical_klines.return_value = [
            [1620000000000, '40000.123', '41000.456', '39000.789', '40500.123', '100', 0, '0', 0, '0', '0', '0']
        ]
        
        data = await self.market_data.get_historical_data('BTCUSDT')
        tick_size = await self.market_data.get_tick_size('BTCUSDT')
        
        # Test calculation with tick size truncation
        calculated_price = truncate_decimal(data[0].close * Decimal('0.95'), tick_size)
        expected_price = Decimal('38475.12')  # 40500.12 * 0.95 = 38475.114 → truncate to 0.01
        
        self.assertEqual(calculated_price, expected_price)

    async def test_cache_validation(self):
        """Test TTL-based cache invalidation"""
        # Prime cache
        self.market_data._historical_cache['BTCUSDT'] = {
            'data': [MagicMock(spec=CandleStick)],
            'timestamp': datetime.now().timestamp() - 301  # Expired
        }
        
        data = await self.market_data.get_historical_data('BTCUSDT')
        self.client.get_historical_klines.assert_awaited()  # Should refresh cache

    async def test_locale_safety(self):
        """Test locale-aware formatting"""
        # ID locale with different decimal format
        id_config = FormatterConfig(locale='id_ID', price_precision=2)
        
        data = CandleStick(
            open=Decimal('40000.12'),
            high=Decimal('41000.56'),
            low=Decimal('39000.78'),
            close=Decimal('40500.90'),
            volume=Decimal('100.1234'),
            timestamp=datetime.now(),
            trades=100,
            quote_volume=Decimal('4000000.789')
        )
        
        formatted = data.formatted_dict(id_config)
        self.assertEqual(formatted['close'], '40.500,90')
        self.assertEqual(formatted['volume'], '100,1234')

    @patch('src.telegram_notifier.TelegramNotifier.send_alert')
    async def test_alert_thresholds(self, mock_alert):
        """Test price alert triggering with debounce"""
        # Setup alert
        test_symbol = 'BTCUSDT'
        alert_price = Decimal('40000')
        tolerance = Decimal('0.5')
        
        self.market_data.subscribe(test_symbol, self.market_data._check_alerts)
        self.market_data.add_alert(
            symbol=test_symbol,
            price=alert_price,
            callback=MagicMock(),
            tolerance=tolerance
        )
        
        # Simulate price events
        event1 = MarketEvent(
            symbol=test_symbol,
            timestamp=datetime.now(),
            open=Decimal('39999'),
            high=Decimal('40000.6'),  # Within tolerance
            low=Decimal('39900'),
            close=Decimal('40000.5'),
            volume=Decimal('100'),
            interval='1m'
        )
        
        await self.market_data._process_event(event1)
        mock_alert.assert_not_called()  # Should debounce
        
        event2 = MarketEvent(
            symbol=test_symbol,
            timestamp=datetime.now() + timedelta(seconds=2),
            open=Decimal('40000'),
            high=Decimal('40001'),
            low=Decimal('39999'),
            close=Decimal('40000.6'),  # Trigger alert
            volume=Decimal('100'),
            interval='1m'
        )
        
        await self.market_data._process_event(event2)
        mock_alert.assert_called_once()

if __name__ == '__main__':
    unittest.main()