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

# Konfigurasi logging
log_directory = 'logs/bot'
if not os.path.exists(log_directory):
    os.makedirs(log_directory)

log_file = os.path.join(log_directory, 'bot.log')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=5),
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
        send_telegram_message(f"Beli {quantity} {symbol} pada harga {order['fills'][0]['price']}", TELEGRAM_TOKEN, TELEGRAM_GROUP_ID)
        save_transaction(symbol, 'buy', quantity, float(order['fills'][0]['price']))
        return order
    except (BinanceAPIException, BinanceOrderException) as e:
        logging.error(f"Gagal membeli {symbol}: {e}")
        send_telegram_message(f"Gagal membeli {symbol}: {e}", TELEGRAM_TOKEN, TELEGRAM_GROUP_ID)
        raise HTTPException(status_code=500, detail=str(e))

# Fungsi untuk menjual aset
def sell_asset(symbol, quantity):
    try:
        order = client.order_market_sell(
            symbol=symbol,
            quantity=quantity
        )
        logging.info(f"Jual {quantity} {symbol} pada harga {order['fills'][0]['price']}")
        send_telegram_message(f"Jual {quantity} {symbol} pada harga {order['fills'][0]['price']}", TELEGRAM_TOKEN, TELEGRAM_GROUP_ID)
        save_transaction(symbol, 'sell', quantity, float(order['fills'][0]['price']))
        return order
    except (BinanceAPIException, BinanceOrderException) as e:
        logging.error(f"Gagal menjual {symbol}: {e}")
        send_telegram_message(f"Gagal menjual {symbol}: {e}", TELEGRAM_TOKEN, TELEGRAM_GROUP_ID)
        raise HTTPException(status_code=500, detail=str(e))

# Fungsi untuk mendapatkan harga terakhir
def get_last_price(symbol):
    try:
        ticker = client.get_symbol_ticker(symbol=symbol)
        return float(ticker['price'])
    except BinanceAPIException as e:
        logging.error(f"Gagal mendapatkan harga terakhir untuk {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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
        raise HTTPException(status_code=500, detail=str(e))

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
            elif filter_info['filterType'] == 'MIN_NOTIONAL':
                min_notional = float(filter_info['minNotional'])
                return step_size, min_qty, max_qty, min_notional
        logging.error(f"Tidak ditemukan stepSize, minQty, atau maxQty untuk simbol {symbol}")
        raise HTTPException(status_code=500, detail="Tidak ditemukan informasi filter untuk simbol")
    except BinanceAPIException as e:
        logging.error(f"Gagal mendapatkan informasi simbol untuk {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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
        raise HTTPException(status_code=500, detail=str(e))

# Fungsi untuk memeriksa apakah ada transaksi pending
def has_pending_orders():
    try:
        open_orders = client.get_open_orders()
        return len(open_orders) > 0
    except BinanceAPIException as e:
        logging.error(f"Gagal mendapatkan pesanan terbuka: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Fungsi untuk mengirimkan status saldo setiap satu jam
def send_status_every_hour():
    while True:
        usdt_free, asset_balances = get_balances()
        status_message = f"Status saldo setiap jam: Saldo USDT: {usdt_free}, Saldo Aset: {asset_balances}"
        logging.info(status_message)
        send_telegram_message(status_message, TELEGRAM_TOKEN, TELEGRAM_GROUP_ID)
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
        raise HTTPException(status_code=500, detail=str(e))

# Fungsi untuk mendapatkan riwayat transaksi
def get_transaction_history(symbol):
    try:
        cursor.execute('''
            SELECT * FROM transactions
            WHERE symbol = ?
            ORDER BY timestamp DESC
            LIMIT 1
        ''', (symbol,))
        result = cursor.fetchone()
        return result
    except sqlite3.Error as e:
        logging.error(f"Gagal mendapatkan riwayat transaksi: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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

    if has_pending_orders():
        logging.info("Ada pesanan terbuka, menunggu 5 menit sebelum melanjutkan.")
        raise HTTPException(status_code=400, detail="Ada pesanan terbuka, coba lagi nanti.")

    last_price = get_last_price(symbol)
    if last_price is None:
        raise HTTPException(status_code=500, detail=f"Gagal mendapatkan harga terakhir untuk {symbol}")

    usdt_free, asset_balances = get_balances()
    if usdt_free < last_price * quantity:
        raise HTTPException(status_code=400, detail=f"Saldo USDT tidak cukup untuk membeli {quantity} {symbol}")

    step_size, min_qty, max_qty, min_notional = get_symbol_info(symbol)

    if step_size is not None and min_qty is not None and max_qty is not None and min_notional is not None:
        quantity = round_quantity(quantity, step_size)
        quantity = max(quantity, min_qty)
        quantity = min(quantity, max_qty)

        if quantity * last_price < min_notional:
            raise HTTPException(status_code=400, detail=f"Minimal notional tidak terpenuhi untuk {symbol} dengan jumlah {quantity} pada harga {last_price}")

        if quantity > 0 and can_buy_asset(usdt_free, last_price, quantity):
            buy_asset(symbol, quantity)
            return {"message": f"Beli {quantity} {symbol} berhasil"}

    raise HTTPException(status_code=400, detail=f"Gagal membeli {symbol}")

# API untuk melakukan penjualan
@app.post("/sell/")
def sell(request: SellRequest):
    symbol = request.symbol
    quantity = request.quantity

    if has_pending_orders():
        logging.info("Ada pesanan terbuka, menunggu 5 menit sebelum melanjutkan.")
        raise HTTPException(status_code=400, detail="Ada pesanan terbuka, coba lagi nanti.")

    usdt_free, asset_balances = get_balances()
    asset = symbol.replace('USDT', '')
    asset_balance = asset_balances.get(asset, 0.0)

    if asset_balance < quantity:
        raise HTTPException(status_code=400, detail=f"Saldo {asset} tidak cukup untuk menjual {quantity} {symbol}")

    step_size, min_qty, max_qty, min_notional = get_symbol_info(symbol)

    if step_size is not None and min_qty is not None and max_qty is not None and min_notional is not None:
        quantity = round_quantity(quantity, step_size)
        quantity = max(quantity, min_qty)
        quantity = min(quantity, max_qty)

        if quantity * get_last_price(symbol) < min_notional:
            raise HTTPException(status_code=400, detail=f"Minimal notional tidak terpenuhi untuk {symbol} dengan jumlah {quantity} pada harga {get_last_price(symbol)}")

        if quantity > 0:
            sell_asset(symbol, quantity)
            return {"message": f"Jual {quantity} {symbol} berhasil"}

    raise HTTPException(status_code=400, detail=f"Gagal menjual {symbol}")

# API untuk melakukan pengecekan saldo
@app.get("/check_balance/")
def check_balance():
    usdt_free, asset_balances = get_balances()
    return {
        "saldo_usdt": usdt_free,
        "saldo_aset": asset_balances
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
