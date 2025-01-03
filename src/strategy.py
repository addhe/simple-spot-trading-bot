# src/strategy.py
import pandas as pd
import logging

class PriceActionStrategy:
    def __init__(self, symbol):
        self.symbol = symbol
        self.data = pd.DataFrame()

    def check_price(self, client):
        try:
            # Mendapatkan data harga terkini
            self.data = client.get_symbol_ticker(symbol=self.symbol)
            current_price = float(self.data['price'])  # Pastikan harga adalah float

            logging.debug(f"Harga saat ini untuk {self.symbol}: {current_price}")

            # Logika strategi Price Action
            # Misalnya, kita bisa menggunakan harga dinamis dari bot
            buy_price = self.calculate_dynamic_buy_price(client)
            sell_price = self.calculate_dynamic_sell_price(client)

            logging.debug(f"Harga Beli Dinamis: {buy_price}, Harga Jual Dinamis: {sell_price}")

            # Contoh logika untuk aksi trading
            if current_price > buy_price:
                logging.info(f"Mempertimbangkan untuk membeli {self.symbol} pada harga {current_price}")
                return 'BUY', current_price
            elif current_price < sell_price:
                logging.info(f"Mempertimbangkan untuk menjual {self.symbol} pada harga {current_price}")
                return 'SELL', current_price
            else:
                logging.info(f"Tidak ada aksi yang diambil untuk {self.symbol} pada harga {current_price}")
                return 'HOLD', current_price

        except Exception as e:
            logging.error(f"Error saat memeriksa harga untuk {self.symbol}: {e}")

    def calculate_dynamic_buy_price(self, client):
        # Implementasi logika untuk menghitung harga beli dinamis
        # Misalnya, menggunakan rata-rata harga historis
        # Di sini Anda bisa menambahkan logika untuk mendapatkan data historis
        # Untuk contoh ini, kita akan menggunakan harga tetap
        return 10000  # Ganti dengan logika dinamis yang sesuai

    def calculate_dynamic_sell_price(self, client):
        # Implementasi logika untuk menghitung harga jual dinamis
        # Di sini Anda bisa menambahkan logika untuk mendapatkan data historis
        # Untuk contoh ini, kita akan menggunakan harga tetap
        return 9000  # Ganti dengan logika dinamis yang sesuai
