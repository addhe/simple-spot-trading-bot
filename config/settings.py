import os

# API Configuration
API_KEY = os.getenv('API_KEY_SPOT_TESTNET_BINANCE', '')
API_SECRET = os.getenv('API_SECRET_SPOT_TESTNET_BINANCE', '')
BASE_URL = 'https://testnet.binance.vision/api'

# Telegram Configuration
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', '')
TELEGRAM_GROUP_ID = os.getenv('TELEGRAM_GROUP_ID', '')

# Trading Pairs Configuration
SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']

# Portfolio Management
MAX_INVESTMENT_PER_TRADE = 0.05     # Reduce dari 10% ke 5% untuk risk management yang lebih baik
PORTFOLIO_STOP_LOSS = 0.15          # Stop trading jika portfolio turun 15%
DAILY_LOSS_LIMIT = 0.07             # Stop trading jika kerugian harian mencapai 7%

# Position Management
STOP_LOSS_PERCENTAGE = 0.03         # Reduce dari 5% ke 3% untuk cut loss lebih cepat
TRAILING_STOP = {                   # Custom trailing stop per pair
    'BTCUSDT': 0.015,              # BTC lebih stabil, trailing stop 1.5%
    'ETHUSDT': 0.02,               # ETH moderate volatility, 2%
    'SOLUSDT': 0.025               # SOL lebih volatile, 2.5%
}
TAKE_PROFIT = {                     # Take profit targets
    'BTCUSDT': 1.02,               # 2% profit untuk BTC
    'ETHUSDT': 1.025,              # 2.5% profit untuk ETH
    'SOLUSDT': 1.03                # 3% profit untuk SOL
}

# Entry Strategy Parameters
BUY_MULTIPLIER = 0.995              # Slightly higher untuk better entry (0.5% dibawah market)
SELL_MULTIPLIER = 1.015             # Increase ke 1.5% untuk better profit
TOLERANCE = 0.01                    # Reduce untuk lebih precise
MIN_VOLUME_MULTIPLIER = 1.5         # Minimal volume harus 1.5x dari rata-rata

# Time Intervals
INTERVAL = '15m'                    # Increase timeframe untuk reduce noise
CACHE_LIFETIME = 60                 # Reduce ke 1 menit untuk faster response
STATUS_INTERVAL = 1800              # Reduce ke 30 menit untuk better monitoring

# Technical Analysis Parameters
RSI_PERIOD = 14
RSI_OVERBOUGHT = 75                 # Increase untuk stronger confirmation
RSI_OVERSOLD = 35                   # Decrease untuk stronger confirmation

# Additional Technical Indicators
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
BB_PERIOD = 20
BB_STD = 2

# Risk Management
MAX_POSITIONS = 3                   # Maximum concurrent positions
MIN_USDT_BALANCE = 100             # Minimum USDT to maintain
MARKET_VOLATILITY_LIMIT = {        # Don't trade if market volatility > limit
    'BTCUSDT': 0.05,               # 5% for BTC (more stable)
    'ETHUSDT': 0.08,               # 8% for ETH (moderate volatility)
    'SOLUSDT': 0.10                # 10% for SOL (higher volatility)
}

# Rate Limiting
RATE_LIMIT_PER_MINUTE = 1200       # Binance limit
RATE_LIMIT_BUFFER = 0.8            # Use only 80% of rate limit

# Error Handling
MAX_API_RETRIES = 5                # Increase retries
ERROR_SLEEP_TIME = 10              # Increase sleep time
RETRY_MULTIPLIER = 2               # Exponential backoff multiplier

# Performance Tracking
WIN_RATE_THRESHOLD = 0.55          # Minimum win rate to continue trading
PROFIT_FACTOR_THRESHOLD = 1.5      # Minimum profit factor to continue trading

# Logging Configuration
LOG_LEVEL = 'INFO'
MAX_LOG_SIZE = 20 * 1024 * 1024    # Increase ke 20MB
LOG_BACKUP_COUNT = 10              # Increase backup files
DETAILED_LOGGING = True            # Enable detailed logging

# Volume Filters
VOLUME_MA_PERIOD = 24              # 24 periods for volume moving average
MIN_24H_VOLUME = {                 # Minimum 24h volume in USDT
    'BTCUSDT': 1000000,
    'ETHUSDT': 500000,
    'SOLUSDT': 100000
}

# Database Configuration
DB_FILE = 'table_transactions.db'
MAX_DATABASE_RETRIES = 3       # Maximum database connection retries

# Minimum Trade Requirements
MIN_TRADE_AMOUNT = {
    'BTCUSDT': 0.0001,  # Minimum BTC amount
    'ETHUSDT': 0.001,   # Minimum ETH amount
    'SOLUSDT': 0.1      # Minimum SOL amount
}
