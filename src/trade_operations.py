from binance.exceptions import BinanceAPIException
from src.get_balances import get_balances
from src.save_transaction import save_transaction
from src.logger import logger


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


def sell_asset(client, symbol, quantity):
    """
    Perform a market sell of the specified asset on Binance.
    """
    try:
        # Similar implementation as buy_asset, but for selling
        pass
    except Exception as e:
        logger.error(f"Unexpected error during sell: {e}")
        raise
