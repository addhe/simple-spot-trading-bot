import requests
import os

def kirim_notifikasi_telegram(pesan):
    token = os.environ['TELEGRAM_TOKEN']
    chat_id = os.environ['TELEGRAM_CHAT_ID']
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

def notifikasi_balance(balance):
    pesan = f'Balance: {balance}'
    kirim_notifikasi_telegram(pesan)
