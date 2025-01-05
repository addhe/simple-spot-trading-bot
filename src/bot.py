# src/bot.py
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
from src.check_price import check_price

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
        self.running = True  # Flag untuk menghentikan bot

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
                'estimasi_profit': 0,
                'stop_loss': 0,
                'take_profit': 0
            }
        except Exception as e:
            logging.error(f"Error saat membaca latest_activity.pkl: {e}")
            return {
                'buy': False,
                'sell': False,
                'symbol': '',
                'quantity': 0,
                'price': 0,
                'estimasi_profit': 0,
                'stop_loss': 0,
                'take_profit': 0
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
            while self.running:  # Periksa flag untuk menghentikan loop
                self.check_config_change()
                schedule.run_pending()
                time.sleep(1)
        except Exception as e:
            logging.error(f"Error dalam run loop: {e}")
            time.sleep(1)
            self.run()

    def stop(self) -> None:
        logging.info("Menghentikan bot trading...")
        self.running = False  # Set flag untuk menghentikan loop

    def calculate_dynamic_quantity(self, action: str, price: float) -> float:
        usdt_balance = 0
        for balance in self.client.get_account()['balances']:
            if balance['asset'] == 'USDT':
                usdt_balance = float(balance['free'])
                break

        percentage = 0.25
        quantity = (usdt_balance * percentage) / price

        # Validasi kuantitas
        if quantity < 0.01:  # Misalnya, minimum kuantitas yang valid
            logging.warning(f"Kuantitas yang dihitung terlalu kecil: {quantity}. Tidak melakukan pembelian.")
            return 0.0

        return round(quantity, 2)

    def check_price(self) -> None:
        try:
            action, price = check_price(self.client, SYMBOL, self.latest_activity)
            price = float(price)
            quantity = self.calculate_dynamic_quantity(action, price)

            if action == 'BUY' and quantity > 0:  # Pastikan kuantitas lebih dari 0
                logging.info(f"Melakukan pembelian {SYMBOL} pada harga {price} sebanyak {quantity}")
                order = self.client.create_order(
                    symbol=SYMBOL,
                    side='BUY',
                    type='LIMIT',
                    quantity=quantity,
                    price=price,
                    timeInForce='GTC'
                )
                logging.debug(f"Order Detail: {order}")

                # Mengatur stop-loss dan take-profit
                risk_management = self.strategy.manage_risk('BUY', price, quantity)
                self.latest_activity = {
                    'buy': True,
                    'sell': False,
                    'symbol': SYMBOL,
                    'quantity': quantity,
                    'price': price,
                    'estimasi_profit': 0,
                    'stop_loss': risk_management['stop_loss'],
                    'take_profit': risk_management['take_profit']
                }
                self.save_latest_activity()
                notifikasi_buy(SYMBOL, quantity, price)
                notifikasi_balance(self.client)

            elif action == 'SELL':
                if self.latest_activity['buy']:
                    estimasi_profit = price - self.latest_activity['price'] if self.latest_activity['price'] else 0
                    if estimasi_profit > 0:
                        logging.info(f"Melakukan penjualan {SYMBOL} pada harga {price} sebanyak {self.latest_activity['quantity']}")
                        order = self.client.create_order(
                            symbol=SYMBOL,
                            side='SELL',
                            type='LIMIT',
                            quantity=self.latest_activity['quantity'],
                            price=price,
                            timeInForce='GTC'
                        )
                        logging.debug(f"Order Detail: {order}")
                        self.latest_activity = {
                            'buy': False,
                            'sell': True,
                            'symbol': SYMBOL,
                            'quantity': self.latest_activity['quantity'],
                            'price': price,
                            'estimasi_profit': estimasi_profit,
                            'stop_loss': 0,
                            'take_profit': 0
                        }
                        self.save_latest_activity()
                        notifikasi_sell(SYMBOL, self.latest_activity['quantity'], price, estimasi_profit)
                        notifikasi_balance(self.client)
                    else:
                        logging.info(f"Tidak melakukan penjualan {SYMBOL} karena estimasi profit negatif: {estimasi_profit}")
                else:
                    logging.info(f"Tidak ada transaksi pembelian sebelumnya untuk {SYMBOL}")

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
