#!/usr/bin/env python
import os
import time
import sqlite3
import threading
import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler
from binance.client import Client
from binance.exceptions import BinanceAPIException
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests

# Configure logging
log_directory = 'logs/bot'
os.makedirs(log_directory, exist_ok=True)

log_file = os.path.join(log_directory, 'bot.log')
handler = RotatingFileHandler(log_file, maxBytes=1000000, backupCount=5)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[handler])

# Import settings
import config.settings as settings

# Environment variables
API_KEY = settings.API_KEY
API_SECRET = settings.API_SECRET
BASE_URL = settings.BASE_URL
TELEGRAM_TOKEN = settings.TELEGRAM_TOKEN
TELEGRAM_GROUP_ID = settings.TELEGRAM_GROUP_ID

# Binance client initialization
client = Client(api_key=API_KEY, api_secret=API_SECRET)
client.API_URL = BASE_URL

# Database setup
DB_NAME = 'table_transactions.db'
conn = sqlite3.connect(DB_NAME, check_same_thread=False)
cursor = conn.cursor()

# Create transactions table if not exists
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

# Pydantic models
class BuyRequest(BaseModel):
    symbol: str
    quantity: float

# Function to get symbol information
def get_symbol_info(symbol):
    try:
        logging.info(f"Fetching symbol info for: {symbol}")
        symbol_info = client.get_symbol_info(symbol)
        
        if not symbol_info:
            logging.error(f"No information found for symbol: {symbol}")
            return None, None, None, None
        
        logging.debug(f"Symbol info: {symbol_info}")

        step_size = min_qty = max_qty = min_notional = None
        for filter_info in symbol_info['filters']:
            if filter_info['filterType'] == 'LOT_SIZE':
                step_size = float(filter_info['stepSize'])
                min_qty = float(filter_info['minQty'])
                max_qty = float(filter_info['maxQty'])
            elif filter_info['filterType'] == 'MIN_NOTIONAL':
                min_notional = float(filter_info['minNotional'])

        return step_size, min_qty, max_qty, min_notional
    
    except BinanceAPIException as e:
        logging.error(f"Binance API error: {e}")
        return None, None, None, None
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        return None, None, None, None

# Function to fetch last price
def get_last_price(symbol):
    try:
        ticker = client.get_symbol_ticker(symbol=symbol)
        return float(ticker['price'])
    except BinanceAPIException as e:
        logging.error(f"Failed to get last price for {symbol}: {e}")
        return None

# Function to fetch balances
def get_balances():
    try:
        balances = client.get_account()['balances']
        usdt_balance = next((item for item in balances if item['asset'] == 'USDT'), None)
        usdt_free = float(usdt_balance['free']) if usdt_balance else 0.0
        asset_balances = {item['asset']: float(item['free']) for item in balances if item['asset'] in ['BTC', 'ETH', 'SOL']}
        return usdt_free, asset_balances
    except BinanceAPIException as e:
        logging.error(f"Failed to get balances: {e}")
        return 0.0, {}

# Function to round asset quantity according to precision
def round_quantity(quantity, step_size):
    return round(quantity / step_size) * step_size

# Function to send Telegram message
def send_telegram_message(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_GROUP_ID,
            "text": message
        }
        response = requests.post(url, json=payload)
        response.raise_for_status()
        logging.info(f"Telegram message sent: {message}")
    except Exception as e:
        logging.error(f"Failed to send Telegram message: {e}")

# Buying asset function
def buy_asset(symbol, quantity):
    try:
        order = client.order_market_buy(symbol=symbol, quantity=quantity)
        price = float(order['fills'][0]['price'])
        logging.info(f"Buy {quantity} {symbol} at price {price}")
        send_telegram_message(f"Bought {quantity} {symbol} at {price}")
        save_transaction(symbol, 'buy', quantity, price)
        return order
    except BinanceAPIException as e:
        logging.error(f"Failed to buy {symbol}: {e}")
        send_telegram_message(f"Failed to buy {symbol}: {e}")
        return None

# Function to save transaction to database
def save_transaction(symbol, type, quantity, price):
    try:
        cursor.execute('''
            INSERT INTO transactions (timestamp, symbol, type, quantity, price)
            VALUES (?, ?, ?, ?, ?)
        ''', (time.strftime('%Y-%m-%d %H:%M:%S'), symbol, type, quantity, price))
        conn.commit()
        logging.info(f"Transaction {type} for {quantity} {symbol} at {price} saved")
    except sqlite3.Error as e:
        logging.error(f"Failed to save transaction: {e}")

# FastAPI initialization
app = FastAPI()

# Endpoint to buy asset
@app.post("/buy/")
def buy_asset_endpoint(request: BuyRequest):
    symbol = request.symbol
    quantity = request.quantity

    last_price = get_last_price(symbol)
    if last_price is None:
        raise HTTPException(status_code=400, detail=f"Failed to get last price for {symbol}")

    step_size, min_qty, max_qty, min_notional = get_symbol_info(symbol)
    if None in (step_size, min_qty, max_qty, min_notional):
        raise HTTPException(status_code=400, detail=f"Failed to get symbol info for {symbol}")

    quantity = round_quantity(quantity, step_size)
    quantity = max(quantity, min_qty)
    quantity = min(quantity, max_qty)

    notional = quantity * last_price
    if notional < min_notional:
        raise HTTPException(status_code=400, detail=f"Minimum notional not met for {symbol} with quantity {quantity} at price {last_price}")

    usdt_free, _ = get_balances()
    if usdt_free < notional:
        raise HTTPException(status_code=400, detail=f"Not enough USDT balance to buy {symbol}")

    buy_order = buy_asset(symbol, quantity)
    if buy_order is None:
        raise HTTPException(status_code=500, detail=f"Failed to buy {symbol}")

    return {
        "symbol": symbol,
        "quantity": quantity,
        "price": last_price,
        "status": "success",
        "message": f"Bought {quantity} {symbol} at {last_price}"
    }

# Endpoint to check balance
@app.get("/check_balance/")
def check_balance():
    usdt_free, asset_balances = get_balances()
    return {
        "usdt_free": usdt_free,
        "asset_balances": asset_balances
    }

# Main function to run the server
def main():
    status_thread = threading.Thread(target=send_status_every_hour)
    status_thread.daemon = True
    status_thread.start()

    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

# Send status every hour
def send_status_every_hour():
    while True:
        usdt_free, asset_balances = get_balances()
        status_message = f"Status Saldo:\nSaldo USDT: {usdt_free}\nSaldo Aset: {asset_balances}"
        logging.info(status_message)
        send_telegram_message(status_message)
        time.sleep(3600)

if __name__ == "__main__":
    main()