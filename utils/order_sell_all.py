#!/usr/bin/env python
import os
import sys
import logging
import time
from datetime import datetime
from decimal import Decimal, ROUND_DOWN
from typing import Dict, Optional, List

# Add project root to Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceOrderException
from config.settings import (
    API_KEY,
    API_SECRET,
    BASE_URL,
    SYMBOLS
)
from src.send_telegram_message import send_telegram_message

# Setup logging
os.makedirs('logs/bot', exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/bot/sell_all_assets.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialize Binance client
client = Client(api_key=API_KEY, api_secret=API_SECRET)
if BASE_URL:
    client.API_URL = BASE_URL

def get_symbol_precision(symbol: str) -> int:
    """Get quantity precision for a symbol"""
    try:
        info = client.get_symbol_info(symbol)
        lot_size_filter = next(filter(lambda x: x['filterType'] == 'LOT_SIZE', info['filters']))
        step_size = Decimal(lot_size_filter['stepSize'])
        return abs(step_size.as_tuple().exponent)
    except Exception as e:
        logger.error(f"Error getting precision for {symbol}: {e}")
        return 8  # Default precision

def save_transaction(symbol: str, type_: str, quantity: float, price: float) -> None:
    """Save transaction to database"""
    try:
        import sqlite3
        conn = sqlite3.connect('table_transactions.db')
        cursor = conn.cursor()
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute('''
            INSERT INTO transactions (timestamp, symbol, type, quantity, price)
            VALUES (?, ?, ?, ?, ?)
        ''', (timestamp, symbol, type_, quantity, price))
        conn.commit()
        logger.info(f"Transaction saved: {type_} {quantity} {symbol} at {price}")
    except Exception as e:
        logger.error(f"Failed to save transaction: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

def sell_asset(symbol: str, quantity: float) -> Optional[float]:
    """Sell an asset and return the average price if successful"""
    try:
        # Round quantity according to symbol's precision
        precision = get_symbol_precision(symbol)
        quantity = float(Decimal(str(quantity)).quantize(
            Decimal(f"0.{'0' * precision}"),
            rounding=ROUND_DOWN
        ))

        if quantity <= 0:
            logger.warning(f"Quantity too small for {symbol}: {quantity}")
            return None

        # Place market sell order
        order = client.order_market_sell(symbol=symbol, quantity=quantity)

        # Calculate average fill price
        total_qty = sum(float(fill['qty']) for fill in order['fills'])
        total_price = sum(float(fill['qty']) * float(fill['price']) for fill in order['fills'])
        avg_price = total_price / total_qty if total_qty > 0 else 0

        # Save transaction
        save_transaction(symbol, 'SELL', quantity, avg_price)
        logger.info(f"Successfully sold {quantity} {symbol} at average price {avg_price}")

        return avg_price

    except BinanceAPIException as e:
        logger.error(f"Binance API error selling {symbol}: {e}")
    except BinanceOrderException as e:
        logger.error(f"Order error selling {symbol}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error selling {symbol}: {e}")
    return None

def get_current_balances() -> Dict[str, float]:
    """Get current balances for trading assets"""
    try:
        account = client.get_account()
        balances = {}
        for balance in account['balances']:
            free = float(balance['free'])
            if free > 0:
                balances[balance['asset']] = free
        return balances
    except Exception as e:
        logger.error(f"Error getting balances: {e}")
        return {}

def format_sale_summary(sales: List[Dict]) -> str:
    """Format sale summary for Telegram"""
    total_usdt = 0
    msg_lines = ["🚨 <b>Emergency Sell Summary</b>"]

    for sale in sales:
        symbol = sale['symbol']
        quantity = sale['quantity']
        price = sale['price']
        usdt_value = quantity * price
        total_usdt += usdt_value

        msg_lines.append(
            f"{symbol}: <code>{quantity:.8f}</code> @ <code>${price:.2f}</code>"
            f" = <code>${usdt_value:.2f}</code>"
        )

    msg_lines.extend([
        "",
        f"💵 <b>Total USDT:</b> <code>${total_usdt:.2f}</code>"
    ])

    return "\n".join(msg_lines)

def sell_all_assets() -> None:
    """Sell all assets and convert to USDT"""
    try:
        logger.info("Starting sell all assets process...")
        send_telegram_message("🚨 <b>EMERGENCY SELL ALL</b>\nStarting to sell all assets...")

        # Get initial balances
        balances = get_current_balances()
        if not balances:
            send_telegram_message("❌ No balances available to sell")
            return

        # Track successful sales
        successful_sales = []

        # Sell each asset
        for symbol in SYMBOLS:
            base_asset = symbol.replace('USDT', '')
            quantity = balances.get(base_asset, 0.0)

            if quantity > 0:
                logger.info(f"Attempting to sell {quantity} {base_asset}")
                price = sell_asset(symbol, quantity)

                if price:
                    successful_sales.append({
                        'symbol': base_asset,
                        'quantity': quantity,
                        'price': price
                    })
                    # Send individual sale notification
                    value = quantity * price
                    msg = (f"✅ Sold {base_asset}:\n"
                          f"Amount: <code>{quantity:.8f}</code>\n"
                          f"Price: <code>${price:.2f}</code>\n"
                          f"Value: <code>${value:.2f}</code>")
                    send_telegram_message(msg)
                else:
                    send_telegram_message(f"❌ Failed to sell {base_asset}")

                time.sleep(1)  # Avoid rate limits

        # Send final summary if there were any successful sales
        if successful_sales:
            summary = format_sale_summary(successful_sales)
            send_telegram_message(summary)

    except Exception as e:
        error_msg = f"❌ Error during sell all process: {str(e)}"
        logger.error(error_msg)
        send_telegram_message(error_msg)
    finally:
        logger.info("Sell all process completed")

def main():
    """Main function"""
    try:
        if not API_KEY or not API_SECRET:
            raise ValueError("API Key and Secret not found! Make sure they are set in environment variables.")
        sell_all_assets()
    except Exception as e:
        logger.error(f"Critical error: {e}")
        send_telegram_message(f"❌ Critical error: {str(e)}")

if __name__ == "__main__":
    main()
