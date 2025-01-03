import logging
import time
import schedule
from binance.client import Client
from config.settings import settings
from strategy import PriceActionStrategy  # Pastikan Anda memiliki strategi ini

# Konfigurasi logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

class BotTrading:
    def __init__(self):
        # Inisialisasi klien dengan API Key dan Secret
        self.client = Client(settings['API_KEY'], settings['API_SECRET'])
        self.client.API_URL = 'https://testnet.binance.vision/api'  # Setel URL ke Testnet
        self.strategy = PriceActionStrategy('ETHUSDT')  # Ganti dengan simbol yang Anda gunakan
        self.latest_activity = self.load_latest_activity()
        self.historical_data = self.load_historical_data()

    def load_latest_activity(self):
        # Implementasi untuk memuat aktivitas terbaru
        pass

    def load_historical_data(self):
        # Implementasi untuk memuat data historis
        pass

    def check_price(self):
        try:
            # Mendapatkan harga terkini
            current_price = float(self.client.get_symbol_ticker(symbol='ETHUSDT')['price'])
            logging.debug(f"Harga saat ini untuk ETHUSDT: {current_price}")

            # Menggunakan strategi untuk menentukan aksi
            action = self.strategy.check_price(self.client)

            if action == 'BUY':
                logging.info(f"Melakukan pembelian ETHUSDT pada harga {current_price}")
                self.client.create_test_order(
                    symbol='ETHUSDT',
                    side='BUY',
                    type='LIMIT',
                    quantity=0.01,  # Sesuaikan dengan jumlah yang valid
                    price=current_price,
                    timeInForce='GTC'
                )
                # Simpan aktivitas terbaru
                self.latest_activity = {'action': 'BUY', 'price': current_price}
                self.save_latest_activity()

            elif action == 'SELL':
                logging.info(f"Melakukan penjualan ETHUSDT pada harga {current_price}")
                self.client.create_test_order(
                    symbol='ETHUSDT',
                    side='SELL',
                    type='LIMIT',
                    quantity=0.01,  # Sesuaikan dengan jumlah yang valid
                    price=current_price,
                    timeInForce='GTC'
                )
                # Simpan aktivitas terbaru
                self.latest_activity = {'action': 'SELL', 'price': current_price}
                self.save_latest_activity()

        except Exception as e:
            logging.error(f"Error dalam check_price: {e}")

    def save_latest_activity(self):
        # Implementasi untuk menyimpan aktivitas terbaru
        pass

    def run(self):
        logging.info("Bot trading dimulai...")
        schedule.every(1).minutes.do(self.check_price)  # Atur interval pengecekan harga
        while True:
            schedule.run_pending()
            time.sleep(1)

if __name__ == "__main__":
    bot = BotTrading()
    bot.run()
