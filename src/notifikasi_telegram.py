# src/notifikasi_telegram.py
import requests
import os

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
        crypto_balances = []

        # Menghitung saldo USDT dan simbol trading lainnya
        for balance in account_info['balances']:
            asset = balance['asset']
            free = float(balance['free'])
            if asset == 'USDT':
                usdt_balance = free
            elif free > 0:
                crypto_balances.append(f"{asset}: {free}")

        # Menyusun pesan notifikasi
        pesan = f'Balance USDT: {usdt_balance}\n'
        if crypto_balances:
            # Batasi jumlah simbol yang ditampilkan
            limited_balances = crypto_balances[:10]  # Tampilkan hanya 10 simbol teratas
            pesan += 'Saldo Kripto:\n' + '\n'.join(limited_balances)
            pesan += f"\n... dan {len(crypto_balances) - 10} simbol lainnya."  # Menyebutkan jumlah simbol lainnya
        else:
            pesan += 'Tidak ada saldo kripto yang tersedia.'

        kirim_notifikasi_telegram(pesan)

    except Exception as e:
        print(f"Error saat mengambil saldo: {e}")
        kirim_notifikasi_telegram(f"Error saat mengambil saldo: {e}")  # Kirim notifikasi kesalahan
