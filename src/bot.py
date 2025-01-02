import os
import schedule
import time
from binance.client import Client
from config.settings import settings
from strategy import PriceActionStrategy
from notifikasi_telegram import notifikasi_buy, notifikasi_sell, notifikasi_balance
import pickle
import importlib
import hashlib
import logging

logging.basicConfig(filename='bot.log', level=logging.ERROR)

class BotTrading:
    def __init__(self):
        self.client = Client(os.environ['API_KEY_SPOT_BINANCE'], os.environ['API_SECRET_SPOT_BINANCE'], base_url='https://testnet.binance.vision/api')
        self.strategy = PriceActionStrategy()
        self.latest_activity = self.load_latest_activity()
        self.settings_hash = self.get_settings_hash()

    def load_latest_activity(self):
        try:
            with open('latest_activity.pkl', 'rb') as f:
                return pickle.load(f)
        except FileNotFoundError:
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

    def get_settings_hash(self):
        with open('config/settings.py', 'r') as f:
            settings_code = f.read()
        return hashlib.md5(settings_code.encode()).hexdigest()

    def check_settings_change(self):
        current_hash = self.get_settings_hash()
        if current_hash != self.settings_hash:
            self.settings_hash = current_hash
            importlib.reload(settings)
            print("Settings telah berubah, reload config...")

    def run(self):
        try:
            schedule.every(1).minutes.do(self.check_price)
            while True:
                self.check_settings_change()
                schedule.run_pending()
                time.sleep(1)
        except Exception as e:
            logging.error(f"Error: {e}")
            time.sleep(1)
            self.run()

    def check_price(self):
        try:
            # Implementasi strategi Price Action
            self.strategy.check_price(self.client)
            # Implementasi logika strategi Price Action
            if self.data['price'] > 10000:
                # Implementasi aksi trading
                quantity = 0.1
                price = 10000
                self.client.place_order(symbol='BTCUSDT', side='BUY', type='LIMIT', quantity=quantity, price=price)
                self.latest_activity = {
                    'buy': True,
                    'sell': False,
                    'symbol': 'BTCUSDT',
                    'quantity': quantity,
                    'price': price,
                    'estimasi_profit': 0
                }
                self.save_latest_activity()
                notifikasi_buy('BTCUSDT', quantity, price)
            elif self.data['price'] < 9000:
                # Implementasi aksi trading
                quantity = 0.1
                price = 9000
                self.client.place_order(symbol='BTCUSDT', side='SELL', type='LIMIT', quantity=quantity, price=price)
                estimasi_profit = self.client.get_symbol_ticker(symbol='BTCUSDT')['price'] - price
                self.latest_activity = {
                    'buy': False,
                    'sell': True,
                    'symbol': 'BTCUSDT',
                    'quantity': quantity,
                    'price': price,
                    'estimasi_profit': estimasi_profit
                }
                self.save_latest_activity()
                notifikasi_sell('BTCUSDT', quantity, price, estimasi_profit)
            notifikasi_balance(self.client.get_account()['balances'][0]['free'])

            # Cek jika terdapat aktivitas pembelian atau penjualan terakhir
            if self.latest_activity['buy']:
                # Cek jika harga saat ini lebih tinggi dari harga pembelian
                if self.data['price'] > self.latest_activity['price']:
                    # Implementasi aksi trading untuk menjual
                    quantity = self.latest_activity['quantity']
                    price = self.data['price']
                    self.client.place_order(symbol='BTCUSDT', side='SELL', type='LIMIT', quantity=quantity, price=price)
                    estimasi_profit = price - self.latest_activity['price']
                    self.latest_activity = {
                        'buy': False,
                        'sell': True,
                        'symbol': 'BTCUSDT',
                        'quantity': quantity,
                        'price': price,
                        'estimasi_profit': estimasi_profit
                    }
                    self.save_latest_activity()
                    notifikasi_sell('BTCUSDT', quantity, price, estimasi_profit)
            elif self.latest_activity['sell']:
                # Cek jika harga saat ini lebih rendah dari harga penjualan
                if self.data['price'] < self.latest_activity['price']:
                    # Implementasi aksi trading untuk membeli
                    quantity = self.latest_activity['quantity']
                    price = self.data['price']
                    self.client.place_order(symbol='BTCUSDT', side='BUY', type='LIMIT', quantity=quantity, price=price)
                    self.latest_activity = {
                        'buy': True,
                        'sell': False,
                        'symbol': 'BTCUSDT',
                        'quantity': quantity,
                        'price': price,
                        'estimasi_profit': 0
                    }
                    self.save_latest_activity()
                    notifikasi_buy('BTCUSDT', quantity, price)
        except Exception as e:
            logging.error(f"Error: {e}")
            time.sleep(1)
            self.check_price()