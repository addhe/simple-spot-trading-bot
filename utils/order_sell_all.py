import os
import logging
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceOrderException
from src.send_telegram_message import send_telegram_message

# Konfigurasi logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
                    filename='sell_all_assets.log', filemode='w')  # Menyimpan log ke file

# Mengambil variabel lingkungan
API_KEY = os.environ['API_KEY_SPOT_TESTNET_BINANCE']
API_SECRET = os.environ['API_SECRET_SPOT_TESTNET_BINANCE']
BASE_URL = 'https://testnet.binance.vision/api'

# Inisialisasi klien Binance
client = Client(api_key=API_KEY, api_secret=API_SECRET, testnet=True)

SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']

def sell_all_assets():
    try:
        balances = client.get_account()['balances']
        for balance in balances:
            asset = balance['asset']
            free_balance = float(balance['free'])
            if free_balance > 0 and asset in ['BTC', 'ETH', 'SOL']:
                symbol = f"{asset}USDT"
                step_size, min_qty, max_qty = get_symbol_info(symbol)
                if step_size is not None and min_qty is not None and max_qty is not None:
                    quantity = round_quantity(free_balance, step_size)
                    quantity = max(quantity, min_qty)
                    quantity = min(quantity, max_qty)
                    if quantity > 0:
                        sell_order = sell_asset(symbol, quantity)
                        if sell_order:
                            logging.info(f"Jual {quantity} {symbol} pada harga {sell_order['fills'][0]['price']}")
                            send_telegram_message(f"Jual {quantity} {symbol} pada harga {sell_order['fills'][0]['price']}")
    except (BinanceAPIException, BinanceOrderException) as e:
        logging.error(f"Gagal menjual semua aset: {e}")
        send_telegram_message(f"Gagal menjual semua aset: {e}")

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

def round_quantity(quantity, step_size):
    return round(quantity / step_size) * step_size

def sell_asset(symbol, quantity):
    try:
        order = client.order_market_sell(
            symbol=symbol,
            quantity=quantity
        )
        logging.info(f"Jual {quantity} {symbol} pada harga {order['fills'][0]['price']}")
        send_telegram_message(f"Jual {quantity} {symbol} pada harga {order['fills'][0]['price']}")
        return order
    except (BinanceAPIException, BinanceOrderException) as e:
        logging.error(f"Gagal menjual {symbol}: {e}")
        send_telegram_message(f"Gagal menjual {symbol}: {e}")
        return None

if __name__ == "__main__":
    sell_all_assets()
