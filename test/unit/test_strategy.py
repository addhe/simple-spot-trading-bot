import unittest  
from unittest.mock import patch, MagicMock  
from src.strategy import PriceActionStrategy  
import pandas as pd  
import numpy as np  
  
class TestPriceActionStrategy(unittest.TestCase):  
    def setUp(self):  
        self.symbol = 'BTCUSDT'  
        self.strategy = PriceActionStrategy(self.symbol)  
  
    @patch('src.check_price.CryptoPriceChecker.check_price')  
    def test_check_price_failure(self, mock_check_price):  
        mock_check_price.side_effect = Exception("API Error")  
        with self.assertRaises(Exception) as context:  
            self.strategy.check_price({'buy': False})  
        self.assertEqual(str(context.exception), "API Error")  
  
    @patch('src.check_price.CryptoPriceChecker.check_price')  
    def test_check_price_success(self, mock_check_price):  
        mock_check_price.return_value = ('BUY', 104038.42)  
        result = self.strategy.check_price({'buy': False})  
        self.assertEqual(result, ('BUY', 104038.42))  
  
    @patch('src.strategy.PriceActionStrategy.get_historical_data')  
    def test_calculate_atr(self, mock_get_historical_data):  
        historical_data = pd.DataFrame({  
            'high': [51000, 51500, 52000, 52500, 53000, 53500, 54000, 54500, 55000, 55500],  
            'low': [49000, 49500, 50000, 50500, 51000, 51500, 52000, 52500, 53000, 53500],  
            'close': [50500, 51000, 51500, 52000, 52500, 53000, 53500, 54000, 54500, 55000]  
        })  
        mock_get_historical_data.return_value = historical_data  
        result = self.strategy.calculate_atr()  
        self.assertIsNotNone(result)  
  
    @patch('src.strategy.PriceActionStrategy.get_historical_data')  
    def test_calculate_dynamic_buy_price(self, mock_get_historical_data):  
        historical_data = pd.DataFrame({  
            'close': [49000, 49500, 50000, 50500, 51000, 51500, 52000, 52500, 53000, 53500]  
        })  
        mock_get_historical_data.return_value = historical_data  
        result = self.strategy.calculate_dynamic_buy_price()  
        close_values = historical_data['close'].values  
        moving_average = close_values[-10:].mean()  
        expected_buy_price = moving_average * 0.95  
        self.assertAlmostEqual(result, expected_buy_price, places=2)  
  
    @patch('src.strategy.PriceActionStrategy.get_historical_data')  
    def test_calculate_dynamic_sell_price(self, mock_get_historical_data):  
        historical_data = pd.DataFrame({  
            'close': [49000, 49500, 50000, 50500, 51000, 51500, 52000, 52500, 53000, 53500]  
        })  
        mock_get_historical_data.return_value = historical_data  
        result = self.strategy.calculate_dynamic_sell_price()  
        close_values = historical_data['close'].values  
        moving_average = close_values[-10:].mean()  
        expected_sell_price = moving_average * 1.05  
        self.assertAlmostEqual(result, expected_sell_price, places=2)  
  
    @patch('src.strategy.PriceActionStrategy.get_historical_data')  
    def test_calculate_atr_nan(self, mock_get_historical_data):  
        historical_data = pd.DataFrame({  
            'high': [np.nan] * 10,  
            'low': [np.nan] * 10,  
            'close': [np.nan] * 10  
        })  
        mock_get_historical_data.return_value = historical_data  
        result = self.strategy.calculate_atr()  
        self.assertEqual(result, 0)  
  
    def test_should_buy(self):  
        with patch.object(self.strategy, 'calculate_moving_average', return_value=50000):  
            result = self.strategy.should_buy(51000)  
            self.assertTrue(result)  
  
        with patch.object(self.strategy, 'calculate_moving_average', return_value=52000):  
            result = self.strategy.should_buy(51000)  
            self.assertFalse(result)  
  
    @patch('src.strategy.PriceActionStrategy.get_historical_data')  
    def test_get_historical_data(self, mock_get_historical_data):  
        historical_data = pd.DataFrame({  
            'timestamp': [1643723400, 1643723460, 1643723520],  
            'open': [49000, 49500, 50000],  
            'high': [51000, 51500, 52000],  
            'low': [49000, 49500, 50000],  
            'close': [50500, 51000, 51500],  
            'volume': [100, 200, 300],  
            'close_time': [1643723460, 1643723520, 1643723580],  
            'quote_asset_volume': [100, 200, 300],  
            'number_of_trades': [10, 20, 30],  
            'taker_buy_base_asset_volume': [10, 20, 30],  
            'taker_buy_quote_asset_volume': [10, 20, 30],  
            'ignore': [0, 0, 0]  
        })  
        mock_get_historical_data.return_value = historical_data  
        result = self.strategy.get_historical_data()  
        self.assertIsInstance(result, pd.DataFrame)  
  
    def test_manage_risk(self):  
        action = 'BUY'  
        price = 50000  
        quantity = 1  
        with patch.object(self.strategy, 'calculate_atr', return_value=1000):  
            result = self.strategy.manage_risk(action, price, quantity)  
            self.assertIsInstance(result, dict)  
            self.assertIn('stop_loss', result)  
            self.assertIn('take_profit', result)  
            self.assertIn('quantity', result)  
  
if __name__ == '__main__':  
    unittest.main()  
