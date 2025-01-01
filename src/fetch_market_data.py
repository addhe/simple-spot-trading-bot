import ccxt
import logging

# Setup logger
logger = logging.getLogger(__name__)

def fetch_market_data(exchange, symbol, timeframe):
    """Ambil data harga."""
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe=timeframe)
        return bars
    except ccxt.BaseError as e:
        logger.error(f"Error fetching market data: {e}")
        return None