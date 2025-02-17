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

def get_balances(client):
    """Get current balances from Binance"""
    try:
        # Get account information
        account_info = client.get_account()
        
        # Filter and format balances
        balances = {}
        for asset in account_info['balances']:
            free = float(asset['free'])
            locked = float(asset['locked'])
            total = free + locked
            
            # Only include assets with non-zero balance
            if total > 0:
                balances[asset['asset']] = {
                    'free': free,
                    'locked': locked,
                    'total': total
                }
        
        return balances
    except Exception as e:
        logger.error(f"Error getting balances: {e}")
        return None
