import os
import time
import logging
import sqlite3
import threading
import math
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceOrderException

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
        return balances
    except BinanceAPIException as e:
        logging.error(f"Failed to get balances: {e}")
        return {}