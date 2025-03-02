import asyncio
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from src.database_manager import db_manager
from src.ml_manager import MLManager
from src.logger import logger
from src.monitoring import metrics
from binance.exceptions import BinanceAPIException
from src.technical_analysis import TechnicalAnalysis

class TradeManager:
    def __init__(self, db_manager, client):
        self.db_manager = db_manager
        self.client = client
        self.logger = logger
        self.ml_manager = MLManager()
        self.timeframes = ['1m', '5m', '15m', '1h', '4h']
        self.min_score = 3  # Minimum score needed for buy signal
        self.position_sizing = PositionSizing()
        self.risk_manager = RiskManager()
        self.ta = TechnicalAnalysis()  # Initialize with default parameters

    async def analyze_market(self, symbol: str, current_price: float) -> Tuple[bool, float, Dict]:
        """Analyze market using multi-timeframe analysis and ML predictions"""
        try:
            total_score = 0
            signals = {}

            # Get historical data for all timeframes
            for timeframe in self.timeframes:
                # Get historical data from database
                data = await self._get_historical_data(symbol, timeframe)
                if data is None or len(data) < 50:
                    continue

                df = pd.DataFrame(data)

                # Get ML prediction
                prediction = self.ml_manager.predict(symbol, timeframe, df)

                # Calculate technical signals
                signals[timeframe] = await self._calculate_signals(df, prediction)

                # Weight the signals based on timeframe
                weight = self._get_timeframe_weight(timeframe)
                total_score += signals[timeframe]['score'] * weight

            # Normalize total score
            total_score = total_score / len(self.timeframes)

            # Get position size recommendation
            position_size = await self.position_sizing.calculate_position_size(
                symbol, current_price, total_score
            )

            # Check risk management
            should_trade, adjusted_size = await self.risk_manager.check_trade(
                symbol, current_price, position_size
            )

            return should_trade, adjusted_size, {
                'total_score': total_score,
                'signals': signals,
                'risk_metrics': self.risk_manager.get_metrics()
            }

        except Exception as e:
            logger.error(f"Error analyzing market for {symbol}: {str(e)}")
            metrics.record_error("market_analysis")
            return False, 0, {}

    async def _get_historical_data(self, symbol: str, timeframe: str) -> Optional[List[Dict]]:
        """Get historical data for a specific timeframe"""
        try:
            # Calculate time range based on timeframe
            end_time = datetime.utcnow()
            start_time = self._calculate_start_time(end_time, timeframe)

            # Get data from database
            return await db_manager.get_market_data(symbol, start_time, end_time)

        except Exception as e:
            logger.error(f"Error getting historical data for {symbol} {timeframe}: {str(e)}")
            return None

    async def _calculate_signals(self, df: pd.DataFrame, ml_prediction: Optional[float]) -> Dict:
        """Calculate technical signals and combine with ML prediction"""
        signals = {
            'rsi_signal': 0,
            'bb_signal': 0,
            'macd_signal': 0,
            'volume_signal': 0,
            'ml_signal': 0,
            'score': 0
        }

        # RSI Signal
        rsi = df['close'].rolling(window=14).apply(lambda x: pd.Series(x).ta.rsi().iloc[-1])
        if rsi.iloc[-1] < 30:
            signals['rsi_signal'] = 1

        # Bollinger Bands Signal
        bb = df['close'].rolling(window=20).apply(
            lambda x: pd.Series(x).ta.bbands(length=20, std=2)
        )
        if df['close'].iloc[-1] < bb.iloc[-1]['BBL_20_2.0']:
            signals['bb_signal'] = 1

        # MACD Signal
        macd = df['close'].rolling(window=26).apply(
            lambda x: pd.Series(x).ta.macd().iloc[-1]
        )
        if macd.iloc[-1] > 0:
            signals['macd_signal'] = 1

        # Volume Signal
        volume_sma = df['volume'].rolling(window=20).mean()
        if df['volume'].iloc[-1] > volume_sma.iloc[-1] * 1.5:
            signals['volume_signal'] = 1

        # ML Signal
        if ml_prediction is not None and ml_prediction > 0.7:
            signals['ml_signal'] = 1

        # Calculate total score
        signals['score'] = sum([
            signals['rsi_signal'],
            signals['bb_signal'],
            signals['macd_signal'],
            signals['volume_signal'],
            signals['ml_signal']
        ])

        return signals

    def _get_timeframe_weight(self, timeframe: str) -> float:
        """Get weight for a specific timeframe"""
        weights = {
            '1m': 0.1,
            '5m': 0.15,
            '15m': 0.2,
            '1h': 0.25,
            '4h': 0.3
        }
        return weights.get(timeframe, 0.1)

    def _calculate_start_time(self, end_time: datetime, timeframe: str) -> datetime:
        """Calculate start time based on timeframe"""
        multipliers = {
            '1m': 60,
            '5m': 300,
            '15m': 900,
            '1h': 3600,
            '4h': 14400
        }

        # Get enough data for technical analysis
        candles_needed = 100
        seconds = multipliers.get(timeframe, 60) * candles_needed
        return end_time - timedelta(seconds=seconds)

    def get_historical_data(self, symbol, interval='1h', limit=500):
        """Get historical klines/candlestick data"""
        try:
            klines = self.client.get_klines(
                symbol=symbol,
                interval=interval,
                limit=limit
            )

            df = pd.DataFrame(klines, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_volume', 'trades', 'buy_base_volume',
                'buy_quote_volume', 'ignore'
            ])

            # Convert to float
            df['close'] = df['close'].astype(float)
            df['volume'] = df['volume'].astype(float)
            df['high'] = df['high'].astype(float)
            df['low'] = df['low'].astype(float)

            return df

        except Exception as e:
            self.logger.error(f"Error getting historical data for {symbol}: {e}")
            return None

    def process_trade(self, symbol, current_price, position_size=None):
        """Process trade decision based on technical analysis"""
        try:
            # Get historical data
            df = self.get_historical_data(symbol)
            if df is None or len(df) < 200:  # Need enough data for long MA
                return None

            # Calculate technical indicators
            df = self.ta.analyze(df)

            # Get buy/sell signals
            buy_signal, sell_signal = self.ta.get_signals(
                df,
                use_trend_filter=False,  # Can be configured based on preference
                use_stoch_filter=True,
                use_volume_filter=False
            )

            # Determine action based on signals
            if position_size and position_size > 0:
                if sell_signal:
                    return "SELL"
            else:
                if buy_signal:
                    return "BUY"

            return None

        except Exception as e:
            self.logger.error(f"Error processing trade for {symbol}: {e}")
            return None

    def execute_buy(self, symbol, quantity):
        """Execute buy order"""
        try:
            order = self.client.create_order(
                symbol=symbol,
                side='BUY',
                type='MARKET',
                quantity=quantity
            )

            # Log the trade
            self.db_manager.insert_trade(
                symbol=symbol,
                side='BUY',
                quantity=quantity,
                price=float(order['fills'][0]['price']),
                timestamp=datetime.now()
            )

            return order

        except BinanceAPIException as e:
            self.logger.error(f"Binance API error executing buy for {symbol}: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Error executing buy for {symbol}: {e}")
            return None

    def execute_sell(self, symbol, quantity):
        """Execute sell order"""
        try:
            order = self.client.create_order(
                symbol=symbol,
                side='SELL',
                type='MARKET',
                quantity=quantity
            )

            # Log the trade
            self.db_manager.insert_trade(
                symbol=symbol,
                side='SELL',
                quantity=quantity,
                price=float(order['fills'][0]['price']),
                timestamp=datetime.now()
            )

            return order

        except BinanceAPIException as e:
            self.logger.error(f"Binance API error executing sell for {symbol}: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Error executing sell for {symbol}: {e}")
            return None

class PositionSizing:
    def __init__(self):
        self.max_position_size = 0.1  # 10% of available balance
        self.min_position_size = 0.01  # 1% of available balance
        self.volatility_factor = 0.5  # Reduce position size in high volatility

    async def calculate_position_size(self, symbol: str, current_price: float, signal_strength: float) -> float:
        """Calculate position size based on Kelly Criterion and volatility"""
        try:
            # Get historical data for volatility calculation
            data = await db_manager.get_market_data(
                symbol,
                datetime.utcnow() - timedelta(days=30),
                datetime.utcnow()
            )

            if not data:
                return 0

            df = pd.DataFrame(data)

            # Calculate volatility
            returns = df['close'].pct_change()
            volatility = returns.std()

            # Calculate win rate and average R:R from historical trades
            trades = await db_manager.get_trade_history(symbol, limit=100)
            if trades:
                trades_df = pd.DataFrame(trades)
                win_rate = len(trades_df[trades_df['profit_loss'] > 0]) / len(trades_df)
                avg_win = trades_df[trades_df['profit_loss'] > 0]['profit_loss'].mean()
                avg_loss = abs(trades_df[trades_df['profit_loss'] < 0]['profit_loss'].mean())

                if avg_loss == 0:
                    kelly_fraction = 0
                else:
                    # Kelly Criterion calculation
                    r_ratio = avg_win / avg_loss
                    kelly_fraction = win_rate - ((1 - win_rate) / r_ratio)
            else:
                kelly_fraction = 0.5  # Default if no historical data

            # Adjust position size based on signal strength and volatility
            position_size = kelly_fraction * self.max_position_size
            position_size *= signal_strength  # Adjust based on signal strength
            position_size *= (1 - volatility * self.volatility_factor)  # Reduce for high volatility

            # Ensure position size is within limits
            position_size = max(min(position_size, self.max_position_size), self.min_position_size)

            return position_size

        except Exception as e:
            logger.error(f"Error calculating position size for {symbol}: {str(e)}")
            return self.min_position_size

class RiskManager:
    def __init__(self):
        self.max_daily_loss = 0.02  # 2% max daily loss
        self.max_position_loss = 0.01  # 1% max loss per position
        self.max_correlated_exposure = 0.15  # 15% max exposure to correlated assets
        self.metrics = {}

    async def check_trade(self, symbol: str, current_price: float, position_size: float) -> Tuple[bool, float]:
        """Check if trade meets risk management criteria"""
        try:
            # Calculate daily P&L
            daily_pl = await self._calculate_daily_pl()
            if abs(daily_pl) > self.max_daily_loss:
                return False, 0

            # Check correlation risk
            correlated_exposure = await self._calculate_correlated_exposure(symbol)
            if correlated_exposure > self.max_correlated_exposure:
                # Adjust position size to meet correlation limits
                adjusted_size = position_size * (self.max_correlated_exposure / correlated_exposure)
                position_size = min(position_size, adjusted_size)

            # Update metrics
            self.metrics = {
                'daily_pl': daily_pl,
                'correlated_exposure': correlated_exposure
            }

            return True, position_size

        except Exception as e:
            logger.error(f"Error checking risk management for {symbol}: {str(e)}")
            return False, 0

    async def _calculate_daily_pl(self) -> float:
        """Calculate daily P&L"""
        try:
            today = datetime.utcnow().date()
            trades = await db_manager.get_trade_history(None, limit=1000)

            if not trades:
                return 0

            trades_df = pd.DataFrame(trades)
            today_trades = trades_df[pd.to_datetime(trades_df['exit_time']).dt.date == today]

            return today_trades['profit_loss'].sum()

        except Exception as e:
            logger.error(f"Error calculating daily P&L: {str(e)}")
            return 0

    async def _calculate_correlated_exposure(self, symbol: str) -> float:
        """Calculate exposure to correlated assets"""
        # This is a simplified version. In reality, you'd want to:
        # 1. Maintain a correlation matrix
        # 2. Calculate true portfolio correlation
        # 3. Consider market regimes
        return 0.1  # Placeholder

    def get_metrics(self) -> Dict:
        """Get current risk metrics"""
        return self.metrics

# Initialize trade manager
trade_manager = TradeManager(db_manager, client)
