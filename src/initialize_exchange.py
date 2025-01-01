import ccxt
import os

def initialize_exchange(api_key, api_secret):
    # Load API Key and Secret from Environment Variables
    api_key = os.environ.get('API_KEY_BINANCE')
    api_secret = os.environ.get('API_SECRET_BINANCE')

    try:
        exchange = ccxt.binance({
            'apiKey': api_key,
            'apiSecret': api_secret,
        })
        return exchange
    except ccxt.BaseError as e:
        raise Exception(f"Error inisialisasi exchange: {e}")