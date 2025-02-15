from binance.exceptions import BinanceAPIException
from binance.client import Client
from src.get_balances import get_balances
from src.save_transaction import save_transaction
from src.logger import logger
from .get_last_price import get_last_price
from collections import deque
import numpy as np

# Define moving average windows
short_window = 5  # Short-term moving average window
long_window = 20   # Long-term moving average window

# Initialize a deque to store prices for moving average calculation
prices = deque(maxlen=long_window)

# Define valid symbols
SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'LTCUSDT']  # Add more symbols as needed

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
    logger.info(f"Processing trade for {symbol}")
    if symbol not in SYMBOLS:
        logger.error(f"Invalid symbol: {symbol} not in SYMBOLS list.")
        return
    try:
        # Check internet connection
        if not _check_internet_connection():
            raise ConnectionError("No internet connection available")

        current_price = get_last_price(symbol)
        if current_price is None:
            logger.error(f"Invalid symbol: {symbol}")
            return
        prices.append(current_price)  # Add current price to the deque

        if should_buy():
            # Check if we have enough balance
            balances = get_balances()
            usdt_balance = float(balances.get('USDT', {}).get('free', 0.0))

            order_value = quantity * current_price
            if usdt_balance < order_value:
                raise ValueError(f"Insufficient USDT balance. Required: {order_value}, Available: {usdt_balance}")

            order = client.order_market_buy(
                symbol=symbol,
                quantity=quantity
            )

            # Log successful transaction
            logger.info(f"✅ Buy order successful for {symbol}: Quantity: {quantity}, Price: {current_price}, Total Value: {order_value} USDT")

            # Save transaction details
            save_transaction(symbol, 'BUY', quantity, current_price, order_value)

            return order
        else:
            logger.info(f"Waiting for a better price to buy {symbol}.")

    except BinanceAPIException as e:
        logger.error(f"Binance API Exception during buy: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error during buy: {e}")
        raise


def convert_asset_to_usdt(client, symbol, quantity):
    try:
        response = client.sapi_post('/v1/asset/convert', {
            'fromAsset': symbol,
            'toAsset': 'USDT',
            'amount': quantity,
            'type': 'spot'
        })
        logger.info(f"Converted {quantity} {symbol} to USDT successfully.")
    except Exception as e:
        logger.error(f"Error converting {symbol} to USDT: {e}")


def sell_asset(client, symbol, buy_price, quantity):
    logger.info(f"Processing trade for {symbol}")
    if symbol not in SYMBOLS:
        logger.error(f"Invalid symbol: {symbol} not in SYMBOLS list.")
        return
    current_price = get_last_price(symbol)
    if current_price is None:
        logger.error(f"Invalid symbol: {symbol}")
        return
    prices.append(current_price)  # Add current price to the deque

    if should_sell():
        try:
            # Existing sell logic
            order = client.order_market_sell(
                symbol=symbol,
                quantity=quantity
            )

            # Log successful transaction
            logger.info(f"✅ Sell order successful for {symbol}: Quantity: {quantity}, Price: {current_price}, Total Value: {quantity * current_price} USDT")

            # Save transaction details
            save_transaction(symbol, 'SELL', quantity, current_price, quantity * current_price)

            return order
        except BinanceAPIException as e:
            logger.error(f"Binance API Exception during sell: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error during sell: {e}")
            raise
    else:
        logger.info(f"Waiting for a better price to sell {symbol}.")
