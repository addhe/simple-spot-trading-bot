import os
import logging
import sqlite3
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceOrderException
from config.settings import (
    API_KEY,
    API_SECRET,
    BASE_URL,
    TELEGRAM_TOKEN,
    TELEGRAM_GROUP_ID
)

# Konfigurasi logging
log_directory = 'logs/bot'
if not os.path.exists(log_directory):
    os.makedirs(log_directory)

log_file = os.path.join(log_directory, 'order_sell_all.log')
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
            elif filter_info['filterType'] == 'MIN_NOTIONAL':
                min_notional = float(filter_info['minNotional'])
                return step_size, min_qty, max_qty, min_notional
        logging.error(f"Tidak ditemukan stepSize, minQty, atau maxQty untuk simbol {symbol}")
        return None, None, None, None
    except BinanceAPIException as e:
        logging.error(f"Gagal mendapatkan informasi simbol untuk {symbol}: {e}")
        return None, None, None, None

# Fungsi untuk membulatkan jumlah aset sesuai dengan presisi yang diizinkan
def round_quantity(quantity, step_size):
    return round(quantity / step_size) * step_size

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

# Fungsi untuk mengirimkan pesan Telegram
def send_telegram_message(message, token, chat_id):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': message
    }
    response = requests.post(url, data=payload)
    return response.json()

# Fungsi utama
def main():
    usdt_free, asset_balances = get_balances()
    logging.info(f"Saldo USDT: {usdt_free}, Saldo Aset: {asset_balances}")

    for symbol in asset_balances:
        if symbol == 'USDT':
            continue

        asset_balance = asset_balances[symbol]
        if asset_balance == 0.0:
            logging.info(f"Tidak ada saldo untuk menjual {symbol}")
            continue

        symbol_full = f"{symbol}USDT"
        step_size, min_qty, max_qty, min_notional = get_symbol_info(symbol_full)

        if step_size is not None and min_qty is not None and max_qty is not None and min_notional is not None:
            quantity = round_quantity(asset_balance, step_size)
            quantity = max(quantity, min_qty)
            quantity = min(quantity, max_qty)

            if quantity * get_last_price(symbol_full) < min_notional:
                logging.info(f"Minimal notional tidak terpenuhi untuk {symbol_full} dengan jumlah {quantity} pada harga {get_last_price(symbol_full)}")
                continue

            if quantity > 0:
                sell_asset(symbol_full, quantity)
                time.sleep(5)  # Jeda 5 detik sebelum menjual aset berikutnya

if __name__ == "__main__":
    main()
