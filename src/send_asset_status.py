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
from src.send_telegram_message import send_telegram_message
from src.get_balances import get_balances
from src.get_last_price import get_last_price
from src.get_last_buy_price import get_last_buy_price

SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']

def send_asset_status():
    """Send current asset status to Telegram."""
    try:
        balances = get_balances()
        usdt_free = balances.get('USDT', {}).get('free', 0.0)

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        status_message = f"🔄 Status Aset ({current_time})\n\n"
        status_message += f"💵 USDT: {usdt_free:.2f}\n\n"

        total_value_usdt = usdt_free

        for symbol in SYMBOLS:
            asset = symbol.replace('USDT', '')
            balance = balances.get(asset, {}).get('free', 0.0)
            last_price = get_last_price(symbol)

            if last_price:
                value_usdt = balance * last_price
                total_value_usdt += value_usdt

                last_buy_price = get_last_buy_price(symbol)
                profit_loss = ""
                if last_buy_price and balance > 0:
                    pl_percent = ((last_price - last_buy_price) / last_buy_price) * 100
                    profit_loss = f"(P/L: {pl_percent:.2f}%)"

                status_message += f"🪙 {asset}:\n"
                status_message += f"   Jumlah: {balance:.8f}\n"
                status_message += f"   Harga: {last_price:.2f} USDT\n"
                status_message += f"   Nilai: {value_usdt:.2f} USDT {profit_loss}\n\n"

        status_message += f"💰 Total Nilai Portfolio: {total_value_usdt:.2f} USDT"

        send_telegram_message(status_message)
        logging.info("Status aset berhasil dikirim ke Telegram")

    except Exception as e:
        logging.error(f"Gagal mengirim status aset: {e}")