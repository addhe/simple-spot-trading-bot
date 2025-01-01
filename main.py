import logging
import time
import json
from binance.spot import Spot as Client
from src.initialize_exchange import initialize_exchange
from src.fetch_market_data import fetch_market_data_from_exchange
from src.trading_strategy import TradingStrategy

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def load_config(filename='config.json'):
    with open(filename, 'r') as f:
        return json.load(f)

def execute_trade(client, symbol, side, quantity):
    try:
        order = client.new_order(symbol=symbol, side=side, type='MARKET', quantity=quantity)
        logger.info(f"Order executed: {order}")
    except Exception as e:
        logger.error(f"Error executing trade: {e}")

def main():
    config = load_config()
    client = initialize_exchange()
    symbol = config['SYMBOL']
    timeframe = config['TIMEFRAME']
    quantity = config['QUANTITY']

    trading_strategy = TradingStrategy(config)

    while True:
        try:
            market_data = fetch_market_data_from_exchange(symbol, timeframe)
            side = trading_strategy.trading_strategy_ema(market_data)
            if side is not None:
                execute_trade(client, symbol, side, quantity)
            else:
                logger.info("No trade executed.")
        except Exception as e:
            logger.error(f"Error: {e}")
        time.sleep(config['TRADE_INTERVAL'])

if __name__ == '__main__':
    main()