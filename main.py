import ccxt
import logging
import time
from datetime import datetime
import json
import os

import src.fetch_market_data as fetch_market_data
import src.trading_strategy as trading_strategy
import src.execute_trade as execute_trade
import src.calculate_rsi as calculate_rsi
import src.calculate_ema as calculate_ema
from src.load_config import load_config, validate_config
from src.initialize_exchange import initialize_exchange
from src.logger import setup_logger

# Setup logger
logger = setup_logger(__name__)

def main():
    config = load_config()
    config = validate_config(config)

    # Load API Key and Secret from Environment Variables
    api_key = os.environ.get('API_KEY_BINANCE')
    api_secret = os.environ.get('API_SECRET_BINANCE')

    if not api_key or not api_secret:
        logger.error("API Key or Secret not found in environment variables.")
        exit(1)

    exchange = initialize_exchange(api_key, api_secret)

    while True:
        try:
            market_data = fetch_market_data.fetch_market_data(exchange, config['SYMBOL'], config['TIMEFRAME'])
            if market_data is not None:
                side = trading_strategy.trading_strategy(market_data)
                if side is not None:
                    rsi = calculate_rsi.calculate_rsi(market_data)
                    ema = calculate_ema.calculate_ema(market_data)
                    logger.info(f"RSI: {rsi}, EMA: {ema}, Side: {side}")
                    #execute_trade.execute_trade(exchange, config['SYMBOL'], side)
        except ccxt.BaseError as e:
            logger.error(f"Error exchange: {e}")
        except Exception as e:
            logger.error(f"Error: {e}")
        time.sleep(60)

if __name__ == '__main__':
    main()