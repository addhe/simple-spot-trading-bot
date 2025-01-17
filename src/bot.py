# src/bot.py
import os
import schedule
import time
import pickle
import hashlib
import logging
from binance.client import Client
from binance.exceptions import BinanceAPIException
from config.settings import settings
from config.config import SYMBOLS, INTERVAL
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
        self.strategies = {symbol: PriceActionStrategy(symbol) for symbol in SYMBOLS}
        self.latest_activities = {symbol: self.load_latest_activity(symbol) for symbol in SYMBOLS}
        self.config_hash = self.get_config_hash()
        self.historical_data = {symbol: self.load_historical_data(symbol) for symbol in SYMBOLS}
        self.running = True  # Flag untuk menghentikan bot

    def load_latest_activity(self, symbol: str) -> dict:
        try:
            with open(f'latest_activity_{symbol}.pkl', 'rb') as f:
                return pickle.load(f)
        except FileNotFoundError:
            logging.warning(f"File latest_activity_{symbol}.pkl tidak ditemukan, menggunakan default.")
            return {
                'buy': False,
                'sell': False,
                'symbol': symbol,
                'quantity': 0,
                'price': 0,
                'estimasi_profit': 0,
                'stop_loss': 0,
                'take_profit': 0
            }
        except Exception as e:
            logging.error(f"Error saat membaca latest_activity_{symbol}.pkl: {e}")
            return {
                'buy': False,
                'sell': False,
                'symbol': symbol,
                'quantity': 0,
                'price': 0,
                'estimasi_profit': 0,
                'stop_loss': 0,
                'take_profit': 0
            }

    def save_latest_activity(self, symbol: str) -> None:
        try:
            with open(f'latest_activity_{symbol}.pkl', 'wb') as f:
                pickle.dump(self.latest_activities[symbol], f)
        except Exception as e:
            logging.error(f"Error saat menyimpan latest_activity_{symbol}.pkl: {e}")

    def load_historical_data(self, symbol: str) -> list:
        try:
            with open(f'historical_data_{symbol}.pkl', 'rb') as f:
                return pickle.load(f)
        except FileNotFoundError:
            logging.warning(f"File historical_data_{symbol}.pkl tidak ditemukan, menggunakan default.")
            return []
        except Exception as e:
            logging.error(f"Error saat membaca historical_data_{symbol}.pkl: {e}")
            return []

    def save_historical_data(self, symbol: str) -> None:
        try:
            with open(f'historical_data_{symbol}.pkl', 'wb') as f:
                pickle.dump(self.historical_data[symbol], f)
        except Exception as e:
            logging.error(f"Error saat menyimpan historical_data_{symbol}.pkl: {e}")

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
            schedule.every(1).minutes.do(self.check_prices)
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

    def calculate_dynamic_quantity(self, symbol: str, price: float) -> float:
        usdt_balance = 0
        for balance in self.client.get_account()['balances']:
            if balance['asset'] == 'USDT':
                usdt_balance = float(balance['free'])
                break

        percentage = 0.25
        quantity = (usdt_balance * percentage) / price

        # Validasi kuantitas
        if quantity < 0.01:  # Misalnya, minimum kuantitas yang valid
            logging.warning(f"Kuota yang dihitung terlalu kecil: {quantity}. Tidak melakukan pembelian.")
            return 0.0

        # Periksa batas minimum nominal transaksi
        min_notional = self.get_min_notional(symbol)
        nominal = quantity * price
        if nominal < min_notional:
            logging.warning(f"Nominal transaksi {nominal} kurang dari batas minimum {min_notional}. Tidak melakukan pembelian.")
            return 0.0

        return round(quantity, 2)

    def get_min_notional(self, symbol: str) -> float:
        try:
            symbol_info = self.client.get_symbol_info(symbol)
            for filter in symbol_info['filters']:
                if filter['filterType'] == 'MIN_NOTIONAL':
                    return float(filter['minNotional'])
            return 10.0  # Default minimum notional jika tidak ditemukan
        except Exception as e:
            logging.error(f"Error saat mendapatkan informasi symbol {symbol}: {e}")
            return 10.0  # Default minimum notional jika terjadi error

    def check_prices(self) -> None:
        for symbol in SYMBOLS:
            try:
                strategy = self.strategies[symbol]
                latest_activity = self.latest_activities[symbol]
                action, price = check_price(self.client, symbol, latest_activity)
                price = float(price)
                quantity = self.calculate_dynamic_quantity(symbol, price)

                if action == 'BUY' and quantity > 0:  # Pastikan kuantitas lebih dari 0
                    logging.info(f"Melakukan pembelian {symbol} pada harga {price} sebanyak {quantity}")
                    try:
                        order = self.client.create_order(
                            symbol=symbol,
                            side='BUY',
                            type='LIMIT',
                            quantity=quantity,
                            price=price,
                            timeInForce='GTC'
                        )
                        logging.debug(f"Order Detail: {order}")

                        # Mengatur stop-loss dan take-profit
                        risk_management = strategy.manage_risk('BUY', price, quantity)
                        self.latest_activities[symbol] = {
                            'buy': True,
                            'sell': False,
                            'symbol': symbol,
                            'quantity': quantity,
                            'price': price,
                            'estimasi_profit': 0,
                            'stop_loss': risk_management['stop_loss'],
                            'take_profit': risk_management['take_profit']
                        }
                        self.save_latest_activity(symbol)
                        notifikasi_buy(symbol, quantity, price)
                        notifikasi_balance(self.client)
                    except BinanceAPIException as e:
                        logging.error(f"Error API saat melakukan pembelian {symbol}: {e}")
                    except Exception as e:
                        logging.error(f"Error saat melakukan pembelian {symbol}: {e}")

                elif action == 'SELL':
                    estimasi_profit = price - latest_activity['price'] if latest_activity['price'] else 0
                    if estimasi_profit > 0:
                        logging.info(f"Melakukan penjualan {symbol} pada harga {price} sebanyak {latest_activity['quantity']}")
                        try:
                            order = self.client.create_order(
                                symbol=symbol,
                                side='SELL',
                                type='LIMIT',
                                quantity=latest_activity['quantity'],
                                price=price,
                                timeInForce='GTC'
                            )
                            logging.debug(f"Order Detail: {order}")
                            self.latest_activities[symbol] = {
                                'buy': False,
                                'sell': True,
                                'symbol': symbol,
                                'quantity': latest_activity['quantity'],
                                'price': price,
                                'estimasi_profit': estimasi_profit,
                                'stop_loss': 0,
                                'take_profit': 0
                            }
                            self.save_latest_activity(symbol)
                            notifikasi_sell(symbol, latest_activity['quantity'], price, estimasi_profit)
                            notifikasi_balance(self.client)
                        except BinanceAPIException as e:
                            logging.error(f"Error API saat melakukan penjualan {symbol}: {e}")
                        except Exception as e:
                            logging.error(f"Error saat melakukan penjualan {symbol}: {e}")
                    else:
                        logging.info(f"Tidak melakukan penjualan {symbol} karena estimasi profit negatif: {estimasi_profit}")

                # Periksa kondisi penjualan berdasarkan stop-loss atau take-profit
                if latest_activity['buy']:
                    if strategy.should_sell(price, latest_activity):
                        logging.info(f"Kondisi penjualan terpenuhi untuk {symbol} pada harga {price}")
                        try:
                            order = self.client.create_order(
                                symbol=symbol,
                                side='SELL',
                                type='LIMIT',
                                quantity=latest_activity['quantity'],
                                price=price,
                                timeInForce='GTC'
                            )
                            logging.debug(f"Order Detail: {order}")
                            estimasi_profit = price - latest_activity['price'] if latest_activity['price'] else 0
                            self.latest_activities[symbol] = {
                                'buy': False,
                                'sell': True,
                                'symbol': symbol,
                                'quantity': latest_activity['quantity'],
                                'price': price,
                                'estimasi_profit': estimasi_profit,
                                'stop_loss': 0,
                                'take_profit': 0
                            }
                            self.save_latest_activity(symbol)
                            notifikasi_sell(symbol, latest_activity['quantity'], price, estimasi_profit)
                            notifikasi_balance(self.client)
                        except BinanceAPIException as e:
                            logging.error(f"Error API saat melakukan penjualan {symbol}: {e}")
                        except Exception as e:
                            logging.error(f"Error saat melakukan penjualan {symbol}: {e}")

                # Menyimpan data historis hanya jika ada perubahan harga
                if self.historical_data[symbol] and self.historical_data[symbol][-1]['price'] != price:
                    self.historical_data[symbol].append({
                        'timestamp': time.time(),
                        'price': price,
                        'buy_price': strategy.calculate_dynamic_buy_price(),
                        'sell_price': strategy.calculate_dynamic_sell_price()
                    })
                    self.save_historical_data(symbol)

            except Exception as e:
                logging.error(f"Error dalam check_price untuk {symbol}: {e}")
                time.sleep(1)
                self.check_prices()
