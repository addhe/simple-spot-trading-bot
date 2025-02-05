#!/usr/bin/env python
import os
import sys
import logging
from datetime import datetime
from decimal import Decimal, ROUND_DOWN
from typing import Dict, Optional

# Add project root to Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from binance.client import Client
from binance.exceptions import BinanceAPIException
from tenacity import retry, stop_after_attempt, wait_exponential
from config.settings import (
    API_KEY,
    API_SECRET,
    TELEGRAM_TOKEN,
    TELEGRAM_GROUP_ID,
    SYMBOLS,
    BASE_URL
)
from src.send_telegram_message import send_telegram_message

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/bot/get_balance.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialize Binance client
client = Client(api_key=API_KEY, api_secret=API_SECRET, testnet=True)
if BASE_URL:
    client.API_URL = BASE_URL

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=lambda e: isinstance(e, BinanceAPIException)
)
def get_balance(asset: str) -> Optional[Dict[str, float]]:
    """
    Get balance for a specific asset
    Returns a dictionary with 'free' and 'locked' balances
    """
    try:
        account = client.get_account()
        for balance in account['balances']:
            if balance['asset'] == asset:
                return {
                    'free': float(balance['free']),
                    'locked': float(balance['locked'])
                }
        return {'free': 0.0, 'locked': 0.0}
    except BinanceAPIException as e:
        logger.error(f"Binance API error getting balance for {asset}: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error getting balance for {asset}: {e}")
        return None

def get_balances() -> Dict[str, Dict[str, float]]:
    """
    Get balances for all assets with non-zero balance
    Returns a dictionary of assets with their free and locked balances
    """
    try:
        account = client.get_account()
        balances = {}

        # Get all trading assets from SYMBOLS
        trading_assets = set()
        for symbol in SYMBOLS:
            asset = symbol.replace('USDT', '')
            trading_assets.add(asset)
        trading_assets.add('USDT')  # Add USDT

        # Get balances for trading assets
        for balance in account['balances']:
            if balance['asset'] in trading_assets:
                free = float(balance['free'])
                locked = float(balance['locked'])
                balances[balance['asset']] = {
                    'free': free,
                    'locked': locked
                }

        return balances
    except BinanceAPIException as e:
        logger.error(f"Binance API error getting all balances: {e}")
        return {}
    except Exception as e:
        logger.error(f"Unexpected error getting all balances: {e}")
        return {}

def format_balance(balance: Dict[str, float]) -> str:
    """Format balance for display"""
    return f"Free: {balance['free']:.8f}, Locked: {balance['locked']:.8f}"

def get_last_price(symbol: str) -> Optional[float]:
    """Get last price for a symbol"""
    try:
        ticker = client.get_symbol_ticker(symbol=symbol)
        return float(ticker['price'])
    except Exception as e:
        logger.error(f"Error getting price for {symbol}: {e}")
        return None

def format_telegram_message(balances: Dict[str, Dict[str, float]]) -> str:
    """Format balances for Telegram message with USD values"""
    total_usdt = balances.get('USDT', {}).get('free', 0.0)
    total_portfolio_value = total_usdt  # Start with USDT balance

    msg_lines = [
        "💰 <b>Current Balances Report</b>",
        f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "📊 <b>Trading Assets:</b>"
    ]

    # Add each asset balance with USD value
    for symbol in SYMBOLS:
        asset = symbol.replace('USDT', '')
        if asset in balances:
            balance = balances[asset]
            free_balance = balance['free']
            locked_balance = balance['locked']
            total_balance = free_balance + locked_balance

            # Get current price and calculate USD value
            price = get_last_price(f"{asset}USDT")
            if price:
                usd_value = total_balance * price
                total_portfolio_value += usd_value

                # Format balance line
                balance_line = [
                    f"{asset}: {free_balance:.8f}",
                    f"(${usd_value:.2f})"
                ]

                # Add locked balance if exists
                if locked_balance > 0:
                    balance_line.insert(1, f"🔒{locked_balance:.8f}")

                # Add price
                balance_line.append(f"@ ${price:.2f}")

                msg_lines.append(" ".join(balance_line))
            else:
                msg_lines.append(f"{asset}: {free_balance:.8f}")
                if locked_balance > 0:
                    msg_lines[-1] += f" 🔒{locked_balance:.8f}"

    # Add USDT balance and portfolio total
    msg_lines.extend([
        "",
        "💵 <b>USDT Balance:</b>",
        f"Available: {total_usdt:.2f} USDT",
        "",
        "📈 <b>Portfolio Summary:</b>",
        f"Total Value: ${total_portfolio_value:.2f}"
    ])

    return "\n".join(msg_lines)

def main():
    """Main function for testing balance retrieval"""
    try:
        # Check API credentials
        if not API_KEY or not API_SECRET:
            raise ValueError("API Key and Secret not found! Make sure they are set in environment variables.")

        # Get and display all balances
        logger.info("Fetching all balances...")
        all_balances = get_balances()

        if not all_balances:
            msg = "❌ No balances found or error occurred"
            logger.warning(msg)
            send_telegram_message(msg)
            return

        # Display balances in console
        print("\n=== Current Balances ===")
        for asset, balance in all_balances.items():
            if balance['free'] > 0 or balance['locked'] > 0:
                print(f"{asset}: {format_balance(balance)}")

        # Get specific assets from SYMBOLS
        trading_assets = set()
        for symbol in SYMBOLS:
            trading_assets.add(symbol.replace('USDT', ''))
        trading_assets.add('USDT')

        print("\n=== Trading Asset Balances ===")
        for asset in trading_assets:
            balance = get_balance(asset)
            if balance:
                print(f"{asset}: {format_balance(balance)}")
            else:
                print(f"{asset}: Error fetching balance")

        # Send Telegram notification
        telegram_msg = format_telegram_message(all_balances)
        send_telegram_message(telegram_msg)
        logger.info("Balance report sent to Telegram")

    except ValueError as e:
        error_msg = f"Configuration error: {e}"
        logger.error(error_msg)
        send_telegram_message(f"❌ {error_msg}")
    except Exception as e:
        error_msg = f"Unexpected error: {e}"
        logger.error(error_msg)
        send_telegram_message(f"❌ {error_msg}")

if __name__ == "__main__":
    # Create logs directory if it doesn't exist
    os.makedirs('logs/bot', exist_ok=True)
    main()
