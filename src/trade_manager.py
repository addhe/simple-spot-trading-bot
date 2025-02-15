from src.logger import logger
from src.get_balances import get_balances
from config.settings import TAKE_PROFIT, TRAILING_STOP

class TradeManager:
    def __init__(self, db_manager, client):
        self.db_manager = db_manager
        self.client = client
        self.logger = logger

    def check_take_profit(self, symbol, current_price, buy_price):
        """Check if we should take profit based on current price and buy price"""
        if not buy_price:
            return False

        profit_percentage = (current_price - buy_price) / buy_price
        take_profit_target = TAKE_PROFIT.get(symbol, 0.02)  # Default 2%

        if profit_percentage >= take_profit_target:
            self.logger.info(f"Take profit triggered for {symbol}. Profit: {profit_percentage:.2%}")
            return True

        return False

    def check_trailing_stop(self, symbol, current_price, highest_price):
        """Check if trailing stop loss is triggered"""
        if not highest_price:
            return False

        price_drop = (highest_price - current_price) / highest_price
        trailing_stop = TRAILING_STOP.get(symbol, 0.01)  # Default 1%

        if price_drop >= trailing_stop:
            self.logger.info(f"Trailing stop triggered for {symbol}. Drop: {price_drop:.2%}")
            return True

        return False

    def process_trade(self, symbol, current_price, position_size=None):
        """Process a single trade with take profit and trailing stop"""
        try:
            # Get last buy price from database
            last_buy = self.db_manager.get_last_buy_price(symbol)

            # If we have a position
            if position_size:
                # Update highest price if needed
                highest_price = self.db_manager.get_highest_price(symbol)
                if current_price > highest_price:
                    self.db_manager.update_highest_price(symbol, current_price)

                # Check take profit and trailing stop
                should_take_profit = self.check_take_profit(symbol, current_price, last_buy)
                should_trail_stop = self.check_trailing_stop(symbol, current_price, highest_price)

                if should_take_profit or should_trail_stop:
                    return 'SELL', position_size

            return None, None

        except Exception as e:
            self.logger.error(f"Error processing trade for {symbol}: {e}")
            return None, None

    def execute_sell(self, symbol, quantity):
        """Execute a sell order"""
        try:
            order = self.client.create_order(
                symbol=symbol,
                side='SELL',
                type='MARKET',
                quantity=quantity
            )

            if order['status'] == 'FILLED':
                price = float(order['fills'][0]['price'])
                self.db_manager.save_transaction(symbol, 'SELL', quantity, price)
                self.logger.info(f"Successfully sold {quantity} {symbol} at {price}")
                # Reset highest price after successful sell
                self.db_manager.update_highest_price(symbol, 0)
                return True
            return False

        except Exception as e:
            self.logger.error(f"Error executing sell for {symbol}: {e}")
            return False

    def execute_buy(self, symbol, quantity):
        """Execute a buy order"""
        try:
            order = self.client.create_order(
                symbol=symbol,
                side='BUY',
                type='MARKET',
                quantity=quantity
            )

            if order['status'] == 'FILLED':
                price = float(order['fills'][0]['price'])
                self.db_manager.save_transaction(symbol, 'BUY', quantity, price)
                self.logger.info(f"Successfully bought {quantity} {symbol} at {price}")
                # Initialize highest price after buy
                self.db_manager.update_highest_price(symbol, price)
                return True
            return False

        except Exception as e:
            self.logger.error(f"Error executing buy for {symbol}: {e}")
            return False
