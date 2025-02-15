from binance.exceptions import BinanceAPIException
from binance.client import Client
from src.get_balances import get_balances
from src.save_transaction import save_transaction
from src.logger import logger
from .get_last_price import get_last_price
from collections import deque
import numpy as np
from config.settings import SYMBOLS, MARKET_VOLATILITY_LIMIT, TAKE_PROFIT, STOP_LOSS_PERCENTAGE

# Define moving average windows
short_window = 5  # Short-term moving average window
long_window = 20   # Long-term moving average window

# Initialize a deque to store prices for moving average calculation
prices = deque(maxlen=long_window)

def is_valid_symbol(symbol):
    return symbol in SYMBOLS

def calculate_moving_average(prices, window):
    if len(prices) < window:
        return None
    return sum(prices[-window:]) / window

def calculate_rsi(prices, window=14):
    if len(prices) < window:
        return None
    deltas = np.diff(prices)
    gain = np.where(deltas > 0, deltas, 0)
    loss = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gain[-window:])
    avg_loss = np.mean(loss[-window:])
    rs = avg_gain / avg_loss if avg_loss > 0 else 0
    return 100 - (100 / (1 + rs))

def calculate_bollinger_bands(prices, window=20, num_std_dev=2):
    if len(prices) < window:
        return None, None
    rolling_mean = np.mean(prices[-window:])
    rolling_std = np.std(prices[-window:])
    upper_band = rolling_mean + (rolling_std * num_std_dev)
    lower_band = rolling_mean - (rolling_std * num_std_dev)
    return upper_band, lower_band

def should_buy():
    short_ma = calculate_moving_average(prices, short_window)
    long_ma = calculate_moving_average(prices, long_window)
    rsi = calculate_rsi(prices)
    upper_band, lower_band = calculate_bollinger_bands(prices)
    current_price = prices[-1]

    # Adjusted condition to allow buying if current price is within 1% of moving average
    return (short_ma > long_ma and rsi < 30 and current_price < lower_band) or \
           (current_price < long_ma * 1.01 and current_price > long_ma * 0.99)

def should_sell():
    short_ma = calculate_moving_average(prices, short_window)
    long_ma = calculate_moving_average(prices, long_window)
    rsi = calculate_rsi(prices)
    upper_band, lower_band = calculate_bollinger_bands(prices)
    current_price = prices[-1]
    return (short_ma < long_ma and rsi > 70 and current_price > upper_band) if short_ma and long_ma and rsi and upper_band and lower_band else False

def buy_asset(client, symbol, quantity):
    """
    Perform a market buy of the specified asset on Binance.
    """
    if not is_valid_symbol(symbol):
        logger.error(f"Invalid symbol: {symbol} not in SYMBOLS list.")
        return

    try:
        # Get current market price
        ticker = client.get_symbol_ticker(symbol=symbol)
        current_price = float(ticker['price'])

        # Calculate order parameters
        stop_loss = current_price * (1 - STOP_LOSS_PERCENTAGE)
        take_profit = current_price * TAKE_PROFIT.get(symbol, 1.02)  # Default 2% profit

        # Place market buy order
        order = client.create_order(
            symbol=symbol,
            side=Client.SIDE_BUY,
            type=Client.ORDER_TYPE_MARKET,
            quantity=quantity
        )

        if order['status'] == 'FILLED':
            logger.info(f"Buy order executed for {symbol} at {current_price}")
            # Save transaction details
            save_transaction(symbol, 'BUY', quantity, current_price)
            return True, order
        else:
            logger.error(f"Buy order failed for {symbol}: {order}")
            return False, None

    except BinanceAPIException as e:
        logger.error(f"Binance API error during buy: {e}")
        return False, None
    except Exception as e:
        logger.error(f"Unexpected error during buy: {e}")
        return False, None

def sell_asset(client, symbol, quantity):
    """
    Perform a market sell of the specified asset on Binance.
    """
    if not is_valid_symbol(symbol):
        logger.error(f"Invalid symbol: {symbol} not in SYMBOLS list.")
        return

    try:
        # Place market sell order
        order = client.create_order(
            symbol=symbol,
            side=Client.SIDE_SELL,
            type=Client.ORDER_TYPE_MARKET,
            quantity=quantity
        )

        if order['status'] == 'FILLED':
            # Get the actual sell price
            sell_price = float(order['fills'][0]['price'])
            logger.info(f"Sell order executed for {symbol} at {sell_price}")
            # Save transaction details
            save_transaction(symbol, 'SELL', quantity, sell_price)
            return True, order
        else:
            logger.error(f"Sell order failed for {symbol}: {order}")
            return False, None

    except BinanceAPIException as e:
        logger.error(f"Binance API error during sell: {e}")
        return False, None
    except Exception as e:
        logger.error(f"Unexpected error during sell: {e}")
        return False, None

def convert_asset_to_usdt(client, symbol, quantity):
    """
    Convert an asset to USDT using market sell
    """
    success, order = sell_asset(client, symbol, quantity)
    if success:
        logger.info(f"Successfully converted {quantity} {symbol} to USDT")
        return True
    else:
        logger.error(f"Failed to convert {quantity} {symbol} to USDT")
        return False
