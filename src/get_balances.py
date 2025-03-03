import os
import time
from datetime import datetime
from binance.exceptions import BinanceAPIException
from src.logger import logger
from src.binance_client import get_binance_client

def get_balances():
    """
    Get account balances from Binance
    Returns: dict with 'USDT' and other asset balances
    """
    try:
        client = get_binance_client()
        account = client.get_account()
        balances = {}

        for balance in account['balances']:
            asset = balance['asset']
            free = float(balance['free'])
            locked = float(balance['locked'])

            if free > 0 or locked > 0:  # Only store assets with balance
                balances[asset] = {
                    'free': free,
                    'locked': locked,
                    'total': free + locked
                }
        return balances
    except BinanceAPIException as e:
        logger.error(f"Failed to get balances: {e}")
        return {}
