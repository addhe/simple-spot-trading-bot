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
        self.client = Client(settings['API_KEY'], settings['API_SECRET'])
        self.client.API_URL = 'https://testnet.binance.vision/api'
        self.strategy = PriceActionStrategy(SYMBOL)
        self.latest_activity = self.load_latest_activity()
        self.config_hash = self.get_config_hash()
        self.historical_data = self.load_historical_data()

    def load_latest_activity(self) -> dict:
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
        except Exception as e:
            logging.error(f"Error saat membaca latest_activity.pkl: {e}")
            return {
                'buy': False,
                'sell': False,
                'symbol': '',
                'quantity': 0,
                'price': 0,
                'estimasi_profit': 0
            }

    def save_latest_activity(self) -> None:
        try:
            with open('latest_activity.pkl', 'wb') as f:
                pickle.dump(self.latest_activity, f)
        except Exception as e:
            logging.error(f"Error saat menyimpan latest_activity.pkl: {e}")

    def load_historical_data(self) -> list:
        try:
            with open('historical_data.pkl', 'rb') as f:
                return pickle.load(f)
        except FileNotFoundError:
            logging.warning("File historical_data.pkl tidak ditemukan, menggunakan default.")
            return []
        except Exception as e:
            logging.error(f"Error saat membaca historical_data.pkl: {e}")
            return []

    def save_historical_data(self) -> None:
        try:
            with open('historical_data.pkl', 'wb') as f:
                pickle.dump(self.historical_data, f)
        except Exception as e:
            logging.error(f"Error saat menyimpan historical_data.pkl: {e}")

    def get_config_hash(self) -> str:
        try:
            with open('config/config.py', 'r') as f:
                settings_code = f.read()
            return hashlib.md5(settings_code.encode()).hexdigest()
        except Exception as e:
            logging.error(f"Error saat membaca config/config.py: {e}")
            return None

    def check_config_change(self) -> None:
        current_hash = self.get_config_hash()
        if current_hash and current_hash != self.config_hash:
            self.config_hash = current_hash
            logging.info("Config telah berubah, reload config...")

    def run(self) -> None:
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

    def calculate_dynamic_quantity(self, action: str, price: float) -> float:
        usdt_balance = 0
        for balance in self.client.get_account()['balances']:
            if balance['asset'] == 'USDT':
                usdt_balance = float(balance['free'])
                break

        percentage = 0.10
        quantity = (usdt_balance * percentage) / price
        return round(quantity, 2)

    def check_price(self) -> None:
        try:
            action, price = self.strategy.check_price(self.client)
            price = float(price)
            quantity = self.calculate_dynamic_quantity(action, price)

            if action == 'BUY':
                logging.info(f"Melakukan pembelian {SYMBOL} pada harga {price} sebanyak {quantity}")
                order = self.client.create_test_order(
                    symbol=SYMBOL,
                    side='BUY',
                    type='LIMIT',
                    quantity=quantity,
                    price=price,
                    timeInForce='GTC'
                )
                logging.debug(f"Order Detail: {order}")
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
                notifikasi_balance(self.client)

            elif action == 'SELL':
                estimasi_profit = price - self.latest_activity['price'] if self.latest_activity['price'] else 0
                if estimasi_profit > 0:
                    logging.info(f"Melakukan penjualan {SYMBOL} pada harga {price} sebanyak {quantity}")
                    order = self.client.create_test_order(
                        symbol=SYMBOL,
                        side='SELL',
                        type='LIMIT',
                        quantity=quantity,
                        price=price,
                        timeInForce='GTC'
                    )
                    logging.debug(f"Order Detail: {order}")
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
                    notifikasi_balance(self.client)
                else:
                    logging.info(f"Tidak melakukan penjualan {SYMBOL} karena estimasi profit negatif: {estimasi_profit}")

            self.historical_data.append({
                'timestamp': time.time(),
                'price': price,
                'buy_price': self.strategy.calculate_dynamic_buy_price(),
                'sell_price': self.strategy.calculate_dynamic_sell_price()
            })
            self.save_historical_data()

        except Exception as e:
            logging.error(f"Error dalam check_price: {e}")
            time.sleep(1)
            self.check_price()
