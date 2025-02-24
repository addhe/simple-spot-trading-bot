import logging
from binance.client import Client
from config.settings import (
    API_KEY,
    API_SECRET,
    BASE_URL,
    TELEGRAM_TOKEN,
    TELEGRAM_GROUP_ID
)

# Konfigurasi logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
                    filename='sell_all_assets.log', filemode='w')  # Menyimpan log ke file

# Inisialisasi klien Binance
client = Client(api_key=API_KEY, api_secret=API_SECRET)

def sell_all_assets():
    try:
        balances = client.get_account()['balances']
        for balance in balances:
            asset = balance['asset']
            free_balance = float(balance['free'])
            if free_balance > 0 and asset != 'USDT':
                symbol = f"{asset}USDT"
                try:
                    order = client.order_market_sell(
                        symbol=symbol,
                        quantity=free_balance
                    )
                    logging.info(f"Jual {free_balance} {symbol} pada harga {order['fills'][0]['price']}")
                except (BinanceAPIException, BinanceOrderException) as e:
                    logging.error(f"Gagal menjual {free_balance} {symbol}: {e}")
    except (BinanceAPIException, BinanceOrderException) as e:
        logging.error(f"Gagal mendapatkan saldo: {e}")

if __name__ == "__main__":
    sell_all_assets()
