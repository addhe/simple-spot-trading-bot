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

log_filename = os.path.join(log_directory, 'bot.log')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        RotatingFileHandler(log_filename, maxBytes=5*1024*1024, backupCount=5),
        logging.StreamHandler()
    ]
)

# Mengambil variabel lingkungan
API_KEY = os.environ['API_KEY_SPOT_TESTNET_BINANCE']
API_SECRET = os.environ['API_SECRET_SPOT_TESTNET_BINANCE']
BASE_URL = 'https://api.binance.com/api'  # Menggunakan BASE_URL production
TELEGRAM_TOKEN = os.environ['TELEGRAM_TOKEN']
TELEGRAM_GROUP_ID = os.environ['TELEGRAM_GROUP_ID']
SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
INTERVAL = '1m'
CACHE_LIFETIME = 300  # 5 menit
MAX_RETRIES = 5
RETRY_BACKOFF = 1  # 1 detik
BUY_MULTIPLIER = 0.925
SELL_MULTIPLIER = 1.03
TOLERANCE = 0.01

# Inisialisasi klien Binance
client = Client(api_key=API_KEY, api_secret=API_SECRET, testnet=False)  # Menggunakan testnet=False untuk production

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

# Fungsi untuk memuat riwayat transaksi dari database
def load_transactions():
    try:
        cursor.execute('SELECT symbol, type, quantity, price FROM transactions')
        transactions = cursor.fetchall()
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
            "chat_id": TELEGRAM_GROUP_ID,
            "text": message
        }
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            logging.info(f"Pesan Telegram terkirim: {message}")
        else:
            logging.error(f"Gagal mengirim pesan Telegram: {response.text}")
    except Exception as e:
        logging.error(f"Gagal mengirim pesan Telegram: {e}")

# Fungsi untuk memeriksa apakah jumlah aset memenuhi minimal notional
def check_min_notional(symbol, quantity, price, min_notional):
    notional = quantity * price
    if notional < min_notional:
        logging.error(f"Minimal notional tidak terpenuhi untuk {symbol} dengan jumlah {quantity} pada harga {price}")
        send_telegram_message(f"Minimal notional tidak terpenuhi untuk {symbol} dengan jumlah {quantity} pada harga {price}")
        return False
    return True

# Fungsi utama
def main():
    status_thread = threading.Thread(target=send_status_every_hour)
    status_thread.daemon = True
    status_thread.start()

    while True:
        if has_pending_orders():
            logging.info("Ada pesanan terbuka, menunggu 5 menit sebelum melanjutkan.")
            time.sleep(300)  # 5 menit
            continue

        usdt_free, asset_balances = get_balances()
        logging.info(f"Saldo USDT: {usdt_free}, Saldo Aset: {asset_balances}")
        send_telegram_message(f"Saldo USDT: {usdt_free}, Saldo Aset: {asset_balances}")

        # Bagi saldo USDT merata antara semua simbol trading
        usdt_per_symbol = usdt_free / len(SYMBOLS)

        for symbol in SYMBOLS:
            last_price = get_last_price(symbol)
            if last_price is None:
                continue

            asset = symbol.replace('USDT', '')
            asset_balance = asset_balances.get(asset, 0.0)

            if asset_balance == 0.0:
                # Membeli aset jika tidak memiliki aset tersebut
                quantity = usdt_per_symbol * BUY_MULTIPLIER / last_price
                step_size, min_qty, max_qty, min_notional = get_symbol_info(symbol)

                if step_size is not None and min_qty is not None and max_qty is not None and min_notional is not None:
                    quantity = round_quantity(quantity, step_size)
                    quantity = max(quantity, min_qty)
                    quantity = min(quantity, max_qty)

                    if quantity > 0 and can_buy_asset(usdt_free, last_price, quantity):
                        if check_min_notional(symbol, quantity, last_price, min_notional):
                            buy_order = buy_asset(symbol, quantity)
                            if buy_order:
                                time.sleep(300)  # 5 menit
            else:
                # Menjual aset jika harga naik 3%
                last_buy_price = get_last_buy_price(symbol)
                if last_buy_price is not None:
                    sell_price = last_price * SELL_MULTIPLIER
                    if sell_price >= last_buy_price * (1 + TOLERANCE):
                        if check_min_notional(symbol, asset_balance, sell_price, min_notional):
                            sell_order = sell_asset(symbol, asset_balance)
                            if sell_order:
                                time.sleep(300)  # 5 menit

        time.sleep(CACHE_LIFETIME)

def send_status_every_hour():
    while True:
        send_status_update()
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

# Model Pydantic untuk request body
class BuyRequest(BaseModel):
    symbol: str
    quantity: float

class SellRequest(BaseModel):
    symbol: str
    quantity: float

# Endpoint untuk melakukan pembelian
@app.post("/buy/")
def buy(request: BuyRequest):
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

    if quantity <= 0:
        raise HTTPException(status_code=400, detail=f"Jumlah aset tidak valid untuk {symbol}")

    if not can_buy_asset(get_balances()[0], last_price, quantity):
        raise HTTPException(status_code=400, detail=f"Saldo USDT tidak cukup untuk membeli {symbol}")

    if not check_min_notional(symbol, quantity, last_price, min_notional):
        raise HTTPException(status_code=400, detail=f"Minimal notional tidak terpenuhi untuk {symbol} dengan jumlah {quantity} pada harga {last_price}")

    buy_order = buy_asset(symbol, quantity)
    if buy_order:
        return {"message": f"Beli {quantity} {symbol} pada harga {buy_order['fills'][0]['price']}"}
    else:
        raise HTTPException(status_code=500, detail=f"Gagal membeli {symbol}")

# Endpoint untuk melakukan penjualan
@app.post("/sell/")
def sell(request: SellRequest):
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

    if quantity <= 0:
        raise HTTPException(status_code=400, detail=f"Jumlah aset tidak valid untuk {symbol}")

    if not check_min_notional(symbol, quantity, last_price, min_notional):
        raise HTTPException(status_code=400, detail=f"Minimal notional tidak terpenuhi untuk {symbol} dengan jumlah {quantity} pada harga {last_price}")

    sell_order = sell_asset(symbol, quantity)
    if sell_order:
        return {"message": f"Jual {quantity} {symbol} pada harga {sell_order['fills'][0]['price']}"}
    else:
        raise HTTPException(status_code=500, detail=f"Gagal menjual {symbol}")

# Endpoint untuk melakukan pengecekan saldo
@app.get("/balance/")
def get_balance():
    usdt_free, asset_balances = get_balances()
    return {
        "usdt_free": usdt_free,
        "asset_balances": asset_balances
    }

# Menjalankan aplikasi FastAPI
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
