import unittest  
from unittest.mock import MagicMock  
from binance.client import Client  
from src.check_price import CryptoPriceChecker  
  
class TestCryptoPriceChecker(unittest.TestCase):  
    def setUp(self):  
        # Membuat mock untuk client Binance  
        self.client = MagicMock(Client)  
        self.crypto_checker = CryptoPriceChecker(self.client)  
  
    def test_get_historical_data_success(self):  
        # Menyiapkan data historis yang akan dikembalikan oleh mock  
        self.client.get_historical_klines.return_value = [  
            [1620000000000, '40000', '41000', '39000', '40500', '100', 1620000060000, '4000000', 100, '50', '200', '0']  
        ]  
          
        result = self.crypto_checker.get_historical_data('BTCUSDT')  
        self.assertFalse(result.empty)  
        self.assertEqual(result['close'].iloc[0], 40500.0)  
  
    def test_get_historical_data_failure(self):  
        # Mengatur mock untuk melempar exception  
        self.client.get_historical_klines.side_effect = Exception("API Error")  
          
        result = self.crypto_checker.get_historical_data('BTCUSDT')  
        self.assertTrue(result.empty)  
  
    def test_calculate_dynamic_buy_price(self):  
        # Menyiapkan data historis  
        self.client.get_historical_klines.return_value = [  
            [1620000000000, '40000', '41000', '39000', '40500', '100', 1620000060000, '4000000', 100, '50', '200', '0'],  
            [1620000000000, '41000', '42000', '40000', '41500', '100', 1620000060000, '4000000', 100, '50', '200', '0'],  
            [1620000000000, '42000', '43000', '41000', '42500', '100', 1620000060000, '4000000', 100, '50', '200', '0'],  
        ]  
          
        result = self.crypto_checker.calculate_dynamic_buy_price('BTCUSDT')  
        expected_buy_price = (40500 + 41500 + 42500) * 0.95 / 3  # Rata-rata * BUY_MULTIPLIER  
        self.assertAlmostEqual(result, expected_buy_price)  
  
    def test_calculate_dynamic_sell_price(self):  
        # Menyiapkan data historis  
        self.client.get_historical_klines.return_value = [  
            [1620000000000, '40000', '41000', '39000', '40500', '100', 1620000060000, '4000000', 100, '50', '200', '0'],  
            [1620000000000, '41000', '42000', '40000', '41500', '100', 1620000060000, '4000000', 100, '50', '200', '0'],  
            [1620000000000, '42000', '43000', '41000', '42500', '100', 1620000060000, '4000000', 100, '50', '200', '0'],  
        ]  
          
        result = self.crypto_checker.calculate_dynamic_sell_price('BTCUSDT')  
        expected_sell_price = (40500 + 41500 + 42500) * 1.05 / 3  # Rata-rata * SELL_MULTIPLIER  
        self.assertAlmostEqual(result, expected_sell_price)  
  
    def test_get_current_price(self):  
        # Menyiapkan mock untuk harga saat ini  
        self.client.get_symbol_ticker.return_value = {'price': '40000'}  
          
        result = self.crypto_checker.get_current_price('BTCUSDT')  
        self.assertEqual(result, 40000.0)  
  
    def test_check_price(self):  
        # Menyiapkan mock untuk semua fungsi yang diperlukan  
        self.client.get_historical_klines.return_value = [  
            [1620000000000, '40000', '41000', '39000', '40500', '100', 1620000060000, '4000000', 100, '50', '200', '0'],  
        ]  
        self.client.get_symbol_ticker.return_value = {'price': '41000'}  
          
        latest_activity = {'buy': True, 'price': 40000.0}  
        action, current_price = self.crypto_checker.check_price('BTCUSDT', latest_activity)  
        self.assertEqual(action, 'HOLD')  # Harga saat ini tidak lebih rendah dari harga beli  
  
if __name__ == '__main__':  
    unittest.main()  
