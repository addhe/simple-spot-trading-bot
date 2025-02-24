#!/usr/bin/env python
import os
import time
import sqlite3
import threading
import math
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceOrderException
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests
import sys
import logging

# Konfigurasi logging
log_directory = 'logs/bot'
if not os.path.exists(log_directory):
    os.makedirs(log_directory)

log_file = os.path.join(log_directory, 'bot.log')
handler = RotatingFileHandler(log_file, maxBytes=1000000, backupCount=5)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[handler]
)

import config.settings as settings

# Mengambil variabel lingkungan
API_KEY = settings.API_KEY
API_SECRET = settings.API_SECRET
BASE_URL = settings.BASE_URL
TELEGRAM_TOKEN = settings.TELEGRAM_TOKEN
TELEGRAM_GROUP_ID = settings.TELEGRAM_GROUP_ID
SYMBOLS = settings.SYMBOLS
CACHE_LIFETIME = settings.CACHE_LIFETIME
BUY_MULTIPLIER = settings.BUY_MULTIPLIER
SELL_MULTIPLIER = settings.SELL_MULTIPLIER
TOLERANCE = settings.TOLERANCE

# Inisialisasi klien Binance
client = Client(api_key=API_KEY, api_secret=API_SECRET)
client.API_URL = BASE_URL

# Inisialisasi koneksi database SQLite
DB_NAME = 'table_transactions.db'
conn = sqlite3.connect(DB_NAME, check_same_thread=False)
cursor = conn.cursor()

# Membuat tabel transactions jika belum ada
cursor.execute('''
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT,
    symbol TEXT,
    type TEXT,
    quantity REAL,
    price REAL
)
''')
conn.commit()

# Model Pydantic untuk request body
class BuyRequest(BaseModel):
    symbol: str
    quantity: float

class SellRequest(BaseModel):
    symbol: str
    quantity: float

# Fungsi untuk mengirim pesan Telegram
def send_telegram_message(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_GROUP_ID,
            "text": message
        }
        response = requests.post(url, json=payload)
        response.raise_for_status()
        logging.info(f"Pesan Telegram terkirim: {message}")
    except Exception as e:
        logging.error(f"Gagal mengirim pesan Telegram: {e}")

# Fungsi untuk mendapatkan harga terakhir
def get_last_price(symbol):
    try:
        ticker = client.get_symbol_ticker(symbol=symbol)
        return float(ticker['price'])
    except BinanceAPIException as e:
        logging.error(f"Gagal mendapatkan harga terakhir untuk {symbol}: {e}")
        return None

# Fungsi untuk mendapatkan saldo
def get_balances():
    try:
        balances = client.get_account()['balances']
        usdt_balance = next((item for item in balances if item['asset'] == 'USDT'), None)
        usdt_free = float(usdt_balance['free']) if usdt_balance else 0.0
        asset_balances = {item['asset']: float(item['free']) for item in balances if item['asset'] in ['BTC', 'ETH', 'SOL']}
        return usdt_free, asset_balances
    except BinanceAPIException as e:
        logging.error(f"Gagal mendapatkan saldo: {e}")
        return 0.0, {}

# Fungsi untuk mendapatkan informasi simbol
def get_symbol_info(symbol):
    try:
        symbol_info = client.get_symbol_info(symbol)
        step_size = min_qty = max_qty = min_notional = None  # Initialize all
        for filter_info in symbol_info['filters']:
            if filter_info['filterType'] == 'LOT_SIZE':
                step_size = float(filter_info['stepSize'])
                min_qty = float(filter_info['minQty'])
                max_qty = float(filter_info['maxQty'])
            elif filter_info['filterType'] == 'MIN_NOTIONAL':
                min_notional = float(filter_info['minNotional'])
        return step_size, min_qty, max_qty, min_notional
    except BinanceAPIException as e:
        logging.error(f"Gagal mendapatkan informasi simbol untuk {symbol}: {e}")
        return None, None, None, None

# Fungsi untuk membulatkan jumlah aset sesuai dengan presisi yang diizinkan
def round_quantity(quantity, step_size):
    return round(quantity / step_size) * step_size

# Fungsi untuk memeriksa apakah saldo cukup untuk membeli aset
def can_buy_asset(usdt_free, last_price, quantity):
    return usdt_free >= last_price * quantity

# Fungsi untuk menyimpan transaksi ke database
def save_transaction(symbol, type, quantity, price):
    try:
        cursor.execute('''
            INSERT INTO transactions (timestamp, symbol, type, quantity, price)
            VALUES (?, ?, ?, ?, ?)
        ''', (time.strftime('%Y-%m-%d %H:%M:%S'), symbol, type, quantity, price))
        conn.commit()
        logging.info(f"Transaksi {type} {quantity} {symbol} pada harga {price} disimpan ke database")
    except sqlite3.Error as e:
        logging.error(f"Gagal menyimpan transaksi ke database: {e}")

# Fungsi untuk membeli aset
def buy_asset(symbol, quantity):
    try:
        order = client.order_market_buy(
            symbol=symbol,
            quantity=quantity
        )
        logging.info(f"Beli {quantity} {symbol} pada harga {order['fills'][0]['price']}")
        send_telegram_message(f"Beli {quantity} {symbol} pada harga {order['fills'][0]['price']}")
        save_transaction(symbol, 'buy', quantity, float(order['fills'][0]['price']))
        return order
    except (BinanceAPIException, BinanceOrderException) as e:
        logging.error(f"Gagal membeli {symbol}: {e}")
        send_telegram_message(f"Gagal membeli {symbol}: {e}")
        return None

# Fungsi untuk menjual aset
def sell_asset(symbol, quantity):
    try:
        order = client.order_market_sell(
            symbol=symbol,
            quantity=quantity
        )
        logging.info(f"Jual {quantity} {symbol} pada harga {order['fills'][0]['price']}")
        send_telegram_message(f"Jual {quantity} {symbol} pada harga {order['fills'][0]['price']}")
        save_transaction(symbol, 'sell', quantity, float(order['fills'][0]['price']))
        return order
    except (BinanceAPIException, BinanceOrderException) as e:
        logging.error(f"Gagal menjual {symbol}: {e}")
        send_telegram_message(f"Gagal menjual {symbol}: {e}")
        return None

# Fungsi untuk memeriksa apakah ada transaksi pending
def has_pending_orders():
    try:
        open_orders = client.get_open_orders()
        return len(open_orders) > 0
    except BinanceAPIException as e:
        logging.error(f"Gagal mendapatkan pesanan terbuka: {e}")
        return True

# Fungsi untuk mengirimkan status saldo setiap satu jam
def send_status_every_hour():
    while True:
        usdt_free, asset_balances = get_balances()
        status_message = f"Status Saldo:\nSaldo USDT: {usdt_free}\nSaldo Aset: {asset_balances}"
        logging.info(status_message)
        send_telegram_message(status_message)
        time.sleep(3600)  # 1 jam

# Fungsi untuk mendapatkan harga pembelian terakhir
def get_last_buy_price(symbol):
    try:
        cursor.execute('''
            SELECT price FROM transactions
            WHERE symbol = ? AND type = 'buy'
            ORDER BY timestamp DESC
            LIMIT 1
        ''', (symbol,))
        result = cursor.fetchone()
        return result[0] if result else None
    except sqlite3.Error as e:
        logging.error(f"Gagal mendapatkan harga pembelian terakhir: {e}")
        return None

# Inisialisasi FastAPI
app = FastAPI()

# Endpoint untuk membeli aset
@app.post("/buy/")
def buy_asset_endpoint(request: BuyRequest):
    symbol = request.symbol
    quantity = request.quantity

    last_price = get_last_price(symbol)
    if last_price is None:
        raise HTTPException(status_code=400, detail=f"Gagal mendapatkan harga terakhir untuk {symbol}")

    step_size, min_qty, max_qty, min_notional = get_symbol_info(symbol)
    if step_size is None or min_qty is None or max_qty is None or min_notional is None:
        raise HTTPException(status_code=400, detail=f"Gagal mendapatkan informasi simbol untuk {symbol}")

    quantity = round_quantity(quantity, step_size)
    quantity = max(quantity, min_qty)
    quantity = min(quantity, max_qty)

    notional = quantity * last_price
    if notional < min_notional:
        raise HTTPException(status_code=400, detail=f"Minimal notional tidak terpenuhi untuk {symbol} dengan jumlah {quantity} pada harga {last_price}")

    if has_pending_orders():
        raise HTTPException(status_code=400, detail="Ada pesanan terbuka, tidak dapat melakukan transaksi baru.")

    usdt_free, asset_balances = get_balances()
    if not can_buy_asset(usdt_free, last_price, quantity):
        raise HTTPException(status_code=400, detail=f"Saldo USDT tidak cukup untuk membeli {symbol}")

    buy_order = buy_asset(symbol, quantity)
    if buy_order is None:
        raise HTTPException(status_code=500, detail=f"Gagal membeli {symbol}")

    return {
        "symbol": symbol,
        "quantity": quantity,
        "price": last_price,
        "status": "success",
        "message": f"Beli {quantity} {symbol} pada harga {last_price}"
    }

# Endpoint untuk menjual aset
@app.post("/sell/")
def sell_asset_endpoint(request: SellRequest):
    symbol = request.symbol
    quantity = request.quantity

    step_size, min_qty, max_qty, min_notional = get_symbol_info(symbol)
    if step_size is None or min_qty is None or max_qty is None or min_notional is None:
        raise HTTPException(status_code=400, detail=f"Gagal mendapatkan informasi simbol untuk {symbol}")

    quantity = round_quantity(quantity, step_size)
    quantity = max(quantity, min_qty)
    quantity = min(quantity, max_qty)

    if has_pending_orders():
        raise HTTPException(status_code=400, detail="Ada pesanan terbuka, tidak dapat melakukan transaksi baru.")

    sell_order = sell_asset(symbol, quantity)
    if sell_order is None:
        raise HTTPException(status_code=500, detail=f"Gagal menjual {symbol}")

    return {
        "symbol": symbol,
        "quantity": quantity,
        "status": "success",
        "message": f"Jual {quantity} {symbol}"
    }

# Endpoint untuk melakukan pengecekan saldo
@app.get("/check_balance/")
def check_balance():
    usdt_free, asset_balances = get_balances()
    return {
        "usdt_free": usdt_free,
        "asset_balances": asset_balances
    }

# Fungsi utama
def main():
    status_thread = threading.Thread(target=send_status_every_hour)
    status_thread.daemon = True
    status_thread.start()

    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

if __name__ == "__main__":
    main()
