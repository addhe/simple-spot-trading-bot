import os
import logging
import sqlite3
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceOrderException

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='logs/bot/sell_all_assets.log',
    filemode='a'
)

# Environment variables
API_KEY = os.getenv('API_KEY_SPOT_TESTNET_BINANCE', '')
API_SECRET = os.getenv('API_SECRET_SPOT_TESTNET_BINANCE', '')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', '')
TELEGRAM_GROUP_ID = os.getenv('TELEGRAM_GROUP_ID', '')

# Initialize Binance client
client = Client(api_key=API_KEY, api_secret=API_SECRET, testnet=True)

# Trading pairs to monitor
SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']

def get_db_connection():
    return sqlite3.connect('table_transactions.db')

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

def sell_asset(symbol, quantity):
    try:
        # Get precision requirements for the symbol
        symbol_info = client.get_symbol_info(symbol)
        lot_size_filter = next(filter(lambda x: x['filterType'] == 'LOT_SIZE', symbol_info['filters']))
        step_size = float(lot_size_filter['stepSize'])
        precision = len(str(step_size).split('.')[-1].rstrip('0'))
        
        # Round quantity according to symbol's precision
        quantity = round(quantity, precision)
        
        if quantity > 0:
            order = client.order_market_sell(
                symbol=symbol,
                quantity=quantity
            )
            price = float(order['fills'][0]['price'])
            logging.info(f"Berhasil menjual {quantity} {symbol} pada harga {price}")
            save_transaction(symbol, 'sell', quantity, price)
            return True
    except BinanceAPIException as e:
        logging.error(f"Binance API error saat menjual {symbol}: {e}")
    except BinanceOrderException as e:
        logging.error(f"Order error saat menjual {symbol}: {e}")
    except Exception as e:
        logging.error(f"Error tidak terduga saat menjual {symbol}: {e}")
    return False

def get_current_balances():
    try:
        account = client.get_account()
        # Filter only assets with non-zero balances
        balances = {}
        for balance in account['balances']:
            free_balance = float(balance['free'])
            if free_balance > 0:
                balances[balance['asset']] = free_balance
        return balances
    except BinanceAPIException as e:
        logging.error(f"Gagal mendapatkan saldo: {e}")
        return {}

def sell_all_assets():
    logging.info("Memulai proses penjualan semua aset...")
    
    # Get current balances
    balances = get_current_balances()
    
    if not balances:
        logging.info("Tidak ada saldo yang tersedia untuk dijual")
        return
    
    # Sell each asset
    for symbol in SYMBOLS:
        asset = symbol.replace('USDT', '')
        balance = balances.get(asset, 0.0)
        
        if balance > 0:
            logging.info(f"Mencoba menjual {balance} {asset}")
            if sell_asset(symbol, balance):
                logging.info(f"Berhasil menjual semua {asset}")
            else:
                logging.error(f"Gagal menjual {asset}")

def main():
    try:
        # Check if API credentials are available
        if not API_KEY or not API_SECRET:
            raise ValueError("API Key dan Secret tidak ditemukan! Pastikan telah diatur di environment variables.")
        
        # Execute sell all
        sell_all_assets()
        
        # Get final balances to confirm
        final_balances = get_current_balances()
        logging.info(f"Saldo akhir setelah penjualan: {final_balances}")
        
    except Exception as e:
        logging.error(f"Error dalam proses penjualan: {e}")
    finally:
        logging.info("Proses penjualan selesai")

if __name__ == "__main__":
    main()