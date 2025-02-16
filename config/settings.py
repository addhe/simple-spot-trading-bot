import os

# API Configuration
API_KEY = os.getenv('API_KEY_SPOT_BINANCE', '')
API_SECRET = os.getenv('API_SECRET_SPOT_BINANCE', '')
BASE_URL = 'https://api.binance.com/api'

# Telegram Configuration
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', '')
TELEGRAM_GROUP_ID = os.getenv('TELEGRAM_GROUP_ID_PROD', '')

# Trading Pairs Configuration
SYMBOLS = ['ETHUSDT', 'SOLUSDT']

# Minimum Trade Amount in Base Currency
MIN_TRADE_AMOUNT = {
    'ETHUSDT': 0.001,   # Minimum ETH
    'SOLUSDT': 0.1      # Minimum SOL
}

# Volume Requirements (adjusted for current market conditions)
MIN_24H_VOLUME = {
    'ETHUSDT': 10000,   # Adjusted from 200000
    'SOLUSDT': 5000     # Adjusted from 50000
}

# Symbol Info
SYMBOL_CONFIG = {
    'ETHUSDT': {
        'base_asset': 'ETH',
        'quote_asset': 'USDT',
        'price_precision': 2,
        'quantity_precision': 5
    },
    'SOLUSDT': {
        'base_asset': 'SOL',
        'quote_asset': 'USDT',
        'price_precision': 3,
        'quantity_precision': 2
    }
}

# Portfolio Management
MAX_INVESTMENT_PER_TRADE = 5.00      # Reduced max investment per trade
PORTFOLIO_STOP_LOSS = 0.15          # Stop trading if portfolio drops 15%
DAILY_LOSS_LIMIT = -0.03            # Stop trading if daily loss reaches 3%

# Position Management
STOP_LOSS_PERCENTAGE = 0.02         # Reduced to 2% stop loss
MIN_POSITION_SIZE = 0.0001          # Minimum position size for trades
TRAILING_STOP = {                   # Adjusted trailing stops
    'ETHUSDT': 0.015,              # ETH 1.5% trailing stop
    'SOLUSDT': 0.02                # SOL 2% trailing stop due to higher volatility
}

# Take Profit and Stop Loss Settings
TAKE_PROFIT = {
    'ETHUSDT': 0.025,              # 2.5% profit target for ETH
    'SOLUSDT': 0.03                # 3% profit target for SOL
}

# Market Volatility Settings
MARKET_VOLATILITY_LIMIT = {
    'ETHUSDT': 0.20,               # 20% volatility limit
    'SOLUSDT': 0.25                # 25% for SOL due to higher volatility
}

# Entry Strategy Parameters
BUY_MULTIPLIER = 0.985             # 1.5% below market for better entry
SELL_MULTIPLIER = 1.005            # 0.5% above market for quicker profit
TOLERANCE = 0.01                   # 1% tolerance for price movements
MIN_VOLUME_MULTIPLIER = 1.0        # Minimum volume must be 1x average

# Time Intervals
INTERVAL = '5m'                    # Changed to 5-minute timeframe for quicker entries/exits
CACHE_LIFETIME = 30                # 30 seconds for faster response
STATUS_INTERVAL = 300              # 5 minutes for status updates

# Trading Strategy Parameters
RSI_OVERBOUGHT = 75               # Increased RSI overbought level
RSI_OVERSOLD = 25                 # Decreased RSI oversold level
BOLLINGER_WINDOW = 20             # Window for Bollinger Bands
BOLLINGER_STD_DEV = 2            # Standard deviation for Bollinger Bands

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

# Rate Limiting
RATE_LIMIT_PER_MINUTE = 1200        # Binance limit
RATE_LIMIT_BUFFER = 0.8            # Use only 80% of rate limit

# Error Handling
MAX_API_RETRIES = 5                # Increase retries
ERROR_SLEEP_TIME = 10              # Increase sleep time
RETRY_MULTIPLIER = 2               # Exponential backoff multiplier

# Performance Tracking and Monitoring
WIN_RATE_THRESHOLD = 0.50          # Minimum win rate to continue trading
PROFIT_FACTOR_THRESHOLD = 1.2      # Minimum profit factor to continue trading
DETAILED_LOGGING = True            # Enable detailed logging

# Logging Configuration
LOG_LEVEL = 'INFO'
LOG_FORMAT = '%(asctime)s - %(levelname)s - %(message)s'
LOG_BACKUP_COUNT = 10              # Number of backup files to keep

# Volume Filters
VOLUME_MA_PERIOD = 24              # 24 periods for volume moving average

# Database Configuration
DB_FILE = 'table_transactions.db'
MAX_DATABASE_RETRIES = 3       # Maximum database connection retries

# Persentase kenaikan harga jual
SELL_THRESHOLD_PERCENTAGE = 0.02  # Persentase kenaikan harga untuk melakukan penjualan (5%)

# Status Monitor Configuration
DASHBOARD_HOST = '0.0.0.0'
DASHBOARD_PORT = 8050
UPDATE_INTERVAL = 60  # Update interval in seconds
ALERT_THRESHOLDS = {
    'cpu_usage': 80,
    'memory_usage': 80,
    'disk_usage': 80,
    'win_rate': 0.3,
    'drawdown': -0.05,
    'volatility': 0.8
}
