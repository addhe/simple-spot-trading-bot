import logging  
from binance.client import Client  
from config.settings import settings  

SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']

# Konfigurasi logging  
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',   
                    filename='sell_all_assets.log', filemode='w')  # Menyimpan log ke file  
  
def sell_all_assets():  
    # Inisialisasi klien Binance dengan API Key dan Secret  
    client = Client(settings['API_KEY'], settings['API_SECRET'])  
    client.API_URL = 'https://testnet.binance.vision/api'  # Setel URL ke Testnet  
  
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
                response = client.create_order(  
                    symbol=symbol,  
                    side='SELL',  
                    type='MARKET',  # Menggunakan order pasar untuk menjual  
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
  
            else:  
                logging.info(f"Tidak ada saldo untuk {asset}.")  
  
    except Exception as e:  
        logging.error(f"Terjadi kesalahan: {e}")  
  
if __name__ == "__main__":  
    sell_all_assets()  
