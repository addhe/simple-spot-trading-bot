# test_get_balance.py
import os
import logging
from binance.client import Client
from config.settings import settings

# Konfigurasi logging
logging.basicConfig(level=logging.DEBUG, filename='test_get_balance.log',
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
    client = Client(settings['API_KEY'], settings['API_SECRET'])
    client.API_URL = 'https://testnet.binance.vision/api'

    usdt_balance = get_balance(client, 'USDT')
    eth_balance = get_balance(client, 'ETH')

    logging.info(f"Balance USDT: {usdt_balance}")
    logging.info(f"Balance ETH: {eth_balance}")

if __name__ == "__main__":
    main()
