from binance.client import Client
from config.settings import API_KEY, API_SECRET, BASE_URL

def get_binance_client():
    """Get a singleton instance of the Binance client"""
    if not hasattr(get_binance_client, '_client'):
        client = Client(api_key=API_KEY, api_secret=API_SECRET)
        if BASE_URL:
            client.API_URL = BASE_URL
        get_binance_client._client = client
    return get_binance_client._client
