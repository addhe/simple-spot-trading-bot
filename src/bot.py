# src/bot.py
import os
import schedule
import time
from binance.client import Client
from ..config.settings import settings
from config.config import SYMBOL, INTERVAL
from strategy import PriceActionStrategy
from notifikasi_telegram import notifikasi_buy, notifikasi_sell, notifikasi_balance
import pickle
import hashlib
import logging

logging.basicConfig(filename='bot.log', level=logging.ERROR)

class BotTrading:
    def __init__(self):
        self.client = Client(settings['API_KEY'], settings['API_SECRET'], base_url=settings['BASE_URL'])
        self.strategy = PriceActionStrategy(SYMBOL)
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
            symbol_ticker = self.client.get_symbol_ticker(symbol=SYMBOL)
            price = symbol_ticker['price']
            if price > 10000:
                # Implementasi aksi trading
                quantity = 0.1
                self.client.place_order(symbol=SYMBOL, side='BUY', type='LIMIT', quantity=quantity, price=10000)
                self.latest_activity = {
                    'buy': True,
                    'sell': False,
                    'symbol': SYMBOL,
                    'quantity': quantity,
                    'price': 10000,
                    'estimasi_profit': 0
                }
                self.save_latest_activity()
                notifikasi_buy(SYMBOL, quantity, 10000)
            elif price < 9000:
                # Implementasi aksi trading
                quantity = 0.1
                self.client.place_order(symbol=SYMBOL, side='SELL', type='LIMIT', quantity=quantity, price=9000)
                estimasi_profit = price - 9000
                self.latest_activity = {
                    'buy': False,
                    'sell': True,
                    'symbol': SYMBOL,
                    'quantity': quantity,
                    'price': 9000,
                    'estimasi_profit': estimasi_profit
                }
                self.save_latest_activity()
                notifikasi_sell(SYMBOL, quantity, 9000, estimasi_profit)
            account_info = self.client.get_account()
            notifikasi_balance(account_info['balances'][0]['free'])

            # Cek jika terdapat aktivitas pembelian atau penjualan terakhir
            if self.latest_activity['buy']:
                # Cek jika harga saat ini lebih tinggi dari harga pembelian
                if price > self.latest_activity['price']:
                    # Implementasi aksi trading untuk menjual
                    quantity = self.latest_activity['quantity']
                    self.client.place_order(symbol=SYMBOL, side='SELL', type='LIMIT', quantity=quantity, price=price)
                    estimasi_profit = price - self.latest_activity['price']
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
            elif self.latest_activity['sell']:
                # Cek jika harga saat ini lebih rendah dari harga penjualan
                if price < self.latest_activity['price']:
                    # Implementasi aksi trading untuk membeli
                    quantity = self.latest_activity['quantity']
                    self.client.place_order(symbol=SYMBOL, side='BUY', type='LIMIT', quantity=quantity, price=price)
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
        except Exception as e:
            logging.error(f"Error: {e}")
            time.sleep(1)
            self.check_price()
