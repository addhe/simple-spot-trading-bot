import ccxt
import os
import logging
import time
import pandas as pd
import numpy as np
import json
import signal
import sys
import traceback

from logging.handlers import RotatingFileHandler
from datetime import datetime

from config.config import CONFIG
from src.modules.send_telegram_notification import send_telegram_notification

# Initialize logging with a rotating file handler
log_handler = RotatingFileHandler('trade_log_spot.log', maxBytes=5*1024*1024, backupCount=2)
logging.basicConfig(handlers=[log_handler], level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

# API Configuration
API_KEY = os.environ.get('API_KEY_SPOT_BINANCE')
API_SECRET = os.environ.get('API_SECRET_SPOT_BINANCE')

if API_KEY is None or API_SECRET is None:
    error_message = 'API credentials not found in environment variables'
    logging.error(error_message)
    send_telegram_notification(error_message)
    exit(1)

def check_for_config_updates(last_checked_time):
    logging.info("Configuration updates are managed through code changes.")
    return False, last_checked_time

def handle_exit_signal(signal_number, frame):
    logging.info("Received exit signal, shutting down gracefully...")
    # Perform any cleanup operations here
    sys.exit(0)

signal.signal(signal.SIGTERM, handle_exit_signal)
signal.signal(signal.SIGINT, handle_exit_signal)

class TradeExecution:
    def __init__(self, exchange, performance, trade_history):
        self.exchange = exchange
        self.performance = performance
        self.trade_history = trade_history
        self.market_data = None

    def handle_trade_error(self, error, retry_count=3):
        """Enhanced error handling for 24/7 operation"""
        try:
            for i in range(retry_count):
                try:
                    # Log error details
                    logging.error(f"Trade error (attempt {i+1}/{retry_count}): {str(error)}")

                    # Check if error is critical
                    if any(critical in str(error).lower() for critical in [
                        'insufficient balance',
                        'api key',
                        'permission denied',
                        'margin'
                    ]):
                        logging.critical(f"Critical error detected: {str(error)}")
                        self.send_notification(f"Critical Trading Error: {str(error)}")
                        return False

                    # Exponential backoff
                    wait_time = 2 ** i
                    logging.info(f"Waiting {wait_time} seconds before retry...")
                    time.sleep(wait_time)

                    # Check exchange connection
                    if self.check_exchange_connection():
                        logging.info("Exchange connection restored")
                        return True

                except Exception as e:
                    logging.error(f"Error in retry attempt {i+1}: {str(e)}")

            # If all retries failed
            self.send_notification("Maximum retry attempts reached, manual intervention may be required")
            return False

        except Exception as e:
            logging.error(f"Error in error handler: {str(e)}")
            return False

    def check_exchange_connection(self):
        try:
            self.exchange.fetch_ticker(CONFIG['symbol'])
            return True
        except Exception as e:
            logging.error(f"Exchange connection error: {e}")
            return False

    def get_account_value(self):
        """Get total account value in USDT"""
        try:
            balance = safe_api_call(self.exchange.fetch_balance)
            if balance is None:
                return 0

            total_value = 0
            for currency in ['ETH', 'USDT']:
                if currency in balance:
                    if currency == 'USDT':
                        total_value += balance[currency]['total']
                    else:
                        # Get current price for the asset
                        ticker = safe_api_call(self.exchange.fetch_ticker, f'{currency}/USDT')
                        if ticker:
                            total_value += balance[currency]['total'] * ticker['last']

            return total_value

        except Exception as e:
            logging.error(f"Error getting account value: {str(e)}")
            return 0

    def validate_position_parameters(self, position_size, current_price, market_data):
        """Validate position parameters against multiple criteria"""
        try:
            # Calculate notional value
            notional_value = position_size * current_price

            # Volume-based validation
            avg_volume = market_data['volume'].rolling(
                window=CONFIG['volume_ma_length']
            ).mean().iloc[-1]
            volume_ratio = notional_value / (avg_volume * current_price)

            if volume_ratio > CONFIG['volume_impact_threshold']:
                logging.warning(f"Position size too large relative to volume: {volume_ratio:.2%}")
                return False

            # Risk-based validation
            account_value = self.get_account_value()
            position_risk = (notional_value * CONFIG['stop_loss_percent']) / account_value

            if position_risk > CONFIG['max_single_trade_risk']:
                logging.warning(f"Position risk too high: {position_risk:.2%}")
                return False

            # Trend-based validation
            trend_strength = self.calculate_trend_strength(market_data)
            if trend_strength < CONFIG['trend_strength_threshold']:
                logging.warning(f"Trend strength too weak: {trend_strength:.4f}")
                return False

            logging.info(f"""
            Position Validation:
            Volume Ratio: {volume_ratio:.2%}
            Position Risk: {position_risk:.2%}
            Trend Strength: {trend_strength:.4f}
            """)

            return True

        except Exception as e:
            logging.error(f"Error validating position parameters: {str(e)}")
            return False

    def log_market_summary(self, market_data):
        """Log detailed market summary"""
        try:
            current_price = market_data['close'].iloc[-1]

            # Calculate key metrics
            rsi = self.analyze_price_trend(market_data)['rsi']
            volatility = self.calculate_volatility()
            trend_strength = self.calculate_trend_strength(market_data)

            summary = f"""
    === Market Summary ===
    Symbol: {CONFIG['symbol']}
    Current Price: {current_price:.2f} USDT
    RSI: {rsi:.2f}
    Volatility: {volatility:.4%}
    Trend Strength: {trend_strength:.4f}
    Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    ===================
            """
            logging.info(summary)

        except Exception as e:
            logging.error(f"Error logging market summary: {str(e)}")

    def report_balance_to_telegram(self):
        try:
            balance = safe_api_call(self.exchange.fetch_balance)
            if balance is None:
                logging.error("Failed to fetch balance")
                return

            message = "Current Balances:\n"
            for currency in ['ETH', 'USDT']:
                if currency in balance and balance[currency]['total'] > 0:
                    total = balance[currency]['total']
                    free = balance[currency]['free']
                    used = balance[currency]['used']
                    message += f"{currency}:\n"
                    message += f"  Total: {total:.8f}\n"
                    message += f"  Free: {free:.8f}\n"
                    message += f"  In Use: {used:.8f}\n"

            send_telegram_notification(message)

        except Exception as e:
            logging.error(f"Error reporting balance to Telegram: {str(e)}")
            send_telegram_notification(f"Failed to report balance: {str(e)}")

    def can_trade_time_based(self):
        """Enhanced 24/7 trading time validation"""
        try:
            now = datetime.now()

            # Check minimum trade interval
            if self.trade_history:
                last_trade = max(
                    (trade for trades in self.trade_history.values() for trade in trades),
                    key=lambda x: x['timestamp']
                )
                last_trade_time = datetime.fromisoformat(last_trade['timestamp'])
                time_since_last_trade = (now - last_trade_time).total_seconds()

                if time_since_last_trade < CONFIG['min_trade_interval']:
                    logging.debug(f"Minimum trade interval not met. Waiting {CONFIG['min_trade_interval'] - time_since_last_trade}s")
                    return False

            # Check daily trade limits and profit target
            today_trades = [
                trade for trades in self.trade_history.values()
                for trade in trades
                if trade['timestamp'].startswith(now.strftime('%Y-%m-%d'))
            ]

            # Check daily trade count
            if len(today_trades) >= CONFIG['max_daily_trades']:
                logging.info("Daily trade limit reached")
                return False

            # Calculate daily profit
            today_profit = sum(trade.get('profit', 0) for trade in today_trades)
            daily_profit_target = self.get_account_value() * (CONFIG['daily_profit_target'] / 100)

            if today_profit >= daily_profit_target:
                logging.info(f"Daily profit target reached: {today_profit:.2f} USDT")
                # Send notification for reaching daily target
                self.send_notification(f"Daily profit target reached: {today_profit:.2f} USDT")
                return False

            # Add consecutive loss protection
            recent_trades = today_trades[-CONFIG['max_consecutive_losses']:]
            consecutive_losses = sum(1 for trade in recent_trades if trade.get('profit', 0) < 0)

            if consecutive_losses >= CONFIG['max_consecutive_losses']:
                logging.warning(f"Maximum consecutive losses reached: {consecutive_losses}")
                self.send_notification("Trading paused due to consecutive losses")
                return False

            return True

        except Exception as e:
            logging.error(f"Error checking time-based restrictions: {str(e)}")
            return False

    def monitor_performance(self):
        """Enhanced 24/7 performance monitoring"""
        try:
            # Calculate daily metrics
            today = datetime.now().strftime('%Y-%m-%d')
            today_trades = [
                trade for trade in self.performance.metrics['trade_history']
                if trade['timestamp'].startswith(today)
            ]

            # Daily statistics
            total_trades = len(today_trades)
            winning_trades = sum(1 for trade in today_trades if trade.get('profit', 0) > 0)
            total_profit = sum(trade.get('profit', 0) for trade in today_trades)

            # Calculate win rate and average profit
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
            avg_profit = total_profit / total_trades if total_trades > 0 else 0

            # Log performance metrics
            performance_msg = f"""
            === Daily Performance Update ===
            Total Trades: {total_trades}
            Win Rate: {win_rate:.2f}%
            Total Profit: {total_profit:.2f} USDT
            Average Profit per Trade: {avg_profit:.2f} USDT
            ==============================
            """
            logging.info(performance_msg)

            # Send periodic performance update
            if datetime.now().hour in [0, 8, 16]:  # Send updates every 8 hours
                self.send_notification(performance_msg)

            # Check for warning conditions
            if win_rate < 40 and total_trades >= 5:
                warning_msg = f"Warning: Low win rate ({win_rate:.2f}%) over {total_trades} trades"
                logging.warning(warning_msg)
                self.send_notification(warning_msg)

            if total_profit < 0 and abs(total_profit) > CONFIG['max_daily_loss_percent']:
                warning_msg = f"Warning: Approaching daily loss limit. Current loss: {abs(total_profit):.2f} USDT"
                logging.warning(warning_msg)
                self.send_notification(warning_msg)

            return win_rate, total_profit

        except Exception as e:
            logging.error(f"Error monitoring performance: {str(e)}")
            return None, None

    def validate_entry_conditions(self, market_data, amount_to_trade):
        """Validate entry conditions before trade execution"""
        try:
            # Add current price validation
            if 'close' not in market_data.columns:
                logging.error("Missing close price data")
                return False

            current_price = market_data['close'].iloc[-1]
            if current_price <= 0:
                logging.error("Invalid current price")
                return False

            # Calculate average volume with error handling
            try:
                avg_volume = market_data['volume'].rolling(window=20).mean().iloc[-1]
            except Exception as e:
                logging.error(f"Error calculating average volume: {str(e)}")
                return False

            # Calculate market impact with safeguards
            try:
                market_impact = (amount_to_trade * current_price) / (avg_volume * current_price)
                logging.info(f"Market impact: {market_impact:.4%}")

                if market_impact > CONFIG['market_impact_threshold']:
                    logging.warning(f"Market impact too high: {market_impact:.4%}")
                    return False
            except ZeroDivisionError:
                logging.error("Zero average volume detected")
                return False

            # Enhanced liquidity check
            try:
                liquidity_ratio = amount_to_trade / avg_volume
                logging.info(f"Liquidity ratio: {liquidity_ratio:.4%}")

                if liquidity_ratio > CONFIG['min_liquidity_ratio']:
                    logging.warning(f"Order size too large compared to average volume. Ratio: {liquidity_ratio:.4%}")
                    return False
            except ZeroDivisionError:
                logging.error("Zero average volume in liquidity check")
                return False

            # Enhanced consecutive losses check with safeguards
            try:
                if CONFIG['symbol'] not in self.trade_history:
                    recent_trades = []
                else:
                    recent_trades = self.trade_history[CONFIG['symbol']][-CONFIG['max_consecutive_losses']:]

                consecutive_losses = sum(1 for trade in recent_trades if trade.get('profit', 0) < 0)

                if consecutive_losses >= CONFIG['max_consecutive_losses']:
                    logging.warning(f"Maximum consecutive losses reached: {consecutive_losses}")
                    return False

                logging.info(f"Current consecutive losses: {consecutive_losses}")
            except Exception as e:
                logging.error(f"Error checking consecutive losses: {str(e)}")
                return False

            # Additional validation checks
            if not self.validate_time_window():
                return False

            if not self.validate_market_volatility(market_data):
                return False

            logging.info("All entry conditions validated successfully")
            return True

        except Exception as e:
            logging.error(f"Error validating entry conditions: {str(e)}")
            return False

    def validate_time_window(self):
        """Validate if enough time has passed since last trade"""
        try:
            if not self.trade_history.get(CONFIG['symbol']):
                return True

            last_trade = self.trade_history[CONFIG['symbol']][-1]
            last_trade_time = datetime.fromisoformat(last_trade['timestamp'])
            time_since_last_trade = (datetime.now() - last_trade_time).total_seconds()

            if time_since_last_trade < CONFIG['min_trade_interval']:
                logging.info(f"Minimum trade interval not met. Time since last trade: {time_since_last_trade}s")
                return False

            return True
        except Exception as e:
            logging.error(f"Error validating time window: {str(e)}")
            return False

    def validate_market_volatility(self, market_data):
        """Validate if market volatility is within acceptable range"""
        try:
            # Calculate current volatility
            volatility = self.calculate_volatility(market_data)
            if volatility is None:
                return False

            logging.info(f"Current market volatility: {volatility:.4%}")

            # Check against thresholds
            if volatility > CONFIG['high_volatility_threshold']:
                logging.warning(f"Volatility too high: {volatility:.4%}")
                return False

            if volatility < CONFIG['low_volatility_threshold']:
                logging.warning(f"Volatility too low: {volatility:.4%}")
                return False

            return True
        except Exception as e:
            logging.error(f"Error validating market volatility: {str(e)}")
            return False

    def setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown"""
        try:
            def handle_shutdown(signum, frame):
                logging.info(f"Received signal {signum}, initiating graceful shutdown")
                self.cleanup()
                sys.exit(0)

            # Remove global handlers
            signal.signal(signal.SIGTERM, handle_shutdown)
            signal.signal(signal.SIGINT, handle_shutdown)
            logging.info("Signal handlers setup completed")
        except Exception as e:
            logging.error(f"Error setting up signal handlers: {str(e)}")

    def handle_shutdown(self, signum, frame):
        """Handle shutdown signals"""
        logging.info(f"Received signal {signum}, initiating graceful shutdown")
        self.cleanup()
        sys.exit(0)

    def has_open_positions(self, symbol):
        """Check if there are open positions for the symbol"""
        try:
            balance = safe_api_call(self.exchange.fetch_balance)
            if balance is None:
                return False

            base_currency = symbol.split('/')[0]
            position_size = balance[base_currency]['free']

            return position_size > 0
        except Exception as e:
            logging.error(f"Error checking open positions: {str(e)}")
            return False

    def check_daily_profit_target(self):
        """Check if daily profit target is reached"""
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            today_trades = [
                trade for trade in self.performance.metrics['trade_history']
                if trade['timestamp'].startswith(today)
            ]

            daily_profit = sum(trade['profit'] for trade in today_trades)
            daily_profit_percent = (daily_profit / self.performance.metrics['total_profit']) * 100

            if daily_profit_percent >= CONFIG['daily_profit_target']:
                logging.info(f"Daily profit target reached: {daily_profit_percent:.2f}%")
                return True

            return False

        except Exception as e:
            logging.error(f"Error checking daily profit target: {str(e)}")
            return False

    def check_technical_exit_signals(self, market_data):
        """Check technical indicators for exit signals"""
        try:
            # Get latest technical analysis
            analysis = self.perform_technical_analysis(market_data)
            if analysis is None:
                return False

            trend = analysis['trend_analysis']

            # Exit conditions
            exit_signals = (
                trend['rsi'] > CONFIG['rsi_overbought'] or
                trend['adx'] < CONFIG['adx_threshold'] or
                trend['momentum'] < 0 or
                trend['trend_strength'] < CONFIG['trend_strength_threshold']
            )

            return exit_signals

        except Exception as e:
            logging.error(f"Error checking technical exit signals: {str(e)}")
            return False

    def should_exit_position(self, position, current_price, market_data):
        """Determine if position should be exited"""
        try:
            # Stop loss hit
            if current_price <= position['current_stop']:
                logging.info("Stop loss triggered")
                return True

            # Take profit hit
            if current_price >= position['take_profit']:
                logging.info("Take profit target reached")
                return True

            # Technical exit signals
            if self.check_technical_exit_signals(market_data):
                logging.info("Technical exit signal triggered")
                return True

            return False

        except Exception as e:
            logging.error(f"Error checking exit conditions: {str(e)}")
            return False

    def manage_existing_positions(self, symbol, current_price, market_data):
        """Enhanced position management"""
        try:
            # Get position details
            position = self.get_position_entry(symbol)
            if position is None:
                return

            # Check position duration
            position_age = (datetime.now() - position['entry_time']).total_seconds()
            if position_age > CONFIG['position_max_duration']:
                logging.info("Position exceeded maximum duration, closing")
                self.execute_trade("sell", position['position_size'], symbol)
                return

            # Check update interval
            time_since_update = (datetime.now() - position['last_update']).total_seconds()
            if time_since_update < CONFIG['position_update_interval']:
                return

            # Update trailing stop
            new_stop = self.implement_trailing_stop(
                position['entry_price'],
                current_price,
                position['position_size']
            )

            # Update position info
            position['last_update'] = datetime.now()
            position['current_stop'] = new_stop

            # Check exit conditions
            if self.should_exit_position(position, current_price, market_data):
                self.execute_trade("sell", position['position_size'], symbol)

        except Exception as e:
            logging.error(f"Error managing positions: {str(e)}")

    def cleanup(self):
        """Cleanup resources before shutdown"""
        try:
            logging.info("Initiating cleanup process")

            # Cancel any pending orders
            open_orders = safe_api_call(self.exchange.fetch_open_orders, CONFIG['symbol'])
            if open_orders:
                for order in open_orders:
                    safe_api_call(self.exchange.cancel_order, order['id'], CONFIG['symbol'])
                    logging.info(f"Cancelled order {order['id']}")

            # Save performance metrics
            self.performance.save_metrics()

            # Close exchange connection if available
            if hasattr(self.exchange, 'close'):
                self.exchange.close()

            # Clear market data
            if hasattr(self, 'market_data'):
                del self.market_data

            # Clear large objects
            import gc
            gc.collect()

            logging.info("Cleanup completed successfully")
        except Exception as e:
            logging.error(f"Error during cleanup: {str(e)}")

    def validate_trading_conditions(self, market_data):
        """Enhanced trading conditions validation with detailed logging"""
        try:
            # Create a conditions report
            conditions_report = {
                "market_health": True,
                "spread": True,
                "volume": True,
                "price_movement": True,
                "trend_strength": True,
                "volatility": True,
                "vwap_distance": True
            }

            # Market health check
            if not self.check_market_health():
                conditions_report["market_health"] = False
                logging.info("❌ Market health check failed: Volume or trend conditions not met")
                return False

            # Detailed market data logging
            current_price = market_data['close'].iloc[-1]
            current_volume = market_data['volume'].iloc[-1] * current_price

            logging.info("\n=== Market Conditions Analysis ===")
            logging.info(f"Current Price: {current_price:.2f} USDT")
            logging.info(f"24h Volume: {current_volume:.2f} USDT")

            # Add RSI-based entry condition
            trend_analysis = self.analyze_price_trend(market_data)
            rsi = trend_analysis['rsi']

            # Buy condition when RSI is oversold
            if rsi < CONFIG['rsi_oversold']:
                logging.info(f"✅ RSI oversold condition met: {rsi:.2f}")
                return True

            # 1. Spread Check
            if not self.check_spread(market_data):
                conditions_report["spread"] = False
                logging.info("❌ Spread check failed: Current spread exceeds maximum allowed")
                return False

            # 2. Volume Analysis
            volume_ma = market_data['volume'].rolling(window=CONFIG['volume_ma_period']).mean().iloc[-1]
            volume_threshold = volume_ma * CONFIG['min_volume_multiplier']

            if current_volume < volume_threshold:
                conditions_report["volume"] = False
                logging.info(f"❌ Volume too low: {current_volume:.2f} < {volume_threshold:.2f}")
                return False
            logging.info(f"✅ Volume check passed: {current_volume:.2f} > {volume_threshold:.2f}")

            # 3. Price Movement Check
            price_change = abs(market_data['close'].pct_change().iloc[-1])
            if price_change > CONFIG['price_change_threshold']:
                conditions_report["price_movement"] = False
                logging.info(f"❌ Price change too high: {price_change:.2%}")
                return False
            logging.info(f"✅ Price movement check passed: {price_change:.2%}")

            # 4. Trend Strength Analysis
            trend_strength = self.calculate_trend_strength(market_data)
            logging.info(f"Trend Analysis Details:")
            logging.info(f"- Current Trend Strength: {trend_strength:.6f}")
            logging.info(f"- Threshold: {CONFIG['trend_strength_threshold']}")

            if trend_strength < CONFIG['trend_strength_threshold']:
                conditions_report["trend_strength"] = False
                logging.info(f"❌ Weak trend strength: {trend_strength:.4f}")
                return False
            logging.info(f"✅ Trend strength check passed: {trend_strength:.4f}")

            # 5. Volatility Check
            volatility = self.calculate_volatility()
            if volatility > CONFIG['max_volatility_threshold']:
                conditions_report["volatility"] = False
                logging.info(f"❌ Volatility too high: {volatility:.4%}")
                return False
            logging.info(f"✅ Volatility check passed: {volatility:.4%}")

            # 6. VWAP Distance Check
            vwap = self.calculate_vwap(market_data)
            vwap_distance = abs(current_price - vwap) / vwap
            if vwap_distance > CONFIG['max_spread_percent'] / 100:
                conditions_report["vwap_distance"] = False
                logging.info(f"❌ Price too far from VWAP: {vwap_distance:.4%}")
                return False
            logging.info(f"✅ VWAP distance check passed: {vwap_distance:.4%}")

            # Log summary of all conditions
            logging.info("\n=== Trading Conditions Summary ===")
            for condition, status in conditions_report.items():
                logging.info(f"{condition}: {'✅' if status else '❌'}")

            logging.info("✅ All trading conditions met")
            return True

        except Exception as e:
            logging.error(f"Error validating trading conditions: {str(e)}")
            return False

    def calculate_trend_strength(self, market_data):
        try:
            # Get base EMAs
            ema_short = self.calculate_ema(market_data, CONFIG['ema_short_period'])
            ema_long = self.calculate_ema(market_data, CONFIG['ema_long_period'])

            # Calculate directional movement
            price_change = market_data['close'].pct_change(CONFIG['trend_lookback'])
            direction = np.sign(price_change.mean())

            # Calculate price momentum
            momentum = market_data['close'].pct_change(5).mean()

            # Calculate volume trend
            volume_sma = market_data['volume'].rolling(window=10).mean()
            volume_trend = (market_data['volume'].iloc[-1] / volume_sma.iloc[-1]) - 1

            # Enhanced trend strength calculation
            basic_trend_strength = abs(ema_short.iloc[-1] - ema_long.iloc[-1]) / ema_long.iloc[-1]

            # Weight the components
            weighted_strength = (
                basic_trend_strength * 0.35 +  # Base trend
                abs(momentum) * 0.25 +         # Momentum
                abs(volume_trend) * 0.20 +     # Volume trend
                direction * 0.20               # Direction
            )

            # Apply volatility adjustment
            volatility = self.calculate_volatility()
            if volatility:
                volatility_factor = 1 - (volatility / CONFIG['max_volatility_threshold'])
                weighted_strength *= max(0.5, volatility_factor)  # Cap minimum at 0.5

            logging.debug(f"""
            Trend Components:
            Basic: {basic_trend_strength:.6f}
            Momentum: {momentum:.6f}
            Volume: {volume_trend:.6f}
            Direction: {direction}
            Volatility Adj: {volatility_factor if volatility else 'N/A'}
            Final: {weighted_strength:.6f}
            """)

            return weighted_strength

        except Exception as e:
            logging.error(f"Error calculating trend strength: {str(e)}")
            return 0

    def implement_risk_management(self, symbol, entry_price, position_size, order):
        """Enhanced risk management implementation"""
        try:
            # Basic setup
            stop_loss = self.calculate_stop_loss(entry_price)
            take_profit = entry_price * (1 + CONFIG['profit_target_percent'] / 100)

            # Order tracking
            order_id = order['id']
            entry_time = datetime.now()

            # Save position info
            position_info = {
                'order_id': order_id,
                'entry_time': entry_time,
                'entry_price': entry_price,
                'position_size': position_size,
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'last_update': entry_time
            }

            # Implement trailing stop
            trailing_stop = self.implement_trailing_stop(
                entry_price=entry_price,
                current_price=entry_price,
                position_size=position_size
            )

            # Check slippage
            actual_entry = float(order['price'])
            slippage = abs(actual_entry - entry_price) / entry_price
            if slippage > CONFIG['max_slippage']:
                logging.warning(f"High slippage detected: {slippage:.2%}")

            # Set take profits
            self.implement_partial_take_profits(entry_price, position_size)

            return position_info

        except Exception as e:
            logging.error(f"Error implementing risk management: {str(e)}")
            return None

    def get_position_entry(self, symbol):
        """Get entry details for current position"""
        try:
            trades = self.trade_history.get(symbol, [])
            if not trades:
                return None

            # Get most recent buy trade
            buy_trades = [t for t in trades if t['side'] == 'buy']
            if not buy_trades:
                return None

            return buy_trades[-1]

        except Exception as e:
            logging.error(f"Error getting position entry: {str(e)}")
            return None

    def validate_market_data(self, market_data):
        """Validate market data structure and content"""
        try:
            if market_data is None or market_data.empty:
                return False

            required_columns = ['open', 'high', 'low', 'close', 'volume']
            if not all(col in market_data.columns for col in required_columns):
                logging.error("Missing required columns in market data")
                return False

            if len(market_data) < CONFIG['min_candles_required']:
                logging.error("Insufficient historical data")
                return False

            return True
        except Exception as e:
            logging.error(f"Error validating market data: {str(e)}")
            return False

    def log_trading_metrics(self, symbol_base, optimal_position, amount_to_trade, current_price):
        """Log comprehensive trading metrics"""
        try:
            logging.info("=== Trading Metrics ===")
            logging.info(f"Symbol: {symbol_base}")
            logging.info(f"Current Price: {current_price:.2f}")
            logging.info(f"Optimal Position: {optimal_position:.4f}")
            logging.info(f"Trade Amount: {amount_to_trade:.4f}")
            logging.info(f"Notional Value: {amount_to_trade * current_price:.2f} USDT")
            logging.info("===================")

        except Exception as e:
            logging.error(f"Error logging trading metrics: {str(e)}")

    def execute_trade_with_safety(self, side, amount, symbol, current_price):
        """Execute trade with additional safety checks"""
        try:
            # Add exchange connection check
            if not self.check_exchange_connection():
                logging.error("Exchange connection check failed before safety checks")
                return False

            # Check open orders count
            open_orders = safe_api_call(self.exchange.fetch_open_orders, symbol)
            if len(open_orders) >= CONFIG['max_open_orders']:
                logging.warning("Maximum open orders reached")
                return False

            # Check daily profit target
            if self.check_daily_profit_target():
                logging.info("Daily profit target reached, skipping trade")
                return False

            # Add position parameters validation here
            if not self.validate_position_parameters(amount, current_price, self.market_data):
                logging.warning("Position parameters validation failed")
                return False

            # Pre-trade validation
            if not self.validate_trading_conditions(self.market_data):
                return False

            # Execute trade
            order = self.execute_trade(side, amount, symbol)
            if order is None:
                return False

            # Post-trade actions
            self.implement_risk_management(
                symbol=symbol,
                entry_price=current_price,
                position_size=amount,
                order=order
            )

            # Monitor performance after trade
            self.monitor_performance()

            return True

        except Exception as e:
            self.handle_trade_error(e)
            logging.error(f"Error executing trade with safety: {str(e)}")
            return False

    def should_execute_trade(self, analysis_result, market_data):
        """Determine if trade should be executed based on analysis"""
        try:
            if analysis_result is None:
                return False

            # Check for buy conditions
            ema_short = analysis_result['ema_data']['ema_short']
            ema_long = analysis_result['ema_data']['ema_long']
            trend = analysis_result['trend_analysis']

            # Enhanced buy conditions
            buy_conditions = (
                ema_short.iloc[-2] < ema_long.iloc[-2] and  # Previous crossover
                ema_short.iloc[-1] > ema_long.iloc[-1] and  # Current crossover
                trend['rsi'] < CONFIG['rsi_overbought'] and
                trend['adx'] > CONFIG['adx_threshold'] and
                trend['momentum'] > CONFIG['momentum_threshold'] and
                trend['trend_strength'] > CONFIG['trend_strength_threshold']
            )

            return buy_conditions

        except Exception as e:
            logging.error(f"Error checking trade conditions: {str(e)}")
            return False

    def perform_technical_analysis(self, market_data):
        """Perform comprehensive technical analysis"""
        try:
            # Calculate EMAs
            market_data['ema_short'] = self.calculate_ema(market_data, CONFIG['ema_short_period'])
            market_data['ema_long'] = self.calculate_ema(market_data, CONFIG['ema_long_period'])

            # Get trend analysis
            trend_analysis = self.analyze_price_trend(market_data)

            if None in [market_data['ema_short'], market_data['ema_long'], trend_analysis]:
                return None

            return {
                'ema_data': market_data[['ema_short', 'ema_long']],
                'trend_analysis': trend_analysis
            }

        except Exception as e:
            logging.error(f"Error performing technical analysis: {str(e)}")
            return None

    def calculate_position_size(self, balance, current_price, market_data):
        try:
            # Calculate base position size with minimum consideration
            risk_amount = balance * (CONFIG['risk_percentage'] / 100)
            base_position = max(
                CONFIG['min_trade_amount'],  # Use min_trade_amount instead of min_position_size
                risk_amount / current_price
            )

            # Ensure minimum notional value
            min_notional_position = CONFIG['min_notional_value'] / current_price
            base_position = max(base_position, min_notional_position)

            # Apply volatility-based adjustment
            volatility = self.calculate_volatility()
            if volatility:
                vol_adjustment = 1 - (volatility / CONFIG['max_volatility_threshold'])
                base_position *= max(0.5, vol_adjustment)

            # Apply trend strength adjustment
            trend_strength = self.calculate_trend_strength(market_data)
            trend_adjustment = min(1.2, max(0.8, trend_strength / CONFIG['trend_strength_threshold']))
            base_position *= trend_adjustment

            # Apply market impact adjustment
            avg_volume = market_data['volume'].rolling(window=20).mean().iloc[-1]
            market_impact = (base_position * current_price) / (avg_volume * current_price)
            if market_impact > CONFIG['market_impact_threshold']:
                impact_reduction = CONFIG['market_impact_threshold'] / market_impact
                base_position *= impact_reduction

            # Apply limits
            max_position = min(
                balance * CONFIG['max_position_size'] / current_price,
                CONFIG['max_notional_value'] / current_price
            )
            final_position = min(max_position, base_position)

            # Ensure minimum requirements
            final_position = max(final_position, CONFIG['min_trade_amount'])

            logging.info(f"""
            Position Sizing Details:
            Base Position: {base_position:.6f}
            Volatility Adjustment: {vol_adjustment if volatility else 'N/A'}
            Trend Adjustment: {trend_adjustment:.2f}
            Market Impact: {market_impact:.4%}
            Final Position: {final_position:.6f}
            Notional Value: {final_position * current_price:.2f} USDT
            """)

            # Format the final amount
            amount_to_trade_formatted = adjust_trade_amount(
                final_position,
                current_price,
                CONFIG['min_trade_amount'],
                CONFIG['min_notional_value']
            )

            return final_position, amount_to_trade_formatted

        except Exception as e:
            logging.error(f"Error calculating position size: {str(e)}")
            return None, None

    def validate_position_size(self, amount, price):
        try:
            notional_value = amount * price
            min_notional = CONFIG.get('min_notional_value', 11)  # Add to config
            max_notional = CONFIG.get('max_notional_value', 1000.0)  # Add to config
            min_amount = CONFIG.get('min_trade_amount', 0.004)

            if amount < min_amount:
                logging.warning(f"Position size too small: {amount} ETH (minimum: {min_amount} ETH)")
                return False

            if notional_value < min_notional:
                logging.warning(f"Order value too small: {notional_value:.2f} USDT (minimum: {min_notional} USDT)")
                return False

            if notional_value > max_notional:
                logging.warning(f"Order value too large: {notional_value:.2f} USDT (maximum: {max_notional} USDT)")
                return False

            logging.info(f"Position size validated - Amount: {amount} ETH, Value: {notional_value:.2f} USDT")
            return True
        except Exception as e:
            logging.error(f"Error validating position size: {str(e)}")
            return False

    def check_market_health(self):
        try:
            ticker = safe_api_call(self.exchange.fetch_ticker, CONFIG['symbol'])
            volume_24h = ticker['quoteVolume']

            # Enhanced volume check
            avg_volume = self.market_data['volume'].mean() * self.market_data['close'].mean()
            volume_ratio = volume_24h / (avg_volume * 24)

            logging.info(f"Volume ratio: {volume_ratio:.2f}")

            if volume_ratio < 0.8:  # Volume should be at least 80% of average
                logging.warning("Volume below average")
                return False

            return True
        except Exception as e:
            logging.error(f"Error checking market health: {str(e)}")
            return False

    def check_spread(self, market_data):
        try:
            if 'ask' not in market_data or 'bid' not in market_data:
                logging.warning("Ask/Bid data not available, skipping spread check")
                return True

            spread = (market_data['ask'].iloc[-1] - market_data['bid'].iloc[-1]) / market_data['bid'].iloc[-1]
            logging.info(f"Current spread: {spread:.4%}")

            # Add monitoring for unusual spreads
            if spread < 0:
                logging.warning(f"Negative spread detected: {spread:.4%}")
                return False

            if spread > CONFIG['max_spread_percent'] / 100:
                logging.warning(f"Spread too high: {spread:.4%}")
                return False

            # Log when spread is approaching maximum
            if spread > (CONFIG['max_spread_percent'] / 100) * 0.8:
                logging.warning(f"Spread approaching maximum threshold: {spread:.4%}")

            return True
        except Exception as e:
            logging.error(f"Error checking spread: {str(e)}")
            return False  # Changed to return False on error

    def calculate_optimal_position_size(self, balance, current_price):
        """Calculate optimal position size based on risk management"""
        try:
            # Calculate base position size from account risk
            max_risk_amount = balance * (CONFIG['risk_percentage'] / 100)
            position_size = max_risk_amount / current_price

            # Ensure minimum position size
            min_position = CONFIG.get('min_position_size', 0.004)
            position_size = max(position_size, min_position)

            # Apply volatility adjustment
            adjusted_position = self.manage_position_size(position_size)

            # Apply maximum position limit
            max_position = balance * CONFIG['max_position_size'] / current_price
            final_position = min(adjusted_position, max_position)

            # Ensure minimum notional value
            min_notional = CONFIG.get('min_notional_value', 11.0)
            if final_position * current_price < min_notional:
                final_position = min_notional / current_price

            logging.info(f"Calculated position sizes:")
            logging.info(f"Base position: {position_size:.4f}")
            logging.info(f"Volatility adjusted: {adjusted_position:.4f}")
            logging.info(f"Final position: {final_position:.4f}")
            logging.info(f"Estimated value: {final_position * current_price:.2f} USDT")

            return final_position
        except Exception as e:
            logging.error(f"Error calculating optimal position size: {str(e)}")
            return None

    def fetch_market_data(self, symbol, timeframe):
        """Fetch market data method for class"""
        try:
            candles = safe_api_call(self.exchange.fetch_ohlcv, symbol, timeframe)
            if candles is None:
                return None

            df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            # Fetch current ticker for ask/bid
            ticker = safe_api_call(self.exchange.fetch_ticker, symbol)
            if ticker:
                df['ask'] = ticker['ask']
                df['bid'] = ticker['bid']

            return df
        except Exception as e:
            logging.error(f"Failed to fetch market data: {str(e)}")
            return None

    def check_profitability(self, historical_data, current_price):
        if historical_data is None or historical_data.empty:
            logging.error("Historical data is empty or None")
            return False

        # Calculate sell target taking into account the required profit margin
        latest_price = historical_data['close'].iloc[-1]
        target_price = latest_price * (1 + CONFIG['profit_target_percent'] / 100)

        # Ensure profitability after fees
        profit_margin = target_price - latest_price
        fee_estimate = current_price * CONFIG['fee_rate']

        logging.info(f"Current price: {current_price}, Target price for selling: {target_price}, Fee estimate: {fee_estimate}")

        # Subtract fees to see if profitability is meaningful
        net_profit = profit_margin - fee_estimate
        logging.info(f"Net profit after fee: {net_profit}")

        return net_profit > 0

    def analyze_historical_data(self, symbol, timeframe='1h', limit=100):
        try:
            candles = safe_api_call(self.exchange.fetch_ohlcv, symbol, timeframe, limit=limit)
            if candles is None:
                logging.error(f"Failed to fetch historical data for {symbol}")
                return None

            df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            return df
        except Exception as e:
            logging.error(f"Exception in fetching historical data: {str(e)}")
            return None

    def place_limit_sell_order(self, amount, price):
        """Place limit sell order"""
        try:
            order = safe_api_call(
                self.exchange.create_limit_sell_order,
                CONFIG['symbol'],
                amount,
                price
            )
            logging.info(f"Placed limit sell order: {order}")
            return order
        except Exception as e:
            logging.error(f"Failed to place limit sell order: {str(e)}")
            return None

    def get_original_buy_price(self, symbol, executed_qty):
        """Get weighted average buy price from trade history"""
        try:
            trades = self.trade_history.get(symbol, [])
            buy_trades = [t for t in trades if t['side'] == 'buy']

            if not buy_trades:
                return 0

            total_cost = 0
            total_qty = 0

            for trade in reversed(buy_trades):
                if total_qty >= executed_qty:
                    break

                qty = min(trade['amount'], executed_qty - total_qty)
                total_cost += qty * trade['price']
                total_qty += qty

            if total_qty == 0:
                return 0

            return total_cost / total_qty

        except Exception as e:
            logging.error(f"Error getting original buy price: {str(e)}")
            return 0

    def calculate_profit(self, order):
        """Calculate profit for the trade considering the fee."""
        try:
            if order is None:
                return 0

            executed_qty = float(order['filled'])
            avg_price = float(order['price'])
            symbol = order['symbol']

            # Fetch current price
            current_price = self.fetch_current_price(symbol)
            if current_price is None:
                return 0

            # Calculate profit based on side
            if order['side'] == 'buy':
                profit = (current_price - avg_price) * executed_qty
            elif order['side'] == 'sell':
                original_price = self.get_original_buy_price(symbol, executed_qty)
                profit = (avg_price - original_price) * executed_qty

            # Deduct fees
            fee_cost = executed_qty * avg_price * CONFIG['fee_rate']
            profit -= fee_cost

            return profit

        except Exception as e:
            logging.error(f"Error calculating profit: {str(e)}")
            return 0

    def fetch_current_price(self, symbol):
        """Fetch current price for symbol"""
        try:
            ticker = safe_api_call(self.exchange.fetch_ticker, symbol)
            return ticker['last']
        except Exception as e:
            logging.error(f"Error fetching current price for {symbol}: {str(e)}")
            return None

    def execute_trade(self, side, amount, symbol):
        """
        Execute trade with enhanced error handling and order tracking

        Args:
            side (str): "buy" or "sell"
            amount (float): Amount to trade
            symbol (str): Trading pair symbol
        """
        try:
            # Add exchange connection check
            if not self.check_exchange_connection():
                logging.error("Exchange connection check failed before trade execution")
                return None

            start_time = time.time()

            # Validate market conditions first
            if not self.validate_market_conditions(self.market_data):
                logging.warning(f"Market conditions not met for {symbol}, skipping trade")
                return None

            # Get current balance
            balance = safe_api_call(self.exchange.fetch_balance)
            base_currency = symbol.split('/')[0]
            base_balance = balance[base_currency]['free']

            # Validate balance for sell orders
            if side == "sell" and base_balance < amount:
                logging.warning(f"Insufficient balance for selling {base_currency}. Available: {base_balance}, Required: {amount}")
                return None

            # Execute order with timeout check
            while time.time() - start_time < CONFIG['order_timeout']:
                try:
                    # Place the order
                    if side == "buy":
                        order = self.exchange.create_market_buy_order(symbol, amount)
                    else:
                        order = self.exchange.create_market_sell_order(symbol, amount)

                    # Check if order is filled
                    if order['status'] == 'closed':
                        # Update trade history
                        order_info = {
                            'timestamp': datetime.now().isoformat(),
                            'symbol': symbol,
                            'side': side,
                            'amount': amount,
                            'price': float(order['price']),
                            'order_id': order['id']
                        }

                        if symbol not in self.trade_history:
                            self.trade_history[symbol] = []
                        self.trade_history[symbol].append(order_info)

                        # Log and notify
                        logging.info(f"Executed {side} order: {order}")
                        self.send_notification(
                            f"Executed {side} order:\n"
                            f"Symbol: {symbol}\n"
                            f"Amount: {amount}\n"
                            f"Price: {order['price']}"
                        )

                        return order

                    time.sleep(1)  # Wait before checking again

                except Exception as e:
                    logging.error(f"Order execution error: {str(e)}")
                    return None

            logging.error(f"Order timeout after {CONFIG['order_timeout']} seconds")
            return None

        except Exception as e:
            self.handle_trade_error(e)
            logging.error(f"Error in execute_trade: {str(e)}")
            return None

    def send_notification(self, message):
        try:
            send_telegram_notification(message)
        except Exception as e:
            logging.error(f"Failed to send notification: {str(e)}")

    def check_for_sell_signal(self, symbol, current_price):
        eth_balance = safe_api_call(self.exchange.fetch_balance)[symbol.split('/')[0]]['free']
        if eth_balance <= 0:
            logging.warning(f"No {symbol.split('/')[0]} to sell.")
            return

            historical_data = self.analyze_historical_data(symbol)
            if self.check_profitability(historical_data, current_price):
                logging.info(f"Profit target met. Preparing to sell {eth_balance} {symbol.split('/')[0]}")
                self.execute_trade("sell", eth_balance, symbol)

    def process_trade_signals(self, market_data, symbol, amount_to_trade_formatted):
        """Process trading signals for spot trading"""
        try:
            if market_data is None or market_data.empty:
                logging.warning("Empty market data in process_trade_signals")
                return

            current_price = market_data['close'].iloc[-1]
            analysis = self.analyze_price_trend(market_data)
            rsi = analysis['rsi']

            logging.info(f"""
            Spot Trading Analysis:
            Current Price: {current_price:.2f} USDT
            RSI: {rsi:.2f}
            24h Volume: {market_data['volume'].iloc[-1] * current_price:.2f} USDT
            """)

            # Check for buying conditions
            if rsi < CONFIG['rsi_oversold']:
                logging.info(f"Strong buy signal detected - RSI: {rsi:.2f}")
                # Execute the trade
                self.execute_trade("buy", amount_to_trade_formatted, symbol)
            elif rsi < 45 and self.check_price_stability(market_data):
                logging.info(f"Moderate buy signal detected - RSI: {rsi:.2f}")
                # Execute the trade with smaller position
                adjusted_amount = amount_to_trade_formatted * 0.7  # Reduce position size
                self.execute_trade("buy", adjusted_amount, symbol)
            else:
                logging.info(f"No clear buy signal - RSI: {rsi:.2f}")

        except Exception as e:
            logging.error(f"Error in process_trade_signals: {str(e)}")
            logging.error(traceback.format_exc())

    def validate_market_conditions(self, market_data):
        """Validate market conditions specifically for spot trading"""
        try:
            # Log market conditions
            current_price = market_data['close'].iloc[-1]
            trend_analysis = self.analyze_price_trend(market_data)
            rsi = trend_analysis['rsi']

            logging.info(f"""
            === Detailed Market Analysis ===
            Price: {current_price:.2f} USDT
            RSI: {rsi:.2f}
            Volume: {market_data['volume'].iloc[-1] * current_price:.2f} USDT
            """)

            # 1. Volume Check
            if not self.check_market_health():
                logging.info("❌ Market health check failed")
                return False

            # 2. Spread Check
            current_spread = self.check_spread(market_data)
            if current_spread > CONFIG['max_spread_percent'] / 100:
                logging.info("❌ High spread detected")
                return False

            # 3. Enhanced Entry Conditions for Spot
            # Good buying conditions based on RSI
            if rsi <= CONFIG['rsi_oversold']:
                logging.info(f"✅ Strong buy signal - RSI oversold: {rsi:.2f}")
                return True
            elif rsi < 45:  # Accumulation zone
                # Check price stability
                price_change = abs(market_data['close'].pct_change().iloc[-1])
                if price_change < CONFIG['price_change_threshold']:
                    logging.info(f"✅ Moderate buy signal - RSI in accumulation zone: {rsi:.2f}")
                    return True

            # 4. Volume Validation
            volume_check = self.validate_volume(market_data)
            if not volume_check:
                logging.info("❌ Volume conditions not met")
                return False

            logging.info(f"❌ No clear entry signal - RSI: {rsi:.2f}")
            return False

        except Exception as e:
            logging.error(f"Error validating market conditions: {str(e)}")
            return False

    def validate_volume(self, market_data):
        """Validate volume conditions"""
        try:
            current_volume = market_data['volume'].iloc[-1] * market_data['close'].iloc[-1]
            avg_volume = market_data['volume'].rolling(window=CONFIG['volume_ma_period']).mean().iloc[-1] * market_data['close'].iloc[-1]

            volume_ratio = current_volume / avg_volume
            logging.info(f"Volume ratio: {volume_ratio:.2f}")

            return volume_ratio >= CONFIG['min_volume_multiplier']
        except Exception as e:
            logging.error(f"Error validating volume: {str(e)}")
            return False

    def check_price_stability(self, market_data):
        """Check if price is showing stability"""
        try:
            # Calculate price volatility over last few periods
            recent_volatility = market_data['close'].pct_change().tail(5).std()

            # Check if volatility is within acceptable range
            if recent_volatility < CONFIG['price_stability_threshold']:
                logging.info(f"Price showing stability - volatility: {recent_volatility:.4%}")
                return True

            return False
        except Exception as e:
            logging.error(f"Error checking price stability: {str(e)}")
            return False

    def analyze_price_trend(self, market_data, lookback_period=20):
        """Analyze price trend using multiple indicators"""
        try:
            close_prices = market_data['close']

            # Calculate RSI
            delta = close_prices.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))

            # Calculate price momentum
            momentum = close_prices.pct_change(periods=lookback_period)

            # Calculate average directional index (ADX)
            high_prices = market_data['high']
            low_prices = market_data['low']

            plus_dm = high_prices.diff()
            minus_dm = low_prices.diff()
            plus_dm = plus_dm.where(plus_dm > 0, 0)
            minus_dm = minus_dm.where(minus_dm > 0, 0)

            tr = pd.DataFrame({
                'hl': high_prices - low_prices,
                'hc': abs(high_prices - close_prices.shift(1)),
                'lc': abs(low_prices - close_prices.shift(1))
            }).max(axis=1)

            smoothing = 14
            plus_di = 100 * (plus_dm.rolling(smoothing).mean() / tr.rolling(smoothing).mean())
            minus_di = 100 * (minus_dm.rolling(smoothing).mean() / tr.rolling(smoothing).mean())
            dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
            adx = dx.rolling(smoothing).mean()

            return {
                'rsi': rsi.iloc[-1],
                'momentum': momentum.iloc[-1],
                'adx': adx.iloc[-1],
                'trend_strength': (plus_di.iloc[-1] - minus_di.iloc[-1])
            }

        except Exception as e:
            logging.error(f"Error in trend analysis: {str(e)}")
            return None

    def calculate_vwap(self, market_data):
        """Calculate Volume Weighted Average Price"""
        try:
            v = market_data['volume'].values
            tp = (market_data['high'] + market_data['low'] + market_data['close']) / 3
            return (tp * v).sum() / v.sum()
        except Exception as e:
            logging.error(f"Error calculating VWAP: {str(e)}")
            return None

    def calculate_atr(self, market_data, period):
        """Calculate Average True Range"""
        try:
            high = market_data['high']
            low = market_data['low']
            close = market_data['close']

            tr1 = high - low
            tr2 = abs(high - close.shift())
            tr3 = abs(low - close.shift())

            tr = pd.DataFrame({'tr1': tr1, 'tr2': tr2, 'tr3': tr3}).max(axis=1)
            atr = tr.rolling(window=period).mean()

            return atr.iloc[-1]

        except Exception as e:
            logging.error(f"Error calculating ATR: {str(e)}")
            return float('inf')

    def get_funding_rate(self):
        """Get funding rate for the symbol"""
        try:
            funding_rate = safe_api_call(
                self.exchange.fetch_funding_rate,
                CONFIG['symbol']
            )
            return funding_rate['fundingRate'] if funding_rate else 0
        except Exception as e:
            logging.error(f"Error fetching funding rate: {str(e)}")
            return 0

    def manage_position_size(self, base_position_size):
        """Adjust position size based on market conditions"""
        try:
            volatility = self.calculate_volatility()

            if volatility > CONFIG['high_volatility_threshold']:
                return base_position_size * (1 - CONFIG['high_volatility_adjustment'])

            if volatility < CONFIG['low_volatility_threshold']:
                return base_position_size * (1 + CONFIG['low_volatility_adjustment'])

            return base_position_size

        except Exception as e:
            logging.error(f"Error managing position size: {str(e)}")
            return base_position_size

    def calculate_volatility(self, lookback_period=20):
        """Calculate current market volatility"""
        try:
            if self.market_data is None:
                return None

            returns = np.log(self.market_data['close'] / self.market_data['close'].shift(1))
            return returns.std() * np.sqrt(24) # Annualized volatility

        except Exception as e:
            logging.error(f"Error calculating volatility: {str(e)}")
            return None

    def validate_risk_reward(self, entry_price, stop_loss, take_profit):
        """Validate if trade meets minimum risk-reward ratio"""
        try:
            risk = entry_price - stop_loss
            reward = take_profit - entry_price

            if risk <= 0:
                return False

            rr_ratio = reward / risk
            if rr_ratio < CONFIG['min_risk_reward_ratio']:
                logging.warning(f"Risk-reward ratio {rr_ratio:.2f} below minimum {CONFIG['min_risk_reward_ratio']}")
                return False

            return True

        except Exception as e:
            logging.error(f"Error validating risk-reward: {str(e)}")
            return False

    def implement_trailing_stop(self, entry_price, current_price, position_size):
        """Implement trailing stop logic"""
        try:
            initial_stop = entry_price * (1 - CONFIG['stop_loss_percent'] / 100)
            profit_threshold = entry_price * (1 + CONFIG['initial_profit_for_trailing_stop'])

            if current_price >= profit_threshold:
                trailing_stop = current_price * (1 - CONFIG['trailing_distance_pct'])
                if trailing_stop > initial_stop:
                    logging.info(f"Updating trailing stop to: {trailing_stop}")
                    return trailing_stop

            return initial_stop

        except Exception as e:
            logging.error(f"Error implementing trailing stop: {str(e)}")
            return initial_stop

    def implement_partial_take_profits(self, entry_price, position_size):
        """Implement scaled take profit orders"""
        try:
            # First take profit level
            tp1_size = position_size * CONFIG['partial_tp_1']
            tp1_price = entry_price * (1 + CONFIG['tp1_target'])

            # Second take profit level
            tp2_size = position_size * CONFIG['partial_tp_2']
            tp2_price = entry_price * (1 + CONFIG['tp2_target'])

            # Place take profit orders
            self.place_limit_sell_order(tp1_size, tp1_price)
            self.place_limit_sell_order(tp2_size, tp2_price)

            # Implement trailing stop for remaining position
            self.implement_trailing_stop(entry_price, entry_price, position_size)

        except Exception as e:
            logging.error(f"Error setting take profits: {str(e)}")

    def implement_stop_loss(self, symbol, amount):
        try:
            last_price = self.fetch_current_price(symbol)
            if last_price is None:
                return
            stop_loss_price = self.calculate_stop_loss(last_price)
            logging.info(f"Setting stop-loss order at {stop_loss_price}")
        except Exception as e:
            logging.error(f"Failed to set stop-loss: {str(e)}")

    def calculate_stop_loss(self, current_price):
        return current_price * (1 - CONFIG['stop_loss_percent'] / 100)

    @staticmethod
    def calculate_ema(df, period, column='close'):
        try:
            return df[column].ewm(span=period, adjust=False).mean()
        except Exception as e:
            logging.error(f"Error calculating EMA: {str(e)}")
            return None

    @staticmethod
    def validate_ema_strategy(config):
        if config['ema_short_period'] >= config['ema_long_period']:
            raise ValueError("Short EMA period should be less than Long EMA period.")
        logging.info("EMA strategy validation passed")

    def validate_trade_conditions(self, market_data):
        """Additional trade validation filters"""
        try:
            # Volume filter
            if market_data['volume'].iloc[-1] * market_data['close'].iloc[-1] < CONFIG['min_volume_usdt']:
                return False

            # ATR filter for volatility
            atr = self.calculate_atr(market_data, CONFIG['atr_period'])
            if atr > CONFIG['max_atr_threshold']:
                return False

            # VWAP filter
            vwap = self.calculate_vwap(market_data)
            if market_data['close'].iloc[-1] < vwap:
                return False

            # Funding rate check for market sentiment
            funding_rate = self.get_funding_rate()
            if abs(funding_rate) > CONFIG['funding_rate_threshold']:
                return False

            return True

        except Exception as e:
            logging.error(f"Error validating trade conditions: {str(e)}")
            return False

class PerformanceMetrics:
    def __init__(self):
        self.metrics_file = 'performance_metrics_spot.json'
        self.load_metrics()

    def load_metrics(self):
        try:
            with open(self.metrics_file, 'r') as f:
                self.metrics = json.load(f)
        except FileNotFoundError:
            self.initialize_metrics()

    def initialize_metrics(self):
        self.metrics = {
            'total_trades': 0,
            'winning_trades': 0,
            'total_profit': 0,
            'max_drawdown': 0,
            'daily_trades': 0,
            'daily_loss': 0,
            'trade_history': [],
            'last_reset_date': datetime.now().strftime('%Y-%m-%d')
        }
        self.save_metrics()

    def save_metrics(self):
        with open(self.metrics_file, 'w') as f:
            json.dump(self.metrics, f)

    def update_trade(self, profit, won=False):
        today = datetime.now().strftime('%Y-%m-%d')

        if today != self.metrics['last_reset_date']:
            self.metrics['daily_trades'] = 0
            self.metrics['daily_loss'] = 0
            self.metrics['last_reset_date'] = today

        self.metrics['total_trades'] += 1
        self.metrics['daily_trades'] += 1

        if won:
            self.metrics['winning_trades'] += 1

        self.metrics['total_profit'] += profit
        if profit < 0:
            self.metrics['daily_loss'] += abs(profit)

        self.metrics['trade_history'].append({
            'timestamp': datetime.now().isoformat(),
            'profit': profit,
            'won': won
        })

        self.calculate_metrics()
        self.save_metrics()

    def calculate_metrics(self):
        if self.metrics['total_trades'] > 0:
            self.metrics['win_rate'] = (self.metrics['winning_trades'] / self.metrics['total_trades']) * 100
            profits = [trade['profit'] for trade in self.metrics['trade_history']]
            self.metrics['sharpe_ratio'] = self.calculate_sharpe_ratio(profits)
            self.metrics['max_drawdown'] = self.calculate_max_drawdown(profits)

    @staticmethod
    def calculate_sharpe_ratio(profits, risk_free_rate=0.02):
        if len(profits) < 2:
            return 0
        returns = pd.Series(profits)
        excess_returns = returns - (risk_free_rate / 252)
        if excess_returns.std() == 0:
            return 0
        return np.sqrt(252) * (excess_returns.mean() / excess_returns.std())

    @staticmethod
    def calculate_max_drawdown(profits):
        cumulative = np.cumsum(profits)
        running_max = np.maximum.accumulate(cumulative)
        drawdown = running_max - cumulative
        return np.max(drawdown) if len(drawdown) > 0 else 0

    def can_trade(self):
        if self.metrics['daily_trades'] >= CONFIG['max_daily_trades']:
            logging.warning('Maximum daily trades reached')
            return False
        if self.metrics['daily_loss'] >= (CONFIG['max_daily_loss_percent'] / 100):
            logging.warning('Maximum daily loss reached')
            return False
        if self.metrics['max_drawdown'] >= CONFIG['max_drawdown_percent']:
            logging.warning('Maximum drawdown reached')
            return False
        return True

def initialize_exchange():
    try:
        exchange = ccxt.binance({
            'apiKey': API_KEY,
            'secret': API_SECRET,
            'enableRateLimit': True,
            'options': {'defaultType': 'spot'}
        })
        if CONFIG.get('use_testnet', False):
            exchange.set_sandbox_mode(True)  # Enable testnet mode
        return exchange
    except ccxt.BaseError as e:
        error_message = f"Failed to initialize exchange: {str(e)}"
        logging.error(error_message)
        send_telegram_notification(error_message)
        return None

def adjust_trade_amount(amount_to_trade, latest_close_price, min_trade_amount, min_notional):
    """Adjust trade amount to meet minimum requirements"""
    try:
        decimals_allowed = 4
        amount_to_trade_formatted = round(amount_to_trade, decimals_allowed)
        notional_value = amount_to_trade_formatted * latest_close_price

        # If amount is below minimum, increase it to minimum
        if amount_to_trade_formatted < min_trade_amount:
            amount_to_trade_formatted = min_trade_amount
            notional_value = amount_to_trade_formatted * latest_close_price
            logging.info(f"Adjusted amount up to minimum: {amount_to_trade_formatted}")

        # If notional value is below minimum, adjust amount accordingly
        if notional_value < min_notional:
            amount_to_trade_formatted = math.ceil((min_notional / latest_close_price) * 10000) / 10000
            logging.info(f"Adjusted amount for minimum notional value: {amount_to_trade_formatted}")

        # Final validation
        final_notional = amount_to_trade_formatted * latest_close_price
        if amount_to_trade_formatted >= min_trade_amount and final_notional >= min_notional:
            logging.info(f"Final trade amount: {amount_to_trade_formatted} ({final_notional} USDT)")
            return amount_to_trade_formatted

        logging.warning(f"Could not meet minimum requirements: Amount={amount_to_trade_formatted}, Notional={final_notional}")
        return None

    except Exception as e:
        logging.error(f"Error in adjust_trade_amount: {str(e)}")
        return None

def safe_api_call(func, *args, **kwargs):
    retry_count = kwargs.pop('retry_count', 3)
    retry_delay = kwargs.pop('retry_delay', 5)
    exponential_backoff = kwargs.pop('exponential_backoff', True)

    last_error = None

    for attempt in range(retry_count):
        try:
            # Attempt the API call
            result = func(*args, **kwargs)

            # Validate the response
            if result is None:
                raise ValueError("API call returned None")

            # Log successful call after retries if it's not the first attempt
            if attempt > 0:
                logging.info(f"API call successful after {attempt + 1} attempts")

            return result

        except ccxt.NetworkError as e:
            last_error = e
            if attempt == retry_count - 1:
                logging.error(f"Network error persists after {retry_count} attempts: {str(e)}")
                break

            wait_time = retry_delay * (2 ** attempt if exponential_backoff else 1)
            logging.warning(f"Network error: {str(e)}. Retrying in {wait_time} seconds... (Attempt {attempt + 1}/{retry_count})")
            time.sleep(wait_time)

        except ccxt.RateLimitExceeded as e:
            last_error = e
            if attempt == retry_count - 1:
                logging.error(f"Rate limit exceeded after {retry_count} attempts: {str(e)}")
                break

            wait_time = 30 * (2 ** attempt if exponential_backoff else 1)
            logging.warning(f"Rate limit exceeded. Waiting {wait_time} seconds... (Attempt {attempt + 1}/{retry_count})")
            time.sleep(wait_time)

        except ccxt.ExchangeError as e:
            last_error = e
            if "insufficient balance" in str(e).lower():
                logging.error(f"Insufficient balance error: {str(e)}")
                raise  # Don't retry on balance errors

            if attempt == retry_count - 1:
                logging.error(f"Exchange error persists after {retry_count} attempts: {str(e)}")
                break

            wait_time = retry_delay * (2 ** attempt if exponential_backoff else 1)
            logging.warning(f"Exchange error: {str(e)}. Retrying in {wait_time} seconds... (Attempt {attempt + 1}/{retry_count})")
            time.sleep(wait_time)

        except ccxt.RequestTimeout as e:
            last_error = e
            if attempt == retry_count - 1:
                logging.error(f"Request timeout after {retry_count} attempts: {str(e)}")
                break

            wait_time = retry_delay * (2 ** attempt if exponential_backoff else 1)
            logging.warning(f"Request timeout: {str(e)}. Retrying in {wait_time} seconds... (Attempt {attempt + 1}/{retry_count})")
            time.sleep(wait_time)

        except Exception as e:
            last_error = e
            logging.critical(f"Unexpected error during API call [{func.__name__}]: {str(e)}")
            logging.critical(f"Stack trace: {traceback.format_exc()}")
            raise  # Don't retry on unexpected errors

    # If we've exhausted all retries, log the error and raise the last exception
    error_message = f"API call [{func.__name__}] failed after {retry_count} attempts. Last error: {str(last_error)}"
    logging.error(error_message)

    send_telegram_notification(f"Critical API Error: {error_message}")
    raise last_error

def validate_config():
    try:
        TradeExecution.validate_ema_strategy(CONFIG)

        required_fields = [
            'symbol', 'risk_percentage', 'min_balance',
            'max_daily_trades', 'max_daily_loss_percent'
        ]
        for field in required_fields:
            if field not in CONFIG:
                raise ValueError(f"Missing required config field: {field}")

        if CONFIG['min_balance'] < 0:
            raise ValueError("Min balance cannot be negative")

        if CONFIG['timeframe'] not in ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h']:
            raise ValueError("Invalid timeframe")

        if not (0 < CONFIG['risk_percentage'] <= 100):
            raise ValueError("Risk percentage must be between 0 and 100.")

        if not (0 < CONFIG['fee_rate'] < 1):
            raise ValueError("Fee rate must be a percentage less than 1.")

        if CONFIG['max_daily_loss_percent'] <= 0 or CONFIG['max_drawdown_percent'] <= 0:
            raise ValueError("Max daily loss and max drawdown must be positive numbers.")

        if CONFIG['ema_short_period'] <= 0 or CONFIG['ema_long_period'] <= 0:
            raise ValueError("EMA periods must be positive integers.")

        if CONFIG['max_spread_percent'] <= 0:
            raise ValueError("Max spread percent should be positive")

        if not (0 < CONFIG['max_position_size'] <= 1):
            raise ValueError("Max position size must be between 0 and 1")

        if CONFIG['max_daily_trades'] <= 0:
            raise ValueError("Max daily trades should be positive.")

        if CONFIG['stop_loss_percent'] < 0:
            raise ValueError("Stop loss percent should not be negative.")

        if CONFIG['max_consecutive_losses'] <= 0:
            raise ValueError("max_consecutive_losses must be positive")

        if CONFIG['daily_profit_target'] <= 0:
            raise ValueError("daily_profit_target must be positive")

        if CONFIG['market_impact_threshold'] <= 0:
            raise ValueError("market_impact_threshold must be positive")

        if CONFIG['position_sizing_atr_multiplier'] <= 0:
            raise ValueError("position_sizing_atr_multiplier must be positive")

        if CONFIG['max_open_orders'] <= 0:
            raise ValueError("max_open_orders must be positive")

        if not (0 < CONFIG['min_liquidity_ratio'] <= 1):
            raise ValueError("min_liquidity_ratio must be between 0 and 1")

        logging.info("Config validation passed")
        return True

    except Exception as e:
        logging.error(f"Config validation failed: {e}")
        return False


def get_min_trade_amount_and_notional(exchange, symbol):
    """Fetch minimum trade amount and notional value for a specific symbol."""
    try:
        markets = safe_api_call(exchange.load_markets)
        if not markets:
            logging.error("Markets not loaded.")
            return None, None

        market = markets.get(symbol)
        if not market:
            logging.error(f"Market data not available for symbol: {symbol}")
            return None, None

        logging.debug(f"Market data for {symbol}: {market}")

        min_amount = market['limits']['amount'].get('min')
        min_notional_value = None

        if 'info' in market and 'filters' in market['info']:
            for f in market['info']['filters']:
                if f['filterType'] == 'NOTIONAL':
                    min_notional_value = float(f['minNotional'])
                    break

        if min_amount is None:
            logging.error(f"Minimum amount not found for symbol: {symbol}")
        if min_notional_value is None:
            logging.error(f"NOTIONAL filter not found for symbol: {symbol}")

        return min_amount, min_notional_value
    except Exception as e:
        logging.error(f"Failed to fetch market info: {str(e)}")
        return None, None

def main(performance, trade_history):
    global last_reported_day
    recovery_delay = 60  # seconds
    max_retries = 3
    retry_count = 0

    while retry_count < max_retries:
        try:
            # Initialize exchange and trade execution
            exchange = initialize_exchange()
            if exchange is None:
                raise ValueError("Exchange initialization failed")

            symbol_base = CONFIG['symbol'].split('/')[0]
            trade_execution = TradeExecution(exchange, performance, trade_history)

            if not trade_execution.check_exchange_connection():
                logging.error("Exchange connection check failed")
                raise ValueError("Exchange connection is not stable")

            # Get current day
            current_day = datetime.now().date()

            # Check and report balance to Telegram if not already done today
            if last_reported_day is None or last_reported_day != current_day:
                trade_execution.report_balance_to_telegram()
                last_reported_day = current_day

            # Add time-based check
            if not trade_execution.can_trade_time_based():
                logging.info("Time-based trading restrictions in effect")
                return

            # Setup proper signal handling
            trade_execution.setup_signal_handlers()

            # Configuration validation
            global last_checked_time
            config_update, last_checked_time = check_for_config_updates(last_checked_time)
            if config_update or not validate_config():
                logging.error("Configuration validation failed")
                return

            # Performance checks
            if not performance.can_trade():
                logging.info("Trading limits reached, skipping trading cycle")
                return

            # Balance validation
            balance = safe_api_call(exchange.fetch_balance)
            if balance is None:
                raise ValueError("Failed to fetch balance")

            usdt_balance = balance['USDT']['free']
            if usdt_balance < CONFIG['min_balance']:
                logging.warning(f"Insufficient balance: {usdt_balance} USDT")
                return

            # Market data fetching and validation
            market_data = trade_execution.fetch_market_data(CONFIG['symbol'], CONFIG['timeframe'])
            if not trade_execution.validate_market_data(market_data):
                logging.error("Invalid market data structure")
                return

            trade_execution.market_data = market_data

            # Add market summary logging here
            trade_execution.log_market_summary(market_data)

            # Comprehensive trading conditions validation
            if not trade_execution.validate_trading_conditions(market_data):
                logging.info(f"Trading conditions not met for {CONFIG['symbol']}")
                return

            # Position sizing and validation
            current_price = market_data['close'].iloc[-1]
            position_sizing_result = trade_execution.calculate_position_size(
                balance=usdt_balance,
                current_price=current_price,
                market_data=market_data
            )

            if position_sizing_result[0] is None or position_sizing_result[1] is None:
                logging.warning("Failed to calculate valid position size")
                return

            optimal_position, amount_to_trade_formatted = position_sizing_result
            if trade_execution.validate_entry_conditions(market_data, amount_to_trade_formatted):

                # Technical analysis
                analysis_result = trade_execution.perform_technical_analysis(market_data)
                if analysis_result is None:
                    logging.error("Failed to perform technical analysis")
                    return

                # Check existing positions and manage them
                if trade_execution.has_open_positions(CONFIG['symbol']):
                    trade_execution.manage_existing_positions(
                        symbol=CONFIG['symbol'],
                        current_price=current_price,
                        market_data=market_data
                    )

                # Process trading signals
                if trade_execution.should_execute_trade(analysis_result, market_data):
                    trade_execution.execute_trade_with_safety(
                        side="buy",
                        amount=amount_to_trade_formatted,
                        symbol=CONFIG['symbol'],
                        current_price=current_price
                    )

                # Log trading metrics
                trade_execution.log_trading_metrics(
                    symbol_base=symbol_base,
                    optimal_position=optimal_position,
                    amount_to_trade=amount_to_trade_formatted,
                    current_price=current_price
                )

        except Exception as e:
            retry_count += 1
            error_message = f'Error in main loop (attempt {retry_count}/{max_retries}): {str(e)}'
            logging.error(error_message)
            send_telegram_notification(error_message)

            trade_execution.handle_trade_error(e, retry_count)

            if retry_count < max_retries:
                logging.info(f"Waiting {recovery_delay} seconds before retry...")
                time.sleep(recovery_delay)
                recovery_delay *= 2  # Exponential backoff
        finally:
            # Enhanced cleanup
            try:
                trade_execution.cleanup()
            except Exception as cleanup_error:
                logging.error(f"Error during cleanup: {str(cleanup_error)}")

# Ensure this is declared outside the function to maintain its state across iterations
last_reported_day = None

if __name__ == '__main__':
    performance = PerformanceMetrics()
    trade_history = {}
    last_checked_time = 0
    while True:
        main(performance, trade_history)
        time.sleep(60)
