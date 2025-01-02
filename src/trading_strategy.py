import logging
import numpy as np

# Setup logger
logger = logging.getLogger(__name__)

class TradingStrategy:
    def __init__(self, config):
        self.config = config
        self.take_profit = config['TAKE_PROFIT']
        self.stop_loss = config['STOP_LOSS']

    def ema(self, market_data, period):
        ema = []
        for i in range(len(market_data)):
            if i == 0:
                ema.append(float(market_data[i][4]))
            else:
                ema.append((float(market_data[i][4]) * (2 / (period + 1))) + (ema[i-1] * (1 - (2 / (period + 1)))))
        return ema

    def trading_strategy_ema(self, market_data):
        ema_short = self.ema(market_data, self.config['EMA_SHORT_PERIOD'])
        ema_long = self.ema(market_data, self.config['EMA_LONG_PERIOD'])
        if ema_short[-1] > ema_long[-1]:
            return 'BUY'
        elif ema_short[-1] < ema_long[-1]:
            return 'SELL'
        else:
            return None

    def check_take_profit(self, market_data, buy_price):
        current_price = float(market_data[-1][4])
        profit = (current_price - buy_price) / buy_price * 100
        if profit >= self.take_profit:
            return True
        return False

    def check_stop_loss(self, market_data, buy_price):
        current_price = float(market_data[-1][4])
        loss = (buy_price - current_price) / buy_price * 100
        if loss >= self.stop_loss:
            return True
        return False