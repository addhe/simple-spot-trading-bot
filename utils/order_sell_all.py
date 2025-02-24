import logging
from binance.client import Client
from config.settings import (
    API_KEY,
    API_SECRET,
    BASE_URL,
    TELEGRAM_TOKEN,
    TELEGRAM_GROUP_ID,
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
                order = client.order_market_sell(
                    symbol=symbol,
                    quantity=quantity
                )
                logging.info(f"Jual {quantity} {symbol} berhasil pada harga {order['fills'][0]['price']}")
            else:
                logging.info(f"Tidak ada saldo untuk menjual {symbol}")
    except BinanceAPIException as e:
        logging.error(f"Gagal menjual aset: {e}")

if __name__ == "__main__":
    sell_all_assets()
