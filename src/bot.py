import os
import schedule
import time
import pickle
import hashlib
import logging
from binance.client import Client
from config.settings import settings
from config.config import SYMBOL, INTERVAL
from strategy import PriceActionStrategy
from notifikasi_telegram import notifikasi_buy, notifikasi_sell, notifikasi_balance

# Konfigurasi logging
logging.basicConfig(level=logging.DEBUG, filename='bot.log',
                    format='%(asctime)s - %(levelname)s - %(message)s')


class BotTrading:
    def __init__(self):
        # Inisialisasi klien dengan URL Testnet
        self.client = Client(settings['API_KEY'], settings['API_SECRET'])
        self.client.API_URL = 'https://testnet.binance.vision/api'  # Setel URL ke Testnet
        self.strategy = PriceActionStrategy(SYMBOL)
        self.latest_activity = self.load_latest_activity()
        self.config_hash = self.get_config_hash()
        self.historical_data = self.load_historical_data()

    def load_latest_activity(self):
        try:
            with open('latest_activity.pkl', 'rb') as f:
                return pickle.load(f)
        except FileNotFoundError:
            logging.warning("File latest_activity.pkl tidak ditemukan, menggunakan default.")
            return {
                'buy': False,
                'sell': False,
                'symbol': '',
                'quantity': 0,
                'price': 0,
                'estimasi_profit': 0
            }

    def save_latest_activity(self):
        with open('latest_activity.pkl', 'wb') as f:
            pickle.dump(self.latest_activity, f)

    def load_historical_data(self):
        try:
            with open('historical_data.pkl', 'rb') as f:
                return pickle.load(f)
        except FileNotFoundError:
            logging.warning("File historical_data.pkl tidak ditemukan, menggunakan default.")
            return []

    def save_historical_data(self):
        with open('historical_data.pkl', 'wb') as f:
            pickle.dump(self.historical_data, f)

    def get_config_hash(self):
        try:
            with open('config/config.py', 'r') as f:
                settings_code = f.read()
            return hashlib.md5(settings_code.encode()).hexdigest()
        except Exception as e:
            logging.error(f"Error saat membaca config/config.py: {e}")
            return None

    def check_config_change(self):
        current_hash = self.get_config_hash()
        if current_hash and current_hash != self.config_hash:
            self.config_hash = current_hash
            logging.info("Config telah berubah, reload config...")

    def run(self):
        logging.info("Bot trading dimulai...")
        try:
            schedule.every(1).minutes.do(self.check_price)
            while True:
                self.check_config_change()
                schedule.run_pending()
                time.sleep(1)
        except Exception as e:
            logging.error(f"Error dalam run loop: {e}")
            time.sleep(1)
            self.run()

    def check_price(self):
        try:
            # Implementasi strategi Price Action
            action, price = self.strategy.check_price(self.client)

            # Log the type of price
            logging.debug(f"Action: {action}, Price: {price}, Type of price: {type(price)}")

            # Pastikan price adalah float
            price = float(price)

            if action == 'BUY':
                logging.info(f"Melakukan pembelian {SYMBOL} pada harga {price}")
                quantity = 0.1  # Sesuaikan dengan jumlah yang valid
                self.client.create_test_order(
                    symbol=SYMBOL,
                    side='BUY',
                    type='LIMIT',
                    quantity=quantity,
                    price=price,
                    timeInForce='GTC'
                )
                self.latest_activity = {
                    'buy': True,
                    'sell': False,
                    'symbol': SYMBOL,
                    'quantity': quantity,
                    'price': price,
                    'estimasi_profit': 0
                }
                self.save_latest_activity()
                notifikasi_buy(SYMBOL, quantity, price)

            elif action == 'SELL':
                estimasi_profit = price - self.latest_activity['price'] if self.latest_activity['price'] else 0
                if estimasi_profit > 0:  # Hanya jual jika ada profit
                    logging.info(f"Melakukan penjualan {SYMBOL} pada harga {price}")
                    quantity = 0.1  # Sesuaikan dengan jumlah yang valid
                    self.client.create_test_order(
                        symbol=SYMBOL,
                        side='SELL',
                        type='LIMIT',
                        quantity=quantity,
                        price=price,
                        timeInForce='GTC'
                    )
                    self.latest_activity = {
                        'buy': False,
                        'sell': True,
                        'symbol': SYMBOL,
                        'quantity': quantity,
                        'price': price,
                        'estimasi_profit': estimasi_profit
                    }
                    self.save_latest_activity()
                    notifikasi_sell(SYMBOL, quantity, price, estimasi_profit)
                else:
                    logging.info(f"Tidak melakukan penjualan {SYMBOL} karena estimasi profit negatif: {estimasi_profit}")

            # Simpan data historis
            self.historical_data.append({
                'timestamp': time.time(),
                'price': price,
                'buy_price': self.calculate_dynamic_buy_price(),
                'sell_price': self.calculate_dynamic_sell_price()
            })
            self.save_historical_data()

            account_info = self.client.get_account()
            notifikasi_balance(account_info['balances'][0]['free'])

        except Exception as e:
            logging.error(f"Error dalam check_price: {e}")
            time.sleep(1)
            self.check_price()

    def calculate_dynamic_buy_price(self):
        # Implementasi logika untuk menghitung harga beli dinamis
        if not self.historical_data:
            return 10000  # Default jika tidak ada data historis
        prices = [data['price'] for data in self.historical_data]
        return sum(prices) / len(prices) * 0.95  # 5% di bawah rata-rata

    def calculate_dynamic_sell_price(self):
        # Implementasi logika untuk menghitung harga jual dinamis
        if not self.historical_data:
            return 9000  # Default jika tidak ada data historis
        prices = [data['price'] for data in self.historical_data]
        return sum(prices) / len(prices) * 1.05  # 5% di atas rata-rata


if __name__ == "__main__":
    bot = BotTrading()
    bot.run()
