# src/bot.py
import os
import hashlib
import logging
import sqlite3
import asyncio
from binance.client import Client
from binance.exceptions import BinanceAPIException
from config.settings import settings
from config.config import SYMBOLS, INTERVAL
from src.strategy import PriceActionStrategy
from src.notifikasi_telegram import notifikasi_buy, notifikasi_sell
from src.check_price import CryptoPriceChecker
from requests.exceptions import ConnectionError, Timeout

# Konfigurasi logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)

class DataStorage:
    def __init__(self, db_path='bot_trading.db'):
        self.conn = sqlite3.connect(db_path)
        self.create_tables()

    def create_tables(self):
        cursor = self.conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS latest_activity (
            symbol TEXT PRIMARY KEY,
            buy INTEGER,
            sell INTEGER,
            quantity REAL,
            price REAL,
            stop_loss REAL,
            take_profit REAL
        )''')
        self.conn.commit()

    def save_latest_activity(self, symbol, activity):
        cursor = self.conn.cursor()
        cursor.execute('''REPLACE INTO latest_activity
                          (symbol, buy, sell, quantity, price, stop_loss, take_profit)
                          VALUES (?, ?, ?, ?, ?, ?, ?)''',
                       (symbol, activity['buy'], activity['sell'], activity['quantity'],
                        activity['price'], activity['stop_loss'], activity['take_profit']))
        self.conn.commit()

    def load_latest_activity(self, symbol):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM latest_activity WHERE symbol = ?', (symbol,))
        row = cursor.fetchone()
        if row:
            return {
                'buy': bool(row[1]),
                'sell': bool(row[2]),
                'quantity': row[3],
                'price': row[4],
                'stop_loss': row[5],
                'take_profit': row[6],
            }
        return {'buy': False, 'sell': False, 'quantity': 0, 'price': 0, 'stop_loss': 0, 'take_profit': 0}

class BotTrading:
    def __init__(self):
        self.client = Client(settings['API_KEY'], settings['API_SECRET'])
        self.client.API_URL = settings['BASE_URL']
        self.strategies = {symbol: PriceActionStrategy(symbol) for symbol in SYMBOLS}
        self.storage = DataStorage()
        self.latest_activities = {symbol: self.storage.load_latest_activity(symbol) for symbol in SYMBOLS}
        self.config_hash = self.get_config_hash()
        self.running = True
        self.symbol_info = {}
        self.init_symbol_info()
        self.price_checker = CryptoPriceChecker(self.client)
        self.update_symbol_usdt_allocation()

    def get_config_hash(self):
        """Menghitung hash dari konfigurasi bot."""
        try:
            config_str = f"{settings['API_KEY']}{settings['API_SECRET']}{str(SYMBOLS)}{INTERVAL}"
            return hashlib.md5(config_str.encode()).hexdigest()
        except Exception as e:
            logging.error(f"Error saat menghitung hash konfigurasi: {e}")
            return None

    def init_symbol_info(self):
        """Initialize symbol information including precision and minimum notional requirements."""
        try:
            exchange_info = self.client.get_exchange_info()
            for symbol_info in exchange_info['symbols']:
                if symbol_info['symbol'] in SYMBOLS:
                    self.symbol_info[symbol_info['symbol']] = self.extract_symbol_info(symbol_info)
                    logging.info(f"Initialized {symbol_info['symbol']} info: {self.symbol_info[symbol_info['symbol']]}")
        except Exception as e:
            logging.error(f"Error initializing symbol info: {str(e)}")
            self.set_default_symbol_info()

    def extract_symbol_info(self, symbol_info):
        """Extract necessary symbol information from exchange info."""
        symbol_specific_info = {
            'quantity_precision': 5,
            'price_precision': 2,
            'min_quantity': 0.00001,
            'max_quantity': 9999999,
            'min_notional': 10.0
        }

        try:
            lot_size_filter = next((f for f in symbol_info['filters'] if f['filterType'] == 'LOT_SIZE'), None)
            price_filter = next((f for f in symbol_info['filters'] if f['filterType'] == 'PRICE_FILTER'), None)
            min_notional_filter = next((f for f in symbol_info['filters'] if f['filterType'] == 'MIN_NOTIONAL'), None)

            if lot_size_filter:
                symbol_specific_info.update({
                    'quantity_precision': self.get_precision_from_step_size(lot_size_filter['stepSize']),
                    'min_quantity': float(lot_size_filter['minQty']),
                    'max_quantity': float(lot_size_filter['maxQty'])
                })

            if price_filter:
                symbol_specific_info['price_precision'] = self.get_precision_from_step_size(price_filter['tickSize'])

            if min_notional_filter:
                symbol_specific_info['min_notional'] = float(min_notional_filter['minNotional'])

            return symbol_specific_info

        except Exception as e:
            logging.warning(f"Error processing filters for {symbol_info['symbol']}, using default values: {str(e)}")
            return symbol_specific_info

    def set_default_symbol_info(self):
        """Set default values for all symbols if initialization fails."""
        for symbol in SYMBOLS:
            self.symbol_info[symbol] = {
                'quantity_precision': 5,
                'price_precision': 2,
                'min_quantity': 0.00001,
                'max_quantity': 9999999,
                'min_notional': 10.0
            }
        logging.warning("Using default symbol information due to initialization error")

    def get_usdt_balance(self) -> float:
        try:
            balance = self.client.get_asset_balance(asset='USDT')
            return float(balance['free'])
        except Exception as e:
            logging.error(f"Error getting USDT balance: {e}")
            return 0.0

    def get_precision_from_step_size(self, step_size: str) -> int:
        try:
            step_size = float(step_size)
            if step_size == 1.0:
                return 0
            decimal_str = str(step_size).rstrip('0')
            if '.' in decimal_str:
                return len(decimal_str.split('.')[-1])
            return 0
        except Exception as e:
            logging.error(f"Error calculating precision from step size {step_size}: {str(e)}")
            return 8

    def has_active_orders(self, symbol: str, side: str) -> bool:
        """Cek apakah ada order aktif untuk simbol tertentu."""
        try:
            open_orders = self.client.get_open_orders(symbol=symbol)
            return any(order['side'] == side for order in open_orders)
        except Exception as e:
            logging.error(f"Error checking active orders for {symbol}: {e}")
            return False

    def calculate_dynamic_quantity(self, symbol: str, price: float) -> float:
        try:
            available_usdt = self.symbol_usdt_allocation[symbol]
            logging.info(f"Available USDT balance for {symbol}: {available_usdt}")

            raw_quantity = available_usdt / price
            symbol_info = self.symbol_info[symbol]

            quantity = round(raw_quantity, symbol_info['quantity_precision'])
            quantity = max(symbol_info['min_quantity'], min(quantity, symbol_info['max_quantity']))

            if quantity * price < symbol_info['min_notional']:
                logging.warning(f"Order value below minimum notional ({symbol_info['min_notional']})")
                return 0.0

            return quantity
        except Exception as e:
            logging.error(f"Error calculating quantity for {symbol}: {e}")
            return 0.0

    def update_symbol_usdt_allocation(self):
        """Update alokasi USDT untuk setiap simbol berdasarkan saldo USDT yang tersedia."""
        try:
            total_usdt_balance = self.get_usdt_balance()
            num_symbols = len(SYMBOLS)
            allocation_per_symbol = total_usdt_balance / num_symbols
            self.symbol_usdt_allocation = {symbol: allocation_per_symbol for symbol in SYMBOLS}
            logging.info(f"Updated USDT allocation per symbol: {self.symbol_usdt_allocation}")
        except Exception as e:
            logging.error(f"Error updating USDT allocation: {e}")

    async def check_prices(self):
        for symbol in SYMBOLS:
            try:
                strategy = self.strategies[symbol]
                latest_activity = self.latest_activities[symbol]
                action, price = self.price_checker.check_price(symbol, latest_activity)

                # Cek jika action adalah BUY dan belum ada pembelian sebelumnya
                if action == 'BUY' and not latest_activity['buy'] and not self.has_active_orders(symbol, 'BUY'):
                    quantity = self.calculate_dynamic_quantity(symbol, price)
                    if quantity > 0:
                        await self.execute_buy(symbol, price, quantity, strategy)

                # Cek jika action adalah SELL dan sudah ada pembelian sebelumnya
                elif action == 'SELL' and latest_activity['buy'] and not self.has_active_orders(symbol, 'SELL'):
                    await self.execute_sell(symbol, price, latest_activity)

                # Cek jika harus menjual berdasarkan strategi
                if latest_activity['buy'] and strategy.should_sell(price, latest_activity):
                    await self.execute_sell(symbol, price, latest_activity)

            except Exception as e:
                logging.error(f"Error checking prices for {symbol}: {e}")

    async def execute_buy(self, symbol: str, price: float, quantity: float, strategy: PriceActionStrategy):
        try:
            rounded_price = round(price, self.symbol_info[symbol]['price_precision'])
            rounded_quantity = round(quantity, self.symbol_info[symbol]['quantity_precision'])

            order = self.client.create_order(
                symbol=symbol,
                side='BUY',
                type='LIMIT',
                quantity=rounded_quantity,
                price=rounded_price,
                timeInForce='GTC'
            )
            logging.info(f"Executed BUY for {symbol}: {quantity} at {price}")

            # Save activity and notify
            self.latest_activities[symbol] = {'buy': True, 'sell': False, 'quantity': quantity, 'price': price, 'stop_loss': None, 'take_profit': None}
            self.storage.save_latest_activity(symbol, self.latest_activities[symbol])

            notifikasi_buy(symbol, quantity, price)
        except BinanceAPIException as e:
            logging.error(f"Error executing BUY order for {symbol}: {e}")
        except Exception as e:
            logging.error(f"Unexpected error during BUY for {symbol}: {e}")

    async def execute_sell(self, symbol: str, price: float, activity):
        try:
            quantity = activity['quantity']
            rounded_price = round(price, self.symbol_info[symbol]['price_precision'])
            rounded_quantity = round(quantity, self.symbol_info[symbol]['quantity_precision'])

            order = self.client.create_order(
                symbol=symbol,
                side='SELL',
                type='LIMIT',
                quantity=rounded_quantity,
                price=rounded_price,
                timeInForce='GTC'
            )

            logging.info(f"Executed SELL for {symbol}: {quantity} at {price}")
            self.latest_activities[symbol] = {'buy': False, 'sell': True, 'quantity': 0, 'price': 0, 'stop_loss': None, 'take_profit': None}
            self.storage.save_latest_activity(symbol, self.latest_activities[symbol])

            notifikasi_sell(symbol, activity['quantity'], price)
        except BinanceAPIException as e:
            logging.error(f"Error executing SELL order for {symbol}: {e}")
        except Exception as e:
            logging.error(f"Unexpected error during SELL for {symbol}: {e}")

    async def run(self):
        try:
            while self.running:
                # Periodically check USDT balance and update allocation
                self.update_symbol_usdt_allocation()
                usdt_balance = self.get_usdt_balance()
                logging.info(f"Current USDT balance: {usdt_balance}")
                await asyncio.sleep(60)  # Delay to prevent hitting rate limits

                await self.check_prices()

        except Exception as e:
            logging.error(f"Error during bot execution: {e}")

if __name__ == "__main__":
    bot = BotTrading()
    asyncio.run(bot.run())
