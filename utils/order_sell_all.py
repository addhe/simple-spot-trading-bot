import logging
from binance.client import Client
from config.settings import (
    API_KEY,
    API_SECRET,
    BASE_URL,
    SYMBOLS
)

# Konfigurasi logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
                    filename='sell_all_assets.log', filemode='w')  # Menyimpan log ke file

# Inisialisasi klien Binance
client = Client(api_key=API_KEY, api_secret=API_SECRET)

def sell_all_assets():
    try:
        balances = client.get_account()['balances']
        for symbol in SYMBOLS:
            asset = symbol.replace('USDT', '')
            asset_balance = next((item for item in balances if item['asset'] == asset), None)
            if asset_balance and float(asset_balance['free']) > 0:
                quantity = float(asset_balance['free'])
                step_size, min_qty, max_qty, min_notional = get_symbol_info(symbol)

                if step_size is not None and min_qty is not None and max_qty is not None and min_notional is not None:
                    quantity = round_quantity(quantity, step_size)
                    quantity = max(quantity, min_qty)
                    quantity = min(quantity, max_qty)

                    if quantity > 0:
                        sell_asset(symbol, quantity)
    except Exception as e:
        logging.error(f"Gagal menjual semua aset: {e}")

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
    except Exception as e:
        logging.error(f"Gagal mendapatkan informasi simbol untuk {symbol}: {e}")
        return None, None, None, None

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
    except Exception as e:
        logging.error(f"Gagal menjual {symbol}: {e}")
        return None

if __name__ == "__main__":
    sell_all_assets()
