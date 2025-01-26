"""  
Modul implementasi trading strategy dengan risk management terintegrasi.  
"""  
  
import asyncio  
import logging  
from abc import ABC, abstractmethod  
from datetime import datetime, timedelta  
from decimal import Decimal  
from typing import Dict, Optional, List, Type, AsyncGenerator, Any  
  
import pandas as pd  
from async_lru import alru_cache  
from pydantic import BaseModel, Field, validator  
  
from src.decorators import AsyncRetry, AsyncErrorHandler  
from src.market_data import MarketData  
from src.formatters import FormatterConfig, format_decimal, format_percentage  
from src.utils import validate_timestamp  
  
logger = logging.getLogger(__name__)  
  
class StrategyConfig(BaseModel):  
    """  
    Konfigurasi untuk trading strategy.  
    """  
    symbol: str = Field(..., description="Simbol aset yang akan ditrad")  
    timeframe: str = Field(..., description="Timeframe data historis")  
    confidence_threshold: float = Field(..., description="Threshold kepercayaan untuk signal")  
    stop_loss_percentage: float = Field(..., description="Persentase stop loss")  
    take_profit_percentage: float = Field(..., description="Persentase take profit")  
    tick_size: Decimal = Field(..., description="Ukuran tick untuk aset")  
    volatility_factor: float = Field(..., description="Faktor volatilitas untuk menghitung risk parameter")  
  
    @validator('timeframe')  
    def validate_timeframe(cls, v):  
        valid_timeframes = ['1m', '5m', '15m', '30m', '1h', '4h', '1d']  
        if v not in valid_timeframes:  
            raise ValueError(f"Timeframe {v} tidak valid. Pilih dari {valid_timeframes}")  
        return v  
  
class TradingStrategy(ABC):  
    """  
    Kelas abstrak untuk trading strategy.  
    """  
    def __init__(self, config: StrategyConfig):  
        self.config = config  
        self.market_data = MarketData(symbol=self.config.symbol, timeframe=self.config.timeframe)  
  
    @abstractmethod  
    async def generate_signals(self) -> AsyncGenerator[Dict[str, Any], None]:  
        """  
        Metode abstrak untuk menghasilkan sinyal trading.  
        """  
        pass  
  
    @abstractmethod  
    async def calculate_risk_parameters(self) -> Dict[str, Decimal]:  
        """  
        Metode abstrak untuk menghitung parameter risiko.  
        """  
        pass  
  
class MACrossoverStrategy(TradingStrategy):  
    """  
    Implementasi strategy Moving Average Crossover.  
    """  
    async def generate_signals(self) -> AsyncGenerator[Dict[str, Any], None]:  
        """  
        Menghasilkan sinyal berdasarkan crossover antara MA singkat dan MA panjang.  
        """  
        historical_data = await self.market_data.get_historical_data()  
        if historical_data.empty:  
            logger.warning("Data historis kosong untuk simbol %s", self.config.symbol)  
            return  
  
        historical_data['MA_short'] = historical_data['close'].rolling(window=12).mean()  
        historical_data['MA_long'] = historical_data['close'].rolling(window=26).mean()  
  
        for _, row in historical_data.iterrows():  
            if row['MA_short'] > row['MA_long']:  
                confidence = self.calculate_confidence(row['MA_short'], row['MA_long'])  
                if confidence > self.config.confidence_threshold:  
                    yield {  
                        'timestamp': row['timestamp'],  
                        'symbol': self.config.symbol,  
                        'signal': 'BUY',  
                        'confidence': confidence  
                    }  
            elif row['MA_short'] < row['MA_long']:  
                confidence = self.calculate_confidence(row['MA_short'], row['MA_long'])  
                if confidence > self.config.confidence_threshold:  
                    yield {  
                        'timestamp': row['timestamp'],  
                        'symbol': self.config.symbol,  
                        'signal': 'SELL',  
                        'confidence': confidence  
                    }  
  
    def calculate_confidence(self, ma_short: Decimal, ma_long: Decimal) -> float:  
        """  
        Menghitung kepercayaan berdasarkan selisih antara MA singkat dan MA panjang.  
        """  
        difference = abs(ma_short - ma_long)  
        return difference / ma_long  
  
    async def calculate_risk_parameters(self) -> Dict[str, Decimal]:  
        """  
        Menghitung parameter risiko berdasarkan volatilitas dan tick size.  
        """  
        historical_data = await self.market_data.get_historical_data()  
        if historical_data.empty:  
            logger.warning("Data historis kosong untuk simbol %s", self.config.symbol)  
            return {}  
  
        volatility = historical_data['close'].std()  
        stop_loss = self.config.tick_size * self.config.stop_loss_percentage  
        take_profit = self.config.tick_size * self.config.take_profit_percentage  
  
        return {  
            'stop_loss': stop_loss,  
            'take_profit': take_profit,  
            'volatility': format_decimal(volatility, precision=FormatterConfig.PRECISION)  
        }  
  
class StrategyFactory:  
    """  
    Factory class untuk membuat instance trading strategy.  
    """  
    @staticmethod  
    def create_strategy(strategy_type: str, config: StrategyConfig) -> TradingStrategy:  
        """  
        Membuat instance trading strategy berdasarkan tipe strategy.  
        """  
        if strategy_type == 'MACrossover':  
            return MACrossoverStrategy(config)  
        else:  
            raise ValueError(f"Tipe strategy {strategy_type} tidak dikenali")  
 