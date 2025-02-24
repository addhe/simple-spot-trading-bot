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
                    filename='sell_all_assets.log', filemode='a')  # Menyimpan log ke file

# Inisialisasi klien Binance
client = Client(api_key=API_KEY, api_secret=API_SECRET)

def sell_all_assets():
    try:
        # Mendapatkan saldo aset
        balances = client.get_account()['balances']
        asset_balances = {item['asset']: float(item['free']) for item in balances if item['asset'] in ['BTC', 'ETH', 'SOL']}

        for asset, balance in asset_balances.items():
            if balance > 0:
                symbol = f"{asset}USDT"
                step_size, min_qty, max_qty = get_symbol_info(symbol)
                if step_size is None or min_qty is None or max_qty is None:
                    logging.error(f"Gagal mendapatkan informasi simbol untuk {symbol}")
                    continue

                quantity = round_quantity(balance, step_size)
                quantity = max(quantity, min_qty)
                quantity = min(quantity, max_qty)

                if quantity > 0:
                    order = client.order_market_sell(
                        symbol=symbol,
                        quantity=quantity
                    )
                    logging.info(f"Jual {quantity} {symbol} pada harga {order['fills'][0]['price']}")
                else:
                    logging.info(f"Jumlah aset {symbol} tidak valid untuk penjualan")
            else:
                logging.info(f"Tidak ada saldo untuk menjual {asset}")

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
                return step_size, min_qty, max_qty
        logging.error(f"Tidak ditemukan stepSize, minQty, atau maxQty untuk simbol {symbol}")
        return None, None, None
    except Exception as e:
        logging.error(f"Gagal mendapatkan informasi simbol untuk {symbol}: {e}")
        return None, None, None

def round_quantity(quantity, step_size):
    return round(quantity / step_size) * step_size

if __name__ == "__main__":
    sell_all_assets()
