import os
import time
import sqlite3
import threading
import math
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceOrderException

from config.settings import API_KEY, API_SECRET, BASE_URL
from src.logger import logger

# Inisialisasi klien Binance
client = Client(api_key=API_KEY, api_secret=API_SECRET)
if BASE_URL:
    client.API_URL = BASE_URL

def get_balances():
    """
    Get account balances from Binance
    Returns: dict with 'USDT' and other asset balances
    """
    try:
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

        # Debug logging to capture balances retrieved
        logger.info(f"Retrieved balances: {balances}")

        # Debug logging to capture retrieved balances from Binance before returning them
        logger.debug(f"Returning balances from Binance: {balances}")

        return balances
    except BinanceAPIException as e:
        logger.error(f"Failed to get balances: {e}")
        return {}
