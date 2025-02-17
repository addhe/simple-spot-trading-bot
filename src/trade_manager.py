from src.logger import logger
from src.get_balances import get_balances
from config.settings import TAKE_PROFIT, TRAILING_STOP
import pandas as pd

class TradeManager:
    def __init__(self, db_manager, client):
        self.db_manager = db_manager
        self.client = client
        self.logger = logger

    def should_buy(self, symbol, current_price):
        """Determine whether to buy based on technical analysis"""
        try:
            query = """
                SELECT timestamp, close_price, volume
                FROM historical_data
                WHERE symbol = ?
                ORDER BY timestamp DESC
                LIMIT 500
            """
            cursor = self.db_manager.execute_query(query, (symbol,))
            if not cursor:
                self.logger.error(f"Failed to get cursor for {symbol}")
                return False

            rows = cursor.fetchall()
            if not rows or len(rows) < 50:
                self.logger.debug(f"{symbol}: Not enough historical data for analysis (only {len(rows) if rows else 0} records)")
                return False

            # Convert to DataFrame
            df = pd.DataFrame(rows, columns=['timestamp', 'close_price', 'volume'])

            # Calculate basic indicators
            df['MA_50'] = df['close_price'].rolling(window=50).mean()
            df['MA_200'] = df['close_price'].rolling(window=200).mean()
            df['RSI'] = self._calculate_rsi(df['close_price'])

            # Calculate Bollinger Bands
            df['BB_upper'], df['BB_middle'], df['BB_lower'] = self._calculate_bollinger_bands(df['close_price'])

            # Calculate MACD
            df['MACD'], df['MACD_signal'] = self._calculate_macd(df['close_price'])
            df['MACD_hist'] = df['MACD'] - df['MACD_signal']

            latest = df.iloc[0]  # Most recent data point

            # Log all relevant indicators for debugging
            self.logger.debug(f"Technical Analysis for {symbol}:")
            self.logger.debug(f"Current Price: {current_price}")
            self.logger.debug(f"BB Lower: {latest['BB_lower']}")
            self.logger.debug(f"RSI: {latest['RSI']}")
            self.logger.debug(f"MA_50: {latest['MA_50']}")
            self.logger.debug(f"MA_200: {latest['MA_200']}")
            self.logger.debug(f"MACD: {latest['MACD']}")
            self.logger.debug(f"MACD Signal: {latest['MACD_signal']}")

            # Relaxed decision logic for buying
            # Buy if price is near BB lower band (within 1%) OR RSI is oversold
            bb_lower_threshold = latest['BB_lower'] * 1.01  # Allow price to be 1% above lower band
            rsi_oversold = 35  # Relaxed from 30 to 35

            if latest['close_price'] <= bb_lower_threshold:
                self.logger.debug(f"{symbol}: Price near or below BB lower band")
                if latest['RSI'] < rsi_oversold:
                    self.logger.debug(f"{symbol}: RSI below {rsi_oversold}, conditions met for buying")
                    return True
                else:
                    self.logger.debug(f"{symbol}: RSI not below {rsi_oversold}, checking MACD")
                    # Additional buy condition: MACD crossover
                    if latest['MACD'] > latest['MACD_signal']:
                        self.logger.debug(f"{symbol}: MACD above signal line, conditions met for buying")
                        return True
            else:
                self.logger.debug(f"{symbol}: Price not near BB lower band")

            # Alternative buy condition: Strong oversold on RSI
            if latest['RSI'] < 30:
                self.logger.debug(f"{symbol}: Strong oversold condition (RSI < 30), conditions met for buying")
                return True

            return False

        except Exception as e:
            self.logger.error(f"Error in should_buy for {symbol}: {e}")
            return False

    def process_trade(self, symbol, current_price, position_size=None):
        """Process a single trade with take profit and trailing stop"""
        try:
            # Get last buy price from database
            last_buy = self.db_manager.get_last_buy_price(symbol)

            # Get current position info
            if position_size and last_buy:
                # Update highest price if needed
                highest_price = self.db_manager.get_highest_price(symbol)
                if current_price > highest_price:
                    self.db_manager.update_highest_price(symbol, current_price)
                    highest_price = current_price

                # Check take profit and trailing stop
                if self.check_take_profit(symbol, current_price, last_buy):
                    return "SELL"
                if self.check_trailing_stop(symbol, current_price, highest_price):
                    return "SELL"
                return None

            # No position, check if we should buy
            elif not position_size and self.should_buy(symbol, current_price):
                return "BUY"

            return None

        except Exception as e:
            self.logger.error(f"Error processing trade for {symbol}: {e}")
            return None

    def _calculate_rsi(self, prices, period=14):
        """Calculate RSI indicator"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    def _calculate_bollinger_bands(self, prices, window=20, num_std=2):
        """Calculate Bollinger Bands"""
        rolling_mean = prices.rolling(window=window).mean()
        rolling_std = prices.rolling(window=window).std()
        upper_band = rolling_mean + (rolling_std * num_std)
        lower_band = rolling_mean - (rolling_std * num_std)
        return upper_band, rolling_mean, lower_band

    def _calculate_macd(self, prices, fast=12, slow=26, signal=9):
        """Calculate MACD"""
        exp1 = prices.ewm(span=fast, adjust=False).mean()
        exp2 = prices.ewm(span=slow, adjust=False).mean()
        macd = exp1 - exp2
        signal_line = macd.ewm(span=signal, adjust=False).mean()
        return macd, signal_line

    def check_take_profit(self, symbol, current_price, buy_price):
        """Check if we should take profit"""
        if not buy_price:
            return False

        profit_percentage = (current_price - buy_price) / buy_price
        take_profit_target = TAKE_PROFIT.get(symbol, 0.02)  # Default 2%

        if profit_percentage >= take_profit_target:
            self.logger.info(f"Take profit triggered for {symbol}. Profit: {profit_percentage:.2%}")
            return True

        return False

    def check_trailing_stop(self, symbol, current_price, highest_price):
        """Check if trailing stop is triggered"""
        if not highest_price:
            return False

        price_drop = (highest_price - current_price) / highest_price
        trailing_stop = TRAILING_STOP.get(symbol, 0.01)  # Default 1%

        if price_drop >= trailing_stop:
            self.logger.info(f"Trailing stop triggered for {symbol}. Drop: {price_drop:.2%}")
            return True

        return False

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
