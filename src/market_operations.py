import logging
from src.get_balances import get_balances
from src.save_transaction import save_transaction
from src.send_telegram_message import send_telegram_message


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


# Add this function to the TradingBot class
def get_market_stats(self, symbol):
    """Get 24-hour market statistics with proper error handling and retries"""
    try:
        # Get ticker using the client directly instead of relying on external function
        ticker = self.client.get_ticker(symbol=symbol)

        if not ticker:
            self.logger.error(f"Empty ticker data received for {symbol}")
            return None

        return {
            'symbol': symbol,
            'price': float(ticker['lastPrice']),
            'volume': float(ticker['volume']),
            'price_change_percent': float(ticker['priceChangePercent'])
        }
    except BinanceAPIException as e:
        self.logger.error(f"Binance API error getting market stats for {symbol}: {e}")
        return None
    except Exception as e:
        self.logger.error(f"Unexpected error getting market stats for {symbol}: {e}")
        return None

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
            # Calculate position size based on available USDT
            quantity = calculate_position_size(
                available_usdt,
                current_price,
                self.position_size_limit,
                MIN_POSITION_SIZE
            )

            if quantity:
                # Execute buy order
                order = self.buy_asset_with_retry(symbol, quantity)
                if order:
                    self.logger.info(f"Successfully bought {quantity} {symbol} at {current_price}")
                    send_telegram_message(f"🟢 Bought {quantity} {symbol} at {current_price} USDT")

        # Check if we should sell any existing positions
        balances = get_balances()
        asset_balance = float(balances.get(symbol.replace('USDT', ''), {}).get('free', 0.0))

        if asset_balance > 0:
            # Get the last buy price from database
            last_buy_price = get_last_buy_price(symbol)
            if last_buy_price:
                # Check if price has increased enough to sell
                price_change = (current_price - last_buy_price) / last_buy_price
                if price_change >= SELL_THRESHOLD_PERCENTAGE:
                    try:
                        sell_order = sell_asset(symbol, asset_balance)
                        if sell_order:
                            self.logger.info(f"Successfully sold {asset_balance} {symbol} at {current_price}")
                            send_telegram_message(f"🔴 Sold {asset_balance} {symbol} at {current_price} USDT")
                    except Exception as e:
                        self.logger.error(f"Error selling {symbol}: {e}")

    except Exception as e:
        self.logger.error(f"Error processing {symbol}: {e}")
        self.handle_symbol_error(symbol, e)
