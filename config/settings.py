import os

# API Configuration
API_KEY = os.getenv('API_KEY_SPOT_BINANCE', '')
API_SECRET = os.getenv('API_SECRET_SPOT_BINANCE', '')
BASE_URL = 'https://api.binance.com/api'

# Telegram Configuration
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', '')
TELEGRAM_GROUP_ID = os.getenv('TELEGRAM_GROUP_ID_PROD', '')

# Trading Pairs Configuration
SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']

# Portfolio Management
MAX_INVESTMENT_PER_TRADE = 10.00     # Increased max investment per trade
PORTFOLIO_STOP_LOSS = 0.15          # Stop trading if portfolio drops 15%
DAILY_LOSS_LIMIT = -0.03             # Stop trading if daily loss reaches 3%

# Position Management
STOP_LOSS_PERCENTAGE = 0.03         # 3% stop loss for quicker cut loss
MIN_POSITION_SIZE = 0.0001          # Minimum position size for trades
TRAILING_STOP = {                   # Custom trailing stop per pair
    'BTCUSDT': 0.015,               # BTC more stable, 1.5% trailing stop
    'ETHUSDT': 0.02,                # ETH moderate volatility, 2%
    'SOLUSDT': 0.03                 # SOL more volatile, 3%
}
TAKE_PROFIT = {                     # Take profit targets
    'BTCUSDT': 1.02,                # 2% profit for BTC
    'ETHUSDT': 1.025,               # 2.5% profit for ETH
    'SOLUSDT': 1.05                 # 5% profit for SOL
}

# Entry Strategy Parameters
BUY_MULTIPLIER = 0.98              # 5% below market for better entry
SELL_MULTIPLIER = 1.01             # 2% above market for better profit
TOLERANCE = 0.02                   # Reduced for more precision
MIN_VOLUME_MULTIPLIER = 1.2        # Minimum volume must be 1.2x average

# Time Intervals
INTERVAL = '15m'                    # 15-minute timeframe to reduce noise
CACHE_LIFETIME = 60                 # 1 minute for faster response
STATUS_INTERVAL = 1800              # 30 minutes for better monitoring

# Trading Strategy Parameters
RSI_OVERBOUGHT = 70  # RSI level for overbought condition
RSI_OVERSOLD = 30    # RSI level for oversold condition
BOLLINGER_WINDOW = 20 # Window for Bollinger Bands
BOLLINGER_STD_DEV = 2 # Standard deviation for Bollinger Bands

# Technical Analysis Parameters
RSI_PERIOD = 14
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
BB_PERIOD = 20
BB_STD = 2

# Risk Management
MAX_POSITIONS = 3                   # Maximum concurrent positions
MIN_USDT_BALANCE = 50               # Minimum USDT to maintain (adjusted from 100)
MIN_USD_BALANCE = 1.00              # Minimum USD balance required for trading
MARKET_VOLATILITY_LIMIT = 0.15     # Increase market volatility limit to 15%

# Rate Limiting
RATE_LIMIT_PER_MINUTE = 1200        # Binance limit
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

# Persentase kenaikan harga jual
SELL_THRESHOLD_PERCENTAGE = 0.02  # Persentase kenaikan harga untuk melakukan penjualan (5%)
