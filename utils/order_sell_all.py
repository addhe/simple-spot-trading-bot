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
        # Cek koneksi dengan API
        logging.info("Menghubungkan ke Binance Testnet...")
        server_time = client.get_server_time()
        logging.info(f"Waktu server: {server_time['serverTime']}")

        for symbol in SYMBOLS:
            asset = symbol[:-4]  # Mengambil nama aset (misalnya BTC dari BTCUSDT)
            balance = client.get_asset_balance(asset=asset)

            if balance and float(balance['free']) > 0:
                quantity = float(balance['free'])  # Mengambil jumlah yang tersedia untuk dijual
                logging.info(f"Mencoba menjual {quantity} {asset} untuk {symbol}...")

                # Membuat order jual
                response = client.order_market_sell(
                    symbol=symbol,
                    quantity=quantity
                )

                # Menyusun informasi order yang berhasil
                order_info = {
                    'symbol': response['symbol'],
                    'orderId': response['orderId'],
                    'executedQty': response['executedQty'],
                    'cummulativeQuoteQty': response['cummulativeQuoteQty'],
                    'status': response['status'],
                    'fills': response['fills']
                }

                # Log hasil penjualan
                logging.info(f"Order jual berhasil untuk {asset}:")
                logging.info(f"  - Order ID: {order_info['orderId']}")
                logging.info(f"  - Jumlah yang dieksekusi: {order_info['executedQty']} {asset}")
                logging.info(f"  - Total nilai transaksi: {order_info['cummulativeQuoteQty']} USDT")
                logging.info(f"  - Status: {order_info['status']}")
                for fill in order_info['fills']:
                    logging.info(f"    - Harga: {fill['price']} USDT, Jumlah: {fill['qty']} {asset}")

                # Kirim pesan Telegram
                message = (
                    f"Order jual berhasil untuk {asset}:\n"
                    f"  - Order ID: {order_info['orderId']}\n"
                    f"  - Jumlah yang dieksekusi: {order_info['executedQty']} {asset}\n"
                    f"  - Total nilai transaksi: {order_info['cummulativeQuoteQty']} USDT\n"
                    f"  - Status: {order_info['status']}"
                )
                send_telegram_message(message)

            else:
                logging.info(f"Tidak ada saldo untuk {asset}.")

    except Exception as e:
        logging.error(f"Terjadi kesalahan: {e}")

if __name__ == "__main__":
    sell_all_assets()
