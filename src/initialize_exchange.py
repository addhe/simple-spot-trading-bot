import logging
import os
from binance.spot import Spot as Client

# Setup logger
logger = logging.getLogger(__name__)

def initialize_exchange():
    try:
        # Load API Key dan Secret dari Environment Variables
        api_key = os.environ.get('API_KEY_BINANCE')
        api_secret = os.environ.get('API_SECRET_BINANCE')

        if not api_key or not api_secret:
            logger.error("API Key atau Secret tidak ditemukan pada environment variables")
            raise Exception("API Key atau Secret tidak ditemukan pada environment variables")

        # Buat client Binance
        client = Client(api_key, api_secret, base_url="https://testnet.binance.vision")
        return client
    except Exception as e:
        logger.error(f"Error inisialisasi exchange: {e}")
        raise Exception(f"Error inisialisasi exchange: {e}")
