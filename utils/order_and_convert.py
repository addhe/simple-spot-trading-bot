import os
from binance.client import Client
from src.logger import logger

# Function to convert asset to USDT

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

# Test the conversion feature
if __name__ == '__main__':
    # Initialize Binance client
    api_key = os.getenv('API_KEY')
    api_secret = os.getenv('API_SECRET')
    client = Client(api_key, api_secret)

    # Example usage
    convert_asset_to_usdt(client, 'BTC', 0.01)  # Convert 0.01 BTC to USDT
