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

# Environment variables
API_KEY = os.getenv('API_KEY_SPOT_TESTNET_BINANCE', '')
API_SECRET = os.getenv('API_SECRET_SPOT_TESTNET_BINANCE', '')

# Initialize Binance client
client = Client(api_key=API_KEY, api_secret=API_SECRET, testnet=True)

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
        for balance in account['balances']:
            free = float(balance['free'])
            locked = float(balance['locked'])
            if free > 0 or locked > 0:
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
            logger.warning("No balances found or error occurred")
            return

        # Display balances
        print("\n=== Current Balances ===")
        for asset, balance in all_balances.items():
            if balance['free'] > 0 or balance['locked'] > 0:
                print(f"{asset}: {format_balance(balance)}")

        # Get specific assets
        test_assets = ['BTC', 'ETH', 'SOL', 'USDT']
        print("\n=== Specific Asset Balances ===")
        for asset in test_assets:
            balance = get_balance(asset)
            if balance:
                print(f"{asset}: {format_balance(balance)}")
            else:
                print(f"{asset}: Error fetching balance")

    except ValueError as e:
        logger.error(f"Configuration error: {e}")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")

if __name__ == "__main__":
    # Create logs directory if it doesn't exist
    os.makedirs('logs/bot', exist_ok=True)
    main()
