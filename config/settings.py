# config/settings.py
import os

settings = {
    'API_KEY': os.environ['API_KEY_SPOT_TESTNET_BINANCE'],
    'API_SECRET': os.environ['API_SECRET_SPOT_TESTNET_BINANCE'],
    'BASE_URL': 'https://testnet.binance.vision/api',
    'TELEGRAM_TOKEN': os.getenv('TELEGRAM_TOKEN'),
    'TELEGRAM_GROUP_ID': os.getenv('TELEGRAM_GROUP_ID'),
    'SYMBOLS': ['BTCUSDT', 'ETHUSDT', 'SOLUSDT'],
    'INTERVAL': '1m',
    'CACHE_LIFETIME': 60,  # 5 menit
    'MAX_RETRIES': 5,
    'RETRY_BACKOFF': 1,  # 1 detik
    'BUY_MULTIPLIER': 0.925,
    'SELL_MULTIPLIER': 1.03,
    'TOLERANCE': 0.01
}