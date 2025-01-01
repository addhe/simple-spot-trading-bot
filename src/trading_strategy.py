import logging

# Setup logger
logger = logging.getLogger(__name__)

class TradingStrategy:
    def __init__(self, config):
        self.config = config

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
            return 'buy'
        elif ema_short[-1] < ema_long[-1]:
            return 'sell'
        else:
            return None