import logging
from binance.client import Client

# Konfigurasi logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
                    filename='sell_all_assets.log', filemode='w')  # Menyimpan log ke file

# Mengambil variabel lingkungan dari settings
API_KEY = os.environ['API_KEY_SPOT_TESTNET_BINANCE']
API_SECRET = os.environ['API_SECRET_SPOT_TESTNET_BINANCE']
BASE_URL = 'https://testnet.binance.vision/api'


# Inisialisasi klien Binance dengan API Key dan Secret
client = Client(api_key=API_KEY, api_secret=API_SECRET, testnet=True)

SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']

def get_asset_balance(asset):
    try:
        balances = client.get_account()['balances']
        asset_balance = next((item for item in balances if item['asset'] == asset), None)
        free_balance = float(asset_balance['free']) if asset_balance else 0.0
        return free_balance
    except BinanceAPIException as e:
        logging.error(f"Gagal mendapatkan saldo untuk aset {asset}: {e}")
        return 0.0

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
        return order
    except (BinanceAPIException, BinanceOrderException) as e:
        logging.error(f"Gagal menjual {symbol}: {e}")
        return None

def sell_all_assets():
    for symbol in SYMBOLS:
        asset = symbol.replace('USDT', '')
        asset_balance = get_asset_balance(asset)
        if asset_balance == 0.0:
            logging.info(f"Tidak ada saldo untuk {asset}")
            continue

        step_size, min_qty, max_qty = get_symbol_info(symbol)
        if step_size is None or min_qty is None or max_qty is None:
            logging.error(f"Gagal mendapatkan informasi simbol untuk {symbol}")
            continue

        quantity = round_quantity(asset_balance, step_size)
        quantity = max(quantity, min_qty)
        quantity = min(quantity, max_qty)

        if quantity > 0:
            sell_asset(symbol, quantity)
        else:
            logging.info(f"Jumlah aset {asset} tidak memenuhi syarat minimal untuk penjualan")

if __name__ == "__main__":
    sell_all_assets()
