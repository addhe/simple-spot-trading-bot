#!/usr/bin/env python
import os
import logging
import sqlite3
from datetime import datetime
import time
from decimal import Decimal, ROUND_DOWN
from typing import Dict, Optional, Tuple
import requests
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceOrderException
from tenacity import retry, stop_after_attempt, wait_exponential

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/bot/sell_all_assets.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Environment variables
API_KEY = os.getenv('API_KEY_SPOT_TESTNET_BINANCE', '')
API_SECRET = os.getenv('API_SECRET_SPOT_TESTNET_BINANCE', '')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', '')
TELEGRAM_GROUP_ID = os.getenv('TELEGRAM_GROUP_ID', '')

# Initialize Binance client
client = Client(api_key=API_KEY, api_secret=API_SECRET, testnet=True)

# Trading pairs to monitor
SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']

def send_telegram_message(message: str) -> None:
    """Send message to Telegram"""
    try:
        if TELEGRAM_TOKEN and TELEGRAM_GROUP_ID:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            data = {
                "chat_id": TELEGRAM_GROUP_ID,
                "text": message,
                "parse_mode": "HTML"
            }
            response = requests.post(url, data=data, timeout=10)
            if not response.ok:
                logger.error(f"Failed to send Telegram message: {response.text}")
    except Exception as e:
        logger.error(f"Error sending Telegram message: {e}")

def get_db_connection() -> sqlite3.Connection:
    """Get database connection with proper error handling"""
    try:
        conn = sqlite3.connect('table_transactions.db')
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        logger.error(f"Database connection error: {e}")
        raise

def save_transaction(symbol: str, type: str, quantity: float, price: float) -> None:
    """Save transaction to database with proper error handling"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute('''
            INSERT INTO transactions (timestamp, symbol, type, quantity, price)
            VALUES (?, ?, ?, ?, ?)
        ''', (timestamp, symbol, type, quantity, price))
        conn.commit()
        logger.info(f"Transaction saved: {type} {quantity} {symbol} at {price}")
    except sqlite3.Error as e:
        logger.error(f"Failed to save transaction: {e}")
        raise
    finally:
        if 'conn' in locals():
            conn.close()

def get_symbol_precision(symbol: str) -> Tuple[int, int]:
    """Get price and quantity precision for a symbol"""
    try:
        info = client.get_symbol_info(symbol)
        if not info:
            raise ValueError(f"Symbol info not found for {symbol}")

        # Get quantity precision
        lot_size_filter = next(filter(lambda x: x['filterType'] == 'LOT_SIZE', info['filters']))
        step_size = Decimal(lot_size_filter['stepSize'])
        quantity_precision = abs(step_size.as_tuple().exponent)

        # Get price precision
        price_filter = next(filter(lambda x: x['filterType'] == 'PRICE_FILTER', info['filters']))
        tick_size = Decimal(price_filter['tickSize'])
        price_precision = abs(tick_size.as_tuple().exponent)

        return price_precision, quantity_precision
    except Exception as e:
        logger.error(f"Error getting precision for {symbol}: {e}")
        raise

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=lambda e: isinstance(e, BinanceAPIException)
)
def sell_asset(symbol: str, quantity: float) -> Optional[float]:
    """
    Sell an asset with proper error handling and retries
    Returns the executed price if successful, None otherwise
    """
    try:
        # Get symbol precision
        price_precision, quantity_precision = get_symbol_precision(symbol)

        # Round quantity according to symbol's precision
        quantity = float(Decimal(str(quantity)).quantize(
            Decimal(f"0.{'0' * quantity_precision}"),
            rounding=ROUND_DOWN
        ))

        if quantity <= 0:
            logger.warning(f"Quantity too small for {symbol}: {quantity}")
            return None

        # Place market sell order
        order = client.order_market_sell(
            symbol=symbol,
            quantity=quantity
        )

        # Calculate average fill price
        total_qty = sum(float(fill['qty']) for fill in order['fills'])
        total_price = sum(float(fill['qty']) * float(fill['price']) for fill in order['fills'])
        avg_price = total_price / total_qty if total_qty > 0 else 0

        # Save transaction and log success
        save_transaction(symbol, 'SELL', quantity, avg_price)
        logger.info(f"Successfully sold {quantity} {symbol} at average price {avg_price}")

        return avg_price

    except BinanceAPIException as e:
        logger.error(f"Binance API error selling {symbol}: {e}")
        raise
    except BinanceOrderException as e:
        logger.error(f"Order error selling {symbol}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error selling {symbol}: {e}")
        return None

def get_current_balances() -> Dict[str, float]:
    """Get current balances with proper error handling"""
    try:
        account = client.get_account()
        balances = {}
        for balance in account['balances']:
            free_balance = float(balance['free'])
            if free_balance > 0:
                balances[balance['asset']] = free_balance
        return balances
    except BinanceAPIException as e:
        logger.error(f"Failed to get balances: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error getting balances: {e}")
        return {}

def sell_all_assets() -> None:
    """Sell all assets and convert to USDT"""
    logger.info("Starting sell all assets process...")
    send_telegram_message("🚨 <b>EMERGENCY SELL ALL INITIATED</b>\nStarting to sell all assets...")

    try:
        # Get initial balances
        initial_balances = get_current_balances()
        if not initial_balances:
            msg = "❌ No balances available to sell"
            logger.info(msg)
            send_telegram_message(msg)
            return

        # Format initial balance message
        initial_msg = ["📊 <b>Initial Balances:</b>"]
        for asset, balance in initial_balances.items():
            initial_msg.append(f"{asset}: {balance:.8f}")
        send_telegram_message("\n".join(initial_msg))

        # Sell each asset
        total_usdt_value = 0.0
        for symbol in SYMBOLS:
            asset = symbol.replace('USDT', '')
            balance = initial_balances.get(asset, 0.0)

            if balance > 0:
                logger.info(f"Attempting to sell {balance} {asset}")
                send_telegram_message(f"🔄 Selling {balance:.8f} {asset}...")

                price = sell_asset(symbol, balance)
                if price:
                    usdt_value = balance * price
                    total_usdt_value += usdt_value
                    msg = f"✅ Sold {balance:.8f} {asset} at {price:.8f} USDT (Total: {usdt_value:.2f} USDT)"
                else:
                    msg = f"❌ Failed to sell {asset}"
                send_telegram_message(msg)
                time.sleep(1)  # Avoid rate limits

        # Get final balances
        final_balances = get_current_balances()

        # Format final status message
        final_msg = [
            "🏁 <b>Sell All Process Completed</b>",
            f"💰 Total USDT Value: {total_usdt_value:.2f}",
            "",
            "<b>Final Balances:</b>"
        ]
        for asset, balance in final_balances.items():
            final_msg.append(f"{asset}: {balance:.8f}")

        send_telegram_message("\n".join(final_msg))

    except Exception as e:
        error_msg = f"❌ Error during sell all process: {str(e)}"
        logger.error(error_msg)
        send_telegram_message(error_msg)
    finally:
        logger.info("Sell all process completed")

def main():
    """Main function with proper error handling"""
    try:
        # Validate API credentials
        if not API_KEY or not API_SECRET:
            raise ValueError("API Key and Secret not found! Make sure they are set in environment variables.")

        # Execute sell all
        sell_all_assets()

    except ValueError as e:
        error_msg = f"Configuration Error: {str(e)}"
        logger.error(error_msg)
        send_telegram_message(f"❌ {error_msg}")
    except Exception as e:
        error_msg = f"Critical Error: {str(e)}"
        logger.error(error_msg)
        send_telegram_message(f"❌ {error_msg}")

if __name__ == "__main__":
    main()
