#!/usr/bin/env python
import os
import logging
from typing import Dict, Optional
from binance.client import Client
from binance.exceptions import BinanceAPIException
from tenacity import retry, stop_after_attempt, wait_exponential

from config.settings import (
    API_KEY,
    API_SECRET,
    BASE_URL,
    SYMBOLS
)

# Configure logging
logger = logging.getLogger(__name__)

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=lambda e: isinstance(e, BinanceAPIException)
)
def get_balance(client: Client, asset: str) -> float:
    """
    Get balance for a specific asset from Binance

    Args:
        client: Binance client instance
        asset: Asset symbol (e.g., 'BTC', 'ETH', 'USDT')

    Returns:
        float: Available balance of the asset, 0.0 if not found or error
    """
    try:
        account_info = client.get_account()
        for balance in account_info['balances']:
            if balance['asset'] == asset:
                return float(balance['free'])
        return 0.0
    except BinanceAPIException as e:
        logger.error(f"Binance API error while getting {asset} balance: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error while getting {asset} balance: {e}")
        return 0.0

def get_all_balances() -> Optional[Dict[str, Dict[str, float]]]:
    """
    Get balances for all trading assets and USDT

    Returns:
        Optional[Dict[str, Dict[str, float]]]: Dictionary of asset balances with structure:
            {
                'BTC': {'free': 0.1, 'locked': 0.0},
                'ETH': {'free': 1.5, 'locked': 0.0},
                'USDT': {'free': 1000.0, 'locked': 0.0}
            }
        Returns None if there's an error fetching balances
    """
    try:
        # Initialize Binance client
        if not API_KEY or not API_SECRET:
            logger.error("API Key and Secret not found!")
            return None

        client = Client(API_KEY, API_SECRET)
        if BASE_URL:  # Set custom API URL if provided (e.g., for testnet)
            client.API_URL = BASE_URL

        # Get account information
        account_info = client.get_account()

        # Extract relevant assets (trading pairs + USDT)
        relevant_assets = set()
        for symbol in SYMBOLS:
            asset = symbol.replace('USDT', '')  # Remove USDT from pair
            relevant_assets.add(asset)
        relevant_assets.add('USDT')  # Add USDT

        # Build balances dictionary
        balances = {}
        for balance in account_info['balances']:
            if balance['asset'] in relevant_assets:
                balances[balance['asset']] = {
                    'free': float(balance['free']),
                    'locked': float(balance['locked'])
                }

        # Ensure USDT is always present
        if 'USDT' not in balances:
            balances['USDT'] = {'free': 0.0, 'locked': 0.0}

        return balances

    except BinanceAPIException as e:
        logger.error(f"Binance API error: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error getting balances: {e}")
        return None

def main():
    """
    Main function for testing balance retrieval
    """
    # Set up logging for standalone execution
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('get_balance.log')
        ]
    )

    balances = get_all_balances()
    if balances:
        logger.info("Current balances:")
        for asset, balance in balances.items():
            logger.info(f"{asset}: Free={balance['free']:.8f}, Locked={balance['locked']:.8f}")
    else:
        logger.error("Failed to retrieve balances")

if __name__ == "__main__":
    main()
