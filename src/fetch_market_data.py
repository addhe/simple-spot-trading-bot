import logging
from binance.spot import Spot as Client

# Setup logger
logger = logging.getLogger(__name__)

def fetch_market_data_from_exchange(symbol, timeframe):
    try:
        # Cek format simbol
        if not isinstance(symbol, str) or not symbol.isupper():
            logger.error("Format simbol tidak valid")
            return None

        # Cek format timeframe
        if not isinstance(timeframe, str):
            logger.error("Format timeframe tidak valid")
            return None

        # Dapatkan data harga
        client = Client(base_url="https://testnet.binance.vision")
        market_data = client.klines(symbol, timeframe, limit=100)

        if market_data:
            return market_data
        else:
            logger.error("Gagal mendapatkan data harga")
            return None
    except Exception as e:
        logger.error(f"Error fetching market data: {e}")
        logger.error(f"Simbol: {symbol}, Timeframe: {timeframe}")
        return None
