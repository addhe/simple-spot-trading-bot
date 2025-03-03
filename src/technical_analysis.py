import numpy as np
import pandas as pd
from ta.trend import SMAIndicator
from ta.volatility import BollingerBands
from ta.momentum import RSIIndicator, StochasticRSIIndicator

class TechnicalAnalysis:
    def __init__(self,
                 bb_length=20,
                 bb_std=2.0,
                 short_ma_length=50,
                 long_ma_length=200,
                 rsi_length=14,
                 stoch_length=14,
                 smooth_k=3,
                 smooth_d=3,
                 vol_ma_short_length=5,
                 vol_ma_long_length=10,
                 stoch_overbought=80,
                 stoch_oversold=20):
        self.bb_length = bb_length
        self.bb_std = bb_std
        self.short_ma_length = short_ma_length
        self.long_ma_length = long_ma_length
        self.rsi_length = rsi_length
        self.stoch_length = stoch_length
        self.smooth_k = smooth_k
        self.smooth_d = smooth_d
        self.vol_ma_short_length = vol_ma_short_length
        self.vol_ma_long_length = vol_ma_long_length
        self.stoch_overbought = stoch_overbought
        self.stoch_oversold = stoch_oversold

    def analyze(self, df):
        # Calculate Bollinger Bands
        bb_indicator = BollingerBands(close=df['close'], window=self.bb_length, window_dev=self.bb_std)
        df['bb_middle'] = bb_indicator.bollinger_mavg()
        df['bb_upper'] = bb_indicator.bollinger_hband()
        df['bb_lower'] = bb_indicator.bollinger_lband()

        # Calculate Moving Averages
        df['short_ma'] = SMAIndicator(close=df['close'], window=self.short_ma_length).sma_indicator()
        df['long_ma'] = SMAIndicator(close=df['close'], window=self.long_ma_length).sma_indicator()

        # Calculate RSI
        df['rsi'] = RSIIndicator(close=df['close'], window=self.rsi_length).rsi()

        # Calculate Stochastic RSI
        stoch_rsi = StochasticRSIIndicator(
            close=df['close'],
            window=self.stoch_length,
            smooth1=self.smooth_k,
            smooth2=self.smooth_d
        )
        df['stoch_k'] = stoch_rsi.stochrsi_k() * 100
        df['stoch_d'] = stoch_rsi.stochrsi_d() * 100

        # Calculate Volume Moving Averages
        df['vol_ma_short'] = SMAIndicator(close=df['volume'], window=self.vol_ma_short_length).sma_indicator()
        df['vol_ma_long'] = SMAIndicator(close=df['volume'], window=self.vol_ma_long_length).sma_indicator()

        return df

    def get_signals(self, df, use_trend_filter=False, use_stoch_filter=True, use_volume_filter=False):
        latest = df.iloc[-1]

        # Trend condition
        trend_condition = True if not use_trend_filter else latest['short_ma'] > latest['long_ma']

        # Stochastic condition
        stoch_condition = True if not use_stoch_filter else latest['stoch_k'] < self.stoch_oversold

        # Volume condition
        volume_condition = True if not use_volume_filter else latest['volume'] > latest['vol_ma_short']

        # Buy signal
        buy_signal = (
            latest['close'] < latest['bb_lower'] and
            trend_condition and
            stoch_condition and
            volume_condition
        )

        # Sell conditions (opposite of buy conditions)
        sell_trend_condition = True if not use_trend_filter else latest['short_ma'] < latest['long_ma']
        sell_stoch_condition = True if not use_stoch_filter else latest['stoch_k'] > self.stoch_overbought
        sell_volume_condition = True if not use_volume_filter else latest['volume'] > latest['vol_ma_short']

        sell_signal = (
            latest['close'] > latest['bb_upper'] and
            sell_trend_condition and
            sell_stoch_condition and
            sell_volume_condition
        )

        return buy_signal, sell_signal
