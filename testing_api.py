import requests
import hashlib
import hmac
import time
import json
import os

# Masukkan informasi akun Anda
api_key = os.environ.get('API_KEY_BINANCE')
api_secret = os.environ.get('API_SECRET_BINANCE')

# URL endpoint
base_url = "https://testnet.binance.vision/api/v3"

# Fungsi untuk membuat tanda tangan
def get_signature(params):
    query_string = "&".join([f"{key}={value}" for key, value in params.items()])
    return hmac.new(api_secret.encode(), query_string.encode(), hashlib.sha256).hexdigest()

# Fungsi untuk mendapatkan informasi akun
def get_account_info():
    url = f"{base_url}/account"
    params = {
        "recvWindow": 5000,
        "timestamp": int(time.time() * 1000)
    }
    params["signature"] = get_signature(params)
    headers = {
        "X-MBX-APIKEY": api_key,
        "X-MBX-SIGNATURE": params["signature"],
        "X-MBX-TS": str(params["timestamp"]),
        "Content-Type": "application/json"
    }
    response = requests.get(url, params=params, headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error: {response.status_code}")
        print(f"Response: {response.text}")

# Fungsi untuk mendapatkan saldo akun
def get_balance():
    account_info = get_account_info()
    balances = account_info["balances"]
    for balance in balances:
        if balance["asset"] == "BTC":
            print(f"Saldo BTC: {balance['free']} (tersedia) / {balance['locked']} (terkunci)")
        elif balance["asset"] == "USDT":
            print(f"Saldo USDT: {balance['free']} (tersedia) / {balance['locked']} (terkunci)")

# Fungsi untuk mendapatkan total BTC
def get_total_btc():
    account_info = get_account_info()
    balances = account_info["balances"]
    for balance in balances:
        if balance["asset"] == "BTC":
            print(f"Total BTC: {float(balance['free']) + float(balance['locked'])}")

# Fungsi untuk mendapatkan total USDT
def get_total_usdt():
    account_info = get_account_info()
    balances = account_info["balances"]
    for balance in balances:
        if balance["asset"] == "USDT":
            print(f"Total USDT: {float(balance['free']) + float(balance['locked'])}")

# Fungsi untuk mendapatkan order terbuka
def get_open_orders():
    url = f"{base_url}/openOrders"
    params = {
        "symbol": "BTCUSDT",
        "recvWindow": 5000,
        "timestamp": int(time.time() * 1000)
    }
    params["signature"] = get_signature(params)
    headers = {
        "X-MBX-APIKEY": api_key,
        "X-MBX-SIGNATURE": params["signature"],
        "X-MBX-TS": str(params["timestamp"]),
        "Content-Type": "application/json"
    }
    response = requests.get(url, params=params, headers=headers)
    if response.status_code == 200:
        print(json.dumps(response.json(), indent=4))
    else:
        print(f"Error: {response.status_code}")
        print(f"Response: {response.text}")

# Main program
if __name__ == "__main__":
    print("Informasi Akun:")
    print(json.dumps(get_account_info(), indent=4))
    print("\nSaldo Akun:")
    get_balance()
    print("\nTotal BTC:")
    get_total_btc()
    print("\nTotal USDT:")
    get_total_usdt()
    print("\nOrder Terbuka:")
    get_open_orders()