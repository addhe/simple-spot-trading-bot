import logging
from binance.client import Client
from config.settings import settings

# Konfigurasi logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

def test_api():
    # Inisialisasi klien Binance dengan API Key dan Secret
    client = Client(settings['API_KEY'], settings['API_SECRET'])
    client.API_URL = 'https://testnet.binance.vision/api'  # Setel URL ke Testnet

    try:
        # Cek koneksi dengan API
        logging.info("Menghubungkan ke Binance Testnet...")
        server_time = client.get_server_time()
        logging.info(f"Waktu server: {server_time}")

        # Coba melakukan order percobaan
        symbol = 'ETHUSDT'
        quantity = 0.01  # Sesuaikan dengan jumlah yang valid untuk pengujian
        price = 3000.00  # Sesuaikan dengan harga yang valid untuk pengujian

        logging.info(f"Mencoba melakukan order percobaan untuk {symbol}...")
        response = client.create_test_order(
            symbol=symbol,
            side='BUY',
            type='LIMIT',
            quantity=quantity,
            price=price
        )
        logging.info("Order percobaan berhasil dilakukan.")
    except Exception as e:
        logging.error(f"Terjadi kesalahan: {e}")

if __name__ == "__main__":
    test_api()
