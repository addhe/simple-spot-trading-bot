import logging
from binance.client import Client
from config.settings import API_KEY, API_SECRET

# Initialize Binance client
client = Client(api_key=API_KEY, api_secret=API_SECRET)


def get_historical_prices(symbol, interval='1h', limit=100):
    try:
        # Fetch historical prices from Binance API
        klines = client.get_historical_klines(symbol, interval, limit=limit)
        # Extract closing prices from the response
        prices = [float(kline[4]) for kline in klines]  # Close price is at index 4
        return prices
    except Exception as e:
        logging.error(f"Failed to fetch historical prices for {symbol}: {e}")
        return []  # Return empty list on error
