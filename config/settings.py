#config/settings.py
import os

settings = {
    'API_KEY': os.environ['API_KEY_SPOT_TESTNET_BINANCE'],
    'API_SECRET': os.environ['API_SECRET_SPOT_TESTNET_BINANCE'],
    'BASE_URL': 'https://testnet.binance.vision/api'
}
