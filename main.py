import os
import time
import logging
import sqlite3
import threading
import math
from datetime import datetime
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceOrderException
from src.send_telegram_message import send_telegram_message

# Membuat folder logs jika belum ada
log_directory = 'logs/bot'
if not os.path.exists(log_directory):
    os.makedirs(log_directory)

# Konfigurasi logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
                    filename=os.path.join(log_directory, 'bot.log'), filemode='a')

# Mengambil variabel lingkungan
API_KEY = os.getenv('API_KEY_SPOT_TESTNET_BINANCE', '')
API_SECRET = os.getenv('API_SECRET_SPOT_TESTNET_BINANCE', '')
BASE_URL = 'https://testnet.binance.vision/api'
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', '')
TELEGRAM_GROUP_ID = os.getenv('TELEGRAM_GROUP_ID', '')

if not API_KEY or not API_SECRET:
    logging.error("API Key dan Secret tidak ditemukan! Pastikan telah diatur di environment variables.")
    exit(1)

# Konfigurasi trading
SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
INTERVAL = '1m'
CACHE_LIFETIME = 300  # 5 menit
BUY_MULTIPLIER = 0.925
SELL_MULTIPLIER = 1.03
TOLERANCE = 0.01
STATUS_INTERVAL = 3600  # 1 jam dalam detik

# Inisialisasi klien Binance
client = Client(api_key=API_KEY, api_secret=API_SECRET, testnet=True)

def get_db_connection():
    conn = sqlite3.connect('table_transactions.db', check_same_thread=False)
    return conn

def setup_database():
    conn = get_db_connection()
    cursor = conn.cursor()
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
    conn.close()

setup_database()

def get_symbol_step_size(symbol):
    try:
        info = client.get_symbol_info(symbol)
        for f in info['filters']:
            if f['filterType'] == 'LOT_SIZE':
                return float(f['stepSize'])
    except BinanceAPIException as e:
        logging.error(f"Gagal mendapatkan stepSize untuk {symbol}: {e}")
    return None

def round_quantity(quantity, step_size):
    return math.floor(quantity / step_size) * step_size

def save_transaction(symbol, type, quantity, price):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO transactions (timestamp, symbol, type, quantity, price)
            VALUES (strftime('%Y-%m-%d %H:%M:%S', 'now'), ?, ?, ?, ?)
        ''', (symbol, type, quantity, price))
        conn.commit()
        conn.close()
        logging.info(f"Transaksi {type} {quantity} {symbol} pada harga {price} disimpan ke database")
    except sqlite3.Error as e:
        logging.error(f"Gagal menyimpan transaksi ke database: {e}")

def get_last_buy_price(symbol):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT price FROM transactions
            WHERE symbol = ? AND type = 'buy'
            ORDER BY timestamp DESC
            LIMIT 1
        ''', (symbol,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None
    except sqlite3.Error as e:
        logging.error(f"Gagal mendapatkan harga pembelian terakhir: {e}")
        return None

def get_last_price(symbol):
    try:
        ticker = client.get_symbol_ticker(symbol=symbol)
        return float(ticker['price'])
    except BinanceAPIException as e:
        logging.error(f"Gagal mendapatkan harga terakhir untuk {symbol}: {e}")
        return None

def get_balances():
    try:
        balances = {b['asset']: float(b['free']) for b in client.get_account()['balances']}
        usdt_free = balances.get('USDT', 0.0)
        asset_balances = {sym.replace('USDT', ''): balances.get(sym.replace('USDT', ''), 0.0) for sym in SYMBOLS}
        return usdt_free, asset_balances
    except BinanceAPIException as e:
        logging.error(f"Gagal mendapatkan saldo: {e}")
        return 0.0, {}

def should_buy(symbol, current_price):
    """
    Menganalisis tren harga untuk menentukan apakah ini waktu yang tepat untuk membeli.
    """
    try:
        # Ambil data candlestick 1 jam terakhir
        klines = client.get_historical_klines(symbol, Client.KLINE_INTERVAL_1MINUTE, "1 hour ago UTC")

        # Ekstrak closing prices dan volume
        prices = [float(k[4]) for k in klines]  # Closing prices
        volumes = [float(k[5]) for k in klines]  # Volumes

        if not prices or not volumes:
            return False

        # Hitung indikator teknikal sederhana
        avg_price = sum(prices) / len(prices)
        avg_volume = sum(volumes) / len(volumes)
        latest_volume = volumes[-1]

        # Kondisi untuk membeli:
        # 1. Harga saat ini lebih rendah dari rata-rata (potensi oversold)
        price_condition = current_price < avg_price

        # 2. Volume saat ini lebih tinggi dari rata-rata (menunjukkan momentum)
        volume_condition = latest_volume > avg_volume

        # 3. Tren harga menurun melambat
        price_changes = [prices[i] - prices[i-1] for i in range(1, len(prices))]
        recent_changes = price_changes[-10:]  # 10 menit terakhir
        trend_slowing = sum(recent_changes) > sum(price_changes[-20:-10])  # Dibandingkan dengan 10 menit sebelumnya

        # Logging untuk debugging
        logging.info(f"""
        Analisis {symbol}:
        Harga saat ini: {current_price}
        Rata-rata harga: {avg_price}
        Volume saat ini: {latest_volume}
        Rata-rata volume: {avg_volume}
        Tren melambat: {trend_slowing}
        """)

        # Kembalikan True jika semua kondisi terpenuhi
        return price_condition and volume_condition and trend_slowing

    except Exception as e:
        logging.error(f"Error checking buy condition for {symbol}: {e}")
        return False

def send_asset_status():
    """Mengirim status aset saat ini ke Telegram."""
    try:
        usdt_free, asset_balances = get_balances()
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        status_message = f"🔄 Status Aset ({current_time})\n\n"
        status_message += f"💵 USDT: {usdt_free:.2f}\n\n"

        total_value_usdt = usdt_free

        for symbol in SYMBOLS:
            asset = symbol.replace('USDT', '')
            balance = asset_balances.get(asset, 0.0)
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

def trade():
    while True:
        try:
            usdt_free, asset_balances = get_balances()

            if usdt_free > 0:
                usdt_per_symbol = usdt_free / len(SYMBOLS)
            else:
                usdt_per_symbol = 0

            for symbol in SYMBOLS:
                last_price = get_last_price(symbol)
                if last_price is None:
                    continue

                asset = symbol.replace('USDT', '')
                asset_balance = asset_balances.get(asset, 0.0)

                if asset_balance == 0.0:
                    # Tambahkan analisis tren sebelum membeli
                    if should_buy(symbol, last_price):
                        quantity = usdt_per_symbol * BUY_MULTIPLIER / last_price
                        step_size = get_symbol_step_size(symbol)
                        if step_size:
                            quantity = round_quantity(quantity, step_size)
                        if quantity > 0:
                            buy_asset(symbol, quantity)
                    else:
                        logging.info(f"Kondisi membeli belum tepat untuk {symbol}")
                else:
                    last_buy_price = get_last_buy_price(symbol)
                    if last_buy_price and last_price >= last_buy_price * SELL_MULTIPLIER:
                        sell_asset(symbol, asset_balance)

        except Exception as e:
            logging.error(f"Error dalam fungsi trade: {e}")

        time.sleep(CACHE_LIFETIME)

def status_monitor():
    """Thread terpisah untuk memantau dan mengirim status setiap jam."""
    while True:
        send_asset_status()
        time.sleep(STATUS_INTERVAL)

def main():
    # Memulai thread untuk monitoring status
    status_thread = threading.Thread(target=status_monitor, daemon=True)
    status_thread.start()

    # Memulai thread untuk trading
    trade_thread = threading.Thread(target=trade, daemon=True)
    trade_thread.start()

    # Menunggu kedua thread selesai
    status_thread.join()
    trade_thread.join()

if __name__ == "__main__":
    main()
