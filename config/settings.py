import os

MAX_INVESTMENT_PER_TRADE = 0.1  # Maksimal 10% dari total portfolio per trade
STOP_LOSS_PERCENTAGE = 0.05     # Cut loss pada -5%
TRAILING_STOP = 0.02            # Trailing stop 2% dari harga tertinggi
API_KEY = os.getenv('API_KEY_SPOT_BINANCE', '')
API_SECRET = os.getenv('API_SECRET_SPOT_BINANCE', '')
BASE_URL = 'https://api.binance.com/api'
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', '')
TELEGRAM_GROUP_ID = os.getenv('TELEGRAM_GROUP_ID_PROD', '')
SYMBOLS = ['USDCUSDT', 'ETHUSDT', 'SOLUSDT']
STATUS_INTERVAL = 3600  # 1 jam dalam detik