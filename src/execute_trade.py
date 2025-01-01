import logging
from binance.spot import Spot as Client
from binance.lib.utils import config_logging
from binance.error import ClientError

# Konfigurasi logging
config_logging(logging, logging.INFO)
logger = logging.getLogger(__name__)

def execute_trade(api_key, api_secret, symbol, side, amount):
    try:
        # Buat klien Binance
        client = Client(api_key, api_secret, base_url="https://testnet.binance.vision")

        # Cek saldo akun
        balance = client.account()
        if not balance:
            logger.info("Cannot fetch balance, exchange might not be authenticated or there's a network issue")
            return

        # Dapatkan ticker symbol
        ticker = client.ticker_price(symbol)

        # Buat order
        if side == 'buy':
            # Create a buy order
            order = client.new_order(
                symbol=symbol,
                side='BUY',
                type='LIMIT',
                timeInForce='GTC',
                quantity=amount,
                price=ticker['price']
            )
        elif side == 'sell':
            # Create a sell order
            order = client.new_order(
                symbol=symbol,
                side='SELL',
                type='LIMIT',
                timeInForce='GTC',
                quantity=amount,
                price=ticker['price']
            )
        else:
            logger.error("Invalid side, cannot execute trade")
            return

        logger.info(f"Trade executed: {order}")
    except ClientError as e:
        logger.error(f"Error executing trade: {e.status_code}, {e.error_code}, {e.error_message}")
    except Exception as e:
        logger.error(f"Error executing trade: {e}")

# Contoh penggunaan
api_key = "YOUR_API_KEY"
api_secret = "YOUR_API_SECRET"
symbol = "BTCUSDT"
side = "buy"
amount = 0.01

execute_trade(api_key, api_secret, symbol, side, amount)