import os

# API Configuration
API_KEY = os.getenv('API_KEY_SPOT_TESTNET_BINANCE', '')
API_SECRET = os.getenv('API_SECRET_SPOT_TESTNET_BINANCE', '')
BASE_URL = 'https://testnet.binance.vision/api'

# Telegram Configuration
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', '')
TELEGRAM_GROUP_ID = os.getenv('TELEGRAM_GROUP_ID', '')

# Trading Pairs Configuration
SYMBOLS = ['USDCUSDT', 'ETHUSDT', 'SOLUSDT']

# Trading Parameters
MAX_INVESTMENT_PER_TRADE = 0.1  # Maksimal 10% dari total portfolio per trade
STOP_LOSS_PERCENTAGE = 0.05     # Cut loss pada -5%
TRAILING_STOP = 0.02            # Trailing stop 2% dari harga tertinggi
BUY_MULTIPLIER = 0.925          # Buy price multiplier
SELL_MULTIPLIER = 1.011         # Sell price multiplier
TOLERANCE = 0.01                # Price tolerance

# Time Intervals
INTERVAL = '1m'                 # Candlestick interval (1 minute)
CACHE_LIFETIME = 300            # Cache lifetime in seconds (5 minutes)
STATUS_INTERVAL = 3600          # Status check interval in seconds (1 hour)

# Technical Analysis Parameters
RSI_PERIOD = 14                 # Period for RSI calculation
RSI_OVERBOUGHT = 70            # RSI overbought threshold
RSI_OVERSOLD = 30              # RSI oversold threshold

# Database Configuration
DB_FILE = 'table_transactions.db'
MAX_DATABASE_RETRIES = 3       # Maximum database connection retries

# Error Handling
MAX_API_RETRIES = 3            # Maximum API call retries
ERROR_SLEEP_TIME = 5           # Sleep time between retries in seconds

# Logging Configuration
LOG_LEVEL = 'INFO'
MAX_LOG_SIZE = 10 * 1024 * 1024  # 10MB
LOG_BACKUP_COUNT = 5           # Number of backup log files to keep