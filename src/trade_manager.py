from src.logger import logger
from src.get_balances import get_balances
from config.settings import TAKE_PROFIT, TRAILING_STOP, MIN_NOTIONAL_VALUE
import pandas as pd

class TradeManager:
    def __init__(self, db_manager, client):
        """Initialize TradeManager with database and client"""
        self.db_manager = db_manager
        self.client = client
        self.logger = logger
        self.db_manager.initialize_database()

    def should_buy(self, symbol, current_price):
        """Determine whether to buy based on technical analysis"""
        try:
            # Get historical data from database
            rows = self.db_manager.get_historical_data(symbol, limit=500)
            if not rows or len(rows) < 50:
                self.logger.debug(f"{symbol}: Not enough historical data for analysis (only {len(rows) if rows else 0} records)")
                return False

            # Convert to DataFrame
            df = pd.DataFrame(rows, columns=['timestamp', 'close_price', 'volume'])
            df = df.sort_values('timestamp', ascending=True).reset_index(drop=True)

            # Calculate basic indicators
            df['MA_50'] = df['close_price'].rolling(window=50).mean()
            df['MA_200'] = df['close_price'].rolling(window=200).mean()
            df['RSI'] = self._calculate_rsi(df['close_price'])

            # Calculate Bollinger Bands
            df['BB_upper'], df['BB_middle'], df['BB_lower'] = self._calculate_bollinger_bands(df['close_price'])

            # Calculate MACD
            df['MACD'], df['MACD_signal'] = self._calculate_macd(df['close_price'])
            df['MACD_hist'] = df['MACD'] - df['MACD_signal']

            # Get the latest data point and previous point
            latest = df.iloc[-1]  # Most recent data point
            previous = df.iloc[-2] if len(df) > 1 else latest  # Previous data point

            # Log all relevant indicators for debugging
            self.logger.debug(f"Technical Analysis for {symbol}:")
            self.logger.debug(f"Current Price: ${current_price:.2f}")
            self.logger.debug(f"BB Lower: ${latest['BB_lower']:.2f}")
            self.logger.debug(f"RSI: {latest['RSI']:.2f}")
            self.logger.debug(f"MA_50: ${latest['MA_50']:.2f}")
            self.logger.debug(f"MA_200: ${latest['MA_200']:.2f}")
            self.logger.debug(f"MACD Hist: {latest['MACD_hist']:.4f}")

            # More lenient buy conditions
            buy_signals = 0
            required_signals = 2  # Need at least 2 signals to buy

            # 1. Price near Bollinger Band lower (weight: 2)
            bb_lower_threshold = latest['BB_lower'] * 1.02  # Allow price to be 2% above lower band
            if current_price <= bb_lower_threshold:
                buy_signals += 2
                self.logger.debug(f" Price near/below BB lower (${current_price:.2f} <= ${bb_lower_threshold:.2f})")
            else:
                self.logger.debug(f" Price above BB lower (${current_price:.2f} > ${bb_lower_threshold:.2f})")

            # 2. RSI conditions (weight: 2)
            rsi_oversold = 40  # More lenient RSI threshold
            if latest['RSI'] < rsi_oversold:
                buy_signals += 2
                self.logger.debug(f" RSI oversold ({latest['RSI']:.2f} < {rsi_oversold})")
            else:
                self.logger.debug(f" RSI not oversold ({latest['RSI']:.2f} >= {rsi_oversold})")

            # 3. MACD momentum (weight: 1)
            if latest['MACD_hist'] > previous['MACD_hist']:
                buy_signals += 1
                self.logger.debug(" MACD momentum is positive")
            else:
                self.logger.debug(" MACD momentum is negative")

            # 4. Moving Average alignment (weight: 1)
            if current_price > latest['MA_200'] and current_price < latest['MA_50']:
                buy_signals += 1
                self.logger.debug(f" Price between MA200 and MA50")
            else:
                self.logger.debug(f" Price not between MA200 and MA50")

            should_buy = buy_signals >= required_signals
            self.logger.info(f"{symbol} Buy Decision: {should_buy} (Signals: {buy_signals}/{required_signals})")
            return should_buy

        except Exception as e:
            self.logger.error(f"Error in should_buy for {symbol}: {e}")
            return False

    def process_trade(self, symbol, current_price):
        """Process a single trade with take profit and trailing stop"""
        try:
            # Get last buy price and current position
            last_buy_price = self.db_manager.get_last_buy_price(symbol)

            # Check if we have an open position
            if last_buy_price:
                # Get highest price since buy
                highest_price = self.db_manager.get_highest_price(symbol)

                # Update highest price if current price is higher
                if current_price > highest_price:
                    self.db_manager.update_highest_price(symbol, current_price)
                    highest_price = current_price

                # Get available balance before checking sell conditions
                balances = get_balances(self.client)
                base_asset = symbol.replace('USDT', '')
                available_balance = float(balances.get(base_asset, {}).get('free', 0))

                # Get symbol info for minimum quantity
                symbol_info = self.client.get_symbol_info(symbol)
                min_qty = float(next((f['minQty'] for f in symbol_info['filters'] if f['filterType'] == 'LOT_SIZE'), 0.001))

                # Only proceed with sell checks if we have sufficient quantity
                if available_balance >= min_qty:
                    # Check take profit and trailing stop
                    if self.check_take_profit(symbol, current_price, last_buy_price):
                        self.logger.info(f"Take profit triggered for {symbol}")
                        return "SELL"

                    if self.check_trailing_stop(symbol, current_price, highest_price):
                        self.logger.info(f"Trailing stop triggered for {symbol}")
                        return "SELL"

                    self.logger.debug(f"Holding {symbol} position. Entry: {last_buy_price}, Current: {current_price}, Highest: {highest_price}")
                else:
                    self.logger.info(f"Insufficient quantity to sell {symbol}. Available: {available_balance}, Minimum: {min_qty}")
                return None

            # No position, check if we should buy
            if self.should_buy(symbol, current_price):
                # Check if we can meet minimum notional value
                symbol_info = self.client.get_symbol_info(symbol)
                min_notional = float(next((f['minNotional'] for f in symbol_info['filters'] if f['filterType'] == 'MIN_NOTIONAL'), 10))

                # Check USDT balance
                balances = get_balances(self.client)
                usdt_balance = float(balances.get('USDT', {}).get('free', 0))

                # Only signal buy if we can meet minimum notional
                if usdt_balance >= min_notional:
                    self.logger.info(f"Buy signal for {symbol} at {current_price}")
                    return "BUY"
                else:
                    self.logger.info(f"Insufficient USDT for minimum notional. Required: {min_notional}, Available: {usdt_balance}")

            return None

        except Exception as e:
            self.logger.error(f"Error processing trade for {symbol}: {e}")
            return None

    def _calculate_rsi(self, prices, period=14):
        """Calculate RSI technical indicator"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    def _calculate_bollinger_bands(self, prices, period=20, num_std=2):
        """Calculate Bollinger Bands"""
        middle_band = prices.rolling(window=period).mean()
        std_dev = prices.rolling(window=period).std()
        upper_band = middle_band + (std_dev * num_std)
        lower_band = middle_band - (std_dev * num_std)
        return upper_band, middle_band, lower_band

    def _calculate_macd(self, prices, fast=12, slow=26, signal=9):
        """Calculate MACD indicator"""
        try:
            # Convert to float if needed
            prices = prices.astype(float)

            # Calculate MACD
            exp1 = prices.ewm(span=fast, adjust=False).mean()
            exp2 = prices.ewm(span=slow, adjust=False).mean()
            macd = exp1 - exp2
            signal_line = macd.ewm(span=signal, adjust=False).mean()

            # Handle NaN values
            macd = macd.fillna(0)
            signal_line = signal_line.fillna(0)

            return macd, signal_line
        except Exception as e:
            self.logger.error(f"Error calculating MACD: {e}")
            # Return zeros with same length as input
            return pd.Series([0] * len(prices)), pd.Series([0] * len(prices))

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
            # Get symbol info for precision
            symbol_info = self.client.get_symbol_info(symbol)
            if not symbol_info:
                self.logger.error(f"Could not get symbol info for {symbol}")
                return False

            # Get lot size filter
            lot_size_filter = next((f for f in symbol_info['filters'] if f['filterType'] == 'LOT_SIZE'), None)
            if lot_size_filter:
                min_qty = float(lot_size_filter['minQty'])
                step_size = float(lot_size_filter['stepSize'])
                self.logger.info(f"{symbol} - Min Qty: {min_qty}, Step Size: {step_size}")

                # Round quantity to valid step size
                quantity = round(quantity - (quantity % step_size), len(str(step_size).split('.')[1]))
                if quantity < min_qty:
                    self.logger.error(f"Quantity {quantity} is below minimum {min_qty} for {symbol}")
                    return False

            # Check if we have enough balance
            balances = get_balances(self.client)
            asset = symbol.replace('USDT', '')
            available_balance = float(balances.get(asset, {}).get('free', 0))

            if available_balance < quantity:
                self.logger.error(f"Insufficient balance. Required: {quantity} {asset}, Available: {available_balance} {asset}")
                return False

            # Get current price and calculate notional value
            current_price = float(self.client.get_symbol_ticker(symbol=symbol)['price'])
            total_notional = quantity * current_price
            self.logger.info(f"Attempting to sell {quantity} {symbol} at {current_price}, Total Notional: {total_notional}")

            # Check minimum notional
            min_notional_value = float(next((f['minNotional'] for f in symbol_info['filters'] if f['filterType'] == 'MIN_NOTIONAL'), 10))
            self.logger.info(f"Minimum notional value for {symbol}: {min_notional_value}")

            if total_notional < min_notional_value:
                # Try to sell entire balance if available
                if available_balance > quantity:
                    adjusted_quantity = available_balance
                    total_notional = adjusted_quantity * current_price
                    if total_notional >= min_notional_value:
                        self.logger.info(f"Adjusting quantity from {quantity} to {adjusted_quantity} to meet minimum notional")
                        quantity = adjusted_quantity
                    else:
                        self.logger.error(f"Even full balance ({available_balance}) doesn't meet minimum notional")
                        return False
                else:
                    self.logger.error(f"Order value {total_notional} is below minimum {min_notional_value} USDT")
                    return False

            # Create the order
            self.logger.info(f"Creating market sell order: {symbol}, quantity: {quantity}")
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
            self.logger.error(f"Error executing sell for {symbol}: {str(e)}")
            return False

    def execute_buy(self, symbol, quantity):
        """Execute a buy order"""
        try:
            # Get symbol info for precision
            symbol_info = self.client.get_symbol_info(symbol)
            if not symbol_info:
                self.logger.error(f"Could not get symbol info for {symbol}")
                return False

            # Get lot size filter
            lot_size_filter = next((f for f in symbol_info['filters'] if f['filterType'] == 'LOT_SIZE'), None)
            if lot_size_filter:
                min_qty = float(lot_size_filter['minQty'])
                step_size = float(lot_size_filter['stepSize'])
                self.logger.info(f"{symbol} - Min Qty: {min_qty}, Step Size: {step_size}")

                # Round quantity to valid step size
                quantity = round(quantity - (quantity % step_size), len(str(step_size).split('.')[1]))
                if quantity < min_qty:
                    self.logger.error(f"Quantity {quantity} is below minimum {min_qty} for {symbol}")
                    return False

            # Get current price and calculate notional value
            current_price = float(self.client.get_symbol_ticker(symbol=symbol)['price'])
            total_notional = quantity * current_price
            self.logger.info(f"Attempting to buy {quantity} {symbol} at {current_price}, Total Notional: {total_notional}")

            # Check minimum notional
            min_notional_value = float(next((f['minNotional'] for f in symbol_info['filters'] if f['filterType'] == 'MIN_NOTIONAL'), 10))
            self.logger.info(f"Minimum notional value for {symbol}: {min_notional_value}")

            if total_notional < min_notional_value:
                # Try to adjust quantity to meet minimum notional
                adjusted_quantity = (min_notional_value + 0.1) / current_price  # Add small buffer
                adjusted_quantity = round(adjusted_quantity - (adjusted_quantity % step_size), len(str(step_size).split('.')[1]))
                if adjusted_quantity >= min_qty:
                    self.logger.info(f"Adjusting quantity from {quantity} to {adjusted_quantity} to meet minimum notional")
                    quantity = adjusted_quantity
                else:
                    self.logger.error(f"Cannot adjust quantity to meet minimum notional while maintaining minimum quantity")
                    return False

            # Create the order
            self.logger.info(f"Creating market buy order: {symbol}, quantity: {quantity}")
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
            self.logger.error(f"Error executing buy for {symbol}: {str(e)}")
            return False
