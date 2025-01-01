import requests

url = "https://testnet.binance.vision/api/v3/klines"
params = {
    "symbol": "BTCUSDT",
    "interval": "5m"
}

response = requests.get(url, params=params)

if response.status_code == 200:
    print(response.json())
else:
    print(f"Error: {response.status_code}")
    print(f"Response: {response.text}")