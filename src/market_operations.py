import logging
from src.get_balances import get_balances
from src.save_transaction import save_transaction
from src.send_telegram_message import send_telegram_message
from datetime import datetime


def get_24h_stats(symbol):
    """
    Fetch 24-hour statistics for the given symbol from Binance.
    """
    # Implementation here
    pass


def get_last_price(symbol):
    """
    Fetch the last price for the given symbol from Binance.
    """
    # Implementation here
    pass

def process_symbol_trade(self, symbol, available_usdt):
    """Process trading logic for a symbol with proper error handling"""
    try:
        # Get market statistics
        market_stats = self.get_market_stats(symbol)
        if not market_stats:
            raise ValueError(f"Could not fetch market stats for {symbol}")

        current_price = market_stats['price']
        volume_24h = market_stats['volume']

        # Check minimum 24h volume requirement
        if volume_24h < MIN_24H_VOLUME:
            self.logger.info(f"24h volume too low for {symbol}: {volume_24h}")
            return

        # Check if we should buy based on technical analysis
        if self.should_buy(symbol, current_price):
            # Calculate position size based on available USDT and BUY_MULTIPLIER
            quantity = calculate_position_size(
                available_usdt * BUY_MULTIPLIER,
                current_price,
                self.position_size_limit,
                MIN_POSITION_SIZE
            )

            if quantity:
                # Execute buy order
                order = self.buy_asset_with_retry(symbol, quantity)
                if order:
                    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    self.logger.info(f"Successfully bought {quantity} {symbol} at {current_price}")
                    send_telegram_message(f"📊 *Trading Bot Status Report*\n⏰ *Timestamp*: {current_time}\n\n💰 *Portfolio Summary*: Bought {quantity} {symbol} at {current_price} USDT")
                else:
                    self.logger.error(f"Failed to buy {symbol} at {current_price}")
                    send_telegram_message(f"❌ Failed to buy {symbol} at {current_price}. Reason: {order}")

        # Check if we should sell any existing positions
        balances = get_balances()
        asset_balance = float(balances.get(symbol.replace('USDT', ''), {}).get('free', 0.0))

        if asset_balance > 0:
            # Get the last buy price from database
            last_buy_price = get_last_buy_price(symbol)
            if last_buy_price:
                # Check if price has increased enough to sell based on SELL_MULTIPLIER
                price_change = (current_price - last_buy_price) / last_buy_price
                if price_change >= SELL_THRESHOLD_PERCENTAGE * SELL_MULTIPLIER:
                    try:
                        sell_order = sell_asset(symbol, asset_balance)
                        if sell_order:
                            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            self.logger.info(f"Successfully sold {asset_balance} {symbol} at {current_price}")
                            send_telegram_message(f"📊 *Trading Bot Status Report*\n⏰ *Timestamp*: {current_time}\n\n💰 *Portfolio Summary*: Sold {asset_balance} {symbol} at {current_price} USDT")
                        else:
                            self.logger.error(f"Failed to sell {symbol} at {current_price}")
                            send_telegram_message(f"❌ Failed to sell {symbol} at {current_price}. Reason: {sell_order}")
                    except Exception as e:
                        self.logger.error(f"Error selling {symbol}: {e}")
                        send_telegram_message(f"❌ Failed to sell {symbol} at {current_price}. Reason: {e}")

    except Exception as e:
        self.logger.error(f"Error processing {symbol}: {e}")
        self.handle_symbol_error(symbol, e)
