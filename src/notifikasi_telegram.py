# src/notifikasi_telegram.py
import requests
import os
import logging
from config.config import SYMBOLS  # Mengimpor SYMBOLS dari konfigurasi

def kirim_notifikasi_telegram(pesan: str) -> None:
    token = os.environ['TELEGRAM_TOKEN']
    chat_id = os.environ['TELEGRAM_GROUP_ID']
    url = f'https://api.telegram.org/bot{token}/sendMessage'
    params = {
        'chat_id': chat_id,
        'text': pesan
    }
    response = requests.post(url, params=params)
    if response.status_code == 200:
        logging.info('Notifikasi Telegram berhasil dikirim')
    else:
        logging.error('Gagal mengirim notifikasi Telegram')

def notifikasi_buy(symbol: str, quantity: float, price: float) -> None:
    # Menambahkan informasi lebih lengkap pada notifikasi
    pesan = f'📈 *Buy Alert* 📉\n\n' \
            f'Membeli {symbol} sebanyak {quantity} dengan harga {price} USDT.'
    kirim_notifikasi_telegram(pesan)

def notifikasi_sell(symbol: str, quantity: float, price: float, estimasi_profit: float) -> None:
    # Menambahkan estimasi profit dengan lebih jelas
    pesan = f'💰 *Sell Alert* 💸\n\n' \
            f'Menjual {symbol} sebanyak {quantity} dengan harga {price} USDT.\n' \
            f'Estimasi Profit: {estimasi_profit:.2f} USDT'
    kirim_notifikasi_telegram(pesan)

def notifikasi_balance(client) -> None:
    try:
        account_info = client.get_account()  # Mengambil informasi akun dari API
        usdt_balance = 0
        symbol_balances = {}

        # Menghitung saldo USDT dan simbol dasar yang ditentukan
        for balance in account_info['balances']:
            asset = balance['asset']
            free = float(balance['free'])
            if asset == 'USDT':
                usdt_balance = free
            elif asset in [symbol[:-4] for symbol in SYMBOLS]:  # Memeriksa saldo untuk simbol dasar
                symbol_balances[asset] = free

        # Menyusun pesan notifikasi dengan informasi saldo yang lebih rinci
        pesan = f'📊 *Saldo Akun* 📉\n\n' \
                f'Saldo USDT: {usdt_balance:.2f} USDT\n'
        for symbol, balance in symbol_balances.items():
            pesan += f'{symbol} Balance: {balance:.2f} {symbol}\n'

        kirim_notifikasi_telegram(pesan)

    except Exception as e:
        logging.error(f"Error saat mengambil saldo: {e}")
        kirim_notifikasi_telegram(f"❗ Error saat mengambil saldo: {e}")  # Kirim notifikasi kesalahan yang lebih jelas
