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

def process_symbol_trade(self, symbol):
    """Process trading logic for a symbol with error handling."""
    try:
        market_stats = self.get_market_stats(symbol)
        if not market_stats:
            raise ValueError(f"Could not fetch market stats for {symbol}")

        current_price = market_stats['price']
        volume_24h = market_stats['volume']

        if volume_24h < MIN_24H_VOLUME:
            self.logger.info(
                f"24h volume too low for {symbol}: {volume_24h}"
            )
            return

        # Update the logic to fetch the correct available USDT from the Binance API
        available_usdt = self.get_available_usdt()  # Fetch available USDT
        self.logger.info(f"Available USDT: {available_usdt}")  # Debugging line

        if self.should_buy(symbol, current_price):
            quantity = self.calculate_position_size(
                available_usdt,
                current_price
            )
            if quantity:
                order = self.buy_asset_with_retry(symbol, quantity)
                if order:
                    self.logger.info(
                        f"Successfully bought {quantity} {symbol} at "
                        f"{current_price}"
                    )
                    self.send_telegram_message(
                        f"🟢 Bought {quantity} {symbol} at {current_price} USDT"
                    )
                else:
                    self.logger.error(f"Failed to buy {symbol} at {current_price}")
                    self.send_telegram_message(
                        f"❌ Failed to buy {symbol} at {current_price}"
                    )

        balances = get_balances()
        asset_balance = float(balances.get(symbol.replace('USDT', ''), {}).get('free', 0.0))

        if asset_balance > 0:
            last_buy_price = get_last_buy_price(symbol)
            if last_buy_price:
                price_change = (current_price - last_buy_price) / last_buy_price
                if price_change >= SELL_THRESHOLD_PERCENTAGE:
                    sell_order = self.sell_asset(symbol, asset_balance)
                    if sell_order:
                        self.logger.info(
                            f"Successfully sold {asset_balance} {symbol} at "
                            f"{current_price}"
                        )
                        self.send_telegram_message(
                            f"🔴 Sold {asset_balance} {symbol} at {current_price} USDT"
                        )
                    else:
                        self.logger.error(f"Failed to sell {symbol} at {current_price}")
                        self.send_telegram_message(
                            f"❌ Failed to sell {symbol} at {current_price}"
                        )

    except Exception as e:
        self.logger.error(f"Error processing {symbol}: {e}")
        self.handle_symbol_error(symbol, e)


def get_available_usdt(self):
    """Fetch the available USDT from the Binance account."""
    try:
        balances = self.client.get_asset_balance(asset='USDT')
        available_balance = float(balances['free'])
        self.logger.info(f"Fetched USDT Balance: {available_balance}")  # Log fetched balance
        return available_balance
    except Exception as e:
        self.logger.error(f"Error fetching USDT balance: {e}")
        return 0.0
