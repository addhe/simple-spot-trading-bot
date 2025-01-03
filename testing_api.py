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

# Fungsi untuk menjual semua BTC
def get_total_btc():
    account_info = get_account_info()
    balances = account_info["balances"]
    for balance in balances:
        if balance["asset"] == "BTC":
            return float(balance['free']) + float(balance['locked'])

def set_btc_zero():
    url = f"{base_url}/order"
    params = {
        "symbol": "BTCUSDT",
        "side": "SELL",
        "type": "MARKET",
        "quantity": get_total_btc(),
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
    response = requests.post(url, params=params, headers=headers)
    if response.status_code == 200:
        print("Semua BTC telah dijual")
    else:
        print(f"Error: {response.status_code}")
        print(f"Response: {response.text}")

def reset_usdt(saldo_usdt):
    url = f"{base_url}/order"
    params = {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "type": "MARKET",
        "quoteOrderQty": saldo_usdt,
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
    response = requests.post(url, params=params, headers=headers)
    if response.status_code == 200:
        print(f"Saldo USDT telah direset ke {saldo_usdt} USDT")
    else:
        print(f"Error: {response.status_code}")
        print(f"Response: {response.text}")

def add_usdt(jumlah_usdt):
    # Cek saldo BTC yang dimiliki
    saldo_btc = get_total_btc()

    # Cek saldo USDT yang dimiliki
    saldo_usdt = get_total_usdt()

    # Jika saldo USDT < jumlah_usdt, beli USDT yang dibutuhkan
    if saldo_usdt < jumlah_usdt:
        # Jika saldo BTC > 0, jual BTC untuk dapatkan USDT
        if saldo_btc > 0:
            # Jual BTC untuk dapatkan USDT
            url = f"{base_url}/order"
            params = {
                "symbol": "BTCUSDT",
                "side": "SELL",
                "type": "MARKET",
                "quantity": saldo_btc,
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
            response = requests.post(url, params=params, headers=headers)
            if response.status_code == 200:
                print("BTC telah dijual")
            else:
                print(f"Error: {response.status_code}")
                print(f"Response: {response.text}")

        # Beli USDT yang dibutuhkan
        url = f"{base_url}/order"
        params = {
            "symbol": "BTCUSDT",
            "side": "BUY",
            "type": "MARKET",
            "quoteOrderQty": jumlah_usdt - saldo_usdt,
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
        response = requests.post(url, params=params, headers=headers)
        if response.status_code == 200:
            print(f"USDT telah ditambahkan sebesar {jumlah_usdt - saldo_usdt} USDT")
        else:
            print(f"Error: {response.status_code}")
            print(f"Response: {response.text}")
    else:
        print("Saldo USDT sudah mencukupi")

# Main program
if __name__ == "__main__":
    #print("Informasi Akun:")
    #print(json.dumps(get_account_info(), indent=4))
    print("\nSaldo Akun:")
    get_balance()
    print("\nTotal BTC:")
    get_total_btc()
    print("\nTotal USDT:")
    get_total_usdt()
    print("\nOrder Terbuka:")
    get_open_orders()
    #print("reset account")
    #reset_usdt(1000)