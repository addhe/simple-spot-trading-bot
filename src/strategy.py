# src/strategy.py
import pandas as pd

class PriceActionStrategy:
    def __init__(self, symbol):
        self.symbol = symbol
        self.data = pd.DataFrame()

    def check_price(self, client):
        # Implementasi strategi Price Action
        self.data = client.get_symbol_ticker(symbol=self.symbol)
        # Implementasi logika strategi Price Action
        if self.data['price'] > 10000:
            # Implementasi aksi trading
            client.place_order(symbol=self.symbol, side='BUY', type='LIMIT', quantity=0.1, price=10000)
