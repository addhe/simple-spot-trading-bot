import pandas as pd

def calculate_rsi(prices, period=14):
    """Calculate RSI (Relative Strength Index) for a series of prices"""
    # Calculate price changes
    delta = prices.diff()

    # Separate gains and losses
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

    # Calculate RS and RSI
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))

    return rsi