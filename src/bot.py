import os
import schedule
import time
import pickle
import hashlib
import logging
import math
from binance.client import Client
from binance.exceptions import BinanceAPIException
from config.settings import settings
from config.config import SYMBOLS, INTERVAL
from src.strategy import PriceActionStrategy
from src.notifikasi_telegram import notifikasi_buy, notifikasi_sell, notifikasi_balance
from src.check_price import CryptoPriceChecker  # Mengimpor kelas CryptoPriceChecker

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
        self.running = True
        self.symbol_info = {}
        self.init_symbol_info()
        self.price_checker = CryptoPriceChecker(self.client)  # Menggunakan CryptoPriceChecker

    def init_symbol_info(self):
        """Initialize symbol information including precision and minimum notional requirements."""
        try:
            exchange_info = self.client.get_exchange_info()
            for symbol_info in exchange_info['symbols']:
                if symbol_info['symbol'] in SYMBOLS:
                    try:
                        # Get LOT_SIZE filter
                        lot_size_filter = next((f for f in symbol_info['filters'] if f['filterType'] == 'LOT_SIZE'), None)
                        if not lot_size_filter:
                            logging.warning(f"No LOT_SIZE filter found for {symbol_info['symbol']}")
                            continue

                        # Get PRICE_FILTER
                        price_filter = next((f for f in symbol_info['filters'] if f['filterType'] == 'PRICE_FILTER'), None)
                        if not price_filter:
                            logging.warning(f"No PRICE_FILTER filter found for {symbol_info['symbol']}")
                            continue

                        # Get MIN_NOTIONAL filter, use default if not found
                        min_notional_filter = next((f for f in symbol_info['filters'] if f['filterType'] == 'MIN_NOTIONAL'), None)
                        min_notional = float(min_notional_filter['minNotional']) if min_notional_filter else 10.0  # Default to 10 USDT if not found

                        self.symbol_info[symbol_info['symbol']] = {
                            'quantity_precision': self.get_precision_from_step_size(lot_size_filter['stepSize']),
                            'price_precision': self.get_precision_from_step_size(price_filter['tickSize']),
                            'min_quantity': float(lot_size_filter['minQty']),
                            'max_quantity': float(lot_size_filter['maxQty']),
                            'min_notional': min_notional
                        }

                        logging.info(f"Initialized {symbol_info['symbol']} info: {self.symbol_info[symbol_info['symbol']]}")

                    except Exception as e:
                        logging.error(f"Error processing filters for {symbol_info['symbol']}: {str(e)}")
                        continue

            if not self.symbol_info:
                raise Exception("No valid symbols could be initialized")

            logging.info(f"Successfully initialized {len(self.symbol_info)} symbols")

        except Exception as e:
            logging.error(f"Error initializing symbol info: {str(e)}")
            raise

    def get_usdt_balance(self) -> float:
        """Get available USDT balance."""
        try:
            balance = self.client.get_asset_balance(asset='USDT')
            return float(balance['free'])
        except Exception as e:
            logging.error(f"Error getting USDT balance: {e}")
            return 0.0

    def get_precision_from_step_size(self, step_size: str) -> int:
        """Get precision from step size string."""
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
            return 8  # Default to 8 decimal places if there's an error

    def round_step_size(self, quantity: float, step_size: float) -> float:
        """Round quantity to step size."""
        return math.floor(quantity / step_size) * step_size

    def get_config_hash(self):
        """Calculate hash of current configuration settings."""
        config_str = f"{settings['API_KEY']}{settings['API_SECRET']}{str(SYMBOLS)}{INTERVAL}"
        return hashlib.md5(config_str.encode()).hexdigest()

    def load_historical_data(self, symbol: str) -> list:
        """Load historical price data for a symbol."""
        try:
            with open(f'historical_data_{symbol}.pkl', 'rb') as f:
                return pickle.load(f)
        except FileNotFoundError:
            return []
        except Exception as e:
            logging.error(f"Error loading historical data for {symbol}: {e}")
            return []

    def save_historical_data(self, symbol: str) -> None:
        """Save historical price data for a symbol."""
        try:
            with open(f'historical_data_{symbol}.pkl', 'wb') as f:
                pickle.dump(self.historical_data[symbol], f)
        except Exception as e:
            logging.error(f"Error saving historical data for {symbol}: {e}")

    def load_latest_activity(self, symbol: str) -> dict:
        try:
            with open(f'latest_activity_{symbol}.pkl', 'rb') as f:
                return pickle.load(f)
        except FileNotFoundError:
            return {'buy': False, 'sell': False, 'symbol': symbol, 'quantity': 0, 'price': 0}
        except Exception as e:
            logging.error(f"Error saat memuat aktivitas terbaru untuk {symbol}: {e}")
            return {'buy': False, 'sell': False, 'symbol': symbol, 'quantity': 0, 'price': 0}

    def save_latest_activity(self, symbol: str) -> None:
        try:
            with open(f'latest_activity_{symbol}.pkl', 'wb') as f:
                pickle.dump(self.latest_activities[symbol], f)
        except Exception as e:
            logging.error(f"Error saat menyimpan aktivitas terbaru untuk {symbol}: {e}")

    def calculate_dynamic_quantity(self, symbol: str, price: float) -> float:
        try:
            # Get available USDT balance
            available_usdt = self.get_usdt_balance()
            logging.info(f"Available USDT balance: {available_usdt}")

            # Calculate maximum quantity based on available balance
            raw_quantity = available_usdt / price

            # Get symbol precision info
            symbol_info = self.symbol_info[symbol]
            quantity_precision = symbol_info['quantity_precision']
            min_quantity = symbol_info['min_quantity']
            max_quantity = symbol_info['max_quantity']
            min_notional = symbol_info['min_notional']

            # Round to the correct precision
            quantity = round(raw_quantity, quantity_precision)

            # Ensure quantity is within allowed range
            quantity = max(min_quantity, min(quantity, max_quantity))

            # Check if order meets minimum notional value
            notional_value = quantity * price
            if notional_value < min_notional:
                logging.warning(f"Order value ({notional_value} USDT) is below minimum notional ({min_notional} USDT)")
                return 0.0

            return quantity
        except Exception as e:
            logging.error(f"Error calculating quantity for {symbol}: {e}")
            return 0.0

    def check_prices(self) -> None:
        for symbol in SYMBOLS:
            try:
                strategy = self.strategies[symbol]
                latest_activity = self.latest_activities[symbol]
                action, price = self.price_checker.check_price(symbol, latest_activity)  # Menggunakan price_checker
                price = float(price)  # Ensure price is float

                # Only proceed with BUY if we have sufficient USDT balance
                if action == 'BUY':
                    available_usdt = self.get_usdt_balance()
                    min_notional = self.symbol_info[symbol]['min_notional']

                    if available_usdt < min_notional:
                        logging.warning(f"Insufficient USDT balance ({available_usdt}) for minimum notional ({min_notional})")
                        continue

                    quantity = self.calculate_dynamic_quantity(symbol, price)

                    if quantity > 0:
                        logging.info(f"Melakukan pembelian {symbol} pada harga {price} sebanyak {quantity}")
                        self.execute_buy(symbol, price, quantity, strategy)

                elif action == 'SELL':
                    self.execute_sell(symbol, price, latest_activity)

                if latest_activity['buy']:
                    if strategy.should_sell(price, latest_activity):
                        self.execute_sell(symbol, price, latest_activity)

                if self.historical_data[symbol] and self.historical_data[symbol][-1]['price'] != price:
                    self.historical_data[symbol].append({
                        'timestamp': time.time(),
                        'price': float(price),  # Ensure price is float
                        'buy_price': float(strategy.calculate_dynamic_buy_price()),  # Ensure price is float
                        'sell_price': float(strategy.calculate_dynamic_sell_price())  # Ensure price is float
                    })
                    self.save_historical_data(symbol)

            except Exception as e:
                logging.error(f"Error dalam check_price untuk {symbol}: {e}")
                time.sleep(1)
                continue

    def execute_buy(self, symbol: str, price: float, quantity: float, strategy) -> None:
        try:
            # Round price according to symbol's price precision
            price_precision = self.symbol_info[symbol]['price_precision']
            rounded_price = round(price, price_precision)

            # Round quantity according to symbol's quantity precision
            quantity_precision = self.symbol_info[symbol]['quantity_precision']
            rounded_quantity = round(quantity, quantity_precision)

            order = self.client.create_order(
                symbol=symbol,
                side='BUY',
                type='LIMIT',
                quantity=rounded_quantity,
                price=rounded_price,
                timeInForce='GTC'
            )
            logging.debug(f"Order Detail: {order}")

            risk_management = strategy.manage_risk('BUY', rounded_price, rounded_quantity)
            self.latest_activities[symbol] = {
                'buy': True,
                'sell': False,
                'symbol': symbol,
                'quantity': rounded_quantity,
                'price': rounded_price,
                'estimasi_profit': 0,
                'stop_loss': risk_management['stop_loss'],
                'take_profit': risk_management['take_profit']
            }
            self.save_latest_activity(symbol)
            notifikasi_buy(symbol, rounded_quantity, rounded_price)
            notifikasi_balance(self.client)
        except BinanceAPIException as e:
            logging.error(f"Error API saat melakukan pembelian {symbol}: {e}")
        except Exception as e:
            logging.error(f"Error saat melakukan pembelian {symbol}: {e}")

    def execute_sell(self, symbol: str, price: float, latest_activity: dict) -> None:
        estimasi_profit = price - latest_activity['price'] if latest_activity['price'] else 0
        if estimasi_profit > 0:
            logging.info(f"Melakukan penjualan {symbol} pada harga {price} sebanyak {latest_activity['quantity']}")
            try:
                # Round price according to symbol's price precision
                price_precision = self.symbol_info[symbol]['price_precision']
                rounded_price = round(price, price_precision)

                # Round quantity according to symbol's quantity precision
                quantity_precision = self.symbol_info[symbol]['quantity_precision']
                rounded_quantity = round(latest_activity['quantity'], quantity_precision)

                order = self.client.create_order(
                    symbol=symbol,
                    side='SELL',
                    type='LIMIT',
                    quantity=rounded_quantity,
                    price=rounded_price,
                    timeInForce='GTC'
                )
                logging.debug(f"Order Detail: {order}")
                self.latest_activities[symbol] = {
                    'buy': False,
                    'sell': True,
                    'symbol': symbol,
                    'quantity': rounded_quantity,
                    'price': rounded_price,
                    'estimasi_profit': estimasi_profit,
                    'stop_loss': 0,
                    'take_profit': 0
                }
                self.save_latest_activity(symbol)
                notifikasi_sell(symbol, rounded_quantity, rounded_price, estimasi_profit)
                notifikasi_balance(self.client)
            except BinanceAPIException as e:
                logging.error(f"Error API saat melakukan penjualan {symbol}: {e}")
            except Exception as e:
                logging.error(f"Error saat melakukan penjualan {symbol}: {e}")
        else:
            logging.info(f"Tidak melakukan penjualan {symbol} karena estimasi profit negatif: {estimasi_profit}")

# Create a bot instance and schedule price checks
bot = BotTrading()
schedule.every(30).seconds.do(bot.check_prices)

while bot.running:
    schedule.run_pending()
    time.sleep(1)
