#!/usr/bin/env python
import os
import sys
import logging
from datetime import datetime
from typing import Optional, Dict, Tuple
from decimal import Decimal

# Add project root to Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from binance.client import Client
from binance.exceptions import BinanceAPIException
from config.settings import API_KEY, API_SECRET, BASE_URL, SYMBOLS
from src.send_telegram_message import send_telegram_message

# Setup logging
os.makedirs('logs/bot', exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/bot/get_latest_price.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialize Binance client
client = Client(api_key=API_KEY, api_secret=API_SECRET)
if BASE_URL:
    client.API_URL = BASE_URL

def get_db_connection():
    """Get database connection with proper error handling"""
    try:
        import sqlite3
        conn = sqlite3.connect('table_transactions.db')
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        logger.error(f"Database connection error: {e}")
        return None

def get_last_transaction_price(symbol: str, type_: str) -> Optional[Tuple[datetime, float, float]]:
    """
    Get the last transaction price for a symbol and type

    Args:
        symbol: Trading pair symbol (e.g., 'BTCUSDT')
        type_: Transaction type ('BUY' or 'SELL')

    Returns:
        Tuple of (timestamp, quantity, price) if found, None otherwise
    """
    conn = get_db_connection()
    if not conn:
        return None

    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT timestamp, quantity, price
            FROM transactions
            WHERE symbol = ? AND UPPER(type) = UPPER(?)
            ORDER BY timestamp DESC
            LIMIT 1
        ''', (symbol, type_))

        result = cursor.fetchone()
        if result:
            timestamp = datetime.strptime(result['timestamp'], '%Y-%m-%d %H:%M:%S')
            return timestamp, float(result['quantity']), float(result['price'])
        return None

    except Exception as e:
        logger.error(f"Error getting {type_.lower()} price for {symbol}: {e}")
        return None
    finally:
        conn.close()

def get_current_price(symbol: str) -> Optional[float]:
    """
    Get current market price from Binance

    Args:
        symbol: Trading pair symbol (e.g., 'BTCUSDT')

    Returns:
        Current price as float if successful, None otherwise
    """
    try:
        ticker = client.get_symbol_ticker(symbol=symbol)
        return float(ticker['price'])
    except BinanceAPIException as e:
        logger.error(f"Binance API error getting price for {symbol}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error getting price for {symbol}: {e}")
        return None

def format_price_message(symbol: str) -> str:
    """Format price information for Telegram message"""
    # Get current price
    current_price = get_current_price(symbol)
    if not current_price:
        return f"❌ Failed to get current price for {symbol}"

    # Get last buy and sell prices
    last_buy = get_last_transaction_price(symbol, 'BUY')
    last_sell = get_last_transaction_price(symbol, 'SELL')

    msg_lines = [f"💰 <b>{symbol} Price Info</b>"]

    # Add current price
    msg_lines.append(f"Current: <code>${current_price:.2f}</code>")

    # Add last buy price if exists
    if last_buy:
        timestamp, quantity, price = last_buy
        diff = ((current_price - price) / price) * 100
        emoji = "📈" if diff >= 0 else "📉"
        msg_lines.append(
            f"Last Buy: <code>${price:.2f}</code> ({emoji}{diff:+.2f}%)\n"
            f"Amount: <code>{quantity:.8f}</code>\n"
            f"Time: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
        )

    # Add last sell price if exists
    if last_sell:
        timestamp, quantity, price = last_sell
        msg_lines.append(
            f"Last Sell: <code>${price:.2f}</code>\n"
            f"Amount: <code>{quantity:.8f}</code>\n"
            f"Time: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
        )

    return "\n".join(msg_lines)

def main():
    """Main function to get and display latest prices"""
    try:
        if not API_KEY or not API_SECRET:
            raise ValueError("API Key and Secret not found!")

        for symbol in SYMBOLS:
            msg = format_price_message(symbol)
            send_telegram_message(msg)
            logger.info(f"Sent price info for {symbol}")

    except Exception as e:
        error_msg = f"Error in price check: {str(e)}"
        logger.error(error_msg)
        send_telegram_message(f"❌ {error_msg}")

if __name__ == "__main__":
    main()
