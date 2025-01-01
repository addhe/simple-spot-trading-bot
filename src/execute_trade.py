import ccxt
import logging

# Setup logger
logger = logging.getLogger(__name__)

def execute_trade(exchange, symbol, side, amount=0.01):
    """Eksekusi trade."""
    try:
        if side == 'buy':
            exchange.create_order(symbol, 'limit', 'buy', amount, exchange.fetch_ticker(symbol)['ask'])
        elif side == 'sell':
            exchange.create_order(symbol, 'limit', 'sell', amount, exchange.fetch_ticker(symbol)['bid'])
        logger.info(f"Trade executed: {side} {symbol}")
    except Exception as e:
        logger.error(f"Error executing trade: {str(e)}")