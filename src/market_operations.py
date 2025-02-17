import logging
from src.get_balances import get_balances
from src.save_transaction import save_transaction
from src.send_telegram_message import send_telegram_message
from datetime import datetime
from src.logger import logger
from config.settings import MIN_24H_VOLUME


def get_24h_stats(symbol):
    """
    Fetch 24-hour statistics for the given symbol from Binance.
    """
    try:
        from binance.client import Client
        client = Client()
        
        logger.debug(f"Fetching 24h stats for {symbol}")
        stats = client.get_ticker(symbol=symbol)
        
        result = {
            'symbol': symbol,
            'price': float(stats['lastPrice']),
            'volume': float(stats['volume']),
            'high': float(stats['highPrice']),
            'low': float(stats['lowPrice']),
            'price_change': float(stats['priceChangePercent'])
        }
        
        logger.debug(f"24h stats for {symbol}:")
        logger.debug(f"Price: ${result['price']:.2f}")
        logger.debug(f"Volume: ${result['volume']:.2f}")
        logger.debug(f"High: ${result['high']:.2f}")
        logger.debug(f"Low: ${result['low']:.2f}")
        logger.debug(f"Price Change: {result['price_change']}%")
        
        return result
    except Exception as e:
        logger.error(f"Error fetching 24h stats for {symbol}: {e}")
        return None


def get_last_price(symbol):
    """
    Fetch the last price for the given symbol from Binance.
    """
    logger.debug(f"Getting last price for {symbol}")
    stats = get_24h_stats(symbol)
    if stats:
        logger.debug(f"Last price for {symbol}: ${stats['price']:.2f}")
        return stats['price']
    logger.warning(f"Could not get last price for {symbol}")
    return None


def process_symbol_trade(self, symbol):
    """Process trading logic for a symbol with error handling."""
    logger.info(f"Starting trade processing for {symbol}")
    try:
        # Get market stats
        market_stats = get_24h_stats(symbol)
        if not market_stats:
            logger.error(f"Could not fetch market stats for {symbol}")
            raise ValueError(f"Could not fetch market stats for {symbol}")

        current_price = market_stats['price']
        volume_24h = market_stats['volume']

        # Log market conditions
        logger.debug(f"Market conditions for {symbol}:")
        logger.debug(f"Current Price: ${current_price:.2f}")
        logger.debug(f"24h Volume: ${volume_24h:.2f}")
        logger.debug(f"24h Price Change: {market_stats['price_change']}%")

        # Check minimum volume requirement
        min_required_volume = MIN_24H_VOLUME.get(symbol, 100000)  # Default 100k USDT
        if volume_24h < min_required_volume:
            logger.warning(f"{symbol} 24h volume (${volume_24h:.2f}) below minimum requirement (${min_required_volume:.2f})")
            return

        # Log before fetching available USDT
        logger.info("Fetching available USDT...")
        available_usdt = self.get_available_usdt()  # Fetch available USDT
        logger.info(f"Available USDT: {available_usdt}")  # Log the available USDT

        # Check USDT balance
        logger.debug(f"Available USDT balance: ${available_usdt:.2f}")

        # Process trade based on conditions
        if self.should_buy(symbol, current_price):
            logger.debug(f"Buy conditions met for {symbol}")
            # Log the decision to buy
            logger.info(f"Buying {symbol} at {current_price}")
            quantity = self.calculate_position_size(
                available_usdt,
                current_price
            )
            if quantity:
                order = self.buy_asset_with_retry(symbol, quantity)
                if order:
                    logger.info(
                        f"Successfully bought {quantity} {symbol} at "
                        f"{current_price}"
                    )
                    self.send_telegram_message(
                        f"🟢 Bought {quantity} {symbol} at {current_price} USDT"
                    )
                else:
                    logger.error(f"Failed to buy {symbol} at {current_price}")
                    self.send_telegram_message(
                        f"❌ Failed to buy {symbol} at {current_price}"
                    )
        else:
            logger.debug(f"Buy conditions not met for {symbol}")
            logger.info(f"Conditions not favorable for buying {symbol}: "
                             f"Current price {current_price} is above the moving average.")

        balances = get_balances()
        asset_balance = float(balances.get(symbol.replace('USDT', ''), {}).get('free', 0.0))

        if asset_balance > 0:
            last_buy_price = get_last_buy_price(symbol)
            if last_buy_price:
                price_change = (current_price - last_buy_price) / last_buy_price
                logger.info(f"Price Change for {symbol}: {price_change * 100:.2f}%")
                if price_change >= SELL_THRESHOLD_PERCENTAGE:
                    # Log the decision to sell
                    logger.info(f"Selling {symbol} at {current_price}")
                    sell_order = self.sell_asset(symbol, asset_balance)
                    if sell_order:
                        logger.info(
                            f"Successfully sold {asset_balance} {symbol} at "
                            f"{current_price}"
                        )
                        self.send_telegram_message(
                            f"🔴 Sold {asset_balance} {symbol} at {current_price} USDT"
                        )
                    else:
                        logger.error(f"Failed to sell {symbol} at {current_price}")
                        self.send_telegram_message(
                            f"❌ Failed to sell {symbol} at {current_price}"
                        )

    except Exception as e:
        logger.error(f"Error processing {symbol}: {e}")
        self.handle_symbol_error(symbol, e)


def get_available_usdt(self):
    """Fetch the available USDT from the Binance account."""
    logger.info("Attempting to fetch available USDT...")  # Log when fetching starts
    try:
        balances = self.client.get_asset_balance(asset='USDT')
        available_balance = float(balances['free'])
        logger.info(f"Fetched USDT Balance: {available_balance}")  # Log fetched balance
        logger.debug(f"Available USDT balance: ${available_balance:.2f}")
        return available_balance
    except Exception as e:
        logger.error(f"Error fetching USDT balance: {e}")
        return 0.0


def should_buy(self, symbol, current_price):
    """Determine if the bot should buy the asset."""
    moving_average = self.get_moving_average(symbol)
    logger.info(f"Current Price: {current_price}, Moving Average: {moving_average}")

    # Buy if current price is significantly below moving average (1% buffer)
    if current_price < moving_average * 0.99:  # Allow for a 1% buffer
        return True
    else:
        logger.info(f"Conditions not favorable for buying {symbol}: "
                         f"Current price {current_price} is above the moving average.")
        return False
