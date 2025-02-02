# test_get_balance.py    
import os    
import logging    
from binance.client import Client    
from config.settings import BASE_URL, API_KEY, API_SECRET, SYMBOLS
    
# Konfigurasi logging    
logging.basicConfig(level=logging.DEBUG, filename='get_balance.log',    
                    format='%(asctime)s - %(levelname)s - %(message)s')    
    
def get_balance(client, asset: str) -> float:    
    try:    
        account_info = client.get_account()    
        for balance in account_info['balances']:    
            if balance['asset'] == asset:    
                return float(balance['free'])    
        return 0.0    
    except Exception as e:    
        logging.error(f"Error saat mengambil saldo {asset}: {e}")    
        return 0.0    
    
def main():    
    client = Client(API_KEY, API_SECRET)    
    client.API_URL = BASE_URL
    
    # Mendapatkan saldo untuk semua simbol yang ada di SYMBOLS    
    balances = {}    
    for symbol in SYMBOLS:    
        asset = symbol[:-4]  # Mengambil nama aset (misalnya BTC dari BTCUSDT)    
        balances[asset] = get_balance(client, asset)    
    
    # Mendapatkan saldo USDT secara terpisah    
    usdt_balance = get_balance(client, 'USDT')    
    balances['USDT'] = usdt_balance  # Menambahkan saldo USDT ke dictionary balances  
    
    # Logging saldo untuk setiap aset    
    for asset, balance in balances.items():    
        logging.info(f"Balance {asset}: {balance:.3f}")    
    
if __name__ == "__main__":    
    main()    
