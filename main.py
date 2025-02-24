#!/usr/bin/env python
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
import requests
import sys
import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from config.settings import (
    API_KEY,
    API_SECRET,
    BASE_URL,
    TELEGRAM_TOKEN,
    TELEGRAM_GROUP_ID,
    SYMBOLS,
    INTERVAL,
    CACHE_LIFETIME,
    MAX_RETRIES,
    RETRY_BACKOFF,
    BUY_MULTIPLIER,
    SELL_MULTIPLIER,
    TOLERANCE
)

# Membuat folder logs jika belum ada
log_directory = 'logs/bot'
if not os.path.exists(log_directory):
    os.makedirs(log_directory)

# Konfigurasi logging untuk menulis ke file di folder logs/bot
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f"{log_directory}/bot.log"),
        logging.StreamHandler()
    ]
)

# Inisialisasi klien Binance
client = Client(api_key=API_KEY, api_secret=API_SECRET)

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
        for filter_info in symbol_info['filters']:
            if filter_info['filterType'] == 'LOT_SIZE':
                step_size = float(filter_info['stepSize'])
                min_qty = float(filter_info['minQty'])
                max_qty = float(filter_info['maxQty'])
                return step_size, min_qty, max_qty
        logging.error(f"Tidak ditemukan stepSize, minQty, atau maxQty untuk simbol {symbol}")
        return None, None, None
    except BinanceAPIException as e:
        logging.error(f"Gagal mendapatkan informasi simbol untuk {symbol}: {e}")
        return None, None, None

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

# Fungsi untuk memuat riwayat transaksi dari database
def load_transactions():
    try:
        cursor.execute('SELECT symbol, type, quantity, price FROM transactions')
        transactions = cursor.fetchall()
        logging.info(f"Riwayat Transaksi: {transactions}")
        return transactions
    except sqlite3.Error as e:
        logging.error(f"Gagal memuat riwayat transaksi dari database: {e}")
        return []

# Fungsi untuk mengirimkan status saldo setiap satu jam
def send_status_update():
    usdt_free, asset_balances = get_balances()
    status_message = f"Status Saldo:\nSaldo USDT: {usdt_free}\nSaldo Aset: {asset_balances}"
    logging.info(status_message)
    send_telegram_message(status_message)

# Fungsi untuk memeriksa apakah ada pending order
def has_pending_orders():
    try:
        open_orders = client.get_open_orders()
        return len(open_orders) > 0
    except BinanceAPIException as e:
        logging.error(f"Gagal mendapatkan open orders: {e}")
        return False

# Fungsi untuk mengirim pesan Telegram
def send_telegram_message(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            'chat_id': TELEGRAM_GROUP_ID,
            'text': message
        }
        response = requests.post(url, data=payload)
        response.raise_for_status()
        logging.info(f"Pesan Telegram terkirim: {message}")
    except requests.exceptions.RequestException as e:
        logging.error(f"Gagal mengirim pesan Telegram: {e}")

# Fungsi untuk menjalankan log status setiap satu jam
def status_update_thread():
    while True:
        send_status_update()
        time.sleep(3600)  # 3600 detik = 1 jam

# Inisialisasi FastAPI
app = FastAPI()

# Model Pydantic untuk permintaan pembelian
class BuyRequest(BaseModel):
    symbol: str
    quantity: float

# Model Pydantic untuk permintaan penjualan
class SellRequest(BaseModel):
    symbol: str
    quantity: float

# API untuk melakukan pembelian
@app.post("/buy/")
def buy(request: BuyRequest):
    symbol = request.symbol
    quantity = request.quantity

    if symbol not in SYMBOLS:
        raise HTTPException(status_code=400, detail=f"Simbol {symbol} tidak didukung")

    if has_pending_orders():
        raise HTTPException(status_code=400, detail="Ada pending order")

    last_price = get_last_price(symbol)
    if last_price is None:
        raise HTTPException(status_code=400, detail=f"Gagal mendapatkan harga terakhir untuk {symbol}")

    step_size, min_qty, max_qty = get_symbol_info(symbol)
    if step_size is None or min_qty is None or max_qty is None:
        raise HTTPException(status_code=400, detail=f"Gagal mendapatkan informasi simbol untuk {symbol}")

    quantity = round_quantity(quantity, step_size)
    quantity = max(quantity, min_qty)
    quantity = min(quantity, max_qty)

    if quantity <= 0:
        raise HTTPException(status_code=400, detail=f"Jumlah aset {symbol} tidak valid")

    usdt_free, _ = get_balances()
    if not can_buy_asset(usdt_free, last_price, quantity):
        raise HTTPException(status_code=400, detail=f"Saldo USDT tidak cukup untuk membeli {symbol}")

    order = buy_asset(symbol, quantity)
    if order is None:
        raise HTTPException(status_code=500, detail=f"Gagal membeli {symbol}")

    return {
        "symbol": symbol,
        "quantity": quantity,
        "price": last_price,
        "status": "success"
    }

# API untuk melakukan penjualan
@app.post("/sell/")
def sell(request: SellRequest):
    symbol = request.symbol
    quantity = request.quantity

    if symbol not in SYMBOLS:
        raise HTTPException(status_code=400, detail=f"Simbol {symbol} tidak didukung")

    if has_pending_orders():
        raise HTTPException(status_code=400, detail="Ada pending order")

    last_price = get_last_price(symbol)
    if last_price is None:
        raise HTTPException(status_code=400, detail=f"Gagal mendapatkan harga terakhir untuk {symbol}")

    step_size, min_qty, max_qty = get_symbol_info(symbol)
    if step_size is None or min_qty is None or max_qty is None:
        raise HTTPException(status_code=400, detail=f"Gagal mendapatkan informasi simbol untuk {symbol}")

    quantity = round_quantity(quantity, step_size)
    quantity = max(quantity, min_qty)
    quantity = min(quantity, max_qty)

    if quantity <= 0:
        raise HTTPException(status_code=400, detail=f"Jumlah aset {symbol} tidak valid")

    order = sell_asset(symbol, quantity)
    if order is None:
        raise HTTPException(status_code=500, detail=f"Gagal menjual {symbol}")

    return {
        "symbol": symbol,
        "quantity": quantity,
        "price": last_price,
        "status": "success"
    }

# API untuk melakukan pengecekan saldo
@app.get("/balance/")
def get_balance():
    usdt_free, asset_balances = get_balances()
    return {
        "usdt_free": usdt_free,
        "asset_balances": asset_balances
    }

# Fungsi untuk menjalankan log status setiap satu jam
def status_update_thread():
    while True:
        send_status_update()
        time.sleep(3600)  # 3600 detik = 1 jam

# Menjalankan thread untuk log status setiap satu jam
status_thread = threading.Thread(target=status_update_thread, daemon=True)
status_thread.start()

# Menjalankan aplikasi FastAPI
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
