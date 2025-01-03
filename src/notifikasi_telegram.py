# src/notifikasi_telegram.py
import requests
import os
from config.config import SYMBOL  # Mengimpor SYMBOL dari konfigurasi

def kirim_notifikasi_telegram(pesan):
    token = os.environ['TELEGRAM_TOKEN']
    chat_id = os.environ['TELEGRAM_GROUP_ID']
    url = f'https://api.telegram.org/bot{token}/sendMessage'
    params = {
        'chat_id': chat_id,
        'text': pesan
    }
    response = requests.post(url, params=params)
    if response.status_code == 200:
        print('Notifikasi Telegram berhasil dikirim')
    else:
        print('Gagal mengirim notifikasi Telegram')

def notifikasi_buy(symbol, quantity, price):
    pesan = f'Buy {symbol} sebanyak {quantity} dengan harga {price}'
    kirim_notifikasi_telegram(pesan)

def notifikasi_sell(symbol, quantity, price, estimasi_profit):
    pesan = f'Sell {symbol} sebanyak {quantity} dengan harga {price}\nEstimasi Profit: {estimasi_profit}'
    kirim_notifikasi_telegram(pesan)

def notifikasi_balance(client):
    try:
        account_info = client.get_account()  # Mengambil informasi akun dari API
        usdt_balance = 0
        symbol_balance = 0

        # Menghitung saldo USDT dan simbol dasar yang ditentukan
        base_symbol = SYMBOL[:-4]  # Mengambil simbol dasar (misal ETH dari ETHUSDT)

        for balance in account_info['balances']:
            asset = balance['asset']
            free = float(balance['free'])
            if asset == 'USDT':
                usdt_balance = free
            elif asset == base_symbol:  # Memeriksa saldo untuk simbol dasar
                symbol_balance = free

        # Menyusun pesan notifikasi
        pesan = f'Balance USDT: {usdt_balance}\n{base_symbol} Balance: {symbol_balance}'

        kirim_notifikasi_telegram(pesan)

    except Exception as e:
        print(f"Error saat mengambil saldo: {e}")
        kirim_notifikasi_telegram(f"Error saat mengambil saldo: {e}")  # Kirim notifikasi kesalahan
