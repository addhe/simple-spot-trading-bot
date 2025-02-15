from binance.exceptions import BinanceAPIException
from binance.client import Client
from src.get_balances import get_balances
from src.save_transaction import save_transaction
from src.logger import logger
from .get_last_price import get_last_price


def buy_asset(client, symbol, quantity):
    """
    Perform a market buy of the specified asset on Binance.
    """
    try:
        # Check internet connection
        if not _check_internet_connection():
            raise ConnectionError("No internet connection available")

        # Check if we have enough balance
        balances = get_balances()
        usdt_balance = float(balances.get('USDT', {}).get('free', 0.0))

        order_value = quantity * get_last_price(symbol)
        if usdt_balance < order_value:
            raise ValueError(f"Insufficient USDT balance. Required: {order_value}, Available: {usdt_balance}")

        order = client.order_market_buy(
            symbol=symbol,
            quantity=quantity
        )

        # Log successful transaction
        logger.info(f"✅ Buy order successful for {symbol}: Quantity: {quantity}, Price: {get_last_price(symbol)}, Total Value: {order_value} USDT")

        # Save transaction details
        save_transaction(symbol, 'BUY', quantity, get_last_price(symbol), order_value)

        return order

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


def sell_asset(client, symbol, buy_price, current_price, quantity):
    if current_price > buy_price:
        convert_asset_to_usdt(client, symbol, quantity)
    else:
        try:
            # Existing sell logic
            order = client.order_market_sell(
                symbol=symbol,
                quantity=quantity
            )

            # Log successful transaction
            logger.info(f"✅ Sell order successful for {symbol}: Quantity: {quantity}, Price: {get_last_price(symbol)}, Total Value: {quantity * get_last_price(symbol)} USDT")

            # Save transaction details
            save_transaction(symbol, 'SELL', quantity, get_last_price(symbol), quantity * get_last_price(symbol))

            return order

        except BinanceAPIException as e:
            logger.error(f"Binance API Exception during sell: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error during sell: {e}")
            raise
